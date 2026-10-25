from __future__ import annotations

import json
import mimetypes
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .service import WorkbenchService


WEB_ROOT = Path(__file__).resolve().parent / "web"
MAX_REQUEST_BYTES = 16 * 1024


def make_server(
    host: str = "127.0.0.1", port: int = 8000, service: WorkbenchService | None = None
) -> ThreadingHTTPServer:
    # This is an unauthenticated, in-memory teaching app, not a public service.
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("教学工作台仅支持本机地址 127.0.0.1 或 localhost")
    shared_service = service or WorkbenchService()
    service_lock = threading.RLock()

    class Handler(BaseHTTPRequestHandler):
        server_version = "OntologyFDE/0.1"

        def log_message(self, format: str, *args: object) -> None:
            # Keep the local UAT server quiet; API results remain available in the trace UI.
            return

        def do_GET(self) -> None:  # noqa: N802
            if not self._local_request():
                return
            parsed = urlparse(self.path)
            try:
                with service_lock:
                    if parsed.path == "/api/summary":
                        return self._json(shared_service.summary())
                    if parsed.path == "/api/cases":
                        return self._json(shared_service.cases())
                    if parsed.path.startswith("/api/cases/"):
                        return self._json(shared_service.case(parsed.path.rsplit("/", 1)[-1]))
                    if parsed.path == "/api/graph":
                        refund_id = parse_qs(parsed.query).get("refund_id", [None])[0]
                        return self._json(shared_service.graph(refund_id))
                    if parsed.path == "/api/identity":
                        return self._json(shared_service.identity())
                    if parsed.path == "/api/evaluation":
                        return self._json(shared_service.evaluation())
                    if parsed.path == "/api/document-rule":
                        return self._json(shared_service.document_rule())
                return self._static(parsed.path)
            except (KeyError, ValueError, RuntimeError) as error:
                return self._json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)

        def do_POST(self) -> None:  # noqa: N802
            if not self._local_request():
                return
            if self.path not in {"/api/run", "/api/reset"}:
                return self._json({"error": "没有这个接口"}, status=HTTPStatus.NOT_FOUND)
            try:
                if self.headers.get("Transfer-Encoding"):
                    raise ValueError("不支持分块请求")
                if self.headers.get_content_type() != "application/json":
                    return self._json({"error": "请使用 application/json"}, status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0:
                    raise ValueError("请求长度不能为负数")
                if length > MAX_REQUEST_BYTES:
                    return self._json({"error": "请求内容过大"}, status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                self.connection.settimeout(5)
                body = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(body, dict):
                    raise ValueError("请求内容必须是 JSON 对象")
                with service_lock:
                    if self.path == "/api/run":
                        self._validate_run(body)
                        return self._json(shared_service.run(body))
                    if body:
                        raise ValueError("重置接口不接受参数")
                    return self._json(shared_service.reset())
            except TimeoutError:
                return self._json({"error": "接收请求超时，请重新操作"}, status=HTTPStatus.REQUEST_TIMEOUT)
            except (UnicodeDecodeError, KeyError, ValueError, RuntimeError) as error:
                return self._json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)

        def _local_request(self) -> bool:
            authority = self.headers.get("Host", "")
            allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            if self.server.server_port == 80:
                allowed.update({"127.0.0.1", "localhost"})
            if authority not in allowed:
                self._json({"error": "只接受本机工作台请求"}, status=HTTPStatus.FORBIDDEN)
                return False
            origin = self.headers.get("Origin")
            if (origin is not None and origin != f"http://{authority}") or self.headers.get("Sec-Fetch-Site") == "cross-site":
                self._json({"error": "不接受其他网站发起的请求"}, status=HTTPStatus.FORBIDDEN)
                return False
            return True

        @staticmethod
        def _validate_run(body: dict) -> None:
            allowed = {"refund_id", "mode", "actor", "intent_id", "simulate_payment_failure", "processing_at"}
            if set(body) - allowed:
                raise ValueError("请求包含未知参数")
            if not isinstance(body.get("refund_id"), str) or not body["refund_id"]:
                raise ValueError("请选择退款申请 refund_id")
            if body.get("mode", "write") not in ("read", "draft", "write"):
                raise ValueError("mode 必须是 read、draft 或 write")
            for field in ("actor", "intent_id", "processing_at"):
                if field in body and (not isinstance(body[field], str) or not body[field]):
                    raise ValueError(f"{field} 必须是非空字符串")
            if "simulate_payment_failure" in body and type(body["simulate_payment_failure"]) is not bool:
                raise ValueError("simulate_payment_failure 必须是布尔值")

        def _security_headers(self) -> None:
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")

        def _json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status.value)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self._security_headers()
            self.end_headers()
            self.wfile.write(body)

        def _static(self, request_path: str) -> None:
            request_path = unquote(request_path)
            relative = "index.html" if request_path in {"", "/"} else request_path.lstrip("/")
            candidate = (WEB_ROOT / relative).resolve()
            if WEB_ROOT not in candidate.parents and candidate != WEB_ROOT:
                return self._json({"error": "invalid path"}, status=HTTPStatus.BAD_REQUEST)
            if not candidate.is_file():
                return self._json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)
            body = candidate.read_bytes()
            content_type, _ = mimetypes.guess_type(candidate.name)
            self.send_response(HTTPStatus.OK.value)
            self.send_header("Content-Type", f"{content_type or 'application/octet-stream'}; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self._security_headers()
            self.end_headers()
            self.wfile.write(body)

    return ThreadingHTTPServer((host, port), Handler)


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = make_server(host, port)
    print(f"云帆企业本体工作台（本机演练）：http://{host}:{server.server_port}")
    print("无需 API key，不连接真实业务系统。按 Ctrl+C 停止；重启后恢复初始演练数据。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
