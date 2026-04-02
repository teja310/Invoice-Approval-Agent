# Invoice Agent Overview

## What We Built
- End-to-end invoice workflow: ingestion → validation → approval → payment.
- LangGraph orchestration for the multi-agent pipeline.
- Multi-format parsing: TXT, JSON, CSV, XML, PDF.
- Structured output schema with validation + approval results.
- Fraud detection with configurable risky vendors and duplicate detection.
- Streamlit UI for live, readable workflow output.
- LLM integration (Grok via REST) for extraction and decision reasoning.
- Human-readable CLI logging.

## How The Agent Works

### 1) Ingestion
- Detects file type and extracts raw text.
- Parses fields:
  - `invoice_id`, `vendor`, `amount`, `currency`, `due_date`
  - `items` (item_name, quantity, unit_price, line_total)
  - `notes`, `missing_fields`, `suspicious_flags`, `parsing_confidence`
- If `XAI_API_KEY` is set, Grok is used to extract and **refine**.
- Guardrails prevent LLM output from dropping critical fields.

### 2) Validation
- Validates items against `inventory.db`.
- Flags:
  - `unknown_item`, `out_of_stock`, `stock_exceeded`
  - `invalid_quantity`, `amount_mismatch`
  - `suspicious_flags` from ingestion
- Returns:
  - `status`: `pass` / `review` / `fail`
  - `status_reason`
  - list of issues
- Hard-fail rule: if all essential fields are missing, mark as `not_an_invoice`.

### 3) Approval
- `fail` → Reject
- `review` → Manual Review
- `pass` → Approve unless high-risk flags
- Reflection step checks for urgency/wire-transfer signals.

### 4) Payment
- Approved → mock payment
- Not approved → skipped

## Fraud Detection
- `high_total` for large amounts
- risky vendors (configurable)
- duplicate invoice detection (`data/fraud_seen.jsonl`)
- urgent/wire-transfer language
- suspicious item names (fake/fraud/scam)

## Streamlit UI
- Shows original invoice → extracted details → decision panel → LLM reason.
- Live progress and readable outputs.
- Button to clear duplicate history.

## Key Files
- `main.py`: CLI entrypoint
- `agents/langgraph_flow.py`: LangGraph orchestration
- `agents/ingestion.py`: parsing + LLM extraction + post-processing
- `agents/validation.py`: inventory checks + review/fail rules
- `agents/approval.py`: decision logic + reflection
- `agents/payment.py`: mock payment
- `schema.py`: dataclasses for all structures
- `utils/fraud.py`: fraud rules + risky vendor list
- `utils/logging.py`: human-readable logs
- `utils/schemas.py`: pydantic schema validation
- `utils/llm_reason.py`: LLM decision reasoning
- `streamlit_app.py`: UI

## Configuration
- `llm.env` (root or `agents/`) with:
  - `XAI_API_KEY="..."`  
  - `XAI_MODEL="grok-3"` (optional)
  - `XAI_BASE_URL` (optional, default `https://api.x.ai/v1/chat/completions`)

## Notes
- PDF parsing uses `pymupdf` / `pdfplumber` (text-based PDFs only).
- OCR fallback is not included yet.
- Generated files ignored by git via `.gitignore`.
