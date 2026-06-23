#!/usr/bin/env python3
"""
水利智慧运营平台 - 前端API审计脚本
检查所有前端依赖API端点的响应数据逻辑合理性
"""
import json, sys, requests, random
from datetime import datetime, date
from collections import Counter

BASE = "http://localhost:5000/api"
TOKEN = "V5wbquCYJfjQ6LHbfaaepGDVLTmdth6FYqm1aJm8xyQ"
AUTH_HEADER = {"Authorization": f"Bearer {TOKEN}"}

def get(url):
    try:
        r = requests.get(url, headers=AUTH_HEADER, timeout=10)
        if r.status_code in (401, 403):
            return {"_auth_error": True, "_status": r.status_code, "_text": r.text[:200]}
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"_error": str(e), "_url": url}

def section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")

def check(cond, msg, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {msg}")
    if not cond and detail:
        for line in detail.split("\n"):
            print(f"          {line}")

def summary_line(label, value):
    print(f"  {label}: {value}")

failed_checks = []

def report_fail(name, desc=""):
    failed_checks.append((name, desc))

# ============================================================
section("1. 基础数据 - 站点列表")
# ============================================================
sites = get(f"{BASE}/sites")
site_count = len(sites) if isinstance(sites, list) else 0
summary_line("站点总数", site_count)

if isinstance(sites, list) and site_count > 0:
    no_lat = [s for s in sites if not s.get("lat")]
    no_lng = [s for s in sites if not s.get("lng")]
    offline = [s for s in sites if s.get("status") == "offline"]
    check(len(no_lat) == 0, f"所有站点应有lat字段", f"缺失: {len(no_lat)}个")
    check(len(no_lng) == 0, f"所有站点应有lng字段", f"缺失: {len(no_lng)}个")
    if len(no_lat) > 0:
        report_fail("站点经纬度缺失", f"{len(no_lat)}个站点缺少lat, {len(no_lng)}个缺少lng")
    
    check(len(offline) <= site_count * 0.5, f"离线站点 {len(offline)}/{site_count}")
    
    types = Counter(s.get("type","") for s in sites)
    print(f"  站点类型分布: {dict(types)}")
    
    levels = Counter(s.get("level","") for s in sites)
    print(f"  站点等级分布: {dict(levels)}")
    
    print(f"  示例站点字段: {list(sites[0].keys())}")
else:
    check(False, f"站点数据加载失败", f"count={site_count}")
    report_fail("站点数据加载", f"count={site_count}")

# ============================================================
section("2. 站点设备状态")
# ============================================================
for sid in [1, 10, 50, 100, 200]:
    devices = get(f"{BASE}/site/status/{sid}")
    if isinstance(devices, dict):
        dev_list = devices.get("devices", [])
        site_name = "?"
        if isinstance(sites, list):
            for s in sites:
                if s.get("id") == sid:
                    site_name = s.get("name", "?")
                    break
        print(f"  站点#{sid} ({site_name}): 设备数={len(dev_list)}")
        if dev_list:
            for d in dev_list[:3]:
                print(f"    - {d.get('name','?')}: status={d.get('status','?')} type={d.get('type','?')}")
        else:
            print(f"    (无设备信息)")
    else:
        print(f"  站点#{sid}: 非dict格式")

# ============================================================
section("3. 告警相关")
# ============================================================
alerts = get(f"{BASE}/alerts")
alert_count = len(alerts) if isinstance(alerts, list) else 0
summary_line("告警总数", alert_count)

alert_stats = get(f"{BASE}/alerts/stats")
print(f"  告警统计原始数据:")
print(f"    {json.dumps(alert_stats, ensure_ascii=False, indent=2)[:800]}")

if isinstance(alerts, list) and isinstance(alert_stats, dict):
    stats = alert_stats
    total = stats.get("total", 0)

    check(total == alert_count,
          f"stats.total ({total}) == alert列表长度 ({alert_count})")
    if total != alert_count:
        report_fail("告警总数不一致", f"stats.total={total}, 列表length={alert_count}")

    pending = stats.get("pending", 0)
    ack = stats.get("acknowledged", 0)
    pending_review = stats.get("pending_review", 0)
    resolved = stats.get("resolved", 0)
    sum_status = pending + ack + pending_review + resolved
    check(abs(sum_status - total) <= 5,
          f"状态之和 ({sum_status}) ≈ total ({total})",
          f"pending={pending} acknowledged={ack} pending_review={pending_review} resolved={resolved}")
    if abs(sum_status - total) > 5:
        report_fail("告警状态数和不等于总数", f"sum={sum_status}, total={total}")

    by_cat = stats.get("by_category", {})
    if by_cat:
        cat_total = sum(by_cat.values())
        check(cat_total == total,
              f"by_category之和 ({cat_total}) == total ({total})",
              f"categories: {json.dumps(by_cat, ensure_ascii=False)}")
        if cat_total != total:
            report_fail("告警by_category数和不等于总数", f"cat_sum={cat_total}, total={total}")
    else:
        print("  [WARN] 无by_category数据")

    today_str = date.today().isoformat()
    today_alerts = [a for a in alerts if a.get("created_at","").startswith(today_str)]
    today_from_stats = stats.get("today", 0)
    check(today_from_stats == len(today_alerts),
          f"stats.today ({today_from_stats}) == 今天告警数 ({len(today_alerts)})")
    if today_from_stats != len(today_alerts):
        report_fail("today告警数不一致", f"stats.today={today_from_stats}, 实际={len(today_alerts)}")

    # 随机抽样告警
    sample_n = min(5, len(alerts))
    sample = random.sample(alerts, sample_n) if sample_n > 0 else []
    print(f"\n  告警抽样检查 ({sample_n}条):")
    for a in sample:
        aid = a.get("id", "?")
        sn = a.get("site_name", "")
        ca = a.get("created_at", "")
        lv = a.get("level", "")
        msg = a.get("message", "")
        ft = a.get("flow_type", "?")
        fs = a.get("flow_status", "?")
        ron = a.get("related_order_no", "")
        check(bool(sn), f"A#{aid}: site_name有值", f"site_name='{sn}'")
        check(bool(ca), f"A#{aid}: created_at有值", f"created_at='{ca}'")
        check(bool(lv), f"A#{aid}: level有值", f"level='{lv}'")
        check(len(msg) > 5, f"A#{aid}: message描述完整", f"msg='{msg[:60]}'")
        if ft == "auto" and fs == "converted":
            check(bool(ron), f"A#{aid}: auto+converted应有related_order_no", f"ron='{ron}'")
        print(f"      id={aid} site={sn} level={lv} flow={ft}/{fs} ron={ron}")
else:
    check(False, "告警数据加载失败", str(type(alerts)))
    report_fail("告警数据加载", str(type(alerts)))

# ============================================================
section("4. 工单相关")
# ============================================================
workorders = get(f"{BASE}/workorders")
wo_count = len(workorders) if isinstance(workorders, list) else 0
summary_line("工单总数", wo_count)

wo_stats = get(f"{BASE}/workorders/statistics")
print(f"  工单统计原始数据:")
print(f"    {json.dumps(wo_stats, ensure_ascii=False, indent=2)[:800]}")

if isinstance(workorders, list) and isinstance(wo_stats, dict):
    by_status = wo_stats.get("by_status", {})
    if by_status:
        status_sum = sum(by_status.values())
        check(status_sum == wo_count,
              f"by_status之和 ({status_sum}) == 工单总数 ({wo_count})",
              f"by_status: {json.dumps(by_status, ensure_ascii=False)}")
        if status_sum != wo_count:
            report_fail("工单状态数和不等于总数", f"sum={status_sum}, total={wo_count}")
    else:
        print("  [WARN] 无by_status数据")

    closed_count = by_status.get("closed", 0) if by_status else 0
    check(closed_count > 2, f"应有已关闭工单", f"closed={closed_count}")
    if closed_count <= 2 and wo_count > 0:
        report_fail("工单关闭数过少", f"closed={closed_count}, total={wo_count}")

    sla = wo_stats.get("sla", {})
    if sla:
        print(f"  SLA统计: {json.dumps(sla, ensure_ascii=False, indent=2)}")
    else:
        print("  [WARN] 无SLA数据")

    # 检查site_id一致性
    site_levels = {}
    if isinstance(sites, list):
        site_levels = {s.get("id"): s.get("level", "") for s in sites}
    mismatches = []
    for wo in workorders[:30]:
        wid = wo.get("id")
        wsid = wo.get("site_id")
        wlvl = wo.get("level", "")
        slvl = site_levels.get(wsid, "")
        if slvl and wlvl != slvl:
            mismatches.append(f"WO#{wid}: site#{wsid} level={slvl}, WO level={wlvl}")
    check(len(mismatches) == 0, f"工单level与站点level一致（抽样30条）",
          "\n".join(mismatches[:10]))
    if len(mismatches) > 0:
        report_fail("工单level与站点level不一致", f"共{len(mismatches)}条不匹配")

    print(f"\n  工单抽样:")
    for wo in workorders[:5]:
        wo_info = {k: wo.get(k) for k in ("id","site_id","level","status","title","created_at")}
        print(f"    {json.dumps(wo_info, ensure_ascii=False)}")
else:
    if isinstance(workorders, dict) and workorders.get("_auth_error"):
        check(False, "工单API认证失败", "请检查token有效性")
        report_fail("工单API认证失败", "")
    elif wo_count == 0:
        check(False, "工单列表为空")
    else:
        check(False, "工单数据格式异常", str(type(workorders)))

# ============================================================
section("5. 巡检相关")
# ============================================================
inspections = get(f"{BASE}/inspections")
insp_count = len(inspections) if isinstance(inspections, list) else 0
summary_line("巡检计划数", insp_count)

insp_stats = get(f"{BASE}/inspections/statistics")
print(f"  巡检统计原始数据:")
print(f"    {json.dumps(insp_stats, ensure_ascii=False, indent=2)[:500]}")

if isinstance(insp_stats, dict):
    total = insp_stats.get("total", 0)
    completed = insp_stats.get("completed", 0)
    rate = insp_stats.get("completion_rate", 0)
    check(total == insp_count,
          f"inspStats.total ({total}) == 巡检计划数 ({insp_count})")
    if total != insp_count:
        report_fail("巡检总数不一致", f"stats.total={total}, actual={insp_count}")
    if total > 0:
        calc_rate = completed / total * 100
        check(abs(rate - calc_rate) < 0.5,
              f"完成率一致: stats={rate}%, 计算={calc_rate:.1f}%")
        if abs(rate - calc_rate) >= 0.5:
            report_fail("巡检完成率计算不一致", f"stats={rate}%, 计算={calc_rate:.1f}%")
    else:
        check(False, "巡检计划总数为0，数据异常")
        report_fail("巡检计划总数为0", "")

# ============================================================
section("6. 数据到达率")
# ============================================================
arrival = get(f"{BASE}/data/arrival/summary")
print(f"  到达率原始数据:")
print(f"    {json.dumps(arrival, ensure_ascii=False, indent=2)[:800]}")

if isinstance(arrival, dict):
    total_avg = arrival.get("total_avg", -1)
    check(0 <= total_avg <= 100,
          f"total_avg ({total_avg}) 在0-100范围内")
    if not (0 <= total_avg <= 100):
        report_fail("total_avg超出0-100范围", str(total_avg))

    by_type = arrival.get("by_type", {})
    if by_type:
        print(f"  各站型到达率:")
        for t, v in by_type.items():
            rate = v.get("rate", -1)
            ok = "OK" if 0 <= rate <= 100 else "异常"
            print(f"    {t}: rate={rate}% ({ok})")
            if not (0 <= rate <= 100):
                report_fail(f"{t}到达率异常", f"rate={rate}%")
    
    by_metric = arrival.get("by_metric", [])
    if by_metric:
        print(f"  各指标到达率:")
        for m in by_metric:
            print(f"    {m.get('metric')}: avg_rate={m.get('avg_rate')}% sites={m.get('site_count')} below_threshold={m.get('below_threshold')}")
else:
    check(False, "数据到达率格式异常")
    report_fail("数据到达率格式", str(type(arrival)))

# ============================================================
section("7. 传感器数据")
# ============================================================
sensor = get(f"{BASE}/data/site/1?limit=20")
if isinstance(sensor, list):
    print(f"  传感器数据条数: {len(sensor)}")
    if sensor:
        print(f"  字段: {list(sensor[0].keys())}")
        metrics = Counter(s.get("metric","") for s in sensor)
        print(f"  指标分布: {dict(metrics)}")
        for s in sensor[:5]:
            print(f"    {json.dumps(s, ensure_ascii=False)}")
elif isinstance(sensor, dict):
    data_list = sensor.get("data", sensor.get("records", []))
    print(f"  传感器数据条数: {len(data_list)}")
    if data_list:
        print(f"  字段: {list(data_list[0].keys())}")
        for s in data_list[:5]:
            print(f"    {json.dumps(s, ensure_ascii=False)}")
else:
    check(False, f"传感器数据格式异常", str(sensor)[:200])
    report_fail("传感器数据格式", str(type(sensor)))

# ============================================================
section("8. 告警-工单交叉关联检查")
# ============================================================
if isinstance(alerts, list) and isinstance(workorders, list) and len(alerts) > 0 and len(workorders) > 0:
    wo_map = {}
    for wo in workorders:
        wo_map[str(wo.get("id"))] = wo

    broken_refs = []
    site_mismatch = []
    matched_refs = 0
    for a in alerts:
        ron = a.get("related_order_no")
        if ron:
            ron_str = str(ron)
            if ron_str not in wo_map:
                broken_refs.append(f"A#{a.get('id')}: related_order_no={ron} 工单不存在")
            else:
                matched_refs += 1
                target = wo_map[ron_str]
                at = target.get("site_id")
                if at and a.get("site_id") and at != a.get("site_id"):
                    site_mismatch.append(
                        f"A#{a.get('id')}(site={a.get('site_id')}) -> "
                        f"WO#{ron}(site={at}) 站点不一致")

    check(len(broken_refs) == 0, f"related_order_no引用有效，{len(broken_refs)}个断链",
          "\n".join(broken_refs[:10]))
    if len(broken_refs) > 0:
        report_fail("告警工单关联断链", f"{len(broken_refs)}个告警引用了不存在的工单号")
    
    check(len(site_mismatch) == 0, f"告警与工单的site_id一致",
          "\n".join(site_mismatch[:5]))
    if len(site_mismatch) > 0:
        report_fail("告警-工单site_id不匹配", f"{len(site_mismatch)}条")
    
    print(f"  关联引用总数: 告警中有related_order_no的={len([a for a in alerts if a.get('related_order_no')])}")
    print(f"  成功匹配: {matched_refs}")
else:
    print(f"  跳过关联检查 (alerts={len(alerts) if isinstance(alerts,list) else 'N/A'}, workorders={len(workorders) if isinstance(workorders,list) else 'N/A'})")

# ============================================================
section("9. 告警等级与数据质量检查")
# ============================================================
if isinstance(alerts, list) and len(alerts) > 0:
    bad_levels = [a for a in alerts if a.get("level") not in ("critical", "warning", "info")]
    check(len(bad_levels) == 0,
          f"告警level字段在有效范围内 (critical/warning/info)",
          f"异常level值: {set(a.get('level','?') for a in bad_levels[:10])}")
    if len(bad_levels) > 0:
        report_fail("告警level异常", f"发现非标准level值")

    no_site = [a for a in alerts if not a.get("site_id")]
    check(len(no_site) == 0, f"所有告警应有site_id", f"无site_id: {len(no_site)}个")
    if len(no_site) > 0:
        report_fail("告警缺少site_id", f"{len(no_site)}个")

    # 检查message是否包含有用信息
    empty_msg = [a for a in alerts if not a.get("message") or len(a.get("message","").strip()) < 3]
    check(len(empty_msg) == 0, f"所有告警message描述完整",
          f"message过短的告警: {len(empty_msg)}个")
    if len(empty_msg) > 0:
        report_fail("告警message为空或过短", f"{len(empty_msg)}个告警message不足3字符")

# ============================================================
section("10. 审计异常汇总")
# ============================================================
if len(failed_checks) == 0:
    print("  所有检查项均通过，未发现数据异常。")
else:
    print(f"  发现 {len(failed_checks)} 个异常项:\n")
    for name, desc in failed_checks:
        print(f"    [FAIL] {name}")
        if desc:
            print(f"           详情: {desc}")
    print(f"\n  以上异常项需要前端开发人员或后端开发人员确认是否为预期行为。")

print(f"\n  审计时间: {datetime.now().isoformat()}")
print(f"  API基础URL: {BASE}")
