# BA-CH03-03 电商平台精准营销

实验按性别、年龄段、品类和支付方式逐层缩小目标客户范围。年龄段为 18-25、26-35、36-49 和 50 岁以上；客户按唯一客户 ID 计数。

```powershell
python run_precision_marketing.py --input "<authorized.xlsx>" --target-gender Female --target-age-band "50岁以上" --target-categories Clothing Cosmetics
python -m pytest -q
```

本地参考工作簿中，性别总数、目标年龄段的品类分布和支付方式分布可由原始数据复现；女性年龄段汇总区与其筛选标签不一致，Python 保留独立重算结果并在 P1.1 报告中记录差异，不修改或迁就参考表。聚合分层用于描述人群，不证明营销效果或因果关系。

