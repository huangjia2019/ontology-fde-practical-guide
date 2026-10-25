# 第 8 站：退款助手同意，风控要求复核

`YF-R-0610` 申请 280 元，证据、履约和发票条件允许退款助手提出批准建议。但风控发现同一设备短时间内出现多次售后申请，给出 `review`。最终应该保留两个意见，并按约定转人工处理。

## 委托中要带什么

完整[任务信封样例](08-task-envelope-YF-R-0610.json)记录：

| 字段 | 本次含义 |
|---|---|
| `envelope_id` | `ENV-T-0610`，识别这次委托 |
| `correlation_id` | `CORR-YF-R-0610`，关联业务过程 |
| `sender`、`recipient` | 从接待助手委托给退款助手 |
| `object_refs` | 指向工单、客户、订单、订单项和退款申请 |
| `allowed_actions`、`forbidden_actions` | 本次可以做什么，不可以做什么 |
| `context_scope`、`expires_at` | 可以使用哪些对象，委托何时过期 |

样例时间固定，用于可复现实验。运行时默认采用申请发生时间；需要测试过期行为时，可通过 `--processing-at` 指定更晚的带时区时间。

## 裁决后不要丢掉分歧

[Agent 登记表](../../config/identity/agent_registry.yaml)列出三个角色及其关系，[冲突策略](../../config/policies/conflict_resolution.yaml)规定这条次序：

```text
RiskAgent:block > RiskAgent:review > RefundAgent:approve
```

当前程序用确定性候选记录与裁决呈现协作，没有调用三个独立模型服务。这个练习要观察的是意见、依据、权限和结果如何对应。

```bash
python3 run.py run YF-R-0610 --mode write \
  --audit artifacts/ch08-decision-records.jsonl
python3 run.py checkpoint 8 --check
```

在输出或 JSONL 记录中找到：

- `agent_candidates` 同时保留退款助手的 `approve` 与风控的 `review`；
- `conflict_resolution` 记录胜出意见、被覆盖意见及 `POL-AGENT-CONFLICT-001`；
- `task_envelope` 保留本次委托范围，调用轨迹记录检查与执行顺序；
- 退款由 `pending_review` 变为 `pending_human`，创建 `HAP-0610`，不创建付款指令。

JSONL 文件会追加本次结果，不会保存或恢复整套业务状态。多轮练习可换文件名留档。

## 交给业务人员核对

请客服和风控一起确认优先级，以及人工队列由谁处理。遇到策略缺失、冲突优先级不合理等情况，应暂停接入并修复配置，不能把任意程序排序当成企业共识。也不要把这个项目的优先级直接复制到所有业务：有些争议需要法务，有些需要客户授权。

下一站将沿这份决策记录检查实际效果。[返回十站目录](../book-map.md)。
