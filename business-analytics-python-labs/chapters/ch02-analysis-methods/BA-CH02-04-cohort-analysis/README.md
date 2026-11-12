# BA-CH02-04 同期群分析

实验按注册日期建立日同期群，并计算注册后第 N 日的留存率。每个用户在同一注册同期和同一日只计一次；分母是该注册日期的不同注册用户数。总计行按全体不同用户重新计算，不是各同期留存率的简单平均。

```powershell
python run_cohort_analysis.py --input "<authorized.xlsx>"
python -m pytest -q
```

输出 JSON 只记录同期数量和最大观察日，热力图显示聚合留存率。留存反映登录行为，不直接解释流失原因。

