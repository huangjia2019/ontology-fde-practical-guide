from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any


def parse_time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


@dataclass(slots=True)
class CaseFacts:
    refund_id: str
    customer_id: str | None
    order_id: str | None
    order_item_id: str | None
    amount: Decimal
    refund_status: str
    reason_code: str
    request_text: str
    opened_at: datetime
    customer_name: str
    customer_tier: str
    customer_channel: str | None
    order_status: str
    paid_amount: Decimal
    invoice_status: str
    item_category: str
    item_name: str
    item_condition: str
    signed_at: datetime | None
    hours_since_signed: float | None
    evidence_status: str
    evidence_refs: list[str]
    risk_level: str | None
    risk_reason: str
    previous_refunds_30d: int
    ticket_id: str | None
    source_refs: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return jsonable(asdict(self))

    @classmethod
    def from_eval(cls, values: dict[str, Any]) -> "CaseFacts":
        now = datetime.fromisoformat("2026-07-10T12:00:00+08:00")
        hours = values.get("hours_since_signed")
        signed_at = None
        if hours is not None:
            from datetime import timedelta

            signed_at = now - timedelta(hours=float(hours))
        return cls(
            refund_id=str(values.get("refund_id", "EVAL-REFUND")),
            customer_id=values.get("customer_id"),
            order_id=values.get("order_id"),
            order_item_id=values.get("order_item_id"),
            amount=Decimal(str(values.get("amount", 0))),
            refund_status=str(values.get("refund_status", "pending_review")),
            reason_code="eval_fixture",
            request_text=str(values.get("user_text", "")),
            opened_at=now,
            customer_name="Golden-case customer",
            customer_tier=str(values.get("customer_tier", "normal")),
            customer_channel=values.get("customer_channel"),
            order_status=str(values.get("order_status", "signed")),
            paid_amount=Decimal(str(values.get("amount", 0))),
            invoice_status=str(values.get("invoice_status", "none")),
            item_category=str(values.get("item_category", "accessory")),
            item_name="Golden-case product",
            item_condition="damaged",
            signed_at=signed_at,
            hours_since_signed=float(hours) if hours is not None else None,
            evidence_status=str(values.get("evidence_status", "accepted")),
            evidence_refs=["EVAL-EVIDENCE"] if values.get("evidence_status") == "accepted" else [],
            risk_level=values.get("risk_level"),
            risk_reason="eval_fixture",
            previous_refunds_30d=int(values.get("previous_refunds_30d", 0)),
            ticket_id="EVAL-TICKET",
            source_refs=[{"system": "EVAL", "source_id": str(values.get("refund_id"))}],
        )


@dataclass(slots=True)
class DecisionDraft:
    decision: str
    candidate_action: str | None
    final_action: str | None
    reasons: list[str]
    rule_hits: list[str]
    checks: dict[str, bool]
    approval_required: bool
    autonomy_level: str
    agent_candidates: list[dict[str, str]] = field(default_factory=list)
    conflict_resolution: dict[str, str] | None = None
    security_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return jsonable(asdict(self))
