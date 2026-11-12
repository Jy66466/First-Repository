import pandas as pd
import pytest

from cohort_analysis import compute_cohort_analysis


def sample_logins():
    return pd.DataFrame({
        "用户编号": [1, 1, 2, 3, 3, 3],
        "注册日期": ["2024-01-01", "2024-01-01", "2024-01-01", "2024-01-02", "2024-01-02", "2024-01-02"],
        "登录时点": ["2024-01-01 09:00", "2024-01-02 09:00", "2024-01-01 10:00", "2024-01-02 08:00", "2024-01-03 08:00", "2024-01-03 09:00"],
    })


def test_cohort_sizes_and_distinct_retention():
    result = compute_cohort_analysis(sample_logins())
    matrix = result["retention_matrix"]
    assert matrix.loc[pd.Timestamp("2024-01-01"), 0] == 1
    assert matrix.loc[pd.Timestamp("2024-01-01"), 1] == 0.5
    assert matrix.loc[pd.Timestamp("2024-01-02"), 1] == 1
    assert result["overall_retention"].loc[1] == pytest.approx(2 / 3)


def test_duplicate_same_day_login_counts_once():
    data = pd.concat([sample_logins(), sample_logins().iloc[[4]]], ignore_index=True)
    result = compute_cohort_analysis(data)
    assert result["retention_matrix"].loc[pd.Timestamp("2024-01-02"), 1] == 1


def test_rejects_login_before_registration():
    data = sample_logins(); data.loc[0, "登录时点"] = "2023-12-31"
    with pytest.raises(ValueError, match="早于"):
        compute_cohort_analysis(data)

