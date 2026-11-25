#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 平台分支体检：检查「探测本机」的那几个函数，三个系统的分支是不是都写了。
#
# 这台机器上跑得过，只能证明本机的分支存在。真正会出事的是「换个系统就掉进兜底」——
# Windows 上内存读到 0.0，就是兜底被当成了正常返回值。
#
# 做成静态检查而不是靠自觉：只要有人删掉 Windows 分支，CI 直接红。
#
# 用法：python tools/lint_platform.py    退出码 0=通过，1=有缺口
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 文件 -> [(这一项叫什么, [必须同时出现的标记])]
RULES = {
    "deploy-preflight/app/check_env.py": [
        ("内存探测：macOS / Linux / Windows 三条分支",
         ["hw.memsize", "/proc/meminfo", "GlobalMemoryStatusEx"]),
        ("时间源探测：三个系统",
         ["Darwin", "Windows", "timedatectl"]),
        ("防火墙探测：三个系统",
         ["Windows", "netsh", "firewalld"]),
        ("容器内 GPU 透传：docker 与 --gpus",
         ["docker", "--gpus"]),
    ],
}


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    bad = 0
    for rel, rules in RULES.items():
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            print("[FAIL] 文件不存在：%s" % rel)
            bad += 1
            continue
        with open(path, encoding="utf-8", errors="replace") as f:
            src = f.read()
        for name, tokens in rules:
            missing = [t for t in tokens if t not in src]
            if missing:
                print("[FAIL] %s → %s：缺 %s" % (rel, name, "、".join(missing)))
                bad += 1
            else:
                print("[OK  ] %s → %s" % (rel, name))

    print()
    print("缺口 %d 处" % bad if bad else "平台分支齐全")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
