"""Boston matrix calculations reconstructed from the verified workbook rules."""

from __future__ import annotations

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = ("销售日期", "品牌", "单价", "销量")


def classify_position(
    market_share: float,
    growth_rate: float,
    average_share: float,
    market_growth: float,
) -> str:
    """Classify a brand; values equal to a threshold use the lower group."""
    high_share = market_share > average_share
    high_growth = growth_rate > market_growth
    if high_share and high_growth:
        return "明星业务"
    if high_share:
        return "现金牛业务"
    if high_growth:
        return "问题业务"
    return "瘦狗业务"


def compute_boston_matrix(
    sales: pd.DataFrame,
    base_period: str,
    comparison_period: str,
) -> pd.DataFrame:
    """Calculate two-period share, growth, thresholds, and Boston category."""
    missing = [c for c in REQUIRED_COLUMNS if c not in sales.columns]
    if missing:
        raise ValueError(f"缺少必需字段：{', '.join(missing)}")
    if sales.empty:
        raise ValueError("输入数据为空")

    data = sales.loc[:, REQUIRED_COLUMNS].copy()
    data["销售日期"] = pd.to_datetime(data["销售日期"], errors="coerce", format="mixed")
    data["单价"] = pd.to_numeric(data["单价"], errors="coerce")
    data["销量"] = pd.to_numeric(data["销量"], errors="coerce")
    if data.isna().any().any():
        raise ValueError("必需字段存在缺失值或无法解析的值")
    if (data["单价"] < 0).any() or (data["销量"] < 0).any():
        raise ValueError("单价和销量不得为负数")

    data["期间"] = data["销售日期"].dt.to_period("M").astype(str)
    data["销售额"] = data["单价"] * data["销量"]
    selected = data[data["期间"].isin([base_period, comparison_period])]
    if selected.empty:
        raise ValueError("指定期间没有销售记录")

    pivot = selected.pivot_table(
        index="品牌", columns="期间", values="销售额", aggfunc="sum", fill_value=0.0
    ).reindex(columns=[base_period, comparison_period], fill_value=0.0)
    if (pivot[base_period] <= 0).any():
        raise ValueError("品牌基期销售额必须大于 0 才能计算增长率")
    base_total = float(pivot[base_period].sum())
    comparison_total = float(pivot[comparison_period].sum())
    if base_total <= 0 or comparison_total <= 0:
        raise ValueError("两个期间的市场销售额必须大于 0")

    result = pivot.rename(columns={base_period: "base_sales", comparison_period: "comparison_sales"})
    result["two_period_sales"] = result["base_sales"] + result["comparison_sales"]
    result["market_share"] = result["two_period_sales"] / result["two_period_sales"].sum()
    result["growth_rate"] = (result["comparison_sales"] - result["base_sales"]) / result["base_sales"]
    average_share = float(result["market_share"].mean())
    market_growth = (comparison_total - base_total) / base_total
    result["average_share_threshold"] = average_share
    result["market_growth_threshold"] = market_growth
    result["category"] = [
        classify_position(share, growth, average_share, market_growth)
        for share, growth in zip(result["market_share"], result["growth_rate"], strict=True)
    ]
    return result.reset_index().rename(columns={"品牌": "brand"})


def plot_boston_matrix(result: pd.DataFrame):
    """Return an editable Matplotlib Boston-matrix chart."""
    import matplotlib.pyplot as plt

    required = {"brand", "market_share", "growth_rate", "average_share_threshold", "market_growth_threshold"}
    if not required.issubset(result.columns):
        raise ValueError("结果表缺少绘图字段")
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.scatter(result["market_share"], result["growth_rate"], s=70)
    for row in result.itertuples(index=False):
        ax.annotate(str(row.brand), (row.market_share, row.growth_rate), xytext=(4, 4), textcoords="offset points")
    ax.axvline(float(result["average_share_threshold"].iloc[0]), color="gray", linestyle="--")
    ax.axhline(float(result["market_growth_threshold"].iloc[0]), color="gray", linestyle="--")
    ax.set(xlabel="Two-period market share", ylabel="Period-over-period growth", title="Boston matrix")
    fig.tight_layout()
    return fig

