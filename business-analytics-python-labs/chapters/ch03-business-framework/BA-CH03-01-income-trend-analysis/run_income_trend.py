from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from income_trend import analyze_income, plot_yearly_income


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--sheet", default="原始数据")
    parser.add_argument("--base-year", type=int, required=True)
    parser.add_argument("--comparison-year", type=int, required=True)
    parser.add_argument("--focus-month", type=int, default=11)
    parser.add_argument("--focus-province", default="四川")
    parser.add_argument("--output", default="outputs/income_summary.json")
    parser.add_argument("--chart", default="outputs/yearly_income.png")
    args = parser.parse_args()
    result = analyze_income(pd.read_excel(args.input, sheet_name=args.sheet), args.base_year, args.comparison_year, args.focus_month, args.focus_province)
    yearly = result["yearly"]
    payload = {"experiment": "BA-CH03-01", "year_count": int(len(yearly)), "comparison_year_total": float(yearly.get(args.comparison_year, 0)), "growth_convention": "(comparison-base)/comparison"}
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    chart = Path(args.chart); chart.parent.mkdir(parents=True, exist_ok=True)
    plot_yearly_income(yearly).savefig(chart, dpi=150)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

