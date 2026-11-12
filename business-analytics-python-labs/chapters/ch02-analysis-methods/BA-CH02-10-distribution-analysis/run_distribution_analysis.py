from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from distribution_analysis import plot_distribution, summarize_distribution


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--sheet", default=0)
    parser.add_argument("--column", required=True)
    parser.add_argument("--output", default="outputs/distribution_summary.json")
    parser.add_argument("--chart", default="outputs/distribution.png")
    args = parser.parse_args()
    values = pd.read_excel(args.input, sheet_name=args.sheet)[args.column]
    summary = {"experiment": "BA-CH02-10", **summarize_distribution(values)}
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    chart = Path(args.chart); chart.parent.mkdir(parents=True, exist_ok=True)
    plot_distribution(values).savefig(chart, dpi=150)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

