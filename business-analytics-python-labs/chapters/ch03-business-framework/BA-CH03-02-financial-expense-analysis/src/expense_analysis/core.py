"""Period-over-period expense summaries and source reconciliation."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence

import pandas as pd


def _month_number(value: object) -> int:
    match = re.fullmatch(r"\s*(\d{1,2})\s*月?\s*", str(value))
    if not match:
        raise ValueError(f"Invalid month value: {value!r}")
    month = int(match.group(1))
    if not 1 <= month <= 12:
        raise ValueError(f"Month must be between 1 and 12: {value!r}")
    return month


def _normalize_entries(data: pd.DataFrame, required: Sequence[str]) -> pd.DataFrame:
    missing = [name for name in required if name not in data.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    if data.empty:
        raise ValueError("Input table contains no expense records")

    entries = data.loc[:, required].copy()
    entries["year"] = pd.to_numeric(entries["year"], errors="coerce")
    entries["amount"] = pd.to_numeric(entries["amount"], errors="coerce")
    if entries[["year", "amount"]].isna().any().any():
        raise ValueError("Year and amount must contain valid numeric values")
    if not entries["amount"].map(math.isfinite).all():
        raise ValueError("Amounts must be finite numbers")
    if not entries["year"].map(lambda value: float(value).is_integer()).all():
        raise ValueError("Year values must be whole numbers")
    entries["year"] = entries["year"].astype(int)
    entries["month"] = entries["month"].map(_month_number)
    entries["category"] = entries["category"].astype("string").str.strip()
    if entries["category"].isna().any() or entries["category"].eq("").any():
        raise ValueError("Category values cannot be empty")
    return entries


def _period_mask(data: pd.DataFrame, period: tuple[int, int]) -> pd.Series:
    year, month = period
    return data["year"].eq(year) & data["month"].eq(month)


def _compare_periods(
    data: pd.DataFrame, base_period: tuple[int, int], comparison_period: tuple[int, int]
) -> pd.DataFrame:
    base = data.loc[_period_mask(data, base_period), ["category", "amount"]]
    comparison = data.loc[_period_mask(data, comparison_period), ["category", "amount"]]
    if base.empty or comparison.empty:
        raise ValueError("Both comparison periods must have source rows")

    base_totals = base.groupby("category", sort=True)["amount"].sum()
    comparison_totals = comparison.groupby("category", sort=True)["amount"].sum()
    categories = base_totals.index.union(comparison_totals.index).sort_values()
    result = pd.DataFrame(
        {
            "base_amount": base_totals.reindex(categories, fill_value=0.0),
            "comparison_amount": comparison_totals.reindex(categories, fill_value=0.0),
        }
    )
    result.index.name = "category"
    result["total"] = result["base_amount"] + result["comparison_amount"]
    result["delta"] = result["comparison_amount"] - result["base_amount"]
    result["growth_rate"] = result.apply(
        lambda row: None
        if row["base_amount"] == 0
        else row["delta"] / row["base_amount"],
        axis=1,
    )
    return result.reset_index()


def analyze_expenses(
    period_expenses: pd.DataFrame,
    management_expenses: pd.DataFrame,
    overall_totals: pd.DataFrame,
    base_period: tuple[int, int],
    comparison_period: tuple[int, int],
) -> dict[str, pd.DataFrame]:
    """Summarize expense categories and compare their rollup to reported totals.

    Expected input columns are year, month, category, and amount. Missing category-
    period rows are treated as zero; repeated rows are summed, not deduplicated.
    """
    period_rows = _normalize_entries(
        period_expenses, ("year", "month", "category", "amount")
    )
    management_rows = _normalize_entries(
        management_expenses, ("year", "month", "category", "amount")
    )
    totals = _normalize_entries(
        overall_totals.assign(category="overall") if "category" not in overall_totals else overall_totals,
        ("year", "month", "category", "amount"),
    )
    if base_period == comparison_period:
        raise ValueError("Base and comparison periods must be different")

    period_summary = _compare_periods(period_rows, base_period, comparison_period)
    management_summary = _compare_periods(
        management_rows, base_period, comparison_period
    )
    total_summary = _compare_periods(totals, base_period, comparison_period)

    category_sums = period_rows.groupby(["year", "month"], as_index=False)["amount"].sum()
    reported = totals.groupby(["year", "month"], as_index=False)["amount"].sum()
    reconciliation = category_sums.merge(
        reported, on=["year", "month"], how="outer", suffixes=("_categories", "_reported")
    )
    reconciliation["amount_categories"] = reconciliation["amount_categories"].fillna(0.0)
    reconciliation["amount_reported"] = reconciliation["amount_reported"].fillna(0.0)
    reconciliation["difference_categories_minus_reported"] = (
        reconciliation["amount_categories"] - reconciliation["amount_reported"]
    )
    reconciliation = reconciliation.sort_values(["year", "month"]).reset_index(drop=True)

    return {
        "expense_categories": period_summary,
        "management_items": management_summary,
        "reported_totals": total_summary,
        "reconciliation": reconciliation,
    }
