from __future__ import annotations

from pathlib import Path
from typing import Any

from .engine import RefundEngine
from .evaluator import GoldenEvaluator
from .paths import load_structured
from .rule_extraction import OntologyGuidedRuleDemo


class WorkbenchService:
    def __init__(self, audit_path: Path | None = None) -> None:
        self.engine = RefundEngine(audit_path=audit_path)
        self._evaluation: dict[str, Any] | None = None

    def summary(self) -> dict[str, Any]:
        summary = self.engine.repository.summary()
        report = self.evaluation()
        summary["golden"] = {
            "passed": report["core"]["passed"],
            "total": report["core"]["total"],
        }
        summary["document_rule"] = {
            "validations_passed": report["document_to_rule"]["validation"]["passed"],
            "rule_state": report["document_to_rule"]["draft"]["lifecycle"]["state"],
        }
        return summary

    def cases(self) -> list[dict[str, Any]]:
        return self.engine.repository.list_refunds()

    def case(self, refund_id: str) -> dict[str, Any]:
        return self.engine.repository.get_case(refund_id).to_dict()

    def graph(self, refund_id: str | None = None) -> dict[str, Any]:
        return self.engine.repository.graph(refund_id)

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.engine.run(
            payload["refund_id"],
            payload.get("mode", "write"),
            actor=payload.get("actor", "agent.cs.refund.001"),
            intent_id=payload.get("intent_id"),
            simulate_payment_failure=bool(payload.get("simulate_payment_failure", False)),
            processing_at=payload.get("processing_at"),
        )

    def identity(self) -> dict[str, Any]:
        return load_structured("config/identity/refund_agent.yaml")

    def evaluation(self) -> dict[str, Any]:
        if self._evaluation is None:
            self._evaluation = GoldenEvaluator().run()
        return self._evaluation

    def document_rule(self) -> dict[str, Any]:
        return OntologyGuidedRuleDemo().run_demo()

    def reset(self) -> dict[str, Any]:
        self.engine.reset()
        return {"ok": True, "summary": self.summary()}
