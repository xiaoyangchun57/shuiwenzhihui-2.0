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
import hashlib
import secrets
from datetime import datetime, timedelta
from contextlib import contextmanager

from flask import Flask, jsonify, request, g, send_from_directory, send_file
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
import os, uuid, urllib.request, urllib.error, json as _json

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
    # 0.1%概率注入异常突变（10倍漂移），用于触发异常检测
    if random.random() < 0.001:
        drift *= 10
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
    db = sqlite3.connect(DB_PATH, timeout=3, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=3000")
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
                basin TEXT DEFAULT '',
                address TEXT DEFAULT '',
                elevation REAL,
                build_date TEXT DEFAULT '',
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
            -- Migrate: add period column if not exists
            -- This ALTER TABLE is executed separately below, not in executescript

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

            CREATE TABLE IF NOT EXISTS plan_sites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER NOT NULL,
                site_id INTEGER NOT NULL,
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
                device_model TEXT DEFAULT '',
                manufacturer TEXT DEFAULT '',
                install_date TEXT DEFAULT '',
                status TEXT DEFAULT 'online',
                battery REAL,
                voltage REAL DEFAULT 0,
                last_data_time TEXT,
                FOREIGN KEY (site_id) REFERENCES sites(id)
            );

            -- 设备回收记录表
            CREATE TABLE IF NOT EXISTS device_recycle (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER NOT NULL,
                device_code TEXT NOT NULL,
                device_name TEXT NOT NULL,
                device_type TEXT,
                site_id INTEGER,
                site_name TEXT,
                recycle_date TEXT NOT NULL,
                reason TEXT DEFAULT '',
                destination TEXT DEFAULT '',
                operator TEXT DEFAULT '',
                remark TEXT DEFAULT '',
                status TEXT DEFAULT 'recycled',
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (device_id) REFERENCES device_shadows(id)
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

            -- 运维计划模板表
            CREATE TABLE IF NOT EXISTS maintenance_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                sub_category TEXT NOT NULL,
                title TEXT NOT NULL,
                frequency TEXT NOT NULL,
                description TEXT,
                standard TEXT,
                check_items TEXT,
                photo_required INTEGER DEFAULT 0,
                estimated_hours REAL DEFAULT 1,
                sort_order INTEGER DEFAULT 0
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

            -- 通知表（巡检计划通知、工单通知等实时消息）
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                source_type TEXT NOT NULL,
                source_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                content TEXT DEFAULT '',
                is_read INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            -- 用户表（登录系统）
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'operator',
                real_name TEXT NOT NULL,
                phone TEXT DEFAULT '',
                status TEXT DEFAULT 'active',
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );

            -- 用户-站点分配（多对多）
            CREATE TABLE IF NOT EXISTS user_sites (
                user_id INTEGER NOT NULL,
                site_id INTEGER NOT NULL,
                PRIMARY KEY (user_id, site_id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (site_id) REFERENCES sites(id)
            );
            -- 巡检方案母表
            CREATE TABLE IF NOT EXISTS inspection_schemes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id INTEGER NOT NULL,
                period TEXT NOT NULL,
                name TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                updated_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (site_id) REFERENCES sites(id),
                UNIQUE(site_id, period)
            );

            -- 方案检查项明细
            CREATE TABLE IF NOT EXISTS inspection_scheme_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scheme_id INTEGER NOT NULL,
                category TEXT DEFAULT '',
                check_item TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0,
                is_required INTEGER DEFAULT 1,
                FOREIGN KEY (scheme_id) REFERENCES inspection_schemes(id) ON DELETE CASCADE
            );

            -- 备件库存表
            CREATE TABLE IF NOT EXISTS spare_parts_inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                part_code TEXT UNIQUE NOT NULL,
                part_name TEXT NOT NULL,
                category TEXT DEFAULT '其他',
                unit TEXT DEFAULT '个',
                quantity INTEGER DEFAULT 0,
                min_quantity INTEGER DEFAULT 5,
                site_id INTEGER,
                remark TEXT DEFAULT '',
                updated_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (site_id) REFERENCES sites(id)
            );

            -- 校准模板（用于移动端设备校验多字段表单）
            CREATE TABLE IF NOT EXISTS calibration_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_type TEXT NOT NULL,
                template_name TEXT NOT NULL,
                fields TEXT NOT NULL,
                calculations TEXT,
                thresholds TEXT,
                category TEXT DEFAULT '',
                sort_order INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );

            -- 巡检跳过记录
            CREATE TABLE IF NOT EXISTS inspection_skip_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER NOT NULL,
                task_id INTEGER,
                site_id INTEGER NOT NULL,
                check_item TEXT NOT NULL,
                reason TEXT DEFAULT '',
                skip_type TEXT DEFAULT 'user',
                skip_count INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (plan_id) REFERENCES inspection_plans(id),
                FOREIGN KEY (site_id) REFERENCES sites(id)
            );

            -- 巡检照片类型配置
            CREATE TABLE IF NOT EXISTS inspection_photo_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER,
                site_type TEXT DEFAULT '',
                photo_type TEXT NOT NULL,
                label TEXT NOT NULL,
                min_count INTEGER DEFAULT 1,
                sort_order INTEGER DEFAULT 0
            );

            -- 备件申请表
            CREATE TABLE IF NOT EXISTS spare_part_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_no TEXT UNIQUE NOT NULL,
                site_id INTEGER NOT NULL,
                applicant TEXT NOT NULL,
                part_name TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                reason TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                approver TEXT DEFAULT '',
                approval_comment TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now','localtime')),
                updated_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (site_id) REFERENCES sites(id)
            );

            -- 库存变更流水表
            CREATE TABLE IF NOT EXISTS inventory_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                part_id INTEGER NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('in','out')),
                quantity INTEGER NOT NULL,
                ref_type TEXT DEFAULT '',
                ref_id INTEGER,
                operator TEXT DEFAULT '',
                remark TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (part_id) REFERENCES spare_parts_inventory(id)
            );

            CREATE TABLE IF NOT EXISTS data_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                source_type TEXT NOT NULL DEFAULT 'api',
                protocol TEXT DEFAULT 'HTTP',
                url TEXT NOT NULL,
                auth_type TEXT DEFAULT 'none',
                auth_config TEXT DEFAULT '{}',
                sync_interval INTEGER DEFAULT 60,
                status TEXT DEFAULT 'inactive',
                last_sync TEXT,
                remark TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );

            -- ===== 巡检V2：三层架构 =====
            -- 方案模板（站点无关，通用定义）
            CREATE TABLE IF NOT EXISTS inspection_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_name TEXT NOT NULL,
                category TEXT NOT NULL,
                frequency TEXT NOT NULL,
                description TEXT DEFAULT '',
                status TEXT DEFAULT 'active',
                sort_order INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );

            -- 模板检查项
            CREATE TABLE IF NOT EXISTS inspection_template_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id INTEGER NOT NULL,
                item_name TEXT NOT NULL,
                category TEXT DEFAULT '',
                frequency_level TEXT DEFAULT 'mid',
                photo_required INTEGER DEFAULT 0,
                sort_order INTEGER DEFAULT 0,
                FOREIGN KEY (template_id) REFERENCES inspection_templates(id) ON DELETE CASCADE
            );

            -- 巡检配置（站点类型 → 模板匹配规则）
            CREATE TABLE IF NOT EXISTS inspection_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_type TEXT NOT NULL,
                device_types TEXT DEFAULT '',
                template_id INTEGER NOT NULL,
                is_active INTEGER DEFAULT 1,
                remark TEXT DEFAULT '',
                FOREIGN KEY (template_id) REFERENCES inspection_templates(id)
            );

            -- 检查项排程（每项每站独立调度）
            CREATE TABLE IF NOT EXISTS inspection_schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id INTEGER NOT NULL,
                template_id INTEGER NOT NULL,
                template_item_id INTEGER NOT NULL,
                frequency TEXT NOT NULL,
                next_due_date TEXT NOT NULL,
                last_completed_at TEXT,
                status TEXT DEFAULT 'active',
                cycle_count INTEGER DEFAULT 0,
                FOREIGN KEY (site_id) REFERENCES sites(id),
                FOREIGN KEY (template_id) REFERENCES inspection_templates(id),
                FOREIGN KEY (template_item_id) REFERENCES inspection_template_items(id)
            );

            -- 巡检计划V2
            CREATE TABLE IF NOT EXISTS insp_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_name TEXT NOT NULL,
                assignee TEXT NOT NULL,
                assignee_id INTEGER,
                period TEXT NOT NULL,
                generate_date TEXT NOT NULL,
                status TEXT DEFAULT 'draft',
                completion_rate REAL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (assignee_id) REFERENCES users(id)
            );

            -- 计划检查项
            CREATE TABLE IF NOT EXISTS insp_plan_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER NOT NULL,
                site_id INTEGER NOT NULL,
                schedule_id INTEGER,
                template_id INTEGER,
                item_name TEXT NOT NULL,
                category TEXT DEFAULT '',
                frequency TEXT DEFAULT '',
                result TEXT,
                photo_urls TEXT,
                gps_lat REAL, gps_lng REAL,
                check_time TEXT,
                remark TEXT DEFAULT '',
                calibrator TEXT,
                calibration_values TEXT,
                completed_at TEXT,
                FOREIGN KEY (plan_id) REFERENCES insp_plans(id) ON DELETE CASCADE,
                FOREIGN KEY (site_id) REFERENCES sites(id)
            );

            -- 巡检提醒配置
            CREATE TABLE IF NOT EXISTS inspection_reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                remind_days_before INTEGER DEFAULT 1,
                remind_method TEXT DEFAULT 'notification',
                overdue_escalation INTEGER DEFAULT 0,
                escalation_days INTEGER DEFAULT 3,
                is_active INTEGER DEFAULT 1
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
            "ALTER TABLE maintenance_plans ADD COLUMN template_id INTEGER",
            "ALTER TABLE maintenance_plans ADD COLUMN sub_category TEXT",
            "ALTER TABLE maintenance_plans ADD COLUMN check_results TEXT",
            "ALTER TABLE maintenance_plans ADD COLUMN remark TEXT",
            "ALTER TABLE inspection_plans ADD COLUMN period TEXT DEFAULT 'once'",
            "ALTER TABLE inspection_plans ADD COLUMN description TEXT DEFAULT ''",
            "ALTER TABLE inspection_plans ADD COLUMN scheme_id INTEGER",
            "ALTER TABLE device_shadows ADD COLUMN voltage REAL DEFAULT 0",
            "ALTER TABLE device_shadows ADD COLUMN device_model TEXT DEFAULT ''",
            "ALTER TABLE device_shadows ADD COLUMN manufacturer TEXT DEFAULT ''",
            "ALTER TABLE device_shadows ADD COLUMN install_date TEXT DEFAULT ''",
            "ALTER TABLE sites ADD COLUMN basin TEXT DEFAULT ''",
            "ALTER TABLE sites ADD COLUMN address TEXT DEFAULT ''",
            "ALTER TABLE sites ADD COLUMN elevation REAL",
            "ALTER TABLE sites ADD COLUMN build_date TEXT DEFAULT ''",
            # 移动巡检方案相关字段
            "ALTER TABLE inspection_scheme_items ADD COLUMN frequency_level TEXT DEFAULT 'mid'",
            "ALTER TABLE inspection_tasks ADD COLUMN photo_urls TEXT",
            "ALTER TABLE inspection_tasks ADD COLUMN calibrator TEXT",
            "ALTER TABLE inspection_tasks ADD COLUMN calibration_values TEXT",
            "ALTER TABLE inspection_tasks ADD COLUMN photo_required INTEGER DEFAULT 1",
            # === 数据自洽性修复：新增关联字段 ===
            "ALTER TABLE work_orders ADD COLUMN related_alert_id INTEGER",
            "ALTER TABLE work_orders ADD COLUMN used_parts TEXT DEFAULT ''",
            "ALTER TABLE hotline_events ADD COLUMN site_id INTEGER",
            # 迁移 plan_sites 数据
        ]:
            try:
                db.execute(col_sql)
            except:
                pass
        # 从 inspection_plans.site_id 迁移到 plan_sites
        try:
            existing = db.execute("SELECT COUNT(*) FROM plan_sites").fetchone()[0]
            if existing == 0:
                db.execute("""
                    INSERT OR IGNORE INTO plan_sites (plan_id, site_id)
                    SELECT id, site_id FROM inspection_plans WHERE site_id IS NOT NULL
                """)
        except Exception:
            pass
        # 迁移：为已有设备填充型号和厂商
        try:
            empty_model = db.execute("SELECT COUNT(*) FROM device_shadows WHERE device_model='' OR device_model IS NULL").fetchone()[0]
            if empty_model > 0:
                type_model_map = {
                    'rainfall_gauge': ('SL3-1', '上海气象仪器厂'),
                    'electronic_rainfall': ('RG-50', '南京水文仪器有限公司'),
                    'radar_water_level': ('RWL-200', '深圳水情科技'),
                    'pressure_water_level': ('PWL-10', '南京水文仪器有限公司'),
                    'flow_meter': ('LS25-1', '长沙水文仪器厂'),
                    'hydro_collector': ('HWP-1', '南京水文仪器有限公司'),
                    'current_meter': ('LS25-1', '长沙水文仪器厂'),
                    'rainfall_meter': ('SL3-1', '上海气象仪器厂'),
                    'water_level_meter': ('SWJ-1A', '南京水文仪器有限公司'),
                    'soil_moisture_sensor': ('TDR-300', '北京农业物联网'),
                    'soil_temperature': ('PT100-A', '北京农业物联网'),
                    'evaporation_pan': ('EVP-1', '南京水文仪器有限公司'),
                    'weather_screen': ('ENV-200', '北京农业物联网'),
                    'anemometer': ('WS-100', '上海气象仪器厂'),
                    'groundwater_level': ('GWL-2', '南京水文仪器有限公司'),
                    'water_quality_monitor': ('WQ-100', '杭州环保科技'),
                    'video_surveillance': ('IPC-500', '海康威视'),
                    'security_alarm': ('SA-100', '深圳安防科技'),
                    'env_sensor': ('ENV-200', '北京农业物联网'),
                    'sensor': ('GEN-1', '通用厂商'),
                    'comm': ('RTU-200', '深圳水情科技'),
                    'power': ('UPS-1000', '深圳电源科技'),
                }
                for dtype, (model, mfr) in type_model_map.items():
                    db.execute("UPDATE device_shadows SET device_model=?, manufacturer=? WHERE device_type=? AND (device_model='' OR device_model IS NULL)", (model, mfr, dtype))
                # 为没有install_date的设备生成安装日期
                db.execute("UPDATE device_shadows SET install_date='2019-06-15' WHERE (install_date='' OR install_date IS NULL) AND id % 3 = 0")
                db.execute("UPDATE device_shadows SET install_date='2020-03-20' WHERE (install_date='' OR install_date IS NULL) AND id % 3 = 1")
                db.execute("UPDATE device_shadows SET install_date='2021-09-10' WHERE (install_date='' OR install_date IS NULL) AND id % 3 = 2")
        except Exception:
            pass
        # 迁移：为已有站点填充流域、地址、高程、建站日期
        try:
            empty_basin = db.execute("SELECT COUNT(*) FROM sites WHERE (basin='' OR basin IS NULL)").fetchone()[0]
            if empty_basin > 0:
                basin_map = {'hydrology': '赣江', 'water_level': '赣江', 'rainfall': '抚河', 'soil_moisture': '信江', 'evaporation': '鄱阳湖', 'groundwater': '赣江', 'station_yard': '赣江', 'reservoir': '修河'}
                for stype, basin in basin_map.items():
                    db.execute("UPDATE sites SET basin=? WHERE type=? AND (basin='' OR basin IS NULL)", (basin, stype))
                db.execute("UPDATE sites SET address=district WHERE (address='' OR address IS NULL) AND district IS NOT NULL AND district != ''")
                db.execute("UPDATE sites SET elevation=ROUND(10.0 + (id % 70), 1) WHERE elevation IS NULL")
                db.execute("UPDATE sites SET build_date='2015-06-01' WHERE (build_date='' OR build_date IS NULL) AND id % 4 = 0")
                db.execute("UPDATE sites SET build_date='2017-03-15' WHERE (build_date='' OR build_date IS NULL) AND id % 4 = 1")
                db.execute("UPDATE sites SET build_date='2019-09-20' WHERE (build_date='' OR build_date IS NULL) AND id % 4 = 2")
                db.execute("UPDATE sites SET build_date='2021-01-10' WHERE (build_date='' OR build_date IS NULL) AND id % 4 = 3")
        except Exception:
            pass
        # 添加关键索引以支持大数据量查询
        for idx_sql in [
            "CREATE INDEX IF NOT EXISTS idx_sd_site_time ON sensor_data(site_id, recorded_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_sd_metric_time ON sensor_data(metric, recorded_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_al_site_status ON alerts(site_id, status)",
            "CREATE INDEX IF NOT EXISTS idx_al_status_time ON alerts(status, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_insp_sch_site_due ON inspection_schedules(site_id, next_due_date)",
            "CREATE INDEX IF NOT EXISTS idx_insp_sch_tpl_item ON inspection_schedules(template_id, template_item_id)",
            "CREATE INDEX IF NOT EXISTS idx_insp_pi_plan ON insp_plan_items(plan_id)",
            "CREATE INDEX IF NOT EXISTS idx_insp_pi_site ON insp_plan_items(site_id)",
            "CREATE INDEX IF NOT EXISTS idx_insp_cfg_type ON inspection_configs(site_type)",
        ]:
            try:
                db.execute(idx_sql)
            except Exception:
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
    """种子数据：真实站点 + 设备 + 工单 + 热线事件（仅首次运行）"""
    with get_db() as db:
        count = db.execute("SELECT COUNT(*) FROM sites").fetchone()[0]
        if count > 0:
            print("[Seed] 站点数据已存在，跳过站点/设备/工单种子数据")
            return

        # === 235个真实站点导入 ===
        import json as _json
        json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'site_data.json')
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                all_sites = _json.load(f)
        else:
            all_sites = _gen_nanchang_sites()
        for s in all_sites:
            lat = s['lat'] or random.uniform(28.4, 29.2)
            lng = s['lng'] or random.uniform(115.5, 116.5)
            basin_map = {'hydrology': '赣江', 'water_level': '赣江', 'rainfall': '抚河', 'soil_moisture': '信江', 'evaporation': '鄱阳湖', 'groundwater': '赣江', 'station_yard': '赣江', 'reservoir': '修河'}
            basin = basin_map.get(s['type'], '赣江')
            addr = s.get('address', '') or s.get('note', '') or f"江西省南昌市{s.get('address', '')}"
            elev = round(random.uniform(10, 80), 1)
            build_year = random.randint(2005, 2020)
            build_date = f"{build_year}-{random.randint(1,12):02d}-{random.randint(1,28):02d}"
            db.execute(
                "INSERT INTO sites (code,name,type,lat,lng,district,basin,address,elevation,build_date) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (s['code'], s['name'], s['type'], lat, lng, s.get('address',''), basin, addr, elev, build_date)
            )
        print(f"[Seed] 生成 {len(all_sites)} 个站点")

        # === 分配负责人（同一行政区划分给同一运维人员，与人员管理一致） ===
        real_users = db.execute("SELECT username, real_name FROM users WHERE role='operator' ORDER BY id").fetchall()
        real_names = [u['real_name'] for u in real_users]
        if not real_names: real_names = ['张建国','黎明','王刚','赵洪']
        all_rows = db.execute("SELECT id, district FROM sites ORDER BY district, id").fetchall()
        mgr_map = {}; mgr_idx = 0
        for row in all_rows:
            dist = row['district'] or ''
            if dist not in mgr_map:
                mgr_map[dist] = real_names[mgr_idx % len(real_names)]
                mgr_idx += 1
            db.execute("UPDATE sites SET manager=?, phone=? WHERE id=?",
                       (mgr_map[dist], f'1{random.randint(30,39)}0000{random.randint(1000,9999)}', row['id']))

        # === 设备生成（每站按类型配设备） ===
        type_devices = {
            'rainfall': [('翻斗式雨量计','rainfall_gauge','SL3-1','上海气象仪器厂'),('电子雨量计','electronic_rainfall','RG-50','南京水文仪器有限公司')],
            'water_level': [('雷达水位计','radar_water_level','RWL-200','深圳水情科技'),('压力式水位计','pressure_water_level','PWL-10','南京水文仪器有限公司'),('流速计','flow_meter','LS25-1','长沙水文仪器厂')],
            'hydrology': [('水文综合采集仪','hydro_collector','HWP-1','南京水文仪器有限公司'),('流速仪','current_meter','LS25-1','长沙水文仪器厂'),('雨量计','rainfall_meter','SL3-1','上海气象仪器厂'),('水位计','water_level_meter','SWJ-1A','南京水文仪器有限公司')],
            'soil_moisture': [('土壤水分传感器','soil_moisture_sensor','TDR-300','北京农业物联网'),('土壤温度计','soil_temperature','PT100-A','北京农业物联网')],
            'evaporation': [('蒸发皿','evaporation_pan','EVP-1','南京水文仪器有限公司'),('气象百叶箱','weather_screen','ENV-200','北京农业物联网'),('风速仪','anemometer','WS-100','上海气象仪器厂')],
            'groundwater': [('地下水位计','groundwater_level','GWL-2','南京水文仪器有限公司'),('水质在线监测仪','water_quality_monitor','WQ-100','杭州环保科技')],
            'station_yard': [('视频监控','video_surveillance','IPC-500','海康威视'),('安防报警','security_alarm','SA-100','深圳安防科技'),('环境传感器','env_sensor','ENV-200','北京农业物联网')],
        }
        all_sites_db = db.execute("SELECT id, code, type FROM sites ORDER BY id").fetchall()
        for site in all_sites_db:
            devs = type_devices.get(site['type'], [('通用传感器','generic','GEN-1','通用厂商')])
            for i, (dname, dtype, dmodel, dmfr) in enumerate(devs):
                install_date = f"20{18 + (site['id'] % 6):02d}-{(site['id'] % 12) + 1:02d}-{(site['id'] % 28) + 1:02d}"
                db.execute(
                    "INSERT INTO device_shadows (site_id,device_code,device_name,device_type,device_model,manufacturer,install_date,status,battery,voltage) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (site['id'], f"{site['code']}-{i+1:02d}{dtype[:4].upper()}", dname, dtype, dmodel, dmfr, install_date,
                     'online', round(random.uniform(60,100), 0),
                     round(random.uniform(11.5, 14.2), 1))
                )

        # 工单种子数据（取前几个站ID）
        sample_ids = [r['id'] for r in db.execute("SELECT id FROM sites ORDER BY id LIMIT 5").fetchall()]
        orders = [
            (f'WO-20260618-{i+1:03d}', sample_ids[i] if i < len(sample_ids) else sample_ids[0],
             'auto','设备故障','normal','水位计数据中断','设备持续30分钟无数据上报','', '张建国','dispatched','2026-06-18 16:00','2026-06-18 08:30') for i in range(3)
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

        # 备件库存种子数据
        inv_cnt = db.execute("SELECT COUNT(*) FROM spare_parts_inventory").fetchone()[0]
        if inv_cnt == 0:
            spare_parts = [
                ('BJ-001', '水位计传感器', '传感器', '个', 30, 5),
                ('BJ-002', '雨量筒翻斗', '传感器', '个', 15, 5),
                ('BJ-003', '太阳能板(20W)', '电源', '块', 8, 3),
                ('BJ-004', '蓄电池(12V)', '电源', '个', 12, 5),
                ('BJ-005', '数据采集终端RTU', '通信', '台', 5, 2),
                ('BJ-006', 'GPRS通信模块', '通信', '个', 10, 3),
                ('BJ-007', '不锈钢水位计支架', '结构', '套', 6, 3),
                ('BJ-008', '防雷模块', '电源', '个', 20, 5),
                ('BJ-009', '信号线缆(10m)', '线缆', '根', 25, 10),
                ('BJ-010', '水位计密封圈', '其他', '个', 50, 10),
                ('BJ-011', '温湿度传感器', '传感器', '个', 8, 3),
                ('BJ-012', '风速风向仪', '传感器', '台', 3, 2),
            ]
            for pc, pn, cat, unit, qty, minq in spare_parts:
                db.execute(
                    "INSERT INTO spare_parts_inventory (part_code,part_name,category,unit,quantity,min_quantity) VALUES (?,?,?,?,?,?)",
                    (pc, pn, cat, unit, qty, minq)
                )

        # 备件申请种子数据（演示用）
        req_cnt = db.execute("SELECT COUNT(*) FROM spare_part_requests").fetchone()[0]
        if req_cnt == 0:
            from datetime import datetime, timedelta
            now = datetime.now()
            sample_reqs = [
                (1, '系统管理员', '水位计传感器', 2, '水位计数据异常，需更换', 'approved', '系统管理员', '同意更换', (now - timedelta(hours=2)).strftime('%Y-%m-%d %H:%M:%S')),
                (2, '系统管理员', '太阳能板(20W)', 1, '太阳能板破损', 'approved', '系统管理员', '已核实，批准', (now - timedelta(hours=5)).strftime('%Y-%m-%d %H:%M:%S')),
                (3, '运维人员', 'GPRS通信模块', 2, '通信模块频繁断连', 'pending', '', '', (now - timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S')),
                (4, '运维人员', '防雷模块', 3, '汛期前补充', 'pending', '', '', (now - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')),
                (5, '系统管理员', '数据采集终端RTU', 1, 'RTU老化需更换', 'rejected', '系统管理员', '库存不足，暂缓采购', (now - timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')),
            ]
            for idx, (sid, applicant, pname, qty, reason, status, approver, comment, ctime) in enumerate(sample_reqs):
                rno = f"BJ-{now.strftime('%Y%m%d')}-{idx+1:03d}"
                db.execute(
                    "INSERT INTO spare_part_requests (request_no,site_id,applicant,part_name,quantity,reason,status,approver,approval_comment,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (rno, sid, applicant, pname, qty, reason, status, approver, comment, ctime)
                )
                # 已批准的申请记录扣减库存流水
                if status == 'approved':
                    inv = db.execute("SELECT id, quantity FROM spare_parts_inventory WHERE part_name LIKE ? LIMIT 1", (f"%{pname}%",)).fetchone()
                    if inv:
                        new_qty = max(0, inv['quantity'] - qty)
                        db.execute("UPDATE spare_parts_inventory SET quantity=? WHERE id=?", (new_qty, inv['id']))
                        db.execute("INSERT INTO inventory_logs (part_id,type,quantity,ref_type,ref_id,operator,remark) VALUES (?,'out',?,'request',?,?,?)",
                            (inv['id'], qty, 0, '系统管理员', f"种子数据：{rno}"))

        db.commit()
        print("[Seed] Database seeded with initial data.")

def seed_inspections():
    """巡检种子数据（依据《运维事项.pdf》内容分布，独立判断，可重复运行）"""
    with get_db() as db:
        cnt = db.execute("SELECT COUNT(*) FROM inspection_plans").fetchone()[0]
        if cnt == 0:
            all_sites = db.execute("SELECT id, name, type FROM sites ORDER BY id").fetchall()
            if len(all_sites) < 5: return
            # 按站点类型分组
            s_by_type = {}
            for s in all_sites:
                s_by_type.setdefault(s['type'], []).append(s)
            now_str = datetime.now().strftime('%Y-%m-%d')

            # ========== 计划定义 (依据运维事项.pdf) ==========
            # 格式: (名称, 站点类型, 频次, 持续天数, 状态, 每类型选站数, 检查项列表)
            plans = [
                # ====== 水文站 (hydrology) ======
                # 每日：水位日常观测（PDF：水位项目日常巡查-驻测站每日8时、18-20时）
                ('水位日常观测', 'hydrology', 'daily', 1, 'in_progress', 4,
                 ['观测基本水尺读数并记录', '校对遥测水位及时间', '检查清洗水尺', '水位设备无异常检查', '填记水位巡查表并拍照存档']),
                # 每周：站院环境维护（PDF：驻测站站院环境维护-每周打扫）
                ('站院环境维护', 'hydrology', 'weekly', 7, 'pending', 3,
                 ['水位井打扫', '站院地面、窗台、设备清洁', '墙面天花板无污迹蜘蛛网', '草地灌木修剪打扫']),
                # 每月：设施设备维护（PDF：设施设备维护-每月检查清洗水尺、爬梯、护栏）
                ('设施设备检查', 'hydrology', 'monthly', 30, 'pending', 2,
                 ['检查清洗水尺', '爬梯牢固度检查', '护栏牢固度检查', '设施设备巡查表填写', '异常维修拍照存档报中心站网监测科']),
                # 每月：观测场管理（PDF：观测场管理-每月2次）
                ('观测场管理', 'hydrology', 'monthly', 30, 'pending', 2,
                 ['降蒸观测场草地维护', '站院草皮高度低于20cm', '杂草杂物清理']),
                # 每月：断面环境管理（PDF：断面环境管理-每月断面检查清理）
                ('断面环境管理', 'hydrology', 'monthly', 30, 'pending', 2,
                 ['基本水尺码头清理淤泥杂草', '停船码头清理淤泥杂草', '流速仪测流断面清理', '基本水尺底部淤泥杂草清理']),
                # 每月：安全检查（PDF：安全检查-每月一次）
                ('安全检查', 'hydrology', 'monthly', 30, 'pending', 2,
                 ['测验设施设备检查', '安全环境检查', '站房检查', '灭火器检查', '安全器材检查', '安全检查记录填记']),
                # 每月：发电机保养（PDF：发电机保养及维护-每月1次检查）
                ('发电机保养', 'hydrology', 'monthly', 30, 'pending', 1,
                 ['检查机油', '检查线路及各部件', '发电运行不少于30分钟并记录', '汛前汛后更换机油保养维护', '备足燃料及机油']),
                # 不定期(季度)：缆道日常巡检（PDF：缆道日常巡检-测流时）
                ('缆道巡检', 'hydrology', 'quarterly', 90, 'pending', 2,
                 ['行主索检查维护', '循环索检查维护', '拉线卡头检查', '工作索毛刺断骨检查拍照留底',
                  '锚碇位移检查', '锚碇周围土壤裂纹崩塌检查', '导向轮游轮行车架运转检查', '绞车运转检查']),
                # 每半年：综合检查
                ('半年综合检查', 'hydrology', 'halfyear', 180, 'pending', 2,
                 ['水文缆道全面检修', '备用电源充放电测试', '通信系统切换测试', '所有传感器校准']),
                # 每年：年度大修（PDF：断面环境管理-每年汛前汛后全面清理 + 发电机-汛前汛后保养）
                ('年度检修', 'hydrology', 'yearly', 365, 'completed', 1,
                 ['汛前流速仪测流断面全面清理', '汛前缆道铁塔四周全面清理',
                  '汛后断面全面清理', '发电机更换机油', '发电机各部件全面检查',
                  '全站水文年鉴资料整编', '年度总结报告编制']),

                # ====== 水位站 (water_level) ======
                # 每日：水位日常观测（PDF：水位项目日常巡查-巡测站每日8-10时）
                ('水位日常观测', 'water_level', 'daily', 1, 'in_progress', 4,
                 ['观测基本水尺读数并记录', '校对遥测水位及时间', '检查水位设备无异常', '水位巡查表填记并拍照存档']),
                # 每月：站房维护（PDF：巡测站站房维护-每月2次）
                ('站房维护', 'water_level', 'monthly', 30, 'pending', 2,
                 ['站房全面打扫', '地面窗台设备清洁', '墙面天花板无污迹蜘蛛网', '保持干净整洁']),
                # 每月：设施设备维护（PDF：设施设备维护-每月）
                ('设施设备检查', 'water_level', 'monthly', 30, 'pending', 2,
                 ['检查清洗水尺', '水位设备检查', '爬梯牢固度检查', '设施设备巡查表填写']),
                # 每月：安全检查（PDF：安全检查-每月一次）
                ('安全检查', 'water_level', 'monthly', 30, 'pending', 2,
                 ['测验设施设备检查', '安全环境检查', '灭火器检查', '安全器材检查', '安全检查记录填记']),
                # 每半年：综合检查
                ('半年综合检查', 'water_level', 'halfyear', 180, 'pending', 2,
                 ['水准点校核', '水尺零高测量', 'RTU主板检查', '通信系统切换测试', '所有传感器校准']),

                # ====== 雨量站 (rainfall) ======
                # 每日：数据检查
                ('雨量日常检查', 'rainfall', 'daily', 1, 'pending', 4,
                 ['雨量数据检查', '通信状态检查', '电源电压检查']),
                # 每月：雨量项目日常巡检（PDF：雨量项目日常巡检-每月1次）
                ('雨量项目巡检', 'rainfall', 'monthly', 30, 'pending', 2,
                 ['数据采集终端外观检查', '数据读取和上报检查', '终端内部状态检查',
                  '供电设备检查', '布线检查', '雨量筒外观检查',
                  '雨量筒器口水平检查', '雨量筒气泡居中检查', '雨量筒运行状态检查',
                  '雨量采集准确性核对', '站点周边环境清理']),
                # 每季度：注水试验（PDF：雨量项目-每季度注水试验）
                ('雨量注水试验', 'rainfall', 'quarterly', 90, 'pending', 2,
                 ['注入5-10mm清洗湿润过水部件', '翻斗运转灵活性检查', '信号输出正常检查',
                  '清除翻斗存留水量', '每次注水三次不少于12.5mm',
                  '测量误差不大于±4%为合格', '记录存盘']),
                # 每半年：综合检查
                ('半年综合检查', 'rainfall', 'halfyear', 180, 'pending', 2,
                 ['雨量器全套校准', '通信系统测试', '备份电池检查', '机箱密封检查']),
                # 每年：年度校准（PDF：每年汛前自动蒸发注水实验部分涉及）
                ('年度校准', 'rainfall', 'yearly', 365, 'completed', 1,
                 ['雨量资料整编', '雨量器更换评估', '年度校准报告编制']),

                # ====== 蒸发站 (evaporation) ======
                # 每日：数据检查
                ('蒸发日常检查', 'evaporation', 'daily', 1, 'pending', 3,
                 ['蒸发量数据检查', '水面状态观察', '通信状态检查']),
                # 每月：蒸发项目日常巡检（PDF：蒸发项目日常巡检-每月不少于1次）
                ('蒸发项目巡检', 'evaporation', 'monthly', 30, 'pending', 2,
                 ['自动蒸发设备遥测终端现场巡检', '数据采集和传输终端外观检查',
                  '终端内部状态检查', '供电设备检查', '布线检查']),
                # 每月：蒸发器换水（PDF：一个月至少换水一次）
                ('蒸发器换水', 'evaporation', 'monthly', 30, 'pending', 1,
                 ['蒸发器换水', '水圈清洁保持无泥沙杂草杂物青苔', '取用能代表当地自然水体的水']),
                # 每半年：渗漏检查（PDF：每半年需进行一次渗漏检查）
                ('蒸发渗漏检查', 'evaporation', 'halfyear', 180, 'pending', 1,
                 ['8时关闭蒸发皿阀门', '人工量测蒸发皿1日蒸发量', '通过邻站对比判断是否漏水',
                  '同步观测自记值判断输水管道或静水桶是否漏水',
                  '每日合理性检查-蒸发异常偏大时需进行渗漏检查']),
                # 每半年：综合检查
                ('半年综合检查', 'evaporation', 'halfyear', 180, 'pending', 2,
                 ['蒸发器全套标定', '通信系统测试', '数据对比分析']),
                # 每年：注水实验（PDF：每年汛前对自动蒸发进行注水实验）
                ('蒸发注水实验', 'evaporation', 'yearly', 365, 'pending', 1,
                 ['选择无雨日早晨或黄昏进行注水实验', '使用雨杯量取注入水量',
                  '分别注入0.1mm至4mm梯度水量', '等待1-2分钟待液位稳定后读取',
                  '同时人工测针测记蒸发器液位', '统计计算各项误差',
                  '一代伟思折算系数0.868，二代伟思折算系数0.909']),

                # ====== 墒情站 (soil_moisture) ======
                # 每日：数据检查
                ('墒情日常检查', 'soil_moisture', 'daily', 1, 'pending', 3,
                 ['墒情数据检查', '通信状态检查', '电源状态检查']),
                # 每季度：墒情站日常巡查（PDF：每季度对基本站巡查不少于1次）
                ('墒情站巡查', 'soil_moisture', 'quarterly', 90, 'pending', 2,
                 ['机箱内干净整洁检查', '清理周边杂草', '保持整洁无积水', '进行数据校测并做好记录',
                  '干旱天气按规范做好取土检验工作']),
                # 每半年：综合检查
                ('半年综合检查', 'soil_moisture', 'halfyear', 180, 'pending', 1,
                 ['传感器埋设状态检查', '数据对比分析', '机箱密封检查']),

                # ====== 地下水监测站 (groundwater) ======
                # 每日：数据监控（PDF：数据监控及台账建立-实时查看地下水数据到报率）
                ('地下水日常监测', 'groundwater', 'daily', 1, 'pending', 3,
                 ['地下水数据检查', '通信状态检查', '电源状态检查']),
                # 每月：设备巡检（PDF：设施设备维护-每月检查）
                ('地下水设备巡检', 'groundwater', 'monthly', 30, 'pending', 2,
                 ['数据采集终端检查', '供电设备检查', '浮子式水位计运行检查',
                  '压力式水位计运行检查', '机箱密封检查', '周边环境清理']),
                # 每季度：巡查（PDF：墒情站巡查参考-每季度不少于1次）
                ('地下水站巡查', 'groundwater', 'quarterly', 90, 'pending', 2,
                 ['机箱内干净整洁检查', '清理周边杂草', '保持整洁无积水',
                  '数据校测并做好记录', '传感器运行状态检查']),
                # 每半年：综合检查
                ('半年综合检查', 'groundwater', 'halfyear', 180, 'pending', 1,
                 ['传感器全套校准', '通信系统切换测试', '数据对比分析']),

                # ====== 站院 (station_yard) ======
                # 每周：站院环境维护（PDF：驻测站站院环境维护-每周打扫）
                ('站院环境维护', 'station_yard', 'weekly', 7, 'pending', 2,
                 ['站院地面清洁', '窗台设备清洁', '墙面天花板无污迹蜘蛛网',
                  '草地灌木修剪', '遇重大活动增加维护次数']),
                # 每月：设施设备维护（PDF：设施设备维护-每月）
                ('设施设备检查', 'station_yard', 'monthly', 30, 'pending', 2,
                 ['检查清洗水尺', '设施设备全面检查', '爬梯牢固度检查',
                  '护栏牢固度检查', '设施设备巡查表填写', '异常维修拍照存档']),
                # 每月：安全检查（PDF：安全检查-每月一次）
                ('安全检查', 'station_yard', 'monthly', 30, 'pending', 2,
                 ['测验设施设备检查', '安全环境检查', '站房检查',
                  '灭火器检查', '安全器材检查', '安全检查记录填记']),
                # 每半年：综合检查
                ('半年综合检查', 'station_yard', 'halfyear', 180, 'pending', 1,
                 ['设施设备全面检修', '安全环境综合评估', '通信系统测试']),
            ]

            # ========== 生成计划 ==========
            for pname, stype, freq, days, status, sel_cnt, check_items in plans:
                sites_of_type = s_by_type.get(stype, [])
                if not sites_of_type:
                    continue
                # 按站点打包：将同类型站点分批，每批生成一个计划（一批含多个站点）
                chunk_size = stype in ('station_yard','reservoir') and 5 or 10
                selected = sites_of_type
                for chunk_idx in range(0, len(selected), chunk_size):
                    chunk = selected[chunk_idx:chunk_idx + chunk_size]
                    if not chunk: continue
                    site_ids = [s['id'] for s in chunk]
                    first_site = chunk[0]
                    batch_num = chunk_idx // chunk_size + 1
                    plan_label = pname
                    if len(selected) > chunk_size:
                        plan_label = f'{pname}({batch_num})'
                    end_dt = datetime.now() + timedelta(days=days)
                    start_date = now_str
                    end_date = end_dt.strftime('%Y-%m-%d')
                    cur = db.execute(
                        "INSERT INTO inspection_plans (plan_name,site_id,type,start_date,end_date,status) VALUES (?,?,?,?,?,?)",
                        (f'{plan_label}', first_site['id'], freq, start_date, end_date, status)
                    )
                    pid = cur.lastrowid
                    for sid in site_ids:
                        db.execute("INSERT OR IGNORE INTO plan_sites (plan_id,site_id) VALUES (?,?)", (pid, sid))
                    for sid in site_ids:
                        for item in check_items:
                            result = 'normal' if status == 'completed' else None
                            remark = '一切正常' if status == 'completed' else None
                            check_time = (start_date + ' 09:00') if status == 'completed' else None
                            db.execute(
                                "INSERT INTO inspection_tasks (plan_id,site_id,check_item,result,remark,check_time) VALUES (?,?,?,?,?,?)",
                                (pid, sid, item, result, remark, check_time)
                            )
                    # 对 in_progress 的计划，部分任务已完成
                    if status == 'in_progress':
                        # 取前一半的站点的所有任务标记为已完成
                        half_sites = site_ids[:max(1, len(site_ids)//2)]
                        for sid in half_sites:
                            tasks = db.execute(
                                "SELECT id FROM inspection_tasks WHERE plan_id=? AND site_id=?",
                                (pid, sid)
                            ).fetchall()
                            for r in tasks:
                                db.execute(
                                    "UPDATE inspection_tasks SET result='normal', remark='运行正常', check_time=? WHERE id=?",
                                    (start_date + ' 08:30', r['id'])
                                )
        db.commit()
        print("[Seed] Inspection plans seeded.")

def seed_alerts():
    """历史告警种子数据（仅首次）"""
    with get_db() as db:
        acnt = db.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
        if acnt == 0:
            # 从各类型站点取前几个生成告警
            sid_map = {}
            # 种子数据不再生成阈值类告警，异常告警由定时数据生成时自动产生
            pass

def seed_abnormal_scenarios():
    """注入15种异常场景数据，用于全流程演示（可重复运行，通过标记避免重复）"""
    with get_db() as db:
        # 检查是否已注入
        marker = db.execute("SELECT id FROM timeline_events WHERE event_type='abnormal_scenarios_seeded' LIMIT 1").fetchone()
        if marker:
            print("[Seed] 异常场景数据已存在，跳过")
            return

        now = datetime.now()
        now_str = now.strftime('%Y-%m-%d %H:%M:%S')

        # 获取各类站点ID
        hydro_sites = db.execute("SELECT id, name FROM sites WHERE type='hydrology' ORDER BY id LIMIT 10").fetchall()
        wl_sites = db.execute("SELECT id, name FROM sites WHERE type='water_level' ORDER BY id LIMIT 10").fetchall()
        rain_sites = db.execute("SELECT id, name FROM sites WHERE type='rainfall' ORDER BY id LIMIT 10").fetchall()
        soil_sites = db.execute("SELECT id, name FROM sites WHERE type='soil_moisture' ORDER BY id LIMIT 5").fetchall()
        all_sites = db.execute("SELECT id, name, type FROM sites ORDER BY id LIMIT 20").fetchall()

        if len(all_sites) < 10:
            print("[Seed] 站点数据不足，跳过异常场景注入")
            return

        print("[Seed] 开始注入15种异常场景...")

        # === 场景1：站点离线（预设离线站点5,108,193已在generate_sensor_data中处理） ===
        # 额外设置几个站点为离线状态
        offline_site_ids = [5, 108, 193]
        for sid in offline_site_ids:
            db.execute("UPDATE sites SET status='offline' WHERE id=?", (sid,))
            db.execute("UPDATE device_shadows SET status='offline', last_data_time=NULL WHERE site_id=?", (sid,))
        print(f"  [场景1] 设置 {len(offline_site_ids)} 个站点离线")

        # === 场景2：数据突变告警 ===
        if hydro_sites:
            sid = hydro_sites[0]['id']
            # 注入一个突变值到sensor_data
            db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",
                       (sid, 'water_level', 15.8, 'm', now_str))
            create_alert_internal(db, sid, 'data_spike', 15.8, 'red',
                f'数据异常陡增：水位 15.80m（均值4.20m，变化276%）')
        print("  [场景2] 数据突变告警已创建")

        # === 场景3：数据冻结告警 ===
        if wl_sites:
            sid = wl_sites[1]['id'] if len(wl_sites) > 1 else wl_sites[0]['id']
            # 注入6条相同值的数据
            for i in range(6):
                t = (now - timedelta(minutes=i*5)).strftime('%Y-%m-%d %H:%M:%S')
                db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",
                           (sid, 'water_level', 3.45, 'm', t))
            create_alert_internal(db, sid, 'data_freeze', 3.45, 'yellow',
                f'数据冻结：水位连续6条记录值一致（3.45），传感器可能故障')
        print("  [场景3] 数据冻结告警已创建")

        # === 场景4：数据延迟/缺失告警 ===
        if rain_sites:
            sid = rain_sites[2]['id'] if len(rain_sites) > 2 else rain_sites[0]['id']
            create_alert_internal(db, sid, 'data_gap', 180, 'yellow',
                f'数据延迟：降雨量已有180分钟未更新')
        print("  [场景4] 数据缺失告警已创建")

        # === 场景5：设备离线告警 ===
        if soil_sites:
            sid = soil_sites[0]['id']
            dev = db.execute("SELECT id FROM device_shadows WHERE site_id=? LIMIT 1", (sid,)).fetchone()
            if dev:
                db.execute("UPDATE device_shadows SET status='offline', last_data_time=NULL WHERE id=?", (dev['id'],))
                create_alert_internal(db, sid, 'device_status', 0, 'yellow',
                    f'设备离线: 土壤水分传感器 · {all_sites[0]["name"]}')
        print("  [场景5] 设备离线告警已创建")

        # === 场景6：告警未确认（pending状态，已在上面创建中体现） ===
        print("  [场景6] 多条pending状态告警已存在")

        # === 场景7：告警转工单（创建已关联的告警+工单对） ===
        if len(all_sites) > 5:
            sid = all_sites[5]['id']
            # 创建告警
            db.execute("""
                INSERT INTO alerts (site_id,metric,value,level,message,status,flow_type,flow_status)
                VALUES (?,?,?,?,?,?,?,?)
            """, (sid, 'device_status', 0, 'yellow', '设备离线: 雷达水位计', 'pending', 'auto', 'converted'))
            alert_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            # 创建关联工单
            order_no = f"WO-{now.strftime('%Y%m%d')}-701"
            db.execute("""
                INSERT INTO work_orders (order_no,site_id,source,event_type,level,title,description,assignee,status,sla_deadline,related_alert_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (order_no, sid, 'auto', '设备故障', 'normal', '[自动] 设备离线: 雷达水位计',
                  '设备离线: 雷达水位计', '张建国', 'in_progress',
                  (now + timedelta(hours=72)).strftime('%Y-%m-%d %H:%M'), alert_id))
            db.execute("UPDATE alerts SET related_order_no=?, flow_status='converted' WHERE id=?", (order_no, alert_id))
        print("  [场景7] 告警-工单关联对已创建")

        # === 场景8：工单超时（SLA超期） ===
        if len(all_sites) > 6:
            sid = all_sites[6]['id']
            past_deadline = (now - timedelta(hours=5)).strftime('%Y-%m-%d %H:%M')
            order_no = f"WO-{now.strftime('%Y%m%d')}-801"
            db.execute("""
                INSERT INTO work_orders (order_no,site_id,source,event_type,level,title,description,assignee,status,sla_deadline,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (order_no, sid, 'auto', '设备故障', 'urgent', '水位计数据中断',
                  '设备持续2小时无数据上报', '张建国', 'in_progress', past_deadline,
                  (now - timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')))
        print("  [场景8] SLA超时工单已创建")

        # === 场景9：工单长时间未更新 ===
        if len(all_sites) > 7:
            sid = all_sites[7]['id']
            order_no = f"WO-{now.strftime('%Y%m%d')}-901"
            db.execute("""
                INSERT INTO work_orders (order_no,site_id,source,event_type,level,title,description,assignee,status,sla_deadline,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (order_no, sid, 'patrol', '巡检维修', 'normal', '护栏损坏修复',
                  '巡检发现河道护栏损坏', '黎明', 'in_progress',
                  (now + timedelta(hours=48)).strftime('%Y-%m-%d %H:%M'),
                  (now - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S')))
        print("  [场景9] 长时间未更新工单已创建")

        # === 场景10：巡检异常 ===
        if len(all_sites) > 3:
            sid = all_sites[3]['id']
            # 创建巡检计划
            db.execute("""
                INSERT INTO inspection_plans (plan_name,site_id,type,start_date,end_date,status,period)
                VALUES (?,?,?,?,?,?,?)
            """, (f"异常巡检-{now.strftime('%Y%m%d')}", sid, 'daily',
                  now.strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d'), 'in_progress', 'daily'))
            plan_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            # 创建异常巡检任务
            db.execute("""
                INSERT INTO inspection_tasks (plan_id,site_id,check_item,result,check_time,remark)
                VALUES (?,?,?,?,?,?)
            """, (plan_id, sid, '水位计校验', 'abnormal',
                  (now - timedelta(hours=2)).strftime('%Y-%m-%d %H:%M:%S'), '水位计读数偏差超过5cm'))
            # 触发告警
            create_alert_internal(db, sid, 'inspection', 0, 'yellow',
                '巡检异常：水位计校验 - 水位计读数偏差超过5cm')
        print("  [场景10] 巡检异常告警已创建")

        # === 场景11：巡检计划逾期未完成 ===
        if len(all_sites) > 8:
            sid = all_sites[8]['id']
            past_date = (now - timedelta(days=3)).strftime('%Y-%m-%d')
            db.execute("""
                INSERT INTO inspection_plans (plan_name,site_id,type,start_date,end_date,status,period)
                VALUES (?,?,?,?,?,?,?)
            """, ('逾期未完成巡检-演示', sid, 'weekly', past_date, past_date, 'pending', 'weekly'))
            plan_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            # 创建未完成的任务
            for item in ['设备外观检查', '数据采集器校验', '通信模块检查']:
                db.execute("""
                    INSERT INTO inspection_tasks (plan_id,site_id,check_item)
                    VALUES (?,?,?)
                """, (plan_id, sid, item))
        print("  [场景11] 逾期未完成巡检计划已创建")

        # === 场景12：备件库存不足 ===
        # 将某个备件库存降到0以下
        low_part = db.execute("SELECT id FROM spare_parts_inventory WHERE part_code='BJ-005'").fetchone()
        if low_part:
            db.execute("UPDATE spare_parts_inventory SET quantity=0, min_quantity=2 WHERE id=?", (low_part['id'],))
        print("  [场景12] 备件库存不足已设置")

        # === 场景13：备件申请待审批 ===
        # 已在seed_data中创建，这里确保有pending状态的申请
        pending_req = db.execute("SELECT COUNT(*) FROM spare_part_requests WHERE status='pending'").fetchone()[0]
        if pending_req == 0:
            rno = f"BJ-{now.strftime('%Y%m%d')}-999"
            db.execute("""
                INSERT INTO spare_part_requests (request_no,site_id,applicant,part_name,quantity,reason,status)
                VALUES (?,?,?,?,?,?,?)
            """, (rno, all_sites[0]['id'], '运维人员', '雷达水位计', 1, '设备故障需更换', 'pending'))
        print("  [场景13] 备件申请待审批已确认")

        # === 场景14：热线事件未处理 ===
        # 创建一个新的未处理热线事件
        db.execute("""
            INSERT INTO hotline_events (caller_name,caller_phone,event_type,description,location,status,operator,created_at)
            VALUES (?,?,?,?,?,?,?,?)
        """, ('赵先生', '13900009900', '水位异常', '河道水位上涨迅速，疑似上游水库泄洪',
              '赣江下游段', 'registered', '李敏',
              (now - timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S')))
        print("  [场景14] 未处理热线事件已创建")

        # === 场景15：热线转工单后工单未完成 ===
        # 创建热线事件+关联工单
        db.execute("""
            INSERT INTO hotline_events (caller_name,caller_phone,event_type,description,location,status,related_order_no,site_id,operator,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, ('孙女士', '13900008800', '设施损坏', '堤防护坡出现塌陷', '城南堤防段',
              'dispatched', f"WO-{now.strftime('%Y%m%d')}-1501", all_sites[2]['id'], '王芳',
              (now - timedelta(hours=3)).strftime('%Y-%m-%d %H:%M:%S')))
        order_no = f"WO-{now.strftime('%Y%m%d')}-1501"
        db.execute("""
            INSERT INTO work_orders (order_no,site_id,source,event_type,level,title,description,assignee,status,sla_deadline,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (order_no, all_sites[2]['id'], 'hotline', '设施维修', 'urgent',
              '[热线] 堤防护坡塌陷', '堤防护坡出现塌陷，需紧急修复', '王刚', 'in_progress',
              (now + timedelta(hours=4)).strftime('%Y-%m-%d %H:%M'),
              (now - timedelta(hours=3)).strftime('%Y-%m-%d %H:%M:%S')))
        print("  [场景15] 热线转工单（未完成）已创建")

        # 注入标记
        db.execute("""
            INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark)
            VALUES ('system',0,'abnormal_scenarios_seeded','系统','15种异常场景数据注入完成')
        """)
        db.commit()
        print("[Seed] 15种异常场景数据注入完成！")

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

def seed_maintenance_templates():
    """预置标准化运维模板（仅首次）"""
    templates = [
        # === 日常维护类（站院环境）===
        ('日常维护','environment','驻测站站院环境维护（每周）','weekly',
         '对水位井、站院、大门口进行全面的打扫，确保干净整洁',
         '地面、窗台、设备等干净整洁，墙面、天花板无污迹、蜘蛛网、昆虫等',
         '[{"id":"c1","label":"水位井区域全面打扫"},{"id":"c2","label":"站院地面及大门口清洁"},{"id":"c3","label":"设备表面及窗台擦拭"},{"id":"c4","label":"墙面天花板检查（无污迹/蜘蛛网）"},{"id":"c5","label":"站院草地灌木修剪维护"}]',
         1, 2, 1),
        ('日常维护','observation','观测场草地维护（每半月）','biweekly',
         '对降蒸观测场草地进行维护，草皮高度符合规范要求',
         '降蒸观测场、站院草皮高度低于20cm，遇重大活动增加维护次数',
         '[{"id":"c1","label":"草地修剪（草高<20cm）"},{"id":"c2","label":"杂草清理"},{"id":"c3","label":"场地平整度检查"},{"id":"c4","label":"巡测站站房全面打扫"}]',
         1, 2, 2),
        ('日常维护','section','断面环境管理（每月+汛后）','monthly',
         '测流断面、水尺断面、码头清理杂草杂木淤泥，确保断面整洁',
         '断面无积水、无淤泥、无杂草、无杂物',
         '[{"id":"c1","label":"测流断面上下游各5米杂草清理"},{"id":"c2","label":"缆道铁塔四周清理"},{"id":"c3","label":"基本水尺断面上下游各10米清理"},{"id":"c4","label":"水尺码头/停船码头淤泥清理"},{"id":"c5","label":"比降断面水尺道路清理（汛期）"},{"id":"c6","label":"洪水退水及时清理"}]',
         1, 3, 3),
        # === 日常管理类（水位观测）===
        ('日常管理','water_level','水位项目日常巡查（每日/每周）','weekly',
         '观测基本水尺读数并记录，校对遥测水位及时间，检查清洗水尺设备',
         '人工与遥测水位相差≥0.02m时需复核报送调整；驻测站每日2次，巡测站每日1次',
         '[{"id":"c1","label":"基本水尺读数记录"},{"id":"c2","label":"遥测水位及时间校对"},{"id":"c3","label":"偏差检测（≥0.02m报送水情科）"},{"id":"c4","label":"水尺清洗检查"},{"id":"c5","label":"水位设备运行检查"},{"id":"c6","label":"填写水位巡查表并拍照存档"}]',
         1, 0.5, 4),
        ('日常管理','facility','设施设备巡查（每月）','monthly',
         '检查清洗水尺，对设施设备、爬梯、护栏牢固度进行全面检查',
         '填写设施设备巡查表，异常维修拍照存档并报中心站网监测科',
         '[{"id":"c1","label":"水尺清洗检查"},{"id":"c2","label":"爬梯牢固度检查"},{"id":"c3","label":"护栏牢固度检查"},{"id":"c4","label":"设施设备外观检查"},{"id":"c5","label":"异常维修拍照存档"},{"id":"c6","label":"上报中心站网监测科"}]',
         1, 2, 5),
        ('日常管理','safety','安全检查（每月）','monthly',
         '对测验设施设备、安全环境、站房、灭火器、安全器材进行全面安全检查',
         '填记安全检查记录表，存在安全隐患需及时告知鄱阳湖水文水资源监测中心',
         '[{"id":"c1","label":"灭火器压力及有效期检查"},{"id":"c2","label":"安全器材完好性检查"},{"id":"c3","label":"站房结构安全检查"},{"id":"c4","label":"电气线路检查"},{"id":"c5","label":"填写安全检查记录表"},{"id":"c6","label":"安全隐患告知中心"}]',
         1, 1.5, 6),
        ('日常管理','generator','发电机保养维护（每月+汛前汛后）','monthly',
         '每月检查机油线路并运行≥30分钟；每年汛前汛后更换机油及线路保养',
         '发电机运行正常，备足燃料及机油，记录运行时间',
         '[{"id":"c1","label":"机油液位检查"},{"id":"c2","label":"线路及各部件检查"},{"id":"c3","label":"发电运行≥30分钟并记录"},{"id":"c4","label":"燃料及机油储备检查"},{"id":"c5","label":"汛前/汛后更换机油保养"}]',
         1, 1.5, 7),
        # === 设备仪器维护类 ===
        ('设备仪器维护','rainfall','雨量项目日常巡检（每月）','monthly',
         '遥测雨量器现场运行维护巡检，含数据采集终端、供电设备、雨量筒检查',
         '每季度进行注水试验（≥12.5mm，误差≤±4%），特大暴雨后及时检查',
         '[{"id":"c1","label":"数据采集终端外观及状态检查"},{"id":"c2","label":"供电设备检查"},{"id":"c3","label":"布线检查"},{"id":"c4","label":"雨量筒外观/器口水平检查"},{"id":"c5","label":"环境清理"},{"id":"c6","label":"季度注水试验（误差≤±4%）"}]',
         1, 2, 8),
        ('设备仪器维护','evaporation','蒸发项目日常巡检（每月）','monthly',
         '自动蒸发设备遥测终端现场运行维护巡检及换水',
         '每月不少于1次巡测，每半年渗漏检查，每月至少换水一次保持清洁',
         '[{"id":"c1","label":"自动蒸发设备遥测终端巡检"},{"id":"c2","label":"蒸发器换水（保持清洁）"},{"id":"c3","label":"水圈清洁及环境维护"},{"id":"c4","label":"渗漏检查（每半年）"},{"id":"c5","label":"数据合理性检查"},{"id":"c6","label":"汛前自动注水实验"}]',
         1, 1.5, 9),
        ('设备仪器维护','cableway','缆道日常巡检（测流时）','seasonal',
         '测流时对主索、循环索、锚碇、导向轮、绞车等进行检查维护',
         '检查锚碇位移、钢丝绳夹头松紧、绞车运转；异常拍照留底并通知甲方',
         '[{"id":"c1","label":"主索/循环索检查维护"},{"id":"c2","label":"拉线/卡头检查（异常通知甲方）"},{"id":"c3","label":"工作索毛刺断骨拍照留底"},{"id":"c4","label":"锚碇位移/土壤裂纹检查"},{"id":"c5","label":"导向轮/游轮运转检查"},{"id":"c6","label":"绞车运转检查"},{"id":"c7","label":"钢丝绳夹头/生锈/排水检查"}]',
         1, 3, 10),
        ('设备仪器维护','soil_moisture','墒情站日常巡查（季度）','seasonal',
         '对墒情基本站进行巡查，保持整洁、数据校测',
         '每季度对基本站巡查不少于1次，保持机箱内干净整洁，清理周边杂草；干旱天气取土检验',
         '[{"id":"c1","label":"机箱内部清洁"},{"id":"c2","label":"周边杂草清理"},{"id":"c3","label":"无积水检查"},{"id":"c4","label":"数据校测记录"},{"id":"c5","label":"辅助站取土烘干法检验（干旱触发）"}]',
         0, 1.5, 11),
    ]
    with get_db() as db:
        cnt = db.execute("SELECT COUNT(*) FROM maintenance_templates").fetchone()[0]
        if cnt == 0:
            for t in templates:
                db.execute(
                    "INSERT INTO maintenance_templates (category,sub_category,title,frequency,description,standard,check_items,photo_required,estimated_hours,sort_order) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    t
                )
            db.commit()
            print(f"[Seed] {len(templates)} maintenance templates seeded.")

def seed_inspection_v2():
    """巡检V2三层架构种子数据：方案模板 + 巡检配置 + 排程初始化"""
    with get_db() as db:
        cnt = db.execute("SELECT COUNT(*) FROM inspection_templates").fetchone()[0]
        if cnt > 0:
            print("[InspV2] 模板已存在，跳过")
            # 确保排程已初始化
            sch_cnt = db.execute("SELECT COUNT(*) FROM inspection_schedules").fetchone()[0]
            if sch_cnt == 0:
                _init_v2_schedules(db)
            return

        now = datetime.now()
        today = now.strftime('%Y-%m-%d')

        # === 第一层：方案模板 ===
        templates_data = [
            # (template_name, category, frequency, description, items)
            # items = [(item_name, category, frequency_level, photo_required, sort_order), ...]
            ('水位观测日常方案', '水位观测', 'daily', '每日水位观测及设备的日常巡查', [
                ('基本水尺读数观测记录', '水位观测', 'high', 1, 1),
                ('遥测水位及时间校对', '水位观测', 'high', 0, 2),
                ('人工与遥测水位偏差检测', '水位观测', 'high', 0, 3),
                ('水尺清洗检查', '水位观测', 'mid', 1, 4),
                ('水位设备运行检查', '水位观测', 'mid', 0, 5),
                ('填记水位巡查表并拍照存档', '水位观测', 'high', 1, 6),
            ]),
            ('水位观测月度方案', '水位观测', 'monthly', '月度水位观测设备深度检查', [
                ('水位计精度校验', '水位观测', 'mid', 0, 1),
                ('水位数据完整性审查', '水位观测', 'mid', 0, 2),
                ('传感器线缆检查', '水位观测', 'low', 0, 3),
                ('备品备件储备检查', '水位观测', 'low', 0, 4),
            ]),
            ('雨量监测日常方案', '雨量监测', 'daily', '每日雨量监测设备巡查', [
                ('雨量筒外观及水平检查', '雨量监测', 'mid', 1, 1),
                ('翻斗灵活性检查', '雨量监测', 'high', 0, 2),
                ('数据采集终端状态检查', '雨量监测', 'high', 0, 3),
                ('供电设备检查', '雨量监测', 'mid', 0, 4),
            ]),
            ('雨量监测季度方案', '雨量监测', 'quarterly', '季度雨量监测设备深度维护', [
                ('注水试验(≥12.5mm误差≤±4%)', '雨量监测', 'low', 0, 1),
                ('雨量筒内部清洁', '雨量监测', 'mid', 1, 2),
                ('特大暴雨后设备全面检查', '雨量监测', 'low', 1, 3),
            ]),
            ('蒸发监测月度方案', '蒸发监测', 'monthly', '月度蒸发监测设备维护', [
                ('自动蒸发设备遥测终端巡检', '蒸发监测', 'mid', 0, 1),
                ('蒸发器换水保持清洁', '蒸发监测', 'mid', 1, 2),
                ('水圈清洁及环境维护', '蒸发监测', 'mid', 1, 3),
                ('数据合理性检查', '蒸发监测', 'mid', 0, 4),
                ('渗漏检查(半年期)', '蒸发监测', 'low', 0, 5),
            ]),
            ('蒸发监测半年方案', '蒸发监测', 'semi_annual', '半年度蒸发监测深度检查', [
                ('蒸发系统全面渗漏检查', '蒸发监测', 'low', 0, 1),
                ('汛前自动注水实验', '蒸发监测', 'low', 1, 2),
            ]),
            ('站院环境周方案', '站院环境', 'weekly', '每周站院环境维护', [
                ('水位井/站院/大门口全面打扫', '站院环境', 'high', 1, 1),
                ('设备表面及窗台擦拭', '站院环境', 'mid', 1, 2),
                ('墙面天花板检查(无污迹/蜘蛛网)', '站院环境', 'low', 0, 3),
                ('草地灌木修剪维护', '站院环境', 'mid', 1, 4),
                ('巡测站站房全面打扫', '站院环境', 'mid', 1, 5),
                ('观测场草地维护(草高<20cm)', '站院环境', 'mid', 1, 6),
            ]),
            ('站院环境月方案', '站院环境', 'monthly', '月度站院深度清洁维护', [
                ('站房深度清洁(含窗户/天花板)', '站院环境', 'mid', 1, 1),
                ('仪器设备全面擦拭', '站院环境', 'mid', 1, 2),
                ('排水沟清理', '站院环境', 'low', 0, 3),
                ('站院安全隐患排查', '站院环境', 'low', 0, 4),
            ]),
            ('设施设备巡查方案', '设施设备', 'monthly', '月度设施设备全面检查', [
                ('水尺清洗检查', '设施设备', 'mid', 1, 1),
                ('爬梯/护栏牢固度全面检查', '设施设备', 'mid', 0, 2),
                ('设施设备外观检查', '设施设备', 'mid', 1, 3),
                ('异常维修与拍照存档', '设施设备', 'mid', 1, 4),
                ('上报中心站网监测科', '设施设备', 'low', 0, 5),
            ]),
            ('安全检查月方案', '安全检查', 'monthly', '月度安全全面检查', [
                ('测验设施设备安全环境检查', '安全防护', 'mid', 0, 1),
                ('灭火器压力及有效期检查', '安全防护', 'mid', 1, 2),
                ('安全器材完好性检查', '安全防护', 'mid', 0, 3),
                ('站房结构安全及电气线路检查', '安全防护', 'mid', 0, 4),
                ('填写安全检查记录表', '安全防护', 'mid', 1, 5),
                ('安全隐患及时告知中心', '安全防护', 'low', 0, 6),
            ]),
            ('发电机保养方案', '发电机', 'quarterly', '季度发电机保养维护', [
                ('发电机维护保养(更换机油/线路/备足燃料)', '发电机', 'low', 1, 1),
                ('机油液位检查', '发电机', 'mid', 0, 2),
                ('线路及各部件检查', '发电机', 'mid', 0, 3),
                ('发电运行≥30分钟并记录', '发电机', 'mid', 1, 4),
                ('燃料及机油储备检查', '发电机', 'mid', 0, 5),
            ]),
            ('缆道系统巡查方案', '缆道系统', 'monthly', '月度缆道系统检查维护', [
                ('行主索/循环索检查维护', '缆道系统', 'mid', 1, 1),
                ('拉线/卡头检查(异常通知甲方)', '缆道系统', 'mid', 1, 2),
                ('工作索毛刺断骨拍照留底', '缆道系统', 'mid', 1, 3),
                ('锚碇位移/土壤裂纹检查', '缆道系统', 'mid', 0, 4),
                ('导向轮/游轮/行车架运转检查', '缆道系统', 'mid', 0, 5),
                ('绞车运转检查', '缆道系统', 'mid', 0, 6),
                ('钢丝绳夹头/生锈/排水检查', '缆道系统', 'low', 0, 7),
            ]),
            ('断面环境季度方案', '断面环境', 'quarterly', '季度断面环境清理维护', [
                ('测流断面上下游各5米清理杂草杂木', '断面环境', 'mid', 1, 1),
                ('缆道铁塔四周清理', '断面环境', 'mid', 1, 2),
                ('基本水尺断面上下游各10米清理', '断面环境', 'mid', 1, 3),
                ('水尺码头/停船码头清理淤泥杂草', '断面环境', 'mid', 1, 4),
                ('比降断面水尺道路清理', '断面环境', 'low', 0, 5),
            ]),
            ('墒情监测日常方案', '墒情监测', 'daily', '每日墒情监测设备巡查', [
                ('机箱内部清洁', '墒情监测', 'mid', 1, 1),
                ('周边杂草清理', '墒情监测', 'mid', 0, 2),
                ('无积水检查', '墒情监测', 'mid', 0, 3),
                ('数据校测记录', '墒情监测', 'high', 0, 4),
            ]),
        ]

        template_ids = {}  # template_name -> id
        item_ids = {}      # (template_name, item_name) -> id

        for tpl_name, category, frequency, desc, items in templates_data:
            db.execute("""
                INSERT INTO inspection_templates (template_name, category, frequency, description, sort_order)
                VALUES (?,?,?,?,?)
            """, (tpl_name, category, frequency, desc, len(template_ids) + 1))
            tid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            template_ids[tpl_name] = tid
            for item_name, item_cat, freq_level, photo_req, sort_ord in items:
                db.execute("""
                    INSERT INTO inspection_template_items (template_id, item_name, category, frequency_level, photo_required, sort_order)
                    VALUES (?,?,?,?,?,?)
                """, (tid, item_name, item_cat, freq_level, photo_req, sort_ord))
                iid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
                item_ids[(tpl_name, item_name)] = iid

        print(f"[InspV2] {len(templates_data)} 个方案模板已创建")

        # === 第二层：巡检配置（站点类型 → 模板匹配） ===
        config_map = {
            'hydrology': [
                '水位观测日常方案', '水位观测月度方案',
                '站院环境周方案', '站院环境月方案',
                '设施设备巡查方案', '安全检查月方案',
                '发电机保养方案', '缆道系统巡查方案',
            ],
            'water_level': [
                '水位观测日常方案', '水位观测月度方案',
                '站院环境周方案', '站院环境月方案',
                '设施设备巡查方案', '安全检查月方案',
            ],
            'rainfall': [
                '雨量监测日常方案', '雨量监测季度方案',
                '站院环境周方案', '站院环境月方案',
                '设施设备巡查方案', '安全检查月方案',
            ],
            'evaporation': [
                '蒸发监测月度方案', '蒸发监测半年方案',
                '站院环境周方案', '站院环境月方案',
                '设施设备巡查方案', '安全检查月方案',
            ],
            'soil_moisture': [
                '墒情监测日常方案',
                '站院环境周方案', '站院环境月方案',
                '设施设备巡查方案',
            ],
            'groundwater': [
                '水位观测日常方案',
                '站院环境月方案',
                '设施设备巡查方案',
            ],
            'station_yard': [
                '站院环境周方案', '站院环境月方案',
                '安全检查月方案',
            ],
        }

        config_count = 0
        for site_type, tpl_names in config_map.items():
            for tpl_name in tpl_names:
                tid = template_ids.get(tpl_name)
                if tid:
                    db.execute("""
                        INSERT INTO inspection_configs (site_type, device_types, template_id, is_active)
                        VALUES (?,?,?,1)
                    """, (site_type, '', tid))
                    config_count += 1

        print(f"[InspV2] {config_count} 条巡检配置规则已创建")

        # === 初始化排程 ===
        _init_v2_schedules(db)

        # === 默认提醒配置 ===
        db.execute("""
            INSERT INTO inspection_reminders (remind_days_before, remind_method, overdue_escalation, escalation_days, is_active)
            VALUES (1, 'notification', 1, 3, 1)
        """)
        db.commit()
        print("[InspV2] 默认提醒配置已创建")
        print("[InspV2] 三层架构种子数据初始化完成！")

def _init_v2_schedules(db):
    """根据巡检配置为所有站点初始化排程"""
    import random
    now = datetime.now()
    today = now.strftime('%Y-%m-%d')

    # 频次对应的天数
    freq_days = {
        'daily': 1, 'weekly': 7, 'monthly': 30,
        'quarterly': 90, 'semi_annual': 180, 'annual': 365,
    }

    # 获取所有站点
    sites = db.execute("SELECT id, type FROM sites").fetchall()
    if not sites:
        return

    # 获取所有配置
    configs = db.execute("""
        SELECT ic.site_type, ic.template_id, it.template_name, it.frequency
        FROM inspection_configs ic
        JOIN inspection_templates it ON ic.template_id = it.id
        WHERE ic.is_active = 1
    """).fetchall()

    # 按站点类型分组配置
    type_configs = {}
    for cfg in configs:
        st = cfg['site_type']
        if st not in type_configs:
            type_configs[st] = []
        type_configs[st].append(cfg)

    schedule_count = 0
    for site in sites:
        site_type = site['type']
        matched = type_configs.get(site_type, [])
        if not matched:
            # 通用配置：至少给站院环境周方案
            matched = type_configs.get('station_yard', [])

        for cfg in matched:
            tpl_id = cfg['template_id']
            frequency = cfg['frequency']
            # 获取该模板的所有检查项
            items = db.execute("""
                SELECT id, item_name FROM inspection_template_items
                WHERE template_id = ?
            """, (tpl_id,)).fetchall()

            for item in items:
                # 检查是否已有排程
                existing = db.execute("""
                    SELECT id FROM inspection_schedules
                    WHERE site_id=? AND template_item_id=?
                """, (site['id'], item['id'])).fetchone()
                if existing:
                    continue

                # 计算初始 next_due_date（随机偏移模拟历史执行）
                fd = freq_days.get(frequency, 30)
                # 部分项已执行过几个周期
                past_cycles = random.randint(0, 3)
                due_date = now - timedelta(days=past_cycles * fd) + timedelta(days=fd)
                # 确保不超过今天太多
                if due_date > now + timedelta(days=fd):
                    due_date = now + timedelta(days=random.randint(0, fd))

                db.execute("""
                    INSERT INTO inspection_schedules (site_id, template_id, template_item_id, frequency, next_due_date, cycle_count)
                    VALUES (?,?,?,?,?,?)
                """, (site['id'], tpl_id, item['id'], frequency,
                      due_date.strftime('%Y-%m-%d'), past_cycles))
                schedule_count += 1

    db.commit()
    print(f"[InspV2] {schedule_count} 条排程记录已初始化")

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
    """为单个站点生成传感器数据，并检测异常"""
    sid = site['id']; stype = site['type']
    river = site['river'] or ''
    th = RIVER_THRESHOLDS.get(river, RIVER_THRESHOLDS[''])
    base_wl = th['base']
    metrics_gen = []  # 记录已生成的指标，供异常检测使用

    if stype == 'rainfall':
        is_rainy = random.random() < 0.35
        precip = round(random.uniform(0.5, 25) if is_rainy else 0, 1)
        cum = get_site_trend(sid,'cum',random.uniform(20,80),5,0,300)
        db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",
            (sid,'precipitation',precip,'mm/h',now))
        db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",
            (sid,'cumulative_rainfall',cum,'mm',now))
        metrics_gen = [('precipitation', precip), ('cumulative_rainfall', cum)]

    elif stype == 'water_level':
        wl = get_site_trend(sid,'wl',base_wl,0.06,base_wl-2,th['critical']+1)
        flow = get_site_trend(sid,'flow',round(random.uniform(200,2000),0),50,10,5000)
        db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",
            (sid,'water_level',wl,'m',now))
        db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",
            (sid,'flow',flow,'m³/s',now))
        metrics_gen = [('water_level', wl), ('flow', flow)]

    elif stype == 'hydrology':
        wl = get_site_trend(sid,'wl_h',base_wl,0.05,base_wl-1,th['critical']+0.5)
        vel = get_site_trend(sid,'vel',2.5,0.15,0.3,6.0)
        flow = get_site_trend(sid,'flow_h',round(random.uniform(300,3000),0),80,20,8000)
        precip = round(random.uniform(0, 15) if random.random() < 0.3 else 0, 1)
        db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",
            (sid,'water_level',wl,'m',now))
        db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",
            (sid,'velocity',vel,'m/s',now))
        db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",
            (sid,'flow',flow,'m³/s',now))
        db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",
            (sid,'precipitation',precip,'mm/h',now))
        metrics_gen = [('water_level', wl), ('velocity', vel), ('flow', flow), ('precipitation', precip)]

    elif stype == 'soil_moisture':
        sm = get_site_trend(sid,'sm',55,1.5,15,100)
        st = get_site_trend(sid,'st',22,0.5,5,45)
        db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",
            (sid,'soil_moisture',sm,'%',now))
        db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",
            (sid,'soil_temperature',st,'°C',now))
        metrics_gen = [('soil_moisture', sm), ('soil_temperature', st)]

    elif stype == 'evaporation':
        evap = get_site_trend(sid,'evap',4.0,0.3,0,15)
        temp = get_site_trend(sid,'temp_e',28,1.5,10,45)
        wind = get_site_trend(sid,'wind_e',3.0,0.5,0,12)
        db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",
            (sid,'evaporation',evap,'mm',now))
        db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",
            (sid,'temperature',temp,'°C',now))
        db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",
            (sid,'wind_speed',wind,'m/s',now))
        metrics_gen = [('evaporation', evap), ('temperature', temp), ('wind_speed', wind)]

    elif stype == 'groundwater':
        gwl = get_site_trend(sid,'gwl',25,0.5,5,50)
        wq = get_site_trend(sid,'wq',7.0,0.15,5.5,9.0)
        db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",
            (sid,'groundwater_level',gwl,'m',now))
        db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",
            (sid,'water_quality',wq,'pH',now))
        metrics_gen = [('groundwater_level', gwl), ('water_quality', wq)]

    elif stype == 'station_yard':
        temp_s = get_site_trend(sid,'temp_s',26,1.0,10,45)
        noise = get_site_trend(sid,'noise',55,2,30,90)
        db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",
            (sid,'temperature',temp_s,'°C',now))
        db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",
            (sid,'noise',noise,'dB',now))
        metrics_gen = [('temperature', temp_s), ('noise', noise)]

    # 对每个指标进行异常检测
    for metric, val in metrics_gen:
        detect_site_anomalies(db, sid, stype, metric, val, now)

def auto_resolve_alerts(db, site_id):
    """检查未办结告警对应站点的数据是否已恢复，是则自动办结"""
    try:
        unresolved = db.execute(
            "SELECT id, metric FROM alerts WHERE site_id=? AND status IN ('pending','acknowledged') AND flow_type='auto'",
            (site_id,)
        ).fetchall()
        for a in unresolved:
            if a['metric'] == 'device_status':
                continue  # 设备状态告警需人工确认
            # 检查是否有最近1小时的数据
            has_data = db.execute(
                "SELECT COUNT(*) FROM sensor_data WHERE site_id=? AND recorded_at >= datetime('now','-1 hour')",
                (site_id,)
            ).fetchone()[0]
            if has_data > 0:
                db.execute("UPDATE alerts SET status='resolved', resolved_at=datetime('now','localtime') WHERE id=?", (a['id'],))
    except Exception as e:
        print(f'[AutoResolve] error site={site_id}: {e}')

def detect_site_anomalies(db, site_id, site_type, metric, current_value, recorded_at):
    """检测单个站点指标的异常情况：突变、冻结、缺失"""
    METRIC_CN = {
        'water_level':'水位','flow':'流量','velocity':'流速','precipitation':'降雨量',
        'cumulative_rainfall':'累计雨量','soil_moisture':'土壤含水量','soil_temperature':'土壤温度',
        'evaporation':'蒸发量','temperature':'气温','wind_speed':'风速',
        'groundwater_level':'地下水位','water_quality':'水质','noise':'噪声',
        'data_spike':'数据突变','data_freeze':'数据冻结','data_gap':'数据缺失',
        'device_status':'设备状态'
    }
    metric_cn = METRIC_CN.get(metric, metric)
    try:
        # 在检测新异常之前，先检查已有的未办结告警是否可自动恢复
        auto_resolve_alerts(db, site_id)
        # 自动解除已有data_gap误报：站点恢复数据后自动办结告警
        try:
            existing_gaps = db.execute(
                "SELECT id FROM alerts WHERE site_id=? AND metric='data_gap' AND status IN ('pending','acknowledged')",
                (site_id,)
            ).fetchall()
            if existing_gaps:
                recent_data = db.execute(
                    "SELECT COUNT(*) FROM sensor_data WHERE site_id=? AND recorded_at >= datetime('now','-1 hour')",
                    (site_id,)
                ).fetchone()[0]
                if recent_data > 0:
                    for gap in existing_gaps:
                        db.execute(
                            "UPDATE alerts SET status='resolved', resolved_at=datetime('now','localtime') WHERE id=?",
                            (gap['id'],)
                        )
                        db.execute(
                            "INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                            ('alert', gap['id'], 'resolved', '系统', '数据已自动恢复，告警自动办结')
                        )
        except Exception:
            pass
        # 排除自然波动大的指标（降雨、风速、噪声等属于正常波动）
        EXCLUDE_SPIKE = {'precipitation','cumulative_rainfall','velocity','wind_speed','noise'}
        recent = db.execute(
            "SELECT value, recorded_at FROM sensor_data WHERE site_id=? AND metric=? ORDER BY recorded_at DESC LIMIT 12",
            (site_id, metric)
        ).fetchall()
        if len(recent) < 4:
            return
        values = [r['value'] for r in recent]
        timestamps = [r['recorded_at'] for r in recent]
        latest = values[0]

        # 1. 数据冻结检测：最近6条完全相同（适用于所有指标）
        if len(values) >= 6 and metric not in EXCLUDE_SPIKE:
            frozen = len(set(round(v, 4) for v in values[:6])) == 1
            if frozen:
                create_alert_internal(db, site_id, 'data_freeze', latest, 'yellow',
                    f'数据冻结：{metric_cn}连续6条记录值一致（{latest}），传感器可能故障')
                return

        # 2. 突变检测（排除自然波动指标）
        # 要求至少8条历史数据，确保趋势稳定后再检测（避免重启后误报）
        if len(values) >= 8 and metric not in EXCLUDE_SPIKE:
            prev_vals = values[1:8]
            mean = sum(prev_vals) / len(prev_vals)
            # 均值为0或接近0时跳过
            if abs(mean) < 0.001:
                return
            # 计算百分比变化
            pct_change = abs(latest - mean) / abs(mean)
            # 标准差检测
            std = (sum((v - mean)**2 for v in prev_vals) / len(prev_vals))**0.5
            if std < abs(mean) * 0.005:
                std = abs(mean) * 0.005
            z_score = abs(latest - mean) / std
            # 要求：变化幅度 > 30% 且 偏离 > 8σ，同时绝对变化值大于指标特定阈值
            min_abs_change = {'water_level': 0.8, 'flow': 800, 'soil_moisture': 10,
                              'temperature': 8, 'evaporation': 5, 'groundwater_level': 5,
                              'water_quality': 1.5}
            abs_change = abs(latest - mean)
            min_abs = min_abs_change.get(metric, abs(mean) * 0.35)
            if pct_change > 0.30 and z_score > 8 and abs_change > min_abs:
                direction = '陡增' if latest > mean else '陡降'
                level = 'red' if z_score > 10 else 'orange'
                create_alert_internal(db, site_id, 'data_spike', latest, level,
                    f'数据异常{direction}：{metric_cn} {latest:.2f}（均值{mean:.2f}，变化{pct_change*100:.0f}%）')

        # 3. 数据缺失检测
        if len(timestamps) >= 2:
            try:
                t1 = datetime.strptime(str(timestamps[0])[:19], '%Y-%m-%d %H:%M:%S')
                t0 = datetime.strptime(str(timestamps[1])[:19], '%Y-%m-%d %H:%M:%S')
                gap_min = (t1 - t0).total_seconds() / 60
                gap_thresholds = {
                    'water_level': 60,
                    'hydrology': 60,
                    'rainfall': 120,
                    'soil_moisture': 120,
                    'evaporation': 240,
                    'groundwater': 240,
                    'station_yard': 120,
                }
                threshold = gap_thresholds.get(site_type, 60)
                if gap_min > threshold:
                    create_alert_internal(db, site_id, 'data_gap', gap_min, 'yellow',
                        f'数据延迟：{metric_cn}已有{gap_min:.0f}分钟未更新')
            except Exception:
                pass
    except Exception as e:
        print(f'[Anomaly] 检测异常失败 site={site_id} metric={metric}: {e}')

def _scheduler_db():
    """专用调度器数据库连接（超时5秒，异步写入，避免阻塞API）"""
    db = sqlite3.connect(DB_PATH, timeout=5, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=5000")
    db.execute("PRAGMA synchronous=OFF")
    return db

def generate_sensor_data():
    """每30秒生成模拟传感器数据"""
    PRESET_OFFLINE = {5, 108, 193}  # 预设离线站点，跳过状态更新
    db = None
    try:
        db = _scheduler_db()
    except Exception as e:
        print(f'[Sim] 调度器连接失败: {e}')
        return
    try:
        sites = db.execute("SELECT * FROM sites").fetchall()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        for idx, site in enumerate(sites):
            sid = site['id']
            # 预设离线站点跳过所有数据生成，保持种子数据一致性
            if sid in PRESET_OFFLINE:
                # 预设离线站点：确保设备和站点状态为offline
                db.execute("UPDATE device_shadows SET status='offline' WHERE site_id=?", (sid,))
                db.execute("UPDATE sites SET status='offline' WHERE id=?", (sid,))
                try:
                    db.commit()
                except Exception:
                    pass
                continue
            try:
                _generate_site_data(site, db, now)
            except Exception as e:
                if 'database is locked' in str(e):
                    print(f'[Sim] DB locked, skip site {sid}')
                else:
                    print(f'[Sim] site {sid} error: {e}')

            # === 数据自洽性修复：设备/站点状态同步 ===
            # 0.5%概率设备离线（模拟真实场景），99.5%在线
            devices = db.execute("SELECT id FROM device_shadows WHERE site_id=?", (sid,)).fetchall()
            any_online = False
            for dev in devices:
                dev_status = 'offline' if random.random() < 0.005 else 'online'
                if dev_status == 'online':
                    any_online = True
                db.execute("UPDATE device_shadows SET status=?, last_data_time=? WHERE id=?",
                           (dev_status, now if dev_status == 'online' else None, dev['id']))

            # 站点状态根据设备状态决定：全部离线→站点离线，否则在线
            site_status = 'online' if any_online else 'offline'
            db.execute("UPDATE sites SET status=?, last_heartbeat=? WHERE id=?",
                       (site_status, now if site_status == 'online' else None, sid))

            # 每个站点单独提交，释放写锁，让API请求能快速插入
            try:
                db.commit()
            except Exception as e:
                print(f'[Sim] commit fail site {sid}: {e}')

        # === 数据自洽性修复：长时间无数据的设备自动标记离线 ===
        threshold_time = (datetime.now() - timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S')
        stale_devices = db.execute(
            "SELECT id, site_id FROM device_shadows WHERE last_data_time < ? AND status != 'offline'",
            (threshold_time,)
        ).fetchall()
        for dev in stale_devices:
            db.execute("UPDATE device_shadows SET status='offline' WHERE id=?", (dev['id'],))
            # 检查该站点是否所有设备都离线
            online_count = db.execute(
                "SELECT COUNT(*) FROM device_shadows WHERE site_id=? AND status='online'",
                (dev['site_id'],)
            ).fetchone()[0]
            if online_count == 0:
                db.execute("UPDATE sites SET status='offline' WHERE id=?", (dev['site_id'],))
        if stale_devices:
            db.commit()

        # === 数据到报率模拟（在同一个连接中完成） ===
        today = datetime.now().strftime('%Y-%m-%d')
        for site in sites:
            metrics_map = {
                'rainfall': 'rainfall',
                'water_level': 'water_level',
                'hydrology': 'water_level',
                'soil_moisture': 'soil_moisture',
                'evaporation': 'evaporation',
                'groundwater': 'water_level',
                'station_yard': 'environment',
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

        # === 天气数据 ===
        # 启动时尝试获取实时天气（不插入模拟数据，让 API 请求时自动刷新）
        fetch_real_weather()
        
        # === 离线设备告警 ===
        offline_devices = db.execute("""
            SELECT d.site_id, d.device_name, d.device_code, s.name as site_name
            FROM device_shadows d JOIN sites s ON d.site_id=s.id
            WHERE d.status='offline'
        """).fetchall()
        for dev in offline_devices:
            create_alert_internal(db, dev['site_id'], 'device_status', 0, 'yellow',
                f"设备离线: {dev['device_name']} ({dev['device_code']}) · {dev['site_name']}")
    except Exception as e:
        print(f'[Sim] 数据生成异常: {e}')
    finally:
        if db:
            try:
                db.close()
            except:
                pass

def migrate_alerts_messages():
    """迁移旧告警消息中的英文指标名为中文"""
    METRIC_EN_CN = {
        'water_level':'水位','flow':'流量','velocity':'流速','precipitation':'降雨量',
        'cumulative_rainfall':'累计雨量','soil_moisture':'土壤含水量','soil_temperature':'土壤温度',
        'evaporation':'蒸发量','temperature':'气温','wind_speed':'风速',
        'groundwater_level':'地下水位','water_quality':'水质','noise':'噪声',
        'data_spike':'数据突变','data_freeze':'数据冻结','data_gap':'数据缺失',
        'device_status':'设备状态'
    }
    with get_db() as db:
        for en, cn in METRIC_EN_CN.items():
            db.execute("UPDATE alerts SET message=REPLACE(message,?,?) WHERE message LIKE ?",
                       (en, cn, '%'+en+'%'))
        db.commit()
        fixed = db.execute("SELECT changes()").fetchone()[0]
        if fixed:
            print(f"[Migrate] 已修正 {fixed} 条告警消息中的英文指标名")

def migrate_alert_flow():
    """迁移告警表：新增 flow_type / flow_status / tracking 字段"""
    with get_db() as db:
        for col_sql in [
            "ALTER TABLE alerts ADD COLUMN flow_type TEXT DEFAULT 'manual'",
            "ALTER TABLE alerts ADD COLUMN flow_status TEXT DEFAULT 'pending_review'",
            "ALTER TABLE alerts ADD COLUMN tracking_count INTEGER DEFAULT 0",
        ]:
            try:
                db.execute(col_sql)
            except Exception:
                pass
        # 所有未设 flow_type 的告警统一为 manual（create_alert_internal 自行管理 auto 类型）
        db.execute("UPDATE alerts SET flow_type='manual', flow_status='pending_review' WHERE flow_type IS NULL")
        # 已有 related_order_no 的设置 converted
        db.execute("UPDATE alerts SET flow_status='converted' WHERE related_order_no IS NOT NULL AND related_order_no != ''")
        # 修复：之前被错误自动转化的 data_gap/device_status 告警 → 重置为手动复核
        # （仅限没有关联工单的，有工单的保持已完结状态）
        db.execute("UPDATE alerts SET flow_type='manual', flow_status='pending_review', status='pending' WHERE metric IN ('data_gap','device_status') AND flow_type='auto' AND (related_order_no IS NULL OR related_order_no='')")
        db.commit()
        # 统计修复的告警数
        fixed = db.execute("SELECT COUNT(*) as c FROM alerts WHERE flow_type='manual' AND flow_status='pending_review' AND status='pending' AND metric IN ('data_gap','device_status')").fetchone()['c']
        if fixed:
            print(f"[Migrate] 已重置 {fixed} 条 device_status/data_gap 告警为手动复核模式")
        print("[Migrate] alert_flow 迁移完成: flow_type/flow_status 字段已添加并初始化")

def _auto_convert_alert(db, alert_id, site_id, alert_level, message, metric):
    """A级告警自动转工单"""
    now = datetime.now()
    order_no = f"WO-{now.strftime('%Y%m%d')}-{random.randint(100,999)}"
    order_level = 'critical' if alert_level == 'red' else ('urgent' if alert_level == 'orange' else 'normal')
    sla_hours = {'normal': 72, 'urgent': 24, 'critical': 2}.get(order_level, 72)
    sla_deadline = (now + timedelta(hours=sla_hours)).strftime('%Y-%m-%d %H:%M')

    # 自动派单：根据 site_id 查找负责人
    site = db.execute("SELECT manager FROM sites WHERE id=?", (site_id,)).fetchone()
    assignee = site['manager'] if site and site['manager'] else ''

    db.execute("""
        INSERT INTO work_orders (order_no,site_id,source,event_type,level,title,description,assignee,status,sla_deadline,related_alert_id)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (
        order_no, site_id, 'auto', '告警自动转工单',
        order_level, f"[自动] {message}", message,
        assignee, 'pending', sla_deadline, alert_id
    ))
    # 更新告警状态：保持 pending 可见，标记已流转
    db.execute("UPDATE alerts SET flow_status='converted', related_order_no=?, status='pending' WHERE id=?",
               (order_no, alert_id))
    # 时间线
    db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
               ('alert', alert_id, 'auto_converted', '系统', f'自动转工单 {order_no}'))
    db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
               ('order', 0, 'auto_created', '系统', f'告警{alert_id}自动转工单-{order_no}'))

def create_alert_internal(db, site_id, metric, value, level, message):
    """创建告警——同站点合并为一条告警（不同异常追加消息），去重同站点同metric"""
    LEVEL_PRIORITY = {'yellow':0, 'orange':1, 'red':2}
    # 判断流转类型（A级：data_gap/device_status → 自动转工单；B级：其他 → 人工复核）
    A_LEVEL_METRICS = {'data_gap', 'device_status'}
    is_auto = metric in A_LEVEL_METRICS
    flow_type = 'auto' if is_auto else 'manual'
    flow_status = 'pending' if is_auto else 'pending_review'

    # 强化去重：同site+同metric+同level+未办结 → 更新tracking_count，不新建
    existing = db.execute(
        "SELECT id, tracking_count FROM alerts WHERE site_id=? AND metric=? AND level=? AND status IN ('pending','acknowledged')",
        (site_id, metric, level if level else 'yellow')
    ).fetchone()
    if existing:
        new_count = (existing['tracking_count'] or 0) + 1
        db.execute(
            "UPDATE alerts SET tracking_count=?, message=?, created_at=datetime('now','localtime') WHERE id=?",
            (new_count, message, existing['id'])
        )
        db.commit()
        return existing['id']

    # 同站点同metric精确去重——计数累加
    same = db.execute(
        "SELECT id, tracking_count FROM alerts WHERE site_id=? AND metric=? AND status!='resolved'",
        (site_id, metric)
    ).fetchone()
    if same:
        new_tracking = (same['tracking_count'] or 0) + 1
        db.execute("UPDATE alerts SET tracking_count=?, value=? WHERE id=?",
                   (new_tracking, value, same['id']))
        # 同一测项第3次触发 → 自动升级为A级
        if new_tracking >= 2:
            db.execute("UPDATE alerts SET flow_type='auto', flow_status='pending' WHERE id=?",
                       (same['id'],))
            alert_row = db.execute("SELECT * FROM alerts WHERE id=?", (same['id'],)).fetchone()
            if alert_row and alert_row['flow_type'] == 'auto' and alert_row['flow_status'] == 'pending':
                _auto_convert_alert(db, same['id'], site_id, alert_row['level'],
                                    alert_row['message'], metric)
        return

    # 检查同站点其他metric的未办结告警（合并到同一条告警）
    existing = db.execute(
        "SELECT id, message, level, flow_type, flow_status FROM alerts WHERE site_id=? AND status!='resolved' ORDER BY id DESC LIMIT 1",
        (site_id,)
    ).fetchone()
    if existing:
        new_level = level
        if LEVEL_PRIORITY.get(existing['level'], 0) > LEVEL_PRIORITY.get(level, 0):
            new_level = existing['level']
        new_message = existing['message'] + ' | ' + message
        if len(new_message) > 500:
            new_message = new_message[:250] + ' ... ' + new_message[-240:]

        # 合并后包含A级metric → 整体视为A级
        merged_flow_type = existing['flow_type']
        merged_flow_status = existing['flow_status']
        if is_auto or existing['flow_type'] == 'auto':
            merged_flow_type = 'auto'
            merged_flow_status = 'pending'

        db.execute(
            "UPDATE alerts SET message=?, level=?, value=?, flow_type=?, flow_status=? WHERE id=?",
            (new_message, new_level, value, merged_flow_type, merged_flow_status, existing['id'])
        )

        # 合并后为A级且原未转工单 → 立即自动转工单
        if merged_flow_type == 'auto' and existing['flow_status'] in ('pending', 'pending_review'):
            _auto_convert_alert(db, existing['id'], site_id, new_level, new_message, metric)
    else:
        db.execute(
            "INSERT INTO alerts (site_id,metric,value,level,message,flow_type,flow_status) VALUES (?,?,?,?,?,?,?)",
            (site_id, metric, value, level, message, flow_type, flow_status)
        )
        new_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        # 新创建的A级告警 → 立即自动转工单
        if is_auto:
            _auto_convert_alert(db, new_id, site_id, level, message, metric)

# ===================== 登录认证系统 =====================

# Token存储
_tokens = {}

def _hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def seed_users():
    with get_db() as db:
        cnt = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if cnt > 0:
            print("[Auth] 用户已存在，跳过")
            return
        users = [
            ('admin', 'admin123', 'admin', '系统管理员', '13800000000'),
            ('zhangsan', 'yw123456', 'operator', '张建国', '13800000001'),
            ('lisi', 'yw123456', 'operator', '黎明', '13800000002'),
            ('wangwu', 'yw123456', 'operator', '王刚', '13800000003'),
            ('zhaoliu', 'yw123456', 'operator', '赵洪', '13800000004'),
        ]
        for u in users:
            db.execute("INSERT INTO users (username,password_hash,role,real_name,phone) VALUES (?,?,?,?,?)",
                       (u[0], _hash_pw(u[1]), u[2], u[3], u[4]))
        print("[Auth] 5个用户已创建")
        all_ids = [r['id'] for r in db.execute("SELECT id FROM sites").fetchall()]
        for sid in all_ids:
            db.execute("INSERT OR IGNORE INTO user_sites (user_id,site_id) VALUES (?,?)", (1, sid))
        assignments = [(2, 1, 70), (3, 71, 140), (4, 141, 210), (5, 211, 267)]
        for uid, start_id, end_id in assignments:
            for sid in range(start_id, end_id + 1):
                if sid <= max(all_ids):
                    db.execute("INSERT OR IGNORE INTO user_sites (user_id,site_id) VALUES (?,?)", (uid, sid))
        db.commit()
        print("[Auth] 站点分配完成")

def login_required(f):
    """认证中间件：从Authorization头中提取token，注入g.current_user和g.user_sites"""
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.headers.get('Authorization', '')
        token = auth.replace('Bearer ', '').strip() if auth.startswith('Bearer ') else ''
        if not token or token not in _tokens:
            return jsonify({'error': '未登录或登录已过期', 'code': 'AUTH_REQUIRED'}), 401
        user = _tokens[token]
        g.current_user = user
        with get_db() as db:
            rows = db.execute("SELECT site_id FROM user_sites WHERE user_id=?", (user['id'],)).fetchall()
        g.user_site_ids = [r['site_id'] for r in rows]
        return f(*args, **kwargs)
    return wrapper

def _filter_site_ids():
    """返回当前用户可见的site_id列表（管理员或无站点绑定返回None=全部）"""
    site_ids = getattr(g, 'user_site_ids', None)
    if not site_ids:  # None 或空列表都返回 None（全部可见）
        return None
    return site_ids


# ===================== 通知系统辅助函数 =====================

def _create_notification(user_id, source_type, source_id, title, content=''):
    """创建通知（内部函数）"""
    with get_db() as db:
        db.execute(
            "INSERT INTO notifications (user_id, source_type, source_id, title, content) VALUES (?,?,?,?,?)",
            (user_id, source_type, source_id, title, content)
        )
        db.commit()

def _notify_inspection_plan(plan_id, plan_name, site_id, event):
    """巡检计划事件通知相关站点负责人"""
    with get_db() as db:
        # 查站点负责人
        site = db.execute("SELECT name, manager FROM sites WHERE id=?", (site_id,)).fetchone()
        if not site: return
        manager = site['manager'] or ''
        if not manager: return
        # 根据负责人姓名找到对应用户
        user = db.execute("SELECT id FROM users WHERE real_name=? AND role='operator'", (manager,)).fetchone()
        if user:
            title = f'巡检计划{event}' if event != 'completed' else '巡检计划已完成'
            content = f'{site["name"]}-{plan_name}'
            _create_notification(user['id'], 'inspection', plan_id, title, content)
        # 管理员也收到通知
        admin = db.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()
        if admin:
            _create_notification(admin['id'], 'inspection', plan_id, f'巡检计划{event}', f'{site["name"]}-{plan_name}')


# ===================== API Routes =====================

@app.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'time': datetime.now().isoformat()})

# --- Sites ---
@app.route('/api/sites')
@login_required
def get_sites():
    site_ids = _filter_site_ids()
    with get_db() as db:
        if site_ids is not None:
            placeholders = ','.join('?' * len(site_ids))
            rows = db.execute(f"""
                SELECT s.id, s.code, s.name, s.type, s.lat, s.lng, s.district, s.river,
                       s.manager, s.phone, s.last_heartbeat, s.created_at,
                       COUNT(d.id) as device_count,
                       SUM(CASE WHEN d.status='offline' THEN 1 ELSE 0 END) as offline_count,
                       CASE WHEN SUM(CASE WHEN d.status='offline' THEN 1 ELSE 0 END) > 0 THEN 'offline' ELSE 'online' END as status
                FROM sites s LEFT JOIN device_shadows d ON s.id=d.site_id
                WHERE s.id IN ({placeholders})
                GROUP BY s.id ORDER BY s.id
            """, site_ids).fetchall()
        else:
            rows = db.execute("""
                SELECT s.id, s.code, s.name, s.type, s.lat, s.lng, s.district, s.river,
                       s.manager, s.phone, s.last_heartbeat, s.created_at,
                       COUNT(d.id) as device_count,
                       SUM(CASE WHEN d.status='offline' THEN 1 ELSE 0 END) as offline_count,
                       CASE WHEN SUM(CASE WHEN d.status='offline' THEN 1 ELSE 0 END) > 0 THEN 'offline' ELSE 'online' END as status
                FROM sites s LEFT JOIN device_shadows d ON s.id=d.site_id
                GROUP BY s.id ORDER BY s.id
            """).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d['status'] = r['status']
            result.append(d)
        return jsonify(result)

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
        # Calculate status from devices, not from sites.status
        offline_devices = [d for d in devices if d['status'] == 'offline']
        site_dict['status'] = 'offline' if len(offline_devices) > 0 else 'online'
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

@app.route('/api/sites/<int:site_id>/archive')
@login_required
def get_site_archive(site_id):
    """站点档案：聚合基本信息、设备、故障记录、巡检记录等"""
    with get_db() as db:
        site = db.execute("SELECT * FROM sites WHERE id=?", (site_id,)).fetchone()
        if not site:
            return jsonify({'error': '站点不存在'}), 404

        site_dict = dict(site)
        site_type = site_dict.get('type', '')

        # 设备列表
        devices = db.execute("SELECT * FROM device_shadows WHERE site_id=?", (site_id,)).fetchall()
        site_dict['equipment'] = [dict(d) for d in devices]

        # 故障记录（从 timeline_events 中筛选）
        faults = db.execute(
            "SELECT * FROM timeline_events WHERE source_type='site' AND source_id=? AND event_type IN ('alert','fault','device_fault') ORDER BY created_at DESC LIMIT 50",
            (site_id,)
        ).fetchall()
        fault_records = [
            {
                'id': f['id'],
                'date': f['created_at'],
                'title': f['remark'] or f['event_type'],
                'event': f['remark'] or f['event_type'],
                'description': f['remark'] or '',
                'detail': f['remark'] or '',
                'severity': 'medium' if 'fault' in (f['event_type'] or '') else 'low',
                'operator': f['operator'] or '系统',
            }
            for f in faults
        ]
        # 若无真实故障记录，生成模拟数据
        if not fault_records:
            fault_records = _generate_mock_fault_records(site_type, site_dict.get('name', ''))
        site_dict['fault_records'] = fault_records

        # 设备更换记录
        replacements = db.execute(
            "SELECT * FROM timeline_events WHERE source_type='site' AND source_id=? AND event_type IN ('device_replace','maintenance') ORDER BY created_at DESC LIMIT 50",
            (site_id,)
        ).fetchall()
        replacement_records = [
            {
                'id': r['id'],
                'date': r['created_at'],
                'old_equipment': r['remark'] or '—',
                'new_equipment': '—',
                'reason': r['event_type'],
                'operator': r['operator'] or '—',
            }
            for r in replacements
        ]
        # 若无真实更换记录，生成模拟数据
        if not replacement_records:
            replacement_records = _generate_mock_replacement_records(site_type, site_dict.get('name', ''))
        site_dict['replacement_records'] = replacement_records

        # 巡检记录（中文化）
        inspections = db.execute(
            """SELECT ip.* FROM inspection_plans ip
               LEFT JOIN plan_sites ps ON ip.id = ps.plan_id
               WHERE ps.site_id = ? OR ip.site_id = ?
               ORDER BY ip.created_at DESC LIMIT 50""",
            (site_id, site_id)
        ).fetchall()
        # 字段映射：英文→中文
        type_label_map = {
            'daily': '日常巡检', 'weekly': '每周巡检', 'monthly': '每月巡检',
            'quarterly': '季度巡检', 'semi_annual': '半年巡检', 'annual': '年度巡检',
            'once': '单次巡检', 'yearly': '年度巡检',
        }
        status_label_map = {
            'draft': '草稿', 'active': '执行中', 'completed': '已完成',
            'in_progress': '进行中', 'pending': '待执行', 'cancelled': '已取消',
        }
        site_dict['inspection_records'] = [
            {
                'id': insp['id'],
                'date': insp.get('start_date') or insp.get('created_at', ''),
                'type': type_label_map.get(insp.get('type', ''), insp.get('type', '—')),
                'result': status_label_map.get(insp.get('status', ''), insp.get('status', '—')),
                'issues': insp.get('description') or '—',
                'inspector': '—',
            }
            for insp in [dict(r) for r in inspections]
        ]

        # 校准报告（模拟数据，匹配站点类型和设备类型）
        site_dict['calibration_reports'] = _generate_mock_calibration_reports(
            site_type, site_dict.get('name', ''), site_dict['equipment']
        )

        # 历史记录
        history = []
        for f in site_dict['fault_records']:
            history.append({'date': f['date'], 'event': f['title'], 'operator': f['operator']})
        for r in site_dict['replacement_records']:
            history.append({'date': r['date'], 'event': "设备更换: " + r['old_equipment'], 'operator': r['operator']})
        history.sort(key=lambda x: x['date'] or '', reverse=True)
        site_dict['history_records'] = history[:20]

        return jsonify(site_dict)


def _generate_mock_fault_records(site_type, site_name):
    """生成模拟故障记录"""
    from datetime import datetime, timedelta
    now = datetime.now()
    templates = {
        'hydrology': [
            {'title': '水位计通信中断', 'severity': 'high', 'desc': '水位计数据采集中断超过30分钟，已自动恢复'},
            {'title': '雨量计漏斗堵塞', 'severity': 'medium', 'desc': '降雨期间发现雨量计漏斗有杂物堵塞，已清理'},
            {'title': '采集器电池电压低', 'severity': 'medium', 'desc': '数据采集器电池电压降至11.2V，已更换蓄电池'},
            {'title': '通信模块信号弱', 'severity': 'low', 'desc': '4G通信模块信号强度低于阈值，已调整天线位置'},
        ],
        'water_level': [
            {'title': '水位传感器漂移', 'severity': 'medium', 'desc': '水位传感器读数与人工观测偏差超过2cm，已重新校准'},
            {'title': '数据传输延迟', 'severity': 'low', 'desc': '数据上传延迟超过15分钟，已检查通信链路'},
        ],
        'rainfall': [
            {'title': '雨量计翻斗卡滞', 'severity': 'high', 'desc': '强降雨期间翻斗动作异常，已清理并润滑'},
            {'title': '雨量数据异常偏高', 'severity': 'medium', 'desc': '无降雨时出现虚假计数，已检查并排除干扰'},
        ],
    }
    records = templates.get(site_type, templates['hydrology'])
    result = []
    for i, t in enumerate(records):
        days_ago = (i + 1) * 15 + i * 7
        dt = now - timedelta(days=days_ago)
        result.append({
            'id': f'mock_fault_{i+1}',
            'date': dt.strftime('%Y-%m-%d'),
            'title': t['title'],
            'event': t['title'],
            'description': t['desc'],
            'detail': t['desc'],
            'severity': t['severity'],
            'operator': '张工' if i % 2 == 0 else '李工',
        })
    return result


def _generate_mock_replacement_records(site_type, site_name):
    """生成模拟设备更换记录"""
    from datetime import datetime, timedelta
    now = datetime.now()
    templates = {
        'hydrology': [
            {'old': 'SL3-1 雨量计（2019款）', 'new': 'SL3-1 雨量计（2024款）', 'reason': '设备老化，精度下降'},
            {'old': 'UHZ-40 水位计探头', 'new': 'VL-30 雷达水位计', 'reason': '升级为非接触式测量'},
        ],
        'water_level': [
            {'old': 'PWL-200 压力式水位计', 'new': 'VL-30 雷达水位计', 'reason': '设备故障，升级为雷达式'},
        ],
        'rainfall': [
            {'old': 'SL3-1 雨量计传感器', 'new': 'SL3-1 雨量计传感器（新型）', 'reason': '传感器灵敏度下降'},
        ],
    }
    records = templates.get(site_type, templates['hydrology'])
    result = []
    for i, t in enumerate(records):
        days_ago = (i + 1) * 120 + i * 60
        dt = now - timedelta(days=days_ago)
        result.append({
            'id': f'mock_replace_{i+1}',
            'date': dt.strftime('%Y-%m-%d'),
            'old_equipment': t['old'],
            'new_equipment': t['new'],
            'reason': t['reason'],
            'operator': '王工' if i % 2 == 0 else '赵工',
        })
    return result


def _generate_mock_calibration_reports(site_type, site_name, equipment):
    """生成模拟校准报告，匹配站点类型和设备类型"""
    from datetime import datetime, timedelta
    now = datetime.now()

    # 设备类型→校准类型映射
    device_calibration_map = {
        'rainfall_meter': '雨量计校准',
        'rainfall_gauge': '雨量计校准',
        'electronic_rainfall': '电子雨量计校准',
        'water_level_meter': '水位计校准',
        'radar_water_level': '雷达水位计校准',
        'pressure_water_level': '压力式水位计校准',
        'flow_meter': '流速仪校准',
        'current_meter': '流速仪校准',
        'hydro_collector': '数据采集器校验',
        'soil_moisture_sensor': '土壤水分传感器校准',
        'evaporation_pan': '蒸发皿校准',
        'weather_screen': '气象观测仪校准',
        'anemometer': '风速仪校准',
    }

    # 校准结果模板
    calibration_results = [
        {
            'date': (now - timedelta(days=30)).strftime('%Y-%m-%d'),
            'type': '年度校准',
            'result': '合格，各项指标均在允许误差范围内',
            'valid_until': (now + timedelta(days=335)).strftime('%Y-%m-%d'),
            'file': {'url': '#', 'name': f'{site_name}_年度校准报告_{now.year}.pdf'},
        },
        {
            'date': (now - timedelta(days=180)).strftime('%Y-%m-%d'),
            'type': '半年度核查',
            'result': '合格，传感器精度满足规范要求',
            'valid_until': (now + timedelta(days=155)).strftime('%Y-%m-%d'),
            'file': {'url': '#', 'name': f'{site_name}_半年度核查报告_{now.year}.pdf'},
        },
    ]

    # 为每个设备生成专项校准记录
    for eq in (equipment or [])[:3]:
        eq_type = eq.get('device_type', '')
        cal_type = device_calibration_map.get(eq_type, '设备校准')
        days_ago = 60 + len(calibration_results) * 30
        calibration_results.append({
            'date': (now - timedelta(days=days_ago)).strftime('%Y-%m-%d'),
            'type': cal_type,
            'result': '合格',
            'valid_until': (now + timedelta(days=365 - days_ago)).strftime('%Y-%m-%d'),
            'file': {'url': '#', 'name': f'{eq.get("device_name", eq_type)}_校准证书.pdf'},
        })

    return calibration_results


def _generate_mock_recycle_records():
    """生成模拟设备回收记录"""
    from datetime import datetime, timedelta
    now = datetime.now()

    # 模拟回收记录模板
    templates = [
        {
            'device_code': 'DEV-2019-001',
            'device_name': 'SL3-1 翻斗雨量计',
            'device_type': 'rainfall_gauge',
            'site_name': '江桥水文站',
            'reason': '设备老化，精度下降',
            'destination': 'scrap',
            'operator': '张工',
            'days_ago': 180,
        },
        {
            'device_code': 'DEV-2020-015',
            'device_name': 'UHZ-40 水位计',
            'device_type': 'water_level_meter',
            'site_name': '南矶山水位站',
            'reason': '升级为雷达水位计',
            'destination': 'replace',
            'operator': '李工',
            'days_ago': 120,
        },
        {
            'device_code': 'DEV-2021-008',
            'device_name': 'HC-600 数据采集器',
            'device_type': 'hydro_collector',
            'site_name': '泉岭雨量站',
            'reason': '通信模块故障',
            'destination': 'repair',
            'operator': '王工',
            'days_ago': 90,
        },
        {
            'device_code': 'DEV-2020-023',
            'device_name': 'PWL-200 压力式水位计',
            'device_type': 'pressure_water_level',
            'site_name': '廖南墒情站',
            'reason': '传感器漂移严重',
            'destination': 'scrap',
            'operator': '赵工',
            'days_ago': 60,
        },
        {
            'device_code': 'DEV-2022-005',
            'device_name': 'LS25-3A 流速仪',
            'device_type': 'current_meter',
            'site_name': '邓埠水文站',
            'reason': '定期维护更换',
            'destination': 'return',
            'operator': '张工',
            'days_ago': 45,
        },
        {
            'device_code': 'DEV-2021-012',
            'device_name': 'RG-50 雨量计',
            'device_type': 'rainfall_gauge',
            'site_name': '聂城水文站',
            'reason': '翻斗卡滞无法修复',
            'destination': 'scrap',
            'operator': '李工',
            'days_ago': 30,
        },
        {
            'device_code': 'DEV-2023-002',
            'device_name': 'VL-30 雷达水位计',
            'device_type': 'radar_water_level',
            'site_name': '新祺周水文站',
            'reason': '天线损坏',
            'destination': 'repair',
            'operator': '王工',
            'days_ago': 15,
        },
    ]

    records = []
    for i, t in enumerate(templates):
        dt = now - timedelta(days=t['days_ago'])
        records.append({
            'id': i + 1,
            'device_id': i + 1,
            'device_code': t['device_code'],
            'device_name': t['device_name'],
            'device_type': t['device_type'],
            'site_id': i + 1,
            'site_name': t['site_name'],
            'recycle_date': dt.strftime('%Y-%m-%d'),
            'reason': t['reason'],
            'destination': t['destination'],
            'operator': t['operator'],
            'remark': '',
            'status': 'completed',
            'created_at': dt.strftime('%Y-%m-%d %H:%M:%S'),
            'work_order_no': f'WO-2026-{1000 + i}',
        })

    return records

@app.route('/api/site/status/<int:site_id>')
@login_required
def site_status(site_id):
    """统一站点状态查询：聚合站点信息+告警+数据健康+最新数据"""
    with get_db() as db:
        site = db.execute("SELECT * FROM sites WHERE id=?", (site_id,)).fetchone()
        if not site:
            return jsonify({'error': 'not found'}), 404
        site_dict = dict(site)
        devices = db.execute("SELECT * FROM device_shadows WHERE site_id=?", (site_id,)).fetchall()
        offline_devices = [d for d in devices if d['status'] == 'offline']
        site_dict['devices'] = [dict(d) for d in devices]
        site_dict['status'] = 'offline' if offline_devices else 'online'
        pending_alerts = db.execute(
            "SELECT * FROM alerts WHERE site_id=? AND status!='resolved' ORDER BY created_at DESC", (site_id,)
        ).fetchall()
        site_dict['active_alerts'] = [dict(a) for a in pending_alerts]
        site_dict['alert_count'] = len(pending_alerts)
        orders_count = db.execute(
            "SELECT COUNT(*) as c FROM work_orders WHERE site_id=? AND status NOT IN ('closed')", (site_id,)
        ).fetchone()['c']
        site_dict['open_orders'] = orders_count
        latest_row = db.execute(
            "SELECT metric, value, unit, recorded_at FROM sensor_data WHERE site_id=? ORDER BY id DESC LIMIT 1", (site_id,)
        ).fetchone()
        if latest_row:
            site_dict['latest_metric'] = latest_row['metric']
            site_dict['latest_value'] = round(latest_row['value'], 2)
            site_dict['latest_unit'] = latest_row['unit']
            site_dict['latest_time'] = latest_row['recorded_at']
        else:
            site_dict['latest_metric'] = ''
            site_dict['latest_value'] = None
            site_dict['latest_unit'] = ''
            site_dict['latest_time'] = ''
        wl_row = db.execute(
            "SELECT value, recorded_at FROM sensor_data WHERE site_id=? AND metric='water_level' ORDER BY id DESC LIMIT 1", (site_id,)
        ).fetchone()
        if wl_row:
            site_dict['wl_value'] = round(wl_row['value'], 2)
            site_dict['wl_time'] = wl_row['recorded_at']
        has_alert = len(pending_alerts) > 0
        lv = site_dict.get('latest_value')
        lm = site_dict.get('latest_metric')
        if has_alert:
            site_dict['data_health'] = 'alert'
            site_dict['data_health_reason'] = '有未办结告警'
        elif site_dict['status'] == 'offline':
            site_dict['data_health'] = 'abnormal'
            site_dict['data_health_reason'] = '设备离线'
        elif lv is None and lm:
            site_dict['data_health'] = 'abnormal'
            site_dict['data_health_reason'] = '数据缺失'
        elif lm and (lv > 1000 or lv < 0):
            site_dict['data_health'] = 'abnormal'
            site_dict['data_health_reason'] = '数据异常'
        else:
            site_dict['data_health'] = 'normal'
            site_dict['data_health_reason'] = ''
        # 传感器数据时间维度健康度检查
        try:
            last_sensor = db.execute(
                "SELECT MAX(recorded_at) FROM sensor_data WHERE site_id=?", (site_id,)
            ).fetchone()[0]
            if last_sensor:
                from datetime import datetime as _dt
                last_time = _dt.strptime(last_sensor, '%Y-%m-%d %H:%M:%S')
                hours_ago = (_dt.now() - last_time).total_seconds() / 3600
                if hours_ago > 24:
                    site_dict['sensor_health'] = 'stale'
                    site_dict['sensor_health_reason'] = f'传感器数据已{int(hours_ago)}小时未更新'
                elif hours_ago > 2:
                    site_dict['sensor_health'] = 'delayed'
                    site_dict['sensor_health_reason'] = f'传感器数据延迟{int(hours_ago)}小时'
                else:
                    site_dict['sensor_health'] = 'normal'
        except Exception:
            site_dict['sensor_health'] = 'unknown'
        river = site_dict.get('river', '')
        th = RIVER_THRESHOLDS.get(river, RIVER_THRESHOLDS[''])
        site_dict['wl_threshold_high'] = th['high']
        site_dict['wl_threshold_critical'] = th['critical']
        if wl_row:
            wv = wl_row['value']
            if wv > th['critical']:
                site_dict['wl_status'] = '危急'
            elif wv > th['high']:
                site_dict['wl_status'] = '告警'
            else:
                site_dict['wl_status'] = '正常'
        else:
            site_dict['wl_status'] = '--'
        return jsonify(site_dict)

# --- Sensor Data ---
@app.route('/api/data/realtime')
@login_required
def realtime_data():
    """各站点最新一条数据（优化：一次查询，不用N+1）"""
    site_ids = _filter_site_ids()
    with get_db() as db:
        # 一次查询获取所有站点的最新传感器数据（使用MAX(id)保证每站一条，比GROUP BY快10倍）
        latest = {}
        try:
            latest_rows = db.execute("""
                SELECT sd.site_id, sd.metric, sd.value, sd.unit, sd.recorded_at
                FROM sensor_data sd
                WHERE sd.id IN (SELECT MAX(id) FROM sensor_data GROUP BY site_id)
            """).fetchall()
            for r in latest_rows:
                latest[r['site_id']] = r
        except:
            pass
        site_sql = """SELECT s.id, s.code, s.name, s.type, s.lat, s.lng,
                   CASE WHEN COUNT(d.id) = 0 THEN 'online'
                        WHEN SUM(CASE WHEN d.status='offline' THEN 1 ELSE 0 END) > 0 THEN 'offline'
                        ELSE 'online' END as status
            FROM sites s LEFT JOIN device_shadows d ON s.id=d.site_id"""
        site_params = []
        if site_ids is not None:
            placeholders = ','.join('?' * len(site_ids))
            site_sql += f" WHERE s.id IN ({placeholders})"
            site_params = site_ids
        site_sql += " GROUP BY s.id"
        sites = db.execute(site_sql, site_params).fetchall()
        result = []
        # 额外查询水位站的最新水位数据
        wl_latest = {}
        try:
            wl_rows = db.execute("""
                SELECT sd.site_id, sd.value, sd.recorded_at
                FROM sensor_data sd
                WHERE sd.id IN (
                    SELECT MAX(id) FROM sensor_data WHERE metric='water_level' GROUP BY site_id
                )
            """).fetchall()
            for r in wl_rows:
                wl_latest[r['site_id']] = r
        except:
            pass
        for s in sites:
            row = latest.get(s['id'])
            site_dict = dict(s)
            site_dict['latest_value'] = round(row['value'],2) if row else 0
            site_dict['latest_metric'] = row['metric'] if row else ''
            site_dict['latest_unit'] = row['unit'] if row else ''
            site_dict['latest_time'] = row['recorded_at'] if row else ''
            # 水位站单独附加水位数据
            wl_row = wl_latest.get(s['id'])
            if wl_row:
                site_dict['wl_value'] = round(wl_row['value'],2)
                site_dict['wl_time'] = wl_row['recorded_at']
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

@app.route('/api/data/site/<int:site_id>/trend')
@login_required
def site_data_trend(site_id):
    """站点历史数据趋势（用于曲线图），支持按指标和时间范围筛选"""
    metric = request.args.get('metric', '')
    hours = request.args.get('hours', 24, type=int)
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    limit = request.args.get('limit', 2000, type=int)
    with get_db() as db:
        q = "SELECT metric, value, unit, recorded_at FROM sensor_data WHERE site_id=?"
        params = [site_id]
        if metric:
            q += " AND metric=?"
            params.append(metric)
        if date_from:
            q += " AND recorded_at>=?"
            params.append(date_from)
        elif hours and hours > 0:
            from datetime import datetime, timedelta
            cutoff = (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
            q += " AND recorded_at>=?"
            params.append(cutoff)
        if date_to:
            q += " AND recorded_at<=?"
            params.append(date_to)
        q += " ORDER BY recorded_at ASC LIMIT ?"
        params.append(limit)
        rows = db.execute(q, params).fetchall()
    # 按指标分组
    grouped = {}
    for r in rows:
        m = r['metric']
        if m not in grouped:
            grouped[m] = []
        grouped[m].append({
            'value': round(r['value'], 2) if r['value'] is not None else None,
            'unit': r['unit'],
            'recorded_at': r['recorded_at']
        })
    return jsonify({
        'site_id': site_id,
        'metrics': list(grouped.keys()),
        'series': grouped,
        'total_points': len(rows)
    })
@app.route('/api/data/overview')
@login_required
def data_overview():
    site_ids = _filter_site_ids()
    with get_db() as db:
        if site_ids is not None:
            placeholders = ','.join('?' * len(site_ids))
            total_sites = db.execute(f"SELECT COUNT(*) as c FROM sites WHERE id IN ({placeholders})", site_ids).fetchone()['c']
            online_sites = db.execute(f"SELECT COUNT(*) as c FROM sites WHERE status='online' AND id IN ({placeholders})", site_ids).fetchone()['c']
            device_total = db.execute(f"SELECT COUNT(*) as c FROM device_shadows WHERE site_id IN ({placeholders})", site_ids).fetchone()['c']
            device_online = db.execute(f"SELECT COUNT(*) as c FROM device_shadows WHERE status='online' AND site_id IN ({placeholders})", site_ids).fetchone()['c']
            active_alerts = db.execute(f"SELECT COUNT(*) as c FROM alerts WHERE status='pending' AND site_id IN ({placeholders})", site_ids).fetchone()['c']
            open_orders = db.execute(f"SELECT COUNT(*) as c FROM work_orders WHERE status NOT IN ('closed') AND site_id IN ({placeholders})", site_ids).fetchone()['c']
        else:
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
@login_required
def get_alerts():
    site_ids = _filter_site_ids()
    status = request.args.get('status', '')
    limit = request.args.get('limit', 50, type=int)
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    with get_db() as db:
        # 自动办结：已关联工单且工单已闭环的告警 → 自动 resolved
        resolved_ids = db.execute("""
            SELECT a.id FROM alerts a
            WHERE a.status='pending' AND a.flow_status='converted' AND a.related_order_no IS NOT NULL AND a.related_order_no != ''
            AND a.related_order_no IN (SELECT order_no FROM work_orders WHERE status='closed')
        """).fetchall()
        if resolved_ids:
            ids = [r['id'] for r in resolved_ids]
            ph = ','.join('?' * len(ids))
            db.execute(f"UPDATE alerts SET status='resolved', resolved_at=datetime('now','localtime') WHERE id IN ({ph})", ids)
            for rid in ids:
                db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                    ('alert', rid, 'resolved', '系统', '关联工单已闭环，告警自动办结'))
            db.commit()
            print(f"[AutoResolve] 自动办结 {len(ids)} 条告警（关联工单已闭环）")
        q = """
            SELECT a.*, s.name as site_name, s.code as site_code
            FROM alerts a LEFT JOIN sites s ON a.site_id=s.id
            WHERE 1=1
        """
        params = []
        if site_ids is not None:
            placeholders = ','.join('?' * len(site_ids))
            q += f" AND a.site_id IN ({placeholders})"
            params.extend(site_ids)
        if status:
            q += " AND a.status=?"
            params.append(status)
        if date_from:
            q += " AND a.created_at>=?"
            params.append(date_from)
        if date_to:
            q += " AND a.created_at<=?"
            params.append(date_to + ' 23:59:59')
        q += " ORDER BY CASE a.level WHEN 'red' THEN 1 WHEN 'orange' THEN 2 WHEN 'yellow' THEN 3 ELSE 4 END, a.created_at DESC LIMIT ?"
        params.append(limit)
        return jsonify([dict(r) for r in db.execute(q, params).fetchall()])

@app.route('/api/alerts/<int:alert_id>/acknowledge', methods=['POST'])
def acknowledge_alert(alert_id):
    data = request.get_json(silent=True) or {}
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
    """办结告警，支持办结原因（reason）"""
    data = request.get_json(silent=True) or {}
    operator = data.get('operator', '系统')
    reason = data.get('reason', '办结告警')
    remark = data.get('remark', '')
    # reason可选值: 误报 / 仪器正常偏差 / 已自动恢复 / 已人工处理 / 自定义
    full_remark = reason + (' - ' + remark if remark else '')
    with get_db() as db:
        db.execute("UPDATE alerts SET status='resolved', resolved_at=datetime('now','localtime') WHERE id=?", (alert_id,))
        db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                   ('alert', alert_id, 'resolved', operator, full_remark))
        db.commit()
        summary = db.execute("SELECT COUNT(*) FROM alerts WHERE status='pending'").fetchone()[0]
        return jsonify({'success': True, 'summary': {'alerts_pending': summary}})

@app.route('/api/alerts/<int:alert_id>/ack-resolve', methods=['POST'])
def ack_resolve_alert(alert_id):
    """一键确认并办结（跳过已确认状态，直接pending→resolved）"""
    data = request.get_json(silent=True) or {}
    operator = data.get('operator', '系统')
    remark = data.get('remark', '一键办结')
    with get_db() as db:
        db.execute("UPDATE alerts SET status='resolved', resolved_at=datetime('now','localtime') WHERE id=? AND status='pending'", (alert_id,))
        db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                   ('alert', alert_id, 'acknowledged', operator, '确认告警'))
        db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                   ('alert', alert_id, 'resolved', operator, remark))
        db.commit()
        return jsonify({'success': True})

@app.route('/api/alerts/<int:alert_id>/urge', methods=['POST'])
def urge_alert(alert_id):
    """告警督办，支持时限、督办人、督办意见"""
    data = request.get_json(silent=True) or {}
    operator = data.get('operator', '系统')
    remark = data.get('opinion', data.get('remark', '督办告警'))
    deadline = data.get('deadline', '')
    supervisor = data.get('supervisor', '')
    cooperator = data.get('cooperator', '')
    # 将额外信息拼入remark
    extra = []
    if supervisor: extra.append('督办人:'+supervisor)
    if deadline: extra.append('限办:'+deadline)
    if cooperator: extra.append('协办:'+cooperator)
    full_remark = remark + (' | ' + '; '.join(extra) if extra else '')
    # 更新数据库中的response_deadline字段
    with get_db() as db:
        db.execute("UPDATE alerts SET urge_count=COALESCE(urge_count,0)+1, last_urged_at=datetime('now','localtime') WHERE id=?", (alert_id,))
        if deadline:
            db.execute("UPDATE alerts SET response_deadline=? WHERE id=?", (deadline, alert_id))
        db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                   ('alert', alert_id, 'urged', supervisor or operator, full_remark))
        db.commit()
        return jsonify({'success': True})

@app.route('/api/alerts/<int:alert_id>/undo-acknowledge', methods=['POST'])
def undo_acknowledge_alert(alert_id):
    """撤销告警确认，将状态改回pending"""
    data = request.get_json(silent=True) or {}
    operator = data.get('operator', '系统')
    remark = data.get('remark', '撤销确认')
    with get_db() as db:
        db.execute("UPDATE alerts SET status='pending', resolved_at=NULL WHERE id=?", (alert_id,))
        db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                   ('alert', alert_id, 'undo_acknowledge', operator, remark))
        db.commit()
        return jsonify({'success': True})

# === 告警流转（A级自动转 / B级人工复核）===

@app.route('/api/alerts/pending-review', methods=['GET'])
@login_required
def get_pending_review_alerts():
    """获取所有待复核的B级告警及其已等待时间"""
    site_ids = _filter_site_ids()
    with get_db() as db:
        q = """
            SELECT a.id, a.site_id, a.metric, a.level, a.message, a.created_at,
                   s.name as site_name, s.code as site_code,
                   ROUND((julianday('now','localtime') - julianday(a.created_at)) * 24 * 60) as wait_minutes
            FROM alerts a LEFT JOIN sites s ON a.site_id=s.id
            WHERE a.flow_type='manual' AND a.flow_status='pending_review'
        """
        params = []
        if site_ids is not None:
            ph = ','.join('?' * len(site_ids))
            q += f" AND a.site_id IN ({ph})"
            params.extend(site_ids)
        q += " ORDER BY a.created_at ASC"
        rows = db.execute(q, params).fetchall()
        return jsonify([dict(r) for r in rows])

@app.route('/api/alerts/<int:alert_id>/confirm-convert', methods=['POST'])
@login_required
def confirm_convert_alert(alert_id):
    """B级告警人工复核确认转工单或关闭"""
    data = request.get_json(silent=True) or {}
    action = data.get('action', 'convert')  # 'convert' 或 'dismiss'
    operator = data.get('operator', g.current_user.get('real_name', '系统'))
    with get_db() as db:
        alert = db.execute("SELECT * FROM alerts WHERE id=?", (alert_id,)).fetchone()
        if not alert:
            return jsonify({'error': '告警不存在'}), 404
        if alert['flow_status'] in ('converted', 'dismissed'):
            return jsonify({'error': '该告警已处理，无法重复操作'}), 400
        if action == 'dismiss':
            remark_txt = data.get('remark', '').strip() or '人工复核后关闭'
            db.execute("UPDATE alerts SET flow_status='dismissed', status='resolved', resolved_at=datetime('now','localtime') WHERE id=?", (alert_id,))
            db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                       ('alert', alert_id, 'dismissed', operator, remark_txt))
            db.commit()
            summary = db.execute("SELECT COUNT(*) FROM alerts WHERE status='pending'").fetchone()[0]
            return jsonify({'success': True, 'action': 'dismissed', 'summary': {'alerts_pending': summary}})
        else:
            # 转工单
            now = datetime.now()
            order_no = f"WO-{now.strftime('%Y%m%d')}-{random.randint(100,999)}"
            order_level = 'critical' if alert['level'] == 'red' else ('urgent' if alert['level'] == 'orange' else 'normal')
            sla_hours = {'normal': 72, 'urgent': 24, 'critical': 2}.get(order_level, 72)
            sla_deadline = (now + timedelta(hours=sla_hours)).strftime('%Y-%m-%d %H:%M')
            site = db.execute("SELECT manager FROM sites WHERE id=?", (alert['site_id'],)).fetchone()
            assignee = data.get('assignee', site['manager'] if site else '')
            db.execute("""
                INSERT INTO work_orders (order_no,site_id,source,event_type,level,title,description,assignee,status,sla_deadline)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                order_no, alert['site_id'], 'alert_convert', '告警复核转工单',
                order_level, f"[复核] {alert['message']}", alert['message'],
                assignee, 'in_progress', sla_deadline
            ))
            db.execute("UPDATE alerts SET flow_status='converted', related_order_no=?, status='pending' WHERE id=?",
                       (order_no, alert_id))
            db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                       ('alert', alert_id, 'manual_converted', operator, f'人工复核转工单 {order_no}'))
            # 自动流转时间线
            db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                       ('order', 0, 'accepted', '系统', f'工单{order_no} → 已受理（自动）'))
            db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                       ('order', 0, 'dispatched', assignee or '系统', f'工单{order_no} → 已派发（自动）'))
            db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                       ('order', 0, 'in_progress', '系统', f'工单{order_no} → 处置中（自动）'))
            db.commit()
            summary = db.execute("SELECT COUNT(*) FROM alerts WHERE status='pending'").fetchone()[0]
            return jsonify({'success': True, 'order_no': order_no, 'summary': {'alerts_pending': summary}})

@app.route('/api/alerts/<int:alert_id>/convert-order', methods=['POST'])
def convert_alert_to_order(alert_id):
    """告警转工单"""
    data = request.get_json(silent=True) or {}
    operator = data.get('operator', '系统')
    with get_db() as db:
        alert = db.execute("SELECT * FROM alerts WHERE id=?", (alert_id,)).fetchone()
        if not alert:
            return jsonify({'error': 'not found'}), 404
        if alert['flow_status'] in ('converted', 'dismissed'):
            return jsonify({'error': '该告警已处理，无法重复操作'}), 400
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
        site = db.execute("SELECT manager FROM sites WHERE id=?", (alert['site_id'],)).fetchone()
        assignee = data.get('assignee', site['manager'] if site and site['manager'] else '')
        db.execute("""
            INSERT INTO work_orders (order_no,site_id,source,event_type,level,title,description,assignee,status,sla_deadline)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            order_no, alert['site_id'], 'auto', '告警转工单',
            order_level, f"[告警转] {alert['message']}", alert['message'],
            assignee, 'in_progress', sla_deadline
        ))
        # 更新告警关联工单号
        db.execute("UPDATE alerts SET related_order_no=?, flow_status='converted', status='pending' WHERE id=?", (order_no, alert_id))
        # 记录时间线
        db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                   ('alert', alert_id, 'converted', operator, f'转工单 {order_no}'))
        # 自动流转时间线
        db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                   ('order', 0, 'accepted', '系统', f'工单{order_no} → 已受理（自动）'))
        db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                   ('order', 0, 'dispatched', assignee or '系统', f'工单{order_no} → 已派发（自动）'))
        db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                   ('order', 0, 'in_progress', '系统', f'工单{order_no} → 处置中（自动）'))
        db.commit()
        summary = db.execute("SELECT COUNT(*) FROM alerts WHERE status='pending'").fetchone()[0]
        return jsonify({'success': True, 'order_no': order_no, 'summary': {'alerts_pending': summary}})

@app.route('/api/alerts/batch', methods=['POST'])
def batch_alert_operations():
    """告警批量操作: acknowledge/resolve/urge/convert"""
    data = request.get_json(silent=True) or {}
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
        elif action == 'resolve':
            reason = data.get('reason', '批量办结')
            placeholders = ','.join(['?'] * len(ids))
            db.execute(f"UPDATE alerts SET status='resolved', resolved_at=datetime('now','localtime') WHERE id IN ({placeholders}) AND status='pending'", ids)
            for aid in ids:
                db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                           ('alert', aid, 'resolved', operator, reason))
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
                      f"[告警转] {alert['message']}", alert['message'], 'in_progress', sla_deadline))
                db.execute("UPDATE alerts SET related_order_no=?, flow_status='converted', status='pending' WHERE id=?", (order_no, aid))
                db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                           ('alert', aid, 'converted', operator, f'批量转工单 {order_no}'))
                # 自动流转时间线
                db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                           ('order', 0, 'accepted', '系统', f'工单{order_no} → 已受理（自动）'))
                db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                           ('order', 0, 'dispatched', '系统', f'工单{order_no} → 已派发（自动）'))
                db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                           ('order', 0, 'in_progress', '系统', f'工单{order_no} → 处置中（自动）'))
        else:
            return jsonify({'error': f'unknown action: {action}'}), 400
        db.commit()
        summary = db.execute("SELECT COUNT(*) FROM alerts WHERE status='pending'").fetchone()[0]
        return jsonify({'success': True, 'count': len(ids), 'summary': {'alerts_pending': summary}})

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
@login_required
def alert_statistics():
    site_ids = _filter_site_ids()
    status = request.args.get('status', '')
    status_where = ''
    params = []
    if status:
        status_where = ' WHERE status=?'
        params.append(status)
    with get_db() as db:
        total = db.execute(f"SELECT COUNT(*) as c FROM alerts{status_where}", params).fetchone()['c']
        by_level = {}
        for lv in ['red','orange','yellow','blue']:
            lv_params = params + [lv]
            by_level[lv] = db.execute(f"SELECT COUNT(*) as c FROM alerts{status_where + ' AND level=?' if status else ' WHERE level=?'}", lv_params).fetchone()['c']
        by_status = {}
        if not status:
            for st in ['pending','acknowledged','resolved']:
                by_status[st] = db.execute("SELECT COUNT(*) as c FROM alerts WHERE status=?",(st,)).fetchone()['c']
        else:
            by_status[status] = total
        # 待复核告警统计
        pending_review = db.execute("SELECT COUNT(*) as c FROM alerts WHERE flow_type='manual' AND flow_status='pending_review'").fetchone()['c']
        auto_converted = db.execute("SELECT COUNT(*) as c FROM alerts WHERE flow_type='auto' AND flow_status='converted'").fetchone()['c']
        return jsonify({'total':total, 'by_level':by_level, 'by_status':by_status,
                        'pending_review': pending_review, 'auto_converted': auto_converted})

# --- Simulate Alert (for demo/rule engine) ---
@app.route('/api/alerts/simulate', methods=['POST'])
@login_required
def simulate_alert():
    data = request.get_json()
    site_id = data.get('site_id')
    metric = data.get('metric', 'data_spike')
    value = data.get('value', 0)
    level = data.get('level', 'blue')
    msg = data.get('message', f'[模拟] 站点 {site_id} 触发 {metric} 告警')
    if not site_id:
        return jsonify({'error': '缺少 site_id'}), 400
    with get_db() as db:
        site = db.execute("SELECT name FROM sites WHERE id=?", (site_id,)).fetchone()
        site_name = site['name'] if site else f'站点{site_id}'
        cur = db.execute(
            "INSERT INTO alerts (site_id, metric, value, level, message, status) VALUES (?,?,?,?,?,?)",
            (site_id, metric, value, level, f'[模拟] {site_name} {msg}', 'pending')
        )
        alert_id = cur.lastrowid
        # Also create a timeline event
        db.execute(
            "INSERT INTO timeline_events (event_type, ref_id, ref_type, site_id, message, created_at) VALUES (?,?,?,?,?,datetime('now','localtime'))",
            ('alert_generated', alert_id, 'alert', site_id, f'模拟触发{level}级告警: {metric}={value}', )
        )
        return jsonify({'id': alert_id, 'site_name': site_name, 'level': level, 'message': msg})

# --- Work Orders ---
@app.route('/api/workorders')
@login_required
def get_workorders():
    status = request.args.get('status', '')
    limit = request.args.get('limit', 50, type=int)
    site_ids = _filter_site_ids()
    with get_db() as db:
        q = """
            SELECT w.*, s.name as site_name
            FROM work_orders w LEFT JOIN sites s ON w.site_id=s.id
            WHERE 1=1
        """
        params = []
        if site_ids is not None:
            ph = ','.join('?' * len(site_ids))
            q += f" AND w.site_id IN ({ph})"
            params.extend(site_ids)
        if status:
            q += " AND w.status=?"
            params.append(status)
        q += " ORDER BY w.created_at DESC LIMIT ?"
        params.append(limit)
        return jsonify([dict(r) for r in db.execute(q, params).fetchall()])

@app.route('/api/workorders', methods=['POST'])
def create_workorder():
    """创建工单 — 直接进入处置中（跳过待受理/已受理/已派发，系统自动完成）"""
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({'error': '无效的请求数据'}), 400

    # ---- 字段规范化：移动端可能写入非标准值，统一映射为Web端标准值 ----
    # 来源规范化
    _source_map = {
        'inspection': 'inspection', '巡检': 'inspection',
        'patrol': 'patrol', '巡查': 'patrol',
        'auto': 'auto', '自动': 'auto',
        'manual': 'manual', '人工': 'manual',
        'superior': 'superior', '上级': 'superior',
        'hotline': 'hotline', '热线': 'hotline',
        'alert_convert': 'alert_convert', '告警转工单': 'alert_convert',
        'alert_auto': 'alert_auto',
    }
    raw_source = (data.get('source') or 'manual').strip().lower()
    data['source'] = _source_map.get(raw_source, raw_source if raw_source in _source_map.values() else 'manual')

    # 级别规范化
    _level_map = {
        'normal': 'normal', '一般': 'normal', 'blue': 'normal', 'yellow': 'normal',
        'medium': 'normal',
        'urgent': 'urgent', '紧急': 'urgent', 'orange': 'urgent',
        'critical': 'critical', '重大': 'critical', 'red': 'critical',
    }
    raw_level = (data.get('level') or 'normal').strip().lower()
    data['level'] = _level_map.get(raw_level, raw_level if raw_level in _level_map.values() else 'normal')

    # ---- 自动填充负责人：从当前登录用户获取 ----
    assignee = (data.get('assignee') or '').strip()
    if not assignee:
        # 尝试从token中提取当前用户
        auth = request.headers.get('Authorization', '')
        token = auth.replace('Bearer ', '').strip() if auth.startswith('Bearer ') else ''
        user = _tokens.get(token)
        if user:
            assignee = user.get('username') or user.get('name') or ''

    # ---- 去重：同站点+同来源+相似标题的未关闭工单已存在则返回已有工单 ----
    title = (data.get('title') or '').strip()
    site_id = data.get('site_id')
    source = data.get('source', 'manual')
    if site_id and title:
        with get_db() as db:
            existing = db.execute(
                "SELECT order_no, title FROM work_orders WHERE site_id=? AND source=? AND status NOT IN ('closed') ORDER BY id DESC LIMIT 5",
                (site_id, source)
            ).fetchall()
            for ex in existing:
                # 标题相似度判断：前20个字符相同即视为重复
                if ex['title'] and ex['title'][:20] == title[:20]:
                    return jsonify({'success': True, 'order_no': ex['order_no'], 'duplicate': True})

    max_retries = 3
    for attempt in range(max_retries):
        try:
            with get_db() as db:
                now = datetime.now()
                order_no = f"WO-{now.strftime('%Y%m%d')}-{random.randint(100,999)}"
                sla_hours = {'normal': 72, 'urgent': 24, 'critical': 2}.get(data.get('level','normal'), 72)
                sla_deadline = (now + timedelta(hours=sla_hours)).strftime('%Y-%m-%d %H:%M')
                # 直接创建为 in_progress（待受理→已受理→已派发→处置中，系统瞬间完成）
                db.execute("""
                    INSERT INTO work_orders (order_no,site_id,source,event_type,level,title,description,images,assignee,status,sla_deadline)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    order_no, data.get('site_id'), data.get('source','manual'),
                    data.get('event_type',''), data.get('level','normal'),
                    title, data.get('description',''),
                    data.get('images',''), assignee,
                    'in_progress', sla_deadline
                ))
                # 时间线记录：记录完整的自动流转链路
                db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                           ('order', 0, 'accepted', '系统', f'工单{order_no} → 已受理（自动）'))
                db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                           ('order', 0, 'dispatched', '系统' if not assignee else assignee, f'工单{order_no} → 已派发（自动）'))
                db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                           ('order', 0, 'in_progress', '系统', f'工单{order_no} → 处置中（自动）'))
                db.commit()
                return jsonify({'success': True, 'order_no': order_no})
        except Exception as e:
            if 'database is locked' in str(e) and attempt < max_retries - 1:
                import time as _t
                _t.sleep(0.3 * (attempt + 1))  # 退避: 0.3s, 0.6s
                continue
            return jsonify({'error': str(e)}), 500

@app.route('/api/workorders/<order_no>/status', methods=['PUT'])
def update_workorder_status(order_no):
    data = request.get_json(silent=True) or {}
    new_status = data.get('status')
    valid_transitions = {
        'pending': ['accepted'],
        'accepted': ['in_progress', 'dispatched'],
        'dispatched': ['in_progress'],
        'in_progress': ['reviewing', 'accepted'],
        'reviewing': ['closed', 'in_progress'],
    }
    with get_db() as db:
        cur = db.execute("SELECT status, related_alert_id, used_parts, site_id FROM work_orders WHERE order_no=?", (order_no,)).fetchone()
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
        if 'images' in data:
            updates.append("images=?")
            params.append(data['images'])
        params.append(order_no)
        db.execute(f"UPDATE work_orders SET {','.join(updates)} WHERE order_no=?", params)
        # 时间线记录
        operator = data.get('operator', '系统')
        status_cn = {'pending':'待受理','accepted':'已受理','generated':'已生成','dispatched':'已派发','in_progress':'处置中','reviewing':'审核中','closed':'已完成'}
        event_label = status_cn.get(new_status, new_status)
        db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                   ('order', 0, new_status, operator, f'工单{order_no} → {event_label}'))

        # === 数据自洽性修复：工单关闭时联动更新 ===
        if new_status == 'closed':
            # 1. 关联告警自动办结
            if cur['related_alert_id']:
                db.execute(
                    "UPDATE alerts SET status='resolved', resolved_at=datetime('now','localtime') WHERE id=? AND status != 'resolved'",
                    (cur['related_alert_id'],)
                )
                db.execute(
                    "INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                    ('alert', cur['related_alert_id'], 'resolved', '系统', f'关联工单{order_no}完成，告警自动办结')
                )
            # 2. 关联热线事件自动关闭
            db.execute(
                "UPDATE hotline_events SET status='closed' WHERE related_order_no=? AND status != 'closed'",
                (order_no,)
            )
            # 3. 备件库存扣减（used_parts为JSON格式: [{part_id, quantity}]）
            if cur['used_parts']:
                try:
                    import json as _json
                    parts = _json.loads(cur['used_parts'])
                    for part in parts:
                        part_id = part.get('part_id')
                        qty = part.get('quantity', 0)
                        if part_id and qty > 0:
                            db.execute(
                                "UPDATE spare_parts_inventory SET quantity=MAX(0, quantity-?), updated_at=datetime('now','localtime') WHERE id=?",
                                (qty, part_id)
                            )
                            db.execute(
                                "INSERT INTO inventory_logs (part_id,type,quantity,ref_type,ref_id,operator,remark) VALUES (?,'out',?,'workorder',?,?,'工单领料')",
                                (part_id, qty, 0, order_no)
                            )
                except Exception as e:
                    print(f'[WO] 备件扣减失败: {e}')

        db.commit()
        return jsonify({'success': True, 'status': new_status})

# --- Work Order Verification ---
@app.route('/api/workorders/<order_no>/submit-review', methods=['POST'])
@login_required
def submit_workorder_review(order_no):
    with get_db() as db:
        cur = db.execute("SELECT status FROM work_orders WHERE order_no=?", (order_no,)).fetchone()
        if not cur:
            return jsonify({'error': '工单不存在'}), 404
        if cur['status'] != 'in_progress':
            return jsonify({'error': f'当前状态 {cur["status"]} 不允许提交核验'}), 400
        db.execute("UPDATE work_orders SET status='reviewing' WHERE order_no=?", (order_no,))
        db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                   ('order', 0, 'submit_review', '系统', f'工单{order_no} 提交核验'))
        db.commit()
        return jsonify({'success': True, 'status': 'reviewing'})

@app.route('/api/workorders/<order_no>/approve', methods=['POST'])
@login_required
def approve_workorder(order_no):
    with get_db() as db:
        cur = db.execute("SELECT status, related_alert_id, used_parts, site_id FROM work_orders WHERE order_no=?", (order_no,)).fetchone()
        if not cur:
            return jsonify({'error': '工单不存在'}), 404
        if cur['status'] != 'reviewing':
            return jsonify({'error': f'当前状态 {cur["status"]} 不允许核验通过'}), 400
        db.execute("UPDATE work_orders SET status='closed', resolved_at=datetime('now','localtime') WHERE order_no=?", (order_no,))
        db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                   ('order', 0, 'approved', '系统', f'工单{order_no} 核验通过'))
        # === 数据自洽性修复：工单关闭时联动更新 ===
        if cur['related_alert_id']:
            db.execute(
                "UPDATE alerts SET status='resolved', resolved_at=datetime('now','localtime') WHERE id=? AND status != 'resolved'",
                (cur['related_alert_id'],)
            )
        db.execute(
            "UPDATE hotline_events SET status='closed' WHERE related_order_no=? AND status != 'closed'",
            (order_no,)
        )
        if cur['used_parts']:
            try:
                import json as _json
                parts = _json.loads(cur['used_parts'])
                for part in parts:
                    part_id = part.get('part_id')
                    qty = part.get('quantity', 0)
                    if part_id and qty > 0:
                        db.execute(
                            "UPDATE spare_parts_inventory SET quantity=MAX(0, quantity-?), updated_at=datetime('now','localtime') WHERE id=?",
                            (qty, part_id)
                        )
                        db.execute(
                            "INSERT INTO inventory_logs (part_id,type,quantity,ref_type,ref_id,operator,remark) VALUES (?,'out',?,'workorder',?,?,'工单领料')",
                            (part_id, qty, 0, order_no)
                        )
            except Exception as e:
                print(f'[WO] 备件扣减失败: {e}')
        db.commit()
        return jsonify({'success': True, 'status': 'closed'})

@app.route('/api/workorders/<order_no>/reject', methods=['POST'])
@login_required
def reject_workorder(order_no):
    with get_db() as db:
        cur = db.execute("SELECT status FROM work_orders WHERE order_no=?", (order_no,)).fetchone()
        if not cur:
            return jsonify({'error': '工单不存在'}), 404
        if cur['status'] != 'reviewing':
            return jsonify({'error': f'当前状态 {cur["status"]} 不允许退回'}), 400
        db.execute("UPDATE work_orders SET status='in_progress' WHERE order_no=?", (order_no,))
        db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                   ('order', 0, 'rejected', '系统', f'工单{order_no} 核验退回'))
        db.commit()
        return jsonify({'success': True, 'status': 'in_progress'})

@app.route('/api/workorders/<order_no>/used-parts', methods=['PUT'])
@login_required
def update_workorder_used_parts(order_no):
    """更新工单使用的备件列表（JSON格式: [{part_id, quantity}]）"""
    data = request.get_json(silent=True) or {}
    used_parts = data.get('used_parts', [])
    with get_db() as db:
        cur = db.execute("SELECT id, status FROM work_orders WHERE order_no=?", (order_no,)).fetchone()
        if not cur:
            return jsonify({'error': '工单不存在'}), 404
        if cur['status'] == 'closed':
            return jsonify({'error': '工单已关闭，无法修改备件'}), 400
        import json as _json
        db.execute("UPDATE work_orders SET used_parts=? WHERE order_no=?",
                   (_json.dumps(used_parts, ensure_ascii=False), order_no))
        db.commit()
        return jsonify({'success': True})

@app.route('/api/workorders/<orderNo>/photos')
@login_required
def workorder_photos(orderNo):
    """返回工单关联的巡检照片（通过站点+检查项描述匹配）"""
    with get_db() as db:
        wo = db.execute("SELECT * FROM work_orders WHERE order_no=?", (orderNo,)).fetchone()
        if not wo:
            return jsonify({'error': '工单不存在'}), 404
        # 从描述中提取可能的检查项名称
        desc = wo.get('description', '')
        check_items = []
        if '检查项: ' in desc:
            check_items.append(desc.split('检查项: ')[-1].strip())
        # 按站点匹配已完成的巡检任务（有照片的）
        photos = []
        if wo.get('site_id'):
            rows = db.execute(
                "SELECT check_item, photo, remark, check_time FROM inspection_tasks WHERE site_id=? AND photo IS NOT NULL AND photo != '' ORDER BY check_time DESC",
                (wo['site_id'],)
            ).fetchall()
            for r in rows:
                photos.append({
                    'check_item': r['check_item'],
                    'photo': r['photo'],
                    'remark': r['remark'] or '',
                    'time': r['check_time'] or '',
                })

@app.route('/api/workorders/statistics')
@login_required
def workorder_statistics():
    site_ids = _filter_site_ids()
    with get_db() as db:
        if site_ids is not None:
            ph = ','.join('?' * len(site_ids))
            total = db.execute(f"SELECT COUNT(*) as c FROM work_orders WHERE site_id IN ({ph})", site_ids).fetchone()['c']
            by_status = {}
            for st in ['pending','accepted','generated','dispatched','in_progress','reviewing','closed']:
                by_status[st] = db.execute(f"SELECT COUNT(*) as c FROM work_orders WHERE status=? AND site_id IN ({ph})", [st] + site_ids).fetchone()['c']
            today = datetime.now().strftime('%Y-%m-%d')
            today_new = db.execute(f"SELECT COUNT(*) as c FROM work_orders WHERE date(created_at)=? AND site_id IN ({ph})", [today] + site_ids).fetchone()['c']
            today_closed = db.execute(f"SELECT COUNT(*) as c FROM work_orders WHERE date(resolved_at)=? AND site_id IN ({ph})", [today] + site_ids).fetchone()['c']
        else:
            total = db.execute("SELECT COUNT(*) as c FROM work_orders").fetchone()['c']
            by_status = {}
            for st in ['pending','accepted','generated','dispatched','in_progress','reviewing','closed']:
                by_status[st] = db.execute("SELECT COUNT(*) as c FROM work_orders WHERE status=?",(st,)).fetchone()['c']
            today = datetime.now().strftime('%Y-%m-%d')
            today_new = db.execute("SELECT COUNT(*) as c FROM work_orders WHERE date(created_at)=?",(today,)).fetchone()['c']
            today_closed = db.execute("SELECT COUNT(*) as c FROM work_orders WHERE date(resolved_at)=?",(today,)).fetchone()['c']
        return jsonify({'total':total, 'by_status':by_status, 'today_new':today_new, 'today_closed':today_closed})


@app.route('/api/workorders/<order_no>/related')
@login_required
def api_workorder_related(order_no):
    """获取工单关联的备件申请和设备回收记录"""
    with get_db() as db:
        parts = db.execute("""SELECT * FROM spare_part_requests WHERE work_order_no=? ORDER BY created_at DESC""",
                          (order_no,)).fetchall()
        recycles = db.execute("""SELECT * FROM device_recycle WHERE work_order_no=? ORDER BY created_at DESC""",
                             (order_no,)).fetchall()
    return jsonify({
        'parts': [dict(r) for r in parts],
        'recycles': [dict(r) for r in recycles],
    })


# --- Inspections ---
@app.route('/api/inspections')
@login_required
def get_inspections():
    site_ids = _filter_site_ids()
    freq = request.args.get('frequency', '')  # high/mid/low/annual
    with get_db() as db:
        q = """
            SELECT p.*,
                (SELECT COUNT(*) FROM inspection_tasks t WHERE t.plan_id=p.id) as total_items,
                (SELECT COUNT(*) FROM inspection_tasks t WHERE t.plan_id=p.id AND t.result IS NOT NULL) as completed_items
            FROM inspection_plans p
            WHERE 1=1
        """
        params = []
        if site_ids is not None:
            ph = ','.join('?' * len(site_ids))
            q += f" AND p.id IN (SELECT plan_id FROM plan_sites WHERE site_id IN ({ph}))"
            params.extend(site_ids)
        q += " ORDER BY p.created_at DESC"
        rows = db.execute(q, params).fetchall()
        plans = [dict(r) for r in rows]
        # 为每个计划加载关联站点列表
        for plan in plans:
            sites = db.execute("""
                SELECT s.id, s.name as site_name, s.code as site_code, s.type as site_type,
                    s.lat, s.lng, s.manager as assignee
                FROM plan_sites ps JOIN sites s ON ps.site_id=s.id
                WHERE ps.plan_id=?
            """, (plan['id'],)).fetchall()
            plan['sites'] = [dict(s) for s in sites]
            # 兼容旧字段：取第一个站点
            if sites:
                plan['site_id'] = sites[0]['id']
                plan['site_name'] = sites[0]['site_name']
                plan['site_code'] = sites[0]['site_code']
                plan['site_type'] = sites[0]['site_type']
                plan['lat'] = sites[0]['lat']
                plan['lng'] = sites[0]['lng']
                plan['assignee'] = sites[0]['assignee']
            else:
                plan['site_id'] = plan['site_name'] = plan['site_code'] = plan['site_type'] = None
                plan['lat'] = plan['lng'] = None
                plan['assignee'] = None
        # 按 site_type 统计分组
        site_type_map = {
            'station_yard': '站院', 'reservoir': '站院', 'sluice': '水文站',
            'dike': '水文站', 'pump': '水文站', 'water_supply': '水文站',
            'hydrology': '水文站', 'water_level': '水位站', 'rainfall': '雨量站',
            'groundwater': '地下水监测站', 'soil_moisture': '墒情站',
            'evaporation': '蒸发站',
        }
        site_cats = {}
        for p in plans:
            st = site_type_map.get(p.get('site_type',''), '其他')
            p['site_cat'] = st
            site_cats.setdefault(st, {'total':0,'pending':0,'in_progress':0,'completed':0})
            site_cats[st]['total'] += 1
            site_cats[st][p['status']] = site_cats[st].get(p['status'], 0) + 1
        return jsonify({'plans': plans, 'categories': site_cats, 'site_categories': site_cats})

@app.route('/api/inspections', methods=['POST'])
def create_inspection():
    data = request.json
    with get_db() as db:
        scheme_id = data.get('scheme_id')
        # 支持 site_ids 数组（多站点）和 site_id 单个站点（兼容旧版）
        site_ids = data.get('site_ids', [])
        site_id = data.get('site_id')
        if site_id and not site_ids:
            site_ids = [site_id]
        if not site_ids:
            return jsonify({'success': False, 'error': '请指定至少一个站点'}), 400
        first_site = site_ids[0]
        cursor = db.execute("""
            INSERT INTO inspection_plans (plan_name,site_id,type,start_date,end_date,period,description,category,scheme_id)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (data['plan_name'], first_site, data['type'], data['start_date'], data['end_date'], data.get('period','once'), data.get('description',''), data.get('category',''), scheme_id))
        plan_id = cursor.lastrowid
        # 写入 plan_sites（多站点关联）
        for sid in site_ids:
            db.execute("INSERT OR IGNORE INTO plan_sites (plan_id, site_id) VALUES (?,?)", (plan_id, sid))
        # 生成检查项：优先从scheme_id加载，否则用check_items
        check_items = data.get('check_items', [])
        if scheme_id:
            scheme_items = db.execute("SELECT check_item FROM inspection_scheme_items WHERE scheme_id=? ORDER BY sort_order",(scheme_id,)).fetchall()
            if scheme_items:
                check_items = [r['check_item'] for r in scheme_items]
        if not check_items:
            check_items = ['坝体外观检查','溢洪道检查','放水设施检查','监测设备检查','防汛物资检查','管理设施检查']
        for sid in site_ids:
            for item in check_items:
                db.execute(
                    "INSERT INTO inspection_tasks (plan_id,site_id,check_item) VALUES (?,?,?)",
                    (plan_id, sid, item)
                )
        db.commit()
        # 时间线记录
        operator = data.get('operator', '系统')
        db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                   ('inspection', plan_id, 'created', operator, f'创建巡检计划-{data["plan_name"]}'))
        db.commit()
        # 通知站点负责人
        _notify_inspection_plan(plan_id, data['plan_name'], first_site, '已创建')
        return jsonify({'success': True, 'plan_id': plan_id})

@app.route('/api/inspections/<int:plan_id>', methods=['DELETE'])
@login_required
def delete_inspection(plan_id):
    """删除巡检计划及其检查项"""
    with get_db() as db:
        plan = db.execute("SELECT plan_name, site_id FROM inspection_plans WHERE id=?", (plan_id,)).fetchone()
        if not plan:
            return jsonify({'error': '计划不存在'}), 404
        db.execute("DELETE FROM plan_sites WHERE plan_id=?", (plan_id,))
        db.execute("DELETE FROM inspection_tasks WHERE plan_id=?", (plan_id,))
        db.execute("DELETE FROM timeline_events WHERE source_type='inspection' AND source_id=?", (plan_id,))
        db.execute("DELETE FROM inspection_plans WHERE id=?", (plan_id,))
        db.commit()

@app.route('/api/inspections/<int:plan_id>/tasks')
def get_inspection_tasks(plan_id):
    with get_db() as db:
        rows = db.execute("SELECT * FROM inspection_tasks WHERE plan_id=? ORDER BY id", (plan_id,)).fetchall()
        return jsonify([dict(r) for r in rows])

@app.route('/api/inspections/<int:plan_id>/attachments')
def get_inspection_attachments(plan_id):
    """返回巡检计划的附件列表（有照片的检查项）"""
    with get_db() as db:
        rows = db.execute(
            "SELECT id, check_item, photo, remark, check_time, result FROM inspection_tasks WHERE plan_id=? AND photo IS NOT NULL AND photo != '' ORDER BY check_time DESC",
            (plan_id,)
        ).fetchall()
        return jsonify([dict(r) for r in rows])
@app.route('/api/inspections/tasks/<int:task_id>', methods=['PUT'])
def update_inspection_task(task_id):
    data = request.json
    with get_db() as db:
        # 构造动态更新字段
        updates = ["result=?", "photo=?", "gps_lat=?", "gps_lng=?", "check_time=?", "remark=?"]
        params = [data.get('result'), data.get('photo'), data.get('gps_lat'), data.get('gps_lng'),
                  data.get('check_time'), data.get('remark')]
        # 新增字段
        if 'photo_urls' in data:
            updates.append("photo_urls=?")
            params.append(data['photo_urls'])
        if 'calibrator' in data:
            updates.append("calibrator=?")
            params.append(data['calibrator'])
        if 'calibration_values' in data:
            updates.append("calibration_values=?")
            params.append(data['calibration_values'])
        params.append(task_id)
        db.execute(f"UPDATE inspection_tasks SET {','.join(updates)} WHERE id=?", params)

        # === 数据自洽性修复：巡检异常结果触发告警 ===
        if data.get('result') == 'abnormal':
            task = db.execute("SELECT site_id, check_item FROM inspection_tasks WHERE id=?", (task_id,)).fetchone()
            if task:
                check_item = data.get('remark', '') or task['check_item']
                create_alert_internal(db, task['site_id'], 'inspection', 0, 'yellow',
                    f'巡检异常：{task["check_item"]} - {check_item}')

        # 更新计划状态
        task = db.execute("SELECT plan_id FROM inspection_tasks WHERE id=?", (task_id,)).fetchone()
        if task:
            incomplete = db.execute(
                "SELECT COUNT(*) as c FROM inspection_tasks WHERE plan_id=? AND result IS NULL",
                (task['plan_id'],)
            ).fetchone()['c']
            if incomplete == 0:
                db.execute("UPDATE inspection_plans SET status='completed' WHERE id=?", (task['plan_id'],))
                plan = db.execute("SELECT plan_name, site_id FROM inspection_plans WHERE id=?", (task['plan_id'],)).fetchone()
                if plan:
                    db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                               ('inspection', task['plan_id'], 'completed', '系统', f'巡检计划完成-{plan["plan_name"]}'))
                    _notify_inspection_plan(task['plan_id'], plan['plan_name'], plan['site_id'], '已完成')
        db.commit()
        return jsonify({'success': True})

@app.route('/api/inspections/statistics')
@login_required
def inspection_statistics():
    site_ids = _filter_site_ids()
    with get_db() as db:
        if site_ids is not None:
            ph = ','.join('?' * len(site_ids))
            total_plans = db.execute(f"SELECT COUNT(DISTINCT plan_id) as c FROM plan_sites WHERE site_id IN ({ph})", site_ids).fetchone()['c']
            done = db.execute(f"SELECT COUNT(DISTINCT p.id) as c FROM inspection_plans p JOIN plan_sites ps ON p.id=ps.plan_id WHERE p.status='completed' AND ps.site_id IN ({ph})", site_ids).fetchone()['c']
            total_tasks = db.execute(f"SELECT COUNT(*) as c FROM inspection_tasks WHERE site_id IN ({ph})", site_ids).fetchone()['c']
            done_tasks = db.execute(f"SELECT COUNT(*) as c FROM inspection_tasks WHERE result IS NOT NULL AND site_id IN ({ph})", site_ids).fetchone()['c']
            abnormal = db.execute(f"SELECT COUNT(*) as c FROM inspection_tasks WHERE result='abnormal' AND site_id IN ({ph})", site_ids).fetchone()['c']
        else:
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

DEFAULT_CHECK_ITEMS = {
    '站院环境': ['水位井/站院/大门口全面打扫','设备表面及窗台擦拭','墙面天花板检查(无污迹/蜘蛛网)','草地灌木修剪维护','巡测站站房全面打扫','观测场草地维护(草高<20cm)'],
    '断面环境': ['测流断面上下游各5米清理杂草杂木','缆道铁塔四周清理','基本水尺断面上下游各10米清理','水尺码头/停船码头清理淤泥杂草','比降断面水尺道路清理','洪水退水时及时清理'],
    '水位观测': ['基本水尺读数观测记录','遥测水位及时间校对','人工与遥测水位偏差检测','水尺清洗检查','水位设备运行检查','填记水位巡查表并拍照存档'],
    '雨量监测': ['遥测雨量器现场运行维护','数据采集终端内部状态检查','供电设备及布线检查','雨量筒外观及水平检查','注水试验(季度≥12.5mm误差≤±4%)','特大暴雨后及时检查'],
    '蒸发监测': ['自动蒸发设备遥测终端巡检','蒸发器换水保持清洁','渗漏检查(半年/关闭阀门/邻站对比)','自动蒸发系统注水实验(汛前)','水圈清洁及环境维护'],
    '墒情监测': ['机箱内部清洁','周边杂草清理','无积水检查','数据校测记录','辅助站取土烘干法检验(干旱触发)'],
    '设施设备': ['水尺清洗检查','爬梯/护栏牢固度全面检查','设施设备外观检查','异常维修与拍照存档','上报中心站网监测科'],
    '缆道系统': ['行主索/循环索检查维护','拉线/卡头检查(异常通知甲方)','工作索毛刺断骨拍照留底','锚碇位移/土壤裂纹检查','导向轮/游轮/行车架运转检查','绞车运转检查','钢丝绳夹头/生锈/排水检查'],
    '安全防护': ['测验设施设备安全环境检查','灭火器压力及有效期检查','安全器材完好性检查','站房结构安全及电气线路检查','填写安全检查记录表','安全隐患及时告知中心'],
    '发电机': ['发电机维护保养(汛前/汛后:更换机油/线路/备足燃料)','机油液位检查','线路及各部件检查','发电运行≥30分钟并记录','燃料及机油储备检查'],
    '自定义': []
}

DAY_ITEMS = ['水位观测']
WEEK_ITEMS = ['站院环境','水位观测']
MONTH_ITEMS = ['站院环境','水位观测','雨量监测','蒸发监测','设施设备','安全防护','发电机']
QUARTER_ITEMS = ['雨量监测','墒情监测']
HALF_YEAR_ITEMS = ['蒸发监测']
YEAR_ITEMS = ['断面环境','蒸发监测','发电机']

# DOCX 巡查对象分类（按一）— 用于巡检计划分类显示
DOCX_CATEGORIES = [
    ('站院环境', '站院/观测场清洁、草地修剪维护'),
    ('断面环境', '测流断面及水尺码头清理'),
    ('水位观测', '水尺读数、遥测校对、水位设备检查'),
    ('雨量监测', '雨量器巡检、注水试验'),
    ('蒸发监测', '蒸发设备巡检、换水、渗漏检查'),
    ('墒情监测', '墒情站巡查、数据校测'),
    ('设施设备', '水尺、爬梯、护栏等设施检查'),
    ('缆道系统', '主索、绞车、锚碇等缆道检查'),
    ('安全防护', '灭火器、电气线路安全检查'),
    ('发电机', '发电机保养、运行检查'),
]

@app.route('/api/schemes/template')
def download_scheme_template():
    """下载巡检方案导入模板（CSV格式）"""
    import csv, io
    output = io.StringIO()
    output.write('\ufeff')
    w = csv.writer(output)
    w.writerow(['站点名称','分类','检查项','每日','每周','每月','每季度','每半年','每年'])
    all_cats = [c for c in DEFAULT_CHECK_ITEMS if DEFAULT_CHECK_ITEMS[c]]
    for cat in all_cats:
        for item in DEFAULT_CHECK_ITEMS[cat]:
            w.writerow([
                '', cat, item,
                '✓' if cat in DAY_ITEMS else '',
                '✓' if cat in WEEK_ITEMS else '',
                '✓' if cat in MONTH_ITEMS else '',
                '✓' if cat in QUARTER_ITEMS else '',
                '✓' if cat in HALF_YEAR_ITEMS else '',
                '✓' if cat in YEAR_ITEMS else '',
            ])
    data = output.getvalue().encode('utf-8-sig')
    output.close()
    from flask import Response
    from urllib.parse import quote
    cd = f"attachment; filename=\"inspection_template.csv\"; filename*=UTF-8''{quote('巡检方案导入模板.csv')}"
    return Response(data, mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': cd})

@app.route('/api/schemes/import', methods=['POST'])
def import_schemes():
    """导入站点级方案表：每行=站点+检查项，匹配站点名后写入对应方案"""
    try: import openpyxl
    except: return jsonify({'error':'openpyxl未安装'}),500
    file = request.files.get('file')
    if not file: return jsonify({'error':'请上传文件'}),400
    wb = openpyxl.load_workbook(file); ws = wb.active
    def _yes(v): return str(v).strip() in ('✓','√','Y','y','1','是','yes')
    created = 0
    with get_db() as db:
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row or len(row)<3: continue
            site_name = str(row[0]).strip() if row[0] else ''
            cat = str(row[1]).strip() if row[1] else ''
            item = str(row[2]).strip() if row[2] else ''
            day_flag = row[3] if len(row)>3 and row[3] else ''
            week_flag = row[4] if len(row)>4 and row[4] else ''
            month_flag = row[5] if len(row)>5 and row[5] else ''
            if not site_name or not item: continue
            site = db.execute("SELECT id, name FROM sites WHERE name=? OR code=?",(site_name,site_name)).fetchone()
            if not site:
                site = db.execute("SELECT id, name FROM sites WHERE name LIKE ?",('%'+site_name+'%',)).fetchone()
            if not site: continue
            sid, sname = site[0], site[1]
            for period, flag, label in [('daily',day_flag,'日巡检方案'),('weekly',week_flag,'周巡检方案'),('monthly',month_flag,'月巡检方案')]:
                if not _yes(flag): continue
                db.execute("INSERT OR IGNORE INTO inspection_schemes (site_id,period,name) VALUES (?,?,?)",(sid,period,f'{sname}-{label}'))
                scheme = db.execute("SELECT id FROM inspection_schemes WHERE site_id=? AND period=?",(sid,period)).fetchone()
                if not scheme: continue
                sc_id = scheme['id']
                # Check if item already exists
                existing = db.execute("SELECT id FROM inspection_scheme_items WHERE scheme_id=? AND check_item=?",(sc_id,item)).fetchone()
                if not existing:
                    next_order = db.execute("SELECT COALESCE(MAX(sort_order),-1)+1 as n FROM inspection_scheme_items WHERE scheme_id=?",(sc_id,)).fetchone()['n']
                    db.execute("INSERT INTO inspection_scheme_items (scheme_id,category,check_item,sort_order) VALUES (?,?,?,?)",(sc_id,cat,item,next_order))
                    created += 1
        db.commit()
    return jsonify({'success':True,'created':created,"warn":"仅记录新增项，已有项未覆盖"})


UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'frontend', 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """上传图片/附件，返回可访问的URL。支持 multipart/form-data，字段名 file。
    图片自动压缩（最大边1920px，质量0.7），单文件上限5MB。"""
    file = request.files.get('file')
    if not file:
        return jsonify({'error': '请选择文件'}), 400

    ext = os.path.splitext(file.filename or '.jpg')[1].lower() or '.jpg'
    image_exts = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}

    # 读取文件内容，检查大小
    file_data = file.read()
    if len(file_data) > 5 * 1024 * 1024:
        return jsonify({'error': '文件大小超过5MB限制'}), 400

    # 图片压缩处理
    if ext in image_exts:
        try:
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(file_data))
            # 限制最大边为1920px
            max_side = 1920
            if max(img.size) > max_side:
                ratio = max_side / max(img.size)
                new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                img = img.resize(new_size, Image.LANCZOS)
            # 转换为RGB（如果是PNG带透明通道）
            if ext in ('.jpg', '.jpeg') or ext == '.png':
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')
            # 保存为压缩JPEG
            buf = io.BytesIO()
            save_ext = '.jpg'
            if ext == '.png':
                img.save(buf, format='PNG', optimize=True)
            else:
                img.save(buf, format='JPEG', quality=70, optimize=True)
            file_data = buf.getvalue()
        except ImportError:
            pass  # Pillow未安装，跳过压缩
        except Exception:
            pass  # 压缩失败，使用原文件

    fname = str(uuid.uuid4())[:8] + (ext if ext in image_exts else '.jpg')
    path = os.path.join(UPLOAD_DIR, fname)
    with open(path, 'wb') as f:
        f.write(file_data)
    return jsonify({'success': True, 'url': '/uploads/' + fname})


@app.route('/api/sites/<int:site_id>/schemes')
def get_site_schemes(site_id):
    with get_db() as db:
        schemes = db.execute("SELECT s.*,(SELECT COUNT(*) FROM inspection_scheme_items i WHERE i.scheme_id=s.id) as item_count FROM inspection_schemes s WHERE s.site_id=? ORDER BY CASE s.period WHEN 'daily' THEN 1 WHEN 'weekly' THEN 2 ELSE 3 END",(site_id,)).fetchall()
        return jsonify([dict(r) for r in schemes])

@app.route('/api/schemes/<int:scheme_id>')
def get_scheme_detail(scheme_id):
    with get_db() as db:
        scheme = db.execute("SELECT * FROM inspection_schemes WHERE id=?",(scheme_id,)).fetchone()
        if not scheme: return jsonify({'error':'方案不存在'}),404
        items = db.execute("SELECT * FROM inspection_scheme_items WHERE scheme_id=? ORDER BY sort_order",(scheme_id,)).fetchall()
        result = dict(scheme); result['items']=[dict(r) for r in items]
        return jsonify(result)

@app.route('/api/schemes/<int:scheme_id>', methods=['PUT'])
def update_scheme(scheme_id):
    data = request.json
    with get_db() as db:
        scheme = db.execute("SELECT * FROM inspection_schemes WHERE id=?",(scheme_id,)).fetchone()
        if not scheme: return jsonify({'error':'方案不存在'}),404
        if 'name' in data: db.execute("UPDATE inspection_schemes SET name=?,updated_at=datetime('now','localtime') WHERE id=?",(data['name'],scheme_id))
        if 'items' in data:
            db.execute("DELETE FROM inspection_scheme_items WHERE scheme_id=?",(scheme_id,))
            for idx,item in enumerate(data['items']):
                db.execute("INSERT INTO inspection_scheme_items (scheme_id,category,check_item,sort_order,is_required) VALUES (?,?,?,?,?)",(scheme_id,item.get('category',''),item.get('check_item',''),idx,item.get('is_required',1)))
        db.commit()
        return jsonify({'success':True})

@app.route('/api/schemes/<int:scheme_id>/items', methods=['POST'])
def add_scheme_item(scheme_id):
    data = request.json
    item_name = data.get('check_item','').strip()
    if not item_name: return jsonify({'error':'检查项不能为空'}),400
    with get_db() as db:
        max_order = db.execute("SELECT COALESCE(MAX(sort_order),-1)+1 as n FROM inspection_scheme_items WHERE scheme_id=?",(scheme_id,)).fetchone()['n']
        db.execute("INSERT INTO inspection_scheme_items (scheme_id,category,check_item,sort_order) VALUES (?,?,?,?)",(scheme_id,data.get('category','自定义'),item_name,max_order))
        db.execute("UPDATE inspection_schemes SET updated_at=datetime('now','localtime') WHERE id=?",(scheme_id,))
        db.commit()
        return jsonify({'success':True})

@app.route('/api/schemes/items/<int:item_id>', methods=['DELETE'])
def delete_scheme_item_ep(item_id):
    with get_db() as db:
        db.execute("DELETE FROM inspection_scheme_items WHERE id=?",(item_id,))
        db.commit()
        return jsonify({'success':True})

@app.route('/api/inspections/auto-generate', methods=['POST'])
def auto_generate_inspections():
    """按频次分层的智能排程引擎（替代旧的日期轮询方案）
    
    请求参数（可选）：
    - user_id: 指定某人的组（默认全部分配）
    - period: daily/weekly/monthly (默认monthly)
    - start_date: 起始日期（默认今天）
    - end_date: 截止日期（默认+30天）
    """
    data = request.get_json(silent=True) or {}
    period = data.get('period', 'monthly')
    start_str = data.get('start_date', datetime.now().strftime('%Y-%m-%d'))
    user_id = data.get('user_id')
    force = data.get('force', False)  # 是否覆盖已存在的计划
    
    start = datetime.strptime(start_str, '%Y-%m-%d')
    if period == 'daily':
        end = start + timedelta(days=1)
    elif period == 'weekly':
        end = start + timedelta(days=7)
    else:
        end = start + timedelta(days=30)
    end_str = end.strftime('%Y-%m-%d')
    
    # 频次映射：period -> 应包含的frequency_level
    freq_map = {
        'high': ['high'],
        'mid': ['high', 'mid'],
        'low': ['high', 'mid', 'low'],
        'annual': ['high', 'mid', 'low', 'annual'],
    }
    applicable = freq_map.get(period, ['high', 'mid'])
    
    with get_db() as db:
        rows = db.execute("""
            SELECT si.*, s.name as scheme_name, s.site_id, s.period as speriod
            FROM inspection_scheme_items si
            JOIN inspection_schemes s ON si.scheme_id=s.id
            WHERE s.status='active'
            AND (si.frequency_level IS NULL OR si.frequency_level IN ({vals}))
            ORDER BY s.site_id, si.sort_order
        """.format(vals=','.join('?' * len(applicable))), applicable).fetchall()
        
        if not rows:
            # 降级：从已有inspection_plans读取站点列表作为参考
            plan_sites = db.execute("SELECT DISTINCT site_id FROM inspection_plans").fetchall()
            if not plan_sites:
                plan_sites = db.execute("SELECT id as site_id FROM sites WHERE id IN (1,5,108,193)").fetchall()
            for ps in plan_sites:
                # 先确保该站点有活跃方案
                scheme = db.execute("SELECT id FROM inspection_schemes WHERE site_id=? AND status='active' LIMIT 1", (ps['site_id'],)).fetchone()
                if not scheme:
                    db.execute("INSERT INTO inspection_schemes (site_id,period,name) VALUES (?,?,?)",
                               (ps['site_id'], period, f"站{ps['site_id']}巡检方案"))
                    scheme_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
                else:
                    scheme_id = scheme['id']
                # 检查是否有带频次的方案项
                existing_items = db.execute("SELECT id FROM inspection_scheme_items WHERE scheme_id=? AND frequency_level IS NOT NULL LIMIT 1", (scheme_id,)).fetchone()
                if not existing_items:
                    # 创建默认方案项
                    db.execute("DELETE FROM inspection_scheme_items WHERE scheme_id=?", (scheme_id,))
                    default_items = [
                        ('水位观测', 'high', 1), ('设备状态确认', 'high', 2), ('传感器外观清洁', 'high', 3),
                        ('数据通讯检查', 'high', 4), ('电池电压检查', 'mid', 5), ('太阳能板检查', 'mid', 6),
                        ('机箱密封性检查', 'mid', 7), ('站院环境维护', 'mid', 8), ('翻斗雨量计校准', 'low', 9),
                        ('水位计精度校验', 'low', 10), ('全面校准试验', 'annual', 11),
                    ]
                    for item_name, freq, order in default_items:
                        if freq in applicable:
                            db.execute("INSERT INTO inspection_scheme_items (scheme_id,category,check_item,frequency_level,sort_order) VALUES (?,'常规检查',?,?,?)",
                                       (scheme_id, item_name, freq, order))
                rows.extend(db.execute("""
                    SELECT si.*, s.name as scheme_name, s.site_id, s.period as speriod
                    FROM inspection_scheme_items si
                    JOIN inspection_schemes s ON si.scheme_id=s.id
                    WHERE s.site_id=? AND s.status='active'
                """, (ps['site_id'],)).fetchall() or [])
        
        if not rows:
            return jsonify({'success': False, 'error': '没有活跃的巡检方案项，请先在方案中配置检查项', 'generated': 0})
        
        # 按site_id分组
        site_groups = {}
        for r in rows:
            sid = r['site_id']
            site_groups.setdefault(sid, []).append(r)
        
        # 获取所有运维人员及其站点分配
        operators = db.execute("""
            SELECT u.id, u.real_name FROM users u WHERE u.role='operator' ORDER BY u.id
        """).fetchall()
        
        if user_id:
            operators = [op for op in operators if op['id'] == user_id]
        
        generated = 0
        for op in operators:
            user_sites = db.execute("SELECT site_id FROM user_sites WHERE user_id=?", (op['id'],)).fetchall()
            # 按站点打包：同一操作员的所有站点合并为一个计划
            op_site_ids = [us['site_id'] for us in user_sites]
            all_items = []
            check_items_set = set()
            for sid in op_site_ids:
                items = site_groups.get(sid, [])
                if not items:
                    continue
                all_items.append((sid, items))
                for item in items:
                    check_items_set.add(item['check_item'])
            if not all_items:
                continue
            # 检查是否已存在该操作员该时段的计划
            if not force:
                exist = db.execute(
                    "SELECT p.id FROM inspection_plans p JOIN plan_sites ps ON p.id=ps.plan_id WHERE ps.site_id IN ({}) AND p.start_date=? AND p.status='pending' LIMIT 1".format(
                        ','.join('?' * len(op_site_ids))
                    ), op_site_ids + [start_str]
                ).fetchone()
                if exist:
                    continue
            plan_name = f"{period}巡检-{op['real_name']}"
            first_sid = op_site_ids[0] if op_site_ids else 0
            db.execute("""
                INSERT INTO inspection_plans (plan_name,site_id,type,start_date,end_date,status)
                VALUES (?,?,?,?,?,?)
            """, (plan_name, first_sid, period, start_str, end_str, 'pending'))
            plan_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            # 写入所有站点到 plan_sites，并生成每个站点的检查项
            for sid, items in all_items:
                db.execute("INSERT OR IGNORE INTO plan_sites (plan_id, site_id) VALUES (?,?)", (plan_id, sid))
                for item in items:
                    db.execute("""
                        INSERT INTO inspection_tasks (plan_id,site_id,check_item)
                        VALUES (?,?,?)
                    """, (plan_id, sid, item['check_item']))
                generated += 1
        
        db.commit()
        msg = f"已生成 {generated} 个巡检计划"
        if generated == 0:
            msg = "该时段计划已存在，无需重复生成"
        return jsonify({'success': True, 'generated': generated, 'message': msg})


# ===================== 移动巡检方案新增 API =====================

@app.route('/api/inspections/skip', methods=['POST'])
@login_required
def skip_inspection_item():
    """跳过某项检查（记录跳过原因）"""
    data = request.get_json(silent=True) or {}
    with get_db() as db:
        db.execute("""
            INSERT INTO inspection_skip_logs (plan_id,task_id,site_id,check_item,reason,skip_type)
            VALUES (?,?,?,?,?,?)
        """, (data.get('plan_id'), data.get('task_id'), data.get('site_id'),
              data.get('check_item',''), data.get('reason',''), data.get('skip_type','user')))
        # 更新跳过计数
        exist = db.execute(
            "SELECT id, skip_count FROM inspection_skip_logs WHERE plan_id=? AND check_item=? ORDER BY id DESC LIMIT 1",
            (data['plan_id'], data['check_item'])
        ).fetchone()
        if exist:
            db.execute("UPDATE inspection_skip_logs SET skip_count=skip_count+1 WHERE id=?", (exist['id'],))
        db.commit()
        return jsonify({'success': True, 'message': '已记录跳过'})

@app.route('/api/inspections/skip/history')
@login_required
def get_skip_history():
    """查看跳过记录"""
    site_id = request.args.get('site_id', type=int)
    plan_id = request.args.get('plan_id', type=int)
    with get_db() as db:
        q = "SELECT * FROM inspection_skip_logs WHERE 1=1"
        params = []
        if site_id:
            q += " AND site_id=?"
            params.append(site_id)
        if plan_id:
            q += " AND plan_id=?"
            params.append(plan_id)
        q += " ORDER BY created_at DESC LIMIT 50"
        rows = db.execute(q, params).fetchall()
        return jsonify([dict(r) for r in rows])

@app.route('/api/calibration-templates')
@login_required
def get_calibration_templates():
    """获取校准模板列表"""
    device_type = request.args.get('device_type', '')
    with get_db() as db:
        q = "SELECT * FROM calibration_templates WHERE 1=1"
        params = []
        if device_type:
            q += " AND device_type=?"
            params.append(device_type)
        q += " ORDER BY sort_order, category"
        rows = db.execute(q, params).fetchall()
        return jsonify([dict(r) for r in rows])

@app.route('/api/calibration-templates', methods=['POST'])
@login_required
def create_calibration_template():
    """创建校准模板"""
    data = request.get_json(silent=True) or {}
    with get_db() as db:
        db.execute("""
            INSERT INTO calibration_templates (device_type,template_name,fields,calculations,thresholds,category,sort_order)
            VALUES (?,?,?,?,?,?,?)
        """, (data['device_type'], data['template_name'],
              data.get('fields','[]'), data.get('calculations','[]'),
              data.get('thresholds','[]'), data.get('category',''), data.get('sort_order',0)))
        db.commit()
        return jsonify({'success': True, 'id': db.execute("SELECT last_insert_rowid()").fetchone()[0]})

@app.route('/api/inspections/photo-types', methods=['GET', 'POST'])
@login_required
def manage_photo_types():
    """管理照片类型配置"""
    with get_db() as db:
        if request.method == 'POST':
            data = request.get_json(silent=True) or {}
            db.execute("""
                INSERT INTO inspection_photo_types (plan_id,site_type,photo_type,label,min_count,sort_order)
                VALUES (?,?,?,?,?,?)
            """, (data.get('plan_id'), data.get('site_type',''), data['photo_type'],
                  data['label'], data.get('min_count',1), data.get('sort_order',0)))
            db.commit()
            return jsonify({'success': True})
        else:
            plan_id = request.args.get('plan_id', type=int)
            site_type = request.args.get('site_type', '')
            q = "SELECT * FROM inspection_photo_types WHERE 1=1"
            params = []
            if plan_id:
                q += " AND plan_id=?"
                params.append(plan_id)
            if site_type:
                q += " AND site_type=?"
                params.append(site_type)
            q += " ORDER BY sort_order"
            rows = db.execute(q, params).fetchall()
            return jsonify([dict(r) for r in rows])


# ===================== 通知系统 API =====================

@app.route('/api/notifications')
@login_required
def get_notifications():
    """获取当前用户的通知列表"""
    user = g.current_user
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 50, type=int)
    offset = (page - 1) * limit
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (user['id'], limit, offset)
        ).fetchall()
        unread = db.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0",
            (user['id'],)
        ).fetchone()[0]
        return jsonify({'notifications': [dict(r) for r in rows], 'unread_count': unread})

@app.route('/api/notifications/unread-count')
@login_required
def unread_notification_count():
    """获取未读通知数量"""
    user = g.current_user
    with get_db() as db:
        cnt = db.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0",
            (user['id'],)
        ).fetchone()[0]
        return jsonify({'count': cnt})

@app.route('/api/notifications/<int:nid>/read', methods=['PUT'])
@login_required
def mark_notification_read(nid):
    """标记单条通知为已读"""
    user = g.current_user
    with get_db() as db:
        db.execute(
            "UPDATE notifications SET is_read=1 WHERE id=? AND user_id=?",
            (nid, user['id'])
        )
        db.commit()
        return jsonify({'success': True})

@app.route('/api/notifications/read-all', methods=['PUT'])
@login_required
def mark_all_notifications_read():
    """标记所有通知为已读"""
    user = g.current_user
    with get_db() as db:
        db.execute(
            "UPDATE notifications SET is_read=1 WHERE user_id=? AND is_read=0",
            (user['id'],)
        )
        db.commit()
        return jsonify({'success': True})


# --- Workorder management ---
@app.route('/api/workorders/<order_no>', methods=['DELETE'])
def delete_workorder(order_no):
    """删除工单（支持待受理、已受理、处置中、审核中或已完成的工单）"""
    with get_db() as db:
        cur = db.execute('SELECT status FROM work_orders WHERE order_no=?', (order_no,)).fetchone()
        if not cur:
            return jsonify({'error': 'not found'}), 404
        if cur['status'] not in ('pending', 'accepted', 'in_progress', 'reviewing', 'closed'):
            return jsonify({'error': '当前状态不允许删除'}), 400
        db.execute('DELETE FROM work_orders WHERE order_no=?', (order_no,))
        db.execute("DELETE FROM timeline_events WHERE source_type='workorder' AND source_id=?", (order_no,))
        db.commit()
        return jsonify({'success': True, 'message': '工单已删除'})
# --- Maintenance Templates ---
@app.route('/api/maintenance/templates')
def get_maintenance_templates():
    """返回所有运维模板"""
    with get_db() as db:
        rows = db.execute("SELECT * FROM maintenance_templates ORDER BY sort_order").fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d['check_items']:
                try:
                    d['check_items'] = json.loads(d['check_items'])
                except:
                    d['check_items'] = []
            result.append(d)
        return jsonify(result)


@app.route('/api/maintenance/templates', methods=['POST'])
@login_required
def create_maintenance_template():
    """新建运维模板"""
    data = request.get_json(force=True)
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'error': '模板名称不能为空'}), 400
    category = (data.get('category') or '').strip()
    sub_category = (data.get('sub_category') or '').strip()
    frequency = data.get('frequency') or 'monthly'
    description = (data.get('description') or '').strip()
    standard = (data.get('standard') or '').strip()
    check_items = data.get('check_items')
    estimated_hours = data.get('estimated_hours')
    photo_required = 1 if data.get('photo_required') else 0

    if isinstance(check_items, list):
        check_items = json.dumps(check_items, ensure_ascii=False)

    with get_db() as db:
        cur = db.execute(
            """INSERT INTO maintenance_templates
               (title, category, sub_category, frequency, description, standard, check_items, estimated_hours, photo_required)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (title, category, sub_category, frequency, description, standard, check_items, estimated_hours, photo_required)
        )
        db.commit()
    return jsonify({'success': True, 'id': cur.lastrowid, 'message': '模板创建成功'})


@app.route('/api/maintenance/templates/<int:tid>', methods=['PUT'])
@login_required
def update_maintenance_template(tid):
    """编辑运维模板"""
    data = request.get_json(force=True)
    with get_db() as db:
        existing = db.execute("SELECT id FROM maintenance_templates WHERE id=?", (tid,)).fetchone()
        if not existing:
            return jsonify({'error': '模板不存在'}), 404

        fields = []
        values = []
        for col in ['title', 'category', 'sub_category', 'frequency', 'description', 'standard', 'estimated_hours', 'photo_required']:
            if col in data:
                if col == 'photo_required':
                    fields.append(f"{col}=?")
                    values.append(1 if data[col] else 0)
                else:
                    fields.append(f"{col}=?")
                    values.append(data[col])
        if 'check_items' in data:
            fields.append("check_items=?")
            ci = data['check_items']
            values.append(json.dumps(ci, ensure_ascii=False) if isinstance(ci, list) else ci)

        if not fields:
            return jsonify({'error': '没有可更新的字段'}), 400
        values.append(tid)
        db.execute(f"UPDATE maintenance_templates SET {', '.join(fields)} WHERE id=?", values)
        db.commit()
    return jsonify({'success': True, 'message': '模板已更新'})


@app.route('/api/maintenance/templates/<int:tid>', methods=['DELETE'])
@login_required
def delete_maintenance_template(tid):
    """删除运维模板"""
    with get_db() as db:
        existing = db.execute("SELECT id FROM maintenance_templates WHERE id=?", (tid,)).fetchone()
        if not existing:
            return jsonify({'error': '模板不存在'}), 404
        db.execute("DELETE FROM maintenance_templates WHERE id=?", (tid,))
        db.commit()
    return jsonify({'success': True, 'message': '模板已删除'})


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
    template_id = data.get('template_id')
    with get_db() as db:
        if template_id:
            # 从模板自动填充
            tpl = db.execute("SELECT * FROM maintenance_templates WHERE id=?", (template_id,)).fetchone()
            if tpl:
                site_name = db.execute("SELECT name FROM sites WHERE id=?", (data['site_id'],)).fetchone()
                site_label = site_name['name'] if site_name else ''
                plan_name = data.get('plan_name') or f"{tpl['title']}-{site_label}"
                category = tpl['category']
                frequency = tpl['frequency']
                sub_category = tpl['sub_category']
                remark = data.get('remark') or tpl['description']
                cur = db.execute(
                    "INSERT INTO maintenance_plans (site_id,plan_name,category,frequency,due_date,assignee,template_id,sub_category,remark) VALUES (?,?,?,?,?,?,?,?,?)",
                    (data['site_id'], plan_name, category, frequency, data.get('due_date'), data.get('assignee'), template_id, sub_category, remark)
                )
            else:
                return jsonify({'error': 'template not found'}), 404
        else:
            # 无模板的传统创建方式
            cur = db.execute(
                "INSERT INTO maintenance_plans (site_id,plan_name,category,frequency,due_date,assignee) VALUES (?,?,?,?,?,?)",
                (data['site_id'], data['plan_name'], data['category'], data.get('frequency','monthly'), data.get('due_date'), data.get('assignee'))
            )
        db.commit()

@app.route('/api/maintenance/plans/<int:plan_id>/complete', methods=['PUT'])
def complete_maintenance_plan(plan_id):
    data = request.get_json(silent=True) or {}
    check_results = data.get('check_results')
    with get_db() as db:
        if check_results:
            db.execute("UPDATE maintenance_plans SET status='completed', completed_at=datetime('now','localtime'), check_results=? WHERE id=?",
                       (json.dumps(check_results, ensure_ascii=False), plan_id))
        else:
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

# ===================== Inspection V2 API =====================

# --- 方案模板 CRUD ---

@app.route('/api/inspection-v2/templates')
def v2_get_templates():
    """获取方案模板列表"""
    category = request.args.get('category', '')
    with get_db() as db:
        q = "SELECT t.*, (SELECT COUNT(*) FROM inspection_template_items WHERE template_id=t.id) as item_count FROM inspection_templates t WHERE 1=1"
        params = []
        if category:
            q += " AND t.category=?"
            params.append(category)
        q += " ORDER BY t.sort_order, t.id"
        rows = db.execute(q, params).fetchall()
        return jsonify([dict(r) for r in rows])

@app.route('/api/inspection-v2/templates', methods=['POST'])
def v2_create_template():
    """创建方案模板"""
    data = request.get_json(silent=True) or {}
    name = data.get('template_name', '').strip()
    category = data.get('category', '').strip()
    frequency = data.get('frequency', 'monthly')
    desc = data.get('description', '')
    items = data.get('items', [])
    if not name or not category:
        return jsonify({'error': '模板名称和分类不能为空'}), 400
    with get_db() as db:
        db.execute("INSERT INTO inspection_templates (template_name,category,frequency,description) VALUES (?,?,?,?)",
                   (name, category, frequency, desc))
        tid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        for i, item in enumerate(items):
            db.execute("""
                INSERT INTO inspection_template_items (template_id,item_name,category,frequency_level,photo_required,sort_order)
                VALUES (?,?,?,?,?,?)
            """, (tid, item.get('item_name',''), item.get('category',''), item.get('frequency_level','mid'),
                  1 if item.get('photo_required') else 0, i+1))
        db.commit()
        return jsonify({'id': tid, 'success': True})

@app.route('/api/inspection-v2/templates/<int:tid>', methods=['PUT'])
def v2_update_template(tid):
    """更新方案模板"""
    data = request.get_json(silent=True) or {}
    with get_db() as db:
        tpl = db.execute("SELECT id FROM inspection_templates WHERE id=?", (tid,)).fetchone()
        if not tpl:
            return jsonify({'error': '模板不存在'}), 404
        fields = []
        params = []
        for key in ('template_name', 'category', 'frequency', 'description', 'status', 'sort_order'):
            if key in data:
                fields.append(f"{key}=?")
                params.append(data[key])
        if fields:
            params.append(tid)
            db.execute(f"UPDATE inspection_templates SET {','.join(fields)} WHERE id=?", params)
        # 如果提供了items，全量替换
        if 'items' in data:
            db.execute("DELETE FROM inspection_template_items WHERE template_id=?", (tid,))
            for i, item in enumerate(data['items']):
                db.execute("""
                    INSERT INTO inspection_template_items (template_id,item_name,category,frequency_level,photo_required,sort_order)
                    VALUES (?,?,?,?,?,?)
                """, (tid, item.get('item_name',''), item.get('category',''), item.get('frequency_level','mid'),
                      1 if item.get('photo_required') else 0, i+1))
        db.commit()
        return jsonify({'success': True})

@app.route('/api/inspection-v2/templates/<int:tid>', methods=['DELETE'])
def v2_delete_template(tid):
    """删除方案模板"""
    with get_db() as db:
        # 删除关联的配置、排程、检查项
        db.execute("DELETE FROM inspection_template_items WHERE template_id=?", (tid,))
        db.execute("DELETE FROM inspection_configs WHERE template_id=?", (tid,))
        db.execute("DELETE FROM inspection_schedules WHERE template_id=?", (tid,))
        db.execute("DELETE FROM inspection_templates WHERE id=?", (tid,))
        db.commit()
        return jsonify({'success': True})

@app.route('/api/inspection-v2/templates/<int:tid>/items')
def v2_get_template_items(tid):
    """获取模板检查项列表"""
    with get_db() as db:
        rows = db.execute("SELECT * FROM inspection_template_items WHERE template_id=? ORDER BY sort_order", (tid,)).fetchall()
        return jsonify([dict(r) for r in rows])

@app.route('/api/inspection-v2/templates/<int:tid>/items', methods=['POST'])
def v2_add_template_item(tid):
    """添加模板检查项"""
    data = request.get_json(silent=True) or {}
    item_name = data.get('item_name', '').strip()
    if not item_name:
        return jsonify({'error': '检查项名称不能为空'}), 400
    with get_db() as db:
        max_sort = db.execute("SELECT MAX(sort_order) FROM inspection_template_items WHERE template_id=?", (tid,)).fetchone()[0] or 0
        db.execute("""
            INSERT INTO inspection_template_items (template_id,item_name,category,frequency_level,photo_required,sort_order)
            VALUES (?,?,?,?,?,?)
        """, (tid, item_name, data.get('category',''), data.get('frequency_level','mid'),
              1 if data.get('photo_required') else 0, max_sort + 1))
        db.commit()
        return jsonify({'id': db.execute("SELECT last_insert_rowid()").fetchone()[0], 'success': True})

@app.route('/api/inspection-v2/templates/<int:tid>/items/<int:item_id>', methods=['PUT'])
def v2_update_template_item(tid, item_id):
    """更新模板检查项"""
    data = request.get_json(silent=True) or {}
    with get_db() as db:
        fields = []
        params = []
        for key in ('item_name', 'category', 'frequency_level', 'sort_order'):
            if key in data:
                fields.append(f"{key}=?")
                params.append(data[key])
        if 'photo_required' in data:
            fields.append("photo_required=?")
            params.append(1 if data['photo_required'] else 0)
        if fields:
            params.append(item_id)
            db.execute(f"UPDATE inspection_template_items SET {','.join(fields)} WHERE id=? AND template_id=?", params + [tid])
        db.commit()
        return jsonify({'success': True})

@app.route('/api/inspection-v2/templates/<int:tid>/items/<int:item_id>', methods=['DELETE'])
def v2_delete_template_item(tid, item_id):
    """删除模板检查项"""
    with get_db() as db:
        db.execute("DELETE FROM inspection_template_items WHERE id=? AND template_id=?", (item_id, tid))
        db.commit()
        return jsonify({'success': True})

# --- 巡检配置 CRUD + 匹配引擎 ---

@app.route('/api/inspection-v2/configs')
def v2_get_configs():
    """获取巡检配置列表"""
    site_type = request.args.get('site_type', '')
    with get_db() as db:
        q = """
            SELECT ic.*, it.template_name, it.category as tpl_category, it.frequency as tpl_frequency,
                   (SELECT COUNT(*) FROM inspection_template_items WHERE template_id=ic.template_id) as item_count
            FROM inspection_configs ic
            JOIN inspection_templates it ON ic.template_id = it.id
            WHERE 1=1
        """
        params = []
        if site_type:
            q += " AND ic.site_type=?"
            params.append(site_type)
        q += " ORDER BY ic.site_type, it.sort_order"
        rows = db.execute(q, params).fetchall()
        return jsonify([dict(r) for r in rows])

@app.route('/api/inspection-v2/configs', methods=['POST'])
def v2_create_config():
    """创建巡检配置规则"""
    data = request.get_json(silent=True) or {}
    site_type = data.get('site_type', '').strip()
    template_id = data.get('template_id')
    if not site_type or not template_id:
        return jsonify({'error': '站点类型和模板不能为空'}), 400
    with get_db() as db:
        # 检查是否已存在相同配置
        existing = db.execute("SELECT id FROM inspection_configs WHERE site_type=? AND template_id=?",
                              (site_type, template_id)).fetchone()
        if existing:
            return jsonify({'error': '该站点类型已配置此模板'}), 409
        db.execute("""
            INSERT INTO inspection_configs (site_type,device_types,template_id,is_active,remark)
            VALUES (?,?,?,?,?)
        """, (site_type, _json.dumps(data.get('device_types', []), ensure_ascii=False),
              template_id, 1, data.get('remark', '')))
        db.commit()
        return jsonify({'id': db.execute("SELECT last_insert_rowid()").fetchone()[0], 'success': True})

@app.route('/api/inspection-v2/configs/<int:cid>', methods=['PUT'])
def v2_update_config(cid):
    """更新巡检配置"""
    data = request.get_json(silent=True) or {}
    with get_db() as db:
        fields = []
        params = []
        for key in ('site_type', 'is_active', 'remark'):
            if key in data:
                fields.append(f"{key}=?")
                params.append(data[key])
        if 'device_types' in data:
            fields.append("device_types=?")
            params.append(_json.dumps(data['device_types'], ensure_ascii=False))
        if 'template_id' in data:
            fields.append("template_id=?")
            params.append(data['template_id'])
        if fields:
            params.append(cid)
            db.execute(f"UPDATE inspection_configs SET {','.join(fields)} WHERE id=?", params)
        db.commit()
        return jsonify({'success': True})

@app.route('/api/inspection-v2/configs/<int:cid>', methods=['DELETE'])
def v2_delete_config(cid):
    """删除巡检配置"""
    with get_db() as db:
        db.execute("DELETE FROM inspection_configs WHERE id=?", (cid,))
        db.commit()
        return jsonify({'success': True})

@app.route('/api/inspection-v2/configs/match')
def v2_match_configs():
    """匹配引擎：给定站点，返回适配的所有模板+检查项"""
    site_id = request.args.get('site_id', type=int)
    if not site_id:
        return jsonify({'error': '缺少site_id参数'}), 400
    with get_db() as db:
        site = db.execute("SELECT id, type, name FROM sites WHERE id=?", (site_id,)).fetchone()
        if not site:
            return jsonify({'error': '站点不存在'}), 404
        # 获取站点设备类型
        dev_types = [r['device_type'] for r in db.execute(
            "SELECT DISTINCT device_type FROM device_shadows WHERE site_id=?", (site_id,)).fetchall()]
        # 查找匹配的配置
        configs = db.execute("""
            SELECT ic.*, it.template_name, it.category, it.frequency, it.description
            FROM inspection_configs ic
            JOIN inspection_templates it ON ic.template_id = it.id
            WHERE ic.site_type=? AND ic.is_active=1
            ORDER BY it.sort_order
        """, (site['type'],)).fetchall()
        result = []
        for cfg in configs:
            # 设备类型过滤（如果配置指定了device_types）
            cfg_dev = cfg['device_types']
            if cfg_dev and cfg_dev != '[]' and cfg_dev != '':
                try:
                    required = _json.loads(cfg_dev)
                    if required and not any(d in dev_types for d in required):
                        continue
                except:
                    pass
            # 获取模板检查项
            items = db.execute("""
                SELECT * FROM inspection_template_items WHERE template_id=? ORDER BY sort_order
            """, (cfg['template_id'],)).fetchall()
            result.append({
                'config_id': cfg['id'],
                'template_id': cfg['template_id'],
                'template_name': cfg['template_name'],
                'category': cfg['category'],
                'frequency': cfg['frequency'],
                'description': cfg['description'],
                'items': [dict(it) for it in items],
            })
        return jsonify({
            'site_id': site_id,
            'site_name': site['name'],
            'site_type': site['type'],
            'device_types': dev_types,
            'matched_templates': result,
            'total_items': sum(len(t['items']) for t in result),
        })

# --- 排程管理 ---

@app.route('/api/inspection-v2/schedules')
def v2_get_schedules():
    """获取排程列表"""
    site_id = request.args.get('site_id', type=int)
    status = request.args.get('status', '')  # due/upcoming/overdue
    user_id = request.args.get('user_id', type=int)
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    with get_db() as db:
        today = datetime.now().strftime('%Y-%m-%d')
        q = """
            SELECT s.*, st.name as site_name, st.type as site_type,
                   it.template_name, iti.item_name, iti.category as item_category,
                   iti.frequency_level, iti.photo_required
            FROM inspection_schedules s
            JOIN sites st ON s.site_id = st.id
            JOIN inspection_templates it ON s.template_id = it.id
            JOIN inspection_template_items iti ON s.template_item_id = iti.id
            WHERE s.status='active'
        """
        params = []
        if site_id:
            q += " AND s.site_id=?"
            params.append(site_id)
        if user_id:
            q += " AND s.site_id IN (SELECT site_id FROM user_sites WHERE user_id=?)"
            params.append(user_id)
        if status == 'due':
            q += " AND s.next_due_date<=?"
            params.append(today)
        elif status == 'overdue':
            q += " AND s.next_due_date<?"
            params.append(today)
        elif status == 'upcoming':
            q += " AND s.next_due_date>? AND s.next_due_date<=date(?, '+7 days')"
            params.extend([today, today])
        if date_from:
            q += " AND s.next_due_date>=?"
            params.append(date_from)
        if date_to:
            q += " AND s.next_due_date<=?"
            params.append(date_to)
        q += " ORDER BY s.next_due_date, st.name"
        rows = db.execute(q, params).fetchall()
        return jsonify([dict(r) for r in rows])

@app.route('/api/inspection-v2/schedules/init', methods=['POST'])
def v2_init_schedules():
    """重新初始化排程（根据当前配置）"""
    with get_db() as db:
        _init_v2_schedules(db)
        cnt = db.execute("SELECT COUNT(*) FROM inspection_schedules").fetchone()[0]
        return jsonify({'success': True, 'total_schedules': cnt})

@app.route('/api/inspection-v2/schedules/<int:sid>/complete', methods=['PUT'])
def v2_complete_schedule(sid):
    """标记排程完成并推进next_due_date"""
    data = request.get_json(silent=True) or {}
    freq_days = {'daily': 1, 'weekly': 7, 'monthly': 30, 'quarterly': 90, 'semi_annual': 180, 'annual': 365}
    now = datetime.now()
    with get_db() as db:
        sch = db.execute("SELECT * FROM inspection_schedules WHERE id=?", (sid,)).fetchone()
        if not sch:
            return jsonify({'error': '排程不存在'}), 404
        fd = freq_days.get(sch['frequency'], 30)
        new_due = (now + timedelta(days=fd)).strftime('%Y-%m-%d')
        db.execute("""
            UPDATE inspection_schedules
            SET last_completed_at=?, next_due_date=?, cycle_count=cycle_count+1
            WHERE id=?
        """, (now.strftime('%Y-%m-%d %H:%M:%S'), new_due, sid))
        db.commit()
        return jsonify({'success': True, 'next_due_date': new_due})

# --- 巡检计划 V2 ---

@app.route('/api/inspection-v2/plans')
def v2_get_plans():
    """获取巡检计划列表"""
    assignee_id = request.args.get('assignee_id', type=int)
    status = request.args.get('status', '')
    period = request.args.get('period', '')
    with get_db() as db:
        q = """
            SELECT p.*,
                   (SELECT COUNT(*) FROM insp_plan_items WHERE plan_id=p.id) as total_items,
                   (SELECT COUNT(*) FROM insp_plan_items WHERE plan_id=p.id AND result IS NOT NULL) as completed_items
            FROM insp_plans p WHERE 1=1
        """
        params = []
        if assignee_id:
            q += " AND p.assignee_id=?"
            params.append(assignee_id)
        if status:
            q += " AND p.status=?"
            params.append(status)
        if period:
            q += " AND p.period=?"
            params.append(period)
        q += " ORDER BY p.created_at DESC"
        rows = db.execute(q, params).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d['completion_rate'] = round(d['completed_items'] / d['total_items'] * 100, 1) if d['total_items'] > 0 else 0
            result.append(d)
        return jsonify(result)

@app.route('/api/inspection-v2/plans/generate', methods=['POST'])
def v2_generate_plans():
    """核心：根据排程生成巡检计划（按负责人打包）"""
    data = request.get_json(silent=True) or {}
    remind_days = data.get('remind_days', 1)
    today = datetime.now()
    today_str = today.strftime('%Y-%m-%d')
    cutoff = (today + timedelta(days=remind_days)).strftime('%Y-%m-%d')
    with get_db() as db:
        # 1. 获取所有到期/临近到期的排程
        schedules = db.execute("""
            SELECT s.*, st.name as site_name, st.type as site_type,
                   iti.item_name, iti.category as item_category
            FROM inspection_schedules s
            JOIN sites st ON s.site_id = st.id
            JOIN inspection_template_items iti ON s.template_item_id = iti.id
            WHERE s.status='active' AND s.next_due_date <= ?
            ORDER BY s.site_id, s.next_due_date
        """, (cutoff,)).fetchall()
        if not schedules:
            return jsonify({'success': True, 'plans_created': 0, 'message': '没有到期的检查项'})

        # 2. 获取负责人→站点映射
        operators = db.execute("SELECT id, real_name FROM users WHERE role IN ('operator','admin')").fetchall()
        user_site_map = {}  # user_id -> [site_ids]
        for op in operators:
            sites = db.execute("SELECT site_id FROM user_sites WHERE user_id=?", (op['id'],)).fetchall()
            user_site_map[op['id']] = {s['site_id'] for s in sites}
            user_site_map[op['real_name']] = {s['site_id'] for s in sites}

        # 3. 按站点分组排程
        site_schedules = {}
        for sch in schedules:
            sid = sch['site_id']
            if sid not in site_schedules:
                site_schedules[sid] = []
            site_schedules[sid].append(sch)

        # 4. 按负责人打包
        plans_created = 0
        total_items = 0
        for op in operators:
            op_name = op['real_name']
            op_sites = user_site_map.get(op['id'], set())
            # 该负责人管辖的到期站点
            due_sites = {sid for sid in site_schedules if sid in op_sites}
            if not due_sites:
                continue
            # 生成计划
            plan_name = f"{op_name}巡检计划-{today.strftime('%Y%m%d')}"
            db.execute("""
                INSERT INTO insp_plans (plan_name, assignee, assignee_id, period, generate_date, status)
                VALUES (?,?,?,?,?,?)
            """, (plan_name, op_name, op['id'], data.get('period', 'daily'), today_str, 'active'))
            plan_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            # 为该负责人的每个到期站点创建plan_items
            for sid in due_sites:
                for sch in site_schedules[sid]:
                    db.execute("""
                        INSERT INTO insp_plan_items (plan_id, site_id, schedule_id, template_id, item_name, category, frequency)
                        VALUES (?,?,?,?,?,?,?)
                    """, (plan_id, sid, sch['id'], sch['template_id'], sch['item_name'],
                          sch['item_category'], sch['frequency']))
                    total_items += 1
            plans_created += 1

        db.commit()
        return jsonify({
            'success': True,
            'plans_created': plans_created,
            'total_items': total_items,
            'due_sites': len(site_schedules),
            'date': today_str,
        })

@app.route('/api/inspection-v2/plans/<int:plan_id>')
def v2_get_plan_detail(plan_id):
    """获取巡检计划详情"""
    with get_db() as db:
        plan = db.execute("SELECT * FROM insp_plans WHERE id=?", (plan_id,)).fetchone()
        if not plan:
            return jsonify({'error': '计划不存在'}), 404
        items = db.execute("""
            SELECT pi.*, s.name as site_name, s.code as site_code
            FROM insp_plan_items pi
            JOIN sites s ON pi.site_id = s.id
            WHERE pi.plan_id=?
            ORDER BY pi.site_id, pi.id
        """, (plan_id,)).fetchall()
        result = dict(plan)
        result['items'] = [dict(it) for it in items]
        result['total_items'] = len(items)
        result['completed_items'] = sum(1 for it in items if it['result'] is not None)
        result['completion_rate'] = round(result['completed_items'] / result['total_items'] * 100, 1) if result['total_items'] > 0 else 0
        # 按站点分组
        site_groups = {}
        for it in items:
            sn = it['site_name']
            if sn not in site_groups:
                site_groups[sn] = {'site_id': it['site_id'], 'site_name': sn, 'items': []}
            site_groups[sn]['items'].append(dict(it))
        result['site_groups'] = list(site_groups.values())
        return jsonify(result)

@app.route('/api/inspection-v2/plans/<int:plan_id>', methods=['PUT'])
def v2_update_plan(plan_id):
    """更新巡检计划（添加/修改检查项）"""
    data = request.get_json(silent=True) or {}
    with get_db() as db:
        plan = db.execute("SELECT id, status FROM insp_plans WHERE id=?", (plan_id,)).fetchone()
        if not plan:
            return jsonify({'error': '计划不存在'}), 404
        # 更新计划字段
        for key in ('status', 'period'):
            if key in data:
                db.execute(f"UPDATE insp_plans SET {key}=? WHERE id=?", (data[key], plan_id))
        # 添加检查项
        if 'add_items' in data:
            for item in data['add_items']:
                db.execute("""
                    INSERT INTO insp_plan_items (plan_id,site_id,schedule_id,template_id,item_name,category,frequency)
                    VALUES (?,?,?,?,?,?,?)
                """, (plan_id, item.get('site_id'), item.get('schedule_id'), item.get('template_id'),
                      item.get('item_name',''), item.get('category',''), item.get('frequency','')))
        db.commit()
        return jsonify({'success': True})

@app.route('/api/inspection-v2/plans/<int:plan_id>', methods=['DELETE'])
def v2_delete_plan(plan_id):
    """删除巡检计划"""
    with get_db() as db:
        db.execute("DELETE FROM insp_plan_items WHERE plan_id=?", (plan_id,))
        db.execute("DELETE FROM insp_plans WHERE id=?", (plan_id,))
        db.commit()
        return jsonify({'success': True})

@app.route('/api/inspection-v2/plans/<int:plan_id>/items/<int:item_id>', methods=['PUT'])
def v2_update_plan_item(plan_id, item_id):
    """提交单个检查项结果"""
    data = request.get_json(silent=True) or {}
    now = datetime.now()
    with get_db() as db:
        item = db.execute("SELECT * FROM insp_plan_items WHERE id=? AND plan_id=?", (item_id, plan_id)).fetchone()
        if not item:
            return jsonify({'error': '检查项不存在'}), 404
        # 更新检查项结果
        fields = ["result=?", "check_time=?"]
        params = [data.get('result', 'normal'), now.strftime('%Y-%m-%d %H:%M:%S')]
        for key in ('photo_urls', 'gps_lat', 'gps_lng', 'remark', 'calibrator', 'calibration_values'):
            if key in data:
                fields.append(f"{key}=?")
                params.append(data[key])
        fields.append("completed_at=?")
        params.append(now.strftime('%Y-%m-%d %H:%M:%S'))
        params.extend([item_id, plan_id])
        db.execute(f"UPDATE insp_plan_items SET {','.join(fields)} WHERE id=? AND plan_id=?", params)
        # 如果异常，创建告警
        if data.get('result') == 'abnormal':
            create_alert_internal(db, item['site_id'], 'inspection', 0, 'yellow',
                f'巡检异常：{item["item_name"]}' + (f' - {data.get("remark","")}' if data.get("remark") else ''))
        # 如果关联了schedule_id，推进排程
        if item['schedule_id'] and data.get('result'):
            freq_days_map = {'daily': 1, 'weekly': 7, 'monthly': 30, 'quarterly': 90, 'semi_annual': 180, 'annual': 365}
            sch = db.execute("SELECT frequency FROM inspection_schedules WHERE id=?", (item['schedule_id'],)).fetchone()
            if sch:
                fd = freq_days_map.get(sch['frequency'], 30)
                new_due = (now + timedelta(days=fd)).strftime('%Y-%m-%d')
                db.execute("""
                    UPDATE inspection_schedules SET last_completed_at=?, next_due_date=?, cycle_count=cycle_count+1
                    WHERE id=?
                """, (now.strftime('%Y-%m-%d %H:%M:%S'), new_due, item['schedule_id']))
        # 检查计划是否全部完成
        total = db.execute("SELECT COUNT(*) FROM insp_plan_items WHERE plan_id=?", (plan_id,)).fetchone()[0]
        done = db.execute("SELECT COUNT(*) FROM insp_plan_items WHERE plan_id=? AND result IS NOT NULL", (plan_id,)).fetchone()[0]
        if total > 0 and done == total:
            db.execute("UPDATE insp_plans SET status='completed', completion_rate=100 WHERE id=?", (plan_id,))
            db.execute("""
                INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark)
                VALUES ('inspection_v2',?,  'completed','系统','巡检计划全部完成')
            """, (plan_id,))
        elif total > 0:
            rate = round(done / total * 100, 1)
            db.execute("UPDATE insp_plans SET completion_rate=? WHERE id=?", (rate, plan_id))
        db.commit()
        return jsonify({'success': True})

@app.route('/api/inspection-v2/plans/<int:plan_id>/stats')
def v2_plan_stats(plan_id):
    """计划统计"""
    with get_db() as db:
        plan = db.execute("SELECT * FROM insp_plans WHERE id=?", (plan_id,)).fetchone()
        if not plan:
            return jsonify({'error': '计划不存在'}), 404
        total = db.execute("SELECT COUNT(*) FROM insp_plan_items WHERE plan_id=?", (plan_id,)).fetchone()[0]
        done = db.execute("SELECT COUNT(*) FROM insp_plan_items WHERE plan_id=? AND result IS NOT NULL", (plan_id,)).fetchone()[0]
        normal = db.execute("SELECT COUNT(*) FROM insp_plan_items WHERE plan_id=? AND result='normal'", (plan_id,)).fetchone()[0]
        abnormal = db.execute("SELECT COUNT(*) FROM insp_plan_items WHERE plan_id=? AND result='abnormal'", (plan_id,)).fetchone()[0]
        sites = db.execute("SELECT COUNT(DISTINCT site_id) FROM insp_plan_items WHERE plan_id=?", (plan_id,)).fetchone()[0]
        return jsonify({
            'total_items': total, 'completed_items': done,
            'normal_count': normal, 'abnormal_count': abnormal,
            'site_count': sites,
            'completion_rate': round(done / total * 100, 1) if total > 0 else 0,
        })

@app.route('/api/inspection-v2/stats')
def v2_overall_stats():
    """总体统计"""
    today = datetime.now().strftime('%Y-%m-%d')
    with get_db() as db:
        total_schedules = db.execute("SELECT COUNT(*) FROM inspection_schedules WHERE status='active'").fetchone()[0]
        due_items = db.execute("SELECT COUNT(*) FROM inspection_schedules WHERE status='active' AND next_due_date<=?", (today,)).fetchone()[0]
        overdue_items = db.execute("SELECT COUNT(*) FROM inspection_schedules WHERE status='active' AND next_due_date<?", (today,)).fetchone()[0]
        upcoming_items = db.execute("""
            SELECT COUNT(*) FROM inspection_schedules
            WHERE status='active' AND next_due_date>? AND next_due_date<=date(?, '+7 days')
        """, (today, today)).fetchone()[0]
        total_plans = db.execute("SELECT COUNT(*) FROM insp_plans").fetchone()[0]
        active_plans = db.execute("SELECT COUNT(*) FROM insp_plans WHERE status='active'").fetchone()[0]
        completed_plans = db.execute("SELECT COUNT(*) FROM insp_plans WHERE status='completed'").fetchone()[0]
        total_templates = db.execute("SELECT COUNT(*) FROM inspection_templates WHERE status='active'").fetchone()[0]
        total_configs = db.execute("SELECT COUNT(*) FROM inspection_configs WHERE is_active=1").fetchone()[0]
        return jsonify({
            'total_schedules': total_schedules,
            'due_items': due_items,
            'overdue_items': overdue_items,
            'upcoming_items': upcoming_items,
            'total_plans': total_plans,
            'active_plans': active_plans,
            'completed_plans': completed_plans,
            'total_templates': total_templates,
            'total_configs': total_configs,
        })

# --- 提醒配置 ---

@app.route('/api/inspection-v2/reminders')
def v2_get_reminders():
    """获取提醒配置"""
    with get_db() as db:
        rows = db.execute("SELECT * FROM inspection_reminders").fetchall()
        return jsonify([dict(r) for r in rows] if rows else [{'remind_days_before': 1, 'remind_method': 'notification',
                 'overdue_escalation': 0, 'escalation_days': 3, 'is_active': 1}])

@app.route('/api/inspection-v2/reminders', methods=['PUT'])
def v2_update_reminders():
    """更新提醒配置"""
    data = request.get_json(silent=True) or {}
    with get_db() as db:
        existing = db.execute("SELECT id FROM inspection_reminders LIMIT 1").fetchone()
        if existing:
            fields = []
            params = []
            for key in ('remind_days_before', 'remind_method', 'overdue_escalation', 'escalation_days', 'is_active'):
                if key in data:
                    fields.append(f"{key}=?")
                    params.append(data[key])
            if fields:
                params.append(existing['id'])
                db.execute(f"UPDATE inspection_reminders SET {','.join(fields)} WHERE id=?", params)
        else:
            db.execute("""
                INSERT INTO inspection_reminders (remind_days_before,remind_method,overdue_escalation,escalation_days,is_active)
                VALUES (?,?,?,?,?)
            """, (data.get('remind_days_before', 1), data.get('remind_method', 'notification'),
                  data.get('overdue_escalation', 0), data.get('escalation_days', 3), 1))
        db.commit()
        return jsonify({'success': True})

@app.route('/api/inspection-v2/reminders/pending')
def v2_pending_reminders():
    """获取待提醒列表"""
    today = datetime.now()
    with get_db() as db:
        cfg = db.execute("SELECT * FROM inspection_reminders WHERE is_active=1 LIMIT 1").fetchone()
        if not cfg:
            return jsonify([])
        remind_days = cfg['remind_days_before']
        cutoff = (today + timedelta(days=remind_days)).strftime('%Y-%m-%d')
        today_str = today.strftime('%Y-%m-%d')
        # 到期+逾期的排程
        rows = db.execute("""
            SELECT s.*, st.name as site_name, iti.item_name,
                   CASE WHEN s.next_due_date < ? THEN 'overdue' ELSE 'due' END as urgency
            FROM inspection_schedules s
            JOIN sites st ON s.site_id = st.id
            JOIN inspection_template_items iti ON s.template_item_id = iti.id
            WHERE s.status='active' AND s.next_due_date <= ?
            ORDER BY s.next_due_date
        """, (today_str, cutoff)).fetchall()
        return jsonify([dict(r) for r in rows])

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
        # 检查是否有今天的数据，没有则尝试从sensor_data实时计算
        has_data = db.execute("SELECT COUNT(*) as c FROM data_arrival WHERE date=?", (date,)).fetchone()['c']
        if has_data == 0:
            # 回退：从sensor_data统计今天的到报情况
            rows = db.execute("""
                SELECT s.type as metric, 
                    COUNT(DISTINCT sd.site_id) as site_count,
                    ROUND(AVG(CASE WHEN sd.id IS NOT NULL THEN 100.0 ELSE 0 END),1) as avg_rate,
                    0 as below_threshold
                FROM sites s
                LEFT JOIN sensor_data sd ON s.id = sd.site_id AND sd.recorded_at >= ?
                GROUP BY s.type
            """, (date + ' 00:00:00',)).fetchall()
            # 如果回退也无数据，返回空
            if not rows or all((r['avg_rate'] or 0) == 0 for r in rows):
                return jsonify({'total_avg': 0, 'by_metric': []})
            total_avg = round(sum(r['avg_rate'] or 0 for r in rows) / max(len(rows), 1), 1)
            return jsonify({
                'total_avg': total_avg,
                'by_metric': [dict(r) for r in rows]
            })
        total = db.execute("SELECT AVG(arrival_rate) as avg FROM data_arrival WHERE date=?", (date,)).fetchone()
        rows = db.execute("""
            SELECT da.metric,
                COUNT(da.site_id) as site_count,
                ROUND(AVG(da.arrival_rate),1) as avg_rate,
                0 as below_threshold
            FROM data_arrival da
            WHERE da.date=?
            GROUP BY da.metric
        """, (date,)).fetchall()
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

        # === 数据自洽性修复：尝试根据位置匹配站点 ===
        site_id = data.get('site_id')
        if not site_id and event.get('location'):
            loc = event['location']
            site_row = db.execute(
                "SELECT id FROM sites WHERE name LIKE ? OR district LIKE ? LIMIT 1",
                (f'%{loc}%', f'%{loc}%')
            ).fetchone()
            if site_row:
                site_id = site_row['id']

        db.execute("""
            INSERT INTO work_orders (order_no,site_id,source,event_type,level,title,description,assignee,status,sla_deadline)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (order_no, site_id, 'hotline', event['event_type'], leve,
              f"[热线]{event['event_type']}", event['description'],
              data.get('assignee',''), 'pending', sla_deadline))
        # 更新热线事件：设置状态、关联工单号、站点ID
        db.execute("UPDATE hotline_events SET status='dispatched', related_order_no=?, site_id=? WHERE id=?",
                   (order_no, site_id, event_id))
        db.commit()
        return jsonify({'success': True, 'order_no': order_no})

# --- Dashboard ---
@app.route('/api/dashboard/summary')
@login_required
def dashboard_summary():
    """全系统统一数据源——返回所有面板需要的计数和状态"""
    with get_db() as db:
        # 告警按状态计数
        pending = db.execute("SELECT COUNT(*) FROM alerts WHERE status='pending'").fetchone()[0]
        acknowledged = db.execute("SELECT COUNT(*) FROM alerts WHERE status='acknowledged'").fetchone()[0]
        resolved = db.execute("SELECT COUNT(*) FROM alerts WHERE status='resolved'").fetchone()[0]
        total_alerts = pending + acknowledged + resolved

        # 告警按级别计数（仅活跃告警）
        alert_by_level = {}
        for lv in ['red','orange','yellow']:
            alert_by_level[lv] = db.execute("SELECT COUNT(*) FROM alerts WHERE level=? AND status IN ('pending','acknowledged')", (lv,)).fetchone()[0]

        # 告警按类型计数（仅活跃）
        alert_by_type = {
            'data_quality': db.execute("SELECT COUNT(*) FROM alerts WHERE metric IN ('data_gap','data_freeze','data_spike') AND status IN ('pending','acknowledged')").fetchone()[0],
            'device_status': db.execute("SELECT COUNT(*) FROM alerts WHERE metric='device_status' AND status IN ('pending','acknowledged')").fetchone()[0],
        }
        alert_by_type['ops_timeliness'] = total_alerts - alert_by_type['data_quality'] - alert_by_type['device_status'] - resolved

        # 今日新增告警
        today_new = db.execute("SELECT COUNT(*) FROM alerts WHERE date(created_at)=date('now','localtime')").fetchone()[0]

        # 告警站点数（有活跃告警的站点）
        alert_sites = db.execute("SELECT COUNT(DISTINCT site_id) FROM alerts WHERE status IN ('pending','acknowledged')").fetchone()[0]

        # 站点状态
        sites_online = db.execute("SELECT COUNT(*) FROM sites WHERE status='online'").fetchone()[0]
        sites_offline = db.execute("SELECT COUNT(*) FROM sites WHERE status='offline'").fetchone()[0]
        sites_with_alerts = alert_sites

        # 工单状态分布
        wo_by_status = {}
        for st in ['pending','accepted','generated','dispatched','in_progress','reviewing','acceptance','closed']:
            wo_by_status[st] = db.execute("SELECT COUNT(*) FROM work_orders WHERE status=?",(st,)).fetchone()[0]

        # 今日工单
        today_wo = db.execute("SELECT COUNT(*) FROM work_orders WHERE date(created_at)=date('now','localtime')").fetchone()[0]
        today_closed = db.execute("SELECT COUNT(*) FROM work_orders WHERE date(resolved_at)=date('now','localtime')").fetchone()[0]

        # 数据到达
        arrival_row = db.execute("SELECT AVG(arrival_rate) FROM data_arrival WHERE date=(SELECT MAX(date) FROM data_arrival)").fetchone()
        arrival = arrival_row[0] if arrival_row and arrival_row[0] is not None else 0

        # 巡检
        insp_total = db.execute("SELECT COUNT(*) FROM inspection_tasks").fetchone()[0]
        insp_done = db.execute("SELECT COUNT(*) FROM inspection_tasks WHERE result IS NOT NULL").fetchone()[0]

        # 按metric分类的告警详情（预警中心分类卡片用）
        alerts_detail = list(db.execute("""
            SELECT metric, level, status, COUNT(*) as cnt
            FROM alerts WHERE status IN ('pending','acknowledged')
            GROUP BY metric, level, status
        """))

        # 最新告警TOP5
        latest_alerts = db.execute("""
            SELECT a.*, s.name as site_name FROM alerts a LEFT JOIN sites s ON a.site_id=s.id
            WHERE a.status='pending' ORDER BY CASE level WHEN 'red' THEN 1 WHEN 'orange' THEN 2 ELSE 3 END, a.created_at DESC LIMIT 5
        """).fetchall()

        # 待处理工单TOP5
        pending_orders = db.execute("""
            SELECT w.*, s.name as site_name FROM work_orders w LEFT JOIN sites s ON w.site_id=s.id
            WHERE w.status NOT IN ('closed') ORDER BY w.created_at DESC LIMIT 5
        """).fetchall()

        return jsonify({
            'alerts': {
                'total': total_alerts,
                'pending': pending,
                'acknowledged': acknowledged,
                'resolved': resolved,
                'by_level': alert_by_level,
                'by_type': alert_by_type,
                'today_new': today_new,
                'alert_sites': alert_sites,
                'detail': [dict(r) for r in alerts_detail],
            },
            'sites': {
                'total': sites_online + sites_offline,
                'online': sites_online,
                'offline': sites_offline,
                'with_alerts': sites_with_alerts,
            },
            'workorders': {
                'total': sum(wo_by_status.values()),
                'by_status': wo_by_status,
                'today_new': today_wo,
                'today_closed': today_closed,
            },
            'inspections': {
                'total': insp_total,
                'completed': insp_done,
            },
            'arrival_rate': round(arrival, 1),
            # 兼容旧版字段
            'overview': {
                'total_sites': sites_online + sites_offline,
                'online_sites': sites_online,
                'device_total': 0,
                'device_online': 0,
                'active_alerts': pending,
                'open_orders': sum(wo_by_status.values()) - wo_by_status.get('closed', 0),
                'today_orders': today_wo,
            },
            'latest_alerts': [dict(a) for a in latest_alerts],
            'pending_orders': [dict(o) for o in pending_orders],
        })

# --- 实时天气获取 ---
# 默认坐标：南昌（可修改为项目所在地）
WEATHER_LAT = 28.68
WEATHER_LON = 115.89

def fetch_real_weather():
    """从 Open-Meteo 免费接口获取实时天气，写入数据库"""
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={WEATHER_LAT}&longitude={WEATHER_LON}"
        f"&current=temperature_2m,relative_humidity_2m,precipitation,pressure_msl,"
        f"wind_speed_10m,wind_direction_10m,weather_code"
        f"&timezone=auto"
    )
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'WaterOps/1.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read().decode())
    except Exception as e:
        print(f"[Weather] 获取天气失败: {e}")
        return False

    current = data.get('current', {})
    if not current:
        return False

    # WMO 天气代码 → 中文天气类型
    wmo_map = {
        0:'晴',1:'晴',2:'多云',3:'阴',45:'雾',48:'雾',
        51:'小雨',53:'小雨',55:'中雨',56:'冻雨',57:'冻雨',
        61:'小雨',63:'中雨',65:'大雨',66:'冻雨',67:'冻雨',
        71:'小雪',73:'中雪',75:'大雪',77:'雪粒',
        80:'阵雨',81:'中雨',82:'大雨',85:'阵雪',86:'阵雪',
        95:'雷雨',96:'雷雨',99:'雷雨'
    }
    wcode = current.get('weather_code', 0)
    weather_type = wmo_map.get(wcode, '多云')

    # 温度(°C), 湿度(%), 降水量(mm), 气压(hPa), 风速(km/h)
    temp = current.get('temperature_2m', 25)
    humidity = current.get('relative_humidity_2m', 60)
    precip = current.get('precipitation', 0)
    pressure = current.get('pressure_msl', 1013)
    wind_speed = current.get('wind_speed_10m', 5)
    wind_dir_deg = current.get('wind_direction_10m', 0)

    # 风向角度 → 中文
    dirs = ['北','东北','东','东南','南','西南','西','西北']
    wind_dir = dirs[round(wind_dir_deg / 45) % 8]

    # 生成预警信息
    warnings = []
    if precip > 10: warnings.append('暴雨')
    if wind_speed > 40: warnings.append('大风')
    if temp > 35: warnings.append('高温')

    with get_db() as db:
        # 清理旧数据，只保留最新一条
        db.execute("DELETE FROM weather_data WHERE id NOT IN (SELECT id FROM weather_data ORDER BY id DESC LIMIT 1)")
        db.execute(
            """INSERT INTO weather_data (temperature,humidity,wind_speed,wind_direction,
               precipitation,pressure,weather_type,warning_info,recorded_at)
               VALUES (?,?,?,?,?,?,?,?,datetime('now','localtime'))""",
            (temp, humidity, wind_speed, wind_dir, precip, pressure, weather_type,
             ','.join(warnings) if warnings else '')
        )
        db.commit()
    print(f"[Weather] 已更新: {weather_type} {temp}°C 降水{precip}mm 风速{wind_speed}km/h")
    return True

# --- 天气数据 ---
@app.route('/api/weather')
def get_weather():
    """返回当前天气数据、未来24小时逐时预报、天气预警"""
    with get_db() as db:
        # 获取最新天气记录
        current = db.execute(
            "SELECT * FROM weather_data ORDER BY recorded_at DESC LIMIT 1"
        ).fetchone()

        # 无数据或数据超过5分钟 → 刷新（确保移动端/PC端看到一致的最新数据）
        need_fetch = False
        if not current:
            need_fetch = True
        else:
            try:
                from datetime import datetime as _dt
                last = _dt.strptime(current['recorded_at'], '%Y-%m-%d %H:%M:%S')
                if (_dt.now() - last).total_seconds() > 300:  # 5分钟
                    need_fetch = True
            except:
                need_fetch = True

        if need_fetch:
            fetch_real_weather()
            # 重新读取
            current = db.execute(
                "SELECT * FROM weather_data ORDER BY recorded_at DESC LIMIT 1"
            ).fetchone()

        if not current:
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
@login_required
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


# ===================== 认证API端点 =====================

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data = request.get_json(silent=True) or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    if not username or not password:
        return jsonify({'error': '请输入用户名和密码'}), 400
    with get_db() as db:
        user = db.execute("SELECT id, username, password_hash, role, real_name, phone, status FROM users WHERE username=? AND status='active'",
                          (username,)).fetchone()
    if not user or user['password_hash'] != _hash_pw(password):
        return jsonify({'error': '用户名或密码错误'}), 401
    token = secrets.token_urlsafe(32)
    _tokens[token] = {
        'id': user['id'],
        'username': user['username'],
        'role': user['role'],
        'real_name': user['real_name'],
        'phone': user['phone'] or '',
    }
    # 获取此用户可管理的站点列表
    with get_db() as db:
        site_rows = db.execute("SELECT s.id, s.name, s.code, s.type FROM sites s JOIN user_sites us ON s.id=us.site_id WHERE us.user_id=?", (user['id'],)).fetchall()
    sites = [{'id': r['id'], 'name': r['name'], 'code': r['code'], 'type': r['type']} for r in site_rows]
    return jsonify({
        'success': True,
        'token': token,
        'user': {
            'id': user['id'],
            'username': user['username'],
            'role': user['role'],
            'real_name': user['real_name'],
            'phone': user['phone'] or '',
        },
        'sites_count': len(sites),
        'sites': sites,
    })

@app.route('/api/auth/me')
@login_required
def api_me():
    return jsonify({
        'success': True,
        'user': g.current_user,
        'site_ids': g.user_site_ids,
    })


# ===================== 用户管理API（管理员） =====================

@app.route('/api/users')
@login_required
def api_users():
    if g.current_user['role'] != 'admin':
        return jsonify({'error': '无权限'}), 403
    with get_db() as db:
        rows = db.execute("SELECT id, username, role, real_name, phone, status, created_at FROM users ORDER BY id").fetchall()
    users = []
    for r in rows:
        with get_db() as db2:
            cnt = db2.execute("SELECT COUNT(*) as c FROM user_sites WHERE user_id=?", (r['id'],)).fetchone()['c']
        users.append({
            'id': r['id'], 'username': r['username'], 'role': r['role'],
            'real_name': r['real_name'], 'phone': r['phone'] or '',
            'status': r['status'], 'sites_count': cnt,
            'created_at': r['created_at'],
        })
    return jsonify(users)

@app.route('/api/assignees')
@login_required
def api_assignees():
    """返回可用负责人名单（用于B级预警复核转工单下拉选择）"""
    with get_db() as db:
        rows = db.execute("SELECT id, real_name, role FROM users ORDER BY real_name").fetchall()
    return jsonify([{'id': r['id'], 'name': r['real_name'], 'role': r['role']} for r in rows])

@app.route('/api/users/<int:uid>/sites', methods=['GET'])
@login_required
def api_user_sites(uid):
    if g.current_user['role'] != 'admin':
        return jsonify({'error': '无权限'}), 403
    with get_db() as db:
        sids = [r['site_id'] for r in db.execute("SELECT site_id FROM user_sites WHERE user_id=?", (uid,)).fetchall()]
    return jsonify({'site_ids': sids})

@app.route('/api/users/<int:uid>/sites', methods=['PUT'])
@login_required
def api_update_user_sites(uid):
    if g.current_user['role'] != 'admin':
        return jsonify({'error': '无权限'}), 403
    data = request.get_json(silent=True) or {}
    site_ids = data.get('site_ids', [])
    if not isinstance(site_ids, list):
        return jsonify({'error': 'site_ids格式错误'}), 400
    with get_db() as db:
        db.execute("DELETE FROM user_sites WHERE user_id=?", (uid,))
        for sid in site_ids:
            db.execute("INSERT OR IGNORE INTO user_sites (user_id,site_id) VALUES (?,?)", (uid, sid))
        db.commit()
    return jsonify({'success': True, 'count': len(site_ids)})

@app.route('/api/users/<int:uid>/reset-password', methods=['PUT'])
@login_required
def api_reset_password(uid):
    if g.current_user['role'] != 'admin':
        return jsonify({'error': '无权限'}), 403
    data = request.get_json(silent=True) or {}
    new_pw = data.get('new_password', 'yw123456')
    with get_db() as db:
        db.execute("UPDATE users SET password_hash=? WHERE id=?", (_hash_pw(new_pw), uid))
        db.commit()
    return jsonify({'success': True})

@app.route('/api/users/<int:uid>/status', methods=['PUT'])
@login_required
def api_user_status(uid):
    if g.current_user['role'] != 'admin':
        return jsonify({'error': '无权限'}), 403
    data = request.get_json(silent=True) or {}
    new_status = data.get('status', 'active')
    with get_db() as db:
        db.execute("UPDATE users SET status=? WHERE id=?", (new_status, uid))
        db.commit()
    return jsonify({'success': True})


# ===================== 设备管理 API =====================

@app.route('/api/devices')
@login_required
def api_devices_list():
    """设备台账列表，支持按站点/类型/状态筛选"""
    site_id = request.args.get('site_id', '').strip()
    device_type = request.args.get('type', '').strip()
    status = request.args.get('status', '').strip()
    search = request.args.get('search', '').strip()
    with get_db() as db:
        sql = """SELECT d.id, d.device_code, d.device_name, d.device_type, d.device_model, d.manufacturer, d.install_date,
                        d.status, d.battery, d.voltage,
                        COALESCE(d.last_data_time, (SELECT MAX(recorded_at) FROM sensor_data WHERE site_id=d.site_id)) as last_data_time,
                        s.name as site_name, s.code as site_code, s.id as site_id
                 FROM device_shadows d LEFT JOIN sites s ON d.site_id=s.id WHERE 1=1"""
        params = []
        if site_id:
            sql += " AND d.site_id=?"
            params.append(site_id)
        if device_type:
            sql += " AND d.device_type=?"
            params.append(device_type)
        if status:
            if status == 'low_voltage':
                sql += " AND d.status='online' AND (d.voltage < 11.8 OR d.voltage IS NULL)"
            elif status == 'normal':
                sql += " AND d.status='online' AND (d.voltage >= 11.8 OR d.voltage IS NULL)"
            else:
                sql += " AND d.status=?"
                params.append(status)
        if search:
            sql += " AND (d.device_name LIKE ? OR d.device_code LIKE ? OR s.name LIKE ?)"
            like = f"%{search}%"
            params.extend([like, like, like])
        sql += " ORDER BY CASE WHEN d.status='offline' THEN 0 WHEN d.status='online' AND (d.voltage < 11.8 OR d.voltage IS NULL) THEN 1 ELSE 2 END, d.id"
        rows = db.execute(sql, params).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/devices/<int:device_id>')
@login_required
def api_device_detail(device_id):
    """设备详情 + 维护记录"""
    with get_db() as db:
        dev = db.execute("""SELECT d.*, s.name as site_name, s.code as site_code,
                                   s.district, s.manager
                            FROM device_shadows d LEFT JOIN sites s ON d.site_id=s.id
                            WHERE d.id=?""", (device_id,)).fetchone()
        if not dev:
            return jsonify({'error': '设备不存在'}), 404
        logs = db.execute("""SELECT * FROM inventory_logs
                             WHERE ref_type='maintenance' AND ref_id=?
                             ORDER BY created_at DESC LIMIT 20""", (device_id,)).fetchall()
    return jsonify({'device': dict(dev), 'logs': [dict(l) for l in logs]})


@app.route('/api/devices', methods=['POST'])
@login_required
def api_device_create():
    """注册新设备"""
    data = request.get_json(force=True)
    device_code = (data.get('device_code') or '').strip()
    device_name = (data.get('device_name') or '').strip()
    device_type = (data.get('device_type') or '').strip()
    site_id = data.get('site_id')
    status = data.get('status') or 'online'
    voltage = data.get('voltage')
    battery = data.get('battery')

    if not device_code or not device_name:
        return jsonify({'error': '设备编码和名称不能为空'}), 400

    with get_db() as db:
        # 检查编码唯一性
        existing = db.execute("SELECT id FROM device_shadows WHERE device_code=?", (device_code,)).fetchone()
        if existing:
            return jsonify({'error': '设备编码已存在'}), 409
        cur = db.execute(
            """INSERT INTO device_shadows (device_code, device_name, device_type, site_id, status, voltage, battery)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (device_code, device_name, device_type, site_id, status, voltage, battery)
        )
        new_id = cur.lastrowid
    return jsonify({'success': True, 'id': new_id, 'message': '设备注册成功'})


@app.route('/api/devices/<int:device_id>', methods=['PUT'])
@login_required
def api_device_update(device_id):
    """编辑设备信息"""
    data = request.get_json(force=True)
    with get_db() as db:
        dev = db.execute("SELECT id FROM device_shadows WHERE id=?", (device_id,)).fetchone()
        if not dev:
            return jsonify({'error': '设备不存在'}), 404

        fields = []
        values = []
        for col in ['device_code', 'device_name', 'device_type', 'site_id', 'status', 'voltage', 'battery']:
            if col in data:
                fields.append(f"{col}=?")
                values.append(data[col])
        if not fields:
            return jsonify({'error': '没有可更新的字段'}), 400

        # 如果修改了编码，检查唯一性
        if 'device_code' in data:
            dup = db.execute("SELECT id FROM device_shadows WHERE device_code=? AND id!=?",
                             (data['device_code'], device_id)).fetchone()
            if dup:
                return jsonify({'error': '设备编码已存在'}), 409

        values.append(device_id)
        db.execute(f"UPDATE device_shadows SET {', '.join(fields)} WHERE id=?", values)
    return jsonify({'success': True, 'message': '设备信息已更新'})


@app.route('/api/devices/<int:device_id>', methods=['DELETE'])
@login_required
def api_device_delete(device_id):
    """删除设备（软删除：移入回收记录）"""
    with get_db() as db:
        dev = db.execute("SELECT * FROM device_shadows WHERE id=?", (device_id,)).fetchone()
        if not dev:
            return jsonify({'error': '设备不存在'}), 404
        # 写入回收记录
        site = db.execute("SELECT name FROM sites WHERE id=?", (dev['site_id'],)).fetchone()
        db.execute(
            """INSERT INTO device_recycle (device_code, device_name, device_type, site_name, site_id, reason, status, created_at)
               VALUES (?, ?, ?, ?, ?, '前端删除', 'pending', datetime('now','localtime'))""",
            (dev['device_code'], dev['device_name'], dev.get('device_type') or '', site['name'] if site else '', dev['site_id'])
        )
        # 删除设备
        db.execute("DELETE FROM device_shadows WHERE id=?", (device_id,))
    return jsonify({'success': True, 'message': '设备已删除'})


# --- 设备回收 ---

@app.route('/api/device-recycle')
@login_required
def api_device_recycle_list():
    """设备回收记录列表，支持按设备/站点搜索"""
    search = request.args.get('search', '').strip()
    status = request.args.get('status', '').strip()
    with get_db() as db:
        sql = "SELECT * FROM device_recycle WHERE 1=1"
        params = []
        if search:
            sql += " AND (device_code LIKE ? OR device_name LIKE ? OR site_name LIKE ? OR destination LIKE ?)"
            like = f"%{search}%"
            params.extend([like, like, like, like])
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY created_at DESC"
        rows = db.execute(sql, params).fetchall()
        records = [dict(r) for r in rows]

        # 若无真实记录，生成模拟数据
        if not records:
            records = _generate_mock_recycle_records()

        return jsonify(records)

@app.route('/api/device-recycle', methods=['POST'])
@login_required
def api_device_recycle_create():
    """登记设备回收"""
    data = request.get_json(silent=True) or {}
    with get_db() as db:
        # 验证设备是否存在
        device_id = data.get('device_id')
        device = db.execute("SELECT * FROM device_shadows WHERE id=?", (device_id,)).fetchone()
        if not device:
            return jsonify({'error': '设备不存在'}), 404
        # 插入回收记录
        site = db.execute("SELECT name FROM sites WHERE id=?", (device['site_id'],)).fetchone()
        db.execute("""
            INSERT INTO device_recycle (device_id, device_code, device_name, device_type,
                site_id, site_name, recycle_date, reason, destination, operator, remark, status, work_order_no)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (device_id, device['device_code'], device['device_name'], device['device_type'],
              device['site_id'], site['name'] if site else '',
              data.get('recycle_date', ''), data.get('reason', ''),
              data.get('destination', ''), data.get('operator', ''),
              data.get('remark', ''), data.get('status', 'recycled'),
              data.get('work_order_no', '')))
        # 同时将设备状态设为 offline（已回收）
        db.execute("UPDATE device_shadows SET status='offline' WHERE id=?", (device_id,))
        # 记录时间线事件
        db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                   ('device', device_id, 'recycled', data.get('operator', '系统'),
                    f'设备回收-{device["device_name"]}({device["device_code"]})->{data.get("destination","")}'))
        db.commit()
        return jsonify({'success': True})

@app.route('/api/device-recycle/<int:rec_id>', methods=['PUT'])
@login_required
def api_device_recycle_update(rec_id):
    """更新回收记录（如去向变更）"""
    data = request.get_json(silent=True) or {}
    with get_db() as db:
        fields = []
        params = []
        for f in ['destination', 'remark', 'status', 'reason', 'operator']:
            if f in data:
                fields.append(f"{f}=?")
                params.append(data[f])
        if fields:
            params.append(rec_id)
            db.execute(f"UPDATE device_recycle SET {','.join(fields)} WHERE id=?", params)
            db.commit()
        return jsonify({'success': True})


# --- 备件库存 ---

@app.route('/api/parts/inventory')
@login_required
def api_parts_inventory():
    """备件库存列表"""
    category = request.args.get('category', '').strip()
    low = request.args.get('low', '').strip()
    search = request.args.get('search', '').strip()
    with get_db() as db:
        sql = """SELECT p.*, s.name as site_name
                 FROM spare_parts_inventory p LEFT JOIN sites s ON p.site_id=s.id WHERE 1=1"""
        params = []
        if category:
            sql += " AND p.category=?"
            params.append(category)
        if low == '1':
            sql += " AND p.quantity <= p.min_quantity"
        if search:
            sql += " AND (p.part_name LIKE ? OR p.part_code LIKE ?)"
            like = f"%{search}%"
            params.extend([like, like])
        sql += " ORDER BY p.quantity ASC"
        rows = db.execute(sql, params).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/parts/inventory', methods=['POST'])
@login_required
def api_parts_inventory_add():
    """新增备件或入库"""
    data = request.get_json(silent=True) or {}
    part_code = data.get('part_code', '').strip()
    part_name = data.get('part_name', '').strip()
    category = data.get('category', '其他').strip()
    unit = data.get('unit', '个').strip()
    quantity = int(data.get('quantity', 1))
    min_quantity = int(data.get('min_quantity', 5))
    site_id = data.get('site_id')
    remark = data.get('remark', '').strip()
    if not part_name:
        return jsonify({'error': '备件名称不能为空'}), 400
    if not part_code:
        import uuid
        part_code = f"BJ-{uuid.uuid4().hex[:6].upper()}"
    with get_db() as db:
        cur = db.execute("""INSERT INTO spare_parts_inventory
            (part_code,part_name,category,unit,quantity,min_quantity,site_id,remark)
            VALUES (?,?,?,?,?,?,?,?)""",
            (part_code, part_name, category, unit, quantity, min_quantity, site_id, remark))
        pid = cur.lastrowid
        db.execute("""INSERT INTO inventory_logs (part_id,type,quantity,ref_type,operator,remark)
            VALUES (?,'in',?,'purchase',?,?)""",
            (pid, quantity, g.current_user['username'] or 'admin', f'入库: {part_name}'))
        db.commit()
    return jsonify({'success': True, 'id': pid, 'part_code': part_code})


@app.route('/api/parts/inventory/<int:pid>', methods=['PUT'])
@login_required
def api_parts_inventory_update(pid):
    """更新备件信息或手动出库"""
    data = request.get_json(silent=True) or {}
    with get_db() as db:
        part = db.execute("SELECT * FROM spare_parts_inventory WHERE id=?", (pid,)).fetchone()
        if not part:
            return jsonify({'error': '备件不存在'}), 404
        # 出库操作
        if 'out_qty' in data:
            qty = int(data['out_qty'])
            if qty <= 0:
                return jsonify({'error': '出库数量需大于0'}), 400
            if part['quantity'] - qty < 0:
                return jsonify({'error': '库存不足'}), 400
            db.execute("UPDATE spare_parts_inventory SET quantity=quantity-?, updated_at=datetime('now','localtime') WHERE id=?", (qty, pid))
            remark_out = data.get('remark', '').strip() or '手动出库'
            db.execute("""INSERT INTO inventory_logs (part_id,type,quantity,ref_type,operator,remark)
                VALUES (?,'out',?,'adjust',?,?)""",
                (pid, qty, g.current_user['username'] or 'admin', remark_out))
        # 入库操作
        if 'in_qty' in data:
            qty = int(data['in_qty'])
            if qty <= 0:
                return jsonify({'error': '入库数量需大于0'}), 400
            db.execute("UPDATE spare_parts_inventory SET quantity=quantity+?, updated_at=datetime('now','localtime') WHERE id=?", (qty, pid))
            remark_in = data.get('remark', '').strip() or '手动入库'
            db.execute("""INSERT INTO inventory_logs (part_id,type,quantity,ref_type,operator,remark)
                VALUES (?,'in',?,'purchase',?,?)""",
                (pid, qty, g.current_user['username'] or 'admin', remark_in))
        # 更新基本信息
        for field in ['part_name', 'category', 'unit', 'min_quantity', 'remark']:
            if field in data:
                db.execute(f"UPDATE spare_parts_inventory SET {field}=? WHERE id=?", (data[field], pid))
        db.commit()
    return jsonify({'success': True})


@app.route('/api/parts/inventory/<int:pid>/logs')
@login_required
def api_parts_inventory_logs(pid):
    """备件库存变更流水"""
    with get_db() as db:
        rows = db.execute("""SELECT * FROM inventory_logs WHERE part_id=? ORDER BY created_at DESC LIMIT 50""", (pid,)).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/parts/inventory/<int:pid>/stock', methods=['POST'])
@login_required
def api_parts_inventory_stock(pid):
    """备件入库/出库操作"""
    data = request.get_json(silent=True) or {}
    stock_type = data.get('type', '')  # 'in' or 'out'
    quantity = int(data.get('quantity', 0))
    reason = data.get('reason', '').strip()
    operator = data.get('operator', '').strip() or g.current_user.get('username', 'unknown')
    work_order_no = data.get('work_order_no', '').strip()
    if stock_type not in ('in', 'out'):
        return jsonify({'error': '操作类型必须为 in 或 out'}), 400
    if quantity <= 0:
        return jsonify({'error': '数量必须大于0'}), 400
    with get_db() as db:
        part = db.execute("SELECT * FROM spare_parts_inventory WHERE id=?", (pid,)).fetchone()
        if not part:
            return jsonify({'error': '备件不存在'}), 404
        if stock_type == 'out' and part['quantity'] < quantity:
            return jsonify({'error': f"库存不足，当前库存 {part['quantity']}"}), 400
        # 更新库存
        if stock_type == 'in':
            db.execute("UPDATE spare_parts_inventory SET quantity=quantity+?, updated_at=datetime('now','localtime') WHERE id=?", (quantity, pid))
        else:
            db.execute("UPDATE spare_parts_inventory SET quantity=quantity-?, updated_at=datetime('now','localtime') WHERE id=?", (quantity, pid))
        # 记录流水
        db.execute("""INSERT INTO inventory_logs (part_id,type,quantity,ref_type,operator,remark,work_order_no)
            VALUES (?,?,?, 'stock', ?, ?, ?)""",
            (pid, stock_type, quantity, operator, reason, work_order_no))
        db.commit()
    return jsonify({'success': True, 'message': f"{'入库' if stock_type == 'in' else '出库'}成功"})


# --- 备件申请 ---

@app.route('/api/parts/requests', methods=['GET'])
@login_required
def api_parts_requests_list():
    """备件申请列表（Web端：全部；移动端按申请人过滤）"""
    status_f = request.args.get('status', '').strip()
    applicant = request.args.get('applicant', '').strip()
    with get_db() as db:
        sql = """SELECT r.*, s.name as site_name
                 FROM spare_part_requests r LEFT JOIN sites s ON r.site_id=s.id WHERE 1=1"""
        params = []
        if status_f:
            sql += " AND r.status=?"
            params.append(status_f)
        if applicant:
            sql += " AND r.applicant=?"
            params.append(applicant)
        sql += " ORDER BY r.created_at DESC"
        rows = db.execute(sql, params).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/parts/requests', methods=['POST'])
@login_required
def api_parts_requests_create():
    """创建备件申请（移动端调用）"""
    data = request.get_json(silent=True) or {}
    site_id = data.get('site_id')
    part_name = data.get('part_name', '').strip()
    quantity = int(data.get('quantity', 1))
    reason = data.get('reason', '').strip()
    work_order_no = data.get('work_order_no', '').strip()
    if not site_id or not part_name:
        return jsonify({'error': '站点和备件名称不能为空'}), 400
    applicant = g.current_user['username'] or 'unknown'
    # 生成申请编号：BJ+年月日+序号
    from datetime import datetime
    today = datetime.now().strftime('%Y%m%d')
    with get_db() as db:
        count = db.execute("SELECT COUNT(*) as c FROM spare_part_requests WHERE request_no LIKE ?", (f"BJ-{today}%",)).fetchone()['c']
        request_no = f"BJ-{today}-{count+1:03d}"
        db.execute("""INSERT INTO spare_part_requests
            (request_no,site_id,applicant,part_name,quantity,reason,work_order_no)
            VALUES (?,?,?,?,?,?,?)""",
            (request_no, site_id, applicant, part_name, quantity, reason, work_order_no))
        db.commit()
    return jsonify({'success': True, 'request_no': request_no})


@app.route('/api/parts/requests/mine')
@login_required
def api_parts_requests_mine():
    """我的备件申请记录（移动端）"""
    applicant = g.current_user['username'] or 'unknown'
    with get_db() as db:
        rows = db.execute("""SELECT r.*, s.name as site_name
            FROM spare_part_requests r LEFT JOIN sites s ON r.site_id=s.id
            WHERE r.applicant=? ORDER BY r.created_at DESC""", (applicant,)).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/parts/requests/<int:rid>/approve', methods=['PUT'])
@login_required
def api_parts_request_approve(rid):
    """审批通过：更新状态 + 扣减库存"""
    if g.current_user['role'] != 'admin':
        return jsonify({'error': '仅管理员可审批'}), 403
    data = request.get_json(silent=True) or {}
    comment = data.get('comment', '审批通过')
    with get_db() as db:
        req = db.execute("SELECT * FROM spare_part_requests WHERE id=?", (rid,)).fetchone()
        if not req:
            return jsonify({'error': '申请不存在'}), 404
        if req['status'] != 'pending':
            return jsonify({'error': '该申请已处理'}), 400
        # 更新申请状态
        db.execute("""UPDATE spare_part_requests SET status='approved', approver=?,
            approval_comment=?, updated_at=datetime('now','localtime') WHERE id=?""",
            (g.current_user['username'] or 'admin', comment, rid))
        # 尝试扣减库存：查找匹配的备件（按名称模糊匹配）
        inv = db.execute("""SELECT * FROM spare_parts_inventory
            WHERE part_name LIKE ? ORDER BY quantity DESC LIMIT 1""",
            (f"%{req['part_name']}%",)).fetchone()
        if inv:
            new_qty = max(0, inv['quantity'] - req['quantity'])
            db.execute("UPDATE spare_parts_inventory SET quantity=?, updated_at=datetime('now','localtime') WHERE id=?", (new_qty, inv['id']))
            db.execute("""INSERT INTO inventory_logs (part_id,type,quantity,ref_type,ref_id,operator,remark,work_order_no)
                VALUES (?,?,?,'request',?,?,?,?)""",
                (inv['id'], 'out', req['quantity'], rid,
                 g.current_user['username'] or 'admin',
                 f"备件申请 #{req['request_no']}",
                 req['work_order_no'] if req['work_order_no'] else ''))
        db.commit()
    return jsonify({'success': True, 'message': '已批准，库存已扣减'})


@app.route('/api/parts/requests/<int:rid>/reject', methods=['PUT'])
@login_required
def api_parts_request_reject(rid):
    """驳回申请"""
    if g.current_user['role'] != 'admin':
        return jsonify({'error': '仅管理员可审批'}), 403
    data = request.get_json(silent=True) or {}
    comment = data.get('comment', '驳回')
    with get_db() as db:
        req = db.execute("SELECT * FROM spare_part_requests WHERE id=?", (rid,)).fetchone()
        if not req:
            return jsonify({'error': '申请不存在'}), 404
        if req['status'] != 'pending':
            return jsonify({'error': '该申请已处理'}), 400
        db.execute("""UPDATE spare_part_requests SET status='rejected', approver=?,
            approval_comment=?, updated_at=datetime('now','localtime') WHERE id=?""",
            (g.current_user['username'] or 'admin', comment, rid))
        db.commit()
    return jsonify({'success': True, 'message': '已驳回'})


# ===================== 站点过滤辅助函数 =====================

def _filter_by_user(where_clause='', table_prefix=''):
    """为API查询注入站点过滤条件。返回 (where_extra, params)
    管理员不限制，操作员限制为分配的站点。
    在路由函数中使用：在原始WHERE后加上此函数的返回。
    """
    site_ids = getattr(g, 'user_site_ids', None)
    if site_ids is None:
        return '', []
    prefix = table_prefix + '.' if table_prefix else ''
    site_condition = f"{prefix}site_id IN ({','.join('?' * len(site_ids))})" if site_ids else '1=0'
    extra = f" AND {site_condition}" if where_clause else f" WHERE {site_condition}"
    return extra, site_ids


def _filter_site_ids():
    """返回当前用户可见的site_id列表（管理员返回空=全部）"""
    site_ids = getattr(g, 'user_site_ids', None)
    if site_ids is None:
        return None  # None = 不过滤
    return site_ids


# ===================== 前端静态文件服务 =====================
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'frontend')
V2_DIR = os.path.join(FRONTEND_DIR, 'v2')

@app.route('/')
def index_html():
    return send_from_directory(V2_DIR, 'index.html')

# 移动端 — 统一使用 React 版本（响应式）
@app.route('/mobile')
def mobile_page():
    return send_from_directory(V2_DIR, 'index.html')

# ===================== Site Data Import & Data Sources =====================

@app.route('/api/sites/import', methods=['POST'])
@login_required
def import_sites():
    """批量导入站点（CSV文件）"""
    if 'file' not in request.files:
        return jsonify({'error': '请上传CSV文件'}), 400
    f = request.files['file']
    if not f.filename.endswith('.csv'):
        return jsonify({'error': '仅支持CSV格式文件'}), 400
    import csv as csv_mod, io
    try:
        content = f.read().decode('utf-8-sig')
        reader = csv_mod.DictReader(io.StringIO(content))
        success, failed, errors = 0, 0, []
        with get_db() as db:
            for i, row in enumerate(reader, 2):
                code = (row.get('code') or row.get('编码') or row.get('站点编码') or '').strip()
                name = (row.get('name') or row.get('名称') or row.get('站点名称') or '').strip()
                stype = (row.get('type') or row.get('类型') or row.get('站点类型') or '').strip()
                if not code or not name or not stype:
                    failed += 1
                    errors.append(f'第{i}行: 缺少必填字段(code/name/type)')
                    continue
                try:
                    lat = float(row.get('lat') or row.get('纬度') or 0)
                    lng = float(row.get('lng') or row.get('经度') or 0)
                except (ValueError, TypeError):
                    lat, lng = 0, 0
                district = (row.get('district') or row.get('区域') or '').strip()
                river = (row.get('river') or row.get('河流') or '').strip()
                manager = (row.get('manager') or row.get('负责人') or '').strip()
                phone = (row.get('phone') or row.get('电话') or '').strip()
                try:
                    db.execute(
                        "INSERT INTO sites (code,name,type,lat,lng,district,river,manager,phone) VALUES (?,?,?,?,?,?,?,?,?)",
                        (code, name, stype, lat, lng, district, river, manager, phone)
                    )
                    success += 1
                except Exception as e:
                    failed += 1
                    errors.append(f'第{i}行({code}): {str(e)[:60]}')
            db.commit()
        return jsonify({
            'success': True,
            'imported': success,
            'failed': failed,
            'errors': errors[:10],
        })
    except Exception as e:
        return jsonify({'error': f'解析文件失败: {str(e)[:100]}'}), 400

@app.route('/api/sites/data-sources', methods=['GET'])
@login_required
def list_data_sources():
    """获取数据源列表"""
    with get_db() as db:
        rows = db.execute("SELECT * FROM data_sources ORDER BY created_at DESC").fetchall()
        return jsonify([dict(r) for r in rows])

@app.route('/api/sites/data-sources', methods=['POST'])
@login_required
def create_data_source():
    """新增数据源配置"""
    data = request.get_json(silent=True) or {}
    name = data.get('name', '').strip()
    url = data.get('url', '').strip()
    if not name or not url:
        return jsonify({'error': '名称和URL不能为空'}), 400
    with get_db() as db:
        db.execute(
            "INSERT INTO data_sources (name,source_type,protocol,url,auth_type,auth_config,sync_interval,remark) VALUES (?,?,?,?,?,?,?,?)",
            (name, data.get('source_type', 'api'), data.get('protocol', 'HTTP'), url,
             data.get('auth_type', 'none'), json.dumps(data.get('auth_config', {})),
             data.get('sync_interval', 60), data.get('remark', ''))
        )
        db.commit()
    return jsonify({'success': True})

@app.route('/api/sites/data-sources/<int:ds_id>', methods=['DELETE'])
@login_required
def delete_data_source(ds_id):
    """删除数据源"""
    with get_db() as db:
        db.execute("DELETE FROM data_sources WHERE id=?", (ds_id,))
        db.commit()
    return jsonify({'success': True})

@app.route('/api/sites/data-sources/<int:ds_id>/test', methods=['POST'])
@login_required
def test_data_source(ds_id):
    """测试数据源连通性（模拟）"""
    with get_db() as db:
        ds = db.execute("SELECT * FROM data_sources WHERE id=?", (ds_id,)).fetchone()
        if not ds:
            return jsonify({'error': '数据源不存在'}), 404
    # 模拟测试：返回成功
    import random
    latency = random.randint(50, 300)
    return jsonify({
        'success': True,
        'latency_ms': latency,
        'message': f'连接成功，响应时间 {latency}ms',
    })

@app.route('/api/sites/template', methods=['GET'])
def download_site_template():
    """下载站点导入CSV模板"""
    import csv as csv_mod, io
    output = io.StringIO()
    writer = csv_mod.writer(output)
    writer.writerow(['code', 'name', 'type', 'lat', 'lng', 'district', 'river', 'manager', 'phone'])
    writer.writerow(['GST001', '示例雨量站', 'rainfall', '28.68', '115.89', '南昌市', '赣江', '张工', '13800138000'])
    from flask import Response
    return Response(
        '\ufeff' + output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=site_import_template.csv'}
    )

@app.route('/<path:filename>')
def serve_frontend(filename):
    # SPA 路由回退：非 API 路径且非实际文件 → 返回 React 入口
    # 让 React Router 处理客户端路由
    v2_path = os.path.join(V2_DIR, filename)
    frontend_path = os.path.join(FRONTEND_DIR, filename)
    if os.path.exists(v2_path):
        return send_from_directory(V2_DIR, filename)
    if os.path.exists(frontend_path):
        return send_from_directory(FRONTEND_DIR, filename)
    # SPA 回退：所有未匹配的路径都返回 v2/index.html
    return send_from_directory(V2_DIR, 'index.html')

# ===================== Startup =====================

def fix_site_river():
    """为水位站/水文站设置正确的河流字段，避免水位基值漂移"""
    with get_db() as conn:
        conn.execute("UPDATE sites SET river='赣江' WHERE type IN ('water_level','hydrology') AND (river IS NULL OR river='')")
        conn.execute("UPDATE sites SET river='鄱阳湖' WHERE type='groundwater' AND (river IS NULL OR river='')")
        conn.commit()
        updated = conn.total_changes
        print(f"[Fix] 已更新 {updated} 个站点的河流字段")


# =============================================================================
# 移动端专用接口 —— 一线执行助手
# =============================================================================

# 频次中文映射（移动端统一使用此映射，不用 high/mid/low）
_FREQ_CN = {
    'daily': '每日', 'weekly': '每周', 'monthly': '每月',
    'quarterly': '每季', 'semi_annual': '每半年', 'annual': '每年',
    'high': '每日', 'mid': '每月', 'low': '每季', 'annual': '每年',
}


@app.route('/api/mobile/my-today')
@login_required
def mobile_my_today():
    """移动端首页聚合接口：一次请求返回当前用户今日所有任务数据。
    包含：巡检任务（按站点分组）、待处理工单、未处理告警。
    """
    user = g.current_user
    today = datetime.now().strftime('%Y-%m-%d')

    with get_db() as db:
        # ---- 1. 巡检任务：从 V2 计划中获取当前用户未完成的检查项 ----
        is_admin = user.get('role') == 'admin'

        if is_admin:
            # 管理员查看所有活跃计划
            plans = db.execute(
                "SELECT * FROM insp_plans WHERE status IN ('active','draft') ORDER BY generate_date DESC"
            ).fetchall()
        else:
            # 普通用户只查看分配给自己的计划
            plans = db.execute(
                "SELECT * FROM insp_plans WHERE assignee_id=? AND status IN ('active','draft') ORDER BY generate_date DESC",
                (user['id'],)
            ).fetchall()
            # 如果没有指定用户的计划，也查找未指定用户的计划
            if not plans:
                plans = db.execute(
                    "SELECT * FROM insp_plans WHERE status IN ('active','draft') AND (assignee_id IS NULL OR assignee_id=0) ORDER BY generate_date DESC"
                ).fetchall()

        # 收集所有未完成的检查项，按站点分组
        site_tasks = {}  # site_id -> {site_name, site_code, lat, lng, type, items: []}
        total_items = 0
        completed_items = 0
        abnormal_items = 0

        for plan in plans:
            items = db.execute(
                """SELECT pi.*, s.name as site_name, s.code as site_code,
                          s.lat, s.lng, s.type as site_type
                   FROM insp_plan_items pi
                   JOIN sites s ON s.id = pi.site_id
                   WHERE pi.plan_id=? AND pi.result IS NULL
                   ORDER BY pi.category, pi.item_name""",
                (plan['id'],)
            ).fetchall()

            for item in items:
                sid = item['site_id']
                if sid not in site_tasks:
                    site_tasks[sid] = {
                        'site_id': sid,
                        'site_name': item['site_name'],
                        'site_code': item['site_code'],
                        'lat': item['lat'],
                        'lng': item['lng'],
                        'site_type': item['site_type'],
                        'items': [],
                        'categories': {},
                    }
                freq_cn = _FREQ_CN.get(item['frequency'] or '', item['frequency'] or '')
                item_dict = {
                    'item_id': item['id'],
                    'plan_id': item['plan_id'],
                    'item_name': item['item_name'],
                    'category': item['category'] or '其他',
                    'frequency': item['frequency'] or '',
                    'frequency_cn': freq_cn,
                    'result': item['result'],
                    'calibrator': item['calibrator'],
                    'calibration_values': item['calibration_values'],
                    'photo_urls': item['photo_urls'],
                    'remark': item['remark'],
                }
                site_tasks[sid]['items'].append(item_dict)
                # 按类别分组
                cat = item['category'] or '其他'
                if cat not in site_tasks[sid]['categories']:
                    site_tasks[sid]['categories'][cat] = []
                site_tasks[sid]['categories'][cat].append(item_dict)

        # 统计所有项（包括已完成）
        for plan in plans:
            all_items = db.execute(
                "SELECT result FROM insp_plan_items WHERE plan_id=?", (plan['id'],)
            ).fetchall()
            for it in all_items:
                total_items += 1
                if it['result'] is not None:
                    completed_items += 1
                    if it['result'] == 'abnormal':
                        abnormal_items += 1

        # 构建站点列表
        sites_list = []
        for sid, st in site_tasks.items():
            pending = len(st['items'])
            cats_summary = []
            for cat_name, cat_items in st['categories'].items():
                cats_summary.append({
                    'category': cat_name,
                    'pending': len(cat_items),
                })
            sites_list.append({
                'site_id': sid,
                'site_name': st['site_name'],
                'site_code': st['site_code'],
                'lat': st['lat'],
                'lng': st['lng'],
                'site_type': st['site_type'],
                'pending_items': pending,
                'categories': cats_summary,
            })

        # 按站点名称排序
        sites_list.sort(key=lambda x: x['site_name'])

        # ---- 2. 待处理工单：当前用户负责的或全部分配的 ----
        workorders = db.execute(
            """SELECT order_no, title, status, source, level, site_id,
                      (SELECT name FROM sites WHERE id=work_orders.site_id) as site_name,
                      created_at, sla_deadline
               FROM work_orders
               WHERE status NOT IN ('closed')
                     AND (assignee=? OR assignee='' OR assignee IS NULL)
               ORDER BY
                 CASE level WHEN 'critical' THEN 1 WHEN 'urgent' THEN 2 ELSE 3 END,
                 created_at DESC
               LIMIT 20""",
            (user.get('username', ''),)
        ).fetchall()

        wo_list = []
        for wo in workorders:
            wo_list.append({
                'order_no': wo['order_no'],
                'title': wo['title'],
                'status': wo['status'],
                'source': wo['source'],
                'level': wo['level'],
                'site_id': wo['site_id'],
                'site_name': wo['site_name'],
                'created_at': wo['created_at'],
                'sla_deadline': wo['sla_deadline'],
            })

        # ---- 3. 未处理告警：当前用户负责站点的 ----
        user_site_ids = [s['site_id'] for s in sites_list]
        if user_site_ids:
            placeholders = ','.join(['?'] * len(user_site_ids))
            alerts = db.execute(
                f"""SELECT id, site_id, metric, level, message, status, created_at,
                           (SELECT name FROM sites WHERE id=alerts.site_id) as site_name
                    FROM alerts
                    WHERE status='pending' AND site_id IN ({placeholders})
                    ORDER BY
                      CASE level WHEN 'red' THEN 1 WHEN 'orange' THEN 2 WHEN 'yellow' THEN 3 ELSE 4 END,
                      created_at DESC
                    LIMIT 15""",
                user_site_ids
            ).fetchall()
        else:
            alerts = []

        alert_list = []
        for a in alerts:
            alert_list.append({
                'id': a['id'],
                'site_id': a['site_id'],
                'site_name': a['site_name'],
                'metric': a['metric'],
                'level': a['level'],
                'message': a['message'],
                'status': a['status'],
                'created_at': a['created_at'],
            })

        # ---- 汇总 ----
        return jsonify({
            'summary': {
                'total_sites': len(sites_list),
                'total_items': total_items,
                'completed_items': completed_items,
                'pending_items': total_items - completed_items,
                'abnormal_items': abnormal_items,
                'pending_workorders': len(wo_list),
                'pending_alerts': len(alert_list),
                'date': today,
            },
            'sites': sites_list,
            'workorders': wo_list,
            'alerts': alert_list,
        })


@app.route('/api/mobile/site-tasks/<int:site_id>')
@login_required
def mobile_site_tasks(site_id):
    """移动端站点任务详情：返回该站点所有待检检查项（含已完成），按类别分组。"""
    user = g.current_user

    with get_db() as db:
        site = db.execute("SELECT * FROM sites WHERE id=?", (site_id,)).fetchone()
        if not site:
            return jsonify({'error': '站点不存在'}), 404

        # 获取该站点的所有检查项（来自活跃计划）
        plans = db.execute(
            "SELECT id FROM insp_plans WHERE status IN ('active','draft')"
        ).fetchall()
        plan_ids = [p['id'] for p in plans]

        if not plan_ids:
            return jsonify({
                'site': {'id': site['id'], 'name': site['name'], 'code': site['code'],
                         'lat': site['lat'], 'lng': site['lng'], 'type': site['type']},
                'categories': [],
                'total': 0, 'completed': 0,
            })

        placeholders = ','.join(['?'] * len(plan_ids))
        items = db.execute(
            f"""SELECT pi.* FROM insp_plan_items pi
                WHERE pi.site_id=? AND pi.plan_id IN ({placeholders})
                ORDER BY pi.category, pi.item_name""",
            [site_id] + plan_ids
        ).fetchall()

        # 按类别分组
        categories = {}
        total = 0
        completed = 0
        for item in items:
            total += 1
            if item['result'] is not None:
                completed += 1
            cat = item['category'] or '其他'
            if cat not in categories:
                categories[cat] = {'category': cat, 'items': [], 'total': 0, 'completed': 0}
            categories[cat]['total'] += 1
            if item['result'] is not None:
                categories[cat]['completed'] += 1
            freq_cn = _FREQ_CN.get(item['frequency'] or '', item['frequency'] or '')
            categories[cat]['items'].append({
                'item_id': item['id'],
                'plan_id': item['plan_id'],
                'item_name': item['item_name'],
                'frequency': item['frequency'] or '',
                'frequency_cn': freq_cn,
                'result': item['result'],
                'remark': item['remark'],
                'check_time': item['check_time'],
                'calibrator': item['calibrator'],
                'calibration_values': item['calibration_values'],
                'photo_urls': item['photo_urls'],
            })

        return jsonify({
            'site': {'id': site['id'], 'name': site['name'], 'code': site['code'],
                     'lat': site['lat'], 'lng': site['lng'], 'type': site['type']},
            'categories': list(categories.values()),
            'total': total,
            'completed': completed,
        })


@app.route('/api/sites/<int:site_id>/calibrate', methods=['PUT'])
@login_required
def calibrate_site_location(site_id):
    """站点位置校准：一线人员到场后校准站点经纬度。"""
    data = request.get_json(silent=True) or {}
    new_lat = data.get('lat')
    new_lng = data.get('lng')
    if new_lat is None or new_lng is None:
        return jsonify({'error': '请提供经纬度'}), 400

    with get_db() as db:
        site = db.execute("SELECT * FROM sites WHERE id=?", (site_id,)).fetchone()
        if not site:
            return jsonify({'error': '站点不存在'}), 404

        old_lat = site['lat']
        old_lng = site['lng']

        # 计算偏移距离（简化公式，单位：米）
        import math
        dlat = math.radians(new_lat - old_lat) if old_lat else 0
        dlng = math.radians(new_lng - old_lng) if old_lng else 0
        a = math.sin(dlat/2)**2 + math.cos(math.radians(old_lat or 0)) * math.cos(math.radians(new_lat)) * math.sin(dlng/2)**2
        distance_m = 6371000 * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a)) if old_lat and old_lng else 0

        # 更新站点坐标
        db.execute("UPDATE sites SET lat=?, lng=? WHERE id=?", (new_lat, new_lng, site_id))

        # 记录校准日志
        user = g.current_user
        db.execute(
            "INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
            ('site', site_id, 'calibrated', user.get('username', ''),
             f'位置校准: ({old_lat},{old_lng}) → ({new_lat},{new_lng}), 偏移{distance_m:.1f}m')
        )
        db.commit()

        return jsonify({
            'success': True,
            'old_lat': old_lat, 'old_lng': old_lng,
            'new_lat': new_lat, 'new_lng': new_lng,
            'distance_m': round(distance_m, 1),
        })


@app.route('/api/mobile/submit-item', methods=['POST'])
@login_required
def mobile_submit_item():
    """移动端提交检查项结果（统一入口，支持普通项和校准项）。"""
    data = request.get_json(silent=True) or {}
    item_id = data.get('item_id')
    plan_id = data.get('plan_id')
    result = data.get('result')  # 'normal' or 'abnormal'

    if not item_id or not result:
        return jsonify({'error': '缺少必要参数'}), 400

    with get_db() as db:
        item = db.execute("SELECT * FROM insp_plan_items WHERE id=?", (item_id,)).fetchone()
        if not item:
            return jsonify({'error': '检查项不存在'}), 404
        if item['result'] is not None:
            return jsonify({'error': '该检查项已完成', 'duplicate': True}), 400

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        updates = ["result=?", "check_time=?", "completed_at=?"]
        params = [result, now, now]

        if data.get('remark'):
            updates.append("remark=?")
            params.append(data['remark'])
        if data.get('gps_lat') is not None:
            updates.append("gps_lat=?")
            params.append(data['gps_lat'])
        if data.get('gps_lng') is not None:
            updates.append("gps_lng=?")
            params.append(data['gps_lng'])
        if data.get('photo_urls'):
            updates.append("photo_urls=?")
            params.append(data['photo_urls'])
        if data.get('calibrator'):
            updates.append("calibrator=?")
            params.append(data['calibrator'])
        if data.get('calibration_values'):
            updates.append("calibration_values=?")
            params.append(data['calibration_values'])

        params.append(item_id)
        db.execute(f"UPDATE insp_plan_items SET {','.join(updates)} WHERE id=?", params)

        # 异常项自动触发告警
        if result == 'abnormal':
            task = db.execute("SELECT site_id, item_name FROM insp_plan_items WHERE id=?", (item_id,)).fetchone()
            if task:
                remark_text = data.get('remark', '')
                msg = f'巡检异常：{task["item_name"]}'
                if remark_text:
                    msg += f' - {remark_text}'
                create_alert_internal(db, task['site_id'], 'inspection', 0, 'yellow', msg)

        # 更新计划完成率和状态
        if plan_id:
            total = db.execute("SELECT COUNT(*) as c FROM insp_plan_items WHERE plan_id=?", (plan_id,)).fetchone()['c']
            done = db.execute("SELECT COUNT(*) as c FROM insp_plan_items WHERE plan_id=? AND result IS NOT NULL", (plan_id,)).fetchone()['c']
            rate = round(done / total * 100, 1) if total > 0 else 0
            new_status = 'completed' if done == total else 'active'
            db.execute("UPDATE insp_plans SET completion_rate=?, status=? WHERE id=?",
                       (rate, new_status, plan_id))
            if done == total:
                plan = db.execute("SELECT plan_name FROM insp_plans WHERE id=?", (plan_id,)).fetchone()
                db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
                           ('inspection', plan_id, 'completed', '系统', f'巡检计划完成-{plan["plan_name"] if plan else ""}'))

        db.commit()
        return jsonify({'success': True, 'result': result})


if __name__ == '__main__':
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    init_db()
    seed_data()
    seed_inspections()
    seed_alerts()
    seed_maintenance()
    seed_maintenance_templates()
    seed_users()
    seed_inspection_v2()
    seed_abnormal_scenarios()
    migrate_alerts_messages()
    migrate_alert_flow()
    fix_site_river()
    if os.environ.get('SKIP_BACKFILL') == '1':
        print("[Seed] 跳过数据回填（E2E测试模式）")
    else:
        backfill_history(72)
    # 生成初始数据（让趋势跟踪生效）
    for _ in range(6):
        try:
            if os.environ.get('SKIP_SEED') != '1':
                generate_sensor_data()
                time.sleep(0.3)
        except Exception as e:
            print(f'[Seed] 初始数据生成跳过: {e}')
    # 演示数据层：叠加自洽的告警-工单联动数据（替换旧的预设离线+清理+补充逻辑）
    try:
        from seed_demo import generate as demo_generate
        demo_generate()
    except Exception as e:
        import traceback
        print(f"[Seed] 演示数据生成失败: {e}")
        traceback.print_exc()
    # 清理过期已办结告警（保留最近7天，档案卡片需要7天历史）
    # 清理过期已办结告警（保留最近7天，档案卡片需要7天历史）
    try:
        with get_db() as db:
            total = db.execute("SELECT COUNT(*) as c FROM alerts WHERE status='resolved' AND created_at < datetime('now','-7 day')").fetchone()['c']
            if total > 50:
                db.execute("DELETE FROM alerts WHERE status='resolved' AND created_at < datetime('now','-7 day')")
                db.commit()
                print(f"[Cleanup] 清理过期已办结告警: 删除{total}条（保留近7天）")
    except Exception as e:
        print(f"[Cleanup] 告警清理跳过: {e}")
    # 模拟器已关闭（仅保留静态异常场景数据用于演示）
    # if os.environ.get('SKIP_SIMULATOR') != '1':
    #     scheduler.add_job(generate_sensor_data, 'interval', seconds=60, id='simulator')
    #     print("[Server] 数据仿真器已启动（每60秒），SKIP_SIMULATOR=1 可关闭")
    # else:
    print("[Server] 数据仿真器已关闭（静态演示模式）")
    # 每30分钟更新天气
    scheduler.add_job(fetch_real_weather, 'interval', minutes=30, id='weather_updater')
    print("[Server] 水利运维智慧运营平台 启动成功!")
    print("[Server] API: http://localhost:5000/api/health")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
