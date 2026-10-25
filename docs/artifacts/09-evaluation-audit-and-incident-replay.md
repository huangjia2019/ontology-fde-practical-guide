# 第 9 站：批准之后失败了，记录能否说明白

`YF-R-0800` 满足批准条件。执行器先批准，再创建付款指令。如果第二步失败，业务已经发生过变化。客服、财务和运维必须知道哪一步完成、哪一步未完成，才能继续处理。

## 先读一份决策记录

[DecisionRecord](../../src/ontology_fde/audit.py)保存以下信息：执行主体与版本、权限依据、目标对象、来源及证据、条件检查、命中规则、候选动作与裁决、前后状态、预期效果、实际效果、调用顺序。

例如，第 8 站的记录应能解释退款助手为何提出批准、风控为何要求复核、最后为何只创建人工审批材料。只看到接口成功码，回答不了这些问题。

## 运行评估和一次失败

```bash
python3 run.py evaluate --output artifacts/ch09-eval.json
python3 run.py run YF-R-0800 --mode write \
  --simulate-payment-failure --audit artifacts/ch09-failure.jsonl
python3 run.py checkpoint 9 --check
```

评估中的核心策略样例应为 `36/36`，事故回放为 `2/2`。它们直接调用策略层，不经过全部数据装配、写入和补偿路径。端到端行为还要运行测试：

```bash
python3 tools/verify.py
```

失败案例中，请依次找出：

1. 退款已批准；
2. `payments.create_refund_instruction` 状态为 `failed`；
3. 退款进入 `approval_pending_payment`；
4. 创建财务任务 `FMT-0800`；
5. `actual_effect` 说明指令创建失败及后续处理，没有报告“付款成功”。

调用耗时是教学用的确定性模拟数值，不是实际 ERP 或模型的性能测量。可用它理解顺序，不能拿它作为生产速度指标。

## 修过的问题留下回放

| 回放 | 问题 | 修复后应保持的判断 |
|---|---|---|
| `INC-REPLAY-001` | 客户渠道缺失，被当作普通个人客户 | `unknown` 转人工核实 |
| `INC-REPLAY-002` | 大写 `B2B` 绕过了渠道比较 | 先规范大小写，命中 R5 并转人工 |

两项记录位于[事故回放集](../../config/evals/incident_replays.json)。新项目遇到判断错误时，保存脱敏输入、当时输出、业务确认的预期结果和修复点，再加入回归。不要只把出错对话放进资料库。

## 谁来验收这份证据

财务核对“批准”“付款指令”和“到账”的区别；客服确认未完成业务有接手人；测试人员检查正常、拒绝、转人工、重试与故障路径；安全与运维确认审计存储及访问要求。

本地 JSONL 便于阅读，不防篡改，也不替代企业的审计保存机制。[测试口径说明](../release-baseline.md)解释书中 53 项测试与仓库当前数量的关系。

[下一站：运行交接与退出](10-operations-handoff-and-replication.md) · [返回十站目录](../book-map.md)。
