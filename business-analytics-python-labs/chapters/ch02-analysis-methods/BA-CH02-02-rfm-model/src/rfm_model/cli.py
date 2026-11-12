"""Command-line workflow for the BA-CH02-02 RFM experiment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .core import compute_rfm, result_summary
from .quality import analyze_duplicate_sensitivity
from .reference import compare_reference, read_reference

EXPERIMENT_ROOT = Path(__file__).resolve().parents[2]


def read_transactions(path: str | Path) -> pd.DataFrame:
    """Read the source workbook's transaction sheet without modifying it."""
    return pd.read_excel(path, sheet_name="原始数据")


def build_report(
    transactions: pd.DataFrame,
    analysis_date: str,
    reference: pd.DataFrame | None = None,
) -> tuple[dict[str, object], int]:
    results = compute_rfm(transactions, analysis_date)
    report: dict[str, object] = {
        "experiment_id": "BA-CH02-02",
        "analysis_date": pd.Timestamp(analysis_date).date().isoformat(),
        "textbook_reproduction": {
            "source_rows": int(len(transactions)),
            **result_summary(results),
        },
        "duplicate_sensitivity": analyze_duplicate_sensitivity(transactions, analysis_date),
        "privacy": "Aggregate-only output. Customer-level identifiers and transaction rows are not serialized.",
    }
    exit_code = 0
    if reference is not None:
        validation = compare_reference(results, reference)
        report["reference_validation"] = validation
        exit_code = 0 if validation["passed"] else 1
    return report, exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description="复现 BA-CH02-02 RFM 模型并生成汇总报告")
    parser.add_argument("--input", required=True, help="本地授权的 RFM 输入工作簿路径")
    parser.add_argument("--analysis-date", required=True, help="分析日，格式 YYYY-MM-DD")
    parser.add_argument("--reference-answer", help="可选：仅用于独立核验的本地答案工作簿")
    parser.add_argument(
        "--output",
        default=str(EXPERIMENT_ROOT / "outputs" / "rfm_summary.json"),
        help="汇总 JSON 输出路径（默认写入本实验 outputs 目录）",
    )
    args = parser.parse_args()

    try:
        transactions = read_transactions(args.input)
        reference = read_reference(args.reference_answer) if args.reference_answer else None
        report, exit_code = build_report(transactions, args.analysis_date, reference)
    except (OSError, ValueError, KeyError) as exc:
        parser.error(str(exc))

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return exit_code
