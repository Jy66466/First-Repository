from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from effect_decomposition import (
    centered_moving_average,
    classical_decomposition,
    log_transform,
    remove_festival_effect,
    seasonal_indices,
    seasonal_naive_forecast,
)


def _monthly_series() -> tuple[pd.Series, pd.Series]:
    """构造 3 年合成月度序列：趋势 100+t，季节因子 7 月 1.5、11 月 0.5。

    因子取值满足 12 个月均值为 1（(1.5+0.5+10)/12 = 1），
    与乘性分解的归一化口径一致。
    """
    months = pd.Series([((i % 12) + 1) for i in range(36)])
    trend = 100.0 + np.arange(36, dtype=float)
    factor = months.map(lambda m: 1.5 if m == 7 else (0.5 if m == 11 else 1.0))
    values = trend * factor
    return values, months


# ---------------------------------------------------------------------------
# 对数变换
# ---------------------------------------------------------------------------

def test_log_transform_known_values():
    values = pd.Series([1.0, np.e, np.e**2])
    result = log_transform(values)
    assert np.allclose(result, [0.0, 1.0, 2.0])


def test_log_transform_rejects_non_positive():
    with pytest.raises(ValueError):
        log_transform(pd.Series([1.0, 0.0]))


# ---------------------------------------------------------------------------
# 趋势与季节指数
# ---------------------------------------------------------------------------

def test_centered_moving_average_of_trendless_series():
    # 常数序列的中心化移动平均应仍为常数。
    values = pd.Series([10.0] * 24)
    ma = centered_moving_average(values, 12)
    valid = ma.dropna()
    assert len(valid) == 24 - 12
    assert np.allclose(valid, 10.0)


def test_seasonal_indices_match_design_factors():
    values, months = _monthly_series()
    trend = pd.Series(100.0 + np.arange(36, dtype=float))
    indices = seasonal_indices(values, months, trend)
    assert indices.loc[7] == pytest.approx(1.5, abs=1e-9)
    assert indices.loc[11] == pytest.approx(0.5, abs=1e-9)
    assert indices.mean() == pytest.approx(1.0, abs=1e-12)


def test_seasonal_indices_reject_additive_model():
    with pytest.raises(ValueError):
        seasonal_indices(pd.Series([1.0]), pd.Series([1]), pd.Series([1.0]), model="additive")


# ---------------------------------------------------------------------------
# 经典分解
# ---------------------------------------------------------------------------

def test_classical_decomposition_reconstruction():
    values, months = _monthly_series()
    result = classical_decomposition(values, months)
    core = result.dropna(subset=["trend", "irregular"])
    # 乘性模型：趋势 × 季节 × 余项 ≈ 原序列。
    recon = core["trend"] * core["seasonal"] * core["irregular"]
    assert np.allclose(recon, core["value"], atol=1e-6)


def test_classical_decomposition_deseasonalized_recovers_trend():
    values, months = _monthly_series()
    result = classical_decomposition(values, months)
    core = result.dropna(subset=["deseasonalized"])
    # 去季节序列应近似还原趋势 100 + t。经典分解的趋势来自移动平均，
    # 对非对称季节因子存在固有的少量季节泄漏，因此使用绝对容差。
    expected = 100.0 + core.index.to_numpy(dtype=float)
    assert np.allclose(core["deseasonalized"], expected, atol=0.6)


def test_classical_decomposition_length_mismatch_raises():
    with pytest.raises(ValueError):
        classical_decomposition(pd.Series([1.0, 2.0]), pd.Series([1]))


# ---------------------------------------------------------------------------
# 节日效应
# ---------------------------------------------------------------------------

def test_remove_festival_effect_known_offset():
    daily = pd.DataFrame(
        {
            "date": pd.date_range("2013-03-01", periods=10, freq="D"),
            "amount": [200.0] * 3 + [150.0] * 7,
        }
    )
    festival = pd.Series(pd.date_range("2013-03-01", periods=3))
    result, effect = remove_festival_effect(daily, "amount", festival)
    # 节日效应 = 节日均值(200) - 非节日均值(150) = +50。
    assert effect == pytest.approx(50.0)
    # 节日日扣除效应后应等于非节日水平 150。
    assert result.loc[result["is_festival"], "festival_effect_removed"].eq(150.0).all()
    assert result.loc[~result["is_festival"], "festival_effect_removed"].eq(150.0).all()


def test_remove_festival_effect_requires_both_groups():
    daily = pd.DataFrame(
        {"date": pd.date_range("2013-03-01", periods=5, freq="D"), "amount": [1.0] * 5}
    )
    with pytest.raises(ValueError):
        remove_festival_effect(daily, "amount", pd.Series(pd.date_range("2013-03-01", periods=5)))


# ---------------------------------------------------------------------------
# 季节朴素预测
# ---------------------------------------------------------------------------

def test_seasonal_naive_forecast_repeats_last_cycle():
    values, months = _monthly_series()
    forecast = seasonal_naive_forecast(values, months, horizon=12)
    assert list(forecast["forecast"].round(6)) == [round(v, 6) for v in values.iloc[-12:]]
    assert list(forecast["month"]) == list(months.iloc[-12:])


def test_seasonal_naive_forecast_needs_full_cycle():
    with pytest.raises(ValueError):
        seasonal_naive_forecast(pd.Series([1.0, 2.0]), pd.Series([1, 2]))
