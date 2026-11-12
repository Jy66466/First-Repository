"""Python equivalents for the workbook's summary and lookup exercises."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

SALES_COLUMNS = ("销售地区", "销售人员", "品名", "数量", "单价")
DEFAULT_GRADES = ((0, "不及格"), (60, "及格"), (70, "可以"), (80, "良好"), (90, "优秀"))


def summarize_sales(sales: pd.DataFrame, region: str | None = None) -> dict[str, pd.DataFrame]:
    missing = [c for c in SALES_COLUMNS if c not in sales.columns]
    if missing:
        raise ValueError(f"缺少必需字段：{', '.join(missing)}")
    data = sales.loc[:, SALES_COLUMNS].copy()
    if data.isna().any().any():
        raise ValueError("销售字段存在缺失值")
    data["数量"] = pd.to_numeric(data["数量"], errors="coerce")
    data["单价"] = pd.to_numeric(data["单价"], errors="coerce")
    if data[["数量", "单价"]].isna().any().any() or not np.isfinite(data[["数量", "单价"]]).all().all():
        raise ValueError("数量和单价必须是有限数值")
    if region is not None:
        data = data[data["销售地区"] == region]
        if data.empty:
            raise ValueError("指定地区没有销售记录")
    data["销售金额"] = data["数量"] * data["单价"]
    by_person = data.groupby("销售人员", as_index=False).agg(数量总计=("数量", "sum"), 销售金额总计=("销售金额", "sum"))
    by_product = data.groupby("品名", as_index=False).agg(数量总计=("数量", "sum"), 销售金额总计=("销售金额", "sum"))
    return {"by_person": by_person, "by_product": by_product}


def grade_lookup(scores: pd.Series, thresholds: Sequence[tuple[float, str]] = DEFAULT_GRADES) -> pd.Series:
    ordered = sorted((float(cutoff), label) for cutoff, label in thresholds)
    if not ordered or len({x[0] for x in ordered}) != len(ordered):
        raise ValueError("等级阈值必须非空且不重复")
    numeric = pd.to_numeric(scores, errors="coerce")
    if numeric.isna().any() or not np.isfinite(numeric).all():
        raise ValueError("成绩必须是有限数值")
    cutoffs = np.array([x[0] for x in ordered], dtype=float)
    labels = [x[1] for x in ordered]
    positions = np.searchsorted(cutoffs, numeric.to_numpy(dtype=float), side="right") - 1
    if (positions < 0).any():
        raise ValueError("存在低于最低等级阈值的成绩")
    return pd.Series([labels[i] for i in positions], index=scores.index, name="成绩等级")


def multiplication_table(size: int = 9) -> pd.DataFrame:
    if not isinstance(size, int) or size < 1:
        raise ValueError("size 必须是正整数")
    values = []
    for left in range(1, size + 1):
        values.append([f"{left}*{right}={left * right}" if right <= left else "" for right in range(1, size + 1)])
    return pd.DataFrame(values, index=range(1, size + 1), columns=range(1, size + 1))

