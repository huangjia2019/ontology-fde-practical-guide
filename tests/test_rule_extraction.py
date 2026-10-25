import copy
import unittest

from ontology_fde.rule_extraction import OntologyGuidedRuleDemo, RuleLifecycleError


class RuleExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.demo = OntologyGuidedRuleDemo()
        self.draft = self.demo.extract()

    def test_four_validation_types_and_five_case_kinds_pass(self) -> None:
        report = self.demo.validate(self.draft)
        self.assertTrue(report["validation_complete"])
        self.assertEqual(
            set(report["validation_types"]),
            {"structural", "semantic", "operational", "epistemic"},
        )
        self.assertEqual(
            set(report["test_kinds"]),
            {"positive", "negative", "boundary", "missing_data", "out_of_scope"},
        )

    def test_validated_draft_is_still_not_production_ready(self) -> None:
        report = self.demo.validate(self.draft)
        self.assertFalse(report["production_ready"])
        self.assertIn("missing_inputs_not_resolved", report["production_blockers"])
        self.assertIn("human_review_not_completed", report["production_blockers"])

    def test_candidate_draft_cannot_execute(self) -> None:
        with self.assertRaises(RuleLifecycleError):
            self.demo.execute_rule(
                self.draft,
                {"customer_channel": "b2c", "item_category": "opened_consumable", "hours_since_signed": 25},
            )

    def test_missing_inputs_block_compile_even_if_state_is_manually_changed(self) -> None:
        tampered = copy.deepcopy(self.draft)
        tampered["lifecycle"]["state"] = "approved"
        with self.assertRaises(RuleLifecycleError):
            self.demo.compile_rule(tampered)

    def test_review_then_compile_then_execute(self) -> None:
        approved = self.demo.approve_rule(
            self.draft,
            reviewer="Customer Service Operations Lead",
            resolved_missing_inputs=["opened_state_not_explicitly_modeled"],
        )
        compiled = self.demo.compile_rule(approved)
        actual = self.demo.execute_rule(
            compiled,
            {"customer_channel": "b2c", "item_category": "opened_consumable", "hours_since_signed": 25},
        )
        self.assertEqual(actual, "match")

    def test_retired_rule_cannot_run(self) -> None:
        approved = self.demo.approve_rule(
            self.draft,
            reviewer="Customer Service Operations Lead",
            resolved_missing_inputs=["opened_state_not_explicitly_modeled"],
        )
        retired = self.demo.retire_rule(self.demo.compile_rule(approved))
        with self.assertRaises(RuleLifecycleError):
            self.demo.execute_rule(
                retired,
                {"customer_channel": "b2c", "item_category": "opened_consumable", "hours_since_signed": 25},
            )

    def test_boundary_and_scope_are_deterministic(self) -> None:
        self.assertEqual(
            self.demo.evaluate_candidate(
                self.draft,
                {"customer_channel": "b2c", "item_category": "opened_consumable", "hours_since_signed": 24},
            ),
            "no_match",
        )
        self.assertEqual(
            self.demo.evaluate_candidate(
                self.draft,
                {"customer_channel": "b2b", "item_category": "opened_consumable", "hours_since_signed": 48},
            ),
            "out_of_scope",
        )

    def test_expert_observation_cannot_strengthen_formal_policy(self) -> None:
        tampered = copy.deepcopy(self.draft)
        tampered["conclusion"]["action"] = "approve_refund_small"
        report = self.demo.validate(tampered)
        self.assertFalse(report["validation_types"]["semantic"]["passed"])
        self.assertFalse(report["validation_types"]["epistemic"]["passed"])

    def test_provenance_has_locator_and_content_hash(self) -> None:
        for item in self.draft["provenance"]:
            self.assertTrue(item["source_locator"])
            self.assertEqual(len(item["source_hash_prefix"]), 12)


if __name__ == "__main__":
    unittest.main()
