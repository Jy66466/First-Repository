"""Command-line runner for BA-CH03-02."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .core import analyze_expenses
from .reference import compare_reference, read_reference_tables

EXPERIMENT_ROOT = Path(__file__).resolve().parents[2]


def _load_table(book: pd.ExcelFile, sheet: str, category_column: str | None = None) -> pd.DataFrame:
    table = pd.read_excel(book, sheet_name=sheet)
    rename = {"年份": "year", "月份": "month", "金额": "amount"}
    if category_column:
        rename[category_column] = "category"
    table = table.rename(columns=rename)
    if not category_column:
        table["category"] = "overall"
    return table.loc[:, ["year", "month", "category", "amount"]]


def main() -> int:
    parser = argparse.ArgumentParser(description="BA-CH03-02 monthly expense comparison")
    parser.add_argument("--input", required=True, help="Local complete-case workbook, not bundled")
    parser.add_argument("--base-period", default="2020-06", help="Base period in YYYY-MM format")
    parser.add_argument("--comparison-period", default="2020-07", help="Comparison period in YYYY-MM format")
    parser.add_argument("--reference-answer", help="Optional workbook with prepared result cells")
    parser.add_argument(
        "--output",
        default=str(EXPERIMENT_ROOT / "outputs" / "expense_summary.json"),
        help="Aggregate summary output path",
    )
    args = parser.parse_args()

    try:
        base = tuple(int(value) for value in args.base_period.split("-", maxsplit=1))
        comparison = tuple(int(value) for value in args.comparison_period.split("-", maxsplit=1))
        if len(base) != 2 or len(comparison) != 2:
            raise ValueError("Periods must use YYYY-MM format")
        with pd.ExcelFile(args.input) as book:
            results = analyze_expenses(
                _load_table(book, "财务三大期间费用-原始数据", "期间费用项"),
                _load_table(book, "管理费用-原始数据", "管理费用项"),
                _load_table(book, "总费用数据-原始数据"),
                base,
                comparison,
            )
        summary: dict[str, object] = {
            "experiment_id": "BA-CH03-02",
            "base_period": args.base_period,
            "comparison_period": args.comparison_period,
            "category_count": int(len(results["expense_categories"])),
            "management_item_count": int(len(results["management_items"])),
            "source_reconciliation_periods": int(len(results["reconciliation"])),
            "source_reconciliation_nonzero_periods": int(
                results["reconciliation"]["difference_categories_minus_reported"].abs().gt(0.01).sum()
            ),
            "privacy": "Aggregate counts and validation status only; no source rows are serialized.",
        }
        if args.reference_answer:
            reference = read_reference_tables(args.reference_answer)
            summary["reference_validation"] = compare_reference(results, reference)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))

    print(f"Aggregate summary written: {output}")
    return 0 if summary.get("reference_validation", {}).get("passed", True) else 1
