# 实验索引

此索引只列出已经实现并完成本地验证的实验。未迁移候选及其教材文件关联清单不随公开项目分发，以免公开未经授权的教材目录路径或内容。

| 编号 | 章节 | 名称 | 原始工具 | 实现实验目录 | 实现状态 | 验证状态 |
| --- | --- | --- | --- | --- | --- | --- |
| BA-CH02-02 | 第 2 章 | RFM 模型 | Excel/WPS | `chapters/ch02-analysis-methods/BA-CH02-02-rfm-model/` | 完成并封存 | 自动化测试、全量参考对照及敏感性分析通过；发布版说明见 `README.public.md` |
| BA-CH02-06 | 第 2 章 | 相关分析 | Excel/WPS | `chapters/ch02-analysis-methods/BA-CH02-06-correlation-analysis/` | 完成 | 自动化测试、输入对照和图表系数舍入核对通过；发布版说明见 `README.public.md` |
| BA-CH03-02 | 第 3 章 | 财务费用分析 | Excel/WPS | `chapters/ch03-business-framework/BA-CH03-02-financial-expense-analysis/` | 完成 | 自动化测试和分类参考对照通过；源表总额差异单独保留 |

尚未迁移的候选仍保持未实现状态。原因包括：教材步骤/指标语义未确认、源演示公式会随机变化、输入与参考版本不一致、需要未提取的 DAX/关系模型，或需要独立的隐私/版权评估。Power BI 实验目前均未标记为 Python 复现；现有资产清单未发现 Notebook，因此没有 Notebook 转换。
