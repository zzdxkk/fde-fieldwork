# FDE 现场交付 · 五个小原型

![cross-platform](https://github.com/zzdxkk/fde-fieldwork/actions/workflows/ci.yml/badge.svg)

不是产品，是五个能在断网机器上跑起来的小东西，用来回答一句最常被问到的话：**你说的"交付"，具体长什么样？**

每个目录都是「一个场景 + 一份实跑报告 + 一套交付文档 + 一组单元测试」，代码以 Python 标准库为主，`python3 app/main.py` 就能出报告。

| 目录 | 场景 | 这份原型想证明的事 | 一眼能看到的数 |
|---|---|---|---|
| `exam-diagnosis/` | 高中数学错题诊断 | 诊断类工具不该冒充"AI 判错因"；教师标注是事实来源，规则只做提示 | 规则-教师一致率 65.1%；82 分钟 → 2.1 分钟 |
| `ops-knowledge-qa/` | 设备运维知识库问答 | 内网断网下的问答，重点不在"能答"，在"知道什么时候不答" | 域外 3/3 拒答、0 误答；冷启动 final 33.3% |
| `deploy-preflight/` | 私有化部署到场前体检 | 把"装完跑不起来"提前到出发前发现，并给出扩容拐点 | 11 项体检；4 并发内首包 P95 2ms，8 并发塌到 3.4s |
| `ticket-routing/` | 园区工单分派与 SLA | 规则引擎的分派率不值得吹，噪声下的掉点才是现场 | 干净集 90.0% / 噪声集 82.5%；自动派单 57.5% |
| `contract-check/` | 合同一致性核查 | 合规工具如果一半都报高风险，就没人看；分级必须可审计 | 字段抽取 96.3%；高风险 50% → 30% |

## 怎么跑

```bash
cd exam-diagnosis && python3 app/main.py          # 报告写到 out/report.md
cd ops-knowledge-qa && python3 app/main.py
cd deploy-preflight && python3 app/check_env.py   # 环境体检
cd ticket-routing && python3 app/main.py
cd contract-check && python3 app/main.py
```

要求 Python 3.10+，全程不联网。只有 `contract-check` 造样例 PDF 时需要 `reportlab`（仅生成测试用的假合同，解析部分是自写的，不依赖它）。

跑测试：

```bash
cd <任一目录> && python3 -m unittest discover -s tests
```

## 复现记录

| 机器 | 日期 | 结果 |
|---|---|---|
| macOS（开发机） | 2026-11-25 | 5 套全部跑通，24 个单元测试全绿 |
| Windows 10 + Python 3.13（干净机器，从本仓库下载后直接跑，未改代码） | 2026-11-25 | 先失败、修完再全绿，见下 |
| GitHub Actions（Ubuntu / Windows / macOS × Python 3.10 / 3.13 / 3.14） | 每次 push | `tools/smoke.py` 全面自检，另有三个「无 reportlab」作业 |

Windows 那台机器上暴露了两个只在换机时才出现的问题，都已修：

1. `deploy-preflight` 的内存检查返回 `0.0` —— 原来只读了 macOS 的 `sysctl` 和 Linux 的 `/proc/meminfo`，Windows 没有这两样。改成 Win32 `GlobalMemoryStatusEx` 后读到 15.9GB。顺带补了 `w32tm`（时间源）和 `netsh advfirewall`（防火墙）两条 Windows 分支。
2. `contract-check` 的测试在没装 reportlab 的机器上整包导入失败 —— 因为测试文件顶层就 `import make_pdfs`。改成按用例懒加载、缺库时 skip 那 2 个造 PDF 的用例，其余 4 个照常跑。

修完的结果：当时那 24 个用例在 Windows 上也全绿；装上 reportlab 后，合同字段抽取在本机重新生成样例 PDF 再抽取，仍是 96.3%（26/27）。01/02/04 的指标（65.1%、81.8/100/33.3、90.0/82.5/57.5）与 macOS 完全一致，说明这些逻辑不依赖平台。

没在 Windows 上重跑的：`deploy-preflight` 的压测（本机是虚拟桌面，测出来的数字没有交付参考价值，仍以 macOS 那组为准）。

之后又补了 7 条「探测值合理性」断言（`deploy-preflight/tests/test_probe.py`），全仓库现在是 31 个用例——只断言「不崩溃」的测试抓不住静默返回 0，必须断言「值在合理范围内」。这 31 个用例由下面的三平台 CI 逐次复核。

## 跨平台验证（换机不靠运气）

一条命令，在这台机器上把五套原型全跑一遍，并核对关键数字与探测值：

```bash
python tools/smoke.py            # 五套全跑
python tools/smoke.py --only 03   # 只跑一套
python tools/smoke.py --list      # 只列目录
```

它做四件事：跑每套的单元测试（用例数低于下限直接判失败，防止「整包导入失败」被误读成「没有测试」）；跑每套程序；比对报告里的关键数字；把 `deploy-preflight` 的探测函数单独拉出来看有没有返回 0 或空串。输出里会带本机的系统、架构、Python 版本。

CI 上同一份脚本跑 9 个组合，另有 3 个「故意不装 reportlab」的作业：

| 系统 | 装了 reportlab | 不装 reportlab |
|---|---|---|
| Ubuntu | 测试 + 五套程序 + 数字校验 | 造 PDF 的 2 个用例跳过，报告写「未执行」 |
| Windows | 同上 | 同上 |
| macOS | 同上 | 同上 |

还有一个静态作业 `tools/lint_platform.py`：内存、时间源、防火墙这几项，只要有人删掉某一个系统的分支，CI 直接红。

两条跨平台约定，写在这里是为了以后不再犯：

1. **取不到就写「未检测」，不返回 0 / 空串 / False。** 体检报告里出现 `0.0GB` 比留空更危险——它会被当成「客户机器真的没有」。`check_env.py` 现在把内存为 0 的情况渲染成「未检测」，报告头部也印上运行环境（系统 / 架构 / Python 版本），方便不同机器出的报告互相区分。
2. **可选依赖只在用例里懒加载。** 一个只用来造测试样例的库，不该决定整套测试能不能跑。

## 关于数字

- 所有准确率都在自己构造的样例数据上算，样本量和切分方式写在各个 README 里，报告的"口径"一节也写了。
- 没跑过的性能不写。`deploy-preflight` 里凡是没实测的项，一律标"未实测"，不用估算值填空。
- 机器的实测环境是 macOS + 无 NVIDIA GPU，所以涉及 GPU 吞吐的部分只给选型与压测方法，不给具体数字。

## 不包含

真实客户数据、真实模型权重、整机与 HIL 测试、等保整改。这些是交付时必须现场补的部分，原型不替它们背书。
