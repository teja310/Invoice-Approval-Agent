from __future__ import annotations

import json
from pathlib import Path
from typing import List

from schema import Invoice


STATE_PATH = Path("data/fraud_seen.jsonl")
RISKY_VENDORS_PATH = Path("data/risky_vendors.txt")
CACHED_VENDORS: set[str] = set()
CACHED_MTIME: float | None = None


def evaluate_fraud(invoice: Invoice) -> List[str]:
    flags: List[str] = []

    if invoice.amount <= 0:
        flags.append("non_positive_total")
    if invoice.amount >= 10000:
        flags.append("high_total")

    vendor = _normalize_vendor(invoice.vendor)
    if vendor and vendor in _load_risky_vendors():
        flags.append("risky_vendor")

    if _is_duplicate(invoice):
        flags.append("possible_duplicate_invoice")

    return flags


def record_invoice(invoice: Invoice) -> None:
    if not invoice.invoice_id or invoice.invoice_id == "UNKNOWN":
        return
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "invoice_id": invoice.invoice_id,
        "vendor": invoice.vendor,
        "amount": invoice.amount,
    }
    with STATE_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def _is_duplicate(invoice: Invoice) -> bool:
    if not invoice.invoice_id or invoice.invoice_id == "UNKNOWN":
        return False
    if not STATE_PATH.exists():
        return False
    try:
        lines = STATE_PATH.read_text(encoding="utf-8").splitlines()
    except Exception:
        return False
    for line in lines:
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if payload.get("invoice_id") == invoice.invoice_id:
            return True
    return False


def _normalize_vendor(vendor: str | None) -> str:
    if not vendor:
        return ""
    normalized = vendor.strip().lower()
    for suffix in [", inc.", " inc.", ", llc", " llc", ", ltd.", " ltd.", ", ltd", " ltd", ", corp.", " corp."]:
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return normalized.strip()


def _load_risky_vendors() -> set[str]:
    global CACHED_MTIME, CACHED_VENDORS

    if not RISKY_VENDORS_PATH.exists():
        CACHED_VENDORS = set()
        CACHED_MTIME = None
        return set()

    try:
        mtime = RISKY_VENDORS_PATH.stat().st_mtime
    except Exception:
        return CACHED_VENDORS

    if CACHED_MTIME is not None and mtime == CACHED_MTIME:
        return CACHED_VENDORS

    try:
        lines = RISKY_VENDORS_PATH.read_text(encoding="utf-8").splitlines()
    except Exception:
        return CACHED_VENDORS

    CACHED_VENDORS = {
        line.strip().lower() for line in lines if line.strip() and not line.strip().startswith("#")
    }
    CACHED_MTIME = mtime
    return CACHED_VENDORS
