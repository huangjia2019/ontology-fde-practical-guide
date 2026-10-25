from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .exit_drill import exit_drill_payload
from .paths import load_structured, project_root
from .repository import EnterpriseRepository


@dataclass(frozen=True, slots=True)
class CheckpointSpec:
    number: int
    title: str
    problem: str
    artifacts: tuple[str, ...]
    commands: tuple[str, ...]
    acceptance: tuple[str, ...]


CHECKPOINTS: dict[int, CheckpointSpec] = {
    1: CheckpointSpec(
        1,
        "项目定位：跟完一笔退款",
        "从遥控器单查业务对象、事实来源与自动化边界。仓库提供十站完成后的离线参考程序；检查卡用于学习和验收，不会逐站开放功能。",
        (
            "docs/artifacts/01-field-walkthrough.md",
            "docs/artifacts/01-ontology-positioning-card.md",
            "docs/artifacts/01-six-question-diagnostic.md",
        ),
        ("python3 run.py inspect YF-R-0311",),
        (
            "能找到七条对象记录和一次 ERP 查无记录的观测；发票状态保留为 unknown，由财务补充确认，不能自动批准。",
        ),
    ),
    2: CheckpointSpec(
        2,
        "原有方案审计",
        "给人提建议的助手开始执行业务动作后，原有接口日志、共享账号和发布流程还缺哪些控制？",
        ("docs/artifacts/02-historical-audit.md",),
        ("python3 run.py summary",),
        (
            "HM-01 至 HM-04 分别对应后续的模式分离、动作记录、独立身份和版本治理，并能找到相应验收。",
        ),
    ),
    3: CheckpointSpec(
        3,
        "IART 身份登记",
        "登记退款助手以谁的名义行动、由谁负责、与谁协作，以及权限何时扩大或收回。",
        (
            "config/identity/refund_agent.yaml",
            "docs/artifacts/03-identity-acceptance.md",
        ),
        ("python3 run.py identity",),
        (
            "技术身份为 agent.cs.refund.001，representation 为 as_itself；负责人、能力、关系与生命周期约定齐全。",
        ),
    ),
    4: CheckpointSpec(
        4,
        "最小本体 v0.1",
        "将各来源记录关联到同一笔退款，保留编号、字段来源、对象关系和允许的状态转换。",
        (
            "docs/artifacts/04-minimum-ontology.md",
            "config/ontology/objects.yaml",
            "config/ontology/relationships.yaml",
            "config/ontology/state_machines.yaml",
            "config/ontology/source_map.yaml",
        ),
        ("python3 run.py graph --refund-id YF-R-0311",),
        (
            "对象图的连线不指向缺失节点；RefundRequest 状态机包含 approved 到 approval_pending_payment 的补偿转换。",
        ),
    ),
    5: CheckpointSpec(
        5,
        "动作契约与执行器",
        "比较 500 元与 500.01 元的申请，将接口调用限定为有前提、效果、审批门槛、重试和失败处理的业务动作。",
        (
            "docs/artifacts/05-action-contract.md",
            "config/actions/approve_refund_small.yaml",
            "config/actions/request_human_refund_approval.yaml",
            "config/actions/request_missing_evidence.yaml",
            "src/ontology_fde/engine.py",
        ),
        (
            "python3 run.py run YF-R-0500 --mode write",
            "python3 run.py run YF-R-0501 --mode write",
        ),
        (
            "其他条件通过时，500 元可批准并创建模拟付款指令；500.01 元转人工，不创建付款指令。批准不等于到账。",
            "Read 和 Draft 不改变业务状态；Write 在内部完成事实读取和条件检查，无需先运行两个命令解锁。",
            "写入路径中的执行、拒绝与转人工结果均有 DecisionRecord，能核对前后状态和实际效果。",
        ),
    ),
    6: CheckpointSpec(
        6,
        "规则来源与草稿",
        "对照正式政策与老陈的经验，检查候选规则的来源、范围和发布条件。本例使用固定语料与确定性提取逻辑，不调用模型，也不自动发布新规则。",
        (
            "docs/artifacts/06-rule-assets.md",
            "config/rules/refund_rules.yaml",
            "config/rules/drafts/opened_consumable_rule_draft.json",
            "config/evals/document_rule_cases.json",
        ),
        (
            "python3 run.py extract-rule "
            "--output artifacts/ch06-rule-draft.json",
            "python3 run.py run YF-R-0602 --mode draft",
        ),
        (
            "四类校验与五类样例通过，草稿仍因输入未补齐、人工审核未完成、尚未编译而不能执行。已有 R4 的建议命中可另行观察。",
        ),
    ),
    7: CheckpointSpec(
        7,
        "身份与六维权限验收",
        "检查数据、工具、动作、条件、时间和环境的授权约定。本地已实现主体和业务动作等检查；字段权限、真实凭据与环境准入仍需企业系统集成。",
        (
            "docs/artifacts/07-identity-and-permissions.md",
            "config/identity/refund_agent.yaml",
            "config/policies/permissions.yaml",
        ),
        (
            "python3 run.py run YF-R-0500 --mode write --actor agent.marketing.unknown",
            "python3 tools/verify.py",
        ),
        (
            "未知主体触发 G-ACTOR，退款状态和付款对象均不改变；权限文件声明生产写入关闭，但不能把全部声明当成已完成的认证授权设施。",
        ),
    ),
    8: CheckpointSpec(
        8,
        "任务信封与冲突裁决",
        "围绕同一笔退款保留退款助手与风控的不同意见，检查委托范围、主体、期限和裁决结果。本例的角色协作用确定性程序呈现。",
        (
            "docs/artifacts/08-multi-agent-coordination.md",
            "docs/artifacts/08-task-envelope-YF-R-0610.json",
            "config/identity/agent_registry.yaml",
            "config/policies/conflict_resolution.yaml",
        ),
        (
            "python3 run.py run YF-R-0610 --mode write "
            "--audit artifacts/ch08-decision-records.jsonl",
        ),
        (
            "ENV-T-0610 可追踪；RiskAgent:review 覆盖 RefundAgent:approve，两项意见均保留。退款进入 pending_human，创建人工审批材料，不创建付款指令。",
        ),
    ),
    9: CheckpointSpec(
        9,
        "决策记录与事故回放",
        "核对每次判断读了什么、依据何种权限、调用了哪些动作、实际改变了什么，再将发现的问题加入回归样例。",
        (
            "docs/artifacts/09-evaluation-audit-and-incident-replay.md",
            "config/evals/golden_set_v1.json",
            "config/evals/incident_replays.json",
            "src/ontology_fde/audit.py",
        ),
        (
            "python3 run.py evaluate --output artifacts/ch09-eval.json",
            "python3 run.py run YF-R-0800 --mode write "
            "--simulate-payment-failure --audit artifacts/ch09-failure.jsonl",
        ),
        (
            "36 个核心策略样例与 2 个事故回放通过；付款指令创建失败后进入补偿状态，记录失败与补偿调用。策略回放不替代执行器的端到端测试。",
        ),
    ),
    10: CheckpointSpec(
        10,
        "运行交接、场景复制与退出",
        "由接管团队核对运行资料、人工接手方式和退出安排。exit-drill 检查静态配置与交接材料，不执行真实凭据撤销、工单迁移或业务连续性交易。",
        (
            "docs/artifacts/10-operations-handoff-and-replication.md",
            "docs/fde-playbook.md",
            "AGENTS.md",
            "Makefile",
            "src/ontology_fde/exit_drill.py",
        ),
        (
            "python3 tools/verify.py",
            "python3 run.py demo --output artifacts/demo",
            "python3 run.py evaluate",
            "python3 run.py exit-drill",
        ),
        (
            "能区分可复用结构与新场景待建内容；退出检查覆盖关闭写入、撤销凭据、交还未完成工作、保留证据与连续性安排。五步 PASS 只说明本地检查通过，现场还需执行回执。",
        ),
    ),
}


def checkpoint_payload(number: int, *, check: bool = False) -> dict[str, Any]:
    if number not in CHECKPOINTS:
        raise ValueError(f"Checkpoint must be between 1 and 10, got {number}")
    payload = asdict(CHECKPOINTS[number])
    if check:
        items = _check_required_paths(CHECKPOINTS[number].artifacts)
        items.extend(_check_semantics(number))
        payload["check"] = {
            "passed": all(item["passed"] for item in items),
            "items": items,
        }
    return payload


def _check_required_paths(paths: tuple[str, ...]) -> list[dict[str, Any]]:
    root = project_root()
    return [
        {
            "name": "required_path_exists",
            "target": path,
            "passed": (root / path).exists(),
        }
        for path in paths
    ]


def _item(name: str, passed: bool, actual: Any) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "actual": actual}


def _check_semantics(number: int) -> list[dict[str, Any]]:
    try:
        if number == 1:
            source_map = load_structured("config/ontology/source_map.yaml")
            case = EnterpriseRepository().get_case("YF-R-0311")
            erp_observations = [
                ref for ref in case.source_refs if ref["system"] == "ERP"
            ]
            return [
                _item(
                    "source_map_declared",
                    bool(source_map),
                    source_map.get("schema_version"),
                ),
                _item(
                    "erp_negative_observation_preserved",
                    len(erp_observations) == 1
                    and erp_observations[0].get("observation") == "not_found",
                    erp_observations,
                ),
                _item(
                    "erp_no_result_remains_unknown",
                    case.invoice_status == "unknown",
                    case.invoice_status,
                ),
            ]
        if number == 2:
            text = (
                project_root() / "docs/artifacts/02-historical-audit.md"
            ).read_text(encoding="utf-8")
            risk_ids = [f"HM-0{index}" for index in range(1, 5)]
            return [
                _item(
                    "four_historical_risks_mapped",
                    all(value in text for value in risk_ids),
                    risk_ids,
                )
            ]
        if number == 3:
            identity = load_structured("config/identity/refund_agent.yaml")
            keys = {"identity", "agency", "relationship", "temporality"}
            temporality = identity["temporality"]
            promotion_gate = temporality.get("promotion_gate", {})
            required_gates = {
                "golden_replay == 36/36",
                "incident_replay == 2/2",
                "decision_record_coverage == 100%",
                "permission_denied_test == pass",
                "business_owner_approval == true",
            }
            required_rollbacks = {
                "guardrail_breach",
                "unexplained_write",
                "evidence_lineage_missing",
            }
            required_sources = {
                "CRM",
                "COMMERCE",
                "AFTER_SALES",
                "ERP",
                "SUPPORT",
                "RISK",
                "EVIDENCE",
                "PAYMENTS",
            }
            required_writes = {
                "HumanApprovalPacket:create",
                "EvidenceRequestDraft:create",
                "FinanceManualTask:create",
                "DecisionRecord:create",
            }
            return [
                _item("iart_complete", keys.issubset(identity), sorted(identity)),
                _item(
                    "acts_as_itself",
                    identity["identity"]["representation"] == "as_itself",
                    identity["identity"]["representation"],
                ),
                _item(
                    "promotion_gate_declared",
                    promotion_gate.get("from") == "L3-human-decision"
                    and promotion_gate.get("to") == "L4-conditional-auto"
                    and required_gates.issubset(set(promotion_gate.get("requires", []))),
                    promotion_gate,
                ),
                _item(
                    "rollback_conditions_declared",
                    required_rollbacks.issubset(
                        set(temporality.get("rollback_on", []))
                    ),
                    temporality.get("rollback_on", []),
                ),
                _item(
                    "eight_data_sources_declared",
                    required_sources.issubset(
                        set(identity["relationship"]["data_sources"])
                    ),
                    identity["relationship"]["data_sources"],
                ),
                _item(
                    "runtime_side_effects_declared",
                    required_writes.issubset(set(identity["agency"]["write"])),
                    identity["agency"]["write"],
                ),
            ]
        if number == 4:
            objects = load_structured("config/ontology/objects.yaml")
            states = load_structured("config/ontology/state_machines.yaml")
            object_names = [
                row["name"]
                for group in ("core_objects", "supporting_objects")
                for row in objects[group]
            ]
            refund_states = states["state_machines"]["RefundRequest"]["transitions"]
            return [
                _item(
                    "refund_request_declared",
                    "RefundRequest" in object_names,
                    object_names,
                ),
                _item(
                    "compensation_state_declared",
                    ["approved", "approval_pending_payment"] in refund_states,
                    refund_states,
                ),
            ]
        if number == 5:
            action = load_structured("config/actions/approve_refund_small.yaml")
            missing_evidence = load_structured(
                "config/actions/request_missing_evidence.yaml"
            )
            artifact_text = (
                project_root() / "docs/artifacts/05-action-contract.md"
            ).read_text(encoding="utf-8")
            success_rows = [
                line
                for line in artifact_text.splitlines()
                if "`approve_refund_small`" in line and "`approved`" in line
            ]
            return [
                _item(
                    "approval_threshold_is_500",
                    action["approval"]["threshold_cny"] == 500,
                    action["approval"]["threshold_cny"],
                ),
                _item(
                    "idempotency_declared",
                    bool(action.get("idempotency")),
                    action.get("idempotency"),
                ),
                _item(
                    "compensation_declared",
                    bool(action.get("compensation")),
                    action.get("compensation"),
                ),
                _item(
                    "third_contract_is_missing_evidence",
                    missing_evidence["action_id"] == "request_missing_evidence",
                    missing_evidence["action_id"],
                ),
                _item(
                    "success_state_is_approved",
                    bool(success_rows),
                    "approved" if success_rows else "missing",
                ),
            ]
        if number == 6:
            rules = load_structured("config/rules/refund_rules.yaml")
            draft = load_structured(
                "config/rules/drafts/opened_consumable_rule_draft.json"
            )
            cases = load_structured("config/evals/document_rule_cases.json")
            case_kinds = sorted({case["kind"] for case in cases["cases"]})
            return [
                _item(
                    "five_explicit_rules",
                    len(rules["rules"]) == 5,
                    len(rules["rules"]),
                ),
                _item(
                    "rule_is_still_draft",
                    draft["lifecycle"]["state"] == "draft",
                    draft["lifecycle"]["state"],
                ),
                _item(
                    "known_gap_declared",
                    bool(draft["missing_inputs"]),
                    draft["missing_inputs"],
                ),
                _item("five_rule_case_kinds", len(case_kinds) == 5, case_kinds),
            ]
        if number == 7:
            permissions = load_structured("config/policies/permissions.yaml")
            dimensions = set(permissions["dimensions"])
            expected = {
                "data",
                "tools",
                "actions",
                "conditions",
                "time",
                "environment",
            }
            return [
                _item(
                    "six_permission_dimensions",
                    dimensions == expected,
                    sorted(dimensions),
                ),
                _item(
                    "production_write_disabled",
                    permissions["dimensions"]["environment"]["production_write"]
                    is False,
                    permissions["dimensions"]["environment"],
                ),
            ]
        if number == 8:
            registry = load_structured("config/identity/agent_registry.yaml")
            policy = load_structured("config/policies/conflict_resolution.yaml")
            envelope = load_structured(
                "docs/artifacts/08-task-envelope-YF-R-0610.json"
            )
            refund_agent = next(
                row
                for row in registry["agents"]
                if row["agent_id"] == "agent.cs.refund.001"
            )
            required_side_effects = {
                "RefundRequest",
                "PaymentInstruction",
                "HumanApprovalPacket",
                "EvidenceRequestDraft",
                "FinanceManualTask",
                "DecisionRecord",
            }
            return [
                _item(
                    "three_agents_registered",
                    len(registry["agents"]) == 3,
                    len(registry["agents"]),
                ),
                _item(
                    "conflict_policy_bound",
                    policy["policy_id"] == "POL-AGENT-CONFLICT-001",
                    policy["policy_id"],
                ),
                _item(
                    "sample_envelope_scoped",
                    envelope["envelope_id"] == "ENV-T-0610"
                    and envelope["recipient"] == "agent.cs.refund.001",
                    {
                        "envelope_id": envelope["envelope_id"],
                        "recipient": envelope["recipient"],
                    },
                ),
                _item(
                    "registry_lists_runtime_side_effects",
                    required_side_effects.issubset(set(refund_agent["writes"])),
                    refund_agent["writes"],
                ),
            ]
        if number == 9:
            golden = load_structured("config/evals/golden_set_v1.json")
            incidents = load_structured("config/evals/incident_replays.json")
            return [
                _item(
                    "golden_set_has_36_cases",
                    len(golden["cases"]) == 36,
                    len(golden["cases"]),
                ),
                _item(
                    "incident_set_has_2_cases",
                    len(incidents["cases"]) == 2,
                    len(incidents["cases"]),
                ),
            ]
        if number == 10:
            text = (
                project_root()
                / "docs/artifacts/10-operations-handoff-and-replication.md"
            ).read_text(encoding="utf-8")
            required = [
                "Close `Write`",
                "Revoke credentials",
                "Return unfinished work to people",
                "Preserve audit evidence",
            ]
            drill = exit_drill_payload()
            return [
                _item(
                    "exit_drill_has_four_controls",
                    all(token in text for token in required),
                    required,
                ),
                _item(
                    "executable_exit_drill_passes",
                    drill["status"] == "PASS" and len(drill["steps"]) == 5,
                    drill,
                ),
            ]
    except (KeyError, OSError, TypeError, ValueError) as error:
        return [
            _item(
                "semantic_check_loads",
                False,
                f"{type(error).__name__}: {error}",
            )
        ]
    return []
