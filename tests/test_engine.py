import unittest
from copy import deepcopy
from decimal import Decimal

from ontology_fde.engine import RefundEngine
from ontology_fde.paths import load_structured
from ontology_fde.policy import RefundPolicy
from ontology_fde.repository import EnterpriseRepository


class EngineTests(unittest.TestCase):
    def test_read_and_draft_do_not_mutate_business_state(self) -> None:
        engine = RefundEngine()
        read = engine.run("YF-R-0311", "read")
        self.assertTrue(read["trace_id"].startswith("TRC-"))
        self.assertTrue(all(call["phase"] == "read" for call in read["tool_calls"]))
        self.assertEqual(engine.repository.refunds["YF-R-0311"]["workflow_state"], "pending_review")
        draft = engine.run("YF-R-0311", "draft")
        self.assertEqual(draft["draft"]["decision"], "queue_human")
        self.assertIn("G-INVOICE-UNKNOWN", draft["draft"]["rule_hits"])
        self.assertEqual(draft["trace_id"], draft["decision_record"]["trace_id"])
        self.assertEqual(engine.repository.refunds["YF-R-0311"]["workflow_state"], "pending_review")

    def test_low_risk_write_auto_approves_as_itself(self) -> None:
        engine = RefundEngine()
        result = engine.run("YF-R-0500", "write")
        record = result["decision_record"]
        self.assertEqual(record["outcome"], "auto_approved")
        self.assertEqual(record["actor"], "agent.cs.refund.001")
        self.assertEqual(record["representation"], "as_itself")
        self.assertEqual(record["state_after"], "approved")
        self.assertTrue(record["trace_id"].startswith("TRC-"))
        self.assertTrue(any(call["phase"] == "write" for call in record["tool_calls"]))

    def test_trace_and_tool_calls_are_deterministic(self) -> None:
        first = RefundEngine().run("YF-R-0610", "write")["decision_record"]
        second = RefundEngine().run("YF-R-0610", "write")["decision_record"]
        self.assertEqual(first["trace_id"], second["trace_id"])
        self.assertEqual(first["tool_calls"], second["tool_calls"])
        self.assertEqual(
            [call["sequence"] for call in first["tool_calls"]],
            list(range(1, len(first["tool_calls"]) + 1)),
        )
        required = {
            "call_id", "sequence", "phase", "tool_name", "display_name",
            "target", "status", "duration_ms", "result",
        }
        self.assertTrue(all(required == set(call) for call in first["tool_calls"]))

    def test_tool_calls_cover_source_reads_evidence_and_controlled_write(self) -> None:
        record = RefundEngine().run("YF-R-0500", "write")["decision_record"]
        names = {call["tool_name"] for call in record["tool_calls"]}
        self.assertIn("crm.read_customer", names)
        self.assertIn("commerce.read_order", names)
        self.assertIn("evidence.verify_refund_evidence", names)
        self.assertIn("ontology.transition_refund_request", names)
        self.assertIn("payments.create_refund_instruction", names)
        self.assertTrue(all(call["duration_ms"] > 0 for call in record["tool_calls"]))

    def test_erp_negative_observation_is_preserved_in_trace(self) -> None:
        result = RefundEngine().run("YF-R-0311", "read")
        refs = [ref for ref in result["facts"]["source_refs"] if ref["system"] == "ERP"]
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["observation"], "not_found")
        self.assertEqual(result["facts"]["invoice_status"], "unknown")
        calls = [call for call in result["tool_calls"] if call["tool_name"] == "erp.read_invoice"]
        self.assertEqual(len(calls), 1)
        self.assertIn("observation=not_found", calls[0]["result"])

    def test_500_is_auto_and_500_01_is_human(self) -> None:
        at_limit = RefundEngine().run("YF-R-0500", "write")["decision_record"]
        above_limit = RefundEngine().run("YF-R-0501", "write")["decision_record"]
        self.assertEqual(at_limit["outcome"], "auto_approved")
        self.assertEqual(above_limit["outcome"], "queued_for_human")
        self.assertIn("G-AMOUNT", above_limit["rule_hits"])
        self.assertEqual(above_limit["state_after"], "pending_human")

    def test_repeat_refund_hits_r4(self) -> None:
        record = RefundEngine().run("YF-R-0602", "write")["decision_record"]
        self.assertIn("R4", record["rule_hits"])
        self.assertEqual(record["outcome"], "queued_for_human")

    def test_risk_agent_review_overrules_refund_agent(self) -> None:
        record = RefundEngine().run("YF-R-0610", "write")["decision_record"]
        self.assertEqual(record["conflict_resolution"]["winner"], "RiskAgent:review")
        self.assertEqual(record["conflict_resolution"]["overruled"], "RefundAgent:approve")
        self.assertEqual(record["correlation_id"], "CORR-YF-R-0610")
        self.assertTrue(record["envelope_id"].startswith("ENV-"))
        names = [call["tool_name"] for call in record["tool_calls"]]
        self.assertIn("policy.resolve_agent_conflict", names)
        self.assertIn("workflow.create_human_approval_packet", names)

    def test_task_envelope_is_audited_and_matches_reference_artifact(self) -> None:
        record = RefundEngine().run("YF-R-0610", "write")["decision_record"]
        expected = load_structured(
            "docs/artifacts/08-task-envelope-YF-R-0610.json"
        )
        self.assertEqual(record["task_envelope"], expected)
        self.assertEqual(record["envelope_id"], expected["envelope_id"])
        self.assertEqual(record["correlation_id"], expected["correlation_id"])

    def test_contract_threshold_is_shared_by_policy_record_and_envelope(self) -> None:
        threshold = load_structured("config/actions/approve_refund_small.yaml")["approval"][
            "threshold_cny"
        ]
        engine = RefundEngine()
        record = engine.run("YF-R-0500", "write")["decision_record"]
        self.assertEqual(engine.policy.threshold_cny, threshold)
        self.assertEqual(record["approval"]["threshold_cny"], threshold)
        self.assertEqual(
            record["task_envelope"]["constraints"]["max_auto_approve_cny"], threshold
        )

    def test_decision_record_names_permission_authority(self) -> None:
        record = RefundEngine().run("YF-R-0500", "write")["decision_record"]
        permissions = load_structured("config/policies/permissions.yaml")
        self.assertEqual(record["permission_policy_id"], permissions["policy_id"])
        self.assertEqual(record["authority"]["source"], "config/policies/permissions.yaml")
        self.assertTrue(record["authority"]["actor_allowed"])
        self.assertFalse(record["authority"]["production_write"])

    def test_expired_task_envelope_blocks_write_without_side_effects(self) -> None:
        engine = RefundEngine()
        state_before = engine.repository.refunds["YF-R-0610"]["workflow_state"]
        payments_before = set(engine.repository.payment_instructions)
        result = engine.run(
            "YF-R-0610",
            "write",
            processing_at="2026-07-10T23:18:00+08:00",
        )
        record = result["decision_record"]
        self.assertEqual(record["outcome"], "task_expired")
        self.assertEqual(record["task_envelope"]["status"], "expired")
        self.assertIn("G-ENVELOPE-EXPIRED", record["rule_hits"])
        self.assertEqual(record["state_before"], state_before)
        self.assertEqual(record["state_after"], state_before)
        self.assertEqual(engine.repository.refunds["YF-R-0610"]["workflow_state"], state_before)
        self.assertEqual(set(engine.repository.payment_instructions), payments_before)
        self.assertNotIn("HAP-0610", engine.repository.human_approval_packets)
        self.assertEqual(record["tool_calls"][-1]["tool_name"], "action.enforce_write_guard")
        self.assertEqual(record["tool_calls"][-1]["status"], "blocked")

    def test_decision_and_side_effect_use_injected_event_clock(self) -> None:
        engine = RefundEngine()
        event_time = "2026-07-10T20:00:00+08:00"
        record = engine.run(
            "YF-R-0500", "write", processing_at=event_time
        )["decision_record"]
        self.assertEqual(record["timestamp"], event_time)
        self.assertTrue(record["decision_id"].startswith("DR-20260710-"))
        self.assertEqual(engine.repository.payment_instructions["PI-0500"]["created_at"], event_time)

    def test_missing_evidence_only_creates_request_draft(self) -> None:
        engine = RefundEngine()
        record = engine.run("YF-R-0702", "write")["decision_record"]
        self.assertEqual(record["outcome"], "evidence_requested")
        self.assertEqual(record["state_before"], "draft")
        self.assertEqual(record["state_after"], "draft")
        self.assertIn("ERD-0702", engine.repository.evidence_request_drafts)

    def test_permission_denied(self) -> None:
        engine = RefundEngine()
        payment_ids_before = set(engine.repository.payment_instructions)
        record = engine.run(
            "YF-R-0500", "write", actor="agent.marketing.unknown"
        )["decision_record"]
        self.assertEqual(record["outcome"], "permission_denied")
        self.assertEqual(record["state_before"], "pending_review")
        self.assertEqual(record["state_after"], "pending_review")
        self.assertIn("G-ACTOR", record["rule_hits"])
        self.assertEqual(record["task_envelope"]["status"], "rejected_actor_mismatch")
        self.assertEqual(set(engine.repository.payment_instructions), payment_ids_before)
        self.assertNotIn("PI-0500", engine.repository.payment_instructions)
        self.assertEqual(record["tool_calls"][-1]["tool_name"], "action.enforce_write_guard")
        self.assertEqual(record["tool_calls"][-1]["status"], "blocked")

    def test_payment_failure_enters_explainable_compensation_state(self) -> None:
        engine = RefundEngine()
        record = engine.run(
            "YF-R-0800", "write", simulate_payment_failure=True
        )["decision_record"]
        self.assertEqual(record["outcome"], "compensated")
        self.assertEqual(record["state_after"], "approval_pending_payment")
        self.assertIn("finance manual task", record["actual_effect"])
        self.assertIn("FMT-0800", engine.repository.finance_manual_tasks)
        failed = [call for call in record["tool_calls"] if call["status"] == "failed"]
        compensated = [call for call in record["tool_calls"] if call["phase"] == "compensate"]
        self.assertEqual([call["tool_name"] for call in failed], ["payments.create_refund_instruction"])
        self.assertEqual(len(compensated), 2)

    def test_same_intent_is_idempotent_even_after_state_changed(self) -> None:
        engine = RefundEngine()
        first = engine.run("YF-R-0500", "write", intent_id="INT-001")
        second = engine.run("YF-R-0500", "write", intent_id="INT-001")
        self.assertEqual(first["decision_record"]["decision_id"], second["decision_record"]["decision_id"])
        self.assertTrue(second["decision_record"]["metadata"]["idempotent_replay"])
        self.assertEqual(len(engine.audit.records), 1)

    def test_unknown_invoice_status_stops_before_payment(self) -> None:
        engine = RefundEngine()
        result = engine.run("YF-R-0311", "write")
        record = result["decision_record"]
        self.assertEqual(result["facts"]["invoice_status"], "unknown")
        self.assertEqual(record["outcome"], "queued_for_human")
        self.assertIn("G-INVOICE-UNKNOWN", record["rule_hits"])
        self.assertEqual(record["state_after"], "pending_human")
        self.assertIn("HAP-0311", engine.repository.human_approval_packets)
        self.assertNotIn("PI-0311", engine.repository.payment_instructions)

    def test_every_write_outcome_has_a_decision_record(self) -> None:
        scenarios = [
            ("YF-R-0500", {}),
            ("YF-R-0501", {}),
            ("YF-R-0702", {}),
            ("YF-R-0500", {"actor": "agent.marketing.unknown"}),
            (
                "YF-R-0610",
                {"processing_at": "2026-07-10T23:18:00+08:00"},
            ),
            ("YF-R-0800", {"simulate_payment_failure": True}),
        ]
        for refund_id, options in scenarios:
            with self.subTest(refund_id=refund_id, options=options):
                result = RefundEngine().run(refund_id, "write", **options)
                self.assertIsNotNone(result["decision_record"])
                self.assertEqual(result["decision_record"]["mode"], "write")


class PolicyConfigBindingTests(unittest.TestCase):
    def test_modified_contract_threshold_and_actor_change_runtime_decision(self) -> None:
        action = deepcopy(load_structured("config/actions/approve_refund_small.yaml"))
        permissions = deepcopy(load_structured("config/policies/permissions.yaml"))
        action["approval"]["threshold_cny"] = 499
        action["actor"]["allowed"] = ["agent.cs.refund.alt"]
        permissions["agent_id"] = "agent.cs.refund.alt"
        policy = RefundPolicy(action_contract=action, permissions=permissions)
        facts = EnterpriseRepository().get_case("YF-R-0500")

        accepted = policy.evaluate(facts, actor="agent.cs.refund.alt")
        rejected = policy.evaluate(facts, actor="agent.cs.refund.001")
        self.assertEqual(policy.auto_approve_threshold, Decimal("499"))
        self.assertEqual(accepted.decision, "queue_human")
        self.assertIn("G-AMOUNT", accepted.rule_hits)
        self.assertEqual(rejected.decision, "permission_denied")

    def test_conflict_winner_and_policy_id_come_from_config(self) -> None:
        conflict = deepcopy(load_structured("config/policies/conflict_resolution.yaml"))
        conflict["policy_id"] = "POL-TEST-REFUND-WINS"
        for row in conflict["priorities"]:
            if row["proposal"] == "RefundAgent:approve":
                row["rank"] = 1
            elif row["proposal"] == "RiskAgent:review":
                row["rank"] = 3
        policy = RefundPolicy(conflict_policy=conflict)
        draft = policy.evaluate(
            EnterpriseRepository().get_case("YF-R-0610"),
            actor="agent.cs.refund.001",
        )
        self.assertEqual(draft.conflict_resolution["policy_id"], "POL-TEST-REFUND-WINS")
        self.assertEqual(draft.conflict_resolution["winner"], "RefundAgent:approve")
        self.assertNotIn("G-RISK", draft.rule_hits)
        self.assertEqual(draft.decision, "auto_approve")


if __name__ == "__main__":
    unittest.main()
