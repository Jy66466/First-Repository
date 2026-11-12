from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from precision_marketing import analyze_marketing, plot_counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--sheet", default="原始数据")
    parser.add_argument("--target-gender", default="Female")
    parser.add_argument("--target-age-band", default="50岁以上")
    parser.add_argument("--target-categories", nargs="+", default=["Clothing", "Cosmetics"])
    parser.add_argument("--output", default="outputs/marketing_summary.json")
    parser.add_argument("--chart", default="outputs/target_categories.png")
    args = parser.parse_args()
    result = analyze_marketing(pd.read_excel(args.input, sheet_name=args.sheet), args.target_gender, args.target_age_band, args.target_categories)
    payload = {
        "experiment": "BA-CH03-03",
        "gender_counts": {str(k): int(v) for k, v in result["gender_counts"].items()},
        "target_category_counts": {str(k): int(v) for k, v in result["category_counts"].items()},
        "target_payment_counts": {str(k): int(v) for k, v in result["payment_counts"].items()},
        "privacy": "aggregate-only output",
    }
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    chart = Path(args.chart); chart.parent.mkdir(parents=True, exist_ok=True)
    plot_counts(result["category_counts"], "Target customer categories").savefig(chart, dpi=150)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

