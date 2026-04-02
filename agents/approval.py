from __future__ import annotations

from schema import ApprovalResult, Invoice, ValidationResult


def approve_invoice(invoice: Invoice, validation: ValidationResult) -> ApprovalResult:
    if validation.status == "fail":
        reason = _summarize_issues(validation)
        status_reason = validation.status_reason or "Validation failed."
        return ApprovalResult(
            approved=False,
            reason=_format_action("reject", status_reason, reason),
            confidence=0.9,
        )
    if validation.status == "review":
        reason = _summarize_issues(validation)
        status_reason = validation.status_reason or "Missing or uncertain fields."
        return ApprovalResult(
            approved=False,
            reason=_format_action("manual_review", status_reason, reason),
            confidence=0.6,
        )

    decision, reason, confidence = _initial_decision(invoice)
    decision, reason, confidence = _reflection(decision, reason, confidence, invoice)
    return ApprovalResult(approved=decision, reason=reason, confidence=confidence)


def _initial_decision(invoice: Invoice) -> tuple[bool, str, float]:
    if invoice.amount > 10000:
        return False, f"Manual review required: amount {invoice.amount:.2f} exceeds 10000.", 0.6
    return True, "Approved within standard limits.", 0.7


def _reflection(decision: bool, reason: str, confidence: float, invoice: Invoice) -> tuple[bool, str, float]:
    flags = []
    raw = (invoice.raw_text or "").lower()
    if "urgent" in raw or "wire transfer" in raw:
        flags.append("urgent_or_wire")
    if invoice.due_date is None:
        flags.append("missing_due_date")
    if invoice.amount <= 0:
        flags.append("invalid_amount")

    if decision and flags:
        decision = False
        confidence = max(0.8, confidence)
        reason = f"Rejected after reflection due to risk flags: {', '.join(flags)}."
    elif not decision and not flags and invoice.amount <= 10000:
        decision = True
        confidence = max(0.6, confidence)
        reason = "Approved after reflection; no additional risk flags."

    return decision, reason, confidence


def _summarize_issues(validation: ValidationResult) -> str:
    if not validation.issues:
        return "unknown issue"
    parts = []
    for issue in validation.issues[:4]:
        if issue.item:
            parts.append(f"{issue.issue_type}({issue.item})")
        else:
            parts.append(issue.issue_type)
    suffix = "..." if len(validation.issues) > 4 else ""
    return ", ".join(parts) + suffix


def _format_action(action: str, status_reason: str, issues: str) -> str:
    action_map = {
        "reject": "Action: Reject payment.",
        "manual_review": "Action: Route to manual review.",
    }
    action_line = action_map.get(action, "Action: Review.")
    detail = f"Reason: {status_reason}"
    if issues:
        detail += f" Issues: {issues}"
    return f"{action_line} {detail}".strip()
