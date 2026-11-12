from __future__ import annotations

import math

import pandas as pd
import pytest

from etl_clean_merge import (
    clean_order_details,
    horizontal_merge,
    split_delimited_column,
    split_quantity_column,
    vertical_concat,
)


# ---------------------------------------------------------------------------
# 拆分列
# ---------------------------------------------------------------------------

def test_split_delimited_column_expands_rows():
    frame = pd.DataFrame(
        {
            "订单号": "M1,M2,M3",
            "收货地址": "福建省厦门市湖里区",
            "数量": "8件",
        },
        index=[0],
    )
    result = split_delimited_column(frame, "订单号")
    assert len(result) == 3
    assert list(result["订单号"]) == ["M1", "M2", "M3"]
    assert (result["收货地址"] == "福建省厦门市湖里区").all()
    assert (result["数量"] == "8件").all()


def test_split_delimited_column_ignores_blank_items():
    frame = pd.DataFrame({"编号": ["A, ,B,"]})
    result = split_delimited_column(frame, "编号")
    assert list(result["编号"]) == ["A", "B"]


def test_split_delimited_column_missing_column_raises():
    with pytest.raises(KeyError):
        split_delimited_column(pd.DataFrame({"x": [1]}), "订单号")


def test_split_quantity_column_numeric_and_unit():
    frame = pd.DataFrame({"数量": ["8件", "10本", None, "abc"]})
    result = split_quantity_column(frame, "数量")
    values = result["数量_value"]
    assert values.iloc[0] == 8.0 and values.iloc[1] == 10.0
    assert values.iloc[2] is pd.NA and values.iloc[3] is pd.NA
    assert result["数量_unit"].tolist() == ["件", "本", None, "abc"]


def test_split_quantity_column_keeps_decimals():
    frame = pd.DataFrame({"数量": ["3.5kg"]})
    result = split_quantity_column(frame, "数量")
    assert math.isclose(float(result.loc[0, "数量_value"]), 3.5)
    assert result.loc[0, "数量_unit"] == "kg"


# ---------------------------------------------------------------------------
# 数据清洗
# ---------------------------------------------------------------------------

def test_clean_order_details_drops_title_blank_and_duplicates():
    frame = pd.DataFrame(
        {
            "订单号": ["demo title", None, "M1", "M2", "M1"],
            "实付金额": [None, None, "269", "#N/A", "269"],
            "下单数量": [None, None, "1", "0", "1"],
        }
    )
    cleaned = clean_order_details(frame)
    # 标题行整行只有一个非空值且金额为空：按占位行删除规则，
    # 标题行因订单号非空而保留，但金额为 NA；空行与重复行被删除。
    assert len(cleaned) == 3
    assert cleaned.loc[cleaned["订单号"] == "M1", "实付金额"].iloc[0] == 269
    m2 = cleaned.loc[cleaned["订单号"] == "M2"].iloc[0]
    assert pd.isna(m2["实付金额"])


def test_clean_order_details_converts_amount_numeric():
    frame = pd.DataFrame({"订单号": ["A", "B"], "实付金额": ["7.9", "0"]})
    cleaned = clean_order_details(frame)
    assert cleaned["实付金额"].tolist() == [7.9, 0.0]
    assert pd.api.types.is_numeric_dtype(cleaned["实付金额"])


def test_clean_order_details_normalizes_missing_tokens():
    frame = pd.DataFrame({"商品id": ["#N/A", "200018485", "N/A"], "ip地址": ["-911", "#N/A", ""]})
    cleaned = clean_order_details(frame, amount_column="不存在的列")
    assert pd.isna(cleaned.loc[0, "商品id"])
    assert cleaned.loc[1, "商品id"] == "200018485"
    # ``#N/A`` 视为缺失；``-911`` 为非法取值，按口径仅保留原值不做修改。
    assert pd.isna(cleaned.loc[1, "ip地址"])
    assert cleaned.loc[0, "ip地址"] == "-911"


def test_clean_order_details_empty_frame():
    cleaned = clean_order_details(pd.DataFrame({"订单号": [], "实付金额": []}))
    assert cleaned.empty


# ---------------------------------------------------------------------------
# 纵向合并
# ---------------------------------------------------------------------------

def test_vertical_concat_same_fields():
    q1 = pd.DataFrame({"门店": ["A1"], "销售数量": [8], "销售额": [200]})
    q2 = pd.DataFrame({"门店": ["A"], "销售数量": [2], "销售额": [100]})
    merged = vertical_concat(q1, q2)
    assert len(merged) == 2
    assert list(merged.columns) == ["门店", "销售数量", "销售额"]


def test_vertical_concat_rename_inconsistent_fields():
    q1 = pd.DataFrame({"门店": ["A1"], "销售数量": [8], "销售额": [200]})
    q2 = pd.DataFrame({"门店": ["A"], "销售数量": [2], "金额": [100]})
    merged = vertical_concat(q1, q2, rename_map={"金额": "销售额"})
    assert list(merged.columns) == ["门店", "销售数量", "销售额"]
    assert merged["销售额"].tolist() == [200, 100]


def test_vertical_concat_unknown_rename_key_raises():
    with pytest.raises(KeyError):
        vertical_concat(
            pd.DataFrame({"a": [1]}),
            pd.DataFrame({"a": [2]}),
            rename_map={"不存在": "a"},
        )


# ---------------------------------------------------------------------------
# 横向合并
# ---------------------------------------------------------------------------

@pytest.fixture()
def school_tables() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    course = pd.DataFrame(
        {"课程号": ["C01", "C02", "C03"], "课程名": ["数据结构", "古代文学", "计算机基础"], "学分": [4, 4, 3.5]}
    )
    student = pd.DataFrame(
        {"学号": [20080101, 20080201], "姓名": ["学生甲", "学生乙"], "系别": ["中文系", "数学系"]}
    )
    elective = pd.DataFrame(
        {"学号": [20080101, 20080101, 20080201], "课程号": ["C02", "C03", "C99"], "成绩": [85, 75.8, 90]}
    )
    return course, student, elective


def test_horizontal_merge_inner_join(school_tables):
    course, _, elective = school_tables
    merged = horizontal_merge(elective, course, on="课程号", how="inner")
    # C99 在课程表中不存在，内连接后应被剔除。
    assert len(merged) == 2
    assert (merged["课程名"] == ["古代文学", "计算机基础"]).all()


def test_horizontal_merge_left_join_keeps_unmatched(school_tables):
    course, _, elective = school_tables
    merged = horizontal_merge(elective, course, on="课程号", how="left")
    assert len(merged) == 3
    unmatched = merged.loc[merged["课程号"] == "C99"]
    assert pd.isna(unmatched["课程名"].iloc[0])


def test_horizontal_merge_three_tables(school_tables):
    course, student, elective = school_tables
    step1 = horizontal_merge(elective, course, on="课程号", how="inner")
    step2 = horizontal_merge(step1, student, on="学号", how="left")
    assert list(step2.columns) == ["学号", "课程号", "成绩", "课程名", "学分", "姓名", "系别"]
    assert step2.loc[step2["学号"] == 20080101, "姓名"].nunique() == 1


def test_horizontal_merge_missing_key_raises(school_tables):
    course, _, _ = school_tables
    with pytest.raises(KeyError):
        horizontal_merge(course, course, on="不存在")
