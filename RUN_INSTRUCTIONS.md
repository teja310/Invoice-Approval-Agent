# Run Instructions

Here’s the quickest way to get this running locally.

## What you need

- Python 3.10+
- An xAI/Grok API key if you want LLM-powered extraction (optional)

## Setup

1. Create a virtual environment and activate it.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install the dependencies.

```powershell
pip install -r requirements.txt
```

3. (Optional) Add your Grok credentials.

Create `llm.env` in the repo root:

```env
XAI_API_KEY="your_key_here"
XAI_MODEL="grok-3"
# XAI_BASE_URL="https://api.x.ai/v1/chat/completions"
```

If `XAI_API_KEY` isn’t set, the pipeline still runs — it just uses non‑LLM heuristics.

4. Inventory DB

You don’t need to do anything here: if `inventory.db` doesn’t exist, it’s created automatically with seed data the first time you run the pipeline. If you want a custom DB, pass `--db_path`.

## Run from the CLI

```powershell
python main.py --invoice_path=data/invoices/invoice1.txt
```

With a custom DB:

```powershell
python main.py --invoice_path=data/invoices/invoice1.txt --db_path=inventory.db
```

## Run the UI

```powershell
streamlit run streamlit_app.py
```

Open the local URL shown in the terminal, choose a sample invoice (or upload your own), and click “Run Pipeline”.
