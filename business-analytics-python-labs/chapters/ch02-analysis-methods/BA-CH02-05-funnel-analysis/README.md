# BA-CH02-05 漏斗分析

漏斗分析按既定业务流程比较相邻阶段和首阶段的用户转化。相邻阶段转化率为本阶段用户数除以上一阶段用户数，总转化率为本阶段用户数除以首阶段用户数。

```powershell
python run_funnel_analysis.py --input "<authorized.xlsx>" --stage-column 阶段 --count-column 用户数
python -m pytest -q
```

程序要求阶段唯一、顺序明确且人数不随流程增加。图表是流程的静态聚合表达，不等同于 Power BI 或网站交互漏斗。

