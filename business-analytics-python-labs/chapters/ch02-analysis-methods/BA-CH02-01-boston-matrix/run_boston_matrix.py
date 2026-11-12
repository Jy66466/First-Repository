"""Run BA-CH02-01 without installing the package."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from boston_matrix import compute_boston_matrix, plot_boston_matrix


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--sheet", default="销售表")
    parser.add_argument("--base-period", required=True, help="YYYY-MM")
    parser.add_argument("--comparison-period", required=True, help="YYYY-MM")
    parser.add_argument("--output", default="outputs/boston_summary.json")
    parser.add_argument("--chart", default="outputs/boston_matrix.png")
    args = parser.parse_args()
    result = compute_boston_matrix(pd.read_excel(args.input, sheet_name=args.sheet), args.base_period, args.comparison_period)
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "experiment": "BA-CH02-01",
        "brand_count": int(len(result)),
        "category_counts": {str(k): int(v) for k, v in result["category"].value_counts().items()},
        "privacy": "aggregate-only output",
    }
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    chart = Path(args.chart); chart.parent.mkdir(parents=True, exist_ok=True)
    plot_boston_matrix(result).savefig(chart, dpi=150)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

