from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from funnel_analysis import compute_funnel, plot_funnel


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--sheet", default=0)
    parser.add_argument("--stage-column", default="阶段")
    parser.add_argument("--count-column", default="用户数")
    parser.add_argument("--output", default="outputs/funnel_summary.json")
    parser.add_argument("--chart", default="outputs/funnel.png")
    args = parser.parse_args()
    result = compute_funnel(pd.read_excel(args.input, sheet_name=args.sheet), args.stage_column, args.count_column)
    payload = {"experiment": "BA-CH02-05", "stage_count": int(len(result)), "final_conversion": float(result["overall_conversion"].iloc[-1])}
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    chart = Path(args.chart); chart.parent.mkdir(parents=True, exist_ok=True)
    plot_funnel(result).savefig(chart, dpi=150)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

