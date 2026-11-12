# BA-CH02-10 分布分析

实验使用均值、五数概括、四分位距和 1.5×IQR 围栏描述连续变量分布，并生成直方图和箱线图。四分位数采用包含端点的线性插值，与工作簿 `QUARTILE.INC` 的可见结果一致。

```powershell
python run_distribution_analysis.py --input "<authorized.xlsx>" --sheet 分布分析 --column "<numeric-column>"
python -m pytest -q
```

原工作簿的演示列标题与复制的数据值存在语义歧义，因此 Python 接口不硬编码“年龄”或“客单价”，由使用者明确指定数值列。异常值是统计标记，不自动认定为错误数据。

