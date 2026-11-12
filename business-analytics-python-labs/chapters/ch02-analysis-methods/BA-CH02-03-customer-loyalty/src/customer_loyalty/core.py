"""Customer loyalty and potential/churn-risk classification."""

from __future__ import annotations

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = ("订单编号", "会员编号", "消费日期", "消费金额")
SCORE_LABELS = {2: "低价值用户", 3: "低价值用户", 4: "普通用户", 5: "进阶用户", 6: "忠诚用户"}


def analyze_customer_loyalty(
    transactions: pd.DataFrame,
    analysis_date: str | pd.Timestamp,
    recent_weeks: int = 13,
) -> dict[str, object]:
    missing = [c for c in REQUIRED_COLUMNS if c not in transactions.columns]
    if missing:
        raise ValueError(f"缺少必需字段：{', '.join(missing)}")
    if transactions.empty or recent_weeks <= 0:
        raise ValueError("输入数据不能为空，recent_weeks 必须为正数")
    data = transactions.loc[:, REQUIRED_COLUMNS].copy()
    if data.isna().any().any():
        raise ValueError("必需字段存在缺失值")
    data["消费日期"] = pd.to_datetime(data["消费日期"], errors="coerce", format="mixed")
    data["消费金额"] = pd.to_numeric(data["消费金额"], errors="coerce")
    if data[["消费日期", "消费金额"]].isna().any().any() or not np.isfinite(data["消费金额"]).all():
        raise ValueError("日期或金额存在无效值")

    as_of = pd.Timestamp(analysis_date).normalize()
    cutoff = as_of - pd.Timedelta(weeks=recent_weeks)
    if data["消费日期"].dt.normalize().gt(as_of).any():
        raise ValueError("存在晚于分析日的消费记录")
    data["recent"] = data["消费日期"] > cutoff

    customer = data.groupby("会员编号").agg(
        last_purchase=("消费日期", "max"),
        frequency=("订单编号", "nunique"),
        monetary=("消费金额", "sum"),
    )
    period_counts = (
        data.groupby(["会员编号", "recent"])["订单编号"]
        .nunique()
        .unstack(fill_value=0)
        .reindex(columns=[False, True], fill_value=0)
        .rename(columns={False: "before_orders", True: "recent_orders"})
    )
    customer = customer.join(period_counts)
    customer["special_status"] = pd.NA
    customer.loc[customer["last_purchase"] < cutoff, "special_status"] = "易流失用户"
    potential = (customer["before_orders"] == 0) & (customer["recent_orders"] == 1)
    customer.loc[potential, "special_status"] = "潜在用户"

    eligible = customer[customer["special_status"].isna()].copy()
    if eligible.empty:
        raise ValueError("排除潜在用户和易流失用户后没有可评分客户")
    fq1, fq3 = eligible["frequency"].quantile([0.25, 0.75], interpolation="linear")
    mq1, mq3 = eligible["monetary"].quantile([0.25, 0.75], interpolation="linear")

    def score(series: pd.Series, q1: float, q3: float) -> pd.Series:
        return pd.Series(np.where(series < q1, 1, np.where(series > q3, 3, 2)), index=series.index)

    eligible["frequency_score"] = score(eligible["frequency"], float(fq1), float(fq3))
    eligible["monetary_score"] = score(eligible["monetary"], float(mq1), float(mq3))
    eligible["total_score"] = eligible["frequency_score"] + eligible["monetary_score"]
    eligible["loyalty_segment"] = eligible["total_score"].map(SCORE_LABELS)
    return {
        "analysis_date": as_of,
        "cutoff": cutoff,
        "customers": customer.reset_index(),
        "eligible_scores": eligible.reset_index(),
        "thresholds": {"frequency_q1": float(fq1), "frequency_q3": float(fq3), "monetary_q1": float(mq1), "monetary_q3": float(mq3)},
    }

