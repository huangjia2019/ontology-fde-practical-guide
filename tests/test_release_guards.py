"""Release regressions: unknown facts must not turn into authorization."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from ontology_fde.audit import AuditStore
from ontology_fde.cli import main
from ontology_fde.engine import RefundEngine
from ontology_fde.evaluator import GoldenEvaluator, evaluation_passed
from ontology_fde.policy import RefundPolicy
from ontology_fde.repository import EnterpriseRepository, OntologyError
from ontology_fde.rule_extraction import OntologyGuidedRuleDemo, RuleLifecycleError


class AuditPortabilityTests(unittest.TestCase):
    def test_cli_write_succeeds_without_system_or_package_timezone_data(self) -> None:
        root = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        env["PYTHONTZPATH"] = ""
        env["PYTHONUTF8"] = "1"
        env.pop("ONTOLOGY_FDE_HOME", None)
        # -S also removes site-packages, so an installed tzdata cannot hide the
        # missing-system-database failure seen on a standard Windows install.
        result = subprocess.run(
            [sys.executable, "-S", "run.py", "run", "YF-R-0500", "--mode", "write"],
            cwd=root, env=env, capture_output=True, text=True, encoding="utf-8", timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        record = json.loads(result.stdout)["decision_record"]
        self.assertEqual(record["decision_id"], "DR-20260710-0001")
        self.assertEqual(record["outcome"], "auto_approved")
        self.assertEqual(record["state_after"], "approved")

    def test_audit_date_uses_utc_plus_eight_at_day_boundary(self) -> None:
        store = AuditStore()
        event = datetime.fromisoformat("2026-07-10T18:00:00+00:00")
        self.assertEqual(store.next_id(event), "DR-20260711-0001")


class ReleaseGuardTests(unittest.TestCase):
    def test_unknown_risk_values_do_not_mean_clear(self) -> None:
        policy = RefundPolicy()
        facts = EnterpriseRepository().get_case("YF-R-0500")
        for level in (None, "", "unknown", "clearr"):
            with self.subTest(level=level):
                facts.risk_level = level
                draft = policy.evaluate(facts)
                self.assertEqual(draft.decision, "missing_data")
                self.assertIn("G-DATA", draft.rule_hits)
                self.assertIsNone(draft.final_action)

    def test_unknown_customer_channel_does_not_mean_b2c(self) -> None:
        policy = RefundPolicy()
        facts = EnterpriseRepository().get_case("YF-R-0500")
        for channel in (None, "", "unknown", "b2b", "b2x"):
            with self.subTest(channel=channel):
                facts.customer_channel = channel
                draft = policy.evaluate(facts)
                self.assertEqual(draft.decision, "queue_human")
                self.assertIn("R5", draft.rule_hits)

    def test_invalid_amount_cannot_reach_automatic_payment(self) -> None:
        policy = RefundPolicy()
        facts = EnterpriseRepository().get_case("YF-R-0500")
        for amount in ("0", "-0.01", "NaN", "Infinity", "-Infinity"):
            with self.subTest(amount=amount):
                facts.amount = Decimal(amount)
                draft = policy.evaluate(facts)
                self.assertEqual(draft.decision, "missing_data")
                self.assertFalse(draft.checks["amount_valid"])
                self.assertIsNone(draft.final_action)

    def test_action_allowlist_is_enforced_for_every_write_path(self) -> None:
        scenarios = (
            ("YF-R-0500", "approve_refund_small"),
            ("YF-R-0501", "request_human_refund_approval"),
            ("YF-R-0702", "request_missing_evidence"),
        )
        for refund_id, action in scenarios:
            with self.subTest(action=action):
                engine = RefundEngine()
                before = deepcopy(engine.repository.refunds)
                payments_before = deepcopy(engine.repository.payment_instructions)
                engine.policy.allowed_actions.remove(action)
                record = engine.run(refund_id, "write")["decision_record"]
                self.assertEqual(record["outcome"], "permission_denied")
                self.assertIn("G-ACTION", record["rule_hits"])
                self.assertFalse(record["checks"]["action_allowed"])
                self.assertIsNone(record["final_action"])
                self.assertEqual(engine.repository.refunds, before)
                self.assertEqual(engine.repository.payment_instructions, payments_before)
                self.assertFalse(engine.repository.human_approval_packets)
                self.assertFalse(engine.repository.evidence_request_drafts)
                self.assertEqual(len(engine.audit.records), 1)

    def test_explicit_deny_overrides_an_action_allow(self) -> None:
        engine = RefundEngine()
        payments_before = deepcopy(engine.repository.payment_instructions)
        engine.policy.denied_actions.append("approve_refund_small")
        record = engine.run("YF-R-0500", "write")["decision_record"]
        self.assertEqual(record["outcome"], "permission_denied")
        self.assertEqual(engine.repository.payment_instructions, payments_before)

    def test_terminal_refund_does_not_request_more_evidence(self) -> None:
        for state in ("paid_out", "rejected"):
            with self.subTest(state=state):
                engine = RefundEngine()
                engine.repository.refunds["YF-R-0500"]["workflow_state"] = state
                engine.repository.evidence.clear()
                record = engine.run("YF-R-0500", "write")["decision_record"]
                self.assertEqual(record["outcome"], "no_action")
                self.assertEqual(record["state_after"], state)
                self.assertFalse(engine.repository.evidence_request_drafts)

    def test_idempotency_does_not_return_another_actors_record(self) -> None:
        engine = RefundEngine()
        engine.repository.refunds["YF-R-0500"]["workflow_state"] = "paid_out"
        original = engine.run("YF-R-0500", "write")["decision_record"]
        denied = engine.run(
            "YF-R-0500", "write", actor="agent.marketing.unknown"
        )["decision_record"]
        self.assertEqual(original["outcome"], "no_action")
        self.assertEqual(denied["outcome"], "permission_denied")
        self.assertEqual(denied["actor"], "agent.marketing.unknown")
        self.assertNotEqual(original["decision_id"], denied["decision_id"])
        self.assertEqual(len(engine.audit.records), 2)

    def test_role_label_is_not_an_authenticated_runtime_actor(self) -> None:
        engine = RefundEngine()
        payments_before = deepcopy(engine.repository.payment_instructions)
        record = engine.run(
            "YF-R-0500", "write", actor="role:cs_supervisor"
        )["decision_record"]
        self.assertEqual(record["outcome"], "permission_denied")
        self.assertIn("G-ACTOR", record["rule_hits"])
        self.assertEqual(engine.repository.payment_instructions, payments_before)

    def test_grounding_rejects_customer_and_order_mismatch(self) -> None:
        repo = EnterpriseRepository()
        repo.refunds["YF-R-0500"]["customer_id"] = "C-8831"
        with self.assertRaisesRegex(OntologyError, "customers differ"):
            repo.get_case("YF-R-0500")

    def test_grounding_rejects_item_from_another_order(self) -> None:
        repo = EnterpriseRepository()
        repo.refunds["YF-R-0500"]["order_item_id"] = "OI-9938-1"
        with self.assertRaisesRegex(OntologyError, "does not belong"):
            repo.get_case("YF-R-0500")

    def test_retry_after_compensation_does_not_create_another_payment(self) -> None:
        engine = RefundEngine()
        first = engine.run(
            "YF-R-0800", "write", intent_id="retry-demo", simulate_payment_failure=True
        )["decision_record"]
        payments = deepcopy(engine.repository.payment_instructions)
        tasks = deepcopy(engine.repository.finance_manual_tasks)
        retried = engine.run(
            "YF-R-0800", "write", intent_id="retry-demo", simulate_payment_failure=False
        )["decision_record"]
        self.assertEqual(retried["decision_id"], first["decision_id"])
        self.assertEqual(retried["outcome"], "compensated")
        self.assertTrue(retried["metadata"]["idempotent_replay"])
        self.assertEqual(engine.repository.payment_instructions, payments)
        self.assertEqual(engine.repository.finance_manual_tasks, tasks)
        self.assertEqual(len(engine.audit.records), 1)

    def test_new_intent_cannot_pay_an_approved_refund_again(self) -> None:
        engine = RefundEngine()
        engine.run("YF-R-0500", "write", intent_id="first")
        payments = deepcopy(engine.repository.payment_instructions)
        retried = engine.run("YF-R-0500", "write", intent_id="second")["decision_record"]
        self.assertEqual(retried["outcome"], "not_ready")
        self.assertIn("G-STATE", retried["rule_hits"])
        self.assertEqual(engine.repository.payment_instructions, payments)


class EvaluationExitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.good_report = GoldenEvaluator().run()

    def test_successful_evaluation_has_an_explicit_overall_result(self) -> None:
        self.assertTrue(self.good_report["passed"])
        with redirect_stdout(io.StringIO()) as output:
            main(["evaluate"])
        self.assertTrue(json.loads(output.getvalue())["passed"])

    def test_each_failed_evaluation_group_causes_nonzero_exit(self) -> None:
        for failure in ("core", "incidents", "validation", "candidate_guard"):
            with self.subTest(failure=failure):
                report = deepcopy(self.good_report)
                if failure == "core":
                    report["core"]["failed"] = 1
                    report["core"]["passed"] -= 1
                elif failure == "incidents":
                    report["incident_replays"]["passed"] -= 1
                elif failure == "validation":
                    report["document_to_rule"]["validation"]["passed"] = False
                else:
                    report["document_to_rule"]["candidate_execution_guard"]["passed"] = False
                # Recalculate from outcomes; do not trust a stale top-level flag.
                with patch("ontology_fde.cli.GoldenEvaluator.run", return_value=report):
                    with redirect_stdout(io.StringIO()) as output:
                        with self.assertRaises(SystemExit) as stopped:
                            main(["evaluate"])
                self.assertEqual(stopped.exception.code, 1)
                self.assertFalse(json.loads(output.getvalue())["passed"])

    def test_empty_golden_suite_does_not_report_a_pass(self) -> None:
        evaluator = GoldenEvaluator()
        evaluator.suite["cases"] = []
        report = evaluator.run()
        self.assertEqual(report["core"]["pass_rate"], 0.0)
        self.assertFalse(report["passed"])

    def test_empty_incident_suite_does_not_report_a_pass(self) -> None:
        report = deepcopy(self.good_report)
        report["incident_replays"].update(total=0, passed=0, results=[])
        self.assertFalse(evaluation_passed(report))

    def test_demo_writes_failed_manifest_and_exits_nonzero(self) -> None:
        report = deepcopy(self.good_report)
        report["core"].update(failed=1, passed=35)
        with tempfile.TemporaryDirectory() as directory:
            with patch("ontology_fde.cli.GoldenEvaluator.run", return_value=report):
                with redirect_stdout(io.StringIO()):
                    with self.assertRaises(SystemExit) as stopped:
                        main(["demo", "--output", directory])
            self.assertEqual(stopped.exception.code, 1)
            manifest = json.loads((Path(directory) / "manifest.json").read_text())
            self.assertFalse(manifest["evaluation"]["passed"])


class RuleReleaseGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.demo = OntologyGuidedRuleDemo()
        self.draft = self.demo.extract()
        self.facts = {
            "customer_channel": "b2c",
            "item_category": "opened_consumable",
            "hours_since_signed": 25,
        }

    def test_empty_document_rule_test_suite_cannot_pass_validation(self) -> None:
        self.demo.test_suite["cases"] = []
        validation = self.demo.validate(self.draft)
        self.assertFalse(validation["passed"])
        self.assertFalse(validation["validation_types"]["operational"]["passed"])

    def test_candidate_uses_the_threshold_extracted_from_source(self) -> None:
        policy = next(
            doc for doc in self.demo.corpus["documents"]
            if doc["document_type"] == "approved_policy"
        )
        policy["text"] = policy["text"].replace("24", "48")
        draft = self.demo.extract()
        self.assertEqual(self.demo.evaluate_candidate(draft, self.facts), "no_match")
        self.facts["hours_since_signed"] = 49
        self.assertEqual(self.demo.evaluate_candidate(draft, self.facts), "match")

    def test_invalid_elapsed_time_is_missing_data_not_a_negative_match(self) -> None:
        for elapsed in ("NaN", "Infinity", "bad", -1):
            with self.subTest(elapsed=elapsed):
                self.facts["hours_since_signed"] = elapsed
                self.assertEqual(
                    self.demo.evaluate_candidate(self.draft, self.facts), "missing_data"
                )

    def test_draft_cannot_grant_itself_permission_to_execute(self) -> None:
        self.draft["missing_inputs"] = []
        self.draft["lifecycle"]["execution_allowed_states"] = ["draft"]
        with self.assertRaises(RuleLifecycleError):
            self.demo.execute_rule(self.draft, self.facts)

    def test_state_label_without_review_does_not_allow_compile_or_execute(self) -> None:
        self.draft["missing_inputs"] = []
        self.draft["lifecycle"]["state"] = "approved"
        with self.assertRaises(RuleLifecycleError):
            self.demo.compile_rule(self.draft)
        self.draft["lifecycle"]["state"] = "compiled"
        with self.assertRaises(RuleLifecycleError):
            self.demo.execute_rule(self.draft, self.facts)

    def test_rule_approval_requires_reviewer_and_draft_state(self) -> None:
        with self.assertRaises(RuleLifecycleError):
            self.demo.approve_rule(
                self.draft, reviewer=" ",
                resolved_missing_inputs=self.draft["missing_inputs"],
            )
        self.draft["lifecycle"]["state"] = "retired"
        with self.assertRaises(RuleLifecycleError):
            self.demo.approve_rule(
                self.draft, reviewer="Customer Service Lead",
                resolved_missing_inputs=self.draft["missing_inputs"],
            )


if __name__ == "__main__":
    unittest.main()
