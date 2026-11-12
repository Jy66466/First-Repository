from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from sales_dashboard import (
    aggregate_profit_by_category,
    aggregate_sales_by_employee,
    aggregate_sales_by_province,
    aggregate_sales_by_year,
    load_star_schema,
    profit_summary,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="BA-CH02-17 分省销售分析核心演示")
    parser.add_argument("--orders", required=True, help="订单表 CSV（已授权本地副本）")
    parser.add_argument("--details", required=True, help="订单表明细表 CSV")
    parser.add_argument("--employees", required=True, help="雇员表 CSV")
    parser.add_argument("--products", required=True, help="商品表 CSV")
    parser.add_argument("--categories", required=True, help="商品类型表 CSV")
    parser.add_argument("--encoding-orders-details", default="gbk")
    parser.add_argument("--encoding-dims", default="utf-8-sig")
    parser.add_argument("--output", default="outputs/sales_dashboard_summary.json")
    args = parser.parse_args()

    orders = pd.read_csv(args.orders, encoding=args.encoding_orders_details)
    details = pd.read_csv(args.details, encoding=args.encoding_orders_details)
    employees = pd.read_csv(args.employees, encoding=args.encoding_dims)
    products = pd.read_csv(args.products, encoding=args.encoding_dims)
    categories = pd.read_csv(args.categories, encoding=args.encoding_dims)

    wide = load_star_schema(orders, details, employees, products, categories)
    summary = {
        "experiment": "BA-CH02-17",
        **profit_summary(wide),
        "by_province_rows": int(len(aggregate_sales_by_province(wide))),
        "by_year": aggregate_sales_by_year(wide).to_dict("records"),
        "by_category_rows": int(len(aggregate_profit_by_category(wide))),
        "top_employee": aggregate_sales_by_employee(wide, top=1).iloc[0].to_dict(),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
