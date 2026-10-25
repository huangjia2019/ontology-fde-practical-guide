# 第 1 站：项目定位卡

项目先处理云帆商城的个人客户售后退款。要改善的是客服反复查找事实、核对条件和准备交接材料的工作，暂不覆盖整个企业的所有客服问题。

## 第一版约定

| 事项 | 本项目的决定 | 对照文件 |
|---|---|---|
| 业务对象 | 一笔 `RefundRequest`，关联客户、订单和订单项 | [对象目录](../../config/ontology/objects.yaml) |
| 执行主体 | `agent.cs.refund.001`，以自身身份行动 | [身份配置](../../config/identity/refund_agent.yaml) |
| 事实范围 | 金额、履约、发票、工单、风控和证据 | [来源映射](../../config/ontology/source_map.yaml) |
| 候选动作 | 批准小额退款、转人工、请求补充证据 | [动作契约](../../config/actions/) |
| 自动批准条件 | 金额不超过 500 元，且全部相关条件通过 | [批准契约](../../config/actions/approve_refund_small.yaml)、[策略实现](../../src/ontology_fde/policy.py) |
| 暂不自动处理 | 合同客户、发票未知或待财务处理、风控异常、超过金额上限等情况 | [退款规则](../../config/rules/refund_rules.yaml) |
| 禁止事项 | 修改申请金额、直接调用真实付款接口、借用主管个人账号 | [权限配置](../../config/policies/permissions.yaml) |

## 怎样验收

```bash
python3 run.py checkpoint 1 --check
python3 run.py run YF-R-0311 --mode draft
python3 run.py run YF-R-0500 --mode write
python3 run.py run YF-R-0501 --mode write
```

347 元的遥控器单因为发票未知而转人工；其他条件满足的 500 元样例可以批准；500.01 元样例必须转人工。批准后的本地付款指令只表示待执行的指令，不表示到账。

还要检查 `read` 和 `draft` 没有改变业务状态，写入结果有决策记录，失败后有状态与接手任务。程序检查不能替代客服、财务和安全对这些边界的认可。

## 到企业后补上哪些约定

请业务负责人填写当前每笔业务的办理时间、等待时间、转人工原因及希望改善的部分，再约定如何比较试运行前后结果。仓库里的样例不提供生产收益数据，也不预设一套适合所有企业的自动化比例。

第一版不接真实付款、不处理跨境与税务冲销、不允许规则草稿自行生效。后续扩大范围时，重新审查涉及的对象、动作和责任，再补案例验证。

[返回十站目录](../book-map.md)。
