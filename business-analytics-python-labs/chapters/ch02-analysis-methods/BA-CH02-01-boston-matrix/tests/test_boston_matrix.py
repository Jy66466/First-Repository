import pandas as pd
import pytest

from boston_matrix import classify_position, compute_boston_matrix


def sample_sales():
    return pd.DataFrame({
        "销售日期": ["2024-01-01", "2024-02-01", "2024-01-02", "2024-02-02"],
        "品牌": ["A", "A", "B", "B"],
        "单价": [10, 10, 10, 10],
        "销量": [10, 15, 10, 5],
    })


def test_calculates_share_growth_and_categories():
    result = compute_boston_matrix(sample_sales(), "2024-01", "2024-02").set_index("brand")
    assert result.loc["A", "two_period_sales"] == 250
    assert result.loc["B", "growth_rate"] == pytest.approx(-0.5)
    assert result["market_share"].sum() == pytest.approx(1)
    assert result.loc["A", "category"] == "明星业务"
    assert result.loc["B", "category"] == "瘦狗业务"


def test_equal_thresholds_use_lower_groups():
    assert classify_position(0.5, 0.2, 0.5, 0.2) == "瘦狗业务"
    assert classify_position(0.6, 0.2, 0.5, 0.2) == "现金牛业务"
    assert classify_position(0.5, 0.3, 0.5, 0.2) == "问题业务"


def test_rejects_missing_columns_and_zero_base():
    with pytest.raises(ValueError, match="缺少"):
        compute_boston_matrix(pd.DataFrame({"品牌": ["A"]}), "2024-01", "2024-02")
    data = sample_sales(); data.loc[0, "销量"] = 0
    with pytest.raises(ValueError, match="基期"):
        compute_boston_matrix(data[data["品牌"] == "A"], "2024-01", "2024-02")

