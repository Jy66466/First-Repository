import pandas as pd
import pytest

from customer_loyalty import analyze_customer_loyalty


def transactions():
    rows = []
    def add(customer, dates, amounts):
        for i, (date, amount) in enumerate(zip(dates, amounts, strict=True), 1):
            rows.append([f"{customer}-{i}", customer, date, amount])
    add("potential", ["2020-12-01"], [100])
    add("risk", ["2020-01-01"], [100])
    add("low", ["2020-09-01", "2020-12-01"], [10, 10])
    add("middle", ["2020-09-01", "2020-11-01", "2020-12-01"], [20, 20, 20])
    add("high", ["2020-08-01", "2020-09-01", "2020-10-15", "2020-11-01"], [100, 100, 100, 100])
    return pd.DataFrame(rows, columns=["订单编号", "会员编号", "消费日期", "消费金额"])


def test_special_status_and_scoring_are_independent():
    result = analyze_customer_loyalty(transactions(), "2021-01-01")
    customers = result["customers"].set_index("会员编号")
    scores = result["eligible_scores"].set_index("会员编号")
    assert customers.loc["potential", "special_status"] == "潜在用户"
    assert customers.loc["risk", "special_status"] == "易流失用户"
    assert set(scores.index) == {"low", "middle", "high"}
    assert scores.loc["high", "loyalty_segment"] == "忠诚用户"


def test_distinct_orders_and_equal_quartile_boundary():
    data = transactions()
    duplicate = data.iloc[[2]].copy()
    data = pd.concat([data, duplicate], ignore_index=True)
    result = analyze_customer_loyalty(data, "2021-01-01")
    scores = result["eligible_scores"].set_index("会员编号")
    assert scores.loc["low", "frequency"] == 2
    assert scores.loc["middle", "frequency_score"] == 2


def test_rejects_future_and_missing_data():
    data = transactions(); data.loc[0, "消费日期"] = "2022-01-01"
    with pytest.raises(ValueError, match="晚于"):
        analyze_customer_loyalty(data, "2021-01-01")
    with pytest.raises(ValueError, match="缺少"):
        analyze_customer_loyalty(pd.DataFrame({"会员编号": [1]}), "2021-01-01")

