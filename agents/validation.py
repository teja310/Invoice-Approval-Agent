from __future__ import annotations

import os
import sqlite3
from typing import Dict, List, Tuple

from schema import Invoice, ValidationIssue, ValidationResult


def validate_invoice(invoice: Invoice, db_path: str) -> ValidationResult:
    inventory = _load_inventory(db_path)
    issues: List[ValidationIssue] = []

    review_flags: List[ValidationIssue] = []

    if not invoice.invoice_id or invoice.invoice_id == "UNKNOWN":
        review_flags.append(
            ValidationIssue(issue_type="missing_invoice_id", item=None, detail="Invoice id missing.")
        )
    if not invoice.vendor or invoice.vendor == "UNKNOWN":
        review_flags.append(ValidationIssue(issue_type="missing_vendor", item=None, detail="Vendor missing."))
    if invoice.amount <= 0:
        review_flags.append(
            ValidationIssue(issue_type="invalid_amount", item=None, detail=f"Amount {invoice.amount} invalid.")
        )
    if not invoice.items:
        review_flags.append(ValidationIssue(issue_type="missing_items", item=None, detail="No line items found."))

    # Hard fail if essential fields are all missing (likely not an invoice).
    essential_missing = (
        (not invoice.invoice_id or invoice.invoice_id == "UNKNOWN")
        and (not invoice.vendor or invoice.vendor == "UNKNOWN")
        and invoice.amount <= 0
        and not invoice.items
    )
    if essential_missing:
        issues.append(
            ValidationIssue(
                issue_type="not_an_invoice",
                item=None,
                detail="Essential invoice fields missing; content does not appear to be an invoice.",
            )
        )

    for item in invoice.items:
        if item.quantity <= 0:
            issues.append(
                ValidationIssue(
                    issue_type="invalid_quantity",
                    item=item.item_name,
                    detail=f"Quantity {item.quantity} invalid for {item.item_name}.",
                )
            )
        if item.item_name not in inventory:
            issues.append(
                ValidationIssue(
                    issue_type="unknown_item",
                    item=item.item_name,
                    detail=f"{item.item_name} not found in inventory.",
                )
            )
            continue
        stock = inventory[item.item_name]
        if stock <= 0:
            issues.append(
                ValidationIssue(
                    issue_type="out_of_stock",
                    item=item.item_name,
                    detail=f"{item.item_name} out of stock (0).",
                )
            )
        elif item.quantity > stock:
            issues.append(
                ValidationIssue(
                    issue_type="stock_exceeded",
                    item=item.item_name,
                    detail=f"Requested {item.quantity}, available {stock}.",
                )
            )

    _check_amount_consistency(invoice, issues)

    if invoice.suspicious_flags:
        review_flags.append(
            ValidationIssue(
                issue_type="suspicious_flags",
                item=None,
                detail="; ".join(invoice.suspicious_flags),
            )
        )

    combined = issues + review_flags
    if issues:
        status = "fail"
        reason = "Hard validation failures present."
    elif review_flags:
        status = "review"
        reason = "Missing or uncertain fields require review."
    else:
        status = "pass"
        reason = "All validation checks passed."
    return ValidationResult(status=status, issues=combined, status_reason=reason)


def _check_amount_consistency(invoice: Invoice, issues: List[ValidationIssue]) -> None:
    total = 0.0
    has_pricing = False
    for item in invoice.items:
        if item.line_total is not None:
            has_pricing = True
            total += item.line_total
            continue
        if item.unit_price is None:
            continue
        has_pricing = True
        total += item.unit_price * item.quantity
    if not has_pricing:
        return
    if invoice.amount <= 0:
        return
    diff = abs(invoice.amount - total)
    if diff > max(1.0, invoice.amount * 0.02):
        issues.append(
            ValidationIssue(
                issue_type="amount_mismatch",
                item=None,
                detail=f"Invoice total {invoice.amount:.2f} differs from items sum {total:.2f}.",
            )
        )


def _load_inventory(db_path: str) -> Dict[str, int]:
    if not os.path.exists(db_path):
        _init_inventory_db(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS inventory (item TEXT PRIMARY KEY, stock INTEGER)")
    cursor.execute("SELECT item, stock FROM inventory")
    inventory = {row[0]: int(row[1]) for row in cursor.fetchall()}
    conn.close()
    return inventory


def _init_inventory_db(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS inventory (item TEXT PRIMARY KEY, stock INTEGER)")
    cursor.execute(
        """
        INSERT OR IGNORE INTO inventory VALUES
        ('WidgetA', 15),
        ('WidgetB', 10),
        ('GadgetX', 5),
        ('FakeItem', 0)
        """
    )
    conn.commit()
    conn.close()
