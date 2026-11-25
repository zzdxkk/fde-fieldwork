#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨平台自检：一条命令把五套原型在本机全部跑一遍，并校验关键数字与平台探测值。

为什么需要它：在本机跑通，不代表在别人的机器上跑通。
本脚本把「换机验证」变成可重复的一条命令；GitHub Actions 的三平台矩阵跑的也是它。

用法：
    python tools/smoke.py              # 五套全跑：测试 + 程序 + 输出校验
    python tools/smoke.py --only 03    # 只跑一套（按序号或目录名）
    python tools/smoke.py --list       # 只列出项目，不执行

退出码 0 = 全绿；非 0 = 有失败项，逐条打印原因。
"""
import os
import sys
import json
import subprocess
import platform
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# (序号, 目录, 入口, 报告文件, [报告里必须出现的关键数字], 最少用例数)
PROJECTS = [
    ("01", "exam-diagnosis", "app/main.py", "out/report.md",
     ["65.1%", "169"], 5),
    ("02", "ops-knowledge-qa", "app/main.py", "out/report.md",
     ["33.3%"], 4),
    ("03", "deploy-preflight", "app/check_env.py", "out/env_report.md",
     ["11 项", "内存 GB"], 10),
    ("04", "ticket-routing", "app/main.py", "out/report.md",
     ["90.0%", "82.5%", "57.5%"], 5),
    ("05", "contract-check", "app/main.py", "out/report.md",
     ["96.3%"], 4),
]


def _stdout_utf8():
    """Windows 控制台默认不是 UTF-8，中文会撞 UnicodeEncodeError。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def run(args, cwd):
    p = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       universal_newlines=True, errors="replace")
    return p.returncode, p.stdout


def check_probes(proj_dir):
    """03 的探测函数：只要有一项返回 0 / 空串，就当失败。

    这是这次真出事的地方——Windows 上 mem_gb() 没有分支，直接 return 0.0，
    程序不崩、报告照出，只有断言「合理性」的检查才能抓住。
    """
    code = (
        "import sys, os, json\n"
        "sys.path.insert(0, 'app')\n"
        "import check_env as c\n"
        "print(json.dumps({'mem_gb': c.mem_gb(), 'cpu': os.cpu_count(), "
        "'ntp': c.ntp_ok(), 'firewall': c.firewall_note()}, ensure_ascii=False))\n"
    )
    rc, out = run([sys.executable, "-c", code], proj_dir)
    if rc != 0:
        tail = (out.strip().splitlines() or [""])[-1]
        return ["探测函数导入/执行失败：%s" % tail], None
    row = json.loads(out.strip().splitlines()[-1])
    errs = []
    if not isinstance(row["mem_gb"], (int, float)) or row["mem_gb"] <= 0:
        errs.append("内存探测返回 %r：这台机器的分支没写，或取值失败" % (row["mem_gb"],))
    if row["mem_gb"] > 8192:
        errs.append("内存读到 %sGB，超出常理，检查单位换算" % row["mem_gb"])
    if not row["cpu"] or row["cpu"] <= 0:
        errs.append("CPU 核数读到 %r" % (row["cpu"],))
    if not str(row["ntp"]).strip():
        errs.append("时间源探测返回空串")
    if not str(row["firewall"]).strip():
        errs.append("防火墙探测返回空串")
    return errs, row


def main(argv):
    _stdout_utf8()
    only = None
    if "--list" in argv:
        for p in PROJECTS:
            print("%s  %s" % (p[0], p[1]))
        return 0
    if "--only" in argv:
        i = argv.index("--only")
        only = argv[i + 1] if i + 1 < len(argv) else ""

    print("=" * 68)
    print("本机环境：%s %s ｜ %s ｜ Python %s"
          % (platform.system(), platform.release(), platform.machine(), sys.version.split()[0]))
    print("工作目录：%s" % ROOT)
    print("=" * 68)

    results = []
    for no, name, entry, report, markers, min_tests in PROJECTS:
        if only and only not in (no, name):
            continue
        d = os.path.join(ROOT, name)
        if not os.path.isdir(d):
            results.append((no, name, "FAIL", "目录不存在：%s" % d))
            continue

        # 1) 单元测试
        rc, out = run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], d)
        m = re.search(r"Ran (\d+) test", out)
        ran = int(m.group(1)) if m else 0
        skipped = len(re.findall(r"skipped", out))
        if rc != 0:
            tail = "\n".join(out.strip().splitlines()[-12:])
            results.append((no, name, "FAIL", "单元测试失败：\n" + tail))
            continue
        if ran < min_tests:
            results.append((no, name, "FAIL", "只收集到 %d 个用例（至少应有 %d 个），可能整包导入失败" % (ran, min_tests)))
            continue

        # 2) 跑程序
        rc, out = run([sys.executable, entry], d)
        if rc != 0:
            tail = "\n".join(out.strip().splitlines()[-12:])
            results.append((no, name, "FAIL", "程序运行失败：\n" + tail))
            continue

        # 3) 报告与关键数字
        rp = os.path.join(d, report)
        if not os.path.exists(rp):
            results.append((no, name, "FAIL", "没生成报告：%s" % rp))
            continue
        with open(rp, encoding="utf-8", errors="replace") as f:
            md = f.read()
        missing = [k for k in markers if k not in md]
        degraded = False
        if missing and no == "05" and "未执行" in md:
            # 没装 reportlab 时的合法降级：报告明说没跑，不假装跑过
            missing = [k for k in missing if k != "96.3%"]
            degraded = True
        if missing:
            results.append((no, name, "FAIL", "报告里找不到这些关键数字：%s" % "、".join(missing)))
            continue

        # 4) 平台探测值（只有 03 有）
        note = "%d 个用例%s" % (ran, "，%d 跳过" % skipped if skipped else "")
        if no == "03":
            errs, row = check_probes(d)
            if errs:
                results.append((no, name, "FAIL", "；".join(errs)))
                continue
            note += "；内存 %.1fGB / CPU %s 核 / 时间源 %s" % (
                row["mem_gb"], row["cpu"], str(row["ntp"])[:28])
        if degraded:
            note += "；缺 reportlab，PDF 抽取如实写「未执行」"
        results.append((no, name, "OK", note))

    print()
    for r in results:
        print("[%-4s] %-18s %s" % (r[2], r[1], r[3]))
    bad = [r for r in results if r[2] != "OK"]
    print()
    print("%d 套通过，%d 套失败" % (len(results) - len(bad), len(bad)))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
