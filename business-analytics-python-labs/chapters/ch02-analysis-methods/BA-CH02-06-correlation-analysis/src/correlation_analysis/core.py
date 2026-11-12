"""Pearson correlation and least-squares line for paired numeric data."""

from __future__ import annotations

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = ("x", "y")


def validate_pairs(data: pd.DataFrame) -> pd.DataFrame:
    """Return a validated x/y copy without dropping or deduplicating rows."""
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in data.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns: {', '.join(missing_columns)}")
    if data.empty:
        raise ValueError("Input contains no paired observations")

    pairs = data.loc[:, REQUIRED_COLUMNS].copy()
    for column in REQUIRED_COLUMNS:
        pairs[column] = pd.to_numeric(pairs[column], errors="coerce")
        values = pairs[column].to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise ValueError(f"Column {column} must contain finite, non-missing numbers")
    if len(pairs) < 2:
        raise ValueError("At least two paired observations are required")
    if pairs["x"].nunique() < 2:
        raise ValueError("Column x has zero variance; correlation and slope are undefined")
    if pairs["y"].nunique() < 2:
        raise ValueError("Column y has zero variance; Pearson correlation is undefined")
    return pairs


def analyze_correlation(data: pd.DataFrame) -> dict[str, float | int]:
    """Calculate Pearson r and the simple least-squares trend line."""
    pairs = validate_pairs(data)
    x = pairs["x"].to_numpy(dtype=float)
    y = pairs["y"].to_numpy(dtype=float)
    x_centered = x - x.mean()
    y_centered = y - y.mean()
    sum_x2 = float(np.dot(x_centered, x_centered))
    sum_y2 = float(np.dot(y_centered, y_centered))
    sum_xy = float(np.dot(x_centered, y_centered))

    pearson_r = sum_xy / np.sqrt(sum_x2 * sum_y2)
    slope = sum_xy / sum_x2
    intercept = float(y.mean() - slope * x.mean())
    predicted = slope * x + intercept
    residual_sum_squares = float(np.square(y - predicted).sum())
    r_squared = 1.0 - residual_sum_squares / sum_y2

    return {
        "observation_count": int(len(pairs)),
        "pearson_r": float(pearson_r),
        "slope": float(slope),
        "intercept": intercept,
        "r_squared": float(r_squared),
        "x_mean": float(x.mean()),
        "y_mean": float(y.mean()),
    }
