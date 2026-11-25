#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""私有化部署「到场前」环境体检与选型工具

定位修正：本工具是**部署前体检 + 选型 + 离线清单生成**，不是"部署包"。
它不承诺性能数字——性能只在 bench.py 实跑后才写进报告；没跑就写「未实测」。

用法：python3 check_env.py
输出：out/env_report.md / out/bench_plan.csv / deploy/docker-compose.yml
"""
import os, sys, json, shutil, platform, subprocess, csv, re

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(BASE), "out")
DEPLOY = os.path.join(BASE, "..", "deploy")


def cmd(c, timeout=8):
    try:
        return subprocess.check_output(c, shell=True, stderr=subprocess.DEVNULL,
                                       timeout=timeout).decode(errors="ignore").strip()
    except Exception:
        return ""


def mem_gb():
    if sys.platform == "darwin":
        v = cmd("sysctl -n hw.memsize")
        return round(int(v) / 1024 ** 3, 1) if v.isdigit() else 0.0
    if sys.platform.startswith("win"):
        # Windows 没有 /proc，用 Win32 GlobalMemoryStatusEx 拿物理内存
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong),
                            ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            st = MEMORYSTATUSEX()
            st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
                return round(st.ullTotalPhys / 1024 ** 3, 1)
        except Exception:
            pass
        return 0.0
    if os.path.exists("/proc/meminfo"):
        for line in open("/proc/meminfo"):
            if "MemTotal" in line:
                return round(int(line.split()[1]) / 1024 ** 2, 1)
    return 0.0


def gpu_info():
    out = cmd("nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader")
    return [x.strip() for x in out.splitlines() if x.strip()] if out else []


def cuda_version():
    """驱动侧 CUDA 版本（nvidia-smi 右上角），不是 toolkit 版本——两者常被混用。"""
    txt = cmd("nvidia-smi")
    m = re.search(r"CUDA Version:\s*([0-9.]+)", txt)
    return m.group(1) if m else ""


def docker_gpu_ok():
    """真正验证容器内能否看到 GPU（很多现场 nvidia-smi 正常但容器透传失败）。"""
    if not shutil.which("docker"):
        return "无 docker"
    r = cmd("docker run --rm --gpus all ubuntu:20.04 nvidia-smi -L 2>&1 | head -3", timeout=60)
    if not r:
        return "未验证（无镜像/无 GPU/需联网拉镜像）"
    return "容器内可见 GPU" if "GPU" in r else "容器内不可见 GPU：" + r[:60]


def ntp_ok():
    """时间不同步会导致 token 计费、日志审计、证书全乱，政企验收会查。"""
    if platform.system() == "Darwin":
        return "macOS 默认 time.apple.com（未逐项校验）"
    if platform.system() == "Windows":
        out = cmd("w32tm /query /status")
        if not out:
            return "w32tm 查不到（时间服务未运行或权限不足，需手动核对时间源）"
        src = re.search(r"Source:\s*(\S.*)", out)
        return "时间源 %s（w32tm 可查）" % (src.group(1).strip() if src else "未知")
    if shutil.which("timedatectl"):
        t = cmd("timedatectl show -p NTPSynchronized --value")
        return {"yes": "已同步", "no": "未同步"}.get(t, "未知")
    return "无 timedatectl"


def firewall_note():
    if platform.system() == "Windows":
        out = cmd("netsh advfirewall show allprofiles state")
        states = re.findall(r"\b(ON|OFF)\b", out)
        return ("Windows 防火墙：%s（推理端口需放行）" % "/".join(states)) if states else "Windows 防火墙：状态未取到"
    if platform.system() == "Linux" and shutil.which("systemctl"):
        s = cmd("systemctl is-active firewalld")
        return "firewalld %s（需放行推理端口）" % (s or "未知")
    if platform.system() == "Darwin":
        return "macOS 应用防火墙（本机默认开启，端口需手动放行）"
    return "未检测"


def read_bench():
    p = os.path.join(OUT, "bench_result.csv")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(DEPLOY, exist_ok=True)

    gpus = gpu_info()
    gpu = bool(gpus)
    docker = shutil.which("docker") is not None
    free_gb = round(shutil.disk_usage(BASE).free / 1024 ** 3, 1)
    cpu = os.cpu_count() or 4

    info = [
        ("操作系统", "%s %s" % (platform.system(), platform.release()), "—"),
        ("Python", sys.version.split()[0], "≥3.10 才支持新版 vLLM"),
        ("CPU 逻辑核", cpu, "决定无 GPU 时的并发上限"),
        ("内存 GB", mem_gb(), "7B-Q4 需 ≥16GB，含 OS 缓冲建议 32GB"),
        ("可用磁盘 GB", free_gb, "7B-Q4 权重约 4.7GB，镜像+wheel 另需 8GB"),
        ("Docker", shutil.which("docker") or "未安装", "政企现场多用容器，无则走原生"),
        ("GPU 型号/显存/驱动", "；".join(gpus) if gpus else "未检测到 NVIDIA GPU", "无 GPU → CPU 量化方案"),
        ("驱动侧 CUDA 版本", cuda_version() or "无", "必须与框架编译版本匹配，差一档就起不来"),
        ("容器内 GPU 透传", docker_gpu_ok(), "这一项失败，是现场最常见的「装了跑不起来」"),
        ("时间同步", ntp_ok(), "审计与证书依赖"),
        ("防火墙状态", firewall_note(), "推理端口需放行"),
    ]

    # 选型：不做"有 GPU 就 vLLM"的一刀切，按显存分档
    vram = 0
    if gpus:
        m = re.search(r"([0-9]+)MiB", gpus[0])
        vram = int(m.group(1)) // 1024 if m else 0
    if gpu and vram >= 24:
        stack, model, why = "vLLM（Docker）", "Qwen2.5-7B-Instruct（FP16）", "显存 ≥24GB，可上吞吐型框架，支持连续批处理"
    elif gpu:
        stack, model, why = "vLLM 或 llama.cpp（按显存）", "Qwen2.5-7B-Instruct（AWQ 4bit）", "显存 8–24GB，需量化；量化后并发与精度都要重测"
    elif docker:
        stack, model, why = "Ollama（Docker）", "Qwen2.5-3B-Instruct（Q4_K_M）", "无 GPU，3B 量化在 CPU 上才勉强可用；7B 在 CPU 上不是「慢」，是不可用"
    else:
        stack, model, why = "llama.cpp 原生", "Qwen2.5-3B-Instruct（Q4）", "无容器，走原生二进制，脚本需手写"

    L = ["# 私有化部署「到场前」环境体检与选型报告\n"]
    L.append("检测方式：本机命令实测（非人工口头确认） ｜ 生成时间：本次运行\n")
    L.append("\n## 一、环境体检（11 项，其中 4 项是最容易漏掉、但现场一定炸的）\n")
    L.append("| 检查项 | 实测值 | 为什么查它 |")
    L.append("|---|---|---|")
    for k, v, why_chk in info:
        L.append("| %s | %s | %s |" % (k, v, why_chk))

    L.append("\n## 二、选型结论\n")
    L.append("| 项 | 选择 | 依据 |")
    L.append("|---|---|---|")
    L.append("| 推理框架 | %s | %s |" % (stack, why))
    L.append("| 模型 | %s | Qwen2.5-7B/3B 为 Apache-2.0，可商用；72B 及以上为社区许可，须法务确认 |" % model)
    L.append("| 容器 | %s | 离线交付用 docker save/load，镜像体积需提前告知客户 |" % ("Docker" if docker else "无（原生安装）"))
    L.append("| 网络 | 全程离线 | 权重、镜像、wheel 三样缺一不可 |")

    bench = read_bench()
    L.append("\n## 三、压测结果（只写跑过的，没跑就写未实测）\n")
    if bench:
        L.append("| 并发 | 首包 P50 | 首包 P95 | 完成 P95 | 成功率 | 吞吐 |")
        L.append("|---|---|---|---|---|---|")
        for r in bench:
            L.append("| %s | %sms | %sms | %sms | %s%% | %s req/s |"
                     % (r["concurrency"], r["first_p50"], r["first_p95"],
                        r["total_p95"], r["success_rate"], r["rps"]))
        L.append("\n> **口径（必须当客户面说清）**：本表测的是**服务链路 + 排队**的开销，"
                 "模型推理耗时用同规格 stub 模拟（每 token 20ms）。"
                 "换真模型后数值会变，方法不变——这才是可复用的部分。")
    else:
        L.append("**未实测。** 本报告不含任何推测的性能数字；签约前须在客户机器上执行 `python3 bench.py` 并回填。")

    L.append("\n## 四、离线交付清单（按体积排序，先解决运输问题）\n")
    for x in ["模型权重（约 4.7GB / Q4 7B）+ sha256 校验和",
              "Docker 镜像 tar（含推理框架，约 6–12GB）",
              "Python 依赖 wheel 目录（vLLM 系依赖较重，务必全量）",
              "docker-compose.yml + run.sh + 回滚脚本",
              "部署手册 / 运维手册 / 验收清单 / 培训大纲",
              "bench.py 与验收用例（客户可自证）"]:
        L.append("- " + x)

    L.append("\n## 五、授权与合规（政企必查，别等法务来问）\n")
    for x in ["模型许可：Qwen2.5-7B/3B 为 Apache-2.0（可商用、可修改）；≥72B 版本为 Qwen 社区许可，商用需法务确认。",
              "版本锁定：交付时固定模型版本 + 权重 sha256，禁止现场 `ollama pull latest`。",
              "数据不出域：推理全在内网；如启用日志，须默认脱敏（手机号/身份证/工单号）。",
              "等保相关：审计日志留存 ≥6 个月、账号权限分离、传输加密，这三条客户一定会问。"]:
        L.append("- " + x)

    L.append("\n## 六、降级路径（按代价从小到大）\n")
    for x in ["降上下文：8K → 4K，显存/内存吃紧时第一步",
              "重量化：FP16 → AWQ 4bit → Q4_K_M，精度损失需抽样对比",
              "换小模型：7B → 3B，能力下降要在验收用例上量化，不能口头说「差不多」",
              "限并发 + 排队 + 首包提示：宁可慢，不要超时雪崩",
              "兜底：模型服务不可用 → 静态 FAQ + 转人工，业务不断流"]:
        L.append("- " + x)

    L.append("\n## 七、本工具不做什么（边界）\n")
    for x in ["不做模型效果评测：效果要在客户业务用例上测，不是跑分。",
              "不承诺性能：没有 bench 数据就不写数字。",
              "不做安全加固全包：等保整改需客户安全团队参与，本工具只给清单。"]:
        L.append("- " + x)

    md = "\n".join(L)
    with open(os.path.join(OUT, "env_report.md"), "w", encoding="utf-8") as f:
        f.write(md)

    compose = """# 由 check_env.py 按实测环境生成；无 GPU 时为 Ollama 路线
services:
  ollama:
    image: ollama/ollama:latest
    restart: always
    ports: ["11434:11434"]
    volumes: ["./models:/root/.ollama"]
    environment:
      - OLLAMA_KEEP_ALIVE=24h
      - OLLAMA_NUM_PARALLEL=4
%s
  app:
    build: .
    restart: always
    ports: ["8080:8080"]
    depends_on: [ollama]
    environment:
      - LLM_BASE=http://ollama:11434
      - MODEL=%s
      - KB_PATH=/data/kb.csv
    volumes: ["./data:/data"]
""" % ("    deploy:\n      resources:\n        reservations:\n          devices:\n            - driver: nvidia\n              count: all\n              capabilities: [gpu]" if gpu else "    # 本机未检测到 GPU：若客户机有 GPU，取消上面 deploy 段注释并改 image 为 vllm/vllm-openai", model)
    with open(os.path.join(DEPLOY, "docker-compose.yml"), "w", encoding="utf-8") as f:
        f.write(compose)

    # 计划表：只写目标值（SLA），不伪造实测值
    with open(os.path.join(OUT, "bench_plan.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["case", "concurrency", "prompt_tokens", "max_new_tokens", "target_first_p95_ms", "target_total_p95_ms", "status"])
        for c in (1, 2, 4, 8, 16):
            w.writerow(["chat-%d" % c, c, 512, 256, 2000, 8000, "实测" if bench else "待实测"])

    print(md)
    print("[OK] env_report.md / bench_plan.csv / docker-compose.yml 已更新（压测数据：%s）"
          % ("已回填" if bench else "未实测"))


if __name__ == "__main__":
    main()
