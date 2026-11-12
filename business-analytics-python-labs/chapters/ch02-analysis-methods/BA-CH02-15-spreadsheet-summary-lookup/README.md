# BA-CH02-15 数据汇总、引用与查找

该工作簿包含多个电子表格练习。Python 版本保留其中可验证的数据分析逻辑：销售金额计算与分组汇总、近似等级查找，以及可复核的九九乘法表生成。条件格式属于展示规则，不把单元格着色机械翻译成业务计算。

```powershell
python run_spreadsheet_operations.py --input "<authorized.xlsx>" --region 济南
python -m pytest -q
```

`summarize_sales` 可按地区筛选并按销售人员、品名汇总。`grade_lookup` 明确实现 Excel 近似查找的下限阈值规则。公开仓库不包含学生成绩或教材工作簿。

