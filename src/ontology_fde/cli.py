from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from .checkpoints import checkpoint_payload
from .engine import RefundEngine
from .evaluator import GoldenEvaluator, evaluation_passed
from .exit_drill import exit_drill_payload
from .models import parse_time
from .paths import load_structured, project_root, write_json
from .repository import EnterpriseRepository
from .rule_extraction import OntologyGuidedRuleDemo
from .web import serve


def print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ontology-fde",
        description="Yunfan Technologies refund agent: an executable ontology and FDE case",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("summary", help="Show a cross-source data and ontology summary")
    sub.add_parser("identity", help="Show the agent's IART identity profile")

    inspect = sub.add_parser("inspect", help="Read the normalized facts for one refund")
    inspect.add_argument("refund_id")

    graph = sub.add_parser("graph", help="Generate a live object graph as JSON")
    graph.add_argument("--refund-id")
    graph.add_argument("--output", type=Path)

    run = sub.add_parser("run", help="Run the Read, Draft, or Write phase")
    run.add_argument("refund_id")
    run.add_argument("--mode", choices=("read", "draft", "write"), default="write")
    run.add_argument("--actor", default="agent.cs.refund.001")
    run.add_argument("--intent-id")
    run.add_argument("--simulate-payment-failure", action="store_true")
    run.add_argument(
        "--processing-at",
        help=(
            "Supply an ISO-8601 event time with a UTC offset. By default, the mock "
            "uses the refund request time for reproducible runs."
        ),
    )
    run.add_argument("--audit", type=Path)

    evaluate = sub.add_parser(
        "evaluate",
        help="Replay 36 golden cases, 2 incidents, and the document-rule tests",
    )
    evaluate.add_argument("--output", type=Path)

    extract = sub.add_parser(
        "extract-rule", help="Run the offline document-to-Rule-Draft demo"
    )
    extract.add_argument("--output", type=Path)

    demo = sub.add_parser(
        "demo", help="Run the complete case and write replayable artifacts"
    )
    demo.add_argument("--output", type=Path, default=Path("artifacts/demo"))

    checkpoint = sub.add_parser(
        "checkpoint",
        help="Show an engineering card for checkpoints 1 through 10",
    )
    checkpoint.add_argument("number", type=int, choices=range(1, 11))
    checkpoint.add_argument(
        "--check",
        action="store_true",
        help="Validate the checkpoint artifacts and required fields",
    )

    sub.add_parser(
        "exit-drill",
        help=(
            "Rehearse disabling Write, revoking credentials, restoring human "
            "control, retaining audit evidence, and checking continuity"
        ),
    )

    server = sub.add_parser("serve", help="Start the browser workbench")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8000)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "summary":
        return print_json(EnterpriseRepository().summary())
    if args.command == "identity":
        return print_json(load_structured("config/identity/refund_agent.yaml"))
    if args.command == "inspect":
        return print_json(EnterpriseRepository().get_case(args.refund_id).to_dict())
    if args.command == "graph":
        payload = EnterpriseRepository().graph(args.refund_id)
        if args.output:
            write_json(args.output, payload)
        return print_json(payload)
    if args.command == "run":
        audit_path = args.audit
        engine = RefundEngine(audit_path=audit_path)
        return print_json(
            engine.run(
                args.refund_id,
                args.mode,
                actor=args.actor,
                intent_id=args.intent_id,
                simulate_payment_failure=args.simulate_payment_failure,
                processing_at=parse_time(args.processing_at),
            )
        )
    if args.command == "evaluate":
        report = GoldenEvaluator().run(args.output)
        print_json(_evaluation_summary(report))
        if not evaluation_passed(report):
            raise SystemExit(1)
        return None
    if args.command == "extract-rule":
        report = OntologyGuidedRuleDemo().run_demo()
        if args.output:
            write_json(args.output, report)
        return print_json(report)
    if args.command == "demo":
        return _run_demo(args.output)
    if args.command == "checkpoint":
        payload = checkpoint_payload(args.number, check=args.check)
        print_json(payload)
        if args.check and not payload["check"]["passed"]:
            raise SystemExit(1)
        return None
    if args.command == "exit-drill":
        payload = exit_drill_payload()
        print_json(payload)
        if payload["status"] != "PASS":
            raise SystemExit(1)
        return None
    if args.command == "serve":
        return serve(args.host, args.port)
    raise AssertionError(args.command)


def _evaluation_summary(report: dict[str, Any]) -> dict[str, Any]:
    document = report["document_to_rule"]
    return {
        "passed": evaluation_passed(report),
        "scope": report["scope"],
        "golden": {
            "passed": report["core"]["passed"],
            "total": report["core"]["total"],
            "categories": report["core"]["categories"],
        },
        "incident_replays": {
            "passed": report["incident_replays"]["passed"],
            "total": report["incident_replays"]["total"],
        },
        "document_to_rule": {
            "four_validations_passed": document["validation"]["passed"],
            "five_case_kinds": document["validation"]["test_kinds"],
            "candidate_execution_blocked": document["candidate_execution_guard"]["passed"],
        },
    }


def _run_demo(output_dir: Path) -> None:
    output_dir = output_dir if output_dir.is_absolute() else project_root() / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    audit_path = output_dir / "decision_records.jsonl"
    if audit_path.exists():
        audit_path.unlink()
    engine = RefundEngine(audit_path=audit_path)
    runs = [
        engine.run("YF-R-0311", "read"),
        engine.run("YF-R-0311", "draft"),
        engine.run("YF-R-0311", "write"),
        engine.run("YF-R-0500", "write"),
        engine.run("YF-R-0501", "write"),
        engine.run("YF-R-0610", "write"),
        engine.run("YF-R-0800", "write", simulate_payment_failure=True),
    ]
    report = GoldenEvaluator().run(output_dir / "evaluation_report.json")
    write_json(output_dir / "demo_runs.json", runs)
    write_json(output_dir / "ontology_graph.json", engine.repository.graph())
    write_json(output_dir / "document_rule_demo.json", report["document_to_rule"])
    manifest = {
        "scenario": "Yunfan Technologies refund agent, from Read to controlled Write",
        "runs": [
            {
                "refund_id": row["refund_id"],
                "mode": row["mode"],
                "outcome": (row.get("decision_record") or {}).get("outcome", "read_only"),
            }
            for row in runs
        ],
        "evaluation": _evaluation_summary(report),
        "artifacts": [
            "decision_records.jsonl",
            "demo_runs.json",
            "ontology_graph.json",
            "evaluation_report.json",
            "document_rule_demo.json",
        ],
    }
    write_json(output_dir / "manifest.json", manifest)
    print_json(manifest)
    if not evaluation_passed(report):
        raise SystemExit(1)
