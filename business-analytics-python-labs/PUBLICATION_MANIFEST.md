# 公开发布边界

## 可以进入候选发布清单

- 本项目自主编写的 Python 源代码、入口脚本和自动化测试。
- 经逐文件审阅、不含教材答案、源数据、客户级记录或内部路径的 README、INPUTS、项目说明和实验索引。
- 项目级 MIT License 和依赖清单。
- 人工构造的合成测试数据。

## 不得发布

- `1《CDA 一级认证教材：商业数据分析》/` 下的任何文件。
- 阶段清单、参考工作簿、PBIX 解析素材和含完整内部路径的审核材料。
- 教材原文、截图、答案、XLS/XLSX、CSV、PBIX/PBIT、PPT/PDF、第三方图表素材和运行输出。
- 客户、银行、员工、学生等记录，以及账号、密钥、Token、个人绝对路径或环境文件。
- 可还原原始数据的客户级或逐笔衍生结果。

## 许可范围

项目级 MIT License 仅适用于 Jy66466 自主编写的代码、合成测试和原创说明。教材、答案、数据和第三方材料不属于该原创授权范围。第三方依赖遵循各自许可证。

## P1.1 新增发布候选

新增 8 个实验目录：BA-CH02-01、03、04、05、10、15，BA-CH03-01、03。每个目录的候选白名单限于 `.gitignore`、README、INPUTS、`pyproject.toml`、运行入口、`src/` 源码和 `tests/` 合成测试。

精准营销实验只发布聚合逻辑和合成测试，不发布客户 ID 或原始记录。收入实验保留特殊参考公式的解释，不复制参考汇总值。所有 `data/`、`outputs/`、缓存和教材资产扩展名继续忽略。

## P1.2 新增发布候选

新增 4 个实验目录：

- `chapters/ch01-analysis-thinking/BA-CH01-02-dimension-model-demo/`
- `chapters/ch02-analysis-methods/BA-CH02-18-etl-clean-merge/`
- `chapters/ch08-sql-fundamentals/BA-CH08-01-sql-fundamentals/`
- `chapters/ch10-forecasting/BA-CH10-01-effect-decomposition/`

候选白名单与 P1.1 相同：`.gitignore`、README、INPUTS、`pyproject.toml`、运行入口、`src/` 源码、`tests/` 合成测试。

P1.2 特别边界：SQL 实验仅发布合成演示数据与原创 SQL；教材 kdd99 CSV 只允许本地只读核对，不进入发布候选。维度模型与效应分解实验的 PBIX 相关结论不写入公开文档（仅说明“未验证，留待后续阶段”）。跳过项 BA-CH02-12、BA-CH02-21、BA-CH09-01 不产生发布候选。

本文件只定义发布候选，不授权 Git add、commit 或 push。

## P1.3 新增发布候选

新增 2 个实验目录（Power BI 迁移，经 Power BI Desktop 实测验证）：

- `chapters/ch02-analysis-methods/BA-CH02-12-sankey-flow/`
- `chapters/ch02-analysis-methods/BA-CH02-17-sales-dashboard/`

候选白名单与 P1.1/P1.2 相同：`.gitignore`、README、INPUTS、`pyproject.toml`、运行入口、`src/` 源码、`tests/` 合成测试。

P1.3 特别边界：桑基实验只发布流数据计算，不发布第三方视觉对象或其许可材料；销售看板实验的教材 CSV（Northwind 中文演示数据，含员工字段）仅本地只读核对，不进入发布候选，公开测试全部使用合成数据。PBIX 审计副本、EVALUATE 证据、截图与内部报告留在 `phase-1.3-review/`，不同步到公开仓库。

本文件只定义发布候选，不授权 Git add、commit 或 push。
