"""Aggregate customer segmentation for the precision-marketing case."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = ("客户ID", "性别", "年龄", "品类", "数量", "支付方式", "订单月份", "订单年份")
AGE_LABELS = ("18-25岁", "26-35岁", "36-49岁", "50岁以上")


def analyze_marketing(
    customers: pd.DataFrame,
    target_gender: str = "Female",
    target_age_band: str = "50岁以上",
    target_categories: Sequence[str] = ("Clothing", "Cosmetics"),
) -> dict[str, pd.Series | pd.DataFrame]:
    missing = [c for c in REQUIRED_COLUMNS if c not in customers.columns]
    if missing:
        raise ValueError(f"缺少必需字段：{', '.join(missing)}")
    data = customers.loc[:, REQUIRED_COLUMNS].copy()
    if data.empty or data.isna().any().any():
        raise ValueError("输入数据不能为空且必需字段不得缺失")
    if data["客户ID"].duplicated().any():
        raise ValueError("本案例按客户计数，客户ID必须唯一")
    data["年龄"] = pd.to_numeric(data["年龄"], errors="coerce")
    data["数量"] = pd.to_numeric(data["数量"], errors="coerce")
    if data[["年龄", "数量"]].isna().any().any() or not np.isfinite(data[["年龄", "数量"]]).all().all():
        raise ValueError("年龄和数量必须是有限数值")
    if (data["年龄"] < 18).any():
        raise ValueError("年龄必须不小于 18")
    data["年龄段"] = pd.cut(data["年龄"], bins=[17, 25, 35, 49, np.inf], labels=AGE_LABELS)

    gender_counts = data["性别"].value_counts().sort_index().rename("customer_count")
    age_by_gender = data.groupby(["性别", "年龄段"], observed=False)["客户ID"].nunique().unstack(fill_value=0).reindex(columns=AGE_LABELS, fill_value=0)
    target = data[(data["性别"] == target_gender) & (data["年龄段"] == target_age_band)]
    if target.empty:
        raise ValueError("目标性别和年龄段没有客户")
    category_counts = target["品类"].value_counts().sort_index().rename("customer_count")
    selected = target[target["品类"].isin(target_categories)]
    payment_counts = selected["支付方式"].value_counts().sort_index().rename("customer_count")
    return {"gender_counts": gender_counts, "age_by_gender": age_by_gender, "category_counts": category_counts, "payment_counts": payment_counts}


def plot_counts(counts: pd.Series, title: str):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7, 4))
    counts.plot(kind="bar", ax=ax)
    ax.set(xlabel="Category", ylabel="Customers", title=title)
    fig.tight_layout()
    return fig

