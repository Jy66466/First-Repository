"""BA-CH01-02 核心实现：星型模型的加载、校验与聚合。

维度建模口径（依教材演示工作簿结构确定）：

- **事实表**：产品销售数据表，粒度为“日期 × 城市 × 产品 × 单据行”，
  度量为 ``销售数量`` 与 ``销售额 = 销售数量 × 销售单价``；
- **维度表**：产品信息表（含品牌、类别层级）、商铺城市、日期表；
  ``品牌``/``类别`` 是教材中独立的演示维度表；
- **规范化**：事实表中的产品编号存在小写（``a001``）与产品信息表中
  大写（``A001``）并存的情况，连接前统一为大写；
- **一致性校验**：事实表 ``销售单价`` 应与产品信息表一致；事实表日期
  应全部落在日期表覆盖范围内；聚合销售额应等于 ``数量 × 单价`` 之和。
"""

from __future__ import annotations

import sqlite3

import pandas as pd

__all__ = [
    "aggregate_sales",
    "build_star_schema_sqlite",
    "load_star_schema",
    "normalize_product_code",
    "validate_fact_against_dimensions",
]

_FACT_REQUIRED = {"订单日期", "商铺城市", "产品编号", "销售数量", "销售单价", "销售额"}
_PRODUCT_REQUIRED = {"产品编号", "产品名称", "品牌名称", "产品类别", "销售单价"}


def normalize_product_code(frame: pd.DataFrame, column: str = "产品编号") -> pd.DataFrame:
    """把产品编号统一为大写字符串并去除首尾空白。"""
    frame = frame.copy()
    frame[column] = frame[column].astype(str).str.strip().str.upper()
    return frame


def load_star_schema(
    fact: pd.DataFrame,
    product: pd.DataFrame,
    city: pd.DataFrame | None = None,
    date_table: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    """组装星型模型：规范化键、连接维度属性到事实表。

    返回字典包含 ``fact``（增强事实表）、``product``、``city``、``date``。
    """
    missing = _FACT_REQUIRED - set(fact.columns)
    if missing:
        raise KeyError(f"fact table missing columns: {sorted(missing)}")
    missing = _PRODUCT_REQUIRED - set(product.columns)
    if missing:
        raise KeyError(f"product dimension missing columns: {sorted(missing)}")

    fact = normalize_product_code(fact)
    product = normalize_product_code(product)
    if product["产品编号"].duplicated().any():
        raise ValueError("product dimension has duplicate keys")

    # 事实表若已冗余携带品牌/类别等属性列，以事实表列为准，
    # 不再从维度表引入同名列，避免 join 后出现 _x/_y 后缀。
    attrs = [c for c in ("品牌名称", "产品类别") if c not in fact.columns]
    product_cols = ["产品编号", "销售单价"] + attrs
    fact = fact.merge(
        product[product_cols].rename(columns={"销售单价": "产品表销售单价"}),
        on="产品编号",
        how="left",
        validate="many_to_one",
    )
    # 城市维度：事实表按商铺城市名称关联城市编码（教材演示结构）。
    # 事实表若已自带城市编码，则视为规范化已完成，不重复引入。
    if city is not None and {"城市编码", "商铺城市"} <= set(city.columns):
        city = city.copy()
        city["城市编码"] = city["城市编码"].astype(str).str.strip()
        city["商铺城市"] = city["商铺城市"].astype(str).str.strip()
        if "商铺城市" in fact.columns and "城市编码" not in fact.columns:
            fact = fact.copy()
            fact["商铺城市"] = fact["商铺城市"].astype(str).str.strip()
            fact = fact.merge(
                city[["城市编码", "商铺城市"]].drop_duplicates("商铺城市"),
                on="商铺城市",
                how="left",
                validate="many_to_one",
            )
    return {"fact": fact, "product": product, "city": city, "date": date_table}


def validate_fact_against_dimensions(schema: dict[str, pd.DataFrame]) -> dict[str, object]:
    """对事实表做一致性校验，返回校验摘要。"""
    fact = schema["fact"]
    price_mismatch = int((fact["销售单价"] != fact["产品表销售单价"]).sum())
    unmatched = int(fact["产品表销售单价"].isna().sum())
    recomputed = fact["销售数量"] * fact["销售单价"]
    amount_mismatch = int((recomputed - fact["销售额"]).abs().gt(1e-6).sum())
    date_coverage_missing = None
    date_dim = schema.get("date")
    if date_dim is not None and {"日期"} <= set(date_dim.columns):
        dates = pd.to_datetime(date_dim["日期"]).dt.normalize()
        fact_dates = pd.to_datetime(fact["订单日期"]).dt.normalize()
        date_coverage_missing = int((~fact_dates.isin(dates)).sum())
    return {
        "rows": int(len(fact)),
        "unmatched_product_keys": unmatched,
        "price_mismatch_rows": price_mismatch,
        "amount_mismatch_rows": amount_mismatch,
        "dates_missing_in_date_table": date_coverage_missing,
    }


def aggregate_sales(
    schema: dict[str, pd.DataFrame],
    by: str | list[str],
) -> pd.DataFrame:
    """按维度属性汇总销售数量与销售额。

    ``by`` 支持 ``品牌名称``、``产品类别``、``商铺城市``、``年度``、``月`` 等
    事实表列名；多列传入列表。汇总口径为求和，不平均分摊。
    """
    keys = [by] if isinstance(by, str) else list(by)
    fact = schema["fact"].copy()
    fact["_年度"] = pd.to_datetime(fact["订单日期"]).dt.year
    fact["_月"] = pd.to_datetime(fact["订单日期"]).dt.month
    keys = ["_年度" if k == "年度" else ("_月" if k == "月" else k) for k in keys]
    missing = [k for k in keys if k not in fact.columns]
    if missing:
        raise KeyError(f"aggregation keys not in fact table: {missing}")
    grouped = (
        fact.groupby(keys, as_index=False)[["销售数量", "销售额"]]
        .sum()
        .rename(columns={"_年度": "年度", "_月": "月"})
    )
    out_keys = ["年度" if k == "_年度" else ("月" if k == "_月" else k) for k in keys]
    return grouped.sort_values(out_keys).reset_index(drop=True)


def build_star_schema_sqlite(
    schema: dict[str, pd.DataFrame],
    database: str = ":memory:",
) -> sqlite3.Connection:
    """把星型模型写入 SQLite，演示显式多表连接。"""
    conn = sqlite3.connect(database)
    schema["fact"].to_sql("fact_sales", conn, index=False, if_exists="replace")
    schema["product"].to_sql("dim_product", conn, index=False, if_exists="replace")
    if schema.get("city") is not None:
        schema["city"].drop_duplicates().to_sql(
            "dim_city", conn, index=False, if_exists="replace"
        )
    if schema.get("date") is not None:
        schema["date"].to_sql("dim_date", conn, index=False, if_exists="replace")
    conn.commit()
    return conn
