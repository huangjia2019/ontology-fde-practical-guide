import io
import json
import unittest
from contextlib import redirect_stdout

from ontology_fde.checkpoints import checkpoint_payload
from ontology_fde.cli import main
from ontology_fde.exit_drill import exit_drill_payload


class CheckpointTests(unittest.TestCase):
    def test_all_ten_checkpoint_structural_checks_pass(self) -> None:
        for number in range(1, 11):
            with self.subTest(checkpoint=number):
                payload = checkpoint_payload(number, check=True)
                failed = [
                    item for item in payload["check"]["items"] if not item["passed"]
                ]
                self.assertTrue(payload["check"]["passed"], failed)

    def test_checkpoint_cli_emits_book_ready_card(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            main(["checkpoint", "8", "--check"])
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["number"], 8)
        self.assertIn("YF-R-0610", payload["commands"][0])
        self.assertTrue(payload["check"]["passed"])

    def test_checkpoint_three_checks_promotion_and_rollback_gates(self) -> None:
        payload = checkpoint_payload(3, check=True)
        items = {item["name"]: item for item in payload["check"]["items"]}
        self.assertTrue(items["promotion_gate_declared"]["passed"])
        self.assertTrue(items["rollback_conditions_declared"]["passed"])
        self.assertTrue(items["eight_data_sources_declared"]["passed"])
        self.assertTrue(items["runtime_side_effects_declared"]["passed"])

    def test_checkpoint_artifact_paths_use_english_names(self) -> None:
        expected = {
            1: [
                "docs/artifacts/01-field-walkthrough.md",
                "docs/artifacts/01-ontology-positioning-card.md",
                "docs/artifacts/01-six-question-diagnostic.md",
            ],
            2: ["docs/artifacts/02-historical-audit.md"],
            3: ["docs/artifacts/03-identity-acceptance.md"],
            4: ["docs/artifacts/04-minimum-ontology.md"],
            5: ["docs/artifacts/05-action-contract.md"],
            6: ["docs/artifacts/06-rule-assets.md"],
            7: ["docs/artifacts/07-identity-and-permissions.md"],
            8: [
                "docs/artifacts/08-multi-agent-coordination.md",
                "docs/artifacts/08-task-envelope-YF-R-0610.json",
            ],
            9: ["docs/artifacts/09-evaluation-audit-and-incident-replay.md"],
            10: ["docs/artifacts/10-operations-handoff-and-replication.md"],
        }
        for number, paths in expected.items():
            with self.subTest(checkpoint=number):
                artifacts = checkpoint_payload(number)["artifacts"]
                self.assertTrue(all(path in artifacts for path in paths))

    def test_exit_drill_runs_five_ordered_controls(self) -> None:
        payload = exit_drill_payload()
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(
            [step["action"] for step in payload["steps"]],
            [
                "Close Write",
                "Revoke credentials",
                "Return unfinished work to people",
                "Preserve audit evidence",
                "Check continuity",
            ],
        )
        self.assertTrue(all(step["status"] == "PASS" for step in payload["steps"]))
        self.assertIn("no_real_iam_or_erp", payload["scope"])

    def test_exit_drill_cli_emits_pass(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            main(["exit-drill"])
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["status"], "PASS")

    def test_checkpoint_ten_reuses_executable_exit_drill(self) -> None:
        payload = checkpoint_payload(10, check=True)
        items = {item["name"]: item for item in payload["check"]["items"]}
        self.assertTrue(items["executable_exit_drill_passes"]["passed"])


if __name__ == "__main__":
    unittest.main()
