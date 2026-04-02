from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Iterable
from datetime import datetime, timezone
from typing import Any, Dict


def log_event(stage: str, payload: Dict[str, Any], level: str = "INFO") -> None:
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "stage": stage,
        "payload": payload,
    }
    header = f"[{event['ts']}] [{event['level']}] [{event['stage'].upper()}]"
    print(header)
    _print_payload(event["payload"])


def _print_payload(payload: Dict[str, Any]) -> None:
    if "invoice" in payload:
        _print_invoice(payload["invoice"])
        return
    if "result" in payload:
        _print_result(payload["result"])
        return
    print(payload)


def _print_invoice(invoice: Any) -> None:
    data = _to_dict(invoice)
    print("Invoice Summary")
    print(f"- Invoice ID: {data.get('invoice_id')}")
    print(f"- Vendor: {data.get('vendor')}")
    print(f"- Amount: {data.get('amount')} {data.get('currency') or ''}".strip())
    print(f"- Due Date: {data.get('due_date')}")
    print(f"- Parsing Confidence: {data.get('parsing_confidence')}")
    if data.get("missing_fields"):
        print(f"- Missing Fields: {', '.join(data.get('missing_fields') or [])}")
    if data.get("suspicious_flags"):
        print(f"- Suspicious Flags: {', '.join(data.get('suspicious_flags') or [])}")
    if data.get("notes"):
        print(f"- Notes: {data.get('notes')}")
    items = data.get("items") or []
    if items:
        print("Items")
        for item in items:
            item_data = _to_dict(item)
            line_total = item_data.get("line_total")
            line_total_str = f", line_total={line_total}" if line_total is not None else ""
            print(
                f"- {item_data.get('item_name')}: qty={item_data.get('quantity')}, "
                f"unit_price={item_data.get('unit_price')}{line_total_str}"
            )


def _print_result(result: Any) -> None:
    data = _to_dict(result)
    if "status" in data and "issues" in data:
        print("Validation Result")
        print(f"- Status: {data.get('status')}")
        if data.get("status_reason"):
            print(f"- Reason: {data.get('status_reason')}")
        issues = data.get("issues") or []
        if issues:
            print("Issues")
            for issue in issues:
                issue_data = _to_dict(issue)
                item = issue_data.get("item")
                item_str = f" ({item})" if item else ""
                print(f"- {issue_data.get('issue_type')}{item_str}: {issue_data.get('detail')}")
        return
    if "approved" in data and "reason" in data:
        print("Approval Result")
        print(f"- Approved: {data.get('approved')}")
        print(f"- Reason: {data.get('reason')}")
        print(f"- Confidence: {data.get('confidence')}")
        return
    if "status" in data and "detail" in data:
        print("Payment Result")
        print(f"- Status: {data.get('status')}")
        print(f"- Detail: {data.get('detail')}")
        return
    print(data)


def _to_dict(value: Any) -> Dict[str, Any]:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return value
    return {"value": value}
