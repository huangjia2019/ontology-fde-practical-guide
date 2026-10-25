import json
import unittest
from pathlib import Path

from ontology_fde.engine import RefundEngine
from ontology_fde.paths import project_root
from ontology_fde.repository import EnterpriseRepository, OntologyError


class RepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = EnterpriseRepository()

    def test_cross_source_case_keeps_real_lineage(self) -> None:
        case = self.repo.get_case("YF-R-0311")
        systems = {ref["system"] for ref in case.source_refs}
        self.assertTrue(
            {
                "CRM", "COMMERCE", "AFTER_SALES", "ERP", "SUPPORT", "RISK", "EVIDENCE"
            }.issubset(systems)
        )
        erp = next(ref for ref in case.source_refs if ref["system"] == "ERP")
        self.assertEqual(erp["observation"], "not_found")
        self.assertEqual(erp["query"], "order_id=O-9938")
        self.assertEqual(case.invoice_status, "unknown")
        self.assertEqual(case.customer_id, "C-8831")
        self.assertEqual(case.order_id, "O-9938")
        self.assertEqual(case.order_item_id, "OI-9938-1")

    def test_summary_reports_eight_enterprise_sources(self) -> None:
        summary = self.repo.summary()
        self.assertEqual(summary["source_count"], 8)
        self.assertIn("ERP", summary["source_systems"])
        self.assertIn("AFTER_SALES", summary["source_systems"])

    def test_graph_has_no_dangling_edge_and_comes_from_seed(self) -> None:
        graph = self.repo.graph("YF-R-0311")
        node_ids = {node["id"] for node in graph["nodes"]}
        self.assertEqual(graph["generated_from"], "data/mock")
        self.assertTrue(graph["edges"])
        for edge in graph["edges"]:
            self.assertIn(edge["from"], node_ids)
            self.assertIn(edge["to"], node_ids)

    def test_graph_changes_after_action_creates_payment_object(self) -> None:
        before = self.repo.graph("YF-R-0500")
        RefundEngine(self.repo).run("YF-R-0500", "write")
        after = self.repo.graph("YF-R-0500")
        self.assertEqual(len(after["nodes"]), len(before["nodes"]) + 1)
        self.assertTrue(any(node["type"] == "PaymentInstruction" for node in after["nodes"]))
        self.assertTrue(any(edge["type"] == "SETTLES" for edge in after["edges"]))

    def test_confirmed_no_invoice_is_distinct_from_no_result(self) -> None:
        case = self.repo.get_case("YF-R-0500")
        erp = next(ref for ref in case.source_refs if ref["system"] == "ERP")
        self.assertEqual(case.invoice_status, "none")
        self.assertEqual(erp["object_type"], "InvoiceStatusConfirmation")
        self.assertEqual(erp["observation"], "confirmed_no_invoice")

    def test_refund_foreign_keys_are_explicit(self) -> None:
        for refund in self.repo.refunds.values():
            self.assertIn(refund["customer_id"], self.repo.customers)
            self.assertIn(refund["order_id"], self.repo.orders)
            self.assertIn(refund["order_item_id"], self.repo.items)

    def test_compensation_state_is_in_state_machine(self) -> None:
        self.repo.transition("RefundRequest", "YF-R-0800", "approved")
        _, state = self.repo.transition("RefundRequest", "YF-R-0800", "approval_pending_payment")
        self.assertEqual(state, "approval_pending_payment")

    def test_illegal_transition_is_rejected(self) -> None:
        with self.assertRaises(OntologyError):
            self.repo.transition("RefundRequest", "YF-R-0311", "paid_out")

    def test_every_config_yaml_is_json_subset(self) -> None:
        for path in (project_root() / "config").rglob("*.yaml"):
            with self.subTest(path=path):
                json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
