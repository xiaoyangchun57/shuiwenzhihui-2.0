"""
水利运维智慧运营平台 - 投标演示后端
Flask RESTful API + SQLite + APScheduler

==================== 完整API端点文档 ====================

【系统与概览】
  GET  /api/health
       健康检查。返回 {'status':'ok','time':'...'}

  GET  /api/dashboard/summary
       仪表盘汇总。返回总览数据、最新告警TOP5、待处理工单TOP5、今日巡检统计

  GET  /api/data/overview
       数据概览。返回站点数/在线数、设备数/在线数、活跃告警数、进行中工单数

【站点管理】
  GET  /api/sites
       所有站点列表。返回站点基本信息及设备数量

  GET  /api/sites/<site_id>
       单个站点详情。返回站点信息、设备列表、活跃告警数、进行中工单数

【实时数据】
  GET  /api/data/realtime
       各站点最新传感器数据。返回每个站点的最新一条数据（metric/value/unit/time）

  GET  /api/data/site/<site_id>?limit=50
       指定站点最近N条数据（默认50条）。返回metric/value/unit/recorded_at数组

【告警管理】
  GET  /api/alerts?status=pending&limit=50
       告警列表。支持按status筛选（pending/acknowledged/resolved），按等级priority排序

  POST /api/alerts/<alert_id>/acknowledge
       确认告警。将告警状态改为acknowledged

  GET  /api/alerts/statistics
       告警统计。返回total、by_level(red/orange/yellow/blue)、by_status(pending/acknowledged/resolved)

【工单管理】
  GET  /api/workorders?status=pending&limit=50
       工单列表。支持按status筛选，返回工单及关联站点名

  POST /api/workorders
       创建工单。请求体JSON: {site_id,source,event_type,level,title,description,images,assignee}
       自动生成工单号和SLA截止时间，返回{'success':True,'order_no':'WO-...'}

  PUT  /api/workorders/<order_no>/status
       更新工单状态。请求体JSON: {status,remark?,satisfaction?}
       状态流转：pending->accepted->generated->dispatched->in_progress->reviewing->acceptance->closed

  GET  /api/workorders/statistics
       工单统计。返回total、by_status各状态计数、today_new、today_closed

【巡检管理】
  GET  /api/inspections
       巡检计划列表。返回计划及完成进度(total_items/completed_items)

  POST /api/inspections
       创建巡检计划。请求体JSON: {plan_name,site_id,type,start_date,end_date,check_items?}
       自动生成检查任务项，返回{'success':True,'plan_id':N}

  GET  /api/inspections/<plan_id>/tasks
       巡检任务列表。返回指定计划下所有检查项

  PUT  /api/inspections/tasks/<task_id>
       提交巡检结果。请求体JSON: {result,photo?,gps_lat?,gps_lng?,check_time?,remark?}

  GET  /api/inspections/statistics
       巡检统计。返回计划数/完成数、任务数/完成数、异常数

【热线管理】
  GET  /api/hotline/events?limit=50
       热线事件列表。返回热线来电记录

  POST /api/hotline/events
       登记热线事件。请求体JSON: {caller_name,caller_phone,event_type,description,location,operator}

  POST /api/hotline/events/<event_id>/convert
       热线转工单。请求体JSON: {level,assignee}
       自动生成工单并更新热线事件状态，返回{'success':True,'order_no':'WO-...'}

【天气数据】 -- NEW
  GET  /api/weather
       天气数据。返回当前天气（温度/湿度/风速/风向/降水量/气压/天气类型）、
       未来24小时逐小时预报数组、天气预警列表（暴雨/大风/高温）

【水质监测】 -- NEW
  GET  /api/water-quality?site_id=<可选>
       水质监测数据。返回供水站/水库的水质指标（浊度/pH/余氯/氨氮/COD），
       每个指标含当前值、记录时间和7日均值对比。支持按site_id筛选

【设备监控】 -- NEW
  GET  /api/devices/status
       设备状态汇总。返回设备总数/在线数/离线数、各类型设备统计、离线设备详情列表

【数据质量】 -- NEW
  GET  /api/data-quality
       数据质量报告。返回今日数据到达率/完整率/及时率、异常站点列表、最近24小时质量趋势
"""
import os
import json
import sqlite3
import random
import time
import threading
from datetime import datetime, timedelta
from contextlib import contextmanager

from flask import Flask, jsonify, request, g, send_from_directory
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
import os

app = Flask(__name__, static_folder=None)  # 禁用默认static，手动控制
CORS(app)

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'water.db')
scheduler = BackgroundScheduler()
scheduler.start()

# ===================== 状态跟踪（每个站点的当前监测值趋势） =====================

_site_state = {}
def get_site_trend(site_id, metric, base, var, min_v=None, max_v=None):
    """生成有趋势的传感器数据：当前值 = 前值 + 随机趋势，避免纯随机跳变"""
    key = (site_id, metric)
    if key not in _site_state:
        _site_state[key] = base
    was = _site_state[key]
    drift = random.uniform(-var, var)
    val = round(was + drift, 2)
    if min_v is not None:
        val = max(min_v, val)
    if max_v is not None:
        val = min(max_v, val)
    _site_state[key] = val
    return val

# ===================== Database =====================

@contextmanager
def get_db():
    db = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=30000")
    db.execute("PRAGMA synchronous=NORMAL")
    db.execute("PRAGMA cache_size=-8000")
    try:
        yield db
    finally:
        db.close()

def init_db():
    with get_db() as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS sites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                lat REAL, lng REAL,
                district TEXT DEFAULT '',
                river TEXT DEFAULT '',
                status TEXT DEFAULT 'online',
                manager TEXT, phone TEXT,
                last_heartbeat TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS sensor_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id INTEGER NOT NULL,
                metric TEXT NOT NULL,
                value REAL NOT NULL,
                unit TEXT,
                threshold_low REAL,
                threshold_high REAL,
                threshold_critical REAL,
                recorded_at TEXT NOT NULL,
                FOREIGN KEY (site_id) REFERENCES sites(id)
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id INTEGER NOT NULL,
                metric TEXT NOT NULL,
                value REAL NOT NULL,
                level TEXT NOT NULL,  -- blue/yellow/orange/red
                message TEXT NOT NULL,
                status TEXT DEFAULT 'pending',  -- pending/acknowledged/resolved
                created_at TEXT DEFAULT (datetime('now','localtime')),
                resolved_at TEXT,
                FOREIGN KEY (site_id) REFERENCES sites(id)
            );

            CREATE TABLE IF NOT EXISTS work_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_no TEXT UNIQUE NOT NULL,
                site_id INTEGER,
                source TEXT NOT NULL,  -- auto/patrol/hotline/superior
                event_type TEXT NOT NULL,
                level TEXT NOT NULL,  -- normal/urgent/critical
                title TEXT NOT NULL,
                description TEXT,
                images TEXT,
                assignee TEXT,
                status TEXT DEFAULT 'pending',  -- pending/accepted/generated/dispatched/in_progress/reviewing/acceptance/closed
                sla_deadline TEXT,
                resolved_at TEXT,
                remark TEXT,
                satisfaction INTEGER,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (site_id) REFERENCES sites(id)
            );

            CREATE TABLE IF NOT EXISTS inspection_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_name TEXT NOT NULL,
                site_id INTEGER NOT NULL,
                type TEXT NOT NULL,  -- daily/weekly/monthly/special
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (site_id) REFERENCES sites(id)
            );

            CREATE TABLE IF NOT EXISTS inspection_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER NOT NULL,
                site_id INTEGER NOT NULL,
                inspector TEXT,
                check_item TEXT NOT NULL,
                result TEXT,  -- normal/abnormal/na
                photo TEXT,
                gps_lat REAL, gps_lng REAL,
                check_time TEXT,
                remark TEXT,
                FOREIGN KEY (plan_id) REFERENCES inspection_plans(id),
                FOREIGN KEY (site_id) REFERENCES sites(id)
            );

            CREATE TABLE IF NOT EXISTS hotline_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                caller_name TEXT,
                caller_phone TEXT,
                event_type TEXT NOT NULL,
                description TEXT NOT NULL,
                location TEXT,
                status TEXT DEFAULT 'registered',  -- registered/dispatched/closed
                related_order_no TEXT,
                operator TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS device_shadows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id INTEGER NOT NULL,
                device_code TEXT UNIQUE NOT NULL,
                device_name TEXT NOT NULL,
                device_type TEXT,
                status TEXT DEFAULT 'online',
                battery REAL,
                last_data_time TEXT,
                FOREIGN KEY (site_id) REFERENCES sites(id)
            );

            -- 天气数据表 (新增)
            CREATE TABLE IF NOT EXISTS weather_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                temperature REAL,
                humidity REAL,
                wind_speed REAL,
                wind_direction TEXT,
                precipitation REAL,
                pressure REAL,
                weather_type TEXT,
                warning_info TEXT,
                recorded_at TEXT DEFAULT (datetime('now','localtime'))
            );

            -- 运维计划表
            CREATE TABLE IF NOT EXISTS maintenance_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id INTEGER NOT NULL,
                plan_name TEXT NOT NULL,
                category TEXT NOT NULL,
                frequency TEXT NOT NULL,
                due_date TEXT,
                status TEXT DEFAULT 'pending',
                assignee TEXT,
                completed_at TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (site_id) REFERENCES sites(id)
            );

            -- 数据到报表
            CREATE TABLE IF NOT EXISTS data_arrival (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                metric TEXT NOT NULL,
                expected_count INTEGER DEFAULT 0,
                actual_count INTEGER DEFAULT 0,
                arrival_rate REAL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (site_id) REFERENCES sites(id)
            );

            -- 水位校验表
            CREATE TABLE IF NOT EXISTS water_level_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id INTEGER NOT NULL,
                manual_level REAL,
                telemetry_level REAL,
                diff REAL,
                status TEXT DEFAULT 'normal',
                adjust_action TEXT,
                operator TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (site_id) REFERENCES sites(id)
            );

            -- 时间线事件表
            CREATE TABLE IF NOT EXISTS timeline_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL,
                source_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                operator TEXT,
                remark TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );
        ''')
        # 兼容已有数据库：尝试添加列，忽略已存在的错误
        for col_sql in [
            "ALTER TABLE alerts ADD COLUMN urge_count INTEGER DEFAULT 0",
            "ALTER TABLE alerts ADD COLUMN last_urged_at TEXT",
            "ALTER TABLE alerts ADD COLUMN related_order_no TEXT",
            "ALTER TABLE alerts ADD COLUMN response_deadline TEXT",
            "ALTER TABLE maintenance_plans ADD COLUMN urge_count INTEGER DEFAULT 0",
            "ALTER TABLE maintenance_plans ADD COLUMN last_urged_at TEXT",
            "ALTER TABLE maintenance_plans ADD COLUMN review_status TEXT DEFAULT NULL",
            "ALTER TABLE maintenance_plans ADD COLUMN review_comment TEXT DEFAULT NULL",
        ]:
            try:
                db.execute(col_sql)
            except:
                pass
        db.commit()

# ===================== Seed Data =====================

_NC_CENTER = (28.68, 115.86)  # 南昌市中心

def _gen_nanchang_sites():
    """生成南昌市300+水文监测站点"""
    sites = []
    # 赣江干流关键节点（南→北）
    ganjiang = [
        (28.20, 115.95), (28.24, 115.93), (28.28, 115.90), (28.32, 115.88),
        (28.36, 115.86), (28.40, 115.85), (28.44, 115.84), (28.48, 115.85),
        (28.52, 115.87), (28.56, 115.90), (28.60, 115.93), (28.64, 115.96),
        (28.68, 115.99), (28.72, 116.02), (28.76, 116.04), (28.80, 116.06),
        (28.84, 116.08), (28.88, 116.10), (28.92, 116.12),
    ]
    # 抚河关键节点（东南→西北）
    fuhe = [
        (28.30, 116.20), (28.34, 116.16), (28.38, 116.12), (28.42, 116.08),
        (28.46, 116.04), (28.50, 116.00), (28.54, 115.96),
    ]
    # 鄱阳湖沿岸（东北）
    poyang = [
        (28.90, 116.08), (28.95, 116.12), (29.00, 116.16), (29.05, 116.20),
        (29.10, 116.18), (29.15, 116.14),
    ]
    # 区县域坐标范围
    districts = {
        '西湖': (28.65, 115.87), '东湖': (28.69, 115.89), '青山湖': (28.70, 115.95),
        '青云谱': (28.63, 115.92), '新建': (28.70, 115.82), '南昌县': (28.55, 115.95),
        '进贤': (28.38, 116.24), '安义': (28.85, 115.55), '湾里': (28.72, 115.73),
    }
    sid = 0
    # 生成雨量站（120个）：沿河高密度+区域均匀
    for i, (blat, blng) in enumerate(ganjiang):
        for j in range(4):  # 每段4个
            lat = blat + random.uniform(-0.04, 0.04)
            lng = blng + random.uniform(-0.04, 0.04)
            sid += 1; dname = random.choice(list(districts.keys()))
            sites.append((f'YL-{dname[:2].upper()}-{sid:03d}', f'{dname}雨量站{sid}', 'rainfall', round(lat,4), round(lng,4), dname, '赣江'))
    # 沿抚河补充
    for i, (blat, blng) in enumerate(fuhe):
        for j in range(3):
            lat = blat + random.uniform(-0.03, 0.03)
            lng = blng + random.uniform(-0.03, 0.03)
            sid += 1; dname = random.choice(['南昌县','进贤'])
            sites.append((f'YL-{dname[:2].upper()}-{sid:03d}', f'{dname}雨量站{sid}', 'rainfall', round(lat,4), round(lng,4), dname, '抚河'))
    # 市区低密度补充到120个
    while len([s for s in sites if s[2]=='rainfall']) < 120:
        lat = random.uniform(28.45, 28.95); lng = random.uniform(115.50, 116.40)
        # 避免离已有站点太近
        too_close = any(abs(s[3]-lat)+abs(s[4]-lng)<0.06 for s in sites)
        if not too_close:
            sid += 1
            dname = min(districts.keys(), key=lambda d: abs(lat-districts[d][0])+abs(lng-districts[d][1]))
            sites.append((f'YL-{dname[:2].upper()}-{sid:03d}', f'{dname}雨量站{sid}', 'rainfall', round(lat,4), round(lng,4), dname, ''))

    # 生成水位站（90个）：赣江沿岸高密度
    for i, (blat, blng) in enumerate(ganjiang):
        for j in range(3):
            lat = blat + random.uniform(-0.015, 0.015)
            lng = blng + random.uniform(-0.015, 0.015)
            sid += 1; dname = random.choice(list(districts.keys()))
            sites.append((f'SW-{dname[:2].upper()}-{sid:03d}', f'{dname}水位站{sid}', 'water_level', round(lat,4), round(lng,4), dname, '赣江'))
    # 抚河补充
    for i, (blat, blng) in enumerate(fuhe):
        for j in range(2):
            lat = blat + random.uniform(-0.015, 0.015)
            lng = blng + random.uniform(-0.015, 0.015)
            sid += 1; dname = random.choice(['南昌县','进贤'])
            sites.append((f'SW-{dname[:2].upper()}-{sid:03d}', f'{dname}水位站{sid}', 'water_level', round(lat,4), round(lng,4), dname, '抚河'))
    # 鄱阳湖补充
    for i, (blat, blng) in enumerate(poyang):
        sid += 1
        sites.append((f'SW-PY-{sid:03d}', f'鄱阳水位站{sid}', 'water_level', round(blat+random.uniform(-0.02,0.02),4), round(blng+random.uniform(-0.02,0.02),4), '进贤', '鄱阳湖'))

    # 生成水文站（45个）：关键断面
    key_points = ganjiang[::2] + fuhe[::2] + poyang[::2]
    for i, (blat, blng) in enumerate(key_points):
        for j in range(2 if i < 8 else 1):
            lat = blat + random.uniform(-0.01, 0.01); lng = blng + random.uniform(-0.01, 0.01)
            sid += 1; dname = random.choice(list(districts.keys()))
            river = '赣江' if i < len(ganjiang)//2 else ('抚河' if i < len(ganjiang)//2+len(fuhe)//2 else '鄱阳湖')
            sites.append((f'HW-{dname[:2].upper()}-{sid:03d}', f'{dname}水文站{sid}', 'hydrology', round(lat,4), round(lng,4), dname, river))

    # 生成墒情站（30个）：农田/灌区
    farm_areas = [(28.45,115.85),(28.50,115.90),(28.55,115.92),(28.60,115.88),(28.65,115.80),
                  (28.70,115.78),(28.75,115.85),(28.40,116.10),(28.45,116.05),(28.35,116.15)]
    for i in range(30):
        if i < len(farm_areas):
            lat, lng = farm_areas[i]
        else:
            lat = random.uniform(28.35,28.80); lng = random.uniform(115.60,116.20)
        lat += random.uniform(-0.02,0.02); lng += random.uniform(-0.02,0.02)
        sid += 1; dname = min(districts.keys(), key=lambda d: abs(lat-districts[d][0])+abs(lng-districts[d][1]))
        sites.append((f'SQ-{dname[:2].upper()}-{sid:03d}', f'{dname}墒情站{sid}', 'soil_moisture', round(lat,4), round(lng,4), dname, ''))

    # 生成蒸发站（15个）：空旷地带
    open_areas = [(28.72,115.73),(28.80,115.60),(28.60,115.70),(28.50,115.75),
                  (28.90,115.90),(28.75,116.00),(28.40,115.88),(28.55,115.65),
                  (28.70,115.55),(28.85,115.70),(28.45,115.78),(28.62,115.82),
                  (28.92,115.95),(28.52,115.68),(28.78,115.92)]
    for i, (lat, lng) in enumerate(open_areas):
        sid += 1; dname = min(districts.keys(), key=lambda d: abs(lat-districts[d][0])+abs(lng-districts[d][1]))
        sites.append((f'ZF-{dname[:2].upper()}-{sid:03d}', f'{dname}蒸发站{sid}', 'evaporation', round(lat+random.uniform(-0.01,0.01),4), round(lng+random.uniform(-0.01,0.01),4), dname, ''))

    return sites

def seed_data():
    """种子数据：300+站点 + 设备 + 工单 + 热线事件（仅首次运行）"""
    with get_db() as db:
        count = db.execute("SELECT COUNT(*) FROM sites").fetchone()[0]
        if count > 0:
            print("[Seed] 站点数据已存在，跳过站点/设备/工单种子数据")
            return

        # === 300+站点生成 ===
        all_sites = _gen_nanchang_sites()
        for s in all_sites:
            db.execute(
                "INSERT INTO sites (code,name,type,lat,lng,district,river,manager,phone) VALUES (?,?,?,?,?,?,?,?,?)",
                (*s, '管理员', f'1{random.randint(30,99)}0000{random.randint(1000,9999)}')
            )
        print(f"[Seed] 生成 {len(all_sites)} 个站点")

        # === 设备生成（每站1-4个设备） ===
        type_devices = {
            'rainfall': [('翻斗式雨量计','rainfall_gauge'),('电子雨量计','electronic_rainfall')],
            'water_level': [('雷达水位计','radar_water_level'),('压力式水位计','pressure_water_level'),('流速计','flow_meter')],
            'hydrology': [('水文综合采集仪','hydro_collector'),('流速仪','current_meter'),('雨量计','rainfall_meter'),('水位计','water_level_meter')],
            'soil_moisture': [('土壤水分传感器','soil_moisture_sensor'),('土壤温度计','soil_temperature')],
            'evaporation': [('蒸发皿','evaporation_pan'),('气象百叶箱','weather_screen'),('风速仪','anemometer')],
        }
        all_sites_db = db.execute("SELECT id, code, type FROM sites").fetchall()
        for site in all_sites_db:
            devs = type_devices.get(site['type'], [('通用传感器','generic')])
            for i, (dname, dtype) in enumerate(devs):
                db.execute(
                    "INSERT INTO device_shadows (site_id,device_code,device_name,device_type,status,battery) VALUES (?,?,?,?,?,?)",
                    (site['id'], f"{site['code']}-{i+1:02d}{dtype[:4].upper()}", dname, dtype,
                     'online', round(random.uniform(60,100), 0))
                )

        # 工单种子数据
        orders = [
            ('WO-20260611-001',1,'auto','设备故障','normal','水位计数据中断','青山水库雷达水位计连续30分钟无数据上报','', '张建国','dispatched','2026-06-11 16:00','2026-06-11 08:30'),
            ('WO-20260611-002',4,'patrol','渗漏隐患','urgent','堤防B段发现渗漏点','巡查发现滨江堤防B段K3+200处堤脚渗水，面积约0.3m²','', '赵永刚','in_progress','2026-06-11 20:00','2026-06-11 09:15'),
            ('WO-20260611-003',6,'auto','设备告警','normal','泵站振动异常','新城泵站3号机组振动值达到8.2mm/s，超过警戒线7.0mm/s','', '王志明','accepted','2026-06-12 12:00','2026-06-11 10:00'),
            ('WO-20260611-004',10,'hotline','水质异常','urgent','供水站出水浊度偏高','市民热线反映自来水发黄，经核实浊度1.8NTU超0.5NTU标准','', '周晓华','in_progress','2026-06-11 22:00','2026-06-10 14:00'),
            ('WO-20260611-005',1,'superior','安全检查','normal','上级要求汛前全面检查','市水利局下发《关于做好2026年汛前水利工程安全检查的通知》','', '张建国','generated','2026-06-15 18:00','2026-06-10 16:00'),
        ]
        for o in orders:
            db.execute(
                "INSERT INTO work_orders (order_no,site_id,source,event_type,level,title,description,images,assignee,status,sla_deadline,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                o
            )

        # 热线事件
        hotlines = [
            ('张先生','13900001100','水质问题','家里的自来水发黄，已经持续两天了','城南街道阳光小区','registered', '', '李敏','2026-06-10 14:05'),
            ('李女士','13900002200','设施损坏','河道护栏被撞坏，存在安全隐患','滨江路新华桥东侧','dispatched','WO-20260611-004','李敏','2026-06-10 16:30'),
            ('陈先生','13900003300','违规举报','有人在河道内非法采砂','滨江堤防B段下游','registered', '', '王芳','2026-06-11 08:15'),
            ('匿名','', '水位异常','东湖水位这两天涨得很快，担心漫堤','东湖公园湖区','registered', '', '王芳','2026-06-11 09:30'),
        ]
        for h in hotlines:
            db.execute(
                "INSERT INTO hotline_events (caller_name,caller_phone,event_type,description,location,status,related_order_no,operator,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                h
            )

        db.commit()
        print("[Seed] Database seeded with initial data.")

def seed_inspections():
    """巡检种子数据（独立判断，可重复运行）"""
    with get_db() as db:
        cnt = db.execute("SELECT COUNT(*) FROM inspection_plans").fetchone()[0]
        if cnt == 0:
                insp_plans = [
                    ('2026年6月青山水库日常巡检',1,'daily','2026-06-10','2026-06-10','completed'),
                    ('2026年6月青山水库周巡检',1,'weekly','2026-06-08','2026-06-14','in_progress'),
                    ('2026年6月梅湖水库日常巡检',2,'daily','2026-06-11','2026-06-11','pending'),
                    ('2026年6月城北水闸日常巡检',3,'daily','2026-06-10','2026-06-10','completed'),
                    ('2026年6月滨江堤防A段巡检',4,'weekly','2026-06-09','2026-06-15','in_progress'),
                    ('2026年6月新城泵站巡检',6,'daily','2026-06-11','2026-06-11','pending'),
                    ('2026年6月城南供水站巡检',10,'daily','2026-06-10','2026-06-10','completed'),
                ]
                insp_items_map = {
                    'reservoir': ['坝体外观检查','溢洪道检查','放水设施检查','监测设备检查','防汛物资检查','管理设施检查'],
                    'sluice': ['闸门启闭检查','电气设备检查','上下游检查','监测设备检查','管理设施检查'],
                    'dike': ['堤身外观检查','堤脚检查','排水设施检查','监测设备检查'],
                    'pump': ['机组运行检查','电气设备检查','管道阀门检查','自动化系统检查'],
                    'water_supply': ['取水口检查','净化设备检查','加药系统检查','水质检测','管理设施检查'],
                }
                site_types = {s['id']: s['type'] for s in db.execute("SELECT id,type FROM sites").fetchall()}
                for plan in insp_plans:
                    pname, psid, ptype, pstart, pend, pstatus = plan
                    cur = db.execute(
                        "INSERT INTO inspection_plans (plan_name,site_id,type,start_date,end_date,status) VALUES (?,?,?,?,?,?)",
                        (pname, psid, ptype, pstart, pend, pstatus)
                    )
                    pid = cur.lastrowid
                    items = insp_items_map.get(site_types.get(psid, 'reservoir'), insp_items_map['reservoir'])
                    for item in items:
                        db.execute(
                            "INSERT INTO inspection_tasks (plan_id,site_id,check_item,result,remark,check_time) VALUES (?,?,?,?,?,?)",
                            (pid, psid, item, 'normal' if pstatus == 'completed' else None,
                             '一切正常' if pstatus == 'completed' else None,
                             pstart + ' 09:00' if pstatus == 'completed' else None)
                        )
                    # 对 in_progress 的计划，部分任务已完成
                    if pstatus == 'in_progress':
                        partial = db.execute(
                            "SELECT id FROM inspection_tasks WHERE plan_id=? LIMIT ?", (pid, len(items)//2)
                        ).fetchall()
                        for r in partial:
                            db.execute(
                                "UPDATE inspection_tasks SET result='normal', remark='运行正常', check_time=? WHERE id=?",
                                (pstart + ' 08:30', r['id'])
                            )
        db.commit()
        print("[Seed] Inspection plans seeded.")

def seed_alerts():
    """历史告警种子数据（仅首次）"""
    with get_db() as db:
        acnt = db.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
        if acnt == 0:
            alerts_seed = [
                (1,'water_level',50.8,'yellow','acknowledged','库水位偏高 50.8m > 49.5m','2026-06-11 06:15:00'),
                (4,'displacement',11.2,'orange','acknowledged','堤防位移超限！11.2mm > 10.0mm','2026-06-11 07:30:00'),
                (6,'vibration',8.5,'yellow','acknowledged','泵站振动超限！8.5mm/s > 7.0mm/s','2026-06-11 07:45:00'),
                (10,'turbidity',0.78,'red','acknowledged','供水浊度超标！0.78NTU > 0.5NTU','2026-06-11 08:00:00'),
                (1,'water_level',51.8,'red','acknowledged','库水位超危急线！51.8m > 51.5m','2026-06-11 09:10:00'),
                (10,'chlorine',0.55,'orange','pending','供水余氯偏高！0.55mg/L','2026-06-11 09:30:00'),
                (6,'vibration',9.3,'orange','pending','泵站振动严重！9.3mm/s','2026-06-11 09:45:00'),
                (1,'seepage',0.85,'yellow','pending','渗流量偏大 0.85L/s','2026-06-11 10:00:00'),
                (3,'water_level_upstream',14.8,'yellow','pending','上游水位偏高 14.8m','2026-06-11 10:15:00'),
                (10,'ph',8.4,'yellow','pending','供水pH值异常 8.4','2026-06-11 10:20:00'),
            ]
            for a in alerts_seed:
                sid = a[0]; metric = a[1]; val = a[2]; lv = a[3]; st = a[4]; msg = a[5]; ct = a[6]
                db.execute(
                    "INSERT INTO alerts (site_id,metric,value,level,status,message,created_at,resolved_at) VALUES (?,?,?,?,?,?,?,?)",
                    (sid, metric, val, lv, st, msg, ct, ct if st != 'pending' else None)
                )
            db.commit()
            print("[Seed] Historical alerts seeded.")

def seed_maintenance():
    """运维计划种子数据（仅首次）"""
    with get_db() as db:
        mcnt = db.execute("SELECT COUNT(*) FROM maintenance_plans").fetchone()[0]
        if mcnt == 0:
            sites = db.execute("SELECT id, name FROM sites LIMIT 50").fetchall()
            categories = [
                ('站院环境维护','environment','weekly'),
                ('站房维护','facility','biweekly'),
                ('设施设备维护','facility','monthly'),
                ('观测场管理','observation','biweekly'),
                ('断面环境管理','section','monthly'),
                ('安全检查','safety','monthly'),
                ('发电机保养','generator','monthly'),
            ]
            now = datetime.now()
            import itertools
            plan_id_counter = itertools.count(1)
            for site in sites:
                for cat_name, cat_key, freq in categories:
                    if freq == 'weekly':
                        due = now + timedelta(days=random.randint(0,7))
                    elif freq == 'biweekly':
                        due = now + timedelta(days=random.randint(0,14))
                    elif freq == 'monthly':
                        due = now + timedelta(days=random.randint(0,30))
                    else:
                        due = now + timedelta(days=random.randint(0,90))
                    # 60%概率已处理，40%待处理
                    status = 'completed' if random.random() < 0.6 else 'pending'
                    completed_at = due.strftime('%Y-%m-%d') if status == 'completed' else None
                    db.execute(
                        "INSERT INTO maintenance_plans (site_id,plan_name,category,frequency,due_date,status,assignee,completed_at) VALUES (?,?,?,?,?,?,?,?)",
                        (site['id'], f"{site['name']}{cat_name}", cat_key, freq,
                         due.strftime('%Y-%m-%d'), status, '管理员', completed_at)
                    )
            db.commit()
            print(f"[Seed] {len(sites)*len(categories)} maintenance plans seeded.")

# ===================== Simulator =====================

# 各河流警戒水位配置
RIVER_THRESHOLDS = {
    '赣江': {'high': 22.0, 'critical': 23.5, 'base': 18.5},
    '抚河': {'high': 32.0, 'critical': 33.5, 'base': 30.0},
    '鄱阳湖': {'high': 18.5, 'critical': 19.8, 'base': 16.5},
    '': {'high': 15.0, 'critical': 16.5, 'base': 13.0},  # 城区默认
}

# 站点类型对应的监测指标
TYPE_METRICS = {
    'rainfall': [
        ('precipitation','mm',20,50),
        ('cumulative_rainfall','mm',100,200),
    ],
    'water_level': [
        ('water_level','m',None,None),  # 阈值在生成时动态计算
        ('flow','m³/s',None,None),
    ],
    'hydrology': [
        ('water_level','m',None,None),
        ('velocity','m/s',None,None),
        ('flow','m³/s',None,None),
        ('precipitation','mm',20,50),
    ],
    'soil_moisture': [
        ('soil_moisture','%',90,None),   # 90%渍涝上限
        ('soil_temperature','°C',None,None),
    ],
    'evaporation': [
        ('evaporation','mm',None,None),
        ('temperature','°C',35,40),
        ('wind_speed','m/s',None,None),
    ],
}

def _generate_site_data(site, db, now):
    """为单个站点生成传感器数据"""
    sid = site['id']; stype = site['type']
    river = site['river'] or ''
    th = RIVER_THRESHOLDS.get(river, RIVER_THRESHOLDS[''])
    base_wl = th['base']

    if stype == 'rainfall':
        # 降雨量：有时无雨，有雨时0.5-25mm
        is_rainy = random.random() < 0.35
        precip = round(random.uniform(0.5, 25) if is_rainy else 0, 1)
        cum = get_site_trend(sid,'cum',random.uniform(20,80),5,0,300)
        db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,threshold_high,threshold_critical,recorded_at) VALUES (?,?,?,?,?,?,?)",
            (sid,'precipitation',precip,'mm/h',20,50,now))
        db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,threshold_high,recorded_at) VALUES (?,?,?,?,?,?)",
            (sid,'cumulative_rainfall',cum,'mm',100,now))
        if precip > 50:
            create_alert_internal(db,sid,'precipitation',precip,'red',f'小时雨量超危急！{precip}mm')
        elif precip > 20:
            create_alert_internal(db,sid,'precipitation',precip,'yellow',f'小时雨量达警戒 {precip}mm')

    elif stype == 'water_level':
        wl = get_site_trend(sid,'wl',base_wl,0.06,base_wl-2,th['critical']+1)
        flow = get_site_trend(sid,'flow',round(random.uniform(200,2000),0),50,10,5000)
        db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,threshold_high,threshold_critical,recorded_at) VALUES (?,?,?,?,?,?,?)",
            (sid,'water_level',wl,'m',th['high'],th['critical'],now))
        db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",
            (sid,'flow',flow,'m³/s',now))
        if wl > th['critical']:
            create_alert_internal(db,sid,'water_level',wl,'red',f'{river}水位超危急！{wl}m > {th["critical"]}m')
        elif wl > th['high']:
            create_alert_internal(db,sid,'water_level',wl,'yellow',f'{river}水位超警戒 {wl}m > {th["high"]}m')

    elif stype == 'hydrology':
        wl = get_site_trend(sid,'wl_h',base_wl,0.05,base_wl-1,th['critical']+0.5)
        vel = get_site_trend(sid,'vel',2.5,0.15,0.3,6.0)
        flow = get_site_trend(sid,'flow_h',round(random.uniform(300,3000),0),80,20,8000)
        precip = round(random.uniform(0, 15) if random.random() < 0.3 else 0, 1)
        db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,threshold_high,threshold_critical,recorded_at) VALUES (?,?,?,?,?,?,?)",
            (sid,'water_level',wl,'m',th['high'],th['critical'],now))
        db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",
            (sid,'velocity',vel,'m/s',now))
        db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",
            (sid,'flow',flow,'m³/s',now))
        db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,threshold_high,threshold_critical,recorded_at) VALUES (?,?,?,?,?,?,?)",
            (sid,'precipitation',precip,'mm/h',20,50,now))
        if wl > th['critical']:
            create_alert_internal(db,sid,'water_level',wl,'red',f'{site["name"]}水位超危急！{wl}m')
        elif wl > th['high']:
            create_alert_internal(db,sid,'water_level',wl,'yellow',f'{site["name"]}水位超警戒 {wl}m')

    elif stype == 'soil_moisture':
        sm = get_site_trend(sid,'sm',55,1.5,15,100)
        st = get_site_trend(sid,'st',22,0.5,5,45)
        db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,threshold_high,threshold_critical,recorded_at) VALUES (?,?,?,?,?,?,?)",
            (sid,'soil_moisture',sm,'%',90,None,now))
        db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",
            (sid,'soil_temperature',st,'°C',now))
        if sm > 90:
            create_alert_internal(db,sid,'soil_moisture',sm,'yellow',f'土壤含水量过高 {sm}%（渍涝风险）')
        elif sm < 20:
            create_alert_internal(db,sid,'soil_moisture',sm,'yellow',f'土壤含水量过低 {sm}%（干旱风险）')

    elif stype == 'evaporation':
        evap = get_site_trend(sid,'evap',4.0,0.3,0,15)
        temp = get_site_trend(sid,'temp_e',28,1.5,10,45)
        wind = get_site_trend(sid,'wind_e',3.0,0.5,0,12)
        db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",
            (sid,'evaporation',evap,'mm',now))
        db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,threshold_high,recorded_at) VALUES (?,?,?,?,?,?)",
            (sid,'temperature',temp,'°C',40,now))
        db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",
            (sid,'wind_speed',wind,'m/s',now))
        if temp > 40:
            create_alert_internal(db,sid,'temperature',temp,'orange',f'极端高温 {temp}°C')
        elif temp > 35:
            create_alert_internal(db,sid,'temperature',temp,'yellow',f'高温预警 {temp}°C')

def generate_sensor_data():
    """每30秒生成模拟传感器数据"""
    with get_db() as db:
        sites = db.execute("SELECT * FROM sites").fetchall()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        for site in sites:
            sid = site['id']
            try:
                _generate_site_data(site, db, now)
            except Exception as e:
                if 'database is locked' in str(e):
                    print(f'[Sim] DB locked, skip site {sid}')
                else:
                    print(f'[Sim] site {sid} error: {e}')
                db.rollback()

            # 设备在线/离线状态切换
            is_offline = random.random() < 0.03  # 3%概率离线
            new_status = 'offline' if is_offline else 'online'
            db.execute("UPDATE device_shadows SET status=?, last_data_time=? WHERE site_id=?",
                       (new_status, now if new_status == 'online' else None, sid))
            db.execute("UPDATE sites SET status=?, last_heartbeat=? WHERE id=?",
                       (new_status, now if new_status == 'online' else None, sid))

            # 设备离线告警
            if is_offline:
                create_alert_internal(db, sid, 'device_status', 0, 'yellow',
                    f'{site["name"]} 设备离线')
            else:
                # 解除离线告警（如果存在）
                db.execute(
                    "UPDATE alerts SET status='resolved', resolved_at=? WHERE site_id=? AND metric='device_status' AND status='pending'",
                    (now, sid)
                )

            # 数据异常检测：突变检测
            # 通过比对最近两条记录的差异来判断
            last_two = db.execute(
                "SELECT metric, value FROM sensor_data WHERE site_id=? ORDER BY recorded_at DESC LIMIT 3",
                (sid,)
            ).fetchmany(3)
            if len(last_two) >= 2:
                for row in last_two[0:2]:  # 对比最新的数据
                    pass  # 简化版本：不做复杂的突变检测

        # 更新设备时间戳
        db.execute("UPDATE device_shadows SET last_data_time=? WHERE status='online'", (now,))

        # === 数据到报率模拟（在同一个连接中完成） ===
        today = datetime.now().strftime('%Y-%m-%d')
        for site in sites:
            metrics_map = {
                'rainfall': 'rainfall',
                'water_level': 'water_level',
                'hydrology': 'water_level',
                'soil_moisture': 'soil_moisture',
                'evaporation': 'evaporation'
            }
            m = metrics_map.get(site['type'])
            if not m: continue
            is_miss = random.random() < 0.08
            existing = db.execute(
                "SELECT id, expected_count, actual_count FROM data_arrival WHERE site_id=? AND date=? AND metric=?",
                (site['id'], today, m)
            ).fetchone()
            if existing:
                exp = existing['expected_count'] + 1
                act = existing['actual_count'] + (0 if is_miss else 1)
                rate = round(act / exp * 100, 1)
                db.execute("UPDATE data_arrival SET expected_count=?, actual_count=?, arrival_rate=? WHERE id=?",
                           (exp, act, rate, existing['id']))
            else:
                db.execute("INSERT INTO data_arrival (site_id,date,metric,expected_count,actual_count,arrival_rate) VALUES (?,?,?,1,?,?)",
                           (site['id'], today, m, 0 if is_miss else 1, 100 if not is_miss else 0))

        # === 天气数据生成（在同一个连接中完成） ===
        temp = round(random.uniform(22, 36), 1)
        humidity = round(random.uniform(55, 95), 1)
        wind_speed = round(random.uniform(1, 10), 1)
        directions = ['北', '东北', '东', '东南', '南', '西南', '西', '西北']
        wind_dir = random.choice(directions)
        precip = round(random.uniform(0, 15), 1)
        pressure = round(random.uniform(1000, 1020), 1)
        weather_types = ['晴', '多云', '阴', '小雨', '中雨', '大雨']
        weights = [0.25, 0.30, 0.15, 0.15, 0.1, 0.05]
        weather = random.choices(weather_types, weights=weights)[0]
        warnings = []
        if precip > 10:
            warnings.append('暴雨黄色预警')
        if wind_speed > 6:
            warnings.append('大风蓝色预警')
        if temp > 35:
            warnings.append('高温橙色预警')
        warning_info = ','.join(warnings) if warnings else ''
        db.execute("""INSERT INTO weather_data (temperature,humidity,wind_speed,wind_direction,
                   precipitation,pressure,weather_type,warning_info) VALUES (?,?,?,?,?,?,?,?)""",
                   (temp, humidity, wind_speed, wind_dir, precip, pressure, weather, warning_info))
        db.commit()

def create_alert_internal(db, site_id, metric, value, level, message):
    exists = db.execute(
        "SELECT id FROM alerts WHERE site_id=? AND metric=? AND level=? AND status='pending' AND created_at > datetime('now','-10 minutes')",
        (site_id, metric, level)
    ).fetchone()
    if not exists:
        db.execute(
            "INSERT INTO alerts (site_id,metric,value,level,message) VALUES (?,?,?,?,?)",
            (site_id, metric, value, level, message)
        )

# ===================== API Routes =====================

@app.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'time': datetime.now().isoformat()})

# --- Sites ---
@app.route('/api/sites')
def get_sites():
    with get_db() as db:
        rows = db.execute("""
            SELECT s.*, COUNT(d.id) as device_count,
                   SUM(CASE WHEN d.status='offline' THEN 1 ELSE 0 END) as offline_count
            FROM sites s LEFT JOIN device_shadows d ON s.id=d.site_id
            GROUP BY s.id ORDER BY s.id
        """).fetchall()
        return jsonify([dict(r) for r in rows])

@app.route('/api/sites/<int:site_id>')
def get_site(site_id):
    with get_db() as db:
        site = db.execute("SELECT * FROM sites WHERE id=?", (site_id,)).fetchone()
        if not site:
            return jsonify({'error': 'not found'}), 404
        devices = db.execute("SELECT * FROM device_shadows WHERE site_id=?", (site_id,)).fetchall()
        alerts_count = db.execute("SELECT COUNT(*) as c FROM alerts WHERE site_id=? AND status='pending'", (site_id,)).fetchone()['c']
        orders_count = db.execute("SELECT COUNT(*) as c FROM work_orders WHERE site_id=? AND status NOT IN ('closed')", (site_id,)).fetchone()['c']
        site_dict = dict(site)
        site_dict['devices'] = [dict(d) for d in devices]
        site_dict['active_alerts'] = alerts_count
        site_dict['open_orders'] = orders_count
        # 水库额外信息
        reservoir_extra = {
            1: {'capacity': 1280, 'flood_level': 49.5, 'critical_level': 51.5, 'normal_level': 48.0},
            2: {'capacity': 860, 'flood_level': 48.0, 'critical_level': 50.0, 'normal_level': 47.0},
        }
        if site['type'] == 'reservoir':
            extra = reservoir_extra.get(site['id'], {})
            site_dict['capacity'] = extra.get('capacity')
            site_dict['flood_level'] = extra.get('flood_level')
            site_dict['critical_level'] = extra.get('critical_level')
            site_dict['normal_level'] = extra.get('normal_level')
        return jsonify(site_dict)

# --- Sensor Data ---
@app.route('/api/data/realtime')
def realtime_data():
    """各站点最新一条数据"""
    with get_db() as db:
        sites = db.execute("SELECT id, code, name, type, lat, lng, status FROM sites").fetchall()
        result = []
        for s in sites:
            row = db.execute(
                "SELECT metric, value, unit, recorded_at FROM sensor_data WHERE site_id=? ORDER BY recorded_at DESC LIMIT 1",
                (s['id'],)
            ).fetchone()
            site_dict = dict(s)
            site_dict['latest_value'] = round(row['value'],2) if row else 0
            site_dict['latest_metric'] = row['metric'] if row else ''
            site_dict['latest_unit'] = row['unit'] if row else ''
            site_dict['latest_time'] = row['recorded_at'] if row else ''
            result.append(site_dict)
        return jsonify(result)

@app.route('/api/data/site/<int:site_id>')
def site_data(site_id):
    """站点最近2小时数据"""
    limit = request.args.get('limit', 50, type=int)
    with get_db() as db:
        rows = db.execute(
            "SELECT metric, value, unit, recorded_at FROM sensor_data WHERE site_id=? ORDER BY recorded_at DESC LIMIT ?",
            (site_id, limit)
        ).fetchall()
        return jsonify([dict(r) for r in rows])

@app.route('/api/data/overview')
def data_overview():
    with get_db() as db:
        total_sites = db.execute("SELECT COUNT(*) as c FROM sites").fetchone()['c']
        online_sites = db.execute("SELECT COUNT(*) as c FROM sites WHERE status='online'").fetchone()['c']
        device_total = db.execute("SELECT COUNT(*) as c FROM device_shadows").fetchone()['c']
        device_online = db.execute("SELECT COUNT(*) as c FROM device_shadows WHERE status='online'").fetchone()['c']
        active_alerts = db.execute("SELECT COUNT(*) as c FROM alerts WHERE status='pending'").fetchone()['c']
        open_orders = db.execute("SELECT COUNT(*) as c FROM work_orders WHERE status NOT IN ('closed')").fetchone()['c']
        return jsonify({
            'total_sites': total_sites, 'online_sites': online_sites,
            'device_total': device_total, 'device_online': device_online,
            'active_alerts': active_alerts, 'open_orders': open_orders
        })

# --- Alerts ---
@app.route('/api/alerts')
def get_alerts():
    status = request.args.get('status', '')
    limit = request.args.get('limit', 50, type=int)
    with get_db() as db:
        q = """
            SELECT a.*, s.name as site_name, s.code as site_code
            FROM alerts a LEFT JOIN sites s ON a.site_id=s.id
            WHERE 1=1
        """
        params = []
        if status:
            q += " AND a.status=?"
            params.append(status)
        q += " ORDER BY CASE a.level WHEN 'red' THEN 1 WHEN 'orange' THEN 2 WHEN 'yellow' THEN 3 ELSE 4 END, a.created_at DESC LIMIT ?"
        params.append(limit)
        return jsonify([dict(r) for r in db.execute(q, params).fetchall()])

@app.route('/api/alerts/<int:alert_id>/acknowledge', methods=['POST'])
def acknowledge_alert(alert_id):
    data = request.json or {}
    operator = data.get('operator', '系统')
    with get_db() as db:
        db.execute("UPDATE alerts SET status='acknowledged' WHERE id=?", (alert_id,))
        # 记录时间线
        db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                   ('alert', alert_id, 'acknowledged', operator, '确认告警'))
        db.commit()
        return jsonify({'success': True})

@app.route('/api/alerts/<int:alert_id>/resolve', methods=['POST'])
def resolve_alert(alert_id):
    """办结告警"""
    data = request.json or {}
    operator = data.get('operator', '系统')
    with get_db() as db:
        db.execute("UPDATE alerts SET status='resolved' WHERE id=?", (alert_id,))
        db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                   ('alert', alert_id, 'resolved', operator, '办结告警'))
        db.commit()
        return jsonify({'success': True})

@app.route('/api/alerts/<int:alert_id>/urge', methods=['POST'])
def urge_alert(alert_id):
    """告警督办"""
    data = request.json or {}
    operator = data.get('operator', '系统')
    remark = data.get('remark', '督办告警')
    with get_db() as db:
        db.execute("UPDATE alerts SET urge_count=COALESCE(urge_count,0)+1, last_urged_at=datetime('now','localtime') WHERE id=?", (alert_id,))
        db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                   ('alert', alert_id, 'urged', operator, remark))
        db.commit()
        return jsonify({'success': True})

@app.route('/api/alerts/<int:alert_id>/undo-acknowledge', methods=['POST'])
def undo_acknowledge_alert(alert_id):
    """撤销告警确认，将状态改回pending"""
    data = request.json or {}
    operator = data.get('operator', '系统')
    remark = data.get('remark', '撤销确认')
    with get_db() as db:
        db.execute("UPDATE alerts SET status='pending', resolved_at=NULL WHERE id=?", (alert_id,))
        db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                   ('alert', alert_id, 'undo_acknowledge', operator, remark))
        db.commit()
        return jsonify({'success': True})

@app.route('/api/alerts/<int:alert_id>/convert-order', methods=['POST'])
def convert_alert_to_order(alert_id):
    """告警转工单"""
    data = request.json or {}
    operator = data.get('operator', '系统')
    with get_db() as db:
        alert = db.execute("SELECT * FROM alerts WHERE id=?", (alert_id,)).fetchone()
        if not alert:
            return jsonify({'error': 'not found'}), 404
        now = datetime.now()
        order_no = f"WO-{now.strftime('%Y%m%d')}-{random.randint(100,999)}"
        level = data.get('level', alert['level'])
        if level == 'red':
            order_level = 'critical'
        elif level == 'orange':
            order_level = 'urgent'
        else:
            order_level = 'normal'
        sla_hours = {'normal': 72, 'urgent': 24, 'critical': 2}.get(order_level, 72)
        sla_deadline = (now + timedelta(hours=sla_hours)).strftime('%Y-%m-%d %H:%M')
        assignee = data.get('assignee', '')
        db.execute("""
            INSERT INTO work_orders (order_no,site_id,source,event_type,level,title,description,assignee,status,sla_deadline)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            order_no, alert['site_id'], 'auto', '告警转工单',
            order_level, f"[告警转] {alert['message']}", alert['message'],
            assignee, 'pending', sla_deadline
        ))
        # 更新告警关联工单号
        db.execute("UPDATE alerts SET related_order_no=? WHERE id=?", (order_no, alert_id))
        # 记录时间线
        db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                   ('alert', alert_id, 'converted', operator, f'转工单 {order_no}'))
        db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                   ('order', 0, 'created', operator, f'告警{alert_id}转工单-{order_no}'))
        db.commit()
        return jsonify({'success': True, 'order_no': order_no})

@app.route('/api/alerts/batch', methods=['POST'])
def batch_alert_operations():
    """告警批量操作: acknowledge/urge/convert"""
    data = request.json or {}
    ids = data.get('ids', [])
    action = data.get('action', '')
    operator = data.get('operator', '系统')
    if not ids or not action:
        return jsonify({'error': 'ids and action required'}), 400
    with get_db() as db:
        if action == 'acknowledge':
            placeholders = ','.join(['?'] * len(ids))
            db.execute(f"UPDATE alerts SET status='acknowledged' WHERE id IN ({placeholders})", ids)
            for aid in ids:
                db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                           ('alert', aid, 'acknowledged', operator, '批量确认'))
        elif action == 'urge':
            remark = data.get('remark', '批量督办')
            for aid in ids:
                db.execute("UPDATE alerts SET urge_count=COALESCE(urge_count,0)+1, last_urged_at=datetime('now','localtime') WHERE id=?", (aid,))
                db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                           ('alert', aid, 'urged', operator, remark))
        elif action == 'convert':
            for aid in ids:
                alert = db.execute("SELECT * FROM alerts WHERE id=?", (aid,)).fetchone()
                if not alert:
                    continue
                now = datetime.now()
                order_no = f"WO-{now.strftime('%Y%m%d')}-{random.randint(100,999)}"
                level = alert['level']
                order_level = 'critical' if level == 'red' else ('urgent' if level == 'orange' else 'normal')
                sla_hours = {'normal': 72, 'urgent': 24, 'critical': 2}.get(order_level, 72)
                sla_deadline = (now + timedelta(hours=sla_hours)).strftime('%Y-%m-%d %H:%M')
                db.execute("""
                    INSERT INTO work_orders (order_no,site_id,source,event_type,level,title,description,status,sla_deadline)
                    VALUES (?,?,?,?,?,?,?,?,?)
                """, (order_no, alert['site_id'], 'auto', '告警批量转工单', order_level,
                      f"[告警转] {alert['message']}", alert['message'], 'pending', sla_deadline))
                db.execute("UPDATE alerts SET related_order_no=? WHERE id=?", (order_no, aid))
                db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                           ('alert', aid, 'converted', operator, f'批量转工单 {order_no}'))
        else:
            return jsonify({'error': f'unknown action: {action}'}), 400
        db.commit()
        return jsonify({'success': True, 'count': len(ids)})

@app.route('/api/timeline')
def get_timeline():
    """时间线查询，可按来源过滤"""
    source_type = request.args.get('source_type', '')
    source_id = request.args.get('source_id', '', type=int) if request.args.get('source_id') else None
    limit = request.args.get('limit', 50, type=int)
    with get_db() as db:
        q = "SELECT * FROM timeline_events WHERE 1=1"
        params = []
        if source_type:
            q += " AND source_type=?"
            params.append(source_type)
        if source_id is not None:
            q += " AND source_id=?"
            params.append(source_id)
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return jsonify([dict(r) for r in db.execute(q, params).fetchall()])

@app.route('/api/alerts/statistics')
def alert_statistics():
    with get_db() as db:
        total = db.execute("SELECT COUNT(*) as c FROM alerts").fetchone()['c']
        by_level = {}
        for lv in ['red','orange','yellow','blue']:
            by_level[lv] = db.execute("SELECT COUNT(*) as c FROM alerts WHERE level=?",(lv,)).fetchone()['c']
        by_status = {}
        for st in ['pending','acknowledged','resolved']:
            by_status[st] = db.execute("SELECT COUNT(*) as c FROM alerts WHERE status=?",(st,)).fetchone()['c']
        return jsonify({'total':total, 'by_level':by_level, 'by_status':by_status})

# --- Work Orders ---
@app.route('/api/workorders')
def get_workorders():
    status = request.args.get('status', '')
    limit = request.args.get('limit', 50, type=int)
    with get_db() as db:
        q = """
            SELECT w.*, s.name as site_name
            FROM work_orders w LEFT JOIN sites s ON w.site_id=s.id
            WHERE 1=1
        """
        params = []
        if status:
            q += " AND w.status=?"
            params.append(status)
        q += " ORDER BY w.created_at DESC LIMIT ?"
        params.append(limit)
        return jsonify([dict(r) for r in db.execute(q, params).fetchall()])

@app.route('/api/workorders', methods=['POST'])
def create_workorder():
    data = request.json
    with get_db() as db:
        now = datetime.now()
        order_no = f"WO-{now.strftime('%Y%m%d')}-{random.randint(100,999)}"
        sla_hours = {'normal': 72, 'urgent': 24, 'critical': 2}.get(data.get('level','normal'), 72)
        sla_deadline = (now + timedelta(hours=sla_hours)).strftime('%Y-%m-%d %H:%M')
        db.execute("""
            INSERT INTO work_orders (order_no,site_id,source,event_type,level,title,description,images,assignee,status,sla_deadline)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            order_no, data.get('site_id'), data.get('source','manual'),
            data.get('event_type',''), data.get('level','normal'),
            data.get('title',''), data.get('description',''),
            data.get('images',''), data.get('assignee',''),
            'pending', sla_deadline
        ))
        db.commit()
        return jsonify({'success': True, 'order_no': order_no})

@app.route('/api/workorders/<order_no>/status', methods=['PUT'])
def update_workorder_status(order_no):
    data = request.json
    new_status = data.get('status')
    valid_transitions = {
        'pending': ['accepted'],
        'accepted': ['generated', 'closed'],
        'generated': ['dispatched'],
        'dispatched': ['in_progress'],
        'in_progress': ['reviewing'],
        'reviewing': ['acceptance'],
        'acceptance': ['closed'],
    }
    with get_db() as db:
        cur = db.execute("SELECT status FROM work_orders WHERE order_no=?", (order_no,)).fetchone()
        if not cur:
            return jsonify({'error': 'not found'}), 404
        if new_status not in valid_transitions.get(cur['status'], []):
            return jsonify({'error': f'invalid transition from {cur["status"]} to {new_status}'}), 400
        updates = ["status=?"]
        params = [new_status]
        if new_status == 'closed':
            updates.append("resolved_at=datetime('now','localtime')")
        if 'remark' in data:
            updates.append("remark=?")
            params.append(data['remark'])
        if 'satisfaction' in data:
            updates.append("satisfaction=?")
            params.append(data['satisfaction'])
        params.append(order_no)
        db.execute(f"UPDATE work_orders SET {','.join(updates)} WHERE order_no=?", params)
        # 时间线记录
        operator = data.get('operator', '系统')
        status_cn = {'pending':'待受理','accepted':'已受理','generated':'已生成','dispatched':'已派发','in_progress':'处置中','reviewing':'审核中','acceptance':'验收中','closed':'已关闭'}
        event_label = status_cn.get(new_status, new_status)
        db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                   ('order', 0, new_status, operator, f'工单{order_no} → {event_label}'))
        db.commit()
        return jsonify({'success': True})

@app.route('/api/workorders/statistics')
def workorder_statistics():
    with get_db() as db:
        total = db.execute("SELECT COUNT(*) as c FROM work_orders").fetchone()['c']
        by_status = {}
        for st in ['pending','accepted','generated','dispatched','in_progress','reviewing','acceptance','closed']:
            by_status[st] = db.execute("SELECT COUNT(*) as c FROM work_orders WHERE status=?",(st,)).fetchone()['c']
        today = datetime.now().strftime('%Y-%m-%d')
        today_new = db.execute("SELECT COUNT(*) as c FROM work_orders WHERE date(created_at)=?",(today,)).fetchone()['c']
        today_closed = db.execute("SELECT COUNT(*) as c FROM work_orders WHERE date(resolved_at)=?",(today,)).fetchone()['c']
        return jsonify({'total':total, 'by_status':by_status, 'today_new':today_new, 'today_closed':today_closed})

# --- Inspections ---
@app.route('/api/inspections')
def get_inspections():
    with get_db() as db:
        rows = db.execute("""
            SELECT p.*, s.name as site_name, s.code as site_code,
                (SELECT COUNT(*) FROM inspection_tasks t WHERE t.plan_id=p.id) as total_items,
                (SELECT COUNT(*) FROM inspection_tasks t WHERE t.plan_id=p.id AND t.result IS NOT NULL) as completed_items
            FROM inspection_plans p LEFT JOIN sites s ON p.site_id=s.id
            ORDER BY p.created_at DESC
        """).fetchall()
        return jsonify([dict(r) for r in rows])

@app.route('/api/inspections', methods=['POST'])
def create_inspection():
    data = request.json
    with get_db() as db:
        cursor = db.execute("""
            INSERT INTO inspection_plans (plan_name,site_id,type,start_date,end_date)
            VALUES (?,?,?,?,?)
        """, (data['plan_name'],data['site_id'],data['type'],data['start_date'],data['end_date']))
        plan_id = cursor.lastrowid
        # 生成检查项
        check_items = data.get('check_items', [
            '坝体外观检查','溢洪道检查','放水设施检查',
            '监测设备检查','防汛物资检查','管理设施检查'
        ])
        for item in check_items:
            db.execute(
                "INSERT INTO inspection_tasks (plan_id,site_id,check_item) VALUES (?,?,?)",
                (plan_id, data['site_id'], item)
            )
        db.commit()
        # 时间线记录
        operator = data.get('operator', '系统')
        db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                   ('inspection', plan_id, 'created', operator, f'创建巡检计划-{data["plan_name"]}'))
        db.commit()
        return jsonify({'success': True, 'plan_id': plan_id})

@app.route('/api/inspections/<int:plan_id>/tasks')
def get_inspection_tasks(plan_id):
    with get_db() as db:
        rows = db.execute("SELECT * FROM inspection_tasks WHERE plan_id=? ORDER BY id", (plan_id,)).fetchall()
        return jsonify([dict(r) for r in rows])

@app.route('/api/inspections/tasks/<int:task_id>', methods=['PUT'])
def update_inspection_task(task_id):
    data = request.json
    with get_db() as db:
        db.execute("""
            UPDATE inspection_tasks SET result=?, photo=?, gps_lat=?, gps_lng=?, check_time=?, remark=?
            WHERE id=?
        """, (data.get('result'),data.get('photo'),data.get('gps_lat'),data.get('gps_lng'),
              data.get('check_time'),data.get('remark'),task_id))
        # 更新计划状态
        task = db.execute("SELECT plan_id FROM inspection_tasks WHERE id=?", (task_id,)).fetchone()
        if task:
            incomplete = db.execute(
                "SELECT COUNT(*) as c FROM inspection_tasks WHERE plan_id=? AND result IS NULL",
                (task['plan_id'],)
            ).fetchone()['c']
            if incomplete == 0:
                db.execute("UPDATE inspection_plans SET status='completed' WHERE id=?", (task['plan_id'],))
                plan = db.execute("SELECT plan_name FROM inspection_plans WHERE id=?", (task['plan_id'],)).fetchone()
                if plan:
                    db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                               ('inspection', task['plan_id'], 'completed', '系统', f'巡检计划完成-{plan["plan_name"]}'))
        db.commit()
        return jsonify({'success': True})

@app.route('/api/inspections/statistics')
def inspection_statistics():
    with get_db() as db:
        total_plans = db.execute("SELECT COUNT(*) as c FROM inspection_plans").fetchone()['c']
        done = db.execute("SELECT COUNT(*) as c FROM inspection_plans WHERE status='completed'").fetchone()['c']
        total_tasks = db.execute("SELECT COUNT(*) as c FROM inspection_tasks").fetchone()['c']
        done_tasks = db.execute("SELECT COUNT(*) as c FROM inspection_tasks WHERE result IS NOT NULL").fetchone()['c']
        abnormal = db.execute("SELECT COUNT(*) as c FROM inspection_tasks WHERE result='abnormal'").fetchone()['c']
        return jsonify({
            'total_plans':total_plans, 'completed_plans':done,
            'total_tasks':total_tasks, 'completed_tasks':done_tasks,
            'abnormal_count':abnormal
        })

# --- Maintenance Plans ---
@app.route('/api/maintenance/plans')
def get_maintenance_plans():
    with get_db() as db:
        status = request.args.get('status')
        category = request.args.get('category')
        q = "SELECT mp.*, s.name as site_name, s.code as site_code FROM maintenance_plans mp LEFT JOIN sites s ON mp.site_id=s.id"
        params = []
        conds = []
        if status:
            conds.append("mp.status=?")
            params.append(status)
        if category:
            conds.append("mp.category=?")
            params.append(category)
        if conds:
            q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY mp.due_date ASC"
        rows = db.execute(q, params).fetchall()
        return jsonify([dict(r) for r in rows])

@app.route('/api/maintenance/plans', methods=['POST'])
def create_maintenance_plan():
    data = request.json
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO maintenance_plans (site_id,plan_name,category,frequency,due_date,assignee) VALUES (?,?,?,?,?,?)",
            (data['site_id'], data['plan_name'], data['category'], data.get('frequency','monthly'), data.get('due_date'), data.get('assignee'))
        )
        db.commit()
        return jsonify({'success': True, 'plan_id': cur.lastrowid})

@app.route('/api/maintenance/plans/<int:plan_id>/complete', methods=['PUT'])
def complete_maintenance_plan(plan_id):
    with get_db() as db:
        db.execute("UPDATE maintenance_plans SET status='completed', completed_at=datetime('now','localtime') WHERE id=?", (plan_id,))
        db.commit()
        # 记录时间线
        db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator) VALUES (?,?,?,?)",
                   ('maintenance', plan_id, 'completed', '系统'))
        db.commit()
        return jsonify({'success': True})

@app.route('/api/maintenance/plans/<int:plan_id>/urge', methods=['POST'])
def urge_maintenance(plan_id):
    with get_db() as db:
        db.execute("UPDATE maintenance_plans SET urge_count=COALESCE(urge_count,0)+1, last_urged_at=datetime('now','localtime') WHERE id=?", (plan_id,))
        db.commit()
        db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator) VALUES (?,?,?,?)",
                   ('maintenance', plan_id, 'urged', '系统'))
        db.commit()
        return jsonify({'success': True})

@app.route('/api/maintenance/stats')
def maintenance_stats():
    """运维统计：今日待办总数/各分类统计"""
    with get_db() as db:
        today = datetime.now().strftime('%Y-%m-%d')
        total_pending = db.execute("SELECT COUNT(*) as c FROM maintenance_plans WHERE status='pending'").fetchone()['c']
        overdue = db.execute("SELECT COUNT(*) as c FROM maintenance_plans WHERE status='pending' AND due_date < ?", (today,)).fetchone()['c']
        return jsonify({'total_pending': total_pending, 'overdue': overdue})

@app.route('/api/maintenance/plans/<int:plan_id>', methods=['PUT'])
def update_maintenance_plan(plan_id):
    """修改运维计划"""
    data = request.json
    with get_db() as db:
        cur = db.execute("SELECT * FROM maintenance_plans WHERE id=?", (plan_id,)).fetchone()
        if not cur:
            return jsonify({'error': 'not found'}), 404
        updates = []
        params = []
        for field in ['plan_name','category','frequency','due_date','site_id','assignee']:
            if field in data:
                updates.append(f"{field}=?")
                params.append(data[field])
        if not updates:
            return jsonify({'error': 'no fields to update'}), 400
        params.append(plan_id)
        db.execute(f"UPDATE maintenance_plans SET {','.join(updates)} WHERE id=?", params)
        db.commit()
        return jsonify({'success': True})

@app.route('/api/maintenance/plans/<int:plan_id>', methods=['DELETE'])
def delete_maintenance_plan(plan_id):
    """删除运维计划"""
    with get_db() as db:
        db.execute("DELETE FROM maintenance_plans WHERE id=?", (plan_id,))
        db.commit()
        return jsonify({'success': True})

@app.route('/api/maintenance/plans/<int:plan_id>/review', methods=['PUT'])
def review_maintenance_plan(plan_id):
    """审核运维计划"""
    data = request.json
    review_result = data.get('review_result', 'pending')
    review_comment = data.get('review_comment', '')
    operator = data.get('operator', '系统')
    with get_db() as db:
        db.execute("UPDATE maintenance_plans SET review_status=?, review_comment=? WHERE id=?",
                   (review_result, review_comment, plan_id))
        db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                   ('maintenance', plan_id, 'reviewed', operator, f'审核结果:{review_result} 意见:{review_comment}'))
        db.commit()
        return jsonify({'success': True})

# --- Water Level Checks (Phase A-3) ---
@app.route('/api/water-level/checks')
def get_water_level_checks():
    """水位差值校验列表"""
    site_id = request.args.get('site_id', '', type=int)
    limit = request.args.get('limit', 50, type=int)
    with get_db() as db:
        q = "SELECT w.*, s.name as site_name, s.code as site_code FROM water_level_checks w LEFT JOIN sites s ON w.site_id=s.id WHERE 1=1"
        params = []
        if site_id:
            q += " AND w.site_id=?"
            params.append(site_id)
        q += " ORDER BY w.created_at DESC LIMIT ?"
        params.append(limit)
        return jsonify([dict(r) for r in db.execute(q, params).fetchall()])

@app.route('/api/water-level/checks', methods=['POST'])
def create_water_level_check():
    """手动录入水位校验"""
    data = request.json
    site_id = data.get('site_id')
    manual_level = data.get('manual_level')
    telemetry_level = data.get('telemetry_level')
    operator = data.get('operator', '系统')
    diff = round(abs(manual_level - telemetry_level), 3)
    status = 'abnormal' if diff > 0.02 else 'normal'
    adjust_action = data.get('adjust_action', '')
    with get_db() as db:
        db.execute("""
            INSERT INTO water_level_checks (site_id,manual_level,telemetry_level,diff,status,adjust_action,operator)
            VALUES (?,?,?,?,?,?,?)
        """, (site_id, manual_level, telemetry_level, diff, status, adjust_action, operator))
        wlc_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        # 如果差值超标，生成告警
        if diff > 0.02:
            site = db.execute("SELECT name, code FROM sites WHERE id=?", (site_id,)).fetchone()
            site_name = site['name'] if site else f'站点{site_id}'
            level = 'red' if diff > 0.05 else 'orange'
            db.execute("""
                INSERT INTO alerts (site_id,level,metric,value,message,status)
                VALUES (?,?,?,?,?,?)
            """, (site_id, level, 'water_level_diff', diff,
                  f'{site_name}水位校验差值{diff}m超过阈值', 'pending'))
            # 时间线
            db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                       ('water_level', wlc_id, 'alert_generated', operator, f'水位差值{diff}m触发告警'))
        db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                   ('water_level', wlc_id, 'checked', operator, f'录入校验-人工{manual_level}m/遥测{telemetry_level}m/差值{diff}m'))
        db.commit()
        return jsonify({'success': True, 'id': wlc_id, 'diff': diff, 'status': status})

@app.route('/api/water-level/checks/auto', methods=['POST'])
def auto_water_level_check():
    """自动生成水位校验记录（模拟手工录入与遥测数据的比较）"""
    with get_db() as db:
        # 选取水位站/水文站
        sites = db.execute(
            "SELECT id, name FROM sites WHERE type IN ('water_level','hydrology') ORDER BY RANDOM() LIMIT 5"
        ).fetchall()
        results = []
        for site in sites:
            manual = round(random.uniform(17.0, 24.0), 2)
            telemetry = round(manual + random.uniform(-0.03, 0.03), 2)
            diff = round(abs(manual - telemetry), 3)
            status = 'abnormal' if diff > 0.02 else 'normal'
            db.execute("""
                INSERT INTO water_level_checks (site_id,manual_level,telemetry_level,diff,status,operator)
                VALUES (?,?,?,?,?,?)
            """, (site['id'], manual, telemetry, diff, status, '自动'))
            wlc_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            if diff > 0.02:
                level = 'red' if diff > 0.05 else 'orange'
                db.execute("""
                    INSERT INTO alerts (site_id,level,metric,value,message,status)
                    VALUES (?,?,?,?,?,?)
                """, (site['id'], level, 'water_level_diff', diff,
                      f'{site["name"]}自动校验差值{diff}m超过阈值', 'pending'))
                db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                           ('water_level', wlc_id, 'alert_generated', '自动', f'自动校验差值{diff}m触发告警'))
            db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                       ('water_level', wlc_id, 'auto_checked', '自动', f'自动校验-人工{manual}m/遥测{telemetry}m/差值{diff}m'))
            results.append({'site_id': site['id'], 'site_name': site['name'], 'diff': diff, 'status': status})
        db.commit()
        return jsonify({'success': True, 'count': len(results), 'results': results})

# --- Data Arrival ---
@app.route('/api/data/arrival')
def get_data_arrival():
    """当日到报率数据"""
    date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    with get_db() as db:
        rows = db.execute(
            "SELECT da.*, s.name as site_name, s.code as site_code, s.type as site_type FROM data_arrival da LEFT JOIN sites s ON da.site_id=s.id WHERE da.date=? ORDER BY da.arrival_rate ASC",
            (date,)
        ).fetchall()
        return jsonify([dict(r) for r in rows])

@app.route('/api/data/arrival/summary')
def data_arrival_summary():
    """到报率汇总：按项目分类"""
    date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    with get_db() as db:
        rows = db.execute(
            "SELECT metric, AVG(arrival_rate) as avg_rate, COUNT(*) as site_count, SUM(CASE WHEN arrival_rate<98 THEN 1 ELSE 0 END) as below_threshold FROM data_arrival WHERE date=? GROUP BY metric",
            (date,)
        ).fetchall()
        total = db.execute("SELECT AVG(arrival_rate) as avg FROM data_arrival WHERE date=?", (date,)).fetchone()
        return jsonify({
            'total_avg': round(total['avg'],1) if total and total['avg'] else 0,
            'by_metric': [dict(r) for r in rows]
        })

# --- Hotline ---
@app.route('/api/hotline/events')
def get_hotline_events():
    limit = request.args.get('limit', 50, type=int)
    with get_db() as db:
        rows = db.execute("SELECT * FROM hotline_events ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return jsonify([dict(r) for r in rows])

@app.route('/api/hotline/events', methods=['POST'])
def create_hotline_event():
    data = request.json
    with get_db() as db:
        db.execute("""
            INSERT INTO hotline_events (caller_name,caller_phone,event_type,description,location,operator)
            VALUES (?,?,?,?,?,?)
        """, (data.get('caller_name',''),data.get('caller_phone',''),
              data.get('event_type',''),data.get('description',''),
              data.get('location',''),data.get('operator','')))
        db.commit()
        return jsonify({'success': True})

@app.route('/api/hotline/events/<int:event_id>/convert', methods=['POST'])
def convert_hotline_to_order(event_id):
    """热线事件转工单"""
    data = request.json
    with get_db() as db:
        event = db.execute("SELECT * FROM hotline_events WHERE id=?", (event_id,)).fetchone()
        if not event:
            return jsonify({'error': 'not found'}), 404
        now = datetime.now()
        order_no = f"WO-{now.strftime('%Y%m%d')}-{random.randint(100,999)}"
        leve = data.get('level','normal')
        sla_hours = {'normal': 72, 'urgent': 24, 'critical': 2}.get(leve, 72)
        sla_deadline = (now + timedelta(hours=sla_hours)).strftime('%Y-%m-%d %H:%M')
        db.execute("""
            INSERT INTO work_orders (order_no,source,event_type,level,title,description,assignee,status,sla_deadline)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (order_no, 'hotline', event['event_type'], leve,
              f"[热线]{event['event_type']}", event['description'],
              data.get('assignee',''), 'pending', sla_deadline))
        db.execute("UPDATE hotline_events SET status='dispatched', related_order_no=? WHERE id=?", (order_no, event_id))
        db.commit()
        return jsonify({'success': True, 'order_no': order_no})

# --- Dashboard ---
@app.route('/api/dashboard/summary')
def dashboard_summary():
    with get_db() as db:
        overview = {
            'total_sites': db.execute("SELECT COUNT(*) as c FROM sites").fetchone()['c'],
            'online_sites': db.execute("SELECT COUNT(*) as c FROM sites WHERE status='online'").fetchone()['c'],
            'device_total': db.execute("SELECT COUNT(*) as c FROM device_shadows").fetchone()['c'],
            'device_online': db.execute("SELECT COUNT(*) as c FROM device_shadows WHERE status='online'").fetchone()['c'],
            'active_alerts': db.execute("SELECT COUNT(*) as c FROM alerts WHERE status='pending'").fetchone()['c'],
            'open_orders': db.execute("SELECT COUNT(*) as c FROM work_orders WHERE status NOT IN ('closed')").fetchone()['c'],
            'today_orders': db.execute("SELECT COUNT(*) as c FROM work_orders WHERE date(created_at)=date('now','localtime')").fetchone()['c'],
        }
        # 最新告警
        latest_alerts = db.execute("""
            SELECT a.*, s.name as site_name FROM alerts a LEFT JOIN sites s ON a.site_id=s.id
            WHERE a.status='pending' ORDER BY CASE level WHEN 'red' THEN 1 WHEN 'orange' THEN 2 ELSE 3 END, a.created_at DESC LIMIT 5
        """).fetchall()
        # 待处理工单
        pending_orders = db.execute("""
            SELECT w.*, s.name as site_name FROM work_orders w LEFT JOIN sites s ON w.site_id=s.id
            WHERE w.status NOT IN ('closed') ORDER BY w.created_at DESC LIMIT 5
        """).fetchall()
        # 今日巡检
        insp = db.execute("""
            SELECT COUNT(*) as today_total,
                (SELECT COUNT(*) FROM inspection_tasks WHERE date(check_time)=date('now','localtime') AND result='abnormal') as abnormal
            FROM inspection_tasks WHERE date(check_time)=date('now','localtime')
        """).fetchone()
        return jsonify({
            'overview': overview,
            'latest_alerts': [dict(a) for a in latest_alerts],
            'pending_orders': [dict(o) for o in pending_orders],
            'today_inspection_total': insp['today_total'] or 0,
            'today_inspection_abnormal': insp['abnormal'] or 0,
        })

# --- 天气数据 (新增) ---
@app.route('/api/weather')
def get_weather():
    """返回当前天气数据、未来24小时逐时预报、天气预警"""
    with get_db() as db:
        # 获取最新天气记录
        current = db.execute(
            "SELECT * FROM weather_data ORDER BY recorded_at DESC LIMIT 1"
        ).fetchone()

        if not current:
            # 无数据时生成一次
            return jsonify({'error': '暂无天气数据，请稍后重试'}), 503

        # 构建当前天气
        now = datetime.now()
        result = {
            'current': {
                'temperature': current['temperature'],
                'humidity': current['humidity'],
                'wind_speed': current['wind_speed'],
                'wind_direction': current['wind_direction'],
                'precipitation': current['precipitation'],
                'pressure': current['pressure'],
                'weather_type': current['weather_type'],
                'recorded_at': current['recorded_at'],
            },
            'hourly_forecast': [],  # 未来24小时逐小时预报
            'warnings': [],  # 天气预警
        }

        # 解析预警信息
        if current['warning_info']:
            for w in current['warning_info'].split(','):
                if '暴雨' in w:
                    result['warnings'].append({'type': '暴雨', 'level': '黄色', 'message': '预计未来6小时有暴雨，请加强防范'})
                elif '大风' in w:
                    result['warnings'].append({'type': '大风', 'level': '蓝色', 'message': '风力已达6级以上，请加固设施'})
                elif '高温' in w:
                    result['warnings'].append({'type': '高温', 'level': '橙色', 'message': '最高气温超过35℃，请做好防暑降温'})

        # 生成未来24小时逐小时预报
        directions = ['北', '东北', '东', '东南', '南', '西南', '西', '西北']
        weather_types = ['晴', '多云', '阴', '小雨', '中雨', '大雨']
        for i in range(24):
            forecast_time = now + timedelta(hours=i+1)
            # 基于当前值做小幅随机波动
            temp_forecast = round(current['temperature'] + random.uniform(-3, 3), 1)
            hum_forecast = round(current['humidity'] + random.uniform(-10, 10), 1)
            hum_forecast = max(20, min(100, hum_forecast))
            wind_forecast = round(current['wind_speed'] + random.uniform(-2, 2), 1)
            wind_forecast = max(0, wind_forecast)
            precip_forecast = round(current['precipitation'] * random.uniform(0.5, 1.5), 1)

            result['hourly_forecast'].append({
                'time': forecast_time.strftime('%H:%M'),
                'datetime': forecast_time.strftime('%Y-%m-%d %H:%M'),
                'temperature': temp_forecast,
                'humidity': hum_forecast,
                'wind_speed': wind_forecast,
                'wind_direction': random.choice(directions),
                'precipitation': precip_forecast,
                'weather': random.choices(weather_types,
                    weights=[0.35, 0.25, 0.15, 0.1, 0.1, 0.05])[0],
            })

        return jsonify(result)

# --- 降雨预报 ---
@app.route('/api/rainfall/forecast')
def rainfall_forecast():
    """降雨预报数据：当前降雨 + 未来48小时逐小时预报 + 数据来源"""
    with get_db() as db:
        # 当前实时降雨（取最新天气记录的降水量）
        current = db.execute("SELECT precipitation, weather_type, temperature FROM weather_data ORDER BY id DESC LIMIT 1").fetchone()
        now = datetime.now()
        # 模拟48小时逐小时降雨预报
        hours = []
        base_precip = current['precipitation'] if current else 5.0
        base_weather = current['weather_type'] if current else '多云'
        rainy_weights = [0.6, 0.2, 0.1, 0.05, 0.05]
        rain_types = ['无雨', '小雨', '中雨', '大雨', '暴雨']
        for i in range(48):
            t = now + timedelta(hours=i)
            # 不同时段降雨概率不同
            hour_of_day = t.hour
            if 2 <= hour_of_day <= 6:
                prob = 0.15  # 凌晨降雨概率低
            elif 14 <= hour_of_day <= 17:
                prob = 0.40  # 午后对流高
            else:
                prob = 0.25
            is_rain = random.random() < prob
            if is_rain:
                p = round(random.uniform(0.5, max(2, base_precip * 1.5)), 1)
                wt = random.choices(rain_types[1:], weights=[0.5, 0.3, 0.15, 0.05])[0]
            else:
                p = 0
                wt = '无雨'
            hours.append({
                'time': t.strftime('%m-%d %H:00'),
                'precipitation': p,
                'rain_type': wt,
                'probability': round(prob * 100),
            })
        sources = ['自动监测站', '气象局', '雷达估测']
        return jsonify({
            'current_rainfall': round(base_precip, 1) if base_precip else 0,
            'current_weather': base_weather,
            'forecast': hours,
            'sources': sources,
        })

# --- 水质监测 ---
@app.route('/api/water-quality')
def water_quality():
    """水质监测数据：返回各供水站/水库的水质指标及7日均值对比"""
    site_id = request.args.get('site_id', type=int)
    with get_db() as db:
        # 查询所有水源相关站点（水库 + 供水站）
        q = "SELECT * FROM sites WHERE type IN ('reservoir','water_supply')"
        params = []
        if site_id:
            q += " AND id=?"
            params.append(site_id)
        sites = db.execute(q, params).fetchall()

        if not sites:
            return jsonify({'error': '没有找到水源相关站点'}), 404

        # 水质指标定义
        water_metrics = [
            ('turbidity', 'NTU', '浊度'),
            ('ph', '', 'pH值'),
            ('chlorine', 'mg/L', '余氯'),
            ('ammonia', 'mg/L', '氨氮'),
            ('cod', 'mg/L', 'COD'),
        ]
        seven_days_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')

        result = []
        for site in sites:
            site_data = {
                'site_id': site['id'],
                'site_code': site['code'],
                'site_name': site['name'],
                'site_type': site['type'],
                'metrics': {},
            }
            for metric, unit, label in water_metrics:
                # 最新值 + 阈值
                latest = db.execute(
                    "SELECT value, threshold_high, threshold_critical, recorded_at FROM sensor_data WHERE site_id=? AND metric=? ORDER BY recorded_at DESC LIMIT 1",
                    (site['id'], metric)
                ).fetchone()

                # 7天均值
                avg_row = db.execute(
                    "SELECT AVG(value) as avg_val FROM sensor_data WHERE site_id=? AND metric=? AND recorded_at > ?",
                    (site['id'], metric, seven_days_ago)
                ).fetchone()

                site_data['metrics'][metric] = {
                    'label': label,
                    'unit': unit,
                    'current': round(latest['value'], 3) if latest and latest['value'] is not None else None,
                    'current_time': latest['recorded_at'] if latest else None,
                    'avg_7d': round(avg_row['avg_val'], 3) if avg_row and avg_row['avg_val'] is not None else None,
                    'thresh_high': round(latest['threshold_high'], 3) if latest and latest['threshold_high'] is not None else None,
                    'thresh_critical': round(latest['threshold_critical'], 3) if latest and latest['threshold_critical'] is not None else None,
                }

            result.append(site_data)

        return jsonify(result)

# --- 设备状态监控 (新增) ---
@app.route('/api/devices/status')
def device_status():
    """设备心跳状态汇总：在线/离线统计、各类型统计、离线设备明细"""
    with get_db() as db:
        # 设备总数与状态统计
        total = db.execute("SELECT COUNT(*) as c FROM device_shadows").fetchone()['c']
        online = db.execute("SELECT COUNT(*) as c FROM device_shadows WHERE status='online'").fetchone()['c']
        offline = db.execute("SELECT COUNT(*) as c FROM device_shadows WHERE status='offline'").fetchone()['c']

        # 按设备类型统计
        by_type = db.execute("""
            SELECT device_type,
                COUNT(*) as total,
                SUM(CASE WHEN status='online' THEN 1 ELSE 0 END) as online,
                SUM(CASE WHEN status='offline' THEN 1 ELSE 0 END) as offline
            FROM device_shadows GROUP BY device_type ORDER BY device_type
        """).fetchall()

        # 离线设备明细
        offline_devices = db.execute("""
            SELECT d.*, s.name as site_name, s.code as site_code
            FROM device_shadows d LEFT JOIN sites s ON d.site_id=s.id
            WHERE d.status='offline'
            ORDER BY d.last_data_time DESC
        """).fetchall()

        # 各站点设备状态
        site_devices = db.execute("""
            SELECT s.id as site_id, s.code, s.name,
                COUNT(d.id) as total_devices,
                SUM(CASE WHEN d.status='online' THEN 1 ELSE 0 END) as online_devices,
                SUM(CASE WHEN d.status='offline' THEN 1 ELSE 0 END) as offline_devices
            FROM sites s LEFT JOIN device_shadows d ON s.id=d.site_id
            GROUP BY s.id ORDER BY s.id
        """).fetchall()

        return jsonify({
            'summary': {
                'total': total,
                'online': online,
                'offline': offline,
                'online_rate': round(online / total * 100, 1) if total > 0 else 0,
            },
            'by_type': [dict(r) for r in by_type],
            'offline_devices': [dict(d) for d in offline_devices],
            'site_devices': [dict(s) for s in site_devices],
        })

# --- 数据质量报告 (新增) ---
@app.route('/api/data-quality')
def data_quality():
    """数据质量报告：今日到达率/完整率/及时率、异常站点、24小时趋势"""
    with get_db() as db:
        today = datetime.now().strftime('%Y-%m-%d')
        now = datetime.now()
        twenty_four_hours_ago = (now - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')

        # 获取所有站点及其类型，确定每个站点期望的指标列表
        sites = db.execute("SELECT * FROM sites").fetchall()
        expected_metrics = {
            'rainfall': ['rainfall', 'precipitation', 'cumulative_rainfall'],
            'water_level': ['water_level', 'flow', 'velocity'],
            'hydrology': ['water_level', 'rainfall', 'flow', 'velocity', 'sediment'],
            'soil_moisture': ['soil_moisture', 'soil_temperature'],
            'evaporation': ['evaporation', 'temperature', 'wind_speed'],
        }

        # 计算今日数据到达率和完整率
        total_expected = 0
        total_received = 0
        anomaly_sites = []  # 异常站点列表

        for site in sites:
            site_metrics = expected_metrics.get(site['type'], [])
            if not site_metrics:
                continue

            # 期望数据点：按每小时12条(每5分钟一条)估算，匹配后端的回填频率
            hours_elapsed = max(1, (now.hour * 60 + now.minute) / 60)
            expected_per_metric = max(1, int(hours_elapsed * 12))  # 每小时12条(每5分钟一次)
            expected_today = len(site_metrics) * expected_per_metric
            total_expected += expected_today

            # 实际收到数据条数
            received = db.execute(
                "SELECT COUNT(*) as c FROM sensor_data WHERE site_id=? AND recorded_at LIKE ?",
                (site['id'], today + '%')
            ).fetchone()['c']
            total_received += received

            # 计算该站点数据完整率
            completeness = round(received / expected_today * 100, 1) if expected_today > 0 else 0

            # 标注异常站点（数据到达率<50%或数据为0的站点）
            if completeness < 50 and expected_today > 5:
                anomaly_sites.append({
                    'site_id': site['id'],
                    'site_code': site['code'],
                    'site_name': site['name'],
                    'site_type': site['type'],
                    'expected': expected_today,
                    'received': received,
                    'completeness': completeness,
                    'reason': '数据到达率低于50%' if received < expected_today / 2 else '数据采集异常',
                })

        # 总体指标
        arrival_rate = round(min(100, total_received / total_expected * 100), 1) if total_expected > 0 else 0
        completeness_rate = arrival_rate  # 在模拟场景下，到达率≈完整率

        # 数据及时率 (最近1小时内是否有数据视为及时)
        one_hour_ago = (now - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
        timely_sites = db.execute("""
            SELECT COUNT(DISTINCT site_id) as c FROM sensor_data WHERE recorded_at > ?
        """, (one_hour_ago,)).fetchone()['c']
        total_sites = len(sites) if sites else 1
        timeliness_rate = round(timely_sites / total_sites * 100, 1)

        # 最近24小时数据质量趋势 (按小时分组)
        hourly_trend = db.execute("""
            SELECT strftime('%Y-%m-%d %H:00', recorded_at) as hour,
                COUNT(*) as data_count
            FROM sensor_data
            WHERE recorded_at > ?
            GROUP BY strftime('%Y-%m-%d %H:00', recorded_at)
            ORDER BY hour ASC
        """, (twenty_four_hours_ago,)).fetchall()

        # 每个小时期望数据量（所有站点 × 12条/小时×指标数）
        expected_per_hour = sum(len(expected_metrics.get(s['type'], [])) for s in sites) * 12

        trend = []
        for row in hourly_trend:
            trend.append({
                'hour': row['hour'],
                'count': row['data_count'],
                'rate': round(min(100, row['data_count'] / expected_per_hour * 100), 1) if expected_per_hour > 0 else 0,
            })

        return jsonify({
            'today': {
                'arrival_rate': arrival_rate,         # 数据到达率(%)
                'completeness_rate': completeness_rate, # 数据完整率(%)
                'timeliness_rate': timeliness_rate,     # 数据及时率(%)
                'total_expected': total_expected,
                'total_received': total_received,
                'active_sites': total_sites,
                'timely_sites': timely_sites,
            },
            'anomaly_sites': anomaly_sites,
            'hourly_trend': trend,
        })

# ===================== 数据回填（生成历史数据用于图表展示） =====================

def backfill_history(hours=72):
    """回填历史监测数据，让图表有历史数据可展示"""
    with get_db() as db:
        count = db.execute("SELECT COUNT(*) as c FROM sensor_data").fetchone()['c']
        if count > 10000:
            print(f"[Backfill] 已有 {count} 条数据，跳过回填")
            return
        sites = db.execute("SELECT * FROM sites").fetchall()
        now = datetime.now()
        print(f"[Backfill] 开始回填 {hours} 小时历史数据...")
        for h in range(hours * 12, 0, -1):  # 每5分钟一条，共hours小时
            ts = (now - timedelta(minutes=5 * h)).strftime('%Y-%m-%d %H:%M:%S')
            for site in sites:
                sid = site['id']
                stype = site['type']
                if stype == 'reservoir':
                    wl = round(random.uniform(46.0, 52.5), 2)
                    sp = round(random.uniform(0.05, 0.6), 3)
                    db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",(sid,'water_level',wl,'m',ts))
                    db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",(sid,'seepage',sp,'L/s',ts))
                    db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",(sid,'inflow',round(random.uniform(10,50),1),'m³/s',ts))
                    db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",(sid,'outflow',round(random.uniform(5,40),1),'m³/s',ts))
                elif stype == 'sluice':
                    db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",(sid,'gate_opening',round(random.uniform(20,80),1),'%',ts))
                elif stype == 'dike':
                    db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",(sid,'displacement',round(random.uniform(0,12),1),'mm',ts))
                elif stype == 'pump':
                    db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",(sid,'flow',round(random.uniform(0.5,3.5),1),'m³/s',ts))
                    db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",(sid,'vibration',round(random.uniform(2,9),1),'mm/s',ts))
                elif stype == 'water_supply':
                    db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",(sid,'turbidity',round(random.uniform(0.05,0.6),2),'NTU',ts))
                    db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",(sid,'ph',round(random.uniform(6.8,7.8),1),'',ts))
                elif stype == 'irrigation':
                    db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",(sid,'water_level',round(random.uniform(2.0,4.5),1),'m',ts))
                    db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",(sid,'soil_moisture',round(random.uniform(30,90),1),'%',ts))
        db.commit()
        total = db.execute("SELECT COUNT(*) as c FROM sensor_data").fetchone()['c']
        print(f"[Backfill] 完成！共 {total} 条历史数据")


# ===================== 前端静态文件服务 =====================
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'frontend')

@app.route('/')
def index_html():
    return send_from_directory(FRONTEND_DIR, 'dashboard.html')

@app.route('/<path:filename>')
def serve_frontend(filename):
    return send_from_directory(FRONTEND_DIR, filename)

# ===================== Startup =====================

if __name__ == '__main__':
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    init_db()
    seed_data()
    seed_inspections()
    seed_alerts()
    seed_maintenance()
    backfill_history(72)
    # 生成初始数据（让趋势跟踪生效）
    for _ in range(6):
        try:
            if os.environ.get('SKIP_SEED') != '1':
                generate_sensor_data()
        except Exception as e:
            print(f'[Seed] 初始数据生成跳过: {e}')
    # 每30秒自动生成数据
    scheduler.add_job(generate_sensor_data, 'interval', seconds=30, id='simulator')
    print("[Server] 水利运维智慧运营平台 启动成功!")
    print("[Server] API: http://localhost:5000/api/health")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
