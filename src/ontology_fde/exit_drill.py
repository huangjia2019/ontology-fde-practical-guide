from __future__ import annotations

from typing import Any

from .paths import load_structured, project_root


def exit_drill_payload() -> dict[str, Any]:
    """Run a deterministic, non-production rehearsal of the five exit controls.

    The reference project cannot revoke an enterprise credential or move a real ERP work item.
    This drill therefore verifies that every handoff has a concrete identity, route and retained
    evidence, while reporting the simulation boundary in the payload itself.
    """

    permissions = load_structured("config/policies/permissions.yaml")
    identity = load_structured("config/identity/refund_agent.yaml")
    human_action = load_structured("config/actions/request_human_refund_approval.yaml")
    refunds = load_structured("data/mock/after_sales/refunds.json")["records"]
    drill_doc = (
        project_root() / "docs/artifacts/10-operations-handoff-and-replication.md"
    ).read_text(encoding="utf-8")

    terminal_states = {"paid_out", "rejected"}
    unfinished = [
        row["canonical_id"]
        for row in refunds
        if row["workflow_state"] not in terminal_states
    ]
    security_principal = identity["identity"]["security_principal"]
    relationship_policies = set(identity["relationship"]["policies"])

    steps = [
        _step(
            1,
            "Close Write",
            permissions["dimensions"]["environment"]["production_write"] is False,
            {
                "policy_id": permissions["policy_id"],
                "production_write": permissions["dimensions"]["environment"][
                    "production_write"
                ],
            },
        ),
        _step(
            2,
            "Revoke credentials",
            security_principal.startswith("workload://")
            and "Revoke credentials" in drill_doc,
            {
                "principal": security_principal,
                "receipt": "drill-only: credential revocation owner and target resolved",
            },
        ),
        _step(
            3,
            "Return unfinished work to people",
            human_action["action_id"] == "request_human_refund_approval"
            and "Return unfinished work to people" in drill_doc,
            {
                "unfinished_count": len(unfinished),
                "sample_ids": unfinished[:3],
                "handoff_action": human_action["action_id"],
            },
        ),
        _step(
            4,
            "Preserve audit evidence",
            "POL-AUDIT-RETENTION" in relationship_policies
            and (project_root() / "src/ontology_fde/audit.py").is_file(),
            {
                "retention_policy": "POL-AUDIT-RETENTION",
                "retained_assets": [
                    "identity_version",
                    "permission_snapshot",
                    "DecisionRecord",
                    "incident_replays",
                ],
            },
        ),
        _step(
            5,
            "Check continuity",
            "Verify business continuity" in drill_doc
            and human_action["effects"][0] == "RefundRequest.status -> pending_human",
            {
                "fallback": "request_human_refund_approval",
                "continuity_probe": "found human handoff action and state transition; no work item submitted",
            },
        ),
    ]
    passed = all(step["status"] == "PASS" for step in steps)
    return {
        "drill": "agent_exit",
        "scope": "deterministic_rehearsal_no_real_iam_or_erp_mutation",
        "status": "PASS" if passed else "FAIL",
        "steps": steps,
    }


def _step(
    sequence: int,
    action: str,
    passed: bool,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "sequence": sequence,
        "action": action,
        "status": "PASS" if passed else "FAIL",
        "evidence": evidence,
    }
