# 实验索引

此索引只列出已经实现的正式实验。原始候选及来源路径继续以本地阶段清单为依据，不复制敏感路径到公开目录。

| 编号 | 章节 | 名称 | 目录 | 实现与验证状态 |
| --- | --- | --- | --- | --- |
| BA-CH02-01 | 第 2 章 | 波士顿矩阵 | `chapters/ch02-analysis-methods/BA-CH02-01-boston-matrix/` | 完成；30 项参考检查一致 |
| BA-CH02-02 | 第 2 章 | RFM 模型 | `chapters/ch02-analysis-methods/BA-CH02-02-rfm-model/` | 已发布并封存；全量参考对照通过 |
| BA-CH02-03 | 第 2 章 | 用户忠诚度模型 | `chapters/ch02-analysis-methods/BA-CH02-03-customer-loyalty/` | 完成；客户集合、指标、分类和阈值一致 |
| BA-CH02-04 | 第 2 章 | 同期群分析 | `chapters/ch02-analysis-methods/BA-CH02-04-cohort-analysis/` | 完成；300 项注册与留存结果一致 |
| BA-CH02-05 | 第 2 章 | 漏斗分析 | `chapters/ch02-analysis-methods/BA-CH02-05-funnel-analysis/` | 完成；阶段转化与总体转化一致 |
| BA-CH02-06 | 第 2 章 | 相关分析 | `chapters/ch02-analysis-methods/BA-CH02-06-correlation-analysis/` | 已发布；输入和图表系数核对通过 |
| BA-CH02-10 | 第 2 章 | 分布分析 | `chapters/ch02-analysis-methods/BA-CH02-10-distribution-analysis/` | 完成；描述统计与 QUARTILE.INC 结果一致 |
| BA-CH02-15 | 第 2 章 | 数据汇总、引用与查找 | `chapters/ch02-analysis-methods/BA-CH02-15-spreadsheet-summary-lookup/` | 完成；销售汇总、近似查找和引用练习一致 |
| BA-CH03-01 | 第 3 章 | 收入趋势分析 | `chapters/ch03-business-framework/BA-CH03-01-income-trend-analysis/` | 完成；232 项聚合结果一致，特殊增长公式已标注 |
| BA-CH03-02 | 第 3 章 | 财务费用分析 | `chapters/ch03-business-framework/BA-CH03-02-financial-expense-analysis/` | 已发布；33 项对照一致，源表差额保留 |
| BA-CH03-03 | 第 3 章 | 电商平台精准营销 | `chapters/ch03-business-framework/BA-CH03-03-precision-marketing/` | 完成；13 项汇总一致，年龄段参考区 4 项不一致 |
| BA-CH01-02 | 第 1 章 | 维度模型演示：商场销售数据 | `chapters/ch01-analysis-thinking/BA-CH01-02-dimension-model-demo/` | 完成（Excel 侧）；12,960 行事实表全键匹配，品牌/城市聚合交叉一致；2,075 行价差与 4 行缓存金额异常作为教材数据特征记录；Power BI 模型语义未验证 |
| BA-CH02-18 | 第 2 章 | ETL：清洗、拆分、纵向/横向合并 | `chapters/ch02-analysis-methods/BA-CH02-18-etl-clean-merge/` | 完成；拆分、清洗、追加与连接共 10 项工作簿对照一致 |
| BA-CH08-01 | 第 8 章 | SQL 基础、导入与开窗函数 | `chapters/ch08-sql-fundamentals/BA-CH08-01-sql-fundamentals/` | 完成（SQLite 等价子集）；教学 CSV 本地核对一致；未安装 MySQL |
| BA-CH10-01 | 第 10 章 | 效应分解：AirPassengers 与节日效应 | `chapters/ch10-forecasting/BA-CH10-01-effect-decomposition/` | 完成（可验证部分）；144 期 ln_AIR 逐值一致，分解重构一致；WPS AI 预测与 Power BI 未复现 |

未迁移条目没有标记为完成。依赖随机公式、缺少明确结果、跨 Power BI/ETL 范围或存在高优先级隐私风险的实验继续保留在阶段报告中。
