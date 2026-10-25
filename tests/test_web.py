import json
from http.client import HTTPConnection
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from ontology_fde.service import WorkbenchService
from ontology_fde.web import MAX_REQUEST_BYTES, make_server


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service = WorkbenchService()
        cls.server = make_server("127.0.0.1", 0, cls.service)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def get_json(self, path: str):
        with urlopen(self.base + path, timeout=5) as response:
            return json.load(response)

    def post_json(self, path: str, payload: dict):
        request = Request(
            self.base + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            return json.load(response)

    def setUp(self) -> None:
        self.post_json("/api/reset", {})

    def test_index_and_static_assets_load_without_cdn(self) -> None:
        with urlopen(self.base + "/", timeout=5) as response:
            html = response.read().decode("utf-8")
        self.assertIn('lang="zh-CN"', html)
        for label in ("云帆企业本体工作台", "业务对象", "退款处理", "决策记录", "测试与评估", "候选规则", "500 元"):
            self.assertIn(label, html)
        self.assertNotIn("https://", html)
        with urlopen(self.base + "/app.js", timeout=5) as response:
            app_js = response.read().decode("utf-8")
        self.assertGreater(len(app_js), 1000)
        self.assertIn("toolCalls", app_js)
        self.assertIn("待核实：本次查询未查到记录", app_js)
        self.assertIn("已确认未开票（ERP 明确返回）", app_js)
        self.assertIn("工具调用顺序", html)
        combined = html + app_js
        for retired_copy in (
            "Turn one refund into",
            "The model can recommend",
            "Logs tell you what happened",
            "Trust is not a feeling",
            "Companion project for Ontology: An FDE Practical Guide",
        ):
            self.assertNotIn(retired_copy, combined)
        self.assertNotIn("FDE Practical Guide", combined)
        self.assertNotIn('params.get("autorun")', app_js)
        self.assertIn("批准和生成退款指令都不等于到账", html)
        self.assertIn("刷新页面不会重置业务数据", html)
        self.assertIn("不用 API key", html)

    def test_dynamic_graph_api_uses_selected_refund(self) -> None:
        graph = self.get_json("/api/graph?refund_id=YF-R-0311")
        self.assertEqual(graph["generated_from"], "data/mock")
        self.assertTrue(any(node["object_id"] == "YF-R-0311" for node in graph["nodes"]))
        facts = self.get_json("/api/cases/YF-R-0311")
        self.assertEqual(facts["invoice_status"], "unknown")

    def test_write_api_exposes_human_gate(self) -> None:
        result = self.post_json(
            "/api/run", {"refund_id": "YF-R-0501", "mode": "write"}
        )
        self.assertEqual(result["decision_record"]["outcome"], "queued_for_human")
        self.assertEqual(result["trace_id"], result["decision_record"]["trace_id"])
        self.assertTrue(result["decision_record"]["tool_calls"])

    def test_conflict_case_does_not_create_payment_instruction(self) -> None:
        result = self.post_json(
            "/api/run", {"refund_id": "YF-R-0610", "mode": "write"}
        )
        self.assertIsNotNone(result["decision_record"]["conflict_resolution"])
        graph = self.get_json("/api/graph?refund_id=YF-R-0610")
        self.assertFalse(any(node["type"] == "PaymentInstruction" for node in graph["nodes"]))

    def test_evaluation_dashboard_payload_contains_rule_demo(self) -> None:
        report = self.get_json("/api/evaluation")
        self.assertEqual(report["core"]["passed"], 36)
        self.assertIn("document_to_rule", report)
        self.assertFalse(report["document_to_rule"]["validation"]["production_ready"])

    def test_read_and_draft_do_not_change_business_state(self) -> None:
        before = self.get_json("/api/cases/YF-R-0500")
        for mode in ("read", "draft"):
            result = self.post_json("/api/run", {"refund_id": "YF-R-0500", "mode": mode})
            self.assertEqual(result["mode"], mode)
            self.assertEqual(self.get_json("/api/cases/YF-R-0500"), before)
        result = self.post_json("/api/run", {"refund_id": "YF-R-0500", "mode": "write"})
        self.assertEqual(result["decision_record"]["outcome"], "auto_approved")
        self.assertEqual(self.get_json("/api/cases/YF-R-0500")["refund_status"], "approved")

    def test_unknown_invoice_never_automatically_approves(self) -> None:
        result = self.post_json("/api/run", {"refund_id": "YF-R-0311", "mode": "write"})
        self.assertEqual(result["decision_record"]["outcome"], "queued_for_human")
        self.assertIn("G-INVOICE-UNKNOWN", result["decision_record"]["rule_hits"])

    def test_duplicate_write_is_replayed_without_crashing_frontend_payload(self) -> None:
        payload = {"refund_id": "YF-R-0500", "mode": "write"}
        first = self.post_json("/api/run", payload)
        second = self.post_json("/api/run", payload)
        self.assertEqual(first["decision_record"]["decision_id"], second["decision_record"]["decision_id"])
        self.assertTrue(second["decision_record"]["metadata"]["idempotent_replay"])

    def test_server_rejects_public_bind_address(self) -> None:
        for host in ("0.0.0.0", "192.168.1.2", "::"):
            with self.subTest(host=host), self.assertRaises(ValueError):
                make_server(host, 0, self.service)

    def test_cross_origin_and_rebinding_requests_are_rejected(self) -> None:
        for headers in (
            {"Origin": "https://untrusted.invalid"},
            {"Origin": "null"},
            {"Host": "untrusted.invalid"},
            {"Sec-Fetch-Site": "cross-site"},
        ):
            request = Request(self.base + "/api/reset", data=b"{}", method="POST",
                              headers={"Content-Type": "application/json", **headers})
            with self.subTest(headers=headers), self.assertRaises(HTTPError) as caught:
                urlopen(request, timeout=5)
            self.assertEqual(caught.exception.code, 403)
            caught.exception.close()
        request = Request(self.base + "/api/reset", data=b"{}", method="POST",
                          headers={"Content-Type": "application/json", "Origin": self.base})
        with urlopen(request, timeout=5) as response:
            self.assertTrue(json.load(response)["ok"])

    def test_invalid_post_inputs_return_json_without_state_changes(self) -> None:
        invalid = ([], None, "test", {"refund_id": []}, {"refund_id": "YF-R-0500", "mode": []},
                   {"refund_id": "YF-R-0500", "simulate_payment_failure": "false"},
                   {"refund_id": "YF-R-0500", "actor": []}, {"refund_id": "YF-R-0500", "extra": 1})
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(HTTPError) as caught:
                self.post_json("/api/run", payload)
            self.assertEqual(caught.exception.code, 400)
            self.assertIn("error", json.load(caught.exception))
            caught.exception.close()
        self.assertEqual(self.get_json("/api/cases/YF-R-0500")["refund_status"], "pending_review")

    def test_request_body_bounds_and_media_type(self) -> None:
        cases = (
            ({"Content-Type": "application/json", "Content-Length": "-1"}, b"", 400),
            ({"Content-Type": "application/json", "Content-Length": "invalid"}, b"", 400),
            ({"Content-Type": "application/json", "Content-Length": str(MAX_REQUEST_BYTES+1)}, b"", 413),
            ({"Content-Type": "text/plain"}, b"{}", 415),
            ({"Content-Type": "application/json"}, b"{", 400),
            ({"Content-Type": "application/json"}, b"\xff", 400),
        )
        for headers, body, status in cases:
            with self.subTest(headers=headers):
                connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
                try:
                    connection.request("POST", "/api/reset", body=body, headers=headers)
                    response = connection.getresponse()
                    self.assertEqual(response.status, status)
                    self.assertIn("error", json.loads(response.read()))
                finally:
                    connection.close()

    def test_static_paths_cannot_escape_web_root(self) -> None:
        for path in ("/../web.py", "/%2e%2e/web.py", "/%2e%2e%2fweb.py"):
            with self.subTest(path=path), self.assertRaises(HTTPError) as caught:
                urlopen(self.base + path, timeout=5)
            self.assertEqual(caught.exception.code, 400)
            caught.exception.close()
        with urlopen(self.base + "/", timeout=5) as response:
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
            self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])

    def test_opening_view_url_never_resets_an_existing_decision(self) -> None:
        self.post_json("/api/run", {"refund_id": "YF-R-0500", "mode": "write"})
        with urlopen(self.base + "/?case=YF-R-0500&view=action&autorun=write", timeout=5) as response:
            self.assertEqual(response.status, 200)
        self.assertEqual(self.get_json("/api/cases/YF-R-0500")["refund_status"], "approved")


if __name__ == "__main__":
    unittest.main()
