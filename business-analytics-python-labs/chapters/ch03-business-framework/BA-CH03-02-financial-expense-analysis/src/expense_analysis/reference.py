"""Read workbook reference cells for post-calculation verification only."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

def read_reference_tables(path: str | Path) -> dict[str, pd.DataFrame]:
    """Read prepared comparison cells; never used to calculate the analysis."""
    workbook = load_workbook(path, data_only=True, read_only=True)
    try:
        if "准备区" not in workbook.sheetnames:
            raise ValueError("Reference workbook is missing the prepared-results sheet")
        sheet = workbook["准备区"]
        category_rows = []
        for row in range(19, 22):
            label = sheet.cell(row, 1).value
            if label is None:
                continue
            category_rows.append(
                {
                    "category": str(label).strip(),
                    "base_amount": float(sheet.cell(row, 2).value),
                    "comparison_amount": float(sheet.cell(row, 3).value),
                    "delta": float(sheet.cell(row, 5).value),
                }
            )
        management_rows = []
        for row in range(31, 39):
            label = sheet.cell(row, 1).value
            if label is None:
                continue
            management_rows.append(
                {
                    "category": str(label).strip(),
                    "base_amount": float(sheet.cell(row, 2).value),
                    "comparison_amount": float(sheet.cell(row, 3).value),
                    "growth_rate": float(sheet.cell(row, 5).value),
                }
            )
        if not category_rows or not management_rows:
            raise ValueError("Reference workbook has incomplete prepared result tables")
        return {
            "expense_categories": pd.DataFrame(category_rows),
            "management_items": pd.DataFrame(management_rows),
        }
    finally:
        workbook.close()


def compare_reference(
    results: dict[str, pd.DataFrame], reference: dict[str, pd.DataFrame], amount_tolerance: float = 0.0,
    rate_tolerance: float = 1e-12,
) -> dict[str, int | bool]:
    """Compare computed category-level values with workbook result cells."""
    checked = 0
    mismatches = 0
    for table_name, columns in (
        ("expense_categories", ("base_amount", "comparison_amount", "delta")),
        ("management_items", ("base_amount", "comparison_amount", "growth_rate")),
    ):
        actual = results[table_name].set_index("category")
        expected = reference[table_name].set_index("category")
        if set(actual.index) != set(expected.index):
            mismatches += len(set(actual.index).symmetric_difference(expected.index))
        for category in actual.index.intersection(expected.index):
            for column in columns:
                checked += 1
                tolerance = rate_tolerance if column == "growth_rate" else amount_tolerance
                left = actual.at[category, column]
                right = expected.at[category, column]
                if pd.isna(left) or pd.isna(right):
                    equal = pd.isna(left) and pd.isna(right)
                else:
                    equal = abs(float(left) - float(right)) <= tolerance
                if not equal:
                    mismatches += 1
    return {
        "checked_values": checked,
        "mismatches": mismatches,
        "passed": mismatches == 0,
    }
