#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""园区/政企工单分派与 SLA 预警（离线规则引擎 · 含安全兜底与鲁棒性测试）

四个要点：
1. 安全类工单（消防/电气/电梯困人/燃气）强制 P1 且**必须人工确认**，规则不自动派单；
2. 一单多问题识别：命中 ≥2 类时输出主类 + 关联类，进人工确认队列；
3. SLA 按**工作日历**计算（9:00–18:00、跳过周末），自然小时会把周末算进去，承诺就失真；
4. 噪声鲁棒性测试：对标题做错别字/语音转写丢字扰动，公开「干净集 vs 噪声集」两个准确率。

用法：python3 main.py
输出：out/report.md
"""
import csv, os, random, time
from collections import defaultdict, Counter
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
OUT = os.path.join(os.path.dirname(BASE), "out")

# 类型 → (责任班组, SLA 工时, 关键词, 是否安全类)
RULES = {
    "网络故障": ("网络组", 4, ["断网", "掉线", "网速", "路由器", "交换机", "wifi", "上网"], False),
    "门禁道闸": ("安防组", 4, ["门禁", "闸机", "刷卡", "人脸", "道闸", "开门"], False),
    "空调暖通": ("设施组", 8, ["空调", "制冷", "不冷", "新风", "风机盘管"], False),
    "消防设施": ("安防组", 2, ["消防", "烟感", "喷淋", "火警", "应急灯"], True),
    "会议设备": ("弱电组", 4, ["投影", "会议", "音响", "话筒", "视频会议", "大屏"], False),
    "账号权限": ("信息组", 8, ["账号", "密码", "权限", "登录", "开通", "oa"], False),
    "水电照明": ("设施组", 8, ["跳闸", "停电", "灯不亮", "插座", "电箱", "水管", "漏水"], True),
    "环境保洁": ("物业组", 24, ["保洁", "垃圾", "异味", "打扫", "绿化"], False),
}

# 安全词：出现即 P1 + 人工确认，任何规则都不能自动派
SAFETY_WORDS = ["冒烟", "起火", "火花", "漏电", "触电", "燃气", "煤气", "困人", "电梯停",
                "冒火", "烧焦", "爆", "坠落", "夹人"]
HIGH_WORDS = ["全楼", "整栋", "整层", "多个", "领导", "会议中", "停产", "无法办公", "全部"]

DESCS = [
 ("B座3楼整层断网，无法办公", "网络故障"),
 ("前台闸机刷脸没反应，排队了", "门禁道闸"),
 ("会议室投影没信号，10分钟后有客户来访", "会议设备"),
 ("2号厂房空调不制冷", "空调暖通"),
 ("消防主机报火警，位置在5楼走廊", "消防设施"),
 ("新员工OA账号登不上", "账号权限"),
 ("食堂插座跳闸，冰箱停了", "水电照明"),
 ("3楼卫生间有异味", "环境保洁"),
 ("研发区网速很慢，多个同事反馈", "网络故障"),
 ("地库道闸抬不起来，车堵在入口", "门禁道闸"),
 ("会议室话筒没声音", "会议设备"),
 ("车间水管漏水，地面积水", "水电照明"),
 ("消防应急灯不亮", "消防设施"),
 ("密码重置后还是登不上", "账号权限"),
 ("走廊灯不亮", "水电照明"),
 ("楼下垃圾桶满了没人收", "环境保洁"),
 ("整栋楼断网，交换机指示灯全灭", "网络故障"),
 ("人脸门禁识别变慢", "门禁道闸"),
 ("大屏黑屏，会议中", "会议设备"),
 ("空调外机噪音很大", "空调暖通"),
 ("配电箱冒烟，有烧焦味", "水电照明"),
 ("3号电梯困人，按了警铃没人应", "水电照明"),
 ("食堂后厨闻到煤气味", "水电照明"),
 ("2楼走廊配电箱打火花", "水电照明"),
]

# 故意制造的「一单多问题」：主问题 + 关联问题
MULTI = [
 ("会议室投影黑屏，同时空调不制冷", "会议设备"),
 ("车间断网，监控大屏也黑屏", "网络故障"),
 ("楼层跳闸后门禁全失效", "水电照明"),
]

# 噪声映射：错别字 + 语音转写常见替换
NOISE_MAP = {"跳闸": "调闸", "断网": "段网", "空调": "空凋", "消防": "肖防",
             "漏水": "漏谁", "门禁": "门近", "插座": "查座", "投影": "头影",
             "账号": "帐号", "保洁": "保结", "电梯": "电剃", "燃气": "然气"}


def ensure_data(n=40, seed=7):
    os.makedirs(DATA, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(DATA, "tickets.csv")
    if os.path.exists(p):
        return p
    random.seed(seed)
    base = datetime(2026, 11, 2, 9, 0)
    rows = [["ticket_id", "title", "submitter", "submit_time", "true_type"]]
    pool = [(t, k) for t, k in DESCS] + [(t, k) for t, k in MULTI]
    for i in range(1, n + 1):
        t, k = pool[(i - 1) % len(pool)]
        rows.append(["T%03d" % i, t, "员工%d" % (10 + i % 30),
                     (base + timedelta(hours=i * 5, minutes=(i * 7) % 60)).strftime("%Y-%m-%d %H:%M"), k])
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerows(rows)
    return p


def classify(text):
    """返回 (主类型, 命中数, 全部命中类型列表)"""
    hit = []
    for typ, (_, _, kws, _s) in RULES.items():
        c = sum(1 for k in kws if k.lower() in text.lower())
        if c:
            hit.append((c, typ))
    hit.sort(reverse=True)
    if not hit:
        return "其他", 0, []
    return hit[0][1], hit[0][0], [h[1] for h in hit]


def priority(text, typ, multi):
    is_safety = typ in [k for k, v in RULES.items() if v[3]] and any(w in text for w in SAFETY_WORDS)
    if any(w in text for w in SAFETY_WORDS):
        return "P1", True, "命中安全词（%s）" % "、".join(w for w in SAFETY_WORDS if w in text)
    if typ == "消防设施":
        return "P1", True, "消防类强制 P1"
    if any(w in text for w in HIGH_WORDS):
        return "P1", True, "影响范围大（%s）" % "、".join(w for w in HIGH_WORDS if w in text)
    if multi:
        return "P2", True, "一单多问题，需人工确认主次"
    if any(w in text for w in ["漏水", "跳闸", "黑屏", "堵", "没反应"]):
        return "P2", False, "局部影响"
    return "P3", False, "一般"


# ---------- 工作日历（9:00–18:00，周一至周五） ----------
WORK_START, WORK_END = 9, 18


def is_workday(d):
    return d.weekday() < 5


def work_hours_between(a, b):
    if b <= a:
        return 0.0
    total = 0.0
    d = a.replace(hour=0, minute=0, second=0, microsecond=0)
    while d <= b:
        if is_workday(d):
            ws = d.replace(hour=WORK_START)
            we = d.replace(hour=WORK_END)
            s = max(a, ws)
            e = min(b, we)
            if e > s:
                total += (e - s).total_seconds() / 3600.0
        d += timedelta(days=1)
    return total


def add_work_hours(start, hours):
    cur = start
    remain = hours
    while remain > 0:
        if not is_workday(cur):
            cur = (cur + timedelta(days=1)).replace(hour=WORK_START, minute=0)
            continue
        if cur.hour < WORK_START:
            cur = cur.replace(hour=WORK_START, minute=0)
        if cur.hour >= WORK_END:
            cur = (cur + timedelta(days=1)).replace(hour=WORK_START, minute=0)
            continue
        avail = (cur.replace(hour=WORK_END) - cur).total_seconds() / 3600.0
        step = min(avail, remain)
        cur += timedelta(hours=step)
        remain -= step
        if remain > 0:
            cur = (cur + timedelta(days=1)).replace(hour=WORK_START, minute=0)
    return cur


def noisy(text, rate=0.5):
    for k, v in NOISE_MAP.items():
        if k in text and random.random() < rate:
            text = text.replace(k, v)
    if random.random() < 0.4:                 # 语音转写丢字
        cut = max(1, int(len(text) * 0.15))
        text = text[:len(text) - cut]
    return text


def main():
    t0 = time.time()
    p = ensure_data()
    rows = list(csv.DictReader(open(p, encoding="utf-8-sig")))
    now = datetime(2026, 11, 4, 18, 0)

    out, noisy_out = [], []
    for r in rows:
        text = r["title"]
        typ, hits, all_typ = classify(text)
        lv, need_human, why = priority(text, typ, len(all_typ) >= 2)
        team, sla, _, _s = RULES.get(typ, ("综合组", 24, [], False))
        st = datetime.strptime(r["submit_time"], "%Y-%m-%d %H:%M")
        used = work_hours_between(st, now)
        out.append({"id": r["ticket_id"], "typ": typ, "team": team, "level": lv, "sla": sla,
                    "submit": r["submit_time"], "used": used, "overdue": used > sla,
                    "true": r["true_type"], "hits": hits, "title": text,
                    "human": need_human, "why": why, "multi": len(all_typ) >= 2,
                    "related": [t for t in all_typ[1:]]})
        random.seed(11)
        nt = noisy(text)
        ntyp, _, nall = classify(nt)
        noisy_out.append({"id": r["ticket_id"], "typ": ntyp, "true": r["true_type"], "text": nt})

    acc = sum(1 for o in out if o["typ"] == o["true"]) / len(out)
    acc_noisy = sum(1 for o in noisy_out if o["typ"] == o["true"]) / len(noisy_out)
    auto_ratio = sum(1 for o in out if not o["human"]) / len(out)
    team_load = Counter(o["team"] for o in out)
    lvl = Counter(o["level"] for o in out)
    overdue = [o for o in out if o["overdue"]]
    human_q = [o for o in out if o["human"]]

    L = ["# 工单分派与 SLA 预警报告（规则引擎 · 含安全兜底与噪声测试）\n"]
    L.append("工单量：%d ｜ 规则类型：%d 类 ｜ 快照时间：2026-11-04 18:00 ｜ SLA 口径：工作日 9:00–18:00\n"
             % (len(out), len(RULES)))

    L.append("\n## 一、总体指标（干净集与噪声集分开报）\n")
    L.append("| 指标 | 数值 | 口径 |")
    L.append("|---|---|---|")
    L.append("| 分派准确率（原始标题） | %.1f%% | 与人工标注比对 |" % (acc * 100))
    L.append("| 分派准确率（错别字/语音转写扰动） | %.1f%% | 同一批工单加噪后重测 |" % (acc_noisy * 100))
    L.append("| 准确率衰减 | -%.1f 个百分点 | 噪声代价，必读 |" % (acc * 100 - acc_noisy * 100))
    L.append("| 自动派单比例 | %.1f%% | 无需人工确认的工单 |" % (auto_ratio * 100))
    L.append("| 人工确认队列 | %d 条 | 安全类 / 大范围 / 一单多问题 |" % len(human_q))
    L.append("| P1 工单 | %d 条 | 全部进人工确认，不自动派 |" % lvl["P1"])
    L.append("| SLA 已超时 | %d 条 | 按工作日历累计工时 |" % len(overdue))
    L.append("| 全量处理耗时 | %.3f 秒 | 本地，%d 单 |" % (time.time() - t0, len(out)))

    L.append("\n**噪声测试怎么做的**：对标题做错别字替换（跳闸→调闸、断网→段网、消防→肖防…）"
             "并模拟语音转写丢字（截掉尾部 15%），再跑同一套规则。这一栏是这套方案最诚实的部分——"
             "规则引擎在真实文本上一定会掉点，掉多少必须先知道，才敢承诺 SLA。")

    L.append("\n## 二、必须人工确认的工单（安全底线，不自动派）\n")
    L.append("| 工单 | 标题 | 判定 | 原因 | 关联问题 |")
    L.append("|---|---|---|---|---|")
    for o in human_q[:14]:
        L.append("| %s | %s | %s | %s | %s |"
                 % (o["id"], o["title"], o["level"], o["why"], "、".join(o["related"]) or "—"))

    L.append("\n## 三、班组负载\n")
    L.append("| 班组 | 工单数 | 占比 |")
    L.append("|---|---|---|")
    for t, c in team_load.most_common():
        L.append("| %s | %d | %.0f%% |" % (t, c, c * 100.0 / len(out)))

    L.append("\n## 四、SLA 超时清单（工作日历口径，跳过周末与夜间）\n")
    L.append("| 工单 | 类型 | 标题 | 提交 | 已耗工时 | SLA | 状态 |")
    L.append("|---|---|---|---|---|---|---|")
    for o in overdue[:12]:
        L.append("| %s | %s | %s | %s | %.1fh | %dh | 已超时 |"
                 % (o["id"], o["typ"], o["title"], o["submit"], o["used"], o["sla"]))

    L.append("\n## 五、分派错误清单（干净集）\n")
    mis = [o for o in out if o["typ"] != o["true"]]
    if not mis:
        L.append("无。")
    else:
        L.append("| 工单 | 标题 | 系统判定 | 人工标注 | 原因 |")
        L.append("|---|---|---|---|---|")
        for o in mis:
            L.append("| %s | %s | %s | %s | 关键词命中 %d 个，跨类冲突 |"
                     % (o["id"], o["title"], o["typ"], o["true"], o["hits"]))

    L.append("\n## 六、噪声集失败样例（这些才是现场真正会发生的）\n")
    nfail = [o for o in noisy_out if o["typ"] != o["true"]]
    L.append("| 工单 | 扰动后文本 | 系统判定 | 应为 |")
    L.append("|---|---|---|---|")
    for o in nfail[:8]:
        L.append("| %s | %s | %s | %s |" % (o["id"], o["text"], o["typ"], o["true"]))

    L.append("\n## 七、这套方案的边界\n")
    for x in ["安全类工单（消防/电气/电梯困人/燃气）永不自动派单，规则只做分拣与升级提醒。",
              "噪声集准确率明显低于干净集，说明现场必须配「同义词+错别字纠正表」，且每周从误派清单补词。",
              "规则引擎适用到日均 100 单左右；再往上、或一单多问题占比 >20% 时，应换分类模型 + 人工复核双轨。",
              "本报告的分派数据为构造样例，签约为准前必须在客户真实工单上跑一轮（至少 200 单）再定 SLA。"]:
        L.append("- " + x)

    md = "\n".join(L)
    with open(os.path.join(OUT, "report.md"), "w", encoding="utf-8") as f:
        f.write(md)
    print(md)


if __name__ == "__main__":
    main()
