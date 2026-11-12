"""Command-line entry point for BA-CH02-06."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from .core import analyze_correlation
from .reference import compare_reference, read_reference_workbook

EXPERIMENT_ROOT = Path(__file__).resolve().parents[2]


def read_pairs(path: str | Path, sheet_name: str) -> pd.DataFrame:
    return pd.read_excel(path, sheet_name=sheet_name)


def save_scatter_plot(pairs: pd.DataFrame, metrics: dict[str, float | int], output_path: Path) -> None:
    x = pairs["x"].to_numpy(dtype=float)
    y = pairs["y"].to_numpy(dtype=float)
    x_line = [float(x.min()), float(x.max())]
    y_line = [metrics["slope"] * value + metrics["intercept"] for value in x_line]

    figure, axis = plt.subplots(figsize=(7, 5), constrained_layout=True)
    axis.scatter(x, y, color="#267A78", alpha=0.8, edgecolors="white", linewidths=0.4, label="Observations")
    axis.plot(x_line, y_line, color="#C54E38", linewidth=1.8, label="Least-squares trend")
    axis.set_xlabel("x")
    axis.set_ylabel("y")
    axis.set_title("Correlation analysis")
    axis.legend(frameon=False)
    axis.grid(alpha=0.2)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=140)
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser(description="BA-CH02-06 Pearson correlation analysis")
    parser.add_argument("--input", required=True, help="Local x/y workbook")
    parser.add_argument("--sheet", default="原始数据", help="Input worksheet")
    parser.add_argument("--reference-answer", help="Optional local answer workbook for independent verification")
    parser.add_argument(
        "--output",
        default=str(EXPERIMENT_ROOT / "outputs" / "correlation_summary.json"),
        help="Aggregate JSON output path",
    )
    parser.add_argument(
        "--plot",
        default=str(EXPERIMENT_ROOT / "outputs" / "correlation_scatter.png"),
        help="Scatter plot output path",
    )
    args = parser.parse_args()

    try:
        pairs = read_pairs(args.input, args.sheet)
        metrics = analyze_correlation(pairs)
        summary: dict[str, object] = {
            "experiment_id": "BA-CH02-06",
            "method": "Pearson correlation with a simple least-squares trend line",
            "metrics": metrics,
            "privacy": "Aggregate statistics only; raw paired observations are not serialized.",
        }
        if args.reference_answer:
            reference_pairs, reference_display = read_reference_workbook(args.reference_answer, args.sheet)
            summary["reference_validation"] = compare_reference(
                pairs, reference_pairs, metrics, reference_display
            )
            exit_code = 0 if summary["reference_validation"]["passed"] else 1
        else:
            exit_code = 0

        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        save_scatter_plot(pairs, metrics, Path(args.plot))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))

    print(f"Summary written: {output_path}")
    print(f"Scatter plot written: {Path(args.plot)}")
    return exit_code
