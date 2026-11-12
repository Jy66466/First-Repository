from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from customer_loyalty import analyze_customer_loyalty


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--sheet", default="销售流水表")
    parser.add_argument("--analysis-date", required=True)
    parser.add_argument("--output", default="outputs/loyalty_summary.json")
    args = parser.parse_args()
    result = analyze_customer_loyalty(pd.read_excel(args.input, sheet_name=args.sheet), args.analysis_date)
    customers = result["customers"]; scores = result["eligible_scores"]
    payload = {
        "experiment": "BA-CH02-03",
        "customer_count": int(len(customers)),
        "special_status_counts": {str(k): int(v) for k, v in customers["special_status"].value_counts().items()},
        "loyalty_segment_counts": {str(k): int(v) for k, v in scores["loyalty_segment"].value_counts().items()},
        "thresholds": result["thresholds"],
        "privacy": "aggregate-only output",
    }
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

