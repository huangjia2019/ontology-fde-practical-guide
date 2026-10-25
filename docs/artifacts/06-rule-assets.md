# 第 6 站：经验怎样成为一条可检查的规则

老陈看一眼，就知道某位客户已经是 30 天内第三次申请退款。要让程序也作出这个判断，需要确定统计对象、时间窗口和处理动作。另一条“已开封耗材签收超过 24 小时须人工复核”的规则，还要回答：从哪个时间开始算，适用于哪些客户，依据是什么？

## 当前规则与新草稿分开看

[退款规则](../../config/rules/refund_rules.yaml)列出 R1–R5：耗材时限、发票、黑名单、退款频率、合同客户。它们在[策略实现](../../src/ontology_fde/policy.py)中有对应判断。

[规则草稿](../../config/rules/drafts/opened_consumable_rule_draft.json)用于练习一次规则变更的提出与审查。它仍处于 `draft`，不会自动替换已运行的 R1。文档提取采用确定性逻辑和模板，不调用大模型 API。

## 先看依据，再看结论

来源文件是[政策与工单语料](../../data/mock/documents/refund_policy_corpus.json)。正式政策限定适用范围，历史工单提供个案印证。工单里出现过的处理，不能自行扩大政策授权。

草稿保留来源定位和内容哈希，还将业务词映射到模型字段：

| 业务含义 | 模型绑定 |
|---|---|
| 签收时间 | `Order.signed_at` |
| 申请时间 | `RefundRequest.opened_at` |
| 需人工复核 | `Action.request_human_refund_approval` |
| 尚未解决的问题 | `missing_inputs` 中的 `opened_state_not_explicitly_modeled` |

“已开封”这个判断的输入仍需要补齐，草稿明确记录了这一点。请客服规则负责人和商品数据负责人共同确认，不能靠把状态改成 `approved` 跳过。

## 运行草稿校验

```bash
python3 run.py extract-rule --output artifacts/ch06-rule-draft.json
python3 run.py run YF-R-0602 --mode draft
python3 run.py checkpoint 6 --check
```

第一条命令检查结构、语义、运行样例及结论是否超出来源支持范围。五类样例覆盖符合、不符合、时间边界、数据缺失、范围之外的情况。

请在报告中同时找两项：`validation_complete: true` 和 `production_ready: false`。校验通过的草稿仍有三个阻断项：

- `missing_inputs_not_resolved`：缺失输入未解决；
- `human_review_not_completed`：人工审核未完成；
- `rule_not_compiled`：规则尚未编译。

第二条命令是另一笔业务：`YF-R-0602` 应命中 R4，提出转人工建议，业务状态不变。这样可以区分“已有规则处理申请”和“新规则准备发布”两项工作。

## 请规则负责人复核的边界

恰好 24 小时不命中“超过 24 小时”；缺少签收时间返回 `missing_data`；B2B 不在这份候选规则的范围内，返回 `out_of_scope`。这些结果都能在[规则样例](../../config/evals/document_rule_cases.json)中查到。

补齐输入、完成审核、编译并通过回归之后，才讨论替换当前规则。测试中的编译演示是本地规则生命周期验证，不是一次真实系统上线。

[下一站：权限验收](07-identity-and-permissions.md) · [返回十站目录](../book-map.md)。
