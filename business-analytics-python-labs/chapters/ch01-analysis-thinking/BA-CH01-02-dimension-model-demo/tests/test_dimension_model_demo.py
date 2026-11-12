from __future__ import annotations

import sqlite3

import pandas as pd
import pytest

from dimension_model_demo import (
    aggregate_sales,
    build_star_schema_sqlite,
    load_star_schema,
    normalize_product_code,
    validate_fact_against_dimensions,
)


@pytest.fixture()
def schema() -> dict[str, pd.DataFrame]:
    fact = pd.DataFrame(
        {
            "订单日期": pd.to_datetime(["2018-01-01", "2018-01-02", "2018-02-01"]),
            "城市编码": ["510100", "320500", "510100"],
            "商铺城市": ["成都市", "苏州市", "成都市"],
            "产品编号": ["a001", "B002", "A001"],
            "销售数量": [40, 12, 5],
            "销售单价": [4669, 4299, 4669],
            "销售额": [186760, 51588, 23345],
        }
    )
    product = pd.DataFrame(
        {
            "产品编号": ["A001", "A002", "B002"],
            "产品名称": ["GL冰箱", "GL电视", "MD电视"],
            "品牌名称": ["GL", "GL", "MD"],
            "产品类别": ["冰箱", "电视", "电视"],
            "采购单价": [2200, 1500, 2000],
            "销售单价": [4669, 3299, 4299],
        }
    )
    city = pd.DataFrame(
        {"城市编码": ["510100", "320500", "430100"], "商铺城市": ["成都市", "苏州市", "长沙市"]}
    )
    date_table = pd.DataFrame(
        {"日期": pd.date_range("2018-01-01", periods=60, freq="D"), "年度": 2018}
    )
    return load_star_schema(fact, product, city, date_table)


def test_normalize_product_code():
    frame = pd.DataFrame({"产品编号": [" a001 ", "B002"]})
    assert list(normalize_product_code(frame)["产品编号"]) == ["A001", "B002"]


def test_load_star_schema_joins_product(schema):
    fact = schema["fact"]
    # 事实表未冗余携带属性时，从维度表补齐品牌与类别。
    assert fact.loc[0, "品牌名称"] == "GL"
    assert fact.loc[0, "产品类别"] == "冰箱"
    assert fact["产品表销售单价"].tolist() == [4669, 4299, 4669]
    assert fact.loc[0, "城市编码"] == "510100"


def test_load_star_schema_missing_columns_raises():
    with pytest.raises(KeyError):
        load_star_schema(pd.DataFrame({"x": [1]}), pd.DataFrame({"产品编号": ["A001"]}))


def test_load_star_schema_duplicate_product_key_raises():
    fact = pd.DataFrame(
        {"订单日期": [pd.Timestamp("2018-01-01")], "商铺城市": ["成都市"], "产品编号": ["A001"],
         "销售数量": [1], "销售单价": [10], "销售额": [10]}
    )
    product = pd.DataFrame(
        {"产品编号": ["A001", "A001"], "产品名称": ["GL冰箱", "GL冰箱"], "品牌名称": ["GL", "GL"],
         "产品类别": ["冰箱", "冰箱"], "销售单价": [10, 10]}
    )
    with pytest.raises(ValueError):
        load_star_schema(fact, product)


def test_validation_detects_price_and_amount(schema):
    report = validate_fact_against_dimensions(schema)
    assert report["rows"] == 3
    assert report["unmatched_product_keys"] == 0
    assert report["price_mismatch_rows"] == 0
    assert report["amount_mismatch_rows"] == 0
    assert report["dates_missing_in_date_table"] == 0


def test_validation_reports_mismatch():
    fact = pd.DataFrame(
        {
            "订单日期": pd.to_datetime(["2018-01-01"]),
            "商铺城市": ["成都市"],
            "产品编号": ["A001"],
            "销售数量": [2],
            "销售单价": [10],
            "销售额": [999],
        }
    )
    product = pd.DataFrame(
        {"产品编号": ["A001"], "产品名称": ["GL冰箱"], "品牌名称": ["GL"], "产品类别": ["冰箱"], "销售单价": [10]}
    )
    schema = load_star_schema(fact, product)
    report = validate_fact_against_dimensions(schema)
    assert report["amount_mismatch_rows"] == 1


def test_aggregate_by_brand(schema):
    result = aggregate_sales(schema, "品牌名称")
    gl = result.loc[result["品牌名称"] == "GL"].iloc[0]
    # GL = a001(40) + A001(5)。
    assert gl["销售数量"] == 45
    assert gl["销售额"] == 186760 + 23345
    md = result.loc[result["品牌名称"] == "MD"].iloc[0]
    assert md["销售额"] == 51588


def test_aggregate_by_year_month(schema):
    result = aggregate_sales(schema, ["年度", "月"])
    assert list(result["月"]) == [1, 2]
    # 1 月 = a001(40) + B002(12)，2 月 = A001(5)。
    assert list(result["销售数量"]) == [52, 5]


def test_aggregate_unknown_key_raises(schema):
    with pytest.raises(KeyError):
        aggregate_sales(schema, "不存在")


def test_sqlite_star_join(schema):
    conn = build_star_schema_sqlite(schema)
    assert isinstance(conn, sqlite3.Connection)
    query = """
    SELECT p.品牌名称, SUM(f.销售数量) AS qty, SUM(f.销售额) AS amt
    FROM fact_sales f
    JOIN dim_product p ON f.产品编号 = p.产品编号
    GROUP BY p.品牌名称
    ORDER BY p.品牌名称
    """
    result = pd.read_sql_query(query, conn)
    assert list(result["品牌名称"]) == ["GL", "MD"]
    assert int(result.loc[result["品牌名称"] == "GL", "qty"].iloc[0]) == 45
