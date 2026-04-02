from __future__ import annotations

import csv
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree

from dotenv import load_dotenv

from schema import Invoice, InvoiceItem
from utils.fraud import evaluate_fraud, record_invoice


def extract_invoice(invoice_path: str) -> Invoice:
    root = Path(__file__).resolve().parent.parent
    load_dotenv(root / "llm.env")
    load_dotenv(root / "agents" / "llm.env")

    path = Path(invoice_path)
    suffix = path.suffix.lower()

    if suffix == ".json":
        invoice, raw_text = _parse_json(path)
    elif suffix == ".csv":
        invoice, raw_text = _parse_csv(path)
    elif suffix == ".xml":
        invoice, raw_text = _parse_xml(path)
    elif suffix == ".pdf":
        invoice, raw_text = _parse_pdf(path)
    else:
        invoice, raw_text = _parse_text(path)

    invoice.raw_text = raw_text
    invoice.source_path = str(path)

    enriched = _maybe_llm_extract(raw_text, path)
    if enriched is not None and _should_accept_llm(invoice, enriched):
        invoice = enriched
        invoice.raw_text = raw_text
        invoice.source_path = str(path)

    _backfill_amount(invoice)
    _postprocess_invoice(invoice)
    return invoice


def _should_accept_llm(original: Invoice, enriched: Invoice) -> bool:
    # Keep deterministic parse if LLM dropped key fields.
    if original.items and not enriched.items:
        return False
    if original.invoice_id != "UNKNOWN" and enriched.invoice_id == "UNKNOWN":
        return False
    if original.vendor != "UNKNOWN" and enriched.vendor == "UNKNOWN":
        return False
    if original.amount > 0 and enriched.amount <= 0:
        return False
    return True


def _parse_json(path: Path) -> Tuple[Invoice, str]:
    raw_text = path.read_text(encoding="utf-8")
    payload = json.loads(raw_text)

    vendor_obj = payload.get("vendor") or {}
    vendor = vendor_obj.get("name") if isinstance(vendor_obj, dict) else vendor_obj
    items = []
    for item in payload.get("line_items", []) or []:
        items.append(
            InvoiceItem(
                item_name=str(item.get("item", "")).strip(),
                quantity=int(item.get("quantity", 0) or 0),
                unit_price=_to_float(item.get("unit_price")),
                line_total=_to_float(item.get("amount") or item.get("line_total")),
            )
        )

    return (
        Invoice(
            invoice_id=str(payload.get("invoice_number") or payload.get("invoice_id") or "UNKNOWN"),
            vendor=str(vendor or "UNKNOWN").strip(),
            amount=_to_float(payload.get("total")) or 0.0,
            currency=str(payload.get("currency") or "").strip() or None,
            due_date=_normalize_date(payload.get("due_date")),
            items=items,
            notes=_extract_notes(payload),
            suspicious_flags=[],
            missing_fields=[],
            parsing_confidence=0.0,
            source_path=str(path),
            raw_text=None,
        ),
        raw_text,
    )


def _parse_csv(path: Path) -> Tuple[Invoice, str]:
    raw_text = path.read_text(encoding="utf-8")
    rows = list(csv.reader(raw_text.splitlines()))
    if not rows:
        return _empty_invoice(path, raw_text)

    header = [cell.strip().lower() for cell in rows[0]]
    if header[:2] == ["field", "value"]:
        return _parse_kv_csv(rows, path, raw_text)
    return _parse_table_csv(rows, path, raw_text)


def _parse_kv_csv(rows: List[List[str]], path: Path, raw_text: str) -> Tuple[Invoice, str]:
    invoice_id = "UNKNOWN"
    vendor = "UNKNOWN"
    due_date = None
    amount = 0.0
    items: List[InvoiceItem] = []
    pending_item: Dict[str, Any] = {}

    for row in rows[1:]:
        if len(row) < 2:
            continue
        key = row[0].strip().lower()
        value = row[1].strip()
        if key in {"invoice_number", "invoice"}:
            invoice_id = value or invoice_id
        elif key == "vendor":
            vendor = value or vendor
        elif key in {"due_date", "due"}:
            due_date = _normalize_date(value)
        elif key in {"total", "total_amount"}:
            amount = _to_float(value) or amount
        elif key == "item":
            if pending_item:
                items.append(_build_item(pending_item))
            pending_item = {"name": value}
        elif key == "quantity":
            pending_item["quantity"] = value
        elif key in {"unit_price", "unit price"}:
            pending_item["unit_price"] = value

    if pending_item:
        items.append(_build_item(pending_item))

    return (
        Invoice(
            invoice_id=invoice_id,
            vendor=vendor,
            amount=amount,
            currency=None,
            due_date=due_date,
            items=items,
            notes=None,
            suspicious_flags=[],
            missing_fields=[],
            parsing_confidence=0.0,
            source_path=str(path),
            raw_text=None,
        ),
        raw_text,
    )


def _parse_table_csv(rows: List[List[str]], path: Path, raw_text: str) -> Tuple[Invoice, str]:
    header = [cell.strip().lower() for cell in rows[0]]
    idx = {name: header.index(name) for name in header if name}

    invoice_id = "UNKNOWN"
    vendor = "UNKNOWN"
    due_date = None
    amount = 0.0
    items: List[InvoiceItem] = []

    for row in rows[1:]:
        if len(row) < len(header):
            continue
        first_cell = row[0].strip()
        if not first_cell:
            # Totals row
            if len(row) >= 2 and "total" in row[-2].lower():
                amount = _to_float(row[-1]) or amount
            continue
        invoice_id = row[idx.get("invoice number", 0)] or invoice_id
        vendor = row[idx.get("vendor", 1)] or vendor
        due_date = _normalize_date(row[idx.get("due date", 3)])
        item_name = row[idx.get("item", 4)]
        qty = row[idx.get("qty", 5)]
        unit_price = row[idx.get("unit price", 6)]
        line_total = None
        if "line total" in idx and idx.get("line total") is not None:
            line_total = _to_float(row[idx["line total"]])
        items.append(
            InvoiceItem(
                item_name=str(item_name).strip(),
                quantity=int(float(qty)) if str(qty).strip() else 0,
                unit_price=_to_float(unit_price),
                line_total=line_total,
            )
        )

    return (
        Invoice(
            invoice_id=invoice_id,
            vendor=vendor,
            amount=amount,
            currency=None,
            due_date=due_date,
            items=items,
            notes=None,
            suspicious_flags=[],
            missing_fields=[],
            parsing_confidence=0.0,
            source_path=str(path),
            raw_text=None,
        ),
        raw_text,
    )


def _parse_xml(path: Path) -> Tuple[Invoice, str]:
    raw_text = path.read_text(encoding="utf-8")
    root = ElementTree.fromstring(raw_text)
    header = root.find("header")

    invoice_id = _text_or_default(header, "invoice_number", "UNKNOWN")
    vendor = _text_or_default(header, "vendor", "UNKNOWN")
    due_date = _normalize_date(_text_or_default(header, "due_date", None))
    total = _to_float(_text_or_default(root.find("totals"), "total", None)) or 0.0

    items: List[InvoiceItem] = []
    for item in root.findall(".//line_items/item"):
        name = _text_or_default(item, "name", "")
        quantity = int(float(_text_or_default(item, "quantity", "0") or 0))
        unit_price = _to_float(_text_or_default(item, "unit_price", None))
        items.append(InvoiceItem(item_name=name, quantity=quantity, unit_price=unit_price))

    return (
        Invoice(
            invoice_id=invoice_id,
            vendor=vendor,
            amount=total,
            currency=_text_or_default(header, "currency", None),
            due_date=due_date,
            items=items,
            notes=None,
            suspicious_flags=[],
            missing_fields=[],
            parsing_confidence=0.0,
            source_path=str(path),
            raw_text=None,
        ),
        raw_text,
    )


def _parse_pdf(path: Path) -> Tuple[Invoice, str]:
    text = _extract_pdf_text(path)
    if not text:
        sibling_txt = path.with_suffix(".txt")
        if sibling_txt.exists():
            return _parse_text(sibling_txt)
        return _empty_invoice(path, "")
    invoice, _ = _parse_text_from_string(text, path)
    return invoice, text


def _parse_text(path: Path) -> Tuple[Invoice, str]:
    raw_text = path.read_text(encoding="utf-8")
    invoice, _ = _parse_text_from_string(raw_text, path)
    return invoice, raw_text


def _parse_text_from_string(raw_text: str, path: Path) -> Tuple[Invoice, str]:
    invoice_id = _find_first(
        raw_text,
        [
            r"Invoice Number:\s*([A-Z0-9-]+)",
            r"Invoice:\s*([A-Z0-9-]+)",
            r"INV[-#]?\s*([0-9]{4})",
            r"Inv #:\s*([A-Z0-9-]+)",
        ],
    )
    if invoice_id and not invoice_id.startswith("INV-") and invoice_id.isdigit():
        invoice_id = f"INV-{invoice_id}"

    vendor = _find_first(
        raw_text,
        [
            r"Vendor:\s*([^\n\r]+)",
            r"Vndr:\s*([^\n\r]+)",
            r"From:\s*([^\n\r]+)",
        ],
    )
    vendor = vendor.strip() if vendor else "UNKNOWN"

    due_date = _find_first(
        raw_text,
        [
            r"Due Date:\s*([^\n\r]+)",
            r"Due Dt:\s*([^\n\r]+)",
            r"Due:\s*([^\n\r]+)",
        ],
    )
    due_date = _normalize_date(due_date)

    amount = _find_first(
        raw_text,
        [
            r"Total Amount:\s*\$?([0-9,]+\.\d{2})",
            r"Total:\s*\$?([0-9,]+\.\d{2})",
            r"TOTAL:\s*\$?([0-9,]+\.\d{2})",
            r"Amt:\s*\$?([0-9,]+\.\d{2})",
        ],
    )
    amount = _to_float(amount) or 0.0

    items = _parse_items_from_text(raw_text)

    return (
        Invoice(
            invoice_id=invoice_id or "UNKNOWN",
            vendor=vendor,
            amount=amount,
            currency=_detect_currency(raw_text),
            due_date=due_date,
            items=items,
            notes=_extract_notes_from_text(raw_text),
            suspicious_flags=[],
            missing_fields=[],
            parsing_confidence=0.0,
            source_path=str(path),
            raw_text=None,
        ),
        raw_text,
    )


def _maybe_llm_extract(raw_text: str, path: Path) -> Optional[Invoice]:
    prompt = (
        "Extract the invoice into strict JSON only. "
        "Schema: {invoice_id, vendor, amount, currency, due_date, items:[{item_name, quantity, unit_price, line_total}], "
        "notes, suspicious_flags, missing_fields, parsing_confidence}.\n"
        "Use null for unknown values. Numbers must be numeric, not strings.\n\n"
        f"INVOICE TEXT:\n{raw_text}"
    )

    content = _try_grok(prompt)
    if not content:
        return None

    payload = _extract_json(content)
    if not isinstance(payload, dict):
        return None

    items_payload = payload.get("items") or []
    items = []
    for item in items_payload:
        if not isinstance(item, dict):
            continue
        items.append(
            InvoiceItem(
                item_name=str(item.get("item_name") or item.get("name") or "").strip(),
                quantity=int(float(item.get("quantity") or 0)),
                unit_price=_to_float(item.get("unit_price")),
                line_total=_to_float(item.get("line_total")),
            )
        )

    return Invoice(
        invoice_id=str(payload.get("invoice_id") or "UNKNOWN"),
        vendor=str(payload.get("vendor") or "UNKNOWN"),
        amount=_to_float(payload.get("amount")) or 0.0,
        currency=str(payload.get("currency") or "").strip() or None,
        due_date=_normalize_date(payload.get("due_date")),
        items=items,
        notes=str(payload.get("notes") or "").strip() or None,
        suspicious_flags=payload.get("suspicious_flags") or [],
        missing_fields=payload.get("missing_fields") or [],
        parsing_confidence=float(payload.get("parsing_confidence") or 0.0),
        source_path=str(path),
        raw_text=None,
    )




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


def _extract_json(content: str) -> Optional[Dict[str, Any]]:
    if not content:
        return None
    content = content.strip()
    if content.startswith("{") and content.endswith("}"):
        try:
            return json.loads(content)
        except Exception:
            pass
    match = re.search(r"\{.*\}", content, flags=re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except Exception:
        return None


def _parse_items_from_text(raw_text: str) -> List[InvoiceItem]:
    items: List[InvoiceItem] = []
    price = r"[0-9,]+(?:\.\d{2})?"
    patterns = [
        # WidgetA qty: 10 unit price: $250.00
        rf"^\s*([A-Za-z0-9() .-]+?)\s+qty[:\s]+(\d+)\s+unit price[:\s]+\$?({price})",
        # GadgetX qty 20 @ $750 ea / each
        rf"^\s*([A-Za-z0-9() .-]+?)\s+qty\s+(\d+)\s+@\s*\$?({price})(?:\s*(?:ea|each))?",
        # - SuperGizmo x12 $400.00 each
        rf"^\s*-\s*([A-Za-z0-9() .-]+?)\s+x(\d+)\s+\$?({price})(?:\s*(?:ea|each))?",
        # Table rows: Item Qty UnitPrice LineTotal
        rf"^\s*([A-Za-z0-9() .-]+?)\s+(\d+)\s+\$?({price})\s+\$?({price})",
        # Item: GadgetX, qty: 20, price: $750.00
        rf"^\s*([A-Za-z0-9() .-]+?)\s*[,;]\s*qty[:\s]+(\d+)\s*[,;]\s*(?:price|unit price)[:\s]+\$?({price})",
    ]
    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.lower().startswith(("subtotal", "tax", "total", "amount")):
            continue
        for pattern in patterns:
            match = re.search(pattern, line, flags=re.IGNORECASE)
            if not match:
                continue
            name = match.group(1).strip()
            qty = int(match.group(2))
            unit_price = _to_float(match.group(3))
            line_total = _to_float(match.group(4)) if match.lastindex and match.lastindex >= 4 else None
            items.append(
                InvoiceItem(
                    item_name=name,
                    quantity=qty,
                    unit_price=unit_price,
                    line_total=line_total,
                )
            )
            break
    if items:
        return items

    # Fallback: scan entire text for item patterns if line-by-line failed.
    fallback_patterns = [
        rf"([A-Za-z0-9() .-]+?)\s+qty[:\s]+(\d+)\s+unit price[:\s]+\$?({price})",
        rf"([A-Za-z0-9() .-]+?)\s+qty\s+(\d+)\s+@\s*\$?({price})(?:\s*(?:ea|each))?",
        rf"-\s*([A-Za-z0-9() .-]+?)\s+x(\d+)\s+\$?({price})(?:\s*(?:ea|each))?",
    ]
    for pattern in fallback_patterns:
        for match in re.finditer(pattern, raw_text, flags=re.IGNORECASE):
            name = match.group(1).strip()
            qty = int(match.group(2))
            unit_price = _to_float(match.group(3))
            items.append(
                InvoiceItem(
                    item_name=name,
                    quantity=qty,
                    unit_price=unit_price,
                )
            )

    return items


def _extract_pdf_text(path: Path) -> str:
    try:
        import fitz  # type: ignore

        doc = fitz.open(path)
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        return text
    except Exception:
        pass

    try:
        import pdfplumber  # type: ignore

        with pdfplumber.open(path) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception:
        return ""


def _normalize_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    lower = cleaned.lower()
    today = datetime.now()
    if lower in {"today", "tod"}:
        return today.date().isoformat()
    if lower in {"yesterday", "yday"}:
        return (today.date() - timedelta(days=1)).isoformat()

    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y"):
        try:
            return datetime.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            continue
    return cleaned


def _find_first(text: str, patterns: List[str]) -> Optional[str]:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).strip().replace("$", "").replace(",", "")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _text_or_default(parent: Optional[ElementTree.Element], tag: str, default: Optional[str]) -> Optional[str]:
    if parent is None:
        return default
    node = parent.find(tag)
    if node is None or node.text is None:
        return default
    return node.text.strip()


def _build_item(payload: Dict[str, Any]) -> InvoiceItem:
    return InvoiceItem(
        item_name=str(payload.get("name") or payload.get("item") or "").strip(),
        quantity=int(float(payload.get("quantity") or 0)),
        unit_price=_to_float(payload.get("unit_price")),
    )


def _backfill_amount(invoice: Invoice) -> None:
    if invoice.amount > 0 or not invoice.items:
        return
    total = 0.0
    for item in invoice.items:
        if item.unit_price is None:
            continue
        total += item.quantity * item.unit_price
    if total > 0:
        invoice.amount = round(total, 2)


def _empty_invoice(path: Path, raw_text: str) -> Tuple[Invoice, str]:
    return (
        Invoice(
            invoice_id="UNKNOWN",
            vendor="UNKNOWN",
            amount=0.0,
            currency=None,
            due_date=None,
            items=[],
            notes=None,
            suspicious_flags=[],
            missing_fields=[],
            parsing_confidence=0.0,
            source_path=str(path),
            raw_text=None,
        ),
        raw_text,
    )


def _postprocess_invoice(invoice: Invoice) -> None:
    missing = []
    if not invoice.invoice_id or invoice.invoice_id == "UNKNOWN":
        missing.append("invoice_id")
    if not invoice.vendor or invoice.vendor == "UNKNOWN":
        missing.append("vendor")
    if invoice.amount <= 0:
        missing.append("amount")
    if not invoice.due_date:
        missing.append("due_date")
    if not invoice.items:
        missing.append("items")
    invoice.missing_fields = missing

    suspicious = []
    if invoice.amount <= 0:
        suspicious.append("non_positive_total")
    raw = (invoice.raw_text or "").lower()
    if "urgent" in raw or "wire transfer" in raw:
        suspicious.append("urgent_or_wire")
    for item in invoice.items:
        if item.quantity <= 0:
            suspicious.append(f"non_positive_quantity:{item.item_name}")
        if item.item_name and any(token in item.item_name.lower() for token in ["fake", "fraud", "scam"]):
            suspicious.append(f"suspicious_item:{item.item_name}")
    fraud_flags = evaluate_fraud(invoice)
    invoice.suspicious_flags = sorted(set(suspicious + fraud_flags))
    record_invoice(invoice)

    invoice.parsing_confidence = _estimate_confidence(invoice)


def _estimate_confidence(invoice: Invoice) -> float:
    total_fields = 5
    filled = 0
    if invoice.invoice_id and invoice.invoice_id != "UNKNOWN":
        filled += 1
    if invoice.vendor and invoice.vendor != "UNKNOWN":
        filled += 1
    if invoice.amount > 0:
        filled += 1
    if invoice.due_date:
        filled += 1
    if invoice.items:
        filled += 1
    return round(filled / total_fields, 2)


def _detect_currency(text: str) -> Optional[str]:
    lowered = text.lower()
    if " usd" in lowered or "$" in text:
        return "USD"
    if " eur" in lowered or "€" in text:
        return "EUR"
    if " gbp" in lowered or "£" in text:
        return "GBP"
    return None


def _extract_notes(payload: Dict[str, Any]) -> Optional[str]:
    notes = []
    payment_terms = payload.get("payment_terms")
    if payment_terms:
        notes.append(f"Payment terms: {payment_terms}")
    extra = payload.get("notes")
    if extra:
        notes.append(str(extra))
    return "; ".join(notes) if notes else None


def _extract_notes_from_text(text: str) -> Optional[str]:
    lines = []
    for line in text.splitlines():
        if line.lower().startswith(("notes:", "note:", "payment terms")):
            lines.append(line.strip())
        if "urgent" in line.lower():
            lines.append(line.strip())
    return "; ".join(lines) if lines else None
