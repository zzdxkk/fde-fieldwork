# 私有化部署「到场前」环境体检与压测

客户说"服务器都备好了"，人到现场才发现：驱动版本比框架编译版本低一档、容器里看不到 GPU、推理端口被防火墙挡着、机器时间没同步导致 token 计费对不上。这几件事有任何一条，当天就回不了酒店。

这个原型把这类事故提前到出发前：先体检、再选型、然后真跑一遍压测，给出"该加卡还是该调参"的拐点。

## 体检 11 项

| 项 | 为什么查 |
|---|---|
| 操作系统 | 决定能不能用容器 |
| Python 版本 | ≥3.10 才支持新版 vLLM |
| CPU 逻辑核 | 无 GPU 时的并发上限 |
| 内存 | 7B-Q4 要 ≥16GB，含 OS 缓冲建议 32GB |
| 可用磁盘 | 权重 4.7GB + 镜像 + wheel ≈ 12GB |
| Docker | 政企现场多用容器，没有就走原生 |
| GPU 型号 / 显存 / 驱动 | 有卡不等于能用，显存决定模型档位 |
| 驱动侧 CUDA 版本 | 与框架编译版本必须匹配，差一档起不来 |
| 容器内 GPU 透传 | 现场最常见的"装了跑不起来" |
| 时间同步 | 审计、证书、计费都依赖 |
| 防火墙 | 推理端口要放行 |

每项都是命令实测，不是问客户"你们装了吗"。

## 选型按显存分档，不按"有卡就上 vLLM"

| 显存 | 方案 | 理由 |
|---|---|---|
| ≥24GB | vLLM + 7B FP16 | 可上吞吐型框架，支持连续批处理 |
| 8–24GB | vLLM / llama.cpp + 7B 4bit | 必须量化，量化后并发与精度都要重测 |
| 无 GPU 有 Docker | Ollama + 3B Q4 | 3B 在 CPU 上勉强可用，7B 不是"慢"，是不可用 |
| 无 GPU 无 Docker | llama.cpp 原生 + 3B Q4 | 走二进制，启动脚本得手写 |

## 压测结论（本机实测，无 GPU）

| 并发 | 首包 P95 | 吞吐 | 结论 |
|---|---|---|---|
| ≤4 | 2ms | 1.17 req/s | 单机够用 |
| 8 | 约 3.4s | 封顶 | 不是调参能救的，该加卡或加实例 |

以上是规则引擎部分在本机的实测值；涉及真模型的吞吐一律没测，报告里写"未实测"。

## 跑

```bash
python3 app/check_env.py     # 生成 out/env_report.md
python3 app/bench.py         # 压测，写 out/bench_result.csv
python3 app/check_env.py     # 回填压测结果到报告
```

`app/bench.py` 不带任何硬编码延迟，测的就是这台机器当下的真实表现。

## 平台差异

| 项 | macOS | Windows | Linux |
|---|---|---|---|
| 内存 | `sysctl hw.memsize` | `GlobalMemoryStatusEx` | `/proc/meminfo` |
| 时间源 | 默认 time.apple.com | `w32tm /query /status`（服务没跑就报"查不到"） | `timedatectl` |
| 防火墙 | 应用防火墙默认开 | `netsh advfirewall show allprofiles state` | `firewalld` |
| GPU | 无 NVIDIA 卡则报"未检测到" | 同左，靠 `nvidia-smi` 是否存在 | 同左 |

Windows 上第一次跑出来的内存是 0.0GB（只写了 macOS/Linux 分支），这是换机验证时发现的，已修。教训是：体检工具自己也要先被体检一遍。

## 已知问题

- macOS 上拿不到 NVIDIA 驱动侧 CUDA 版本，只能报"未检测到"。
- 不做等保整改：安全加固要客户安全团队参与，这里只出清单。
- 压测用的是本机 HTTP 服务，换成真模型后所有数字都要重测。
