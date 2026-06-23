#!/usr/bin/env python3
"""深层次数据调查"""
import json, requests
from collections import Counter

BASE = "http://localhost:5000/api"
TOKEN = "V5wbquCYJfjQ6LHbfaaepGDVLTmdth6FYqm1aJm8xyQ"
H = {"Authorization": f"Bearer {TOKEN}"}

def get(url):
    r = requests.get(url, headers=H, timeout=10)
    return r.json()

# 1. 告警level分布
print("=== 告警level分布 ===")
alerts = get(f"{BASE}/alerts")
levels = Counter(a.get("level","?") for a in alerts)
print(f"  level唯一值: {dict(levels)}")
print(f"  告警ID范围: {min(a['id'] for a in alerts)} ~ {max(a['id'] for a in alerts)}")
samples = [a.get("related_order_no") for a in alerts[:3]]
print(f"  related_order_no示例: {samples}")
has_alpha = any(any(c.isalpha() for c in str(a.get("related_order_no",""))) for a in alerts)
print(f"  工单号含字母: {has_alpha}")

# 2. 工单id格式
print("\n=== 工单ID格式 ===")
wos = get(f"{BASE}/workorders")
if wos:
    print(f"  工单ID: {[w.get('id') for w in wos[:5]]}")
    print(f"  id类型: {type(wos[0].get('id')).__name__}")
    print(f"  列表长度: {len(wos)}")
    print(f"  id实际值: {[w['id'] for w in wos[:3]]}")

# 3. 工单统计详情
print("\n=== 工单统计 ===")
wo_stats = get(f"{BASE}/workorders/statistics")
print(f"  {json.dumps(wo_stats, indent=2, ensure_ascii=False)}")

# 4. 巡检统计
print("\n=== 巡检统计 ===")
insp_stats = get(f"{BASE}/inspections/statistics")
print(f"  {json.dumps(insp_stats, indent=2, ensure_ascii=False)}")

print(f"\n  字段列表: {list(insp_stats.keys())}")

# 5. 所有站点level
print("\n=== 站点等级 ===")
sites = get(f"{BASE}/sites")
print(f"  level唯一值: {set(s.get('level','?') for s in sites)}")
print(f"  status唯一值: {set(s.get('status','?') for s in sites)}")

# 6. 检查告警中used for stats endpoint - try different paths
print("\n=== 尝试不同告警stats路径 ===")
for path in ["/alerts/stats", "/alert/stats", "/alerts/statistics", "/stats/alerts"]:
    try:
        r = requests.get(f"{BASE}{path}", headers=H, timeout=5)
        print(f"  {path}: {r.status_code} - {r.text[:100]}")
    except Exception as e:
        print(f"  {path}: ERROR - {e}")

# 7. 告警工单号 vs 工单id 格式对比
print("\n=== 工单号格式对比 ===")
alert_rons = set()
for a in alerts:
    ron = a.get("related_order_no")
    if ron:
        alert_rons.add(str(ron))
wo_ids = set()
for w in wos:
    wo_ids.add(str(w.get("id")))
print(f"  告警引用的工单号 (前10): {list(alert_rons)[:10]}")
print(f"  工单ID (前10): {list(wo_ids)[:10]}")
intersection = alert_rons & wo_ids
print(f"  交集: {len(intersection)}")
print(f"  工单号格式(含WO-前缀): {any(s.startswith('WO-') for s in alert_rons)}")

# 8. 检查工单列表是否有WO-编号
print("\n=== 工单是否有WO编号字段 ===")
wo_fields = set()
for w in wos:
    wo_fields.update(w.keys())
print(f"  工单所有字段: {sorted(wo_fields)}")
# Check if there's a work_order_no or similar field
has_wo_no = any("order_no" in str(k).lower() or "wo_no" in str(k).lower() for k in wo_fields)
print(f"  包含order_no字段: {has_wo_no}")
for w in wos[:3]:
    print(f"  工单{json.dumps({k:w[k] for k in sorted(w.keys())}, ensure_ascii=False)[:200]}")
