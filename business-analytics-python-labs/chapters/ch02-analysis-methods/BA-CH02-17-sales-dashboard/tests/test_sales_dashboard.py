from __future__ import annotations

import pandas as pd
import pytest

from sales_dashboard import (
    aggregate_profit_by_category,
    aggregate_sales_by_employee,
    aggregate_sales_by_province,
    aggregate_sales_by_year,
    load_star_schema,
    profit_summary,
)


@pytest.fixture()
def wide() -> pd.DataFrame:
    orders = pd.DataFrame(
        {
            "OrderID": [1, 2, 3],
            "EmployeeID": [10, 10, 20],
            "ShipProvince": ["省份甲", "省份甲", "省份乙"],
            "OrderDate": pd.to_datetime(["2020-03-05", "2020-07-01", "2021-01-15"]),
        }
    )
    details = pd.DataFrame(
        {
            "OrderID": [1, 1, 2, 3],
            "ProductID": [100, 200, 100, 999],
            "sales": [100.0, 250.0, 80.0, 60.0],
            "Cost": [70.0, 200.0, 60.0, 50.0],
        }
    )
    employees = pd.DataFrame(
        {
            "EmployeeID": [10, 20],
            "FullName": ["员工甲", "员工乙"],
        }
    )
    products = pd.DataFrame(
        {
            "ProductID": [100, 200],
            "ProductName": ["商品A", "商品B"],
            "CategoryID": [1, 2],
        }
    )
    categories = pd.DataFrame(
        {"CategoryID": [1, 2], "CategoryName": ["类别一", "类别二"]}
    )
    return load_star_schema(orders, details, employees, products, categories)


def test_load_star_schema_computes_profit_and_year(wide):
    # 利润 = sales - Cost：100-70=30, 250-200=50, 80-60=20, 60-50=10。
    assert wide["利润"].tolist() == [30.0, 50.0, 20.0, 10.0]
    assert list(wide["orderyear"].dropna().unique()) == [2020, 2021]
    assert list(wide["ordermonth"].dropna().unique()) == [3, 7, 1]


def test_load_star_schema_keeps_unmatched_rows(wide):
    # ProductID=999 无商品匹配，行保留且维度为 NA。
    row = wide.loc[wide["ProductID"] == 999].iloc[0]
    assert pd.isna(row["ProductName"])
    assert pd.isna(row["CategoryName"])
    assert len(wide) == 4


def test_load_star_schema_missing_columns_raises():
    with pytest.raises(KeyError):
        load_star_schema(
            pd.DataFrame({"x": [1]}),
            pd.DataFrame({"OrderID": [1], "ProductID": [1], "sales": [1], "Cost": [1]}),
            pd.DataFrame({"EmployeeID": [1]}),
            pd.DataFrame({"ProductID": [1]}),
            pd.DataFrame({"CategoryID": [1]}),
        )


def test_province_aggregation(wide):
    result = aggregate_sales_by_province(wide)
    # 省份甲 = 100+250+80 = 430；省份乙 = 60。
    assert result.iloc[0]["ShipProvince"] == "省份甲"
    assert result.iloc[0]["sales"] == 430.0
    assert result.iloc[1]["sales"] == 60.0


def test_year_aggregation_orders_count_distinct(wide):
    result = aggregate_sales_by_year(wide)
    y2020 = result.loc[result["orderyear"] == 2020].iloc[0]
    # 2020 年：订单 1、2（2 张订单），明细销售额 430。
    assert y2020["销售额"] == 430.0
    assert y2020["订单数"] == 2
    y2021 = result.loc[result["orderyear"] == 2021].iloc[0]
    assert y2021["销售额"] == 60.0
    assert y2021["订单数"] == 1


def test_category_profit_aggregation(wide):
    result = aggregate_profit_by_category(wide)
    cat1 = result.loc[result["CategoryName"] == "类别一"].iloc[0]
    # 类别一（商品A）：销售额 180，利润 30+20=50。
    assert cat1["销售额"] == 180.0
    assert cat1["利润"] == 50.0
    # ProductID=999 未匹配类别，聚合含 NA 组。
    assert result["CategoryName"].isna().sum() == 1


def test_employee_top(wide):
    result = aggregate_sales_by_employee(wide, top=1)
    assert len(result) == 1
    assert result.iloc[0]["FullName"] == "员工甲"
    assert result.iloc[0]["sales"] == 430.0


def test_employee_top_invalid_raises(wide):
    with pytest.raises(ValueError):
        aggregate_sales_by_employee(wide, top=0)


def test_profit_summary(wide):
    summary = profit_summary(wide)
    assert summary["orders"] == 3
    assert summary["detail_rows"] == 4
    assert summary["sales"] == 490.0
    assert summary["cost"] == 380.0
    assert summary["profit"] == 110.0


def test_profit_summary_detects_tampering(wide):
    tampered = wide.copy()
    tampered.loc[0, "利润"] = 999.0
    with pytest.raises(ValueError):
        profit_summary(tampered)
