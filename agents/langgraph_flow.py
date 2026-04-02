from __future__ import annotations

from typing import Optional, TypedDict

from langgraph.graph import END, StateGraph

from agents.approval import approve_invoice
from agents.ingestion import extract_invoice
from agents.payment import process_payment
from agents.validation import validate_invoice
from schema import ApprovalResult, Invoice, PaymentResult, ValidationResult, to_dict
from utils.logging import log_event
from utils.schemas import (
    ApprovalInput,
    ApprovalOutput,
    IngestionInput,
    IngestionOutput,
    PaymentInput,
    PaymentOutput,
    ValidationInput,
    ValidationOutput,
    validate_or_raise,
)


class InvoiceState(TypedDict, total=False):
    invoice_path: str
    db_path: str
    invoice: Invoice
    validation: ValidationResult
    approval: ApprovalResult
    payment: PaymentResult


def run_langgraph(invoice_path: str, db_path: str) -> InvoiceState:
    graph = _build_graph()
    return graph.invoke({"invoice_path": invoice_path, "db_path": db_path})


def _build_graph():
    builder: StateGraph[InvoiceState] = StateGraph(InvoiceState)

    builder.add_node("ingestion", _ingestion_node)
    builder.add_node("validation", _validation_node)
    builder.add_node("approval", _approval_node)
    builder.add_node("payment", _payment_node)

    builder.set_entry_point("ingestion")
    builder.add_edge("ingestion", "validation")
    builder.add_edge("validation", "approval")
    builder.add_edge("approval", "payment")
    builder.add_edge("payment", END)

    return builder.compile()


def _ingestion_node(state: InvoiceState) -> InvoiceState:
    validate_or_raise(IngestionInput, {"invoice_path": state.get("invoice_path")})
    invoice = extract_invoice(state["invoice_path"])
    log_event("ingestion", {"invoice": to_dict(invoice)})
    validate_or_raise(IngestionOutput, {"invoice": invoice})
    return {"invoice": invoice}


def _validation_node(state: InvoiceState) -> InvoiceState:
    invoice = state["invoice"]
    validate_or_raise(ValidationInput, {"invoice": invoice, "db_path": state.get("db_path")})
    validation = validate_invoice(invoice, state["db_path"])
    log_event("validation", {"result": to_dict(validation)})
    validate_or_raise(ValidationOutput, {"validation": validation})
    return {"validation": validation}


def _approval_node(state: InvoiceState) -> InvoiceState:
    invoice = state["invoice"]
    validation = state["validation"]
    validate_or_raise(ApprovalInput, {"invoice": invoice, "validation": validation})
    approval = approve_invoice(invoice, validation)
    log_event("approval", {"result": to_dict(approval)})
    validate_or_raise(ApprovalOutput, {"approval": approval})
    return {"approval": approval}


def _payment_node(state: InvoiceState) -> InvoiceState:
    invoice = state["invoice"]
    approval = state["approval"]
    validate_or_raise(PaymentInput, {"invoice": invoice, "approval": approval})
    payment = process_payment(invoice, approval)
    log_event("payment", {"result": to_dict(payment)})
    validate_or_raise(PaymentOutput, {"payment": payment})
    return {"payment": payment}
