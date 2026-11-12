from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from sankey_flow import node_flow_summary, node_levels, validate_edges


def main() -> int:
    parser = argparse.ArgumentParser(description="BA-CH02-12 桑基图流数据演示")
    parser.add_argument("--input", required=True, help="含 来源/目标/流量 列的 CSV 或 Excel（已授权副本）")
    parser.add_argument("--sheet", default=0)
    parser.add_argument("--output", default="outputs/sankey_flow_summary.json")
    args = parser.parse_args()

    frame = (
        pd.read_csv(args.input)
        if str(args.input).lower().endswith("csv")
        else pd.read_excel(args.input, sheet_name=args.sheet)
    )
    edges = frame.rename(columns=str.strip)
    from sankey_flow import load_flow_edges

    edges = load_flow_edges(edges)
    summary = {
        "experiment": "BA-CH02-12",
        **validate_edges(edges),
        "nodes": {k: int(v) for k, v in node_levels(edges).items()},
        "flow_summary": node_flow_summary(edges).to_dict("records"),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
