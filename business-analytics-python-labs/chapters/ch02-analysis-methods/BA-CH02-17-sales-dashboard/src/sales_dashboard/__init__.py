"""BA-CH02-17 销售看板：分省销售分析（星型模型核心计算）。"""

from .core import (
    aggregate_profit_by_category,
    aggregate_sales_by_employee,
    aggregate_sales_by_province,
    aggregate_sales_by_year,
    load_star_schema,
    profit_summary,
)

__all__ = [
    "aggregate_profit_by_category",
    "aggregate_sales_by_employee",
    "aggregate_sales_by_province",
    "aggregate_sales_by_year",
    "load_star_schema",
    "profit_summary",
]
