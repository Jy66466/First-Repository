"""Core RFM calculations using the workbook-verified rules."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

CUSTOMER_ID = "用户编号"
FLOW_ID = "流水号"
SALE_DATE = "销售日期"
SALE_AMOUNT = "销售金额"
REQUIRED_COLUMNS = (CUSTOMER_ID, FLOW_ID, SALE_DATE, SALE_AMOUNT)

SEGMENT_MAP: Mapping[str, str] = {
    "高高高": "重要价值用户",
    "高低高": "重要发展用户",
    "低高高": "重要保持用户",
    "低低高": "重要挽留用户",
    "高高低": "一般价值用户",
    "高低低": "一般发展用户",
    "低高低": "一般保持用户",
    "低低低": "一般挽留用户",
}

RFM_COLUMNS = (
    "customer_id",
    "last_purchase_date",
    "frequency",
    "monetary",
    "recency_days",
    "r_label",
    "f_label",
    "m_label",
    "segment",
)


def validate_transactions(transactions: pd.DataFrame) -> pd.DataFrame:
    """Validate required fields and return a typed copy without dropping rows."""
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in transactions.columns]
    if missing_columns:
        raise ValueError(f"缺少必需字段：{', '.join(missing_columns)}")
    if transactions.empty:
        raise ValueError("输入数据没有交易记录")

    data = transactions.loc[:, REQUIRED_COLUMNS].copy()
    missing_counts = data.isna().sum()
    invalid_missing = {str(k): int(v) for k, v in missing_counts.items() if v}
    if invalid_missing:
        raise ValueError(f"必需字段存在缺失值：{invalid_missing}")

    data[SALE_DATE] = pd.to_datetime(data[SALE_DATE], errors="coerce", format="mixed")
    bad_dates = int(data[SALE_DATE].isna().sum())
    if bad_dates:
        raise ValueError(f"销售日期无法解析的记录数：{bad_dates}")
    if isinstance(data[SALE_DATE].dtype, pd.DatetimeTZDtype):
        raise ValueError("销售日期必须为不带时区的本地日期时间")

    data[SALE_AMOUNT] = pd.to_numeric(data[SALE_AMOUNT], errors="coerce")
    amounts = data[SALE_AMOUNT].to_numpy(dtype=float)
    if not np.isfinite(amounts).all():
        raise ValueError("销售金额必须为有限数值")
    return data


def compute_rfm(transactions: pd.DataFrame, analysis_date: str | pd.Timestamp) -> pd.DataFrame:
    """Calculate customer R/F/M values, mean-based labels, and segment."""
    data = validate_transactions(transactions)
    as_of = pd.Timestamp(analysis_date)
    if pd.isna(as_of):
        raise ValueError("分析日无效")
    if as_of.tz is not None:
        raise ValueError("分析日必须为不带时区的日期")
    as_of = as_of.normalize()
    if data[SALE_DATE].dt.normalize().gt(as_of).any():
        raise ValueError("存在晚于分析日的销售记录")

    result = (
        data.groupby(CUSTOMER_ID, sort=True, dropna=False)
        .agg(
            last_purchase_date=(SALE_DATE, "max"),
            frequency=(FLOW_ID, "nunique"),
            monetary=(SALE_AMOUNT, "sum"),
        )
        .reset_index()
        .rename(columns={CUSTOMER_ID: "customer_id"})
    )
    result["recency_days"] = (as_of - result["last_purchase_date"].dt.normalize()).dt.days

    r_threshold = float(result["recency_days"].mean())
    f_threshold = float(result["frequency"].mean())
    m_threshold = float(result["monetary"].mean())
    result["r_label"] = np.where(result["recency_days"] < r_threshold, "高", "低")
    result["f_label"] = np.where(result["frequency"] > f_threshold, "高", "低")
    result["m_label"] = np.where(result["monetary"] > m_threshold, "高", "低")
    keys = result["r_label"] + result["f_label"] + result["m_label"]
    result["segment"] = keys.map(SEGMENT_MAP)
    if result["segment"].isna().any():
        raise RuntimeError("RFM 标签组合未配置客户类别映射")
    return result.loc[:, RFM_COLUMNS]


def result_summary(results: pd.DataFrame) -> dict[str, object]:
    """Return aggregate-only metrics; never serialize customer-level rows."""
    return {
        "customer_count": int(len(results)),
        "thresholds": {
            "R_mean_days": float(results["recency_days"].mean()),
            "F_mean_distinct_flows": float(results["frequency"].mean()),
            "M_mean_source_amount_units": float(results["monetary"].mean()),
        },
        "segment_counts": {
            str(key): int(value)
            for key, value in results["segment"].value_counts().sort_index().items()
        },
    }
