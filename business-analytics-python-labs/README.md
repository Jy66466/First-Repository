# Business Analytics Python Labs

基于 CDA 一级《商业数据分析》配套材料中的可验证分析方法，使用 Python 独立实现并测试。教材原文、答案、原始数据、PBIX/PBIT 和第三方素材不随项目分发；其公开授权未获确认。

## 当前实验

| 编号 | 名称 | 原实现 | Python 状态 | 验证状态 |
| --- | --- | --- | --- | --- |
| BA-CH02-02 | RFM 模型 | Excel/WPS | 已实现 | 本地全量参考对照通过；自动化测试通过 |
| BA-CH02-06 | 相关分析 | Excel/WPS | 已实现 | 输入与参考一致，图表系数舍入核对通过；自动化测试通过 |
| BA-CH03-02 | 财务费用分析 | Excel/WPS | 已实现 | 分类汇总与参考结果一致；源表合计差异单独保留 |

完整索引见 [EXPERIMENT_INDEX.md](EXPERIMENT_INDEX.md)。未迁移候选及其教材文件关联清单不随公开项目分发；候选不等于已迁移或已验证。

## 环境

Python 3.10 或更高版本。项目共同依赖见 `environments/requirements-core.txt`，测试依赖见 `environments/requirements-test.txt`。

```powershell
python -m pip install -r environments/requirements-core.txt -r environments/requirements-test.txt
```

每个实验仍保留独立的 `pyproject.toml`，可按实验单独安装。不要将教材工作簿放入本项目目录。

## 运行与测试

各实验 README 提供对应命令。项目级测试从实验目录分别执行：

```powershell
python -m pytest -q chapters/ch02-analysis-methods/BA-CH02-02-rfm-model/tests
python -m pytest -q chapters/ch02-analysis-methods/BA-CH02-06-correlation-analysis/tests
python -m pytest -q chapters/ch03-business-framework/BA-CH03-02-financial-expense-analysis/tests
```

教材数据需由使用者自行从获准来源提供；脚本使用明确的本地输入路径，并默认只生成聚合输出。

## 公开边界

发布范围仅限原创代码和经过内容审核的说明。不得提交原始教材、参考答案、未经授权数据、客户/银行/员工/学生级记录、密钥或个人本机路径。具体边界见 [PUBLICATION_MANIFEST.md](PUBLICATION_MANIFEST.md)。

## License

本项目自主编写的 Python 代码、测试代码和原创项目说明采用 [MIT License](LICENSE)，版权归 Jy66466 所有。

MIT License 不适用于教材原文、参考答案、教材截图、原始数据、PBIX/PBIT、第三方资料或其他非本项目原创内容。本仓库不包含上述未经授权材料，也不因引用分析方法或实验名称而取得这些材料的公开授权。第三方依赖及第三方材料继续遵循各自适用的许可证；不得将教材内容或第三方资料归入 Jy66466 的原创版权范围。
