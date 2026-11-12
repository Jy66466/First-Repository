"""Descriptive distribution and IQR outlier analysis."""

from __future__ import annotations

import numpy as np
import pandas as pd


def summarize_distribution(values: pd.Series) -> dict[str, float | int]:
    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.isna().any() or numeric.empty or not np.isfinite(numeric).all():
        raise ValueError("输入必须是非空且无缺失的有限数值序列")
    quantiles = numeric.quantile([0, 0.25, 0.5, 0.75, 1], interpolation="linear")
    q1 = float(quantiles.loc[0.25]); q3 = float(quantiles.loc[0.75]); iqr = q3 - q1
    lower = q1 - 1.5 * iqr; upper = q3 + 1.5 * iqr
    return {
        "count": int(len(numeric)),
        "mean": float(numeric.mean()),
        "min": float(quantiles.loc[0]),
        "q1": q1,
        "median": float(quantiles.loc[0.5]),
        "q3": q3,
        "max": float(quantiles.loc[1]),
        "iqr": iqr,
        "lower_fence": lower,
        "upper_fence": upper,
        "outlier_count": int(((numeric < lower) | (numeric > upper)).sum()),
    }


def plot_distribution(values: pd.Series):
    import matplotlib.pyplot as plt

    numeric = pd.to_numeric(values, errors="raise")
    fig, (ax_hist, ax_box) = plt.subplots(1, 2, figsize=(10, 4), gridspec_kw={"width_ratios": [3, 1]})
    ax_hist.hist(numeric, bins="auto", edgecolor="white")
    ax_hist.set(xlabel="Value", ylabel="Count", title="Distribution")
    ax_box.boxplot(numeric, vert=True)
    ax_box.set(ylabel="Value", xticks=[])
    fig.tight_layout()
    return fig

