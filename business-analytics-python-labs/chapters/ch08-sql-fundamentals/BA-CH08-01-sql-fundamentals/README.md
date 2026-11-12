# BA-CH08-01 SQL 基础、导入与开窗函数练习

实验用 SQLite（Python 标准库 `sqlite3`）本地复现教材 SQL 教学的核心技能点，
**不安装、不依赖 MySQL 服务端**。查询集为原创 SQL，覆盖：

1. 基础查询：选择列、`DISTINCT`、`WHERE` 过滤、`ORDER BY`；
2. 表达式：计算列（利润率）及按表达式过滤；
3. 重编码：`CASE` 把星期映射为“周末/工作日”；
4. 分组汇总：`GROUP BY` + 聚合 + `HAVING`；
5. 横向连接：内连接、左连接、带过滤的交叉连接；
6. 子查询：`IN` 子查询筛选违约账户的交易；
7. 集合操作：`UNION` / `UNION ALL`；
8. 开窗函数：`ROW_NUMBER`、`RANK`、累计 `SUM(...) OVER (...)`；
9. 数据导入：CSV 逐行导入 SQLite 表。

```powershell
python run_sql_fundamentals.py
python -m pytest -q
```

## 口径与方言差异

- 教学环境为 MySQL；`WEEKDAY(d)`（周一=0）在 SQLite 中以
  `strftime('%w', d)`（周日=0）等价改写，映射关系已在查询注释中说明；
- MySQL 不支持 `FULL JOIN`，本实验不包含该操作；
- 开窗函数要求 SQLite 3.25+，Python 3.10+ 内置版本满足。

## 数据边界

- 公开目录只含人工构造的合成演示数据（`build_demo_database`），
  与教材真实数据无关；
- 教材自带的 kdd99 系列 CSV 属于教材资料且含银行字段语义，
  仅可在本地以只读方式做等价性核对，**不复制、不发布**；
- `load_csv_into_sqlite` 供本地核对使用，可指定 `encoding`（如 `gbk`）。

## 已知限制

- 本实验为 **SQLite 等价实现子集**，未在 MySQL 环境中执行或验证；查询
  语义与 MySQL 的等价性依据 SQLite 与 MySQL 的公开文档对照，不构成
  MySQL 实测结论；
- 教材脚本中的 `CREATE TABLE ... AS SELECT`、视图与 MySQL 特有函数
  未纳入本子集，属后续扩展空间；
- SQLite 与 MySQL 的类型推断和隐式转换行为不完全一致，本实验查询集
  避免依赖隐式转换。
