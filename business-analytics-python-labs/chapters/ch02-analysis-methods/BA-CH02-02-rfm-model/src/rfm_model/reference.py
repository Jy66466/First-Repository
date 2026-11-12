"""Read cached answer values for independent validation only."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

REFERENCE_COLUMNS = {
    "用户编号": "customer_id",
    "最近一次消费日期": "last_purchase_date",
    "消费频次": "frequency",
    "消费金额": "monetary",
    "消费时间间隔": "recency_days",
    "R程度": "r_label",
    "F程度": "f_label",
    "M程度": "m_label",
    "用户类别": "segment",
}
COMPARISON_FIELDS = (
    "last_purchase_date",
    "frequency",
    "monetary",
    "recency_days",
    "r_label",
    "f_label",
    "m_label",
    "segment",
)


def read_reference(path: str | Path) -> pd.DataFrame:
    """Read cached worksheet values; pandas does not request formula recalculation."""
    reference = pd.read_excel(path, sheet_name="参考答案", header=5, usecols="A:I")
    reference = reference.dropna(subset=["用户编号"]).rename(columns=REFERENCE_COLUMNS)
    required = set(REFERENCE_COLUMNS.values())
    missing = sorted(required - set(reference.columns))
    if missing:
        raise ValueError(f"参考答案缺少必需字段：{', '.join(missing)}")
    empty_fields = reference[list(required)].isna().sum()
    empty_fields = {str(k): int(v) for k, v in empty_fields.items() if v}
    if empty_fields:
        raise ValueError(f"参考答案存在缺失值：{empty_fields}")
    if reference["customer_id"].duplicated().any():
        raise ValueError("参考答案包含重复客户键，无法进行一对一核验")
    reference["last_purchase_date"] = pd.to_datetime(reference["last_purchase_date"], errors="coerce").dt.normalize()
    if reference["last_purchase_date"].isna().any():
        raise ValueError("参考答案包含无法解析的最近消费日期")
    for field in ("frequency", "monetary", "recency_days"):
        reference[field] = pd.to_numeric(reference[field], errors="coerce")
        if reference[field].isna().any():
            raise ValueError(f"参考答案的 {field} 字段包含非数值")
    return reference.loc[:, ["customer_id", *COMPARISON_FIELDS]]


def compare_reference(actual: pd.DataFrame, reference: pd.DataFrame, monetary_tolerance: float = 1e-8) -> dict[str, object]:
    """Compare all customers and return mismatch counts only, never row details."""
    if actual["customer_id"].duplicated().any():
        raise ValueError("Python 结果包含重复客户键，无法进行一对一核验")
    if reference["customer_id"].duplicated().any():
        raise ValueError("参考答案包含重复客户键，无法进行一对一核验")

    merged = actual.merge(
        reference,
        on="customer_id",
        how="outer",
        suffixes=("_actual", "_reference"),
        indicator=True,
        validate="one_to_one",
    )
    matched = merged[merged["_merge"] == "both"]
    mismatches: dict[str, int] = {}
    for field in COMPARISON_FIELDS:
        left = matched[f"{field}_actual"]
        right = matched[f"{field}_reference"]
        if field == "monetary":
            mismatch = ~np.isclose(
                pd.to_numeric(left, errors="coerce").to_numpy(dtype=float),
                pd.to_numeric(right, errors="coerce").to_numpy(dtype=float),
                rtol=0,
                atol=monetary_tolerance,
                equal_nan=True,
            )
        elif field == "last_purchase_date":
            left_dates = pd.to_datetime(left, errors="coerce").dt.normalize()
            right_dates = pd.to_datetime(right, errors="coerce").dt.normalize()
            mismatch = left_dates.ne(right_dates).to_numpy()
        else:
            mismatch = left.ne(right).to_numpy()
        mismatches[field] = int(np.asarray(mismatch).sum())

    python_only = int((merged["_merge"] == "left_only").sum())
    reference_only = int((merged["_merge"] == "right_only").sum())
    return {
        "python_customers": int(len(actual)),
        "reference_customers": int(len(reference)),
        "matched_customers": int(len(matched)),
        "python_only_customers": python_only,
        "reference_only_customers": reference_only,
        "mismatch_counts": mismatches,
        "monetary_absolute_tolerance": monetary_tolerance,
        "passed": python_only == 0 and reference_only == 0 and all(value == 0 for value in mismatches.values()),
    }
