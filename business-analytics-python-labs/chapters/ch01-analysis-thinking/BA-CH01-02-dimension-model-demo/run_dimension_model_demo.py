from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from dimension_model_demo import (
    aggregate_sales,
    load_star_schema,
    validate_fact_against_dimensions,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="BA-CH01-02 维度模型演示")
    parser.add_argument("--fact", required=True, help="产品销售数据表工作簿（已授权副本）")
    parser.add_argument("--product", required=True, help="产品信息表工作簿")
    parser.add_argument("--output", default="outputs/dimension_model_summary.json")
    args = parser.parse_args()

    fact = pd.read_excel(args.fact)
    product = pd.read_excel(args.product)
    schema = load_star_schema(fact, product)
    validation = validate_fact_against_dimensions(schema)
    by_brand = aggregate_sales(schema, "品牌名称")
    summary = {
        "experiment": "BA-CH01-02",
        **validation,
        "brand_sales": {
            str(r["品牌名称"]): {"数量": float(r["销售数量"]), "销售额": float(r["销售额"])}
            for r in by_brand.to_dict("records")
        },
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
