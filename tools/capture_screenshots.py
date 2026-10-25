#!/usr/bin/env python3
"""从本机工作台生成四张读者截图；Playwright 仅在制图时需要。"""

from __future__ import annotations

import argparse
import json
import os
import struct
import sys
import threading
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
SCREENSHOTS = ROOT / "docs" / "assets" / "screenshots"
VIEWPORT = {"width": 1600, "height": 1000}

sys.path.insert(0, str(ROOT / "src"))

from ontology_fde.web import make_server  # noqa: E402

CAPTURES = (
    ("01-ontology-workbench.png", "ontology", "YF-R-0311", False),
    ("02-action-console.png", "action", "YF-R-0501", True),
    ("03-audit-trace.png", "audit", "YF-R-0610", True),
    ("04-evaluation-dashboard.png", "evaluation", "YF-R-0311", False),
)


def read_json(url: str) -> dict:
    with urlopen(url, timeout=10) as response:
        return json.load(response)


def png_size(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError(f"不是有效的 PNG 文件：{path.name}")
    return struct.unpack(">II", header[16:24])


def launch_browser(playwright, channel: str | None):
    configured = os.environ.get("CHROME_BIN")
    if configured:
        if channel:
            raise SystemExit("CHROME_BIN 与 --channel 只能选一个。")
        executable = Path(configured).expanduser()
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise SystemExit("CHROME_BIN 必须指向可执行的 Chrome 或 Chromium 浏览器。")
        return playwright.chromium.launch(executable_path=str(executable), headless=True)
    if channel:
        return playwright.chromium.launch(channel=channel, headless=True)
    # Prefer Playwright's matching Chromium; an installed Chrome is a fallback.
    for options in ({}, {"channel": "chrome"}):
        try:
            return playwright.chromium.launch(headless=True, **options)
        except Exception:
            continue
    raise SystemExit(
        "没有找到可用浏览器。先运行 uv run --with playwright playwright install chromium，"
        "或指定 CHROME_BIN / --channel chrome。"
    )


def verify_capture(base_url: str, view: str, page) -> None:
    facts = read_json(f"{base_url}/api/cases/YF-R-0311")
    if facts["invoice_status"] != "unknown":
        raise RuntimeError("347 元遥控器单的发票状态必须是 unknown，不能当成确定未开票。")
    if "not_found" not in {ref.get("observation") for ref in facts["source_refs"]}:
        raise RuntimeError("347 元遥控器单必须保留 ERP 本次未查到记录的来源证据。")
    confirmed = read_json(f"{base_url}/api/cases/YF-R-0500")
    if confirmed["invoice_status"] != "none" or "confirmed_no_invoice" not in {
        ref.get("observation") for ref in confirmed["source_refs"]
    }:
        raise RuntimeError("500 元申请必须有 ERP 明确未开票的确认，不能与未知状态混用。")

    if view == "ontology":
        if "待核实：本次查询未查到记录" not in page.locator("#factSummary").inner_text():
            raise RuntimeError("业务对象页没有正确显示发票待核实。")
    elif view in {"action", "audit"}:
        record = json.loads(page.locator("#auditJson").inner_text())
        if record["outcome"] != "queued_for_human" or record["state_after"] != "pending_human":
            raise RuntimeError("这张截图中的申请必须进入人工审核，不能自动批准。")
        expected_rule = "G-AMOUNT" if view == "action" else "G-RISK"
        if expected_rule not in record["rule_hits"]:
            raise RuntimeError(f"截图缺少预期规则：{expected_rule}")
        if not any(call["tool_name"] == "workflow.create_human_approval_packet"
                   for call in record["tool_calls"]):
            raise RuntimeError("没有生成供人工接手的审批材料。")
        if view == "audit":
            if not record["conflict_resolution"]:
                raise RuntimeError("YF-R-0610 必须保留退款助手与风控意见冲突。")
            graph = read_json(f"{base_url}/api/graph?refund_id=YF-R-0610")
            if any(node["type"] == "PaymentInstruction" for node in graph["nodes"]):
                raise RuntimeError("风控要求复核后，不得创建退款指令。")
            if any(call["tool_name"] == "payments.create_refund_instruction"
                   for call in record["tool_calls"]):
                raise RuntimeError("风控要求复核后，不得调用退款指令工具。")
            sequence = [call["sequence"] for call in record["tool_calls"]]
            if sequence != list(range(1, len(sequence)+1)):
                raise RuntimeError("工具调用序号不连续。")
    else:
        report = read_json(f"{base_url}/api/evaluation")
        if (report["core"]["passed"], report["core"]["total"]) != (36, 36):
            raise RuntimeError("核心基线未达到 36/36，请先处理测试失败。")
        if (report["incident_replays"]["passed"], report["incident_replays"]["total"]) != (2, 2):
            raise RuntimeError("故障回放未达到 2/2。")
        if report["document_to_rule"]["validation"]["production_ready"]:
            raise RuntimeError("候选规则仍有未完成条件，不应显示为可生产执行。")


def capture(context, expect, base_url: str, output_dir: Path, spec: tuple) -> None:
    filename, view, refund_id, execute = spec
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(f"{base_url}/?view={view}&case={refund_id}", wait_until="networkidle")
        expect(page.locator("#caseSelect")).to_be_enabled()
        with page.expect_response(lambda response: response.url.endswith("/api/reset")) as reset:
            page.locator("#resetBtn").click()
        if not reset.value.ok:
            raise RuntimeError("截图前重置演练失败。")
        expect(page.locator("#caseSelect")).to_be_enabled()

        # Use the same controls as a reader; merely opening a URL never writes.
        if execute:
            page.locator('[data-view="action"]').click()
            with page.expect_response(lambda response: response.url.endswith("/api/run")) as run:
                page.locator('[data-mode="write"]').click()
            if not run.value.ok:
                raise RuntimeError("模拟执行失败，不能生成成功状态的截图。")
            expect(page.locator("#actionOutcome")).to_contain_text("已转人工审核")
            expect(page.locator("#caseSelect")).to_be_enabled()
        page.locator(f'[data-view="{view}"]').click()
        # Initial help stays available in the app; collapse it in reference images.
        page.locator(".reader-guide summary").click()
        # Reset feedback is transient; it is not part of the business evidence.
        page.locator("#message").evaluate("element => { element.hidden = true; }")
        page.evaluate("document.fonts.ready")
        page.evaluate("window.scrollTo(0, 0)")
        verify_capture(base_url, view, page)
        if page.evaluate("document.documentElement.scrollWidth > window.innerWidth"):
            raise RuntimeError(f"{filename} 出现横向溢出，需先修正页面布局。")
        if errors:
            raise RuntimeError(f"{filename} 存在 JavaScript 错误：{errors[0]}")
        expected_height = page.evaluate(
            "Math.max(document.documentElement.scrollHeight, window.innerHeight)"
        )
        output = output_dir / filename
        page.screenshot(path=str(output), full_page=True, animations="disabled")
        width, height = png_size(output)
        if width != VIEWPORT["width"] or abs(height-expected_height) > 1:
            raise RuntimeError(f"{filename} 不是完整页面截图：{width}×{height}。")
        print(f"已生成 {filename} · {width}×{height} · 业务状态校验通过")
    finally:
        page.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=SCREENSHOTS,
                        help="输出目录，默认 docs/assets/screenshots")
    parser.add_argument("--channel", choices=("chrome",),
                        help="使用已经安装的 Google Chrome")
    args = parser.parse_args()
    try:
        from playwright.sync_api import expect, sync_playwright
    except ImportError:
        raise SystemExit(
            "制图需要 Playwright。请运行：uv run --with playwright python tools/capture_screenshots.py\n"
            "只阅读或运行退款项目不需要安装它。"
        ) from None
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    server = make_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        read_json(f"{base_url}/api/summary")
        with sync_playwright() as playwright:
            browser = launch_browser(playwright, args.channel)
            try:
                context = browser.new_context(
                    viewport=VIEWPORT, device_scale_factor=1, locale="zh-CN"
                )
                try:
                    for spec in CAPTURES:
                        capture(context, expect, base_url, output_dir, spec)
                finally:
                    context.close()
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    main()
