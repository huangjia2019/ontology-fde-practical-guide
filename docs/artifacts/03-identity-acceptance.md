# 第 3 站：给退款助手登记身份

退款助手以 `agent.cs.refund.001` 执行。它不冒充客服主管，记录中的 `as_itself` 表示以自身身份行动。身份由[refund_agent.yaml](../../config/identity/refund_agent.yaml)描述。

## IART 四个问题

| 维度 | 在这里指什么 | 配置中查看什么 |
|---|---|---|
| Identity：身份 | 它是谁，以谁的名义行动 | `technical_id`、`representation`、业务与技术负责人 |
| Agency：行动能力 | 可以读、建议、调用和写什么 | `read`、`draft`、`call`、`write`、`forbidden` |
| Relationship：关系 | 服务谁，受谁监督，和谁协作 | `users`、`supervisors`、`data_sources`、`peer_agents` |
| Temporality：生命周期 | 哪个版本，何时扩大或收回权限 | `promotion_gate`、`rollback_on`、`retirement_conditions` |

配置中的业务责任岗位是客服运营负责人，技术责任岗位是客户平台工程团队。到自己的项目里，需要把岗位落实到实际人员；写一个 `owner` 字段并不会让对方自动承担交接工作。

## 从人工决策到条件自动化

身份配置保留了一组晋级条件：36 个策略样例和 2 个事故回放通过，决策记录覆盖符合要求，拒绝未授权主体的测试通过，并得到业务负责人批准。越权、无法解释的写入或证据来源缺失，触发收回权限的讨论与处理。

当前仓库已经包含条件自动批准的参考实现，不会运行完第 3 站才逐步开放写入。晋级、回退字段是供人审查的治理约定，本地程序没有连接企业的审批或账号管理系统。

```bash
python3 run.py identity
python3 run.py run YF-R-0500 --mode write --actor agent.marketing.unknown
python3 run.py checkpoint 3 --check
```

未知主体的结果应包含 `G-ACTOR`，前后状态都为 `pending_review`，不创建付款指令。请技术与安全负责人核对身份、契约允许主体、权限策略中的 `agent_id` 是否一致。

这里通过命令参数传入身份，便于演练拒绝行为。真实环境必须从可信认证结果取得身份，不能把用户输入的字符串当作认证证明。[第 7 站](07-identity-and-permissions.md)继续检查一次动作是否获准。

[返回十站目录](../book-map.md)。
