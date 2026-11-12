from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from spreadsheet_operations import summarize_sales


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--sheet", default="数据透视表")
    parser.add_argument("--region")
    parser.add_argument("--output", default="outputs/sales_summary.json")
    args = parser.parse_args()
    result = summarize_sales(pd.read_excel(args.input, sheet_name=args.sheet), args.region)
    payload = {
        "experiment": "BA-CH02-15",
        "salesperson_count": int(len(result["by_person"])),
        "product_count": int(len(result["by_product"])),
        "quantity_total": float(result["by_product"]["数量总计"].sum()),
        "sales_total": float(result["by_product"]["销售金额总计"].sum()),
    }
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

