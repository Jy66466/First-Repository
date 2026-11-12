from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from etl_clean_merge import (
    clean_order_details,
    horizontal_merge,
    split_delimited_column,
    split_quantity_column,
    vertical_concat,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="BA-CH02-18 ETL 清洗、拆分与合并演示")
    parser.add_argument("--input", required=True, help="订单明细工作簿（已获授权的本地副本）")
    parser.add_argument("--sheet", default=0)
    parser.add_argument("--header-row", type=int, default=1, help="字段名所在行号（0 起）")
    parser.add_argument("--output", default="outputs/etl_summary.json")
    args = parser.parse_args()

    raw = pd.read_excel(args.input, sheet_name=args.sheet, header=args.header_row)
    cleaned = clean_order_details(raw)
    summary = {
        "experiment": "BA-CH02-18",
        "input_rows": int(len(raw)),
        "cleaned_rows": int(len(cleaned)),
        "amount_sum": float(cleaned["实付金额"].sum()) if "实付金额" in cleaned.columns else None,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
