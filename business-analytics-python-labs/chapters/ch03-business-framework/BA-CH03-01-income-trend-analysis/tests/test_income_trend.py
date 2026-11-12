import pandas as pd
import pytest

from income_trend import analyze_income


def sample_income():
    return pd.DataFrame({
        "订单年份": [2023, 2024, 2023, 2024, 2024],
        "订单月份": [1, 1, 2, 2, 2],
        "销售省份": ["甲", "甲", "甲", "甲", "乙"],
        "销售额": [80, 100, 50, 100, 50],
    })


def test_yearly_monthly_and_reference_growth():
    result = analyze_income(sample_income(), 2023, 2024, focus_month=2, focus_province="甲")
    assert result["yearly"].to_dict() == {2023: 130, 2024: 250}
    monthly = result["monthly_year_over_year"]
    assert monthly.loc[1, "reference_growth"] == pytest.approx(0.2)
    assert monthly.loc[2, "reference_growth"] == pytest.approx((150 - 50) / 150)
    assert result["focus_month_by_province"].loc["乙", "reference_growth"] == 1


def test_zero_comparison_uses_workbook_zero_convention():
    data = sample_income(); data = data[data["订单年份"] == 2023]
    result = analyze_income(data, 2023, 2024)
    assert result["monthly_year_over_year"].loc[1, "reference_growth"] == 0


def test_rejects_invalid_month_and_missing_columns():
    data = sample_income(); data.loc[0, "订单月份"] = 13
    with pytest.raises(ValueError, match="1 至 12"):
        analyze_income(data, 2023, 2024)
    with pytest.raises(ValueError, match="缺少"):
        analyze_income(pd.DataFrame({"销售额": [1]}), 2023, 2024)

