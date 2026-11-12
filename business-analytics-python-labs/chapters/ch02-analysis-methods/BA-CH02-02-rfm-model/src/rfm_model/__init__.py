"""RFM experiment implementation for BA-CH02-02."""

from .core import RFM_COLUMNS, compute_rfm, validate_transactions
from .quality import analyze_duplicate_sensitivity

__all__ = ["RFM_COLUMNS", "compute_rfm", "validate_transactions", "analyze_duplicate_sensitivity"]
