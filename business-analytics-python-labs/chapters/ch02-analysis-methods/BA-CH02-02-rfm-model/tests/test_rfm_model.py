from __future__ import annotations

import pandas as pd
import pytest

from rfm_model.core import SEGMENT_MAP, compute_rfm, validate_transactions
from rfm_model.quality import analyze_duplicate_sensitivity
from rfm_model.reference import compare_reference, read_reference
from rfm_model.cli import read_transactions


ANALYSIS_DATE = "2020-01-04"


def small_transactions() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ["A", "A-1", "2020-01-03", 10.0],
            ["B", "B-1", "2020-01-02", 10.0],
            ["B", "B-2", "2020-01-02", 10.0],
            ["C", "C-1", "2020-01-01", 10.0],
            ["C", "C-2", "2020-01-01", 10.0],
            ["C", "C-3", "2020-01-01", 10.0],
        ],
        columns=["用户编号", "流水号", "销售日期", "销售金额"],
    )


def independent_reference() -> pd.DataFrame:
    """Hand-authored answer rows independent of compute_rfm output."""
    return pd.DataFrame(
        [
            ["A", pd.Timestamp("2020-01-03"), 1, 10.0, 1, "高", "低", "低", "一般发展用户"],
            ["B", pd.Timestamp("2020-01-02"), 2, 20.0, 2, "低", "低", "低", "一般挽留用户"],
            ["C", pd.Timestamp("2020-01-01"), 3, 30.0, 3, "低", "高", "高", "重要保持用户"],
        ],
        columns=[
            "customer_id", "last_purchase_date", "frequency", "monetary",
            "recency_days", "r_label", "f_label", "m_label", "segment",
        ],
    )


def test_reads_excel_input_and_checks_required_fields(tmp_path):
    path = tmp_path / "small.xlsx"
    with pd.ExcelWriter(path) as writer:
        small_transactions().to_excel(writer, sheet_name="原始数据", index=False)
    loaded = read_transactions(path)
    checked = validate_transactions(loaded)
    assert len(checked) == 6
    assert set(checked.columns) == {"用户编号", "流水号", "销售日期", "销售金额"}


def test_customer_aggregation_calculates_recency_distinct_flows_and_amount():
    result = compute_rfm(small_transactions(), ANALYSIS_DATE).set_index("customer_id")
    assert result.loc["A", "last_purchase_date"] == pd.Timestamp("2020-01-03")
    assert result.loc["A", "recency_days"] == 1
    assert result.loc["B", "frequency"] == 2
    assert result.loc["C", "frequency"] == 3
    assert result.loc["C", "monetary"] == 30


def test_mean_thresholds_and_equality_are_strictly_low():
    result = compute_rfm(small_transactions(), ANALYSIS_DATE).set_index("customer_id")
    assert result.loc["B", "recency_days"] == 2  # R mean is 2; equality is low.
    assert result.loc["B", "frequency"] == 2  # F mean is 2; equality is low.
    assert result.loc["B", "monetary"] == 20  # M mean is 20; equality is low.
    assert (result.loc["B", ["r_label", "f_label", "m_label"]] == "低").all()
    assert result.loc["A", "r_label"] == "高"
    assert result.loc["C", "f_label"] == "高"
    assert result.loc["C", "m_label"] == "高"


def test_eight_segment_mapping_is_complete_and_correct():
    assert len(SEGMENT_MAP) == 8
    assert SEGMENT_MAP["高高高"] == "重要价值用户"
    assert SEGMENT_MAP["高低高"] == "重要发展用户"
    assert SEGMENT_MAP["低高高"] == "重要保持用户"
    assert SEGMENT_MAP["低低高"] == "重要挽留用户"
    assert SEGMENT_MAP["高高低"] == "一般价值用户"
    assert SEGMENT_MAP["高低低"] == "一般发展用户"
    assert SEGMENT_MAP["低高低"] == "一般保持用户"
    assert SEGMENT_MAP["低低低"] == "一般挽留用户"
    result = compute_rfm(small_transactions(), ANALYSIS_DATE).set_index("customer_id")
    assert result.loc["B", "segment"] == "一般挽留用户"


def test_independent_reference_with_same_customer_set_matches():
    actual = compute_rfm(small_transactions(), ANALYSIS_DATE)
    comparison = compare_reference(actual, independent_reference())
    assert comparison["matched_customers"] == 3
    assert comparison["python_only_customers"] == 0
    assert comparison["reference_only_customers"] == 0
    assert all(count == 0 for count in comparison["mismatch_counts"].values())
    assert "customer_id" not in str(comparison)


def test_reference_missing_customer_is_reported():
    actual = compute_rfm(small_transactions(), ANALYSIS_DATE)
    reference = independent_reference().loc[lambda frame: frame["customer_id"] != "C"]
    comparison = compare_reference(actual, reference)
    assert comparison["python_only_customers"] == 1
    assert comparison["reference_only_customers"] == 0
    assert comparison["passed"] is False


def test_reference_extra_customer_is_reported():
    actual = compute_rfm(small_transactions(), ANALYSIS_DATE)
    extra = pd.DataFrame(
        [["D", pd.Timestamp("2020-01-01"), 1, 1.0, 3, "低", "低", "低", "一般挽留用户"]],
        columns=independent_reference().columns,
    )
    comparison = compare_reference(actual, pd.concat([independent_reference(), extra], ignore_index=True))
    assert comparison["python_only_customers"] == 0
    assert comparison["reference_only_customers"] == 1
    assert comparison["passed"] is False


def test_reference_metric_mismatch_is_counted():
    actual = compute_rfm(small_transactions(), ANALYSIS_DATE)
    reference = independent_reference()
    reference.loc[reference["customer_id"] == "B", "frequency"] = 9
    comparison = compare_reference(actual, reference)
    assert comparison["mismatch_counts"]["frequency"] == 1
    assert comparison["passed"] is False


def test_reference_reader_uses_cached_values_without_requiring_source_data(tmp_path):
    expected = independent_reference()
    reference = pd.DataFrame(
        {
            "用户编号": expected["customer_id"],
            "最近一次消费日期": expected["last_purchase_date"],
            "消费频次": expected["frequency"],
            "消费金额": expected["monetary"],
            "消费时间间隔": expected["recency_days"],
            "R程度": expected["r_label"],
            "F程度": expected["f_label"],
            "M程度": expected["m_label"],
            "用户类别": expected["segment"],
        }
    )
    path = tmp_path / "reference.xlsx"
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame([[None] * 9 for _ in range(5)]).to_excel(writer, sheet_name="参考答案", index=False, header=False)
        reference.to_excel(writer, sheet_name="参考答案", index=False, startrow=5)
    loaded = read_reference(path)
    comparison = compare_reference(compute_rfm(small_transactions(), ANALYSIS_DATE), loaded)
    assert comparison["passed"] is True


def test_exact_duplicates_are_reported_as_sensitivity_not_removed_from_reproduction():
    data = pd.concat([small_transactions(), small_transactions().iloc[[0]]], ignore_index=True)
    report = analyze_duplicate_sensitivity(data, ANALYSIS_DATE)
    assert report["exact_duplicate_extra_rows"] == 1
    assert report["rows_after_exact_deduplication"] == 6
    assert report["distinct_flow_ids_before_deduplication"] == report["distinct_flow_ids_after_deduplication"]
    assert report["customer_flow_combinations_before_deduplication"] == 6
    assert report["customer_flow_combinations_after_deduplication"] == 6
    assert report["frequency_row_count_vs_distinct_flow"]["customers_with_different_counts"] == 1
    assert report["retained_vs_deduplicated"]["customers_with_changed_metric_or_segment"]["R_recency_days"] == 0
    assert report["retained_vs_deduplicated"]["customers_with_changed_metric_or_segment"]["F_distinct_flows"] == 0
    assert "invalid" in report["interpretation_limit"]


def test_duplicate_detection_uses_every_source_column():
    data = small_transactions().assign(product_group="same")
    data.loc[1, "product_group"] = "different-but-same-rfm-fields"
    report = analyze_duplicate_sensitivity(data, ANALYSIS_DATE)
    assert report["exact_duplicate_extra_rows"] == 0


def test_multiline_same_flow_and_exact_duplicate_are_separate_cases():
    rows = [
        ["A", "T1", "2020-01-03", 10.0, "苹果"],
        ["A", "T1", "2020-01-03", 15.0, "香蕉"],
        ["A", "T2", "2020-01-02", 5.0, "茶"],
        ["B", "T1", "2020-01-02", 20.0, "咖啡"],
        ["B", "T2", "2020-01-01", 30.0, "米"],
        ["A", "T1", "2020-01-03", 10.0, "苹果"],
    ]
    data = pd.DataFrame(rows, columns=["用户编号", "流水号", "销售日期", "销售金额", "商品"])
    reproduction = compute_rfm(data, ANALYSIS_DATE).set_index("customer_id")
    sensitivity = analyze_duplicate_sensitivity(data, ANALYSIS_DATE)

    assert reproduction.loc["A", "frequency"] == 2
    assert reproduction.loc["A", "monetary"] == 40.0
    assert sensitivity["raw_transaction_detail_rows"] == 6
    assert sensitivity["exact_duplicate_extra_rows"] == 1
    assert sensitivity["rows_in_duplicate_groups"] == 2
    assert sensitivity["rows_after_exact_deduplication"] == 5
    assert sensitivity["distinct_flow_ids_before_deduplication"] == 2
    assert sensitivity["customer_flow_combinations_before_deduplication"] == 4
    assert sensitivity["customer_flow_combinations_after_deduplication"] == 4
    assert sensitivity["frequency_row_count_vs_distinct_flow"]["raw_detail_rows_minus_customer_flow_combinations"] == 2
    retained = sensitivity["retained_vs_deduplicated"]["retained"]
    deduplicated = sensitivity["retained_vs_deduplicated"]["deduplicated"]
    assert retained["monetary_total_source_units"] == 90.0
    assert deduplicated["monetary_total_source_units"] == 80.0
    assert sensitivity["retained_vs_deduplicated"]["customers_with_changed_metric_or_segment"]["M_amount"] == 1
    assert sensitivity["retained_vs_deduplicated"]["customers_with_changed_metric_or_segment"]["F_distinct_flows"] == 0


def test_monetary_comparison_respects_absolute_tolerance_boundary():
    actual = compute_rfm(small_transactions(), ANALYSIS_DATE)
    reference = independent_reference()

    within = reference.copy()
    within.loc[within["customer_id"] == "B", "monetary"] += 0.5e-8
    within_result = compare_reference(actual, within)
    assert within_result["mismatch_counts"]["monetary"] == 0
    assert within_result["passed"] is True

    outside = reference.copy()
    outside.loc[outside["customer_id"] == "B", "monetary"] += 1.01e-8
    outside_result = compare_reference(actual, outside)
    assert outside_result["mismatch_counts"]["monetary"] == 1
    assert outside_result["passed"] is False


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda df: df.drop(columns=["销售日期"]), "缺少必需字段"),
        (lambda df: df.assign(用户编号=[None] + list(df["用户编号"].iloc[1:])), "存在缺失值"),
        (lambda df: df.assign(销售日期=["not-a-date"] + list(df["销售日期"].iloc[1:])), "无法解析"),
        (lambda df: df.assign(销售金额=["not-a-number"] + list(df["销售金额"].iloc[1:])), "有限数值"),
    ],
)
def test_invalid_inputs_fail_with_actionable_errors(mutate, message):
    with pytest.raises(ValueError, match=message):
        validate_transactions(mutate(small_transactions()))


def test_empty_input_and_duplicate_reference_keys_are_rejected():
    with pytest.raises(ValueError, match="没有交易记录"):
        validate_transactions(small_transactions().iloc[0:0])
    result = compute_rfm(small_transactions(), ANALYSIS_DATE)
    duplicated = pd.concat([result, result.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="重复客户键"):
        compare_reference(result, duplicated)


def test_analysis_date_cannot_precede_a_transaction():
    with pytest.raises(ValueError, match="晚于分析日"):
        compute_rfm(small_transactions(), "2020-01-02")
