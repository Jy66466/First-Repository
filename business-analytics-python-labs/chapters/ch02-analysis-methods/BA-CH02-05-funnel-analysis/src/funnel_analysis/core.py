"""Ordered-stage funnel calculations."""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_funnel(data: pd.DataFrame, stage_column: str = "阶段", count_column: str = "用户数") -> pd.DataFrame:
    if stage_column not in data.columns or count_column not in data.columns:
        raise ValueError("输入缺少阶段或用户数字段")
    if data.empty:
        raise ValueError("输入数据为空")
    result = data[[stage_column, count_column]].copy()
    if result.isna().any().any() or result[stage_column].duplicated().any():
        raise ValueError("阶段必须唯一且字段不得缺失")
    result[count_column] = pd.to_numeric(result[count_column], errors="coerce")
    if result[count_column].isna().any() or not np.isfinite(result[count_column]).all() or (result[count_column] < 0).any():
        raise ValueError("用户数必须是非负有限数值")
    if (result[count_column].diff().dropna() > 0).any():
        raise ValueError("漏斗阶段用户数不得随流程增加")
    first = float(result[count_column].iloc[0])
    if first <= 0:
        raise ValueError("首阶段用户数必须大于 0")
    previous = result[count_column].shift(1)
    result["stage_conversion"] = result[count_column] / previous
    result.loc[result.index[0], "stage_conversion"] = 1.0
    result["overall_conversion"] = result[count_column] / first
    result["stage_dropoff"] = previous - result[count_column]
    result.loc[result.index[0], "stage_dropoff"] = 0.0
    return result.rename(columns={stage_column: "stage", count_column: "users"})


def plot_funnel(result: pd.DataFrame):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(result["stage"].astype(str), result["users"])
    ax.invert_yaxis()
    ax.set(xlabel="Users", ylabel="Stage", title="Conversion funnel")
    fig.tight_layout()
    return fig

