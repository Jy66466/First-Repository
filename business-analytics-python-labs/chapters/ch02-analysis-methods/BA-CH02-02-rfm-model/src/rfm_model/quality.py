"""Aggregate-only sensitivity analysis for exact duplicate transaction rows."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .core import CUSTOMER_ID, FLOW_ID, compute_rfm, validate_transactions


def analyze_duplicate_sensitivity(
    transactions: pd.DataFrame, analysis_date: str | pd.Timestamp
) -> dict[str, object]:
    """Compare keep-all and exact-row-deduplicated results without exposing IDs."""
    data = validate_transactions(transactions)
    duplicate_mask = transactions.duplicated(keep="first")
    duplicate_involvement = transactions.duplicated(keep=False)
    kept = compute_rfm(data, analysis_date).set_index("customer_id")
    distinct_rows = validate_transactions(transactions.loc[~duplicate_mask].copy())
    deduplicated = compute_rfm(distinct_rows, analysis_date).set_index("customer_id")
    aligned = kept.join(deduplicated, lsuffix="_kept", rsuffix="_deduplicated", how="outer")

    changed = {
        "R_recency_days": int((aligned["recency_days_kept"] != aligned["recency_days_deduplicated"]).sum()),
        "F_distinct_flows": int((aligned["frequency_kept"] != aligned["frequency_deduplicated"]).sum()),
        "M_amount": int(
            (~np.isclose(
                aligned["monetary_kept"].astype(float),
                aligned["monetary_deduplicated"].astype(float),
                rtol=0,
                atol=1e-8,
            )).sum()
        ),
        "segment": int((aligned["segment_kept"] != aligned["segment_deduplicated"]).sum()),
    }
    row_counts = data.groupby(CUSTOMER_ID).size()
    distinct_flow_counts = data.groupby(CUSTOMER_ID)[FLOW_ID].nunique()
    deduplicated_flow_counts = distinct_rows.groupby(CUSTOMER_ID)[FLOW_ID].nunique()
    row_count_vs_distinct_flow_mismatches = int(
        row_counts.ne(distinct_flow_counts).sum()
    )
    customer_flow_combinations_before = int(distinct_flow_counts.sum())
    customer_flow_combinations_after = int(deduplicated_flow_counts.sum())
    total_row_count_excess = int(len(data) - customer_flow_combinations_before)

    def metric_snapshot(frame: pd.DataFrame) -> dict[str, float]:
        return {
            "R_mean_days": float(frame["recency_days"].mean()),
            "F_mean_distinct_flows": float(frame["frequency"].mean()),
            "M_mean_source_amount_units": float(frame["monetary"].mean()),
            "monetary_total_source_units": float(frame["monetary"].sum()),
        }

    return {
        "duplicate_definition": "Exact equality across every source column; keep first when deduplicating.",
        "source_rows": int(len(data)),
        "raw_transaction_detail_rows": int(len(data)),
        "exact_duplicate_extra_rows": int(duplicate_mask.sum()),
        "rows_in_duplicate_groups": int(duplicate_involvement.sum()),
        "rows_after_exact_deduplication": int(len(distinct_rows)),
        "distinct_flow_ids_before_deduplication": int(data[FLOW_ID].nunique()),
        "distinct_flow_ids_after_deduplication": int(distinct_rows[FLOW_ID].nunique()),
        "customer_flow_combinations_before_deduplication": customer_flow_combinations_before,
        "customer_flow_combinations_after_deduplication": customer_flow_combinations_after,
        "customers_with_duplicate_rows": int(transactions.loc[duplicate_mask, CUSTOMER_ID].nunique()),
        "frequency_row_count_vs_distinct_flow": {
            "customers_with_different_counts": row_count_vs_distinct_flow_mismatches,
            "raw_detail_rows_minus_customer_flow_combinations": total_row_count_excess,
            "note": "Customer-flow combinations are the sum of distinct flow counts within each customer. Their count can differ from global distinct flow IDs if an ID is reused across customers. The row/combinations difference is not attributed solely to exact duplicates.",
        },
        "retained_vs_deduplicated": {
            "retained": metric_snapshot(kept.reset_index()),
            "deduplicated": metric_snapshot(deduplicated.reset_index()),
            "customers_with_changed_metric_or_segment": changed,
            "segment_change_rate": float(changed["segment"] / len(aligned)) if len(aligned) else 0.0,
            "segment_counts_retained": {
                str(k): int(v) for k, v in kept["segment"].value_counts().sort_index().items()
            },
            "segment_counts_deduplicated": {
                str(k): int(v)
                for k, v in deduplicated["segment"].value_counts().sort_index().items()
            },
        },
        "interpretation_limit": "Exact duplicate rows are a data-quality signal, not proof of invalid transactions. Deduplication is a sensitivity scenario and does not replace the textbook reproduction result.",
    }
