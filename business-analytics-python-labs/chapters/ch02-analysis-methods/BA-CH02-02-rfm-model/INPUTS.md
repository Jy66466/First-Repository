# Input Data

Provide a local workbook containing transaction-level records with these columns:

- `用户编号`: customer key used only for grouping.
- `流水号`: transaction identifier used to count distinct purchases.
- `销售日期`: transaction date.
- `销售金额`: numeric transaction amount.

The workbook is not included. Use only data you are authorized to process. The script does not download data. It calculates aggregate customer segments and does not serialize customer-level records. The reference-answer workbook is optional and must be supplied separately for local validation; it is not needed for normal use and is not distributed.

For public demonstrations, use synthetic or separately licensed data. Tests use hand-constructed synthetic records.
