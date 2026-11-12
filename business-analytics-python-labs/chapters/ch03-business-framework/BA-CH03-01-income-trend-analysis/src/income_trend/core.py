"""Income trend analysis using the workbook's verified aggregation rules."""

from __future__ import annotations

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = ("订单年份", "订单月份", "销售省份", "销售额")


def _reference_growth(base: pd.Series, comparison: pd.Series) -> pd.Series:
    """Workbook convention: (comparison - base) / comparison; zero comparison returns zero."""
    base_values = base.to_numpy(dtype=float)
    comparison_values = comparison.to_numpy(dtype=float)
    values = np.divide(
        comparison_values - base_values,
        comparison_values,
        out=np.zeros_like(comparison_values),
        where=comparison_values != 0,
    )
    return pd.Series(values, index=base.index, name="reference_growth")


def analyze_income(
    income: pd.DataFrame,
    base_year: int,
    comparison_year: int,
    focus_month: int = 11,
    focus_province: str = "四川",
) -> dict[str, pd.DataFrame | pd.Series]:
    missing = [c for c in REQUIRED_COLUMNS if c not in income.columns]
    if missing:
        raise ValueError(f"缺少必需字段：{', '.join(missing)}")
    data = income.loc[:, REQUIRED_COLUMNS].copy()
    if data.empty or data.isna().any().any():
        raise ValueError("输入数据不能为空且必需字段不得缺失")
    for column in ("订单年份", "订单月份", "销售额"):
        data[column] = pd.to_numeric(data[column], errors="coerce")
    if data[["订单年份", "订单月份", "销售额"]].isna().any().any() or not np.isfinite(data["销售额"]).all():
        raise ValueError("年份、月份或销售额存在无效值")
    if not data["订单月份"].between(1, 12).all():
        raise ValueError("订单月份必须在 1 至 12 之间")
    data["订单年份"] = data["订单年份"].astype(int); data["订单月份"] = data["订单月份"].astype(int)
    if base_year == comparison_year:
        raise ValueError("基期和比较期必须不同")

    yearly = data.groupby("订单年份")["销售额"].sum().sort_index().rename("sales")
    monthly_comparison = data[data["订单年份"] == comparison_year].groupby("订单月份")["销售额"].sum().reindex(range(1, 13), fill_value=0).rename("sales")
    monthly = data[data["订单年份"].isin([base_year, comparison_year])].pivot_table(index="订单月份", columns="订单年份", values="销售额", aggfunc="sum", fill_value=0).reindex(index=range(1, 13), columns=[base_year, comparison_year], fill_value=0)
    monthly.columns = ["base_sales", "comparison_sales"]
    monthly["total_sales"] = monthly.sum(axis=1)
    monthly["reference_growth"] = _reference_growth(monthly["base_sales"], monthly["comparison_sales"])

    province = data[(data["订单年份"].isin([base_year, comparison_year])) & (data["订单月份"] == focus_month)].pivot_table(index="销售省份", columns="订单年份", values="销售额", aggfunc="sum", fill_value=0).reindex(columns=[base_year, comparison_year], fill_value=0)
    province.columns = ["base_sales", "comparison_sales"]
    province["total_sales"] = province.sum(axis=1)
    province["reference_growth"] = _reference_growth(province["base_sales"], province["comparison_sales"])

    focus = data[(data["订单年份"].isin([base_year, comparison_year])) & (data["销售省份"] == focus_province)].pivot_table(index="订单月份", columns="订单年份", values="销售额", aggfunc="sum", fill_value=0).reindex(index=range(1, 13), columns=[base_year, comparison_year], fill_value=0)
    focus.columns = ["base_sales", "comparison_sales"]
    focus["total_sales"] = focus.sum(axis=1)
    focus["reference_growth"] = _reference_growth(focus["base_sales"], focus["comparison_sales"])
    return {"yearly": yearly, "monthly_comparison_year": monthly_comparison, "monthly_year_over_year": monthly, "focus_month_by_province": province, "focus_province_by_month": focus}


def plot_yearly_income(yearly: pd.Series):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(yearly.index.astype(str), yearly.values, marker="o")
    ax.set(xlabel="Year", ylabel="Sales", title="Annual sales trend")
    fig.tight_layout()
    return fig

