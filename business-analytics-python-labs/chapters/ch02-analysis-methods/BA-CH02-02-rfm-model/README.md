# BA-CH02-02 RFM Model

This lab implements customer-level Recency, Frequency, and Monetary summaries from a locally supplied transaction workbook. The workbook and any answer file are not distributed.

The implementation calculates days since the most recent purchase, counts distinct transaction IDs, sums transaction amounts, and applies configurable analysis date plus the documented mean-threshold classification rules. Exact duplicate-row handling is available only as a separate sensitivity analysis; it does not replace the source-row calculation.

Use data you are authorized to process. Required workbook columns are `用户编号`, `流水号`, `销售日期`, and `销售金额`. The command-line entry point is `run_rfm.py`; tests use synthetic data. Outputs contain aggregate summaries only and must be reviewed before sharing.

```powershell
python run_rfm.py --input "<authorized-local-workbook.xlsx>" --analysis-date YYYY-MM-DD
```

Install the common dependencies from the project-level `environments/requirements-core.txt`. Run `python -m pytest` from this experiment directory. Do not publish answer-derived output or the historical local validation report without rights review.
