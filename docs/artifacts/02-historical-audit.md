# 第 2 站：从建议到执行，原有方案缺了什么

过去，客服看完助手的建议，再自己登录系统批准退款。现在希望 Agent 直接执行。接口可以相同，授权和责任已经变了。

请业务负责人和系统负责人一起查下面四项。风险编号用于连接后续验收，便于在复盘时找回当时的决定。

| 风险编号 | 容易沿用的做法 | 在退款项目中会发生什么 | 要补的材料与验收 |
|---|---|---|---|
| HM-01 | 把给人看的建议直接当执行指令 | 一份未获批准的建议改变了业务状态 | [第 5 站](05-action-contract.md)：分开 Read、Draft、Write，验证前两者不写业务对象 |
| HM-02 | 只记录接口返回成功 | 查不到为什么批准，是否真的形成付款指令 | [动作契约](../../config/actions/)与[第 9 站决策记录](09-evaluation-audit-and-incident-replay.md)：核对前后状态和实际效果 |
| HM-03 | 复用客服主管账号 | 审计只能看到主管操作，分不清是谁发起 | [第 3 站身份](03-identity-acceptance.md)与[第 7 站权限](07-identity-and-permissions.md)：未登记主体必须被拒绝 |
| HM-04 | 换一个版本就扩大自动化范围 | 权限扩大了，业务条件和责任没有重审 | 身份配置的晋级条件、[事故回放](../../config/evals/incident_replays.json)与[第 10 站交接](10-operations-handoff-and-replication.md) |

## 在参考程序中核对

```bash
python3 run.py summary
python3 run.py run YF-R-0500 --mode draft
python3 run.py run YF-R-0500 --mode write --actor agent.marketing.unknown
python3 run.py checkpoint 2 --check
```

第一笔运行应停在建议，退款仍为 `pending_review`；第二笔即使业务条件满足，也会因主体未获授权而拒绝，命中 `G-ACTOR`。检查卡只确认四项风险已记录，实际行为要看运行结果和测试。

把审计结论写成可以验收的工作，例如“未登记主体不得创建付款指令”，并请安全和财务确认。写成“加强治理”，接手的人还不知道该改哪里。

[返回十站目录](../book-map.md)。
