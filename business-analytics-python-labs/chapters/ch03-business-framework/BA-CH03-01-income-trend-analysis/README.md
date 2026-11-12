# BA-CH03-01 收入趋势分析

实验从年度、比较期月度、两年同月、省份和重点省份五个层次拆解销售额变化。Python 按原始明细独立聚合，不读取准备区生成结果。

工作簿中名为“同比增长率”的可见公式是 `(比较期-基期)/比较期`，与常见的基期分母定义不同。本实现为复现实验保留该公式，并在字段名和输出中标记为 `reference_growth`，不把它冒充通用同比定义。比较期为零时沿用参考表的零值约定。

```powershell
python run_income_trend.py --input "<authorized.xlsx>" --base-year 2019 --comparison-year 2020
python -m pytest -q
```

图表和 JSON 仅包含聚合结果。销售变化本身不能证明因果原因。

