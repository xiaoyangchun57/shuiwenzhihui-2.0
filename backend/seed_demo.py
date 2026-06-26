"""水利智慧运营平台 — 演示数据层（v5自洽版）
在 app.py 基础种子数据之上覆盖演示场景。
用法：在 app.py 的 __main__ 末尾调用 seed_demo.generate() 即可。
"""
import sqlite3, os, random, time
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'water.db')

def log(msg):
    print(f"[Demo] {msg}")

def _db():
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=5000")
    db.execute("PRAGMA synchronous=OFF")
    return db

def generate():
    """在基础种子数据之上叠加演示场景"""
    t0 = time.time()
    log("=== 开始叠加演示数据 ===")
    db = _db()
    
    # ====== 1. 清理已产生的随机告警、演示工单、旧巡检计划 ======
    db.execute("DELETE FROM alerts")
    db.execute("DELETE FROM work_orders WHERE source IN ('auto','alert_convert') OR order_no LIKE 'WO-DEMO-%'")
    db.execute("DELETE FROM inspection_plans WHERE plan_name NOT LIKE '%智能%' AND status='pending'")
    db.execute("DELETE FROM inspection_tasks WHERE plan_id NOT IN (SELECT id FROM inspection_plans)")
    db.execute("DELETE FROM timeline_events WHERE source_type='alert'")
    db.commit()
    log("清理旧的随机告警/工单")
    
    now = datetime.now()
    
    # ====== 2. 场景1: 邓埠 — 水位陡增（auto/converted，工单已派发） ======
    db.execute("""
        INSERT INTO alerts (site_id,metric,value,level,message,status,created_at,flow_type,flow_status,related_order_no)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (1, 'data_spike', 22.5, 'red',
          '数据异常陡增：邓埠站水位 22.50m（超警戒水位），已自动转工单处理',
          'pending', (now - timedelta(hours=2)).strftime('%Y-%m-%d %H:%M:%S'),
          'auto', 'converted', 'WO-DEMO-001'))
    db.execute("""
        INSERT INTO work_orders (order_no,site_id,source,event_type,level,title,description,assignee,status,sla_deadline,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, ('WO-DEMO-001', 1, 'auto', '告警自动转工单', 'urgent',
          '[自动] 邓埠站水位数据异常陡增',
          '水位数据异常陡增（22.50m），已超警戒水位，请立即核实处理。',
          '张建国', 'dispatched',
          (now + timedelta(hours=24)).strftime('%Y-%m-%d %H:%M'),
          (now - timedelta(hours=2)).strftime('%Y-%m-%d %H:%M:%S')))
    db.execute("INSERT INTO timeline_events (source_type,source_id,event_type,operator,remark) VALUES (?,?,?,?,?)",
               ('alert', 1, 'auto_converted', '系统', '自动转工单 WO-DEMO-001'))
    
    # ====== 3. 场景2: 江桥 — 全部离线（manual/pending_review） ======
    db.execute("""
        INSERT INTO alerts (site_id,metric,value,level,message,status,created_at,flow_type,flow_status)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (5, 'device_status', 0, 'yellow',
          '设备离线：江桥站全部4台设备通信中断',
          'pending', (now - timedelta(hours=4)).strftime('%Y-%m-%d %H:%M:%S'),
          'manual', 'pending_review'))
    db.execute("UPDATE device_shadows SET status='offline', last_data_time=NULL WHERE site_id=5")
    db.execute("UPDATE sites SET status='offline', last_heartbeat=NULL WHERE id=5")
    
    # ====== 4. 场景3: 泉岭 — 全部离线（manual/pending_review） ======
    db.execute("""
        INSERT INTO alerts (site_id,metric,value,level,message,status,created_at,flow_type,flow_status)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (108, 'device_status', 0, 'yellow',
          '设备离线：泉岭站全部2台设备通信中断',
          'pending', (now - timedelta(hours=6)).strftime('%Y-%m-%d %H:%M:%S'),
          'manual', 'pending_review'))
    db.execute("UPDATE device_shadows SET status='offline', last_data_time=NULL WHERE site_id=108")
    db.execute("UPDATE sites SET status='offline', last_heartbeat=NULL WHERE id=108")
    
    # ====== 5. 场景4: 蓼南 — 1台离线（manual/pending_review） ======
    db.execute("""
        INSERT INTO alerts (site_id,metric,value,level,message,status,created_at,flow_type,flow_status)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (193, 'device_status', 0, 'yellow',
          '设备离线：蓼南站土壤温度计通信中断',
          'pending', (now - timedelta(hours=3)).strftime('%Y-%m-%d %H:%M:%S'),
          'manual', 'pending_review'))
    db.execute("UPDATE device_shadows SET status='offline', last_data_time=NULL WHERE site_id=193 AND device_type='soil_temperature'")
    
    db.commit()
    log("4条自洽演示告警已创建 (含联动工单)")
    
    # ====== 6. 传感器趋势数据（含水位突变场景） ======
    log("开始生成传感器趋势数据（48h回填）...")
    sites = db.execute("SELECT id, type FROM sites WHERE id NOT IN (5,108)").fetchall()
    total_count = 0
    
    for site in sites:
        sid = site['id']
        stype = site['type']
        batch = []
        
        for h in range(288, 0, -1):  # 48h × 6/小时 = 288条
            ts = (now - timedelta(minutes=10 * h)).strftime('%Y-%m-%d %H:%M:%S')
            
            if stype == 'hydrology':
                if sid == 1:  # 邓埠水位突增
                    hour_ago = h * 10 / 60
                    if 7.5 <= hour_ago <= 8.5:
                        progress = (hour_ago - 7.5) / 1.0
                        if progress < 0.3: wl = round(17.1 + progress * 2, 2)
                        elif progress < 0.5: wl = round(18.5 + (progress-0.3) * 15, 2)
                        else: wl = round(21.0 + (progress-0.5) * 3, 2)
                    elif hour_ago > 8.5:
                        wl = round(22.5 - (hour_ago-8.5) * 0.05, 2)
                    else:
                        wl = round(random.uniform(16.8, 17.5), 2)
                else:
                    wl = round(random.uniform(16.5, 18.0), 2)
                batch += [(sid,'water_level',wl,'m',ts),
                          (sid,'flow',round(random.uniform(300,3000),0),'m³/s',ts),
                          (sid,'velocity',round(random.uniform(0.5,3.0),2),'m/s',ts),
                          (sid,'precipitation',round(random.uniform(0,5) if random.random()<0.2 else 0,1),'mm/h',ts)]
            
            elif stype == 'water_level':
                wl = round(random.uniform(18.0, 20.5), 2)
                batch += [(sid,'water_level',wl,'m',ts), (sid,'flow',round(random.uniform(200,2000),0),'m³/s',ts)]
            
            elif stype == 'rainfall':
                batch += [(sid,'precipitation',round(random.uniform(0,10) if random.random()<0.25 else 0,1),'mm/h',ts),
                          (sid,'cumulative_rainfall',round(random.uniform(20,80),1),'mm',ts)]
            
            elif stype == 'soil_moisture':
                batch.append((sid,'soil_moisture',round(random.uniform(30,80),1),'%',ts))
                if sid != 193:  # 蓼南温度计离线
                    batch.append((sid,'soil_temperature',round(random.uniform(18,30),1),'°C',ts))
            
            elif stype == 'evaporation':
                batch += [(sid,'evaporation',round(random.uniform(2,8),1),'mm',ts),
                          (sid,'temperature',round(random.uniform(22,35),1),'°C',ts),
                          (sid,'wind_speed',round(random.uniform(1,6),1),'m/s',ts)]
            
            elif stype == 'groundwater':
                batch += [(sid,'groundwater_level',round(random.uniform(5,15),2),'m',ts),
                          (sid,'water_quality',round(random.uniform(0.3,1.5),2),'NTU',ts)]
            
            elif stype == 'station_yard':
                batch.append((sid,'noise',round(random.uniform(30,60),0),'dB',ts))
            
            if len(batch) >= 1000:
                db.execute("BEGIN")
                for r in batch:
                    db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)", r)
                db.commit()
                total_count += len(batch)
                batch = []
        
        if batch:
            db.execute("BEGIN")
            for r in batch:
                db.execute("INSERT INTO sensor_data (site_id,metric,value,unit,recorded_at) VALUES (?,?,?,?,?)", r)
            db.commit()
            total_count += len(batch)
    
    log(f"传感器趋势数据生成完成: {total_count} 条")
    
    # ====== 7. 备件库存补充（1种低库存） ======
    db.execute("UPDATE spare_parts_inventory SET quantity=3, min_quantity=5 WHERE part_code='BJ-011'")
    log("备件库存已调整（风速风向仪低库存演示）")
    
    db.close()
    elapsed = time.time() - t0
    log(f"=== 演示数据叠加完成！耗时 {elapsed:.1f}s ===")
    
    # 打印摘要
    db2 = _db()
    print(f"\n{'='*50}")
    for site_id, name in [(1,'邓埠'),(5,'江桥'),(108,'泉岭'),(193,'蓼南')]:
        a = db2.execute("SELECT level, status, flow_type, flow_status, related_order_no FROM alerts WHERE site_id=? ORDER BY id DESC LIMIT 1", (site_id,)).fetchone()
        if a:
            print(f"  {name}: [{a['level']}] {a['flow_type']}/{a['flow_status']} wo={a['related_order_no'] or '-'}")
    print(f"  总传感器数据: {db2.execute('SELECT COUNT(*) FROM sensor_data').fetchone()[0]}")
    al_pending = db2.execute("SELECT COUNT(*) FROM alerts WHERE status='pending'").fetchone()[0]
    print(f"  待处理告警: {al_pending}")
    wo_count = db2.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0]
    print(f"  工单总数: {wo_count}")
    print(f"{'='*50}")
    db2.close()

if __name__ == '__main__':
    generate()
