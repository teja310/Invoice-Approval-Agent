from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


@dataclass
class InvoiceItem:
    item_name: str
    quantity: int
    unit_price: Optional[float] = None
    line_total: Optional[float] = None


@dataclass
class Invoice:
    invoice_id: str
    vendor: str
    amount: float
    currency: Optional[str]
    due_date: Optional[str]
    items: List[InvoiceItem]
    notes: Optional[str]
    suspicious_flags: List[str]
    missing_fields: List[str]
    parsing_confidence: float
    source_path: str
    raw_text: Optional[str] = None


@dataclass
class ValidationIssue:
    issue_type: str
    item: Optional[str]
    detail: str


@dataclass
class ValidationResult:
    status: str  # "pass" | "fail"
    issues: List[ValidationIssue]
    status_reason: Optional[str] = None


@dataclass
class ApprovalResult:
    approved: bool
    reason: str
    confidence: float


@dataclass
class PaymentResult:
    status: str
    detail: str


def to_dict(obj: Any) -> Dict[str, Any]:
    return asdict(obj)
