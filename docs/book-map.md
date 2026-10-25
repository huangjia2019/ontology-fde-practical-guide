# 随书学习：云帆项目的十站

这份目录对应《企业本体论：人人都是FDE》中的云帆退款项目。读到哪一站，就可以打开相应的交付卡，看看书中的讨论怎样落到数据、规则和程序上。

仓库已经包含十站完成后的参考程序。`checkpoint` 是检查卡，不会逐章开放功能，也不会替你修改配置。可以按书的顺序学，也可以带着一个问题直接进入某一站。

所有练习使用本地样例数据，规则由确定性 Python 程序执行，不调用大模型 API，不需要 API Key，不连接企业系统。先按[首页](../README.md)准备 Python 环境；以下命令均在仓库根目录执行。Windows 的 Python 命令写法也见首页。

## 十站阅读目录

| 站点 | 这一站要回答的问题 | 先读什么 | 需要和谁核实 |
|---|---|---|---|
| 1：确定业务范围 | 347 元的退款，为什么还不能批准？ | [跟完一笔退款](artifacts/01-field-walkthrough.md)、[项目定位卡](artifacts/01-ontology-positioning-card.md)、[六问诊断](artifacts/01-six-question-diagnostic.md) | 客服与财务：缺哪项事实，谁能确认 |
| 2：审视原有方案 | 原来给人提建议的助手，能直接获得写权限吗？ | [原有方案审计](artifacts/02-historical-audit.md) | 业务负责人、系统负责人：建议与执行在哪里分开 |
| 3：登记执行主体 | 系统里是谁在做这次操作？ | [身份验收](artifacts/03-identity-acceptance.md)、[身份配置](../config/identity/refund_agent.yaml) | 客服运营、技术与安全：身份、责任和授权期限 |
| 4：建立最小本体 | 几个系统里的记录，怎样连成同一笔业务？ | [最小本体](artifacts/04-minimum-ontology.md)、[本体配置](../config/ontology/) | 客户主数据、商城、财务、风控：字段含义和权威来源 |
| 5：限定业务动作 | 500 元和 500.01 元，分别可以发生什么？ | [动作契约](artifacts/05-action-contract.md)、[三份契约](../config/actions/) | 客服主管与财务：批准、付款指令、到账的区别 |
| 6：整理判断依据 | 老陈的经验怎样成为可检查的规则？ | [规则来源与草稿](artifacts/06-rule-assets.md)、[规则配置](../config/rules/) | 规则负责人：依据、适用范围、缺失信息与审批 |
| 7：验证权限 | 业务条件都满足，未登记的 Agent 能批准吗？ | [身份与六维权限](artifacts/07-identity-and-permissions.md) | 安全与系统负责人：哪里执行拒绝，如何留证据 |
| 8：处理协作分歧 | 退款助手同意、风控要求复核，听谁的？ | [委托与冲突裁决](artifacts/08-multi-agent-coordination.md) | 客服与风控：委托范围、裁决次序与接手人 |
| 9：评估和复盘 | 已经批准，付款指令却创建失败，如何交代？ | [评估、审计与故障复盘](artifacts/09-evaluation-audit-and-incident-replay.md) | 财务、测试与运维：哪些动作发生过，哪笔工作未完成 |
| 10：交还组织 | 项目组离开之后，谁维护、谁接手、谁停用？ | [运行交接与退出](artifacts/10-operations-handoff-and-replication.md)、[FDE 现场练习](fde-playbook.md) | 业务负责人、接管团队与安全：交接是否真的能执行 |

## 第一轮：从一笔退款走到一次拒绝

先查看“遥控器单”的事实：

```bash
python3 run.py inspect YF-R-0311
python3 run.py run YF-R-0311 --mode draft
```

这笔申请只有 347 元。请留意 `invoice_status` 和 `source_refs`：ERP 本次没有查到发票记录，程序保留 `not_found`，发票状态为 `unknown`。建议结果应为 `queue_human`，命中 `G-INVOICE-UNKNOWN`。财务仍需要确认发票情况，金额小并不能补齐这个事实。

接着比较一分钱的边界：

```bash
python3 run.py run YF-R-0500 --mode write
python3 run.py run YF-R-0501 --mode write
```

两笔样例的其他条件都通过。500 元那笔进入 `approved` 并创建模拟付款指令；500.01 元那笔进入 `pending_human`，创建人工审批材料。`approved` 表示批准，不表示钱已到账。这里执行的 `write` 只改变本次进程的内存数据。

## 第二轮：每站运行一次检查

```bash
# 查看这一站的问题、文件与验收项
python3 run.py checkpoint 4

# 检查文件是否存在，以及必要字段和部分约束
python3 run.py checkpoint 4 --check
```

把 `4` 换成 `1` 到 `10`，即可查看其他站点。结果中的 `check.passed` 应为 `true`。这个结果说明检查卡列出的条件通过了，行为验收还要运行各站交付卡中的案例和测试。例如，第 5 站的文件齐全，不等于已经证明 `draft` 不会写业务状态。

## 程序在哪里实现这些判断

| 要追下去的问题 | 源码入口 |
|---|---|
| 多个来源怎样拼成一笔退款 | [repository.py](../src/ontology_fde/repository.py)，`get_case()`，标记 `BOOK-CH4-START` |
| 哪些条件导致补充证据或转人工 | [policy.py](../src/ontology_fde/policy.py)，`RefundPolicy.evaluate()` |
| 谁可以写，如何处理重试和失败 | [engine.py](../src/ontology_fde/engine.py)，`RefundEngine.run()`，标记 `BOOK-CH5-START` |
| 决策记录保存哪些内容 | [audit.py](../src/ontology_fde/audit.py)，`DecisionRecord` |
| 36 个样例怎样比较预期和实际 | [evaluator.py](../src/ontology_fde/evaluator.py)，标记 `BOOK-CH9-EVAL-START` |

配置文件使用 JSON 兼容的 YAML 格式。金额上限、允许的执行主体、冲突优先级等配置由程序读取；其余退款判断仍有专门的 Python 实现。修改一段规则文字，并不会自动得到一套新程序。做改动前，可先读[架构与实现范围](architecture.md)。

## 给自己的学习记录

每完成一站，记下四件事就够了：本次判断的业务对象；支持判断的来源；实际发生或被拦下的动作；换到自己企业后需要找谁核实。运行输出可以留在本地 `artifacts/` 目录，客户材料不要放入公开仓库。

如果“运行通过”了，却还说不清为什么要停下来，先回到那笔业务。FDE 的学习要积累这种体感：一份材料缺失、一个定义不同、一次交接无人接收，都可能改变交付结果。
