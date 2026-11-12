from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from effect_decomposition import (
    classical_decomposition,
    log_transform,
    seasonal_naive_forecast,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="BA-CH10-01 效应分解演示")
    parser.add_argument("--input", required=True, help="含 DATE/AIR 两列的 CSV 或 Excel（已授权副本）")
    parser.add_argument("--date-column", default="DATE")
    parser.add_argument("--value-column", default="AIR")
    parser.add_argument("--output", default="outputs/effect_decomposition_summary.json")
    args = parser.parse_args()

    frame = (
        pd.read_csv(args.input) if str(args.input).lower().endswith("csv") else pd.read_excel(args.input)
    )
    dates = pd.to_datetime(frame[args.date_column])
    values = pd.Series(frame[args.value_column], dtype="float64")
    months = dates.dt.month
    decomposed = classical_decomposition(values, months)
    forecast = seasonal_naive_forecast(values, months)
    summary = {
        "experiment": "BA-CH10-01",
        "observations": int(len(values)),
        "log_first_value": float(log_transform(values).iloc[0]),
        "log_last_value": float(log_transform(values).iloc[-1]),
        "seasonal_index_july": float(decomposed.loc[months == 7, "seasonal"].iloc[0]),
        "seasonal_index_november": float(decomposed.loc[months == 11, "seasonal"].iloc[0]),
        "irregular_max_abs": float(decomposed["irregular"].dropna().abs().max()),
        "forecast_first_value": float(forecast.loc[0, "forecast"]),
        "note": "WPS AI 预测与 Power BI 内部逻辑未复现，属验证边界",
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
