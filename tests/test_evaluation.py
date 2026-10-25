import unittest

from ontology_fde.evaluator import GoldenEvaluator


class EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = GoldenEvaluator().run()

    def test_all_36_core_cases_pass(self) -> None:
        core = self.report["core"]
        self.assertEqual(core["total"], 36)
        self.assertEqual(core["passed"], 36)
        self.assertEqual(core["failed"], 0)

    def test_six_dimensions_match_book_distribution(self) -> None:
        categories = self.report["core"]["categories"]
        self.assertEqual(
            {name: row["total"] for name, row in categories.items()},
            {"facts": 6, "ontology": 6, "policy": 8, "action": 6, "adversarial": 6, "business": 4},
        )

    def test_two_incident_replays_pass(self) -> None:
        self.assertEqual(self.report["incident_replays"]["total"], 2)
        self.assertEqual(self.report["incident_replays"]["passed"], 2)

    def test_report_declares_policy_and_end_to_end_scopes(self) -> None:
        scope = self.report["scope"]
        self.assertEqual(scope["core_and_incident_replays"], "policy_level")
        self.assertIn("tests/test_engine.py", scope["end_to_end_execution"])

    def test_audit_requirements_are_part_of_every_case(self) -> None:
        self.assertTrue(all(row["audit_complete"] for row in self.report["core"]["results"]))


if __name__ == "__main__":
    unittest.main()
