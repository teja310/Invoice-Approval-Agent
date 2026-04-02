from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from agents.approval import approve_invoice
from agents.ingestion import extract_invoice
from agents.payment import process_payment
from agents.validation import validate_invoice
from schema import to_dict
from utils.fraud import STATE_PATH
from utils.llm_reason import generate_reason


def _run_pipeline_live(invoice_path: str, db_path: str):
    status = st.empty()
    progress = st.progress(0)

    status.info("Step 1/4: Ingesting invoice...")
    invoice = extract_invoice(invoice_path)
    progress.progress(25)

    status.info("Step 2/4: Validating against inventory...")
    validation = validate_invoice(invoice, db_path)
    progress.progress(50)

    status.info("Step 3/4: Approval decision...")
    approval = approve_invoice(invoice, validation)
    progress.progress(75)

    status.info("Step 4/4: Payment step...")
    payment = process_payment(invoice, approval)
    progress.progress(100)
    status.success("Pipeline completed.")

    return invoice, validation, approval, payment


def _list_sample_invoices() -> list[str]:
    invoices_dir = Path("data/invoices")
    if not invoices_dir.exists():
        return []
    return sorted(str(p) for p in invoices_dir.iterdir() if p.is_file())


def main() -> None:
    st.set_page_config(page_title="Invoice Agent Console", layout="wide")
    st.title("Invoice Agent Console")

    st.sidebar.header("Input")
    db_path = st.sidebar.text_input("Inventory DB Path", value="inventory.db")
    if st.sidebar.button("Clear Duplicate History"):
        if STATE_PATH.exists():
            STATE_PATH.unlink(missing_ok=True)
            st.sidebar.success("Duplicate history cleared.")
        else:
            st.sidebar.info("No duplicate history to clear.")

    sample_files = _list_sample_invoices()
    sample_choice = st.sidebar.selectbox("Sample Invoice", ["(none)"] + sample_files)

    uploaded = st.sidebar.file_uploader(
        "Upload Invoice (txt, json, csv, xml, pdf)", type=["txt", "json", "csv", "xml", "pdf"]
    )

    run = st.sidebar.button("Run Pipeline", type="primary")

    invoice_path = None
    temp_file = None

    if uploaded is not None:
        suffix = Path(uploaded.name).suffix or ".txt"
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        temp_file.write(uploaded.read())
        temp_file.close()
        invoice_path = temp_file.name
    elif sample_choice != "(none)":
        invoice_path = sample_choice

    if run:
        if not invoice_path:
            st.error("Please upload a file or choose a sample invoice.")
            return
        invoice, validation, approval, payment = _run_pipeline_live(invoice_path, db_path)

        st.markdown("---")
        st.subheader("Original Invoice")
        st.text(invoice.raw_text or "")

        st.markdown("---")
        st.subheader("Extracted Details")
        st.write(
            {
                "invoice_id": invoice.invoice_id,
                "vendor": invoice.vendor,
                "amount": invoice.amount,
                "currency": invoice.currency,
                "due_date": invoice.due_date,
                "parsing_confidence": invoice.parsing_confidence,
            }
        )
        if invoice.notes:
            st.markdown("Notes")
            st.write(invoice.notes)
        if invoice.missing_fields:
            st.info(f"Missing fields: {', '.join(invoice.missing_fields)}")
        if invoice.suspicious_flags:
            st.warning(f"Suspicious flags: {', '.join(invoice.suspicious_flags)}")

        st.subheader("Line Items")
        if invoice.items:
            st.dataframe([item.__dict__ for item in invoice.items], use_container_width=True)
        else:
            st.write("No line items extracted.")

        st.markdown("---")
        st.subheader("Decision Panel")
        action = "Approve" if approval.approved else "Manual Review" if validation.status == "review" else "Reject"
        if approval.approved:
            st.success(f"Action: {action}")
        elif validation.status == "review":
            st.warning(f"Action: {action}")
        else:
            st.error(f"Action: {action}")

        st.subheader("Decision Reason (LLM)")
        try:
            st.write(generate_reason(invoice, validation, approval))
        except Exception as exc:
            st.error(str(exc))

    if temp_file:
        Path(temp_file.name).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
