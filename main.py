from __future__ import annotations

import argparse



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Invoice processing pipeline")
    parser.add_argument(
        "--invoice_path",
        required=True,
        help="Path to invoice file (txt, json, csv, pdf, xml).",
    )
    parser.add_argument(
        "--db_path",
        default="inventory.db",
        help="Path to inventory sqlite db.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    from agents.langgraph_flow import run_langgraph

    run_langgraph(args.invoice_path, args.db_path)


if __name__ == "__main__":
    main()
