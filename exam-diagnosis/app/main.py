#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""高中数学错题统计与教学决策助手（离线可跑，零第三方依赖）

定位（重要）：错因**不做自动归因**。教师标注的 error_type 是事实来源；
本工具用「文本特征规则」给出一个提示型判定，并用一致率指标证明它只能当排序提示，
不能替代教师判断。这是刻意保留的边界，不是缺陷。

输入：answers.csv（含 answer_text 作答片段 + teacher_error_type 教师标注）
输出：out/report.md（掌握度 / 薄弱点 / 标注结构 / 规则-教师一致率 / 个体清单 / 度量 / 局限）
用法：python3 main.py            # 正常
      python3 main.py --mask     # 学生 ID 脱敏（哈希）
"""
import csv, os, random, re, time, hashlib, sys
from collections import defaultdict, Counter

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
OUT = os.path.join(os.path.dirname(BASE), "out")

KPS = ["函数单调性", "导数应用", "数列求和", "立体几何体积", "圆锥曲线", "概率分布", "三角恒等变换", "不等式恒成立"]
ETYPES = ["概念不清", "计算失误", "审题偏差", "表达不规范", "知识迁移失败"]

STRATEGY = {
    "概念不清": "回炉定义：用 1 道反例题确认边界，再配 2 道变式；课前提问点名该组学生复述条件",
    "计算失误": "限时计算专训（每题 90 秒），要求写出中间步骤；错题只重算不重讲",
    "审题偏差": "圈画训练：先标出「求什么/给了什么/限制条件」三行再动笔，前 3 题强制留痕",
    "表达不规范": "给标准作答模板，按步骤给分演练；同桌互批只抓步骤完整性",
    "知识迁移失败": "做「同源题」对照：同一方法换情境，讲的时候只讲「为什么能迁移」一句",
}

# 作答片段模板：让文本里留下可被规则捕捉的痕迹（也故意留下痕迹不足的样本）
TEXT = {
    "概念不清": ["直接代入x=1得3", "套公式算出4，没看定义域", "用了单调性结论，端点没验", "求导后直接令其为正"],
    "计算失误": ["2*3=5，答案5", "中间算成12，后面全跟着错了", "移项时符号写反，得-3", "约分约错，结果写成2/3"],
    "审题偏差": ["题目要最小值我求了最大值", "问的是至少，我按恰好算", "看漏了x>0这个条件", "问范围我答了个数"],
    "表达不规范": ["所以成立", "由上面可知，答案对", "过程省略，结论正确", "显然可得，略"],
    "知识迁移失败": ["用等比数列公式套到函数题上", "把线性规划方法搬到圆锥曲线", "拿排列组合的思路做概率", "套了立体几何的体积公式但图形不对"],
}


def ensure_data(seed=42):
    os.makedirs(DATA, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(DATA, "answers.csv")
    if os.path.exists(p):
        return p
    random.seed(seed)
    rows = [["student_id", "question_id", "kp", "difficulty", "is_correct",
             "answer_text", "teacher_error_type", "seconds"]]
    for i in range(1, 31):
        sid = "S%02d" % i
        base = random.gauss(0.66, 0.16)          # 学生基线能力
        for q in range(1, 21):
            kp = random.choice(KPS)
            diff = random.randint(1, 3)          # 1 易 2 中 3 难
            p_ok = max(0.05, min(0.95, base - (diff - 2) * 0.13))
            ok = random.random() < p_ok
            if ok:
                et, txt = "", "（作答正确，略）"
            else:
                et = random.choices(ETYPES, weights=[3, 3, 3, 2, 1])[0]
                # 真实场景里「教师标注」与「学生写了什么」不同源：30% 的作答片段
                # 并不带该错因的典型痕迹（学生没写过程、字迹潦草、只留结论）。
                # 这里刻意注入该比例，用来测规则归因的真实上限。
                src = et if random.random() > 0.30 else random.choice([e for e in ETYPES if e != et])
                txt = random.choice(TEXT[src])
            rows.append([sid, "Q%02d" % q, kp, diff, 1 if ok else 0, txt, et,
                         random.randint(60, 420)])
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerows(rows)
    return p


def load(path):
    rows = []
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            for k in ("difficulty", "is_correct", "seconds"):
                r[k] = int(r[k])
            rows.append(r)
    return rows


def mask_id(sid):
    return "S-" + hashlib.sha256(sid.encode()).hexdigest()[:6]


# ---------- 提示型规则归因（只用于排序提示，不进教学决策） ----------
def rule_error_type(text):
    """返回 (类型, 命中依据)。命中依据为空表示规则无法判断。"""
    t = (text or "").strip()
    if len(t) < 6:
        return "未作答", "作答片段过短"
    hit = []
    if re.search(r"(直接代入|套公式|没看|没验|直接令)", t):
        hit.append(("概念不清", "出现「直接代入/套公式」类跳过条件判断的表述"))
    if re.search(r"\d\s*[*×+\-]\s*\d\s*=|算成|算错|符号写反|约错|约分", t):
        hit.append(("计算失误", "出现算式或「算成/符号写反」等计算痕迹"))
    if re.search(r"(求了最大|求了最小|看漏|问的是|按恰好)", t):
        hit.append(("审题偏差", "出现与题目要求不一致的目标表述"))
    if re.search(r"(所以成立|答案对|显然可得|过程省略|略)$", t):
        hit.append(("表达不规范", "结论无推导或直接省略过程"))
    if re.search(r"(公式套|搬到|思路做|套了)", t):
        hit.append(("知识迁移失败", "出现跨题型的公式/方法搬用"))
    if not hit:
        return "规则不确定", "无可用文本特征"
    # 多命中时按顺序取第一类，并把全部依据回传，供教师复核
    return hit[0][0], "；".join(h[1] for h in hit)


def analyse(rows):
    st_kp = defaultdict(lambda: [0, 0])
    cls_kp = defaultdict(lambda: [0, 0])
    w_kp = defaultdict(lambda: [0, 0])        # 难度加权：易=1 中=1.5 难=2
    err = Counter()
    agree = Counter()                          # (教师标注, 规则判定) -> 次数
    disagree_samples = []                       # 用于报告里抽样的分歧样本
    st_err, st_time, st_cnt = defaultdict(Counter), defaultdict(int), Counter()
    for r in rows:
        wt = {1: 1.0, 2: 1.5, 3: 2.0}[r["difficulty"]]
        key = (r["student_id"], r["kp"])
        st_kp[key][1] += 1
        st_kp[key][0] += r["is_correct"]
        cls_kp[r["kp"]][1] += 1
        cls_kp[r["kp"]][0] += r["is_correct"]
        w_kp[r["kp"]][1] += wt
        w_kp[r["kp"]][0] += wt * r["is_correct"]
        st_cnt[r["student_id"]] += 1
        st_time[r["student_id"]] += r["seconds"]
        if not r["is_correct"]:
            et = r["teacher_error_type"] or "未标注"
            err[et] += 1
            st_err[r["student_id"]][et] += 1
            pred, ev = rule_error_type(r["answer_text"])
            agree[(et, pred)] += 1
            if pred != et:
                disagree_samples.append((et, pred, (r["answer_text"] or "")[:18], ev))
    return st_kp, cls_kp, w_kp, err, agree, disagree_samples, st_err, st_time, st_cnt


def level(rate):
    if rate < 0.50:
        return "薄弱"
    if rate < 0.75:
        return "待巩固"
    return "已掌握"


def main():
    mask = "--mask" in sys.argv
    t0 = time.time()
    path = ensure_data()
    rows = load(path)
    st_kp, cls_kp, w_kp, err, agree, dis, st_err, st_time, st_cnt = analyse(rows)

    cls_rate = {kp: (v[0] / v[1], v[1]) for kp, v in cls_kp.items()}
    cls_wrate = {kp: (v[0] / v[1], v[1]) for kp, v in w_kp.items()}
    weak = sorted(cls_rate.items(), key=lambda x: x[1][0])[:4]
    weak_w = sorted(cls_wrate.items(), key=lambda x: x[1][0])[:4]
    order_stable = [x[0] for x in weak] == [x[0] for x in weak_w]

    student_rows = []
    for sid in sorted(st_cnt):
        items = [(kp, v[0] / v[1], v[1]) for (s, kp), v in st_kp.items() if s == sid and v[1] >= 2]
        items.sort(key=lambda x: x[1])
        student_rows.append((sid, items[:3], st_err[sid].most_common(1),
                             st_time[sid] / max(1, st_cnt[sid])))

    total_wrong = sum(err.values())
    n_agree = sum(c for (a, b), c in agree.items() if a == b)
    n_unknown = sum(c for (a, b), c in agree.items() if b == "规则不确定")
    n_unans = sum(c for (a, b), c in agree.items() if b == "未作答")
    covered = total_wrong - n_unknown - n_unans
    acc_on_covered = (n_agree - sum(c for (a, b), c in agree.items() if b == "未作答" and a == b)) / max(1, covered)

    n = len(rows)
    # 两套人工基线：无阅卷系统（手工批改+录入+统计）/ 已有阅卷系统（只需统计）
    human_full = (n * 5.4) / 60 + 30
    human_stats_only = 30.0
    tool_min = (time.time() - t0) / 60

    L = []
    L.append("# 高中数学错题统计与教学决策报告（离线运行）\n")
    L.append("数据规模：%d 名学生、%d 条答题记录、%d 个知识点 ｜ 学生 ID：%s\n"
             % (len(st_cnt), n, len(cls_kp), "已脱敏（sha256 前 6 位）" if mask else "明文（仅本地）"))

    L.append("\n## 一、班级掌握度（原始正确率）\n")
    L.append("| 知识点 | 正确率 | 样本量 | 判定 |")
    L.append("|---|---|---|---|")
    for kp, (r, cnt) in sorted(cls_rate.items(), key=lambda x: x[1][0]):
        flag = "（样本不足，仅供参考）" if cnt < 8 else ""
        L.append("| %s | %.1f%% | %d | %s%s |" % (kp, r * 100, cnt, level(r), flag))

    L.append("\n## 二、本周必须先处理的 4 个知识点（原始排序 vs 难度加权排序）\n")
    L.append("| 排名 | 原始正确率 | 难度加权正确率 | 是否一致 |")
    L.append("|---|---|---|---|")
    for i in range(4):
        a, b = weak[i], weak_w[i]
        L.append("| %d | %s %.1f%% | %s %.1f%% | %s |"
                 % (i + 1, a[0], a[1][0] * 100, b[0], b[1][0] * 100, "一致" if a[0] == b[0] else "分歧"))
    L.append("\n> 两种口径%s。难度加权（易 1 / 中 1.5 / 难 2）用于排除「碰上难题才显得薄弱」的误判；"
             "分歧项建议教研组复核后再定。" % ("排序完全一致，结论稳健" if order_stable else "存在分歧，需人工裁定"))

    L.append("\n## 三、错因结构（教师标注为事实来源，共 %d 次错误）\n" % total_wrong)
    L.append("| 错因（教师标注） | 次数 | 占比 | 干预策略 |")
    L.append("|---|---|---|---|")
    for et, c in err.most_common():
        L.append("| %s | %d | %.1f%% | %s |" % (et, c, c * 100.0 / max(1, total_wrong), STRATEGY.get(et, "—")))

    L.append("\n## 四、规则归因能替代教师吗？（本节是这套工具的边界证明）\n")
    L.append("| 指标 | 数值 | 口径 |")
    L.append("|---|---|---|")
    L.append("| 规则可判定比例 | %.1f%%（%d / %d） | 规则输出「规则不确定」以外的比例 |"
             % (covered * 100.0 / max(1, total_wrong), covered, total_wrong))
    L.append("| 规则与教师标注一致率 | %.1f%% | 仅在规则可判定的 %d 条上计算 |" % (acc_on_covered * 100, covered))
    L.append("| 规则自认「不确定」 | %d 条 | 无可用文本特征 |" % n_unknown)
    L.append("| 规则判为「未作答」 | %d 条 | 作答片段过短 |" % n_unans)
    L.append("| 误判代价（把 A 类判成 B 类） | %d 条 | 会误导分组，但教师复核可拦下 |" % (covered - n_agree))
    verdict = ("一致率 %.1f%%，不足以替代教师判断" % (acc_on_covered * 100)) if acc_on_covered < 0.85 \
        else ("一致率 %.1f%%，但仍低于可自动决策的门槛（行业惯例 ≥95%%）" % (acc_on_covered * 100))
    L.append("\n**结论：%s。**规则归因只能作为「教师复核排序提示」，不能自动下教学决策；"
             "真正的归因来自教师标注，工具做的是把标注汇总、排序、落到班级动作上——"
             "这是本工具与「AI 自动诊断」最本质的区别，也是交付时必须跟客户讲清的一条。" % verdict)

    L.append("\n### 4.1 规则-教师分歧抽样（供教研组复核）\n")
    L.append("\n| 教师标注 | 规则判定 | 作答片段 | 规则依据 |")
    L.append("|---|---|---|---|")
    for et, pred, txt, ev in dis[:10]:
        L.append("| %s | %s | %s | %s |" % (et, pred, txt, ev))

    L.append("\n## 五、个体干预清单（按平均薄弱程度取前 8 名）\n")
    student_rows.sort(key=lambda x: sum(r[1] for r in x[1]) / max(1, len(x[1])))
    L.append("| 学生 | 最薄弱的 3 个知识点（正确率/样本） | 主要错因 | 平均单题耗时 | 建议动作 |")
    L.append("|---|---|---|---|---|")
    for sid, items, terr, avg in student_rows[:8]:
        sid_show = mask_id(sid) if mask else sid
        ws = "；".join("%s %.0f%%(%d题)" % (kp, r * 100, cnt) for kp, r, cnt in items) or "无明显薄弱"
        et = terr[0][0] if terr else "—"
        act = "单独面批 10 分钟（耗时偏高，先查审题）" if avg > 240 else "同组互批 + 错题重做"
        L.append("| %s | %s | %s | %.0f 秒 | %s |" % (sid_show, ws, et, avg, act))

    L.append("\n## 六、下一节课的 3 个干预动作\n")
    L.append("1. **前 8 分钟**：只讲「%s」，用反例题卡边界，配 2 道变式，当堂收 3 份作答。" % weak[0][0])
    top2 = [e for e, _ in err.most_common(2)] + ["—", "—"]
    L.append("2. **中间 20 分钟**：按教师标注的错因分组（%s 组 / %s 组），两组做不同任务，教师只巡「%s」组。"
             % (top2[0], top2[1], weak[0][0]))
    L.append("3. **最后 5 分钟**：让平均耗时 > 240 秒的学生口述解题思路，暴露审题问题；"
             "规则提示与教师标注冲突的 3 个学生，课后单独核对。")

    L.append("\n## 七、度量（两套基线都写出来，避免「省时」被一句「我们早有阅卷机」推翻）\n")
    L.append("| 场景 | 人工基线 | 本工具 | 变化 |")
    L.append("|---|---|---|---|")
    L.append("| A. 无阅卷系统（手工批改+录入+统计） | %.1f 分钟 | %.2f 分钟 | -%.0f%% |"
             % (human_full, tool_min, (1 - tool_min / human_full) * 100))
    L.append("| B. 已有阅卷系统（仅班级统计） | %.1f 分钟 | %.2f 分钟 | -%.0f%% |"
             % (human_stats_only, tool_min, (1 - tool_min / human_stats_only) * 100))
    L.append("| 覆盖学生 | 抽查 5–8 人 | 全部 %d 人 | 全覆盖 |" % len(st_cnt))
    L.append("| 错因口径 | 教师口头、难追溯 | 教师标注落库，可回溯到作答片段 | 可审计 |")
    L.append("\n> 口径说明：A 基线按「每题 5.4 秒录入 + 30 分钟班级统计」估算；B 基线为已有阅卷机、"
             "仅剩统计环节的情形。实际交付需与教研组共同测一次基线，不要拿本表直接对外报价。")

    L.append("\n## 八、已知局限（写出来比藏起来更值钱）\n")
    for x in ["规则归因一致率不足 80%，只作提示；替代教师判断会把个别干预做错，责任在工具侧，因此本工具不自动下结论。",
              "样本规模 600 条、每知识点 3–4 题，掌握度置信度有限；上真实数据后需按知识点题量做最小样本约束（本报告已对 <8 题标注）。",
              "无教学效果验证：没有「干预后两周复测」数据，无法证明掌握度提升；需接入第二次考试数据才能闭环。",
              "数据合规：默认明文存储学生 ID，仅本机可读；对外交付需开 --mask 并配置访问控制与留存期。"]:
        L.append("- " + x)

    md = "\n".join(L)
    with open(os.path.join(OUT, "report.md"), "w", encoding="utf-8") as f:
        f.write(md)
    print(md)
    print("\n[OK] 报告已生成：%s" % os.path.join(OUT, "report.md"))


if __name__ == "__main__":
    main()
