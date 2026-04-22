# Invoice Processing Automation

## Project Overview

This system automates invoice handling with a multi-agent workflow.  
It ingests invoice files, validates extracted data against a local inventory database, applies approval logic, and simulates payment.

## Problem Context

Manual invoice workflows can be slow and error-prone, especially when files come in inconsistent formats.  
This repository provides a local prototype for improving processing speed, consistency, and auditability.

## Workflow

The pipeline runs in four stages:

1. `Ingestion`  
   Extract structured fields from invoices (PDF/TXT/CSV/JSON), including vendor, amount, due date, and line items.

2. `Validation`  
   Validate extracted items and quantities against a SQLite inventory database.  
   Flag unknown items, insufficient stock, and invalid values.

3. `Approval`  
   Apply rule-based approval logic (for example, extra checks on higher-value invoices).

4. `Payment`  
   Simulate payment for approved invoices, or log rejection reasons for declined invoices.

## Technical Approach

- `Language`: Python
- `Architecture`: Multi-agent orchestration (framework-based or custom)
- `LLM`: xAI Grok (or another compatible model)
- `Execution`: Local runtime with mocked external dependencies

## Project Data

Sample invoices are available in `data/invoices/` and include both clean and problematic cases for testing.

## Requirements

- Python 3.10+
- Dependencies listed in `requirements.txt`

Install dependencies:

```bash
pip install -r requirements.txt
```

## Database Setup

Create and seed the local SQLite database used during validation:

```python
import sqlite3

conn = sqlite3.connect("inventory.db")
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS inventory (item TEXT PRIMARY KEY, stock INTEGER)")
cursor.execute("""
    INSERT INTO inventory VALUES
    ('WidgetA', 15),
    ('WidgetB', 10),
    ('GadgetX', 5),
    ('FakeItem', 0)
""")
conn.commit()
conn.close()
```

You can extend this schema with fields such as unit price, category, or vendor metadata if needed.

## Mock Payment Function

```python
def mock_payment(vendor, amount):
    print(f"Paid {amount} to {vendor}")
    return {"status": "success"}
```

## Grok API Example

```python
from xai import Grok

client = Grok(api_key="your_key")
response = client.chat.completions.create(
    model="grok-3",
    messages=[{"role": "user", "content": "Reason about this..."}]
)
```

## Execute

Run the processor for a specific invoice:

```bash
python main.py --invoice_path=data/invoices/invoice1.txt
```

The command outputs processing logs and the final status for the invoice.
