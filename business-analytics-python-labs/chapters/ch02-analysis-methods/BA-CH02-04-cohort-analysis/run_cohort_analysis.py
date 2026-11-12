from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from cohort_analysis import compute_cohort_analysis, plot_retention


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--sheet", default="用户登录明细")
    parser.add_argument("--output", default="outputs/cohort_summary.json")
    parser.add_argument("--chart", default="outputs/cohort_retention.png")
    args = parser.parse_args()
    result = compute_cohort_analysis(pd.read_excel(args.input, sheet_name=args.sheet))
    matrix = result["retention_matrix"]
    payload = {"experiment": "BA-CH02-04", "cohort_count": int(len(matrix)), "max_day": int(max(matrix.columns)), "privacy": "aggregate-only output"}
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    chart = Path(args.chart); chart.parent.mkdir(parents=True, exist_ok=True)
    plot_retention(matrix).savefig(chart, dpi=150)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

