# 第 5 站：500 元可以批准，500.01 元怎么办

`YF-R-0500` 和 `YF-R-0501` 的样例都具备可批准的其他条件，区别在于退款金额。前者 500 元，后者 500.01 元。请先猜一下它们的状态会怎样变化，再运行程序。

```bash
python3 run.py run YF-R-0500 --mode write
python3 run.py run YF-R-0501 --mode write
```

| 样例 | 动作 | 退款状态 | 产生的业务对象 |
|---|---|---|---|
| 500 元且其他条件通过 | `approve_refund_small` | `approved` | 模拟付款指令 |
| 500.01 元 | `request_human_refund_approval` | `pending_human` | 人工审批材料，不创建付款指令 |
| 证据不完整或未核验通过 | `request_missing_evidence` | 保持原状态 | 补充证据请求草稿 |

## 动作契约规定什么

[小额批准契约](../../config/actions/approve_refund_small.yaml)列出执行主体、输入、前提、效果、审批门槛、幂等、失败处理和审计要求。上限由其中的 `threshold_cny` 读取。客户渠道、发票、履约、证据、风控及退款频率也要检查，金额低于上限不等于允许批准。

[人工审批契约](../../config/actions/request_human_refund_approval.yaml)与[补证契约](../../config/actions/request_missing_evidence.yaml)分别规定另外两条路径。财务处理任务是付款失败后的补偿动作，没有作为第四个独立业务契约供 Agent 任意调用。

契约中的主管角色是外部人工流程的声明。CLI 没有实现主管审批入口，不能用 `role:cs_supervisor` 冒充已经认证的真人。

## 先建议，再检查业务写入

```bash
python3 run.py run YF-R-0500 --mode read
python3 run.py run YF-R-0500 --mode draft
```

`read` 返回事实，`draft` 返回候选判断和决策记录；两者都不改变退款状态。`write` 会重新读取并检查事实，在当前进程中执行允许的动作。三条 CLI 命令是三个独立实验，不会共享前一条命令的业务状态。

## 已经批准，付款指令创建失败

```bash
python3 run.py run YF-R-0800 --mode write --simulate-payment-failure
python3 run.py checkpoint 5 --check
```

检查 `state_after` 是否为 `approval_pending_payment`，调用记录是否包含付款指令创建失败和后续补偿，是否形成财务任务。失败的付款指令仍被保留以便核查；不能把这次运行写成“退款完成”。请财务判断这份任务是否足以继续处理。

重试还有一项要求：同一引擎实例内，相同 `intent_id` 返回原来的决策记录，标记 `idempotent_replay: true`，不重复创建业务对象。[执行器测试](../../tests/test_engine.py)验证这个行为。跨进程、跨服务器的幂等需要真实存储与交易设计，本地重复运行 CLI 不会替你验证这一层。

完成时，请客服主管和财务分别核对“批准的条件”和“批准之后发生什么”。[返回十站目录](../book-map.md)。
