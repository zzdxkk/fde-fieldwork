# FDE 现场交付 · 五个小原型

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

## 关于数字

- 所有准确率都在自己构造的样例数据上算，样本量和切分方式写在各个 README 里，报告的"口径"一节也写了。
- 没跑过的性能不写。`deploy-preflight` 里凡是没实测的项，一律标"未实测"，不用估算值填空。
- 机器的实测环境是 macOS + 无 NVIDIA GPU，所以涉及 GPU 吞吐的部分只给选型与压测方法，不给具体数字。

## 不包含

真实客户数据、真实模型权重、整机与 HIL 测试、等保整改。这些是交付时必须现场补的部分，原型不替它们背书。
