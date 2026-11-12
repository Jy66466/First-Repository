import pandas as pd
import pytest

from spreadsheet_operations import grade_lookup, multiplication_table, summarize_sales


def sample_sales():
    return pd.DataFrame({
        "销售地区": ["北京", "北京", "济南"],
        "销售人员": ["甲", "乙", "甲"],
        "品名": ["A", "A", "B"],
        "数量": [2, 3, 4],
        "单价": [10, 10, 5],
    })


def test_sales_summary_and_region_filter():
    result = summarize_sales(sample_sales(), "北京")
    assert result["by_person"]["数量总计"].sum() == 5
    assert result["by_product"]["销售金额总计"].sum() == 50
    with pytest.raises(ValueError, match="没有销售记录"):
        summarize_sales(sample_sales(), "上海")


def test_approximate_grade_lookup_boundaries():
    grades = grade_lookup(pd.Series([0, 59.9, 60, 70, 80, 90, 100]))
    assert grades.tolist() == ["不及格", "不及格", "及格", "可以", "良好", "优秀", "优秀"]


def test_multiplication_table_matches_single_formula_pattern():
    table = multiplication_table(3)
    assert table.loc[1, 1] == "1*1=1"
    assert table.loc[2, 2] == "2*2=4"
    assert table.loc[1, 2] == ""

