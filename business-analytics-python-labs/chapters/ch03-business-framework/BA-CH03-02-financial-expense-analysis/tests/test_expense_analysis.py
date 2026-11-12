from __future__ import annotations

import pandas as pd
import pytest

from expense_analysis.core import analyze_expenses
from expense_analysis.reference import compare_reference


def sample_inputs():
    period = pd.DataFrame(
        {
            "year": [2024, 2024, 2024, 2024, 2024],
            "month": [1, 1, 2, 2, 2],
            "category": ["Admin", "Sales", "Admin", "Sales", "Sales"],
            "amount": [100, 50, 120, 40, 10],
        }
    )
    management = pd.DataFrame(
        {
            "year": [2024, 2024, 2024],
            "month": [1, 2, 2],
            "category": ["Payroll", "Payroll", "Rent"],
            "amount": [80, 100, 20],
        }
    )
    totals = pd.DataFrame(
        {"year": [2024, 2024], "month": [1, 2], "amount": [150, 180]}
    )
    return period, management, totals


def test_period_comparison_sums_rows_and_calculates_change_at_category_level():
    results = analyze_expenses(*sample_inputs(), (2024, 1), (2024, 2))
    categories = results["expense_categories"].set_index("category")
    assert categories.loc["Admin", "base_amount"] == 100
    assert categories.loc["Admin", "comparison_amount"] == 120
    assert categories.loc["Admin", "delta"] == 20
    assert categories.loc["Admin", "growth_rate"] == pytest.approx(0.2)
    assert categories.loc["Sales", "comparison_amount"] == 50
    assert categories.loc["Sales", "growth_rate"] == pytest.approx(0.0)


def test_missing_category_period_is_explicitly_treated_as_zero():
    results = analyze_expenses(*sample_inputs(), (2024, 1), (2024, 2))
    rent = results["management_items"].set_index("category").loc["Rent"]
    assert rent["base_amount"] == 0
    assert rent["comparison_amount"] == 20
    assert rent["delta"] == 20
    assert pd.isna(rent["growth_rate"])


def test_reported_total_reconciliation_exposes_unexplained_gap():
    period, management, totals = sample_inputs()
    totals.loc[1, "amount"] = 200
    results = analyze_expenses(period, management, totals, (2024, 1), (2024, 2))
    reconciliation = results["reconciliation"].set_index(["year", "month"])
    assert reconciliation.loc[(2024, 1), "difference_categories_minus_reported"] == 0
    assert reconciliation.loc[(2024, 2), "difference_categories_minus_reported"] == -30


def test_reference_comparison_checks_each_expected_value_and_detects_mismatch():
    results = analyze_expenses(*sample_inputs(), (2024, 1), (2024, 2))
    references = {
        "expense_categories": results["expense_categories"].loc[:, ["category", "base_amount", "comparison_amount", "delta"]].copy(),
        "management_items": results["management_items"].loc[:, ["category", "base_amount", "comparison_amount", "growth_rate"]].copy(),
    }
    passed = compare_reference(results, references)
    assert passed == {"checked_values": 12, "mismatches": 0, "passed": True}

    references["expense_categories"].loc[0, "delta"] += 1
    failed = compare_reference(results, references)
    assert failed["checked_values"] == 12
    assert failed["mismatches"] == 1
    assert failed["passed"] is False


@pytest.mark.parametrize(
    "column,value,message",
    [
        ("month", 13, "between 1 and 12"),
        ("month", "June", "Invalid month"),
        ("amount", "bad", "valid numeric"),
        ("amount", float("inf"), "finite numbers"),
    ],
)
def test_invalid_source_values_are_rejected(column, value, message):
    period, management, totals = sample_inputs()
    period[column] = period[column].astype("object")
    period.loc[0, column] = value
    with pytest.raises(ValueError, match=message):
        analyze_expenses(period, management, totals, (2024, 1), (2024, 2))


def test_same_period_comparison_is_rejected():
    with pytest.raises(ValueError, match="must be different"):
        analyze_expenses(*sample_inputs(), (2024, 1), (2024, 1))
