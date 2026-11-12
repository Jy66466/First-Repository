from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from correlation_analysis.core import analyze_correlation, validate_pairs
from correlation_analysis.reference import compare_reference


def test_known_paired_data_produces_expected_pearson_and_trendline():
    pairs = pd.DataFrame({"x": [1, 2, 3, 4], "y": [1, 3, 2, 4]})
    result = analyze_correlation(pairs)
    assert result["observation_count"] == 4
    assert result["pearson_r"] == pytest.approx(0.8, abs=1e-12)
    assert result["slope"] == pytest.approx(0.8, abs=1e-12)
    assert result["intercept"] == pytest.approx(0.5, abs=1e-12)
    assert result["r_squared"] == pytest.approx(0.64, abs=1e-12)


def test_perfect_positive_and_negative_correlations_have_expected_sign():
    assert analyze_correlation(pd.DataFrame({"x": [1, 2, 3], "y": [3, 5, 7]}))["pearson_r"] == pytest.approx(1.0)
    assert analyze_correlation(pd.DataFrame({"x": [1, 2, 3], "y": [7, 5, 3]}))["pearson_r"] == pytest.approx(-1.0)


def test_duplicate_observations_are_preserved_as_weighted_pairs():
    pairs = pd.DataFrame({"x": [1, 2, 3, 4, 4], "y": [1, 3, 2, 4, 4]})
    validated = validate_pairs(pairs)
    result = analyze_correlation(pairs)
    assert len(validated) == 5
    assert result["observation_count"] == 5
    assert pairs.duplicated().sum() == 1


@pytest.mark.parametrize(
    "pairs, message",
    [
        (pd.DataFrame({"x": [1, 2], "z": [3, 4]}), "Missing required columns"),
        (pd.DataFrame({"x": [1, None], "y": [2, 3]}), "finite, non-missing"),
        (pd.DataFrame({"x": [1, 2], "y": [2, "bad"]}), "finite, non-missing"),
        (pd.DataFrame({"x": [1, np.inf], "y": [2, 3]}), "finite, non-missing"),
        (pd.DataFrame({"x": [1], "y": [2]}), "At least two"),
        (pd.DataFrame({"x": [1, 1, 1], "y": [2, 3, 4]}), "x has zero variance"),
        (pd.DataFrame({"x": [1, 2, 3], "y": [4, 4, 4]}), "y has zero variance"),
    ],
)
def test_invalid_inputs_are_rejected(pairs, message):
    with pytest.raises(ValueError, match=message):
        analyze_correlation(pairs)


def test_reference_comparison_accepts_chart_rounding_and_rejects_bad_coefficients():
    pairs = pd.DataFrame({"x": [1, 2, 3, 4], "y": [1, 3, 2, 4]})
    metrics = analyze_correlation(pairs)
    reference = {"slope": 0.8, "intercept": 0.5, "r_squared": 0.64}
    precision = {"slope": 1, "intercept": 1, "r_squared": 2}
    displayed = {"display_values": reference, "display_precision_decimal_places": precision, "equation_label": "y = 0.8x + 0.5. R² = 0.64"}
    passed = compare_reference(pairs, pairs.copy(), metrics, displayed)
    assert passed["ordered_input_pairs_exactly_equal"] is True
    assert passed["passed"] is True

    wrong = dict(displayed)
    wrong["display_values"] = {**reference, "slope": 0.95}
    failed = compare_reference(pairs, pairs.copy(), metrics, wrong)
    assert failed["coefficient_matches_chart_rounding"]["slope"] is False
    assert failed["passed"] is False


def test_reference_comparison_rejects_changed_observation():
    pairs = pd.DataFrame({"x": [1, 2, 3, 4], "y": [1, 3, 2, 4]})
    changed = pairs.copy()
    changed.loc[0, "y"] = 99
    metrics = analyze_correlation(pairs)
    display = {
        "display_values": {"slope": 0.8, "intercept": 0.5, "r_squared": 0.64},
        "display_precision_decimal_places": {"slope": 1, "intercept": 1, "r_squared": 2},
        "equation_label": "y = 0.8x + 0.5. R² = 0.64",
    }
    result = compare_reference(pairs, changed, metrics, display)
    assert result["ordered_input_pairs_exactly_equal"] is False
    assert result["passed"] is False
