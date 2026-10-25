from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .models import jsonable


# The book's sample events and audit dates use UTC+8. A fixed offset keeps the
# offline demo usable on Windows without an IANA database or the tzdata package.
AUDIT_TIMEZONE = timezone(timedelta(hours=8))


# BOOK-CH9-START
@dataclass(slots=True)
class ToolCall:
    call_id: str
    sequence: int
    phase: str
    tool_name: str
    display_name: str
    target: str
    status: str
    duration_ms: int
    result: str

    def to_dict(self) -> dict[str, Any]:
        return jsonable(asdict(self))


@dataclass(slots=True)
class TaskEnvelope:
    envelope_id: str
    correlation_id: str
    sender: str
    recipient: str
    task_type: str
    goal: str
    object_refs: list[str]
    allowed_actions: list[str]
    forbidden_actions: list[str]
    context_scope: list[str]
    expires_at: str
    status: str
    constraints: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return jsonable(asdict(self))


@dataclass(slots=True)
class DecisionRecord:
    decision_id: str
    trace_id: str
    timestamp: str
    correlation_id: str
    envelope_id: str
    task_envelope: TaskEnvelope | dict[str, Any]
    mode: str
    actor: str
    representation: str
    permission_policy_id: str
    authority: dict[str, Any]
    agent_version: str
    model_version: str
    ontology_version: str
    policy_version: str
    contract_version: str
    initiator: str
    target_objects: list[str]
    source_refs: list[dict[str, Any]]
    evidence_refs: list[str]
    checks: dict[str, bool]
    rule_hits: list[str]
    agent_candidates: list[dict[str, str]]
    conflict_resolution: dict[str, str] | None
    candidate_action: str | None
    final_action: str | None
    autonomy_level: str
    approval: dict[str, Any]
    state_before: str
    state_after: str
    expected_effect: str
    actual_effect: str
    outcome: str
    idempotency_key: str
    tool_calls: list[ToolCall | dict[str, Any]]
    human_override: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return jsonable(asdict(self))
# BOOK-CH9-END


class AuditStore:
    def __init__(self, output_path: Path | None = None) -> None:
        self.output_path = output_path
        self.records: list[dict[str, Any]] = []
        self._counter = 0

    def next_id(self, event_time: datetime | None = None) -> str:
        self._counter += 1
        event_time = event_time or datetime.now(AUDIT_TIMEZONE)
        today = event_time.astimezone(AUDIT_TIMEZONE).strftime("%Y%m%d")
        return f"DR-{today}-{self._counter:04d}"

    def append(self, record: DecisionRecord | dict[str, Any]) -> dict[str, Any]:
        payload = record.to_dict() if isinstance(record, DecisionRecord) else jsonable(record)
        self.records.append(payload)
        if self.output_path:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            with self.output_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return payload

    def latest(self) -> dict[str, Any] | None:
        return self.records[-1] if self.records else None

    def clear(self) -> None:
        self.records.clear()
        self._counter = 0
        if self.output_path and self.output_path.exists():
            self.output_path.unlink()
