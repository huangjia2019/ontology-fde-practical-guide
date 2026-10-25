from __future__ import annotations

from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

from .models import CaseFacts
from .paths import load_structured, write_json
from .policy import RefundPolicy
from .rule_extraction import OntologyGuidedRuleDemo


class GoldenEvaluator:
    def __init__(self) -> None:
        self.suite = load_structured("config/evals/golden_set_v1.json")
        self.incidents = load_structured("config/evals/incident_replays.json")
        self.policy = RefundPolicy()

    # BOOK-CH9-EVAL-START
    def run(self, output_path: Path | None = None) -> dict[str, Any]:
        core_results = [self._run_case(case) for case in self.suite["cases"]]
        incident_results = [self._run_incident(case) for case in self.incidents["cases"]]
        category_totals = Counter(row["category"] for row in core_results)
        category_passed = Counter(row["category"] for row in core_results if row["passed"])
        document_rule = OntologyGuidedRuleDemo().run_demo()
        report = {
            "suite": self.suite["name"],
            "version": self.suite["version"],
            "scope": {
                "core_and_incident_replays": "policy_level",
                "end_to_end_execution": "tests/test_engine.py and tests/test_repository.py",
                "note": (
                    "The 36+2 replays verify the deterministic policy. Unit tests cover "
                    "state transitions, side effects, expiry, idempotency, compensation, "
                    "and audit records."
                ),
            },
            "core": {
                "total": len(core_results),
                "passed": sum(row["passed"] for row in core_results),
                "failed": sum(not row["passed"] for row in core_results),
                "pass_rate": (
                    round(sum(row["passed"] for row in core_results) / len(core_results), 4)
                    if core_results else 0.0
                ),
                "categories": {
                    category: {
                        "total": category_totals[category],
                        "passed": category_passed[category],
                    }
                    for category in category_totals
                },
                "results": core_results,
            },
            "incident_replays": {
                "total": len(incident_results),
                "passed": sum(row["passed"] for row in incident_results),
                "results": incident_results,
            },
            "document_to_rule": document_rule,
        }
        report["passed"] = evaluation_passed(report)
        if output_path:
            write_json(output_path, report)
        return report
    # BOOK-CH9-EVAL-END

    def _run_case(self, case: dict[str, Any]) -> dict[str, Any]:
        values = {**self.suite["defaults"], **case.get("given", {})}
        facts = CaseFacts.from_eval(values)
        draft = self.policy.evaluate(facts, actor=values["actor"])
        preview_audit = {
            "decision_id": f"DR-{case['case_id']}",
            "actor": values["actor"],
            "target_objects": [facts.refund_id, facts.order_id, facts.order_item_id],
            "checks": draft.checks,
            "rule_hits": draft.rule_hits,
            "policy_version": self.policy.version,
            "permission_policy_id": self.policy.permission_policy_id,
            "authority": {
                "actor_allowed": draft.checks.get("actor_allowed", False),
                "runtime_actor_ids": sorted(self.policy.runtime_allowed_actors),
            },
        }
        expected = case["expect"]
        decision_ok = draft.decision == expected["decision"]
        rule_ok = expected.get("rule_hit") is None or expected["rule_hit"] in draft.rule_hits
        audit_ok = all(field in preview_audit for field in self.suite["audit_must_have"])
        return {
            "case_id": case["case_id"],
            "category": case["category"],
            "title": case["title"],
            "expected": expected,
            "actual": {"decision": draft.decision, "rule_hits": draft.rule_hits},
            "audit_complete": audit_ok,
            "passed": decision_ok and rule_ok and audit_ok,
        }

    def _run_incident(self, case: dict[str, Any]) -> dict[str, Any]:
        values = {**self.suite["defaults"], **case["given"]}
        facts = CaseFacts.from_eval(values)
        draft = self.policy.evaluate(facts, actor=values["actor"])
        expected = case["expect"]
        passed = draft.decision == expected["decision"] and expected["rule_hit"] in draft.rule_hits
        return {
            "case_id": case["case_id"],
            "origin": case["origin"],
            "actual": {"decision": draft.decision, "rule_hits": draft.rule_hits},
            "passed": passed,
        }


def evaluation_passed(report: dict[str, Any]) -> bool:
    """Require every populated evaluation group, not just the golden-case count."""
    core = report["core"]
    incidents = report["incident_replays"]
    document = report["document_to_rule"]
    return (
        core["total"] > 0
        and core["failed"] == 0
        and core["passed"] == core["total"]
        and incidents["total"] > 0
        and incidents["passed"] == incidents["total"]
        and document["validation"]["passed"]
        and document["candidate_execution_guard"]["passed"]
    )
