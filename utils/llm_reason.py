from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv
from pathlib import Path

import sqlite3

from schema import ApprovalResult, Invoice, ValidationResult


def generate_reason(invoice: Invoice, validation: ValidationResult, approval: ApprovalResult) -> str:
    root = Path(__file__).resolve().parent.parent
    load_dotenv(root / "llm.env")
    load_dotenv(root / "agents" / "llm.env")
    base_reason = _deterministic_reason(invoice, validation, approval)
    prompt = _build_prompt(base_reason)
    content = _try_grok(prompt)
    if not content:
        raise RuntimeError("XAI_API_KEY is not set or Grok request failed.")
    refined = content.strip()
    if _is_safe_refinement(refined, base_reason, invoice, validation, approval):
        return refined
    return base_reason


def _build_prompt(base_reason: str) -> str:
    return (
        "Rewrite the following reason into 2-3 concise sentences. "
        "Do not add, remove, or change any facts. Keep invoice id, decision, and issue types intact.\n\n"
        f"Reason: {base_reason}\n"
        "Response:"
    )


def _deterministic_reason(invoice: Invoice, validation: ValidationResult, approval: ApprovalResult) -> str:
    if approval.approved:
        decision = "approved"
    elif validation.status == "review":
        decision = "routed for manual review"
    else:
        decision = "rejected"

    issues = []
    for issue in validation.issues:
        if issue.item:
            issues.append(f"{issue.issue_type}({issue.item})")
        else:
            issues.append(issue.issue_type)
    issues_text = ", ".join(issues) if issues else "no validation issues"

    inventory_summary, remaining_summary = _inventory_summary(invoice, approval)
    return (
        f"Invoice {invoice.invoice_id} was {decision}. "
        f"Validation status was {validation.status} with issues: {issues_text}. "
        f"{inventory_summary} "
        f"{remaining_summary}"
    )


def _is_safe_refinement(
    refined: str,
    base_reason: str,
    invoice: Invoice,
    validation: ValidationResult,
    approval: ApprovalResult,
) -> bool:
    # Must mention invoice id and decision keyword
    if invoice.invoice_id not in refined:
        return False
    if approval.approved and "approve" not in refined.lower():
        return False
    if not approval.approved and validation.status == "review" and "review" not in refined.lower():
        return False
    if not approval.approved and validation.status != "review" and "reject" not in refined.lower():
        return False

    # Ensure it doesn't drop all issue types when issues exist
    if validation.issues:
        for issue in validation.issues:
            if issue.issue_type not in refined:
                return False

    return True


def _inventory_summary(invoice: Invoice, approval: ApprovalResult) -> tuple[str, str]:
    inventory = _load_inventory("inventory.db")
    if not inventory:
        return ("Inventory lookup unavailable.", "Remaining quantities not computed.")

    parts = []
    remaining_parts = []
    for item in invoice.items:
        stock = inventory.get(item.item_name)
        if stock is None:
            parts.append(f"{item.item_name}: not found in inventory")
            continue
        parts.append(f"{item.item_name}: requested {item.quantity}, in stock {stock}")
        if approval.approved:
            remaining = stock - item.quantity
            remaining_parts.append(f"{item.item_name}: remaining {remaining}")

    inventory_summary = "Inventory check: " + "; ".join(parts) + "." if parts else "No items to check."
    if approval.approved and remaining_parts:
        remaining_summary = "Post-approval remaining stock: " + "; ".join(remaining_parts) + "."
    elif approval.approved:
        remaining_summary = "Post-approval remaining stock: not available."
    else:
        remaining_summary = "No stock deducted because the invoice was not approved."
    return inventory_summary, remaining_summary


def _load_inventory(db_path: str) -> dict[str, int]:
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS inventory (item TEXT PRIMARY KEY, stock INTEGER)")
        cursor.execute("SELECT item, stock FROM inventory")
        data = {row[0]: int(row[1]) for row in cursor.fetchall()}
        conn.close()
        return data
    except Exception:
        return {}


def _try_grok(prompt: str) -> Optional[str]:
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        return None
    try:
        import httpx  # type: ignore
    except Exception:
        return None
    model = os.getenv("XAI_MODEL", "grok-3")
    url = os.getenv("XAI_BASE_URL", "https://api.x.ai/v1/chat/completions")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    try:
        resp = httpx.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            return None
        return choices[0]["message"]["content"]
    except Exception:
        return None
