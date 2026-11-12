# BA-CH02-06 Correlation Analysis

This lab calculates Pearson correlation and a simple least-squares trend line for paired numeric observations. It accepts a local workbook with numeric `x` and `y` columns and does not distribute the original input or answer workbook.

The implementation validates missing and non-finite values, retains repeated observations, and reports correlation, slope, intercept, and R-squared. Correlation describes association and does not establish causation. Since the source variables' domain definitions and units are not established, no domain-specific interpretation is included.

Use data you are authorized to process. The command-line entry point is `run_correlation.py`; tests use synthetic data. Outputs are local and should be reviewed before sharing.

```powershell
python run_correlation.py --input "<authorized-local-workbook.xlsx>" --sheet "<sheet-name>"
```

Install common dependencies from the project-level `environments/requirements-core.txt` and run `python -m pytest` from this experiment directory.
