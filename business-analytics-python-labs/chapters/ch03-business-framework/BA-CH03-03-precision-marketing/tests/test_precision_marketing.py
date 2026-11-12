import pandas as pd
import pytest

from precision_marketing import analyze_marketing


def sample_customers():
    return pd.DataFrame({
        "客户ID": [1, 2, 3, 4, 5],
        "性别": ["Female", "Female", "Female", "Male", "Female"],
        "年龄": [18, 25, 50, 36, 35],
        "品类": ["Books", "Clothing", "Cosmetics", "Books", "Clothing"],
        "数量": [1, 1, 2, 1, 1],
        "支付方式": ["Card", "Alipay", "Card", "Card", "WeChat Pay"],
        "订单月份": [1, 1, 1, 1, 1],
        "订单年份": [2024] * 5,
    })


def test_age_boundaries_and_target_drilldown():
    result = analyze_marketing(sample_customers(), target_categories=["Cosmetics"])
    female = result["age_by_gender"].loc["Female"]
    assert female["18-25岁"] == 2
    assert female["26-35岁"] == 1
    assert female["50岁以上"] == 1
    assert result["category_counts"].to_dict() == {"Cosmetics": 1}
    assert result["payment_counts"].to_dict() == {"Card": 1}


def test_gender_counts_are_customer_counts():
    result = analyze_marketing(sample_customers())
    assert result["gender_counts"].to_dict() == {"Female": 4, "Male": 1}


def test_rejects_duplicate_customers_and_underage_values():
    data = sample_customers(); data.loc[1, "客户ID"] = 1
    with pytest.raises(ValueError, match="必须唯一"):
        analyze_marketing(data)
    data = sample_customers(); data.loc[0, "年龄"] = 17
    with pytest.raises(ValueError, match="不小于 18"):
        analyze_marketing(data)

