# 第 7 站：条件都满足，也要问谁有权执行

选 `YF-R-0500` 做这一站的练习，因为它的业务条件全部通过。现在只改变执行主体，让一个未登记的营销 Agent 尝试批准。这样可以单独检查权限，不把金额和发票等问题混进来。

```bash
python3 run.py run YF-R-0500 --mode write --actor agent.marketing.unknown
python3 run.py checkpoint 7 --check
```

结果应为 `permission_denied`，命中 `G-ACTOR`；前后状态都为 `pending_review`，不创建付款指令。任务信封标记 `rejected_actor_mismatch`，调用轨迹中有被拦截的 `action.enforce_write_guard`。

## 六个维度分别限定什么

查看[权限配置](../../config/policies/permissions.yaml)，并与[身份](../../config/identity/refund_agent.yaml)及[动作契约](../../config/actions/approve_refund_small.yaml)对照。

| 维度 | 本项目约定 | 要请谁确认 |
|---|---|---|
| 数据 | 读取退款所需对象，不读取完整银行卡号、证件号和营销画像 | 数据负责人、安全 |
| 工具 | 查询事实、评估规则、经控制创建指令和人工材料 | 系统负责人 |
| 动作 | 小额批准、转人工、补证；禁止修改申请金额 | 客服主管、财务 |
| 条件 | 金额、证据、风控及其他退款条件通过 | 业务规则负责人 |
| 时间 | 配置声明授权起止时间 | 安全、授权负责人 |
| 环境 | 仅声明 `demo`、`gray`，`production_write: false` | 发布与安全负责人 |

## 哪些已经运行，哪些还需要集成

当前执行器检查主体、业务条件、任务信封期限、状态转换和写入结果。`--actor` 是便于教学的参数，不提供身份认证。字段级脱敏、真实凭据到期、权限配置中的授权时间窗和企业环境准入，尚未接入 IAM 或网关执行。

`production_write: false` 表示本项目不授权生产写入。程序本身也没有真实企业写接口；不能仅凭这项配置，就宣称已经完成生产环境隔离。

请再运行金额越界那笔：

```bash
python3 run.py run YF-R-0501 --mode write
```

这次主体合法，但 500.01 元超过自动批准上限，仍须转人工。身份正确和动作获准，需要分别检查。

安全负责人应能指出认证与授权实际发生在哪里，财务应能说明哪些权限不能扩大，系统负责人应能拿出拒绝后的记录。若准备将上限从 500 元改为其他值，需要同步契约、实现绑定、边界测试与业务审批。

[返回十站目录](../book-map.md)。
