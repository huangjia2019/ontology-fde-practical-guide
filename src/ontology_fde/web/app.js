const state = { summary: null, cases: [], facts: null, graph: null, lastRun: null, evaluation: null, busy: false };
const params = new URLSearchParams(location.search);
const requestedView = params.get("view") || "ontology";

const caseNames = {
  "YF-R-0311": "遥控器单", "YF-R-0312": "小额黑名单", "YF-R-0415": "合同优先",
  "YF-R-0500": "刚好五百", "YF-R-0501": "多出一分", "YF-R-0602": "频繁退款",
  "YF-R-0610": "风控有异", "YF-R-0702": "证据未齐", "YF-R-0703": "开封耗材",
  "YF-R-0704": "已经开票", "YF-R-0800": "退款指令失败演练"
};
const outcomeLabels = {
  auto_approve: "建议自动批准", auto_approved: "已批准，已生成模拟退款指令",
  queued_for_human: "已转人工审核", queue_human: "需要人工审核",
  compensated: "已批准，退款指令失败待财务处理", evidence_requested: "已生成补证草稿",
  request_evidence: "需要补充证据", permission_denied: "权限检查未通过",
  missing_data: "必要事实缺失", not_ready: "当前状态不能执行", drafted: "已生成建议，尚未执行",
  task_expired: "任务授权已过期", no_action: "不执行动作"
};
const checkLabels = {
  grounded_customer: "客户对象已关联", grounded_order: "订单对象已关联", grounded_item: "订单项已关联",
  risk_object_present: "风控对象已读取", actor_allowed: "执行主体已获授权",
  state_pending_review: "申请处于待审核状态", order_fulfilled: "订单已完成履约",
  evidence_accepted: "退款证据已通过核验", invoice_status_known_safe: "发票状态允许继续处理",
  amount_within_auto_limit: "金额不超过 500 元", task_envelope_not_expired: "任务授权未过期",
  risk_level_known: "风控结果可识别", amount_valid: "金额有效且大于零", action_allowed: "动作已获授权"
};
const invoiceStatusLabels = {
  unknown: "待核实：本次查询未查到记录", none: "已确认未开票（ERP 明确返回）",
  pending: "正在开票", issued: "已开票", reversed: "已冲红"
};
const stateLabels = {
  pending_review: "待审核", pending_human: "待人工审核", approved: "已批准",
  approval_pending_payment: "已批准，待财务处理", draft: "草稿", signed: "已签收", closed: "已完成",
  normal: "普通", vip: "VIP", blacklist: "黑名单", clear: "风控无异", review: "需复核", block: "拦截",
  accepted: "已通过", missing: "缺失", rejected: "未通过", created: "已创建（未到账）",
  failed: "失败", damaged: "损坏", triaged: "已分派", open: "待处理", active: "有效",
  none: "无", unknown: "待核实", pending: "待处理", issued: "已开票", reversed: "已冲红", paid_out: "已支付"
};
const systemLabels = {
  CRM: "客户系统", COMMERCE: "订单系统", AFTER_SALES: "售后系统", ERP: "财务系统",
  SUPPORT: "客服系统", RISK: "风控系统", EVIDENCE: "证据库", PAYMENTS: "支付模拟"
};
const typeLabels = {
  Customer: "客户", Order: "订单", OrderItem: "订单项", RefundRequest: "退款申请",
  Ticket: "客服工单", RiskSignal: "风控信号", Evidence: "证据", Invoice: "发票",
  PaymentInstruction: "退款指令", HumanApprovalPacket: "人工审批材料", FinanceManualTask: "财务任务",
  EvidenceRequestDraft: "补证草稿"
};
const relationLabels = {
  OWNS: "拥有", CONTAINS: "包含", TARGETS: "针对商品", FOR_ORDER: "对应订单",
  REQUESTED_BY: "申请人", ABOUT: "涉及客户", OPENED_BY: "由客户提出", ABOUT_REFUND: "对应申请",
  BILLS: "为订单开票", SUPPORTS: "支持申请", SETTLES: "退款指令对应"
};
const actionLabels = {
  approve_refund_small: "批准小额退款", request_human_refund_approval: "转交人工审核",
  request_missing_evidence: "拟定补证请求", no_action: "不执行动作"
};
const ruleLabels = {
  R1: "已开封耗材签收超过 24 小时", R2: "已开票，需财务复核", R3: "黑名单客户需人工审核",
  R4: "30 天内第 3 次及以上退款", R5: "合同客户或渠道未确认，先核对条款",
  "G-AMOUNT": "金额超过自动批准上限", "G-INVOICE-UNKNOWN": "发票查询未查到，状态待核实",
  "G-RISK": "风控要求复核或拦截", "G-EVIDENCE": "证据未通过", "G-DATA": "必要事实缺失或未确认",
  "G-ACTOR": "执行主体未获授权", "G-ACTION": "动作未获授权", "G-STATE": "状态不允许执行",
  "G-ENVELOPE-EXPIRED": "任务授权过期", "G-ORDER": "订单履约状态需人工核实"
};
// Display translations only: source data, canonical identifiers and JSON stay unchanged.
const textLabels = {
  "Conference display remote control": "会议平板遥控器", "Six-meter conference cable": "6 米会议连接线",
  "Yunfan Meetings annual seat": "云帆会议年度席位", "Desktop omnidirectional microphone": "桌面全向麦克风",
  "Conference camera": "会议摄像头", "Multiport dock": "多接口扩展坞",
  "Mobile display stand accessory": "移动显示支架配件", "Power adapter": "电源适配器",
  "Microphone windscreens, pack of 10": "麦克风防风罩（10 只装）",
  "No anomalous transactions in the past 90 days": "近 90 天未发现异常交易",
  "Account-abuse history requires human verification": "存在账号滥用记录，需要人工核实",
  "No risk anomaly for this contract customer": "该合同客户未发现风控异常",
  "No anomaly for this VIP customer in the past 90 days": "该 VIP 客户近 90 天未发现异常",
  "The model does not cover refund frequency; Customer Service policy evaluates that rule": "此风控结果不覆盖退款频次，频次由客服规则另行检查",
  "Several after-sales requests came from the same device within a short period": "同一设备短时间内发起多笔售后申请",
  video: "视频", photo: "照片", audio: "音频", contract_excerpt: "合同摘录",
  baseline_clear: "基础检查无异", vip_clear: "VIP 检查无异", identity_abuse_history: "账号滥用记录",
  contract_customer: "合同客户", device_velocity: "短时集中申请",
  "Remote will not pair": "遥控器无法配对", "Return unopened item": "退回未拆封商品",
  "Contract customer seat adjustment": "合同客户调整席位", "Background noise from omnidirectional microphone": "全向麦克风有底噪",
  "Camera autofocus failure": "摄像头无法自动对焦", "Dock does not match equipment": "扩展坞与设备不匹配",
  "Damaged in transit": "运输中损坏", "Adapter will not charge": "适配器无法充电",
  "Return opened consumables": "退回已开封耗材", "Remote failure on invoiced order": "已开票订单的遥控器故障",
  "Excessive microphone noise": "麦克风噪声过大",
  "A refund action requires a verifiable object, time, and evidence": "退款动作需要可核实的对象、时间和证据。",
  "Yunfan official-store B2C after-sales service": "云帆官方商城的个人客户售后",
  "Opened consumables": "已开封耗材",
  "After 24 hours, do not use automatic refund; route the request to a customer service supervisor": "签收超过 24 小时后，转交客服主管审核，不进入自动退款路径。",
  "Read customer master data": "读取客户资料", "Read order": "读取订单", "Read order item": "读取订单项",
  "Read refund request": "读取退款申请", "Read invoice status": "查询发票状态", "Read support ticket": "读取客服工单",
  "Read risk signal": "读取风控信号", "Read refund evidence": "读取退款证据", "Validate task envelope": "核对任务授权",
  "Verify refund evidence": "核验退款证据", "Evaluate refund policy": "检查退款规则", "Resolve agent proposals": "处理建议冲突",
  "Update refund state": "更新退款状态", "Create refund instruction": "创建退款指令",
  "Enter payment compensation state": "转入待财务处理状态", "Create finance manual task": "建立财务人工任务",
  "Create human approval packet": "建立人工审批材料", "Draft evidence request": "拟定补证请求", "Enforce write guard": "执行写入守卫"
};

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[char]));
}
const textLabel = value => textLabels[value] || value || "—";
const stateLabel = value => stateLabels[value] || value || "—";
const outcomeLabel = value => outcomeLabels[value] || value || "尚无结果";
const amountLabel = value => `${Number(value).toLocaleString("zh-CN", {maximumFractionDigits: 2})} 元`;

async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { "Content-Type": "application/json", ...options.headers } });
  let payload;
  try { payload = await response.json(); } catch { throw new Error("服务没有返回可读结果。请确认本机服务仍在运行，再刷新页面。"); }
  if (!response.ok) throw new Error(payload.error || `请求未完成（HTTP ${response.status}）`);
  return payload;
}

function message(text, isError = false) {
  const box = document.querySelector("#message");
  box.textContent = text;
  box.className = `message${isError ? " error" : ""}`;
  box.hidden = !text;
}

function setBusy(busy) {
  state.busy = busy;
  document.querySelectorAll("[data-mode], #resetBtn, #caseSelect, #paymentFailure").forEach(node => { node.disabled = busy; });
  document.querySelector("main").setAttribute("aria-busy", String(busy));
}

async function perform(action) {
  if (state.busy) return;
  setBusy(true); message("");
  try { await action(); }
  catch (error) { message(`本次操作未完成：${error.message || error}。若刚才点击了执行，请先刷新核对状态，不要假定没有写入。`, true); }
  finally { setBusy(false); }
}

async function boot() {
  setBusy(true);
  [state.summary, state.cases, state.evaluation] = await Promise.all([
    api("/api/summary"), api("/api/cases"), api("/api/evaluation")
  ]);
  const select = document.querySelector("#caseSelect");
  select.innerHTML = state.cases.map(row =>
    `<option value="${escapeHtml(row.refund_id)}">${escapeHtml(caseNames[row.refund_id] || row.refund_id)} · ${amountLabel(row.amount)} · ${escapeHtml(row.refund_id)}</option>`
  ).join("");
  const requestedCase = params.get("case");
  select.value = state.cases.some(row => row.refund_id === requestedCase) ? requestedCase : "YF-R-0311";
  renderSummary(); renderEvaluation(); bindEvents(); switchView(requestedView);
  await refreshCase();
  setBusy(false);
  // Opening a shared URL must never reset data or execute a business action.
}

function bindEvents() {
  document.querySelectorAll(".nav-btn").forEach(button => button.addEventListener("click", () => switchView(button.dataset.view)));
  document.querySelector("#caseSelect").addEventListener("change", () => perform(async () => {
    state.lastRun = null;
    document.querySelector("#paymentFailure").checked = false;
    await refreshCase();
  }));
  document.querySelectorAll("[data-mode]").forEach(button => button.addEventListener("click", () => perform(() => runMode(button.dataset.mode))));
  document.querySelector("#resetBtn").addEventListener("click", () => perform(async () => {
    await api("/api/reset", {method:"POST", body:"{}"});
    state.lastRun = null;
    document.querySelector("#paymentFailure").checked = false;
    await refreshCase();
    message("所有申请已恢复到初始演练状态。之前复制到页面外的学习记录不受影响。");
  }));
  document.querySelector("#copyAudit").addEventListener("click", async () => {
    if (!state.lastRun?.decision_record) return message("先生成建议或执行模拟，才有决策记录可以复制。");
    try {
      if (!navigator.clipboard) throw new Error("clipboard unavailable");
      await navigator.clipboard.writeText(document.querySelector("#auditJson").textContent);
      message("决策记录已复制，可以粘贴到自己的学习笔记中。");
    } catch { message("浏览器不允许自动复制，请选中右侧完整记录后手动复制。", true); }
  });
}

function switchView(view) {
  const safe = ["ontology","action","audit","evaluation"].includes(view) ? view : "ontology";
  document.querySelectorAll(".view").forEach(node => node.classList.toggle("active", node.id === `view-${safe}`));
  document.querySelectorAll(".nav-btn").forEach(node => {
    node.classList.toggle("active", node.dataset.view === safe);
    node.setAttribute("aria-pressed", String(node.dataset.view === safe));
  });
  const copy = {
    ontology: ["业务对象", "这笔申请关联了谁、哪张订单、什么证据？每项事实都能追到来源记录。"],
    action: ["退款处理", "读取事实、形成建议、执行模拟。观察哪一步改变了业务状态，哪一步没有。"],
    audit: ["决策记录", "谁作了决定，依据是什么，实际改了什么？沿着同一条追踪编号逐项核对。"],
    evaluation: ["测试与评估", "用已知结果核对规则，再检查候选规则距离执行还缺哪些条件。"]
  }[safe];
  document.querySelector("#viewTitle").textContent = copy[0];
  document.querySelector("#viewSubtitle").textContent = copy[1];
}

async function refreshCase() {
  const id = document.querySelector("#caseSelect").value;
  [state.facts, state.graph] = await Promise.all([
    api(`/api/cases/${encodeURIComponent(id)}`), api(`/api/graph?refund_id=${encodeURIComponent(id)}`)
  ]);
  renderFacts(); renderGraph(); renderAction(); renderAudit();
  document.querySelector("#nodeCount").textContent = state.graph.nodes.length;
}

function renderSummary() {
  document.querySelector("#sourceCount").textContent = state.summary.source_count;
  document.querySelector("#goldenCount").textContent = `${state.summary.golden.passed}/${state.summary.golden.total}`;
}

function renderFacts() {
  const f = state.facts;
  const channels = {b2c:"个人客户（B2C）", b2b:"企业合同客户（B2B）"};
  const values = [
    ["客户", f.customer_name], ["渠道 / 客户类型", `${channels[f.customer_channel] || "渠道待核实"} / ${stateLabel(f.customer_tier)}`],
    ["退款金额", amountLabel(f.amount)], ["申请状态", stateLabel(f.refund_status)],
    ["订单", `${f.order_id} · ${stateLabel(f.order_status)}`], ["商品", textLabel(f.item_name)],
    ["发票状态", invoiceStatusLabels[f.invoice_status] || f.invoice_status], ["风控", `${stateLabel(f.risk_level)} · ${textLabel(f.risk_reason)}`],
    ["证据", stateLabel(f.evidence_status)], ["近 30 天此前退款次数", `${f.previous_refunds_30d} 次（不含本次）`]
  ];
  document.querySelector("#factSummary").innerHTML = values.map(([key,value]) =>
    `<div class="fact"><small>${escapeHtml(key)}</small><strong>${escapeHtml(value)}</strong></div>`).join("");
  const observations = {not_found:"本次查询未查到记录", confirmed_no_invoice:"已确认未开票"};
  document.querySelector("#sourceRefs").innerHTML = f.source_refs.map(ref => {
    const observation = observations[ref.observation];
    return `<div class="source-item"><b>${escapeHtml(systemLabels[ref.system] || ref.system)}</b><div><code>${escapeHtml(ref.source_id)}</code>${observation ? `<small>${observation}</small>` : ""}</div></div>`;
  }).join("");
}

function renderGraph() {
  const svg = document.querySelector("#graph");
  svg.innerHTML = `<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="#9aafbd"></path></marker></defs>`;
  const base = {
    Customer:[35,210], Order:[285,65], OrderItem:[565,65], RefundRequest:[825,210],
    Ticket:[550,380], RiskSignal:[35,400], Evidence:[835,30], Invoice:[285,390], PaymentInstruction:[1020,390],
    HumanApprovalPacket:[1020,500], FinanceManualTask:[1020,610], EvidenceRequestDraft:[800,500]
  };
  const counts = {}, positions = {};
  state.graph.nodes.forEach(node => {
    const index = counts[node.type] || 0; counts[node.type] = index + 1;
    const [x,y] = base[node.type] || [1020,30]; positions[node.id] = {x, y:y + index*90};
  });
  const height = Math.max(525, ...Object.values(positions).map(p => p.y+100));
  svg.setAttribute("viewBox", `0 0 1200 ${height}`);
  state.graph.edges.forEach(edge => {
    const a = positions[edge.from], b = positions[edge.to]; if (!a || !b) return;
    const x1=a.x+78, y1=a.y+36, x2=b.x+78, y2=b.y+36;
    svg.insertAdjacentHTML("beforeend", `<path class="graph-edge" marker-end="url(#arrow)" d="M${x1},${y1} C${(x1+x2)/2},${y1} ${(x1+x2)/2},${y2} ${x2},${y2}"></path><text class="graph-edge-label" x="${(x1+x2)/2}" y="${(y1+y2)/2-7}" text-anchor="middle">${escapeHtml(relationLabels[edge.type] || edge.type)}</text>`);
  });
  state.graph.nodes.forEach(node => {
    const p = positions[node.id];
    const cls = node.type === "RefundRequest" ? "node-refund" : node.type === "RiskSignal" ? "node-risk" : "";
    let label = textLabel(node.label);
    if (node.type === "RefundRequest") label = node.object_id;
    if (node.type === "Customer") label = node.object_id;
    const shortLabel = label.length > 20 ? label.slice(0,19)+"…" : label;
    const detail = node.type === "RefundRequest" ? `${stateLabel(node.state)} · ${amountLabel(state.facts.amount)}` : stateLabel(node.state || "active");
    svg.insertAdjacentHTML("beforeend", `<g class="graph-node ${cls}" transform="translate(${p.x},${p.y})"><title>${escapeHtml(`${typeLabels[node.type] || node.type} · ${node.object_id}\n${textLabel(node.label)}\n${stateLabel(node.state)}\n${node.source_id}`)}</title><rect class="node-box" width="156" height="76" rx="9"></rect><text class="node-type" x="10" y="17">${escapeHtml(typeLabels[node.type] || node.type)}</text><text class="node-label" x="10" y="36">${escapeHtml(shortLabel)}</text><text class="node-state" x="10" y="53">${escapeHtml(detail)}</text><text class="node-source" x="146" y="68" text-anchor="end">${escapeHtml(systemLabels[node.source_system] || node.source_system)}</text></g>`);
  });
  document.querySelector("#graphLegend").innerHTML = "<span>当前退款申请</span><span>风控信号</span><span>其他业务对象与关系</span>";
}

function effectSummary(record, draft) {
  if (record?.metadata?.idempotent_replay) return "本次返回上一次执行的记录，没有重复写入。要从初始状态重做，请点击“重置演练”。";
  if (!record || record.mode === "draft") {
    const rules = (draft?.rule_hits || []).map(rule => ruleLabels[rule] || rule).join("；");
    return `建议：${outcomeLabel(draft?.decision)}。${rules || "金额、证据、履约、发票、风控、频次和渠道检查均通过。"} 这里只形成建议，业务状态没有变化。`;
  }
  const explanations = {
    auto_approved:"申请状态改为已批准，并创建了模拟退款指令。没有连接支付系统，也没有到账回执。",
    queued_for_human:"申请已进入人工审核队列，并生成审批材料。系统没有代替审核人批准退款。",
    compensated:"批准结果保留，申请进入待财务处理状态，并建立财务人工任务。失败的退款指令尚未完成，资金没有退回。",
    evidence_requested:"已建立补证请求草稿。退款申请状态未变，尚未向客户发送消息。",
    permission_denied:"写入已被拦截，没有修改业务对象。请查看权限和动作检查。",
    missing_data:"必要事实缺失或未确认，未执行退款动作。",
    not_ready:"申请当前状态不允许执行，未修改业务对象。",
    task_expired:"任务授权已过期，必须重新委托。申请和关联业务对象均未修改。",
    no_action:"申请已经结束，本次没有再执行业务动作。"
  };
  return explanations[record.outcome] || record.actual_effect;
}

function renderAction() {
  const f = state.facts;
  document.querySelector("#caseBanner").innerHTML = `<strong>${escapeHtml(caseNames[f.refund_id] || f.refund_id)}</strong><span>${escapeHtml(f.refund_id)} · ${escapeHtml(textLabel(f.item_name))}</span><b>${amountLabel(f.amount)}</b>`;
  const box = document.querySelector("#actionOutcome");
  if (!state.lastRun) {
    box.className = "outcome empty"; box.textContent = "先读取事实，再生成建议，最后观察执行会改变什么。";
    document.querySelector("#checks").innerHTML = ""; document.querySelector("#rules").innerHTML = ""; renderPipeline([]); return;
  }
  const draft = state.lastRun.draft, record = state.lastRun.decision_record;
  renderPipeline(state.lastRun.stages);
  if (!draft && !record) {
    box.className = "outcome";
    box.innerHTML = `<strong>已读取来源记录</strong>共读取 ${state.lastRun.facts.source_refs.length} 条来源。申请仍为“${escapeHtml(stateLabel(state.lastRun.facts.refund_status))}”，没有执行业务动作。`;
    document.querySelector("#checks").innerHTML = ""; document.querySelector("#rules").innerHTML = ""; return;
  }
  const outcome = record?.outcome || draft.decision;
  const warn = ["queued_for_human","compensated","queue_human","drafted"].includes(outcome) ? " warn" : ["permission_denied","missing_data","task_expired"].includes(outcome) ? " danger" : "";
  box.className = `outcome${warn}`;
  const action = draft?.final_action || record?.final_action || "no_action";
  box.innerHTML = `<strong>${escapeHtml(outcomeLabel(outcome))}</strong>${escapeHtml(effectSummary(record, draft))}<br><code>动作：${escapeHtml(actionLabels[action] || action)} · ${escapeHtml(action)}</code>`;
  document.querySelector("#checks").innerHTML = Object.entries(draft?.checks || record.checks || {}).map(([key,value]) => `<div class="check ${value ? "" : "fail"}">${escapeHtml(checkLabels[key] || key)}</div>`).join("");
  const hits = draft?.rule_hits || record.rule_hits || [];
  document.querySelector("#rules").innerHTML = hits.length ? hits.map(rule => `<span class="rule-hit">${escapeHtml(rule)} · ${escapeHtml(ruleLabels[rule] || "请查完整决策记录")}</span>`).join("") : "<span class=\"rule-clear\">没有命中拦截或转人工规则。</span>";
}

function renderPipeline(stages) {
  document.querySelectorAll("#pipeline .stage").forEach((node,index) => node.classList.toggle("complete", stages[index]?.status === "complete"));
}

async function runMode(mode) {
  const refund_id = document.querySelector("#caseSelect").value;
  state.lastRun = await api("/api/run", { method:"POST", body: JSON.stringify({refund_id, mode, simulate_payment_failure:document.querySelector("#paymentFailure").checked}) });
  await refreshCase();
}

function approvalLabel(record) {
  if (record.mode === "draft") return "尚未执行，仅生成建议";
  if (["auto_approved","compensated"].includes(record.outcome)) return "已批准；到账另行确认";
  if (record.outcome === "queued_for_human") return "尚未批准，待人工审核";
  return "本次未批准退款";
}

function renderAudit() {
  const record = state.lastRun?.decision_record;
  if (!record) {
    document.querySelector("#traceIdBadge").textContent="尚无记录";
    document.querySelector("#auditHeadline").className="audit-headline empty";
    document.querySelector("#auditHeadline").textContent="生成建议或执行模拟后，这里会列出依据、规则和结果。只读取事实不会生成决策记录。";
    for (const id of ["auditTrace", "toolCalls", "agentConflict"]) document.getElementById(id).innerHTML="";
    document.querySelector("#auditJson").textContent='{ "status": "waiting_for_decision" }'; return;
  }
  document.querySelector("#traceIdBadge").textContent=record.trace_id;
  document.querySelector("#auditHeadline").className="audit-headline";
  document.querySelector("#auditHeadline").innerHTML=`<strong>${escapeHtml(outcomeLabel(record.outcome))}</strong><span>${escapeHtml(record.decision_id)} · ${escapeHtml(record.actor)} · ${record.representation === "as_itself" ? "以自身身份执行" : escapeHtml(record.representation)}</span>`;
  const instruction = state.graph?.nodes.find(node => node.type === "PaymentInstruction");
  const rows = [
    ["证据", `${record.evidence_refs.length} 项证据 / ${record.source_refs.length} 条来源`, record.target_objects.at(-1)],
    ["规则", record.rule_hits.length ? record.rule_hits.map(rule => `${rule} ${ruleLabels[rule] || ""}`).join("；") : "未命中拦截或转人工规则", record.policy_version],
    ["审批", approvalLabel(record), `自动批准金额上限 ${amountLabel(record.approval.threshold_cny)}`],
    ["状态", `${stateLabel(record.state_before)} → ${stateLabel(record.state_after)}`, `退款指令：${instruction ? stateLabel(instruction.state) : "未创建"}`]
  ];
  document.querySelector("#auditTrace").innerHTML=rows.map(([label,title,detail])=>`<div class="trace-row"><b>${escapeHtml(label)}</b><div><strong>${escapeHtml(title)}</strong><span>${escapeHtml(detail)}</span></div></div>`).join("");
  const statuses={succeeded:"成功",failed:"失败",blocked:"拦截",needs_input:"待补充"};
  const phases={read:"读取",draft:"建议",write:"写入",compensate:"补偿处理"};
  document.querySelector("#toolCalls").innerHTML=(record.tool_calls||[]).map(call=>`<div class="tool-call status-${escapeHtml(call.status)}">
    <div class="tool-call-top"><b><i>${Number(call.sequence)}</i>${escapeHtml(textLabel(call.display_name))}</b><span>${escapeHtml(statuses[call.status]||call.status)} · ${Number(call.duration_ms)}ms</span></div>
    <code>${escapeHtml(call.tool_name)}</code><small>${escapeHtml(phases[call.phase]||call.phase)} · ${escapeHtml(call.target)}</small>
  </div>`).join("");
  const conflict=record.conflict_resolution;
  document.querySelector("#agentConflict").innerHTML=conflict?`<div class="conflict-card"><b>退款建议与风控意见冲突</b><div class="conflict-flow"><b>退款助手建议批准</b><i>风控要求优先 →</i><b>${escapeHtml(conflict.winner === "RiskAgent:block" ? "拦截并转人工" : conflict.winner === "RiskAgent:review" ? "转人工复核" : conflict.winner)}</b></div><p>风控要求复核或拦截时，退款助手不能自行放行。依据：${escapeHtml(conflict.policy_id)}</p></div>`:"";
  document.querySelector("#auditJson").textContent=JSON.stringify(record,null,2);
}

function renderEvaluation() {
  const e=state.evaluation, core=e.core;
  document.querySelector("#evalBadge").textContent=`${core.passed===core.total?"全部通过":"有用例未通过"} · ${core.passed}/${core.total}`;
  document.querySelector("#evalRing strong").textContent=`${Math.round(core.pass_rate*100)}%`;
  document.querySelector("#evalRing").style.setProperty("--pass-rate", `${Math.min(100,Math.max(0,core.pass_rate*100))}%`);
  const names={facts:"事实完整性",ontology:"对象关联",policy:"规则决策",action:"动作执行",adversarial:"对抗输入",business:"业务结果"};
  document.querySelector("#categoryBars").innerHTML=Object.entries(core.categories).map(([name,row])=>`<div class="bar"><span>${escapeHtml(names[name]||name)}</span><div><i style="width:${row.total ? row.passed/row.total*100 : 0}%"></i></div><b>${row.passed}/${row.total}</b></div>`).join("");
  document.querySelector("#incidentCount").textContent=`${e.incident_replays.passed}/${e.incident_replays.total}`;
  const demo=e.document_to_rule, draft=demo.draft, validation=demo.validation;
  document.querySelector("#ruleState").textContent=`${stateLabel(draft.lifecycle.state)} · 未获准上线`;
  const layerLabels={general:"通用约束",context:"适用场景",decision:"处理规则"};
  document.querySelector("#ruleLayers").innerHTML=Object.entries(draft.knowledge_layers).map(([name,items])=>`<div class="layer"><b>${escapeHtml(layerLabels[name]||name)}</b><span>${escapeHtml(items.map(textLabel).join("；"))}</span></div>`).join("");
  const labels={structural:"结构完整",semantic:"字段映射",operational:"运行用例",epistemic:"规则依据"};
  document.querySelector("#validationGrid").innerHTML=Object.entries(validation.validation_types).map(([name,row])=>`<div class="validation ${row.passed ? "" : "failed"}"><b>${escapeHtml(labels[name]||name)}</b><span>${row.passed?"✓ 通过":"× 未通过"}</span></div>`).join("");
  const kindLabels={positive:"符合规则",negative:"不符合规则",boundary:"边界值",missing_data:"缺少数据",out_of_scope:"范围外"};
  const actualLabels={match:"命中",no_match:"未命中",missing_data:"缺少数据",out_of_scope:"范围外"};
  document.querySelector("#ruleCases").innerHTML=validation.validation_types.operational.cases.map(row=>`<span class="case-pill ${row.passed?"pass":""}">${escapeHtml(kindLabels[row.kind]||row.kind)} · ${escapeHtml(actualLabels[row.actual]||row.actual)}</span>`).join("");
  const blockerLabels={missing_inputs_not_resolved:"开封状态等必要输入尚未补齐",human_review_not_completed:"业务负责人尚未审核",rule_not_compiled:"规则尚未编译"};
  const blockers=(validation.production_blockers||[]).map(item=>blockerLabels[item]||item).join("；");
  document.querySelector("#executionGuard").textContent=`候选规则不能进入生产执行：${blockers}。`;
}

boot().catch(error => {
  message(`工作台未能加载：${error.message || error}。请确认本机服务正在运行，再刷新页面。`, true);
  // Leave controls disabled until a complete initial state has loaded.
});
