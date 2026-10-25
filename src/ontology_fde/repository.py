from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from .models import CaseFacts, parse_time
from .paths import load_structured


class OntologyError(RuntimeError):
    pass


class EnterpriseRepository:
    """In-memory adapter over realistic, source-preserving enterprise mock data."""

    DATA_FILES = {
        "crm": "data/mock/crm/customers.json",
        "commerce": "data/mock/commerce/orders.json",
        "after_sales": "data/mock/after_sales/refunds.json",
        "erp": "data/mock/erp/invoices.json",
        "support": "data/mock/support/tickets.json",
        "risk": "data/mock/risk/signals.json",
        "evidence": "data/mock/evidence/evidence.json",
        "payments": "data/mock/payments/instructions.json",
        "crosswalk": "data/mock/source_crosswalk.json",
    }

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        datasets = {name: load_structured(path) for name, path in self.DATA_FILES.items()}
        self.datasets = deepcopy(datasets)
        self.customers = {
            row["canonical_id"]: row for row in datasets["crm"]["records"]
        }
        self.orders = {
            row["canonical_id"]: row for row in datasets["commerce"]["orders"]
        }
        self.items = {
            row["canonical_id"]: row for row in datasets["commerce"]["items"]
        }
        self.refunds = {
            row["canonical_id"]: row for row in datasets["after_sales"]["records"]
        }
        self.invoices = {
            row["canonical_id"]: row for row in datasets["erp"]["records"]
        }
        self.invoice_status_confirmations = {
            row["canonical_id"]: row
            for row in datasets["erp"].get("status_confirmations", [])
        }
        self.tickets = {
            row["canonical_id"]: row for row in datasets["support"]["records"]
        }
        self.risk_signals = {
            row["canonical_id"]: row for row in datasets["risk"]["records"]
        }
        self.evidence = {
            row["canonical_id"]: row for row in datasets["evidence"]["records"]
        }
        self.payment_instructions = {
            row["canonical_id"]: row for row in datasets["payments"]["records"]
        }
        self.human_approval_packets: dict[str, dict[str, Any]] = {}
        self.evidence_request_drafts: dict[str, dict[str, Any]] = {}
        self.finance_manual_tasks: dict[str, dict[str, Any]] = {}
        self.crosswalk = {
            row["canonical_id"]: row for row in datasets["crosswalk"]["records"]
        }
        machine = load_structured("config/ontology/state_machines.yaml")
        self.state_machines = machine["state_machines"]

    def list_refunds(self, include_history: bool = False) -> list[dict[str, Any]]:
        rows = []
        for refund_id in sorted(self.refunds):
            refund = self.refunds[refund_id]
            if not include_history and refund["workflow_state"] in {"paid_out", "rejected"}:
                continue
            customer = self.customers[refund["customer_id"]]
            rows.append(
                {
                    "refund_id": refund_id,
                    "amount": refund["requested_amount_cny"],
                    "status": refund["workflow_state"],
                    "customer_name": customer["name"],
                    "channel": customer["account_channel"],
                    "title": refund["request_text"],
                }
            )
        return rows

    # BOOK-CH4-START
    def get_case(self, refund_id: str) -> CaseFacts:
        """Join one RefundRequest to canonical objects while preserving every source reference."""

        try:
            refund = self.refunds[refund_id]
            customer = self.customers[refund["customer_id"]]
            order = self.orders[refund["order_id"]]
            item = self.items[refund["order_item_id"]]
        except KeyError as error:
            raise OntologyError(f"Cannot ground {refund_id}: missing {error.args[0]}") from error

        if order.get("customer_id") != customer["canonical_id"]:
            raise OntologyError(f"Cannot ground {refund_id}: order and refund customers differ")
        if item.get("order_id") != order["canonical_id"]:
            raise OntologyError(f"Cannot ground {refund_id}: item does not belong to the order")

        invoice = next(
            (row for row in self.invoices.values() if row["order_id"] == order["canonical_id"]),
            None,
        )
        invoice_confirmation = next(
            (
                row
                for row in self.invoice_status_confirmations.values()
                if row["order_id"] == order["canonical_id"]
            ),
            None,
        )
        ticket = next(
            (row for row in self.tickets.values() if row.get("refund_id") == refund_id), None
        )
        risks = [
            row
            for row in self.risk_signals.values()
            if row["customer_id"] == customer["canonical_id"]
        ]
        risk = max(risks, key=lambda row: row["observed_at"]) if risks else None
        evidence = [row for row in self.evidence.values() if row["refund_id"] == refund_id]
        evidence_status = "accepted" if any(
            row["verification_status"] == "accepted" for row in evidence
        ) else (evidence[0]["verification_status"] if evidence else "missing")

        opened_at = parse_time(refund["opened_at"])
        signed_at = parse_time(order.get("signed_at"))
        hours_since_signed = None
        if opened_at and signed_at:
            hours_since_signed = (opened_at - signed_at).total_seconds() / 3600

        previous = 0
        if opened_at:
            for row in self.refunds.values():
                if row["canonical_id"] == refund_id or row["customer_id"] != customer["canonical_id"]:
                    continue
                other_opened = parse_time(row["opened_at"])
                if other_opened and timedelta(0) < opened_at - other_opened <= timedelta(days=30):
                    previous += 1

        sources = [
            self._source_ref("CRM", customer, "Customer"),
            self._source_ref("COMMERCE", order, "Order"),
            self._source_ref("COMMERCE", item, "OrderItem"),
            self._source_ref("AFTER_SALES", refund, "RefundRequest"),
        ]
        if invoice:
            sources.append(self._source_ref("ERP", invoice, "Invoice"))
        elif invoice_confirmation:
            confirmation_ref = self._source_ref(
                "ERP", invoice_confirmation, "InvoiceStatusConfirmation"
            )
            confirmation_ref["observation"] = "confirmed_no_invoice"
            sources.append(confirmation_ref)
        else:
            erp_snapshot = self.datasets["erp"]
            sources.append(
                {
                    "system": "ERP",
                    "source_id": erp_snapshot["extract_id"],
                    "canonical_id": f"INVOICE-LOOKUP-{order['canonical_id']}",
                    "object_type": "Invoice",
                    "observation": "not_found",
                    "query": f"order_id={order['canonical_id']}",
                    "observed_at": erp_snapshot["extracted_at"],
                }
            )
        if ticket:
            sources.append(self._source_ref("SUPPORT", ticket, "Ticket"))
        if risk:
            sources.append(self._source_ref("RISK", risk, "RiskSignal"))
        sources.extend(self._source_ref("EVIDENCE", row, "Evidence") for row in evidence)

        return CaseFacts(
            refund_id=refund_id,
            customer_id=customer["canonical_id"],
            order_id=order["canonical_id"],
            order_item_id=item["canonical_id"],
            amount=Decimal(str(refund["requested_amount_cny"])),
            refund_status=refund["workflow_state"],
            reason_code=refund["reason_code"],
            request_text=refund["request_text"],
            opened_at=opened_at,
            customer_name=customer["name"],
            customer_tier=customer["service_tier"],
            customer_channel=customer.get("account_channel") or "unknown",
            order_status=order["fulfillment_status"],
            paid_amount=Decimal(str(order["net_paid_cny"])),
            invoice_status=(
                invoice["status"]
                if invoice
                else invoice_confirmation["status"]
                if invoice_confirmation
                else "unknown"
            ),
            item_category=item["category"],
            item_name=item["product_name"],
            item_condition=item["condition"],
            signed_at=signed_at,
            hours_since_signed=hours_since_signed,
            evidence_status=evidence_status,
            evidence_refs=[row["canonical_id"] for row in evidence],
            risk_level=risk["decision_level"] if risk else None,
            risk_reason=risk["reason"] if risk else "No valid risk object found",
            previous_refunds_30d=previous,
            ticket_id=ticket["canonical_id"] if ticket else None,
            source_refs=sources,
        )
    # BOOK-CH4-END

    def _source_ref(self, system: str, row: dict[str, Any], object_type: str) -> dict[str, Any]:
        return {
            "system": system,
            "source_id": row["source_id"],
            "canonical_id": row["canonical_id"],
            "object_type": object_type,
        }

    def transition(self, object_type: str, object_id: str, new_state: str) -> tuple[str, str]:
        if object_type != "RefundRequest":
            raise OntologyError(f"Demo transition not implemented for {object_type}")
        row = self.refunds[object_id]
        old_state = row["workflow_state"]
        allowed = {tuple(pair) for pair in self.state_machines[object_type]["transitions"]}
        if (old_state, new_state) not in allowed:
            raise OntologyError(f"Illegal {object_type} transition: {old_state} -> {new_state}")
        row["workflow_state"] = new_state
        return old_state, new_state

    def create_payment_instruction(
        self,
        refund_id: str,
        amount: Decimal,
        *,
        fail: bool = False,
        occurred_at: datetime | None = None,
    ) -> dict[str, Any]:
        instruction_id = f"PI-{refund_id.replace('YF-R-', '')}"
        row = {
            "source_id": f"ERP-RFND-DEMO-{refund_id}",
            "canonical_id": instruction_id,
            "refund_id": refund_id,
            "status": "failed" if fail else "created",
            "amount_cny": float(amount),
            "created_at": self._event_timestamp(occurred_at),
            "updated_at": self._event_timestamp(occurred_at),
        }
        self.payment_instructions[instruction_id] = row
        return row

    def create_human_approval_packet(
        self,
        refund_id: str,
        amount: Decimal,
        reason: str,
        *,
        occurred_at: datetime | None = None,
    ) -> dict[str, Any]:
        packet_id = f"HAP-{refund_id.replace('YF-R-', '')}"
        row = {
            "canonical_id": packet_id,
            "refund_id": refund_id,
            "amount_cny": float(amount),
            "reason": reason,
            "status": "pending",
            "created_at": self._event_timestamp(occurred_at),
        }
        self.human_approval_packets[packet_id] = row
        return row

    def create_evidence_request_draft(
        self,
        refund_id: str,
        evidence_status: str,
        *,
        occurred_at: datetime | None = None,
    ) -> dict[str, Any]:
        draft_id = f"ERD-{refund_id.replace('YF-R-', '')}"
        row = {
            "canonical_id": draft_id,
            "refund_id": refund_id,
            "evidence_status": evidence_status,
            "status": "draft",
            "created_at": self._event_timestamp(occurred_at),
        }
        self.evidence_request_drafts[draft_id] = row
        return row

    def create_finance_manual_task(
        self,
        refund_id: str,
        instruction_id: str,
        *,
        occurred_at: datetime | None = None,
    ) -> dict[str, Any]:
        task_id = f"FMT-{refund_id.replace('YF-R-', '')}"
        row = {
            "canonical_id": task_id,
            "refund_id": refund_id,
            "payment_instruction_id": instruction_id,
            "status": "open",
            "created_at": self._event_timestamp(occurred_at),
        }
        self.finance_manual_tasks[task_id] = row
        return row

    @staticmethod
    def _event_timestamp(occurred_at: datetime | None) -> str:
        if occurred_at is None:
            return "2026-07-11T09:30:00+08:00"
        return occurred_at.isoformat(timespec="seconds")

    def summary(self) -> dict[str, Any]:
        graph = self.graph()
        source_systems = sorted(
            {
                dataset["source_system"]
                for name, dataset in self.datasets.items()
                if name != "crosswalk" and "source_system" in dataset
            }
        )
        return {
            "company": "Yunfan Technologies (fictional and de-identified)",
            "source_systems": source_systems,
            "source_count": len(source_systems),
            "active_refunds": len(self.list_refunds()),
            "object_nodes": len(graph["nodes"]),
            "relationships": len(graph["edges"]),
            "approval_threshold_cny": load_structured(
                "config/actions/approve_refund_small.yaml"
            )["approval"]["threshold_cny"],
            "agent_id": "agent.cs.refund.001",
        }

    def graph(self, refund_id: str | None = None) -> dict[str, Any]:
        """Build the graph from actual mock records; no concept-only nodes are hard-coded."""

        nodes: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, str]] = []

        def add_node(kind: str, row: dict[str, Any], label: str, state: str = "") -> str:
            node_id = f"{kind}#{row['canonical_id']}"
            nodes[node_id] = {
                "id": node_id,
                "object_id": row["canonical_id"],
                "type": kind,
                "label": label,
                "state": state,
                "source_system": self._system_for_kind(kind),
                "source_id": row["source_id"],
            }
            return node_id

        refund_rows = (
            [self.refunds[refund_id]]
            if refund_id
            else [self.refunds[row["refund_id"]] for row in self.list_refunds()]
        )
        selected_customers: set[str] = set()
        for refund in refund_rows:
            customer = self.customers[refund["customer_id"]]
            order = self.orders[refund["order_id"]]
            item = self.items[refund["order_item_id"]]
            selected_customers.add(customer["canonical_id"])
            customer_node = add_node(
                "Customer", customer, customer["name"], customer["service_tier"]
            )
            order_node = add_node(
                "Order", order, order["canonical_id"], order["fulfillment_status"]
            )
            item_node = add_node("OrderItem", item, item["product_name"], item["condition"])
            refund_node = add_node(
                "RefundRequest",
                refund,
                f"{refund['canonical_id']} · RMB {refund['requested_amount_cny']}",
                refund["workflow_state"],
            )
            edges.extend(
                [
                    {"from": customer_node, "to": order_node, "type": "OWNS"},
                    {"from": order_node, "to": item_node, "type": "CONTAINS"},
                    {"from": refund_node, "to": item_node, "type": "TARGETS"},
                    {"from": refund_node, "to": order_node, "type": "FOR_ORDER"},
                    {"from": refund_node, "to": customer_node, "type": "REQUESTED_BY"},
                ]
            )
            for ticket in self.tickets.values():
                if ticket.get("refund_id") != refund["canonical_id"]:
                    continue
                ticket_node = add_node("Ticket", ticket, ticket["subject"], ticket["case_status"])
                edges.extend(
                    [
                        {"from": ticket_node, "to": customer_node, "type": "OPENED_BY"},
                        {"from": ticket_node, "to": refund_node, "type": "ABOUT_REFUND"},
                    ]
                )
            for evidence in self.evidence.values():
                if evidence["refund_id"] != refund["canonical_id"]:
                    continue
                ev_node = add_node(
                    "Evidence", evidence, evidence["kind"], evidence["verification_status"]
                )
                edges.append({"from": ev_node, "to": refund_node, "type": "SUPPORTS"})
            for invoice in self.invoices.values():
                if invoice["order_id"] != order["canonical_id"]:
                    continue
                inv_node = add_node("Invoice", invoice, invoice["canonical_id"], invoice["status"])
                edges.append({"from": inv_node, "to": order_node, "type": "BILLS"})
            for payment in self.payment_instructions.values():
                if payment["refund_id"] != refund["canonical_id"]:
                    continue
                pay_node = add_node(
                    "PaymentInstruction", payment, payment["canonical_id"], payment["status"]
                )
                edges.append({"from": pay_node, "to": refund_node, "type": "SETTLES"})

        for risk in self.risk_signals.values():
            if risk["customer_id"] not in selected_customers:
                continue
            customer_node = f"Customer#{risk['customer_id']}"
            risk_node = add_node(
                "RiskSignal", risk, risk["reason_code"], risk["decision_level"]
            )
            edges.append({"from": risk_node, "to": customer_node, "type": "ABOUT"})

        return {"nodes": list(nodes.values()), "edges": edges, "generated_from": "data/mock"}

    @staticmethod
    def _system_for_kind(kind: str) -> str:
        return {
            "Customer": "CRM",
            "Order": "COMMERCE",
            "OrderItem": "COMMERCE",
            "RefundRequest": "AFTER_SALES",
            "RiskSignal": "RISK",
            "Ticket": "SUPPORT",
            "Invoice": "ERP",
            "Evidence": "EVIDENCE",
            "PaymentInstruction": "PAYMENTS",
        }[kind]
