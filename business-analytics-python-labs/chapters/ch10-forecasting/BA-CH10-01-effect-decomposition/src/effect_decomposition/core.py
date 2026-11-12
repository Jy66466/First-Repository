"""BA-CH10-01 核心实现：效应分解与预测基线。

教材“效应分解法”的可验证部分：

- **对数变换**：对原始月度序列取自然对数（教材 `ln_AIR` 列口径），
  用于把乘性季节波动近似化为加性结构；
- **经典效应分解**：以 12 期中心化移动平均估计趋势，季节效应按
  同月平均偏离估计并归一化，余项为残差。乘性模型满足
  ``趋势 × 季节 × 余项 ≈ 原序列``；
- **节日效应**：对日度序列，以节日日均值与非节日日均值的差估计
  节日效应，从节日日中扣除（对应教材“含节日/去除节日”对比口径）；
- **季节朴素预测**：以“去年同月值”作为预测，仅作为原创基线，
  **不声称复现**教材 WPS AI 的黑盒预测结果。

验证边界：WPS 自带 AI 预测与 Power BI（效应分解法.pbix）内部逻辑
不可从文件还原，本实验不模拟其算法，也不对比其预测值。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = [
    "classical_decomposition",
    "log_transform",
    "remove_festival_effect",
    "seasonal_indices",
    "seasonal_naive_forecast",
]


def log_transform(values: pd.Series) -> pd.Series:
    """自然对数变换；非正数直接报错（教材数据均为正数）。"""
    values = pd.Series(values, dtype="float64")
    if (values <= 0).any():
        raise ValueError("log transform requires strictly positive values")
    return np.log(values)


def centered_moving_average(values: pd.Series, period: int = 12) -> pd.Series:
    """偶数周期（如 12）的中心化移动平均；奇数周期直接滚动均值。"""
    values = pd.Series(values, dtype="float64")
    if period < 2:
        raise ValueError("period must be >= 2")
    if period % 2 == 0:
        # 偶数周期中心化（2×period MA）：相邻两个 period 窗口均值再平均，
        # 等价于权重 [0.5, 1, ..., 1, 0.5]/period 的加权移动平均。
        roll = values.rolling(period, center=True).mean()
        return (roll + roll.shift(-1)) / 2
    return values.rolling(period, center=True).mean()


def seasonal_indices(
    values: pd.Series,
    months: pd.Series,
    trend: pd.Series,
    model: str = "multiplicative",
) -> pd.Series:
    """按月份序号（1-12）估计季节指数。

    乘性模型：``季节指数 = 同月 (原值/趋势) 的平均``，再除以总均值归一化，
    使 12 个月指数均值恰为 1。趋势缺失期不参与估计。
    """
    if model != "multiplicative":
        raise ValueError("only multiplicative model is implemented")
    detrended = values / trend
    frame = pd.DataFrame({"m": months, "d": detrended}).dropna()
    indices = frame.groupby("m")["d"].mean()
    indices = indices / indices.mean()
    return indices


def classical_decomposition(
    values: pd.Series,
    months: pd.Series,
    period: int = 12,
) -> pd.DataFrame:
    """乘性经典分解，返回 趋势/季节/去季节序列/余项。"""
    values = pd.Series(values, dtype="float64").reset_index(drop=True)
    months = pd.Series(months).reset_index(drop=True)
    if len(values) != len(months):
        raise ValueError("values and months must have equal length")
    trend = centered_moving_average(values, period)
    indices = seasonal_indices(values, months, trend)
    seasonal = months.map(indices).astype("float64")
    deseasonalized = values / seasonal
    irregular = values / (trend * seasonal)
    return pd.DataFrame(
        {
            "value": values,
            "month": months,
            "trend": trend,
            "seasonal": seasonal,
            "deseasonalized": deseasonalized,
            "irregular": irregular,
        }
    )


def remove_festival_effect(
    daily: pd.DataFrame,
    value_column: str,
    festival_dates: pd.Series,
) -> tuple[pd.DataFrame, float]:
    """估计并移除节日效应。

    口径：``节日效应 = 节日日均值 - 非节日日均值``；对节日日的取值扣除
    该效应后返回。返回 ``(结果 DataFrame, 节日效应值)``。
    """
    daily = daily.copy()
    daily["_date"] = pd.to_datetime(daily.iloc[:, 0])
    festival = set(pd.to_datetime(pd.Series(festival_dates)).dt.normalize())
    is_festival = daily["_date"].isin(festival)
    if is_festival.all() or (~is_festival).all():
        raise ValueError("both festival and non-festival days are required")
    effect = float(daily.loc[is_festival, value_column].mean()
                   - daily.loc[~is_festival, value_column].mean())
    daily["festival_effect_removed"] = daily[value_column] - effect * is_festival.astype(float)
    daily["is_festival"] = is_festival
    return daily.drop(columns="_date"), effect


def seasonal_naive_forecast(
    values: pd.Series,
    months: pd.Series,
    horizon: int = 12,
) -> pd.DataFrame:
    """季节朴素预测：预测值 = 最近一个完整周期中同月份的观测值。"""
    values = pd.Series(values, dtype="float64").reset_index(drop=True)
    months = pd.Series(months).reset_index(drop=True)
    if len(values) < 12:
        raise ValueError("seasonal naive forecast needs at least one full cycle")
    last_cycle = values.iloc[-12:].to_numpy()
    last_months = months.iloc[-12:].to_numpy()
    rows = []
    for step in range(1, horizon + 1):
        idx = (step - 1) % 12
        rows.append(
            {
                "step": step,
                "month": int(last_months[idx]),
                "forecast": float(last_cycle[idx]),
            }
        )
    return pd.DataFrame(rows)
