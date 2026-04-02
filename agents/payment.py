from __future__ import annotations

from schema import ApprovalResult, Invoice, PaymentResult


def mock_payment(vendor: str, amount: float) -> dict:
    print(f"Paid {amount} to {vendor}")
    return {"status": "success"}


def process_payment(invoice: Invoice, approval: ApprovalResult) -> PaymentResult:
    # Placeholder implementation; will be replaced with real flow.
    if approval.approved:
        result = mock_payment(invoice.vendor, invoice.amount)
        return PaymentResult(status=result.get("status", "unknown"), detail="paid")
    return PaymentResult(status="skipped", detail="not approved")
