#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
设备名称规范化脚本
为235个站点生成标准化的设备名称和编码
"""
import sqlite3
import os, sys

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, 'data', 'water.db')

# 每种站型的标准设备配置（含型号和厂商）
STD_DEVICES = {
    'hydrology': [
        ('水位计', 'WL', 'sensor', 'SWJ-1A', '南京水文仪器有限公司'),
        ('流速仪', 'VEL', 'sensor', 'LS25-1', '长沙水文仪器厂'),
        ('流量计', 'FLOW', 'sensor', 'HWP-1', '南京水文仪器有限公司'),
        ('通信模块', 'COMM', 'comm', 'RTU-200', '深圳水情科技'),
    ],
    'water_level': [
        ('水位计', 'WL', 'sensor', 'SWJ-1A', '南京水文仪器有限公司'),
        ('雨量计', 'RF', 'sensor', 'SL3-1', '上海气象仪器厂'),
    ],
    'rainfall': [
        ('翻斗式雨量计', 'RF', 'sensor', 'SL3-1', '上海气象仪器厂'),
        ('通信模块', 'COMM', 'comm', 'RTU-200', '深圳水情科技'),
    ],
    'soil_moisture': [
        ('土壤水分传感器', 'SM', 'sensor', 'TDR-300', '北京农业物联网'),
        ('土壤温度传感器', 'ST', 'sensor', 'PT100-A', '北京农业物联网'),
        ('通信模块', 'COMM', 'comm', 'RTU-200', '深圳水情科技'),
    ],
    'evaporation': [
        ('蒸发传感器', 'EVP', 'sensor', 'EVP-1', '南京水文仪器有限公司'),
        ('气温传感器', 'TMP', 'sensor', 'PT100-A', '北京农业物联网'),
        ('通信模块', 'COMM', 'comm', 'RTU-200', '深圳水情科技'),
    ],
    'groundwater': [
        ('地下水位计', 'GWL', 'sensor', 'GWL-2', '南京水文仪器有限公司'),
        ('水质分析仪', 'WQ', 'sensor', 'WQ-100', '杭州环保科技'),
        ('通信模块', 'COMM', 'comm', 'RTU-200', '深圳水情科技'),
    ],
    'station_yard': [
        ('视频监控', 'CAM', 'sensor', 'IPC-500', '海康威视'),
        ('备用电源', 'PWR', 'power', 'UPS-1000', '深圳电源科技'),
        ('环境传感器', 'ENV', 'sensor', 'ENV-200', '北京农业物联网'),
        ('通信模块', 'COMM', 'comm', 'RTU-200', '深圳水情科技'),
    ],
}

# 站点名称缩写映射（取每个字的首字母或前2个字符）
def abbr_from_id(site_id):
    """根据站点ID生成缩写"""
    known = {5:'WJB',234:'GQ',3:'XQZ',52:'LY',13:'XJL',175:'XZ',
             56:'HG',188:'JT',166:'NG',19:'AY',204:'SB',1:'DC',2:'NC',
             14:'TX',92:'LJ',95:'LJ',6:'LJ',7:'LJ',17:'XZ',22:'XC',
             52:'LY',108:'WF',193:'HS'}
    return known.get(site_id, f"S{site_id:03d}")

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    sites = conn.execute("SELECT id, name, type FROM sites ORDER BY id").fetchall()
    
    # 清空原有设备
    conn.execute("DELETE FROM device_shadows")
    
    total = 0
    for site in sites:
        sid = site['id']
        name = site['name']
        stype = site['type']
        devices = STD_DEVICES.get(stype, [('通用传感器', 'GEN', 'sensor')])
        
        abbr = abbr_from_id(sid)

        for i, (dev_name, dev_code_type, dev_type, dev_model, dev_mfr) in enumerate(devices, 1):
            total += 1
            code = f"{abbr}-{dev_code_type}-{i:02d}"
            # 确保编码全局唯一
            while conn.execute("SELECT id FROM device_shadows WHERE device_code=?", (code,)).fetchone():
                code = f"{abbr}-{dev_code_type}-{i:02d}-{sid}"
                break
            dname = f"{name}{dev_name}"
            status = 'online'
            voltage = round(12.0 + (hash(str(sid*100+i)) % 10 - 5) * 0.2, 1)  # 11.0~13.0V
            install_date = f"20{18 + (sid % 6):02d}-{(sid % 12) + 1:02d}-{(sid % 28) + 1:02d}"
            conn.execute(
                "INSERT INTO device_shadows (site_id, device_code, device_name, device_type, device_model, manufacturer, install_date, status, voltage, last_data_time) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (sid, code, dname, dev_type, dev_model, dev_mfr, install_date, status, voltage, '2026-06-23 08:00:00')
            )
    
    conn.commit()
    
    # 注入特殊异常设备
    # 万家埠(5)设为离线
    conn.execute("UPDATE device_shadows SET status='offline', voltage=10.5, last_data_time=NULL WHERE site_id=5 AND device_type='comm'")
    # 新祺周(3)通信模块离线
    conn.execute("UPDATE device_shadows SET status='offline', voltage=10.8, last_data_time=NULL WHERE site_id=3 AND device_type='comm'")
    # 岗前(234)备用电源电压偏低
    conn.execute("UPDATE device_shadows SET voltage=11.3 WHERE site_id=234 AND device_code LIKE '%-PWR-%'")
    # 罗亭(52)雨量计通信模块信号弱
    conn.execute("UPDATE device_shadows SET status='online', voltage=11.6 WHERE site_id=52 AND device_type='comm'")
    
    conn.commit()
    conn.close()
    print(f"[SeedDevice] 已生成 {total} 条标准化设备记录（235站）")
    print(f"[SeedDevice] 异常设备保留：万家埠离线、新祺周离线、岗前电压偏低、罗亭信号弱")

if __name__ == '__main__':
    main()
