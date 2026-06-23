#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全平台演示数据生成 v3 — 精简自洽版
要求：
- 活跃告警: 3条（红/橙/黄各1）
- 异常设备: 3台（离线/电压低/数据异常）
- 历史采集数据: 7天（235站）
- 归档数据: 7天（档案卡片展示用）
"""

import os, sqlite3, shutil, random
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, 'data', 'water.db')
random.seed(42)
now = datetime.now()

def fmt(dt):
    return dt.strftime('%Y-%m-%d %H:%M:%S')

print("=" * 60)
print("  全平台演示数据生成 v3")
print("=" * 60)

# 备份
shutil.copy2(DB_PATH, DB_PATH.replace('.db', '-v3-backup.db'))
print("[Demo] 已备份")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# =========================================================
# 1. 清除全部业务数据 + 重新生成基础传感器数据
# =========================================================
print("\n[1/6] 清除旧数据+生成7天传感器数据...")
tables = ['alerts','work_orders','sensor_data','device_shadows','data_arrival',
          'timeline_events','inspection_plans','inspection_tasks',
          'spare_parts_inventory','spare_part_requests','inventory_logs']
for t in tables:
    c.execute(f"DELETE FROM {t}")
conn.commit()

# 温度昼夜模式函数
def get_temp(hour):
    if 6 <= hour <= 8: return random.uniform(18, 22)       # 早晨
    elif 8 < hour <= 11: return random.uniform(22, 28)      # 升温
    elif 11 < hour <= 15: return random.uniform(28, 35)     # 中午最高
    elif 15 < hour <= 19: return random.uniform(22, 28)     # 降温
    else: return random.uniform(18, 23)                     # 晚上

# 生成7天传感器数据
c.execute("SELECT id, type FROM sites")
all_sites = c.fetchall()
total_sensor = 0
for day_offset in range(7, -1, -1):  # 7天前到今天
    day = now - timedelta(days=day_offset)
    max_hour = 22
    if day_offset == 0:
        max_hour = min(22, now.hour - 1)  # 今天只到当前小时
    for sid, stype in all_sites:
        if sid == 5:  # 江桥站设备离线，不生成数据
            continue
        base_metrics = []
        if stype in ('rainfall','station_yard'):
            base_metrics.append(('precipitation', None, 'mm'))  # 降雨量在小时循环中生成
        elif stype in ('water_level','hydrology'):
            base_metrics.append(('water_level', round(random.uniform(18.0, 20.5), 2), 'm'))
        elif stype == 'soil_moisture':
            base_metrics.append(('soil_moisture', round(random.uniform(20, 45), 1), '%'))
        elif stype == 'evaporation':
            base_metrics.append(('evaporation', round(random.uniform(0, 6), 1), 'mm'))
        elif stype == 'groundwater':
            base_metrics.append(('groundwater_level', round(random.uniform(5, 12), 2), 'm'))
        for h in range(6, max_hour + 1, 3):
            # 温度随小时变化（昼夜模式）
            metrics = [('temperature', round(get_temp(h), 1), '°C')]
            for metric, base_val, unit in base_metrics:
                # 降雨量：每小时独立生成，晚上(18点后)为0
                if base_val is None:
                    if metric == 'precipitation' and h >= 18:
                        val = 0.0
                    else:
                        val = random.uniform(0, 25)
                else:
                    val = base_val
                metrics.append((metric, round(val, 1), unit))
            for metric, val, unit in metrics:
                t = day.replace(hour=h, minute=random.randint(0, 59))
                v = val + random.uniform(-0.5, 0.5)
                if v < 0: v = 0
                c.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)",
                         (sid, metric, v, unit, fmt(t)))
                total_sensor += 1
conn.commit()
print(f"  ✓ {total_sensor} 条传感器数据（{len(all_sites)}站×7天）")

# 设备影子
c.execute("SELECT id FROM sites")
all_site_ids = [r[0] for r in c.fetchall()]
for sid in all_site_ids:
    for dtype in ['水位计','雨量计','温度计','电压表','通信模块']:
        c.execute("INSERT INTO device_shadows (site_id,device_name,device_type,device_code,status,voltage,last_data_time) VALUES (?,?,?,?,?,?,?)",
                 (sid, f'{dtype}-{sid}', dtype, f'DEV-{sid}-{dtype[:2]}', 'online',
                  round(random.uniform(11.8, 13.5), 2), fmt(now - timedelta(minutes=random.randint(5, 60)))))
conn.commit()
print("  ✓ 设备影子初始化完成")

# =========================================================
# 2. 活跃告警：3条（红/橙/黄各1）
# =========================================================
print("\n[2/6] 活跃告警：3条...")
alerts = [
    (1, 'data_spike', 22.5, 'red', 'pending', 'auto', 'pending',
     '数据异常：邓埠站水位数据发生突变（18.1m→22.5m），疑似传感器故障'),
    (5, 'device_status', 0, 'orange', 'pending', 'auto', 'pending_review',
     '设备离线：江桥站通信中断，所有设备离线超过30分钟'),
    (108, 'data_gap', 65, 'yellow', 'pending', 'auto', 'pending',
     '数据延迟：泉岭站降雨量已有65分钟未更新'),
]
for aid, (sid, metric, val, level, status, ft, fs, msg) in enumerate(alerts, 1):
    c.execute('''INSERT INTO alerts (id,site_id,metric,value,level,message,status,created_at,flow_type,flow_status)
                 VALUES (?,?,?,?,?,?,?,?,?,?)''',
              (aid, sid, metric, val, level, msg, status,
               fmt(now - timedelta(hours=random.randint(1, 6))), ft, fs))
conn.commit()
print(f"  ✓ 3条活跃告警（红:邓埠/橙:江桥/黄:泉岭）")

# =========================================================
# 3. 异常设备：3台
# =========================================================
print("\n[3/6] 异常设备：3台...")
# 设备1: site 5 江桥 — 全部离线
c.execute("UPDATE device_shadows SET status='offline', voltage=0 WHERE site_id=5")
# 设备2: site 1 邓埠 — 一个设备电压偏低
c.execute('''
  UPDATE device_shadows SET voltage=11.2 WHERE site_id=1 AND id=(
    SELECT MIN(id) FROM device_shadows WHERE site_id=1
  )
''')
# 设备3: site 193 蓼南 — 一个设备离线
c.execute('''
  UPDATE device_shadows SET status='offline', voltage=0 WHERE site_id=193 AND id=(
    SELECT MIN(id) FROM device_shadows WHERE site_id=193
  )
''')
conn.commit()
print("  ✓ 江桥全部离线+邓埠电压低+蓼南部分离线")

# =========================================================
# 4. 归档数据（7天历史告警+工单，用于档案卡片展示）
# =========================================================
print("\n[4/6] 归档数据：7天历史记录（档案卡片用）...")

hist_alert_id = 10
hist_wo_id = 10
# 每天2-3条历史告警+工单
for day_offset in range(7, 0, -1):
    day = now - timedelta(days=day_offset)
    count = random.randint(2, 3)
    for _ in range(count):
        sid = random.choice(all_site_ids)
        # 历史告警（已办结）
        level = random.choice(['yellow','yellow','orange'])
        metric = random.choice(['data_gap','data_spike','data_freeze'])
        msg = {
            'data_gap': '数据延迟：已有{}分钟未更新'.format(random.randint(30, 180)),
            'data_spike': '数据波动异常：检测到数据突变',
            'data_freeze': '数据冻结：传感器可能故障',
        }[metric]
        created = day.replace(hour=random.randint(6, 22), minute=random.randint(0, 59))
        resolved = created + timedelta(hours=random.randint(1, 8))
        c.execute('''INSERT INTO alerts (id,site_id,metric,value,level,message,status,created_at,resolved_at,flow_type,flow_status)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                  (hist_alert_id, sid, metric, round(random.uniform(0.5, 5), 2),
                   level, msg, 'resolved', fmt(created), fmt(resolved), 'auto', 'converted'))
        
        # 关联工单（已关闭）
        wo_id = hist_wo_id
        order_no = f'WO-HIST-{hist_wo_id:04d}'
        title = f'{msg[:20]}...'
        wo_created = created
        wo_closed = resolved + timedelta(hours=random.randint(1, 4))
        assignee = random.choice(['张工','李工','王工','刘工'])
        c.execute('''INSERT INTO work_orders (id,order_no,site_id,source,event_type,level,title,description,assignee,status,created_at,resolved_at)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (wo_id, order_no, sid, 'auto', level, level, title,
                   f'系统自动生成工单 - {msg}', assignee, 'closed', fmt(wo_created), fmt(wo_closed)))
        
        # 工单时间线
        events = [
            ('created', '系统', '工单自动生成'),
            ('accepted', assignee, '工单已受理'),
            ('in_progress', assignee, '开始现场处置'),
            ('resolved', assignee, '维修完成，设备恢复正常'),
            ('closed', '班组长', '验收通过，工单归档'),
        ]
        for j, (evt, op, rm) in enumerate(events):
            et = wo_created + timedelta(hours=j)
            c.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark,created_at) VALUES (?,?,?,?,?,?)",
                     ('work_order', wo_id, evt, op, rm, fmt(et)))
        
        # 关联告警→工单
        c.execute("UPDATE alerts SET related_order_no=? WHERE id=?", (order_no, hist_alert_id))
        
        hist_alert_id += 1
        hist_wo_id += 1

conn.commit()
print(f"  ✓ 历史告警: {hist_alert_id - 10}条 + 关联工单: {hist_wo_id - 10}条")

# =========================================================
# 5. 巡检计划（档案卡片中展示用）
# =========================================================
print("\n[5/6] 巡检计划+检查任务...")
plans = [
    (100, 21, '邓埠站日常巡检', 'daily'),
    (101, 13, '谢家垄水位巡检', 'daily'),
    (102, 52, '红旗站月度巡检', 'monthly'),
]
for pid, sid, name, freq in plans:
    c.execute('''INSERT INTO inspection_plans (id,site_id,plan_name,type,start_date,end_date,status,created_at)
                VALUES (?,?,?,?,datetime('now','localtime'),datetime('now','+7 days','localtime'),'pending',datetime('now','localtime'))''',
              (pid, sid, name, freq))
    items = ['坝体外观', '设备运行', '监测数据', '电源系统', '通讯状态', '环境安全']
    for j, item in enumerate(items):
        tid = 1000 + pid * 10 + j
        # 每日巡检部分完成，月度巡检全待完成
        result = random.choices(['pass', None], weights=[3, 1])[0] if freq == 'daily' else None
        c.execute('''INSERT INTO inspection_tasks (id,plan_id,site_id,check_item,result,remark,inspector,check_time)
                    VALUES (?,?,?,?,?,?,?,?)''',
                  (tid, pid, sid, item, result,
                   '设备运行正常' if result == 'pass' else '',
                   random.choice(['张工','李工','王工']) if result else None,
                   fmt(now - timedelta(hours=random.randint(1, 12))) if result else None))
conn.commit()
print(f"  ✓ {len(plans)}个巡检计划 + 18项检查任务")
  
# =========================================================
# 6. 数据到达率
# =========================================================
print("\n[6/6] 数据到达率...")
for i in range(7):
    d = (now - timedelta(days=6-i)).strftime('%Y-%m-%d')
    for sid in all_site_ids:
        rate = round(random.uniform(0.93, 1.0) * 100, 1)
        if random.random() < 0.05:
            rate = round(random.uniform(0.70, 0.90) * 100, 1)
        c.execute("INSERT INTO data_arrival (site_id,date,metric,expected_count,actual_count,arrival_rate,created_at) VALUES (?,?,?,?,?,?,datetime('now','localtime'))",
                 (sid, d, 'data_throughput', 288, int(288*rate/100), rate))
conn.commit()
print("  ✓ 7天×235站 数据到达率")

# =========================================================
# 汇总
# =========================================================
print("\n" + "=" * 60)
print("  生成完成！数据概览：")
print("=" * 60)
for tbl in ['sites','alerts','work_orders','sensor_data','device_shadows','data_arrival',
            'inspection_plans','inspection_tasks','timeline_events']:
    c.execute(f"SELECT COUNT(*) FROM {tbl}")
    print(f"  {tbl}: {c.fetchone()[0]}")

c.execute("SELECT status, COUNT(*) FROM alerts GROUP BY status")
print(f"  告警状态: {dict(c.fetchall())}")
c.execute("SELECT status, COUNT(*) FROM work_orders GROUP BY status")
print(f"  工单状态: {dict(c.fetchall())}")
c.execute("SELECT status, COUNT(*) FROM device_shadows GROUP BY status")
print(f"  设备状态: {dict(c.fetchall())}")

conn.close()
print()
