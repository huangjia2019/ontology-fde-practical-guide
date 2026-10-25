from __future__ import annotations

from decimal import Decimal
from typing import Any

from .models import CaseFacts, DecisionDraft
from .paths import load_structured


class RefundPolicy:
    def __init__(
        self,
        *,
        rule_config: dict[str, Any] | None = None,
        permissions: dict[str, Any] | None = None,
        action_contract: dict[str, Any] | None = None,
        conflict_policy: dict[str, Any] | None = None,
    ) -> None:
        """Load the reviewable policy assets that are bound to this demo adapter.

        The implementation remains deliberately narrow: it is a deterministic adapter for
        the refund scenario, not a general interpreter for every expression in the JSON-subset
        YAML files.  Values that must stay identical across the contract, DecisionRecord and
        TaskEnvelope are loaded here once and then reused by the engine.
        """

        config = rule_config or load_structured("config/rules/refund_rules.yaml")
        self.version = config["version"]
        permissions = permissions or load_structured("config/policies/permissions.yaml")
        action_contract = action_contract or load_structured(
            "config/actions/approve_refund_small.yaml"
        )
        conflict_policy = conflict_policy or load_structured(
            "config/policies/conflict_resolution.yaml"
        )

        self.contract_version = action_contract["version"]
        self.auto_approve_threshold = Decimal(
            str(action_contract["approval"]["threshold_cny"])
        )
        self.allowed_actors = frozenset(action_contract["actor"]["allowed"])
        # Human roles remain declarations for an external approval workflow.  This CLI only
        # authenticates workload identities, so a role label cannot masquerade as an actor ID.
        self.runtime_allowed_actors = frozenset(
            actor for actor in self.allowed_actors if not actor.startswith("role:")
        )

        self.permission_policy_id = permissions["policy_id"]
        self.agent_id = permissions["agent_id"]
        if self.agent_id not in self.runtime_allowed_actors:
            raise ValueError(
                f"Permission agent_id {self.agent_id!r} is not a runtime actor in the "
                "approve_refund_small Action Contract"
            )
        self.allowed_actions = set(
            permissions["dimensions"]["actions"]["allow"]
        )
        self.denied_actions = list(permissions["dimensions"]["actions"]["deny"])
        self.allowed_data_objects = list(
            permissions["dimensions"]["data"]["allow_objects"]
        )
        environment = permissions["dimensions"]["environment"]
        self.allowed_environments = tuple(environment["allow"])
        self.production_write = bool(environment["production_write"])

        self.conflict_policy_id = conflict_policy["policy_id"]
        self.conflict_rule = conflict_policy["rule"]
        self.conflict_priorities = {
            row["proposal"]: int(row["rank"])
            for row in conflict_policy["priorities"]
        }
        if len(self.conflict_priorities) != len(conflict_policy["priorities"]):
            raise ValueError("Conflict policy contains duplicate proposal priorities")

    @property
    def threshold_cny(self) -> int | float:
        """Return the configured Decimal as a stable JSON number."""

        integral = self.auto_approve_threshold.to_integral_value()
        if self.auto_approve_threshold == integral:
            return int(integral)
        return float(self.auto_approve_threshold)

    def evaluate(self, facts: CaseFacts, actor: str = "agent.cs.refund.001") -> DecisionDraft:
        draft = self._evaluate_business_rules(facts, actor)
        if draft.final_action is not None:
            action = draft.final_action
            permitted = action in self.allowed_actions and action not in self.denied_actions
            draft.checks["action_allowed"] = permitted
            if not permitted:
                return self._draft(
                    "permission_denied", action, None,
                    [f"Action {action} is not permitted by {self.permission_policy_id}"],
                    [*draft.rule_hits, "G-ACTION"], draft.checks,
                    security_flags=draft.security_flags,
                )
        return draft

    def _evaluate_business_rules(self, facts: CaseFacts, actor: str) -> DecisionDraft:
        amount_valid = facts.amount.is_finite() and facts.amount > 0
        checks = {
            "grounded_customer": bool(facts.customer_id),
            "grounded_order": bool(facts.order_id),
            "grounded_item": bool(facts.order_item_id),
            "risk_object_present": facts.risk_level is not None,
            "risk_level_known": facts.risk_level in {"clear", "review", "block"},
            "amount_valid": amount_valid,
            "actor_allowed": actor in self.runtime_allowed_actors,
            "state_pending_review": facts.refund_status == "pending_review",
            "order_fulfilled": facts.order_status in {"signed", "closed"},
            "evidence_accepted": facts.evidence_status == "accepted",
            "invoice_status_known_safe": facts.invoice_status in {"none", "reversed"},
            "amount_within_auto_limit": amount_valid and facts.amount <= self.auto_approve_threshold,
        }
        security_flags = self._security_flags(facts.request_text)

        if not all(
            checks[key]
            for key in (
                "grounded_customer",
                "grounded_order",
                "grounded_item",
                "risk_object_present",
                "risk_level_known",
                "amount_valid",
            )
        ):
            return self._draft(
                "missing_data",
                None,
                None,
                ["Required objects, a recognized risk result, and a positive finite amount are needed; do not guess"],
                ["G-DATA"], checks, security_flags=security_flags
            )

        if not checks["actor_allowed"]:
            return self._draft(
                "permission_denied", "approve_refund_small", None,
                [f"{actor} is not an actor authorized by the Action Contract"],
                ["G-ACTOR"], checks,
                security_flags=security_flags,
            )

        if facts.refund_status in {"paid_out", "rejected"}:
            return self._draft(
                "no_action", None, None, ["The refund request is already in a terminal state"],
                ["G-STATE"], checks,
                security_flags=security_flags,
            )

        if facts.evidence_status != "accepted":
            return self._draft(
                "request_evidence", "request_missing_evidence", "request_missing_evidence",
                ["The evidence did not pass verification; only an evidence request draft is allowed"],
                ["G-EVIDENCE"], checks,
                security_flags=security_flags,
            )

        if facts.refund_status != "pending_review":
            return self._draft(
                "not_ready", None, None,
                ["The refund request has not reached pending_review"],
                ["G-STATE"], checks,
                security_flags=security_flags,
            )

        rule_hits: list[str] = []
        reasons: list[str] = []
        if not checks["order_fulfilled"]:
            rule_hits.append("G-ORDER")
            reasons.append(
                "The order is neither signed for nor closed; a person must verify fulfillment"
            )

        if facts.item_category == "opened_consumable":
            if facts.hours_since_signed is None:
                return self._draft(
                    "missing_data", None, None,
                    ["The opened consumable has no verifiable delivery time"],
                    ["G-DATA"], checks, security_flags=security_flags
                )
            if facts.hours_since_signed > 24:
                rule_hits.append("R1")
                reasons.append(
                    "The opened consumable was delivered more than 24 hours ago and cannot use the automatic path"
                )

        if facts.invoice_status == "issued":
            rule_hits.append("R2")
            reasons.append(
                "An invoice has been issued; Finance must review the request before reversal"
            )
        elif facts.invoice_status not in {"none", "reversed"}:
            rule_hits.append("G-INVOICE-UNKNOWN")
            reasons.append(
                "Invoice status is unknown: a not_found query result cannot be treated as confirmed absent"
            )
        if facts.customer_tier == "blacklist":
            rule_hits.append("R3")
            reasons.append("Every refund request from a blocklisted customer requires human review")
        if facts.previous_refunds_30d >= 2:
            rule_hits.append("R4")
            reasons.append(
                "This is the customer's third or later refund request within 30 days"
            )
        channel = (facts.customer_channel or "unknown").lower()
        if channel != "b2c":
            rule_hits.append("R5")
            reasons.append(
                "For B2B customers or an unrecognized channel, check the contract terms first"
            )

        risk_conflict = None
        candidates = [
            {
                "agent_id": self.agent_id,
                "proposal": "approve",
                "basis": "The refund facts satisfy the baseline conditions",
            }
        ]
        if facts.risk_level in {"review", "block"}:
            candidates.append(
                {
                    "agent_id": "agent.cs.risk.001",
                    "proposal": facts.risk_level,
                    "basis": facts.risk_reason,
                }
            )
            risk_conflict = self._resolve_conflict(facts.risk_level)
            if risk_conflict["winner"].startswith("RiskAgent:"):
                rule_hits.append("G-RISK")
                reasons.append(
                    f"RiskAgent returned {facts.risk_level}: {facts.risk_reason}"
                )

        if facts.amount > self.auto_approve_threshold:
            rule_hits.append("G-AMOUNT")
            reasons.append(
                f"RMB {facts.amount} exceeds the RMB {self.threshold_cny} automatic-approval threshold"
            )

        if rule_hits:
            return self._draft(
                "queue_human",
                "approve_refund_small",
                "request_human_refund_approval",
                reasons,
                rule_hits,
                checks,
                approval_required=True,
                autonomy_level="L3-human-decision",
                agent_candidates=candidates,
                conflict_resolution=risk_conflict,
                security_flags=security_flags,
            )

        return self._draft(
            "auto_approve",
            "approve_refund_small",
            "approve_refund_small",
            [
                f"The amount is no more than RMB {self.threshold_cny}, and the evidence, "
                "fulfillment, invoice, risk, frequency, and channel checks all passed"
            ],
            [],
            checks,
            approval_required=False,
            autonomy_level="L4-conditional",
            agent_candidates=candidates,
            conflict_resolution=risk_conflict,
            security_flags=security_flags,
        )

    def _resolve_conflict(self, risk_level: str) -> dict[str, str]:
        proposals = ["RefundAgent:approve", f"RiskAgent:{risk_level}"]
        missing = [proposal for proposal in proposals if proposal not in self.conflict_priorities]
        if missing:
            raise ValueError(
                f"Conflict policy {self.conflict_policy_id} has no priority for {missing}"
            )
        ranked = sorted(proposals, key=lambda proposal: self.conflict_priorities[proposal])
        return {
            "policy_id": self.conflict_policy_id,
            "winner": ranked[0],
            "overruled": ranked[1],
            "reason": self.conflict_rule,
        }

    @staticmethod
    def _security_flags(text: str) -> list[str]:
        lower = text.lower()
        flags = []
        if any(
            token in lower
            for token in (
                "ignore",
                "refund it now",
                "refund directly",
                "no approval",
                "new policy threshold",
            )
        ):
            flags.append("untrusted_instruction_in_business_text")
        if any(token in lower for token in ("bank card", "identity card", "card number")):
            flags.append("sensitive_data_request")
        return flags

    @staticmethod
    def _draft(
        decision: str,
        candidate_action: str | None,
        final_action: str | None,
        reasons: list[str],
        rule_hits: list[str],
        checks: dict[str, bool],
        *,
        approval_required: bool = False,
        autonomy_level: str = "L2-read-draft",
        agent_candidates: list[dict[str, str]] | None = None,
        conflict_resolution: dict[str, str] | None = None,
        security_flags: list[str] | None = None,
    ) -> DecisionDraft:
        return DecisionDraft(
            decision=decision,
            candidate_action=candidate_action,
            final_action=final_action,
            reasons=reasons,
            rule_hits=rule_hits,
            checks=checks,
            approval_required=approval_required,
            autonomy_level=autonomy_level,
            agent_candidates=agent_candidates or [],
            conflict_resolution=conflict_resolution,
            security_flags=security_flags or [],
        )
