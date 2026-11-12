"""BA-CH01-02 维度模型演示：商场销售数据（星型模型的 Python/SQLite 实现）。"""

from .core import (
    aggregate_sales,
    build_star_schema_sqlite,
    load_star_schema,
    normalize_product_code,
    validate_fact_against_dimensions,
)

__all__ = [
    "aggregate_sales",
    "build_star_schema_sqlite",
    "load_star_schema",
    "normalize_product_code",
    "validate_fact_against_dimensions",
]
