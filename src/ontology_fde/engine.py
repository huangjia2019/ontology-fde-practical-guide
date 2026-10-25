from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from .audit import AuditStore, DecisionRecord, TaskEnvelope, ToolCall
from .models import CaseFacts, DecisionDraft, parse_time
from .policy import RefundPolicy
from .repository import EnterpriseRepository, OntologyError

RunMode = Literal["read", "draft", "write"]


class _TraceBuilder:
    """Build a reproducible UAT trace from tool name, target, and execution order."""

    _BASE_LATENCY_MS = {
        "crm.read_customer": 14,
        "commerce.read_order": 19,
        "commerce.read_order_item": 16,
        "after_sales.read_refund_request": 13,
        "erp.read_invoice": 21,
        "support.read_ticket": 17,
        "risk.read_signal": 20,
        "evidence.read_attachment": 15,
        "evidence.verify_refund_evidence": 11,
        "policy.evaluate_refund": 9,
        "policy.resolve_agent_conflict": 7,
        "ontology.transition_refund_request": 12,
        "payments.create_refund_instruction": 24,
        "workflow.create_human_approval_packet": 18,
        "evidence.create_request_draft": 13,
        "operations.create_finance_manual_task": 17,
        "action.validate_task_envelope": 5,
        "action.enforce_write_guard": 6,
    }

    def __init__(self, trace_id: str) -> None:
        self.trace_id = trace_id
        self._calls: list[ToolCall] = []

    def add(
        self,
        phase: str,
        tool_name: str,
        display_name: str,
        target: str,
        status: str,
        result: str,
    ) -> ToolCall:
        sequence = len(self._calls) + 1
        raw = f"{self.trace_id}|{sequence}|{tool_name}|{target}".encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest().upper()
        base = self._BASE_LATENCY_MS.get(tool_name, 10)
        duration_ms = base + int(digest[:2], 16) % 5
        call = ToolCall(
            call_id=f"CALL-{sequence:02d}-{digest[2:10]}",
            sequence=sequence,
            phase=phase,
            tool_name=tool_name,
            display_name=display_name,
            target=target,
            status=status,
            duration_ms=duration_ms,
            result=result,
        )
        self._calls.append(call)
        return call

    @property
    def calls(self) -> list[ToolCall]:
        return list(self._calls)

    def payloads(self) -> list[dict[str, Any]]:
        return [call.to_dict() for call in self._calls]


class RefundEngine:
    def __init__(
        self,
        repository: EnterpriseRepository | None = None,
        audit_path: Path | None = None,
    ) -> None:
        self.repository = repository or EnterpriseRepository()
        self.policy = RefundPolicy()
        self.audit = AuditStore(audit_path)
        self._idempotency: dict[str, dict[str, Any]] = {}
        self._intent_records: dict[str, dict[str, Any]] = {}

    def reset(self) -> None:
        self.repository.reset()
        self.audit.clear()
        self._idempotency.clear()
        self._intent_records.clear()

    def run(
        self,
        refund_id: str,
        mode: RunMode = "write",
        *,
        actor: str = "agent.cs.refund.001",
        intent_id: str | None = None,
        simulate_payment_failure: bool = False,
        processing_at: datetime | str | None = None,
    ) -> dict[str, Any]:
        if mode not in {"read", "draft", "write"}:
            raise ValueError(f"Unsupported mode: {mode}")
        facts = self.repository.get_case(refund_id)
        event_time = self._processing_time(facts, processing_at)
        task_envelope = self._task_envelope(facts, actor, event_time)
        trace_id = self._trace_id(
            refund_id,
            mode,
            actor,
            intent_id or refund_id,
            simulate_payment_failure,
            event_time,
        )
        trace = _TraceBuilder(trace_id)
        self._record_source_reads(trace, facts)
        stages = [
            {
                "name": "Read",
                "status": "complete",
                "detail": f"Read {len(facts.source_refs)} source references",
            },
            {"name": "Draft", "status": "pending", "detail": "No action candidate yet"},
            {"name": "Write", "status": "pending", "detail": "Business state unchanged"},
        ]
        response: dict[str, Any] = {
            "refund_id": refund_id,
            "mode": mode,
            "facts": facts.to_dict(),
            "stages": stages,
            "draft": None,
            "decision_record": None,
            "trace_id": trace_id,
            "processing_at": event_time.isoformat(timespec="seconds"),
            "tool_calls": trace.payloads(),
        }
        if mode == "read":
            return response

        trace.add(
            "draft",
            "action.validate_task_envelope",
            "Validate task envelope",
            f"TaskEnvelope#{task_envelope.envelope_id}",
            "succeeded" if task_envelope.status == "accepted" else "blocked",
            (
                f"status={task_envelope.status}; processing_at="
                f"{event_time.isoformat(timespec='seconds')}; expires_at={task_envelope.expires_at}"
            ),
        )

        if mode == "write" and task_envelope.status == "expired":
            return self._blocked_expired_envelope(
                response,
                facts,
                actor,
                intent_id or refund_id,
                trace,
                task_envelope,
                event_time,
            )

        intent_lookup = f"{refund_id}:{actor}:{intent_id or refund_id}"
        if (
            mode == "write"
            and task_envelope.status == "accepted"
            and intent_lookup in self._intent_records
        ):
            replay = dict(self._intent_records[intent_lookup])
            replay["metadata"] = {**replay.get("metadata", {}), "idempotent_replay": True}
            response["decision_record"] = replay
            response["trace_id"] = replay["trace_id"]
            response["tool_calls"] = replay["tool_calls"]
            response["stages"] = [
                {"name": "Read", "status": "complete", "detail": "Idempotent replay"},
                {"name": "Draft", "status": "complete", "detail": "Reused original decision"},
                {"name": "Write", "status": "complete", "detail": "No duplicate write"},
            ]
            return response

        trace.add(
            "draft",
            "evidence.verify_refund_evidence",
            "Verify refund evidence",
            f"RefundRequest#{refund_id}",
            "succeeded" if facts.evidence_status == "accepted" else "needs_input",
            f"evidence_status={facts.evidence_status}; refs={len(facts.evidence_refs)}",
        )
        draft = self.policy.evaluate(facts, actor=actor)
        draft.checks["task_envelope_not_expired"] = task_envelope.status != "expired"
        trace.add(
            "draft",
            "policy.evaluate_refund",
            "Evaluate refund policy",
            f"RefundRequest#{refund_id}",
            "succeeded",
            f"decision={draft.decision}; rules={','.join(draft.rule_hits) or 'none'}",
        )
        if draft.conflict_resolution:
            trace.add(
                "draft",
                "policy.resolve_agent_conflict",
                "Resolve agent proposals",
                f"RefundRequest#{refund_id}",
                "succeeded",
                f"winner={draft.conflict_resolution['winner']}",
            )
        stages[1] = {
            "name": "Draft",
            "status": "complete",
            "detail": f"Candidate decision: {draft.decision}",
        }
        response["draft"] = draft.to_dict()
        response["tool_calls"] = trace.payloads()
        if mode == "draft":
            record = self._record(
                facts,
                draft,
                actor,
                mode,
                state_after=facts.refund_status,
                outcome="drafted",
                actual_effect="Generated a recommendation only; no business object changed",
                idempotency_key=self._idempotency_key(
                    refund_id, draft.final_action or "no_action", intent_id or refund_id
                ),
                trace_id=trace_id,
                tool_calls=trace.calls,
                task_envelope=task_envelope,
                event_time=event_time,
            )
            response["decision_record"] = self.audit.append(record)
            return response

        # BOOK-CH5-START
        action = draft.final_action or "no_action"
        key = self._idempotency_key(refund_id, action, intent_id or refund_id)
        # Keep the business idempotency key in the record, but do not return one
        # actor's decision as the authorization result for a different actor.
        actor_key = f"{actor}:{key}"
        if actor_key in self._idempotency:
            replay = dict(self._idempotency[actor_key])
            replay["metadata"] = {**replay.get("metadata", {}), "idempotent_replay": True}
            response["decision_record"] = replay
            response["trace_id"] = replay["trace_id"]
            response["tool_calls"] = replay["tool_calls"]
            stages[2] = {
                "name": "Write",
                "status": "complete",
                "detail": "Idempotency match: returned the original decision",
            }
            return response

        state_before = facts.refund_status
        state_after = state_before
        outcome = draft.decision
        actual_effect = "No business write"

        if draft.decision == "auto_approve":
            previous_state, state_after = self.repository.transition(
                "RefundRequest", refund_id, "approved"
            )
            trace.add(
                "write",
                "ontology.transition_refund_request",
                "Update refund state",
                f"RefundRequest#{refund_id}",
                "succeeded",
                f"{previous_state} -> {state_after}",
            )
            instruction = self.repository.create_payment_instruction(
                refund_id,
                facts.amount,
                fail=simulate_payment_failure,
                occurred_at=event_time,
            )
            trace.add(
                "write",
                "payments.create_refund_instruction",
                "Create refund instruction",
                f"PaymentInstruction#{instruction['canonical_id']}",
                "failed" if simulate_payment_failure else "succeeded",
                f"status={instruction['status']}; amount={facts.amount}",
            )
            if simulate_payment_failure:
                compensation_from, state_after = self.repository.transition(
                    "RefundRequest", refund_id, "approval_pending_payment"
                )
                trace.add(
                    "compensate",
                    "ontology.transition_refund_request",
                    "Enter payment compensation state",
                    f"RefundRequest#{refund_id}",
                    "succeeded",
                    f"{compensation_from} -> {state_after}",
                )
                finance_task = self.repository.create_finance_manual_task(
                    refund_id,
                    instruction["canonical_id"],
                    occurred_at=event_time,
                )
                trace.add(
                    "compensate",
                    "operations.create_finance_manual_task",
                    "Create finance manual task",
                    f"FinanceManualTask#{finance_task['canonical_id']}",
                    "succeeded",
                    f"status={finance_task['status']}",
                )
                outcome = "compensated"
                actual_effect = (
                    f"Failed to create {instruction['canonical_id']}; entered "
                    f"approval_pending_payment and created finance manual task "
                    f"{finance_task['canonical_id']}"
                )
            else:
                outcome = "auto_approved"
                actual_effect = (
                    f"RefundRequest -> approved; created mock instruction "
                    f"{instruction['canonical_id']}; a production integration would "
                    "hand it to the ERP refund workflow"
                )
        elif draft.decision == "queue_human":
            if state_before == "pending_review":
                previous_state, state_after = self.repository.transition(
                    "RefundRequest", refund_id, "pending_human"
                )
                trace.add(
                    "write",
                    "ontology.transition_refund_request",
                    "Update refund state",
                    f"RefundRequest#{refund_id}",
                    "succeeded",
                    f"{previous_state} -> {state_after}",
                )
            packet = self.repository.create_human_approval_packet(
                refund_id,
                facts.amount,
                "; ".join(draft.reasons),
                occurred_at=event_time,
            )
            trace.add(
                "write",
                "workflow.create_human_approval_packet",
                "Create human approval packet",
                f"HumanApprovalPacket#{packet['canonical_id']}",
                "succeeded",
                f"status={packet['status']}; amount={facts.amount}",
            )
            outcome = "queued_for_human"
            actual_effect = (
                f"Created human approval packet {packet['canonical_id']}; "
                "the refund was not approved automatically"
            )
        elif draft.decision == "request_evidence":
            request_draft = self.repository.create_evidence_request_draft(
                refund_id,
                facts.evidence_status,
                occurred_at=event_time,
            )
            trace.add(
                "write",
                "evidence.create_request_draft",
                "Draft evidence request",
                f"EvidenceRequestDraft#{request_draft['canonical_id']}",
                "succeeded",
                f"status={request_draft['status']}; refund_state_unchanged",
            )
            outcome = "evidence_requested"
            actual_effect = (
                f"Created evidence request draft {request_draft['canonical_id']}; "
                "the refund state did not change"
            )
        else:
            trace.add(
                "write",
                "action.enforce_write_guard",
                "Enforce write guard",
                f"RefundRequest#{refund_id}",
                "blocked",
                f"decision={draft.decision}; no_business_write",
            )

        record = self._record(
            facts,
            draft,
            actor,
            mode,
            state_after=state_after,
            outcome=outcome,
            actual_effect=actual_effect,
            idempotency_key=key,
            trace_id=trace_id,
            tool_calls=trace.calls,
            task_envelope=task_envelope,
            event_time=event_time,
        )
        payload = self.audit.append(record)
        self._idempotency[actor_key] = payload
        self._intent_records[intent_lookup] = payload
        stages[2] = {
            "name": "Write",
            "status": "complete",
            "detail": f"{state_before} → {state_after}",
        }
        response["decision_record"] = payload
        response["tool_calls"] = trace.payloads()
        response["graph"] = self.repository.graph(refund_id)
        return response
        # BOOK-CH5-END

    def _blocked_expired_envelope(
        self,
        response: dict[str, Any],
        facts: CaseFacts,
        actor: str,
        intent_id: str,
        trace: _TraceBuilder,
        task_envelope: TaskEnvelope,
        event_time: datetime,
    ) -> dict[str, Any]:
        draft = DecisionDraft(
            decision="task_expired",
            candidate_action=None,
            final_action=None,
            reasons=[
                f"The task envelope expired at {task_envelope.expires_at}; this Write "
                "requires a new delegation"
            ],
            rule_hits=["G-ENVELOPE-EXPIRED"],
            checks={
                "actor_allowed": actor in self.policy.runtime_allowed_actors,
                "task_envelope_not_expired": False,
            },
            approval_required=False,
            autonomy_level="L2-read-draft",
        )
        trace.add(
            "write",
            "action.enforce_write_guard",
            "Enforce write guard",
            f"RefundRequest#{facts.refund_id}",
            "blocked",
            "task_envelope_expired; no_business_write",
        )
        record = self._record(
            facts,
            draft,
            actor,
            "write",
            state_after=facts.refund_status,
            outcome="task_expired",
            actual_effect=(
                "The task envelope expired; the refund state and every side-effect "
                "object remained unchanged"
            ),
            idempotency_key=self._idempotency_key(
                facts.refund_id, "no_action", intent_id
            ),
            trace_id=trace.trace_id,
            tool_calls=trace.calls,
            task_envelope=task_envelope,
            event_time=event_time,
        )
        payload = self.audit.append(record)
        response["draft"] = draft.to_dict()
        response["decision_record"] = payload
        response["tool_calls"] = trace.payloads()
        response["stages"] = [
            {"name": "Read", "status": "complete", "detail": "Source reads complete"},
            {"name": "Draft", "status": "blocked", "detail": "Task envelope expired"},
            {"name": "Write", "status": "blocked", "detail": "Business state unchanged"},
        ]
        response["graph"] = self.repository.graph(facts.refund_id)
        return response

    @staticmethod
    def _processing_time(
        facts: CaseFacts,
        value: datetime | str | None,
    ) -> datetime:
        if isinstance(value, str):
            value = parse_time(value)
        event_time = value or facts.opened_at
        if event_time.tzinfo is None or event_time.utcoffset() is None:
            raise ValueError("processing_at must include an explicit UTC offset")
        return event_time

    @staticmethod
    def _idempotency_key(refund_id: str, action: str, intent_id: str) -> str:
        raw = f"{refund_id}:{action}:{intent_id}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:24]

    @staticmethod
    def _trace_id(
        refund_id: str,
        mode: str,
        actor: str,
        intent_id: str,
        simulate_payment_failure: bool,
        event_time: datetime,
    ) -> str:
        raw = (
            f"{refund_id}|{mode}|{actor}|{intent_id}|payment_failure="
            f"{str(simulate_payment_failure).lower()}|processing_at="
            f"{event_time.isoformat(timespec='seconds')}"
        ).encode("utf-8")
        return f"TRC-{hashlib.sha256(raw).hexdigest()[:16].upper()}"

    @staticmethod
    def _record_source_reads(trace: _TraceBuilder, facts: CaseFacts) -> None:
        tools = {
            ("CRM", "Customer"): ("crm.read_customer", "Read customer master data"),
            ("COMMERCE", "Order"): ("commerce.read_order", "Read order"),
            ("COMMERCE", "OrderItem"): ("commerce.read_order_item", "Read order item"),
            ("AFTER_SALES", "RefundRequest"): (
                "after_sales.read_refund_request",
                "Read refund request",
            ),
            ("ERP", "Invoice"): ("erp.read_invoice", "Read invoice status"),
            ("ERP", "InvoiceStatusConfirmation"): (
                "erp.read_invoice",
                "Read invoice status",
            ),
            ("SUPPORT", "Ticket"): ("support.read_ticket", "Read support ticket"),
            ("RISK", "RiskSignal"): ("risk.read_signal", "Read risk signal"),
            ("EVIDENCE", "Evidence"): ("evidence.read_attachment", "Read refund evidence"),
        }
        for ref in facts.source_refs:
            tool_name, display_name = tools.get(
                (ref["system"], ref["object_type"]),
                (f"{ref['system'].lower()}.read_record", "Read source-system record"),
            )
            observation = ref.get("observation", "found")
            if observation == "not_found":
                result = (
                    f"{ref['object_type']} query {ref.get('query', '')}; "
                    f"observation=not_found; snapshot={ref['source_id']}"
                )
            else:
                result = f"{ref['object_type']}#{ref['canonical_id']}"
            trace.add(
                "read",
                tool_name,
                display_name,
                f"{ref['system']}#{ref['source_id']}",
                "succeeded",
                result,
            )

    def _record(
        self,
        facts: CaseFacts,
        draft: DecisionDraft,
        actor: str,
        mode: str,
        *,
        state_after: str,
        outcome: str,
        actual_effect: str,
        idempotency_key: str,
        trace_id: str,
        tool_calls: list[ToolCall],
        task_envelope: TaskEnvelope,
        event_time: datetime,
    ) -> DecisionRecord:
        approval = {
            "required": draft.approval_required,
            "threshold_cny": self.policy.threshold_cny,
            "status": "pending" if draft.approval_required else "not_required",
        }
        authority = {
            "source": "config/policies/permissions.yaml",
            "actor_allowed": draft.checks.get("actor_allowed", False),
            "declared_contract_actors": sorted(self.policy.allowed_actors),
            "runtime_actor_ids": sorted(self.policy.runtime_allowed_actors),
            "allowed_environments": list(self.policy.allowed_environments),
            "production_write": self.policy.production_write,
            "execution_scope": "local_deterministic_mock",
        }
        return DecisionRecord(
            decision_id=self.audit.next_id(event_time),
            trace_id=trace_id,
            timestamp=event_time.isoformat(timespec="seconds"),
            correlation_id=f"CORR-{facts.refund_id}",
            envelope_id=task_envelope.envelope_id,
            task_envelope=task_envelope,
            mode=mode,
            actor=actor,
            representation="as_itself",
            permission_policy_id=self.policy.permission_policy_id,
            authority=authority,
            agent_version="0.3.0",
            model_version="deterministic-policy-demo",
            ontology_version="objects-v0.1",
            policy_version=self.policy.version,
            contract_version=self.policy.contract_version,
            initiator=f"Ticket#{facts.ticket_id}" if facts.ticket_id else "CLI",
            target_objects=[
                f"Customer#{facts.customer_id}",
                f"Order#{facts.order_id}",
                f"OrderItem#{facts.order_item_id}",
                f"RefundRequest#{facts.refund_id}",
            ],
            source_refs=facts.source_refs,
            evidence_refs=facts.evidence_refs,
            checks=draft.checks,
            rule_hits=draft.rule_hits,
            agent_candidates=draft.agent_candidates,
            conflict_resolution=draft.conflict_resolution,
            candidate_action=draft.candidate_action,
            final_action=draft.final_action,
            autonomy_level=draft.autonomy_level,
            approval=approval,
            state_before=facts.refund_status,
            state_after=state_after,
            expected_effect=(
                "Complete the refund within 24 hours"
                if draft.decision == "auto_approve"
                else (
                    "No business write"
                    if draft.decision in {"task_expired", "permission_denied"}
                    else "Review by an authorized person"
                )
            ),
            actual_effect=actual_effect,
            outcome=outcome,
            idempotency_key=idempotency_key,
            tool_calls=tool_calls,
            metadata={"security_flags": draft.security_flags},
        )

    def _task_envelope(
        self,
        facts: CaseFacts,
        actor: str,
        processing_at: datetime,
    ) -> TaskEnvelope:
        envelope_id = f"ENV-{facts.ticket_id or facts.refund_id}"
        correlation_id = f"CORR-{facts.refund_id}"
        expires_at_value = facts.opened_at + timedelta(hours=4)
        expires_at = expires_at_value.isoformat()
        object_refs = []
        if facts.ticket_id:
            object_refs.append(f"Ticket#{facts.ticket_id}")
        object_refs.extend([
            f"Customer#{facts.customer_id}",
            f"Order#{facts.order_id}",
            f"OrderItem#{facts.order_item_id}",
            f"RefundRequest#{facts.refund_id}",
        ])
        if actor not in self.policy.runtime_allowed_actors:
            status = "rejected_actor_mismatch"
        elif processing_at >= expires_at_value:
            status = "expired"
        else:
            status = "accepted"
        return TaskEnvelope(
            envelope_id=envelope_id,
            correlation_id=correlation_id,
            sender="agent.cs.reception.001",
            recipient=self.policy.agent_id,
            task_type="assess_refund_request",
            goal="Return a disposition within the Action Contract and refund-policy boundary",
            object_refs=object_refs,
            allowed_actions=sorted(self.policy.allowed_actions),
            forbidden_actions=sorted(self.policy.denied_actions),
            context_scope=sorted(self.policy.allowed_data_objects),
            expires_at=expires_at,
            status=status,
            constraints={
                "max_auto_approve_cny": self.policy.threshold_cny,
                "risk_signal_required": True,
                "accepted_evidence_required": True,
                "raw_payment_forbidden": True,
            },
        )
