import pandas as pd
import pytest

from distribution_analysis import summarize_distribution


def test_linear_quartiles_and_outliers():
    result = summarize_distribution(pd.Series([1, 2, 3, 4, 5, 100]))
    assert result["mean"] == pytest.approx(19.1666666667)
    assert result["q1"] == pytest.approx(2.25)
    assert result["median"] == pytest.approx(3.5)
    assert result["q3"] == pytest.approx(4.75)
    assert result["outlier_count"] == 1


def test_constant_values_have_zero_iqr():
    result = summarize_distribution(pd.Series([5, 5, 5]))
    assert result["iqr"] == 0
    assert result["outlier_count"] == 0


def test_rejects_missing_or_non_numeric_values():
    with pytest.raises(ValueError, match="有限数值"):
        summarize_distribution(pd.Series([1, None, 2]))
    with pytest.raises(ValueError, match="有限数值"):
        summarize_distribution(pd.Series(["x"]))

