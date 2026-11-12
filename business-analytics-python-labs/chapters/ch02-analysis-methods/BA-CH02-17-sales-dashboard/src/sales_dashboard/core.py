"""BA-CH02-17 核心：分省销售分析（Power BI 报表业务逻辑的 Python 等价实现）。

教材 PBIX（分省销售分析.pbix）经 Power BI Desktop 实测验证的模型语义：

- 星型模型 5 条关系，全部多对一、单向、活动：
  订单表明细表.OrderID -> 订单表.OrderID
  订单表.EmployeeID -> 雇员表.EmployeeID
  订单表明细表.ProductID -> 商品表.ProductID
  商品表.CategoryID -> 商品类型表.CategoryID
  订单表.OrderDate -> 自动日期表（教学口径用 orderyear/ordermonth 替代）
- 显式计算列（PBIX 实测提取的 DAX）：
  订单表.orderyear = YEAR(OrderDate)；订单表.ordermonth = MONTH(OrderDate)
  订单表明细表.利润 = sales - Cost
- 报表聚合全部为隐式 Sum（PBIX 中未发现任何显式度量值）。

Python 实现口径：

- 订单明细先与订单表合并取得省份/员工/年份维度，再与商品、商品类型合并；
- ``利润 = 销售金额 - 销售成本``，与 PBIX 计算列逐行等价；
- 聚合口径为直接求和；无匹配维度的明细行保留并在维度列记为 NA（左连接），
  这与 Power BI 空白成员的语义一致；
- 参考核对使用教材 CSV（只读），公开目录只提供合成数据与原创代码。
"""

from __future__ import annotations

import pandas as pd

__all__ = [
    "aggregate_profit_by_category",
    "aggregate_sales_by_employee",
    "aggregate_sales_by_province",
    "aggregate_sales_by_year",
    "load_star_schema",
    "profit_summary",
]


def _require(frame: pd.DataFrame, cols: set[str], label: str) -> None:
    missing = cols - set(frame.columns)
    if missing:
        raise KeyError(f"{label} missing columns: {sorted(missing)}")


def load_star_schema(
    orders: pd.DataFrame,
    details: pd.DataFrame,
    employees: pd.DataFrame,
    products: pd.DataFrame,
    categories: pd.DataFrame,
) -> pd.DataFrame:
    """按 PBIX 星型模型关系装配分析宽表（每行 = 一条订单明细）。

    合并顺序与 PBIX 关系一致：明细 -> 订单（OrderID）-> 雇员（EmployeeID），
    明细 -> 商品（ProductID）-> 商品类型（CategoryID）。全部左连接，
    未匹配键保留为 NA，不丢弃任何明细行。
    """
    _require(orders, {"OrderID"}, "orders")
    _require(details, {"OrderID", "ProductID", "sales", "Cost"}, "details")
    _require(employees, {"EmployeeID"}, "employees")
    _require(products, {"ProductID"}, "products")
    _require(categories, {"CategoryID"}, "categories")

    orders = orders.copy()
    details = details.copy()
    # PBIX 显式计算列的等价实现。
    if "OrderDate" in orders.columns:
        dates = pd.to_datetime(orders["OrderDate"], errors="coerce")
        orders["orderyear"] = dates.dt.year
        orders["ordermonth"] = dates.dt.month
    if "利润" not in details.columns:
        details["利润"] = pd.to_numeric(details["sales"], errors="coerce") - pd.to_numeric(
            details["Cost"], errors="coerce"
        )

    wide = details.merge(
        orders.drop(columns=["ProductID"], errors="ignore"),
        on="OrderID",
        how="left",
        validate="many_to_one",
    )
    wide = wide.merge(
        employees, on="EmployeeID", how="left", validate="many_to_one"
    )
    wide = wide.merge(
        products, on="ProductID", how="left", validate="many_to_one"
    )
    wide = wide.merge(
        categories, on="CategoryID", how="left", validate="many_to_one"
    )
    return wide.reset_index(drop=True)


def _sum_by(wide: pd.DataFrame, key: str, value: str) -> pd.DataFrame:
    if key not in wide.columns:
        raise KeyError(f"key column not found: {key!r}")
    grouped = (
        wide.groupby(key, dropna=False, as_index=False)[value]
        .sum()
    )
    return grouped.sort_values(value, ascending=False).reset_index(drop=True)


def aggregate_sales_by_province(wide: pd.DataFrame) -> pd.DataFrame:
    """按省份汇总销售额（对应报表的省份条形图）。"""
    return _sum_by(wide, "ShipProvince", "sales")


def aggregate_sales_by_year(wide: pd.DataFrame) -> pd.DataFrame:
    """按订单年份汇总销售额与订单数（对应 orderyear 计算列口径）。"""
    if "orderyear" not in wide.columns:
        raise KeyError("orderyear column missing; provide OrderDate in orders")
    detail_orders = wide.dropna(subset=["OrderID"]).drop_duplicates("OrderID")
    sales = wide.groupby("orderyear", dropna=False)["sales"].sum().rename("销售额")
    counts = detail_orders.groupby("orderyear", dropna=False)["OrderID"].count().rename("订单数")
    result = pd.concat([sales, counts], axis=1).reset_index()
    return result.sort_values("orderyear").reset_index(drop=True)


def aggregate_profit_by_category(wide: pd.DataFrame) -> pd.DataFrame:
    """按商品类别汇总销售额与利润（对应商品类别视觉对象）。"""
    keys = ["CategoryName"]
    missing = [k for k in keys if k not in wide.columns]
    if missing:
        raise KeyError(f"category columns missing: {missing}")
    grouped = wide.groupby(keys, dropna=False)[["sales", "利润"]].sum().reset_index()
    grouped = grouped.rename(columns={"sales": "销售额"})
    return grouped.sort_values("销售额", ascending=False).reset_index(drop=True)


def aggregate_sales_by_employee(wide: pd.DataFrame, top: int | None = None) -> pd.DataFrame:
    """按员工汇总销售额（可选取前 N 名，对应雇员排行视觉对象）。"""
    result = _sum_by(wide, "FullName", "sales")
    if top is not None:
        if top <= 0:
            raise ValueError("top must be positive")
        result = result.head(top).reset_index(drop=True)
    return result


def profit_summary(wide: pd.DataFrame) -> dict[str, float | int]:
    """总额摘要：订单数、明细行数、销售额、成本、利润。

    利润必须等于销售额减成本（PBIX 计算列 ``利润 = sales - Cost`` 的
    聚合等价式），否则说明输入被改动。
    """
    orders = wide.dropna(subset=["OrderID"])["OrderID"].nunique()
    sales = float(wide["sales"].sum())
    cost = float(wide["Cost"].sum())
    profit = float(wide["利润"].sum())
    if abs(profit - (sales - cost)) > 1e-6:
        raise ValueError("profit does not equal sales - cost")
    return {
        "orders": int(orders),
        "detail_rows": int(len(wide)),
        "sales": sales,
        "cost": cost,
        "profit": profit,
    }
