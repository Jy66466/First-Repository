# BA-CH08-01 输入说明

本实验不依赖外部数据文件即可运行：

- `python run_sql_fundamentals.py` 使用 `build_demo_database()` 内存合成库；
- 自动化测试同样只使用合成数据。

## 本地参考核对（可选，不随实验发布）

教材提供 kdd99 系列 CSV（`sale.csv`、`Table1.csv`、`Table2.csv`、
`One.csv`、`Two.csv`、`Kdd99_loans.csv`、`Kdd99_trans.csv` 等）。
这些文件属于教材资料，仅允许本地只读读取用于等价性核对：

```python
from sql_fundamentals import load_csv_into_sqlite

conn = sqlite3.connect(":memory:")   # 或本地临时文件库
load_csv_into_sqlite(conn, "sale", r"<local>\sale.csv", encoding="gbk")
```

导入后可用 `queries.py` 中的查询做本地验证；严禁把 CSV 或查询结果中的
明细行复制到实验目录或公开仓库。银行字段语义（账户、交易、贷款状态）的
详细口径以教材原文为准，本实验只复现查询技能，不重定义业务含义。
