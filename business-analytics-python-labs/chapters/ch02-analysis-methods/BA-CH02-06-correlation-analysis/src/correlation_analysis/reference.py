"""Read and compare the workbook's independent correlation reference."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd

from .core import validate_pairs

CHART_NS = "http://schemas.openxmlformats.org/drawingml/2006/chart"
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
DISPLAY_PATTERN = re.compile(
    r"y\s*=\s*([-+]?\d+(?:\.\d+)?)\s*x\s*([+-])\s*(\d+(?:\.\d+)?)\.\s*R(?:²|\^2)\s*=\s*(\d+(?:\.\d+)?)"
)


def read_reference_workbook(path: str | Path, sheet_name: str = "原始数据") -> tuple[pd.DataFrame, dict[str, object]]:
    """Read answer pairs and the rounded linear trendline printed in its chart."""
    pairs = validate_pairs(pd.read_excel(path, sheet_name=sheet_name))
    labels: list[str] = []
    with ZipFile(path) as archive:
        chart_paths = sorted(
            name for name in archive.namelist()
            if name.startswith("xl/charts/chart") and name.endswith(".xml")
        )
        for chart_path in chart_paths:
            root = ET.fromstring(archive.read(chart_path))
            for trendline in root.iter(f"{{{CHART_NS}}}trendline"):
                label = trendline.find(f"{{{CHART_NS}}}trendlineLbl")
                if label is None:
                    continue
                text = "".join(node.text or "" for node in label.iter(f"{{{DRAWING_NS}}}t"))
                if text:
                    labels.append(text)

    for label in labels:
        match = DISPLAY_PATTERN.search(label)
        if match:
            sign = 1 if match.group(2) == "+" else -1
            values = {
                "slope": float(match.group(1)),
                "intercept": sign * float(match.group(3)),
                "r_squared": float(match.group(4)),
            }
            precisions = {
                "slope": len(match.group(1).split(".", maxsplit=1)[1]) if "." in match.group(1) else 0,
                "intercept": len(match.group(3).split(".", maxsplit=1)[1]) if "." in match.group(3) else 0,
                "r_squared": len(match.group(4).split(".", maxsplit=1)[1]) if "." in match.group(4) else 0,
            }
            return pairs, {
                "display_values": values,
                "display_precision_decimal_places": precisions,
                "equation_label": label,
            }
    raise ValueError("No readable linear trendline equation and R-squared label found in the reference workbook")


def compare_reference(
    actual_pairs: pd.DataFrame,
    reference_pairs: pd.DataFrame,
    actual_metrics: dict[str, float | int],
    reference_display: dict[str, object],
) -> dict[str, object]:
    """Compare ordered x/y observations and coefficients to chart-rounded values."""
    actual = validate_pairs(actual_pairs).to_numpy(dtype=float)
    reference = validate_pairs(reference_pairs).to_numpy(dtype=float)
    same_shape = actual.shape == reference.shape
    data_equal = same_shape and bool(np.array_equal(actual, reference))

    expected_values = reference_display["display_values"]
    precisions = reference_display["display_precision_decimal_places"]
    coefficient_differences: dict[str, float] = {}
    coefficient_tolerances: dict[str, float] = {}
    coefficient_matches: dict[str, bool] = {}
    for field in ("slope", "intercept", "r_squared"):
        difference = abs(float(actual_metrics[field]) - float(expected_values[field]))
        tolerance = 0.5 * 10 ** (-int(precisions[field]))
        coefficient_differences[field] = difference
        coefficient_tolerances[field] = tolerance
        coefficient_matches[field] = difference <= tolerance + 1e-12

    return {
        "input_reference_row_count_equal": same_shape,
        "ordered_input_pairs_exactly_equal": data_equal,
        "input_reference_rows": int(len(actual)),
        "reference_chart_equation": reference_display["equation_label"],
        "coefficient_absolute_differences": coefficient_differences,
        "rounding_tolerances_from_chart_precision": coefficient_tolerances,
        "coefficient_matches_chart_rounding": coefficient_matches,
        "passed": data_equal and all(coefficient_matches.values()),
    }
