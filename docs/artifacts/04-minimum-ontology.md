# 第 4 站：把几条记录连成一笔退款

客服系统说 `YF-R-0311`，售后系统记录为 `AS-RMA-250311`，订单又有自己的编号。先确定这些记录指向谁，再讨论用什么图数据库。这个项目用本地 JSON 和 Python 就能完成第一轮检查。

## 第一版需要回答的问题

1. 谁申请退款，涉及哪个订单和订单项？
2. 金额、签收时间、发票状态分别由哪个来源确认？
3. 哪条风控信号、哪份工单和证据支持本次判断？
4. 申请现在是什么状态，可以进入哪些后续状态？
5. 执行后生成了哪笔付款指令；失败时留下什么待办？

围绕这些问题，[对象目录](../../config/ontology/objects.yaml)包含客户、订单、订单项、退款申请、风控信号、工单六类核心对象，以及发票、证据、付款指令三类辅助对象。首次练习无需给整个企业建立全部对象。

## 字段应该听谁的

| 字段 | 本项目的来源约定 | 要向谁确认 |
|---|---|---|
| 客户等级与渠道 | CRM 主数据 | 客户主数据负责人 |
| 实付金额与签收 | 商城订单 | 交易与履约负责人 |
| 发票状态 | ERP 台账或财务明确确认 | 财务 |
| 退款状态 | 售后申请 | 客服运营 |
| 风控信号 | 最近一次风控观测 | 风控负责人 |

查看[来源映射](../../config/ontology/source_map.yaml)和[编号映射](../../data/mock/source_crosswalk.json)。发票 `not_found` 映射为 `unknown`；只有财务确认记录才能支持 `none`。来源映射中的新鲜度指标需要在真实连接器中实现，本地样例不会自动刷新。

## 从数据生成关系

```text
Customer ─OWNS→ Order ─CONTAINS→ OrderItem
RefundRequest ─REQUESTED_BY→ Customer
RefundRequest ─FOR_ORDER→ Order
RefundRequest ─TARGETS→ OrderItem
RiskSignal ─ABOUT→ Customer
Evidence ─SUPPORTS→ RefundRequest
PaymentInstruction ─SETTLES→ RefundRequest
```

上面列的是部分关系类型。程序按样例中的编号生成实际节点与连线；并不是每一笔申请都有发票或付款指令。

```bash
python3 run.py graph --refund-id YF-R-0311
python3 run.py checkpoint 4 --check
```

先沿申请找到订单项，再找支持申请的视频。查不到发票时，图里不应捏造发票对象。图的节点和边会随数据及本次执行产生的对象改变，不必为了对齐一张旧截图硬凑数量。

## 状态不能随意跳转

[状态机](../../config/ontology/state_machines.yaml)没有允许 `pending_review → paid_out` 直接跳转。批准和到账是两个业务事实。批准后创建付款指令失败，退款应进入 `approval_pending_payment`，不能假装审批从未发生。

请业务人员沿图复述一遍，数据负责人核对来源和编号，财务确认“批准”“待付款”“已支付”的区别。关系无悬空引用、非法状态转换被拒绝等行为在[数据与本体测试](../../tests/test_repository.py)中验证。

[下一站：动作契约](05-action-contract.md) · [返回十站目录](../book-map.md)。
