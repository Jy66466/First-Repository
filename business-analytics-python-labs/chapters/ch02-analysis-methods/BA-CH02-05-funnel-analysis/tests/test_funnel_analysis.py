import pandas as pd
import pytest

from funnel_analysis import compute_funnel


def test_stage_and_overall_conversion():
    result = compute_funnel(pd.DataFrame({"阶段": ["访问", "注册", "购买"], "用户数": [100, 80, 40]}))
    assert result["stage_conversion"].tolist() == pytest.approx([1, 0.8, 0.5])
    assert result["overall_conversion"].tolist() == pytest.approx([1, 0.8, 0.4])
    assert result["stage_dropoff"].tolist() == pytest.approx([0, 20, 40])


def test_zero_later_stage_is_valid():
    result = compute_funnel(pd.DataFrame({"阶段": ["访问", "购买"], "用户数": [10, 0]}))
    assert result["overall_conversion"].iloc[-1] == 0


def test_rejects_increasing_or_duplicate_stages():
    with pytest.raises(ValueError, match="不得随流程增加"):
        compute_funnel(pd.DataFrame({"阶段": ["A", "B"], "用户数": [10, 11]}))
    with pytest.raises(ValueError, match="唯一"):
        compute_funnel(pd.DataFrame({"阶段": ["A", "A"], "用户数": [10, 5]}))

