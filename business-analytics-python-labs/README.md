# Business Analytics Python Labs

本项目将可验证的商业数据分析练习独立实现为 Python 代码、合成测试和聚合输出。教材原文、答案、原始数据、PBIX/PBIT 和第三方素材不随项目分发；其公开授权未获确认。

## 已实现实验

| 编号 | 名称 | 原工具 | 验证状态 |
| --- | --- | --- | --- |
| BA-CH02-01 | 波士顿矩阵 | Excel/WPS | 30 项工作簿结果对照一致 |
| BA-CH02-02 | RFM 模型 | Excel/WPS | 全量客户参考对照和测试通过 |
| BA-CH02-03 | 用户忠诚度模型 | Excel/WPS | 12 组完整客户集合、指标和阈值检查一致 |
| BA-CH02-04 | 同期群分析 | Excel/WPS | 300 项注册、登录和留存矩阵检查一致 |
| BA-CH02-05 | 漏斗分析 | Excel/WPS | 12 项阶段及总体转化率检查一致 |
| BA-CH02-06 | 相关分析 | Excel/WPS | 输入和图表系数对照通过 |
| BA-CH02-10 | 分布分析 | Excel/WPS | 8 项描述统计与四分位结果一致 |
| BA-CH02-15 | 数据汇总、引用与查找 | Excel/WPS | 88 组销售汇总、查找和引用检查一致 |
| BA-CH03-01 | 收入趋势分析 | Excel/WPS | 232 项年度、月度和省份汇总检查一致 |
| BA-CH03-02 | 财务费用分析 | Excel/WPS | 33 项分类结果一致；源表总额差异保留 |
| BA-CH03-03 | 电商平台精准营销 | Excel/WPS | 13 项汇总一致；年龄段参考区 4 项差异保留 |
| BA-CH01-02 | 维度模型演示：商场销售数据 | Excel + Power BI | 事实表 12,960 行全键匹配；品牌/城市聚合交叉一致；Power BI 语义留待 P1.3 |
| BA-CH02-18 | ETL：清洗、拆分、纵向/横向合并 | Power Query / Excel | 10 项工作簿操作结果对照一致 |
| BA-CH08-01 | SQL 基础、导入与开窗函数 | MySQL/SQL | SQLite 等价实现 23 项核验一致；不安装 MySQL |
| BA-CH10-01 | 效应分解：AirPassengers 与节日效应 | WPS/Excel + Power BI | 144 期对数变换逐值一致；分解重构误差 < 1e-13；WPS AI 预测为黑盒边界 |

完整索引见 [EXPERIMENT_INDEX.md](EXPERIMENT_INDEX.md)。候选范围和原始材料证据以本地阶段清单为准；候选不等于已迁移。

## 环境

Python 3.10 或更高版本。共同依赖见 `environments/requirements-core.txt`，测试依赖见 `environments/requirements-test.txt`。

```powershell
python -m pip install -r environments/requirements-core.txt -r environments/requirements-test.txt
```

每个实验包含独立入口、`pyproject.toml`、README、INPUTS 和合成数据测试。教材数据需由使用者从获准来源自行准备。

## 测试

从项目根目录指定全部实验测试目录运行。P1.2 统一验收结果为 `117 passed`，其中 P1.1 前 40 项、P1.1 新增 24 项、P1.2 新增 53 项。

## 公开与许可边界

本项目自主编写的 Python 代码、合成测试和原创说明采用项目级 MIT License，版权声明为 `Copyright (c) 2026 Jy66466`。该许可不适用于教材原文、答案、截图、原始数据、PBIX 或第三方材料。具体边界见 [PUBLICATION_MANIFEST.md](PUBLICATION_MANIFEST.md)。
