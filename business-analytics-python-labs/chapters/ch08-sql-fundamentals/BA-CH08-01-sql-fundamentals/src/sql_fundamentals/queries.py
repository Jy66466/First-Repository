"""BA-CH08-01 演示查询集（原创 SQL，SQLite 方言）。

覆盖教材 SQL 教学脚本登记的技能点：

- 基础查询：选择列、DISTINCT、WHERE 过滤、ORDER BY 排序；
- 表达式：用计算列创建新指标并按表达式过滤；
- 重编码：CASE WHEN 把星期编号映射为“周末/工作日”；
- 分组汇总：GROUP BY + 聚合 + HAVING；
- 横向连接：内连接、左连接、带过滤的交叉连接；
- 子查询：IN 子查询筛选违约账户的交易；
- 集合操作：UNION / UNION ALL；
- 开窗函数：ROW_NUMBER、RANK、累计 SUM OVER。

方言差异（与 MySQL 教学环境对照）：

- MySQL 的 ``WEEKDAY(d)``（周一=0..周日=6）在 SQLite 中用
  ``strftime('%w', d)``（周日=0..周六=6）等价改写；
- MySQL 不支持 FULL JOIN，本查询集同样不使用；
- SQLite 的窗口函数需要 3.25+（Python 3.10+ 内置版本均满足）；
- SQLite 对整数列做整除（``30/800 = 0``），利润率等比值必须先乘
  ``1.0`` 转为浮点；MySQL 中同列类型为浮点时不需此处理。
"""

from __future__ import annotations

__all__ = [
    "Q_CASE_RECODE",
    "Q_CROSS_JOIN_FILTERED",
    "Q_DISTINCT",
    "Q_EXPRESSION_FILTER",
    "Q_GROUP_HAVING",
    "Q_LEFT_JOIN",
    "Q_RANK_WINDOW",
    "Q_RUNNING_SUM_WINDOW",
    "Q_ROW_NUMBER_WINDOW",
    "Q_SELECT_FILTER_ORDER",
    "Q_SUBQUERY_IN",
    "Q_UNION_ALL",
    "Q_UNION_DISTINCT",
]

Q_SELECT_FILTER_ORDER = """
SELECT year, market, sale, profit
FROM sale
WHERE year = :year
ORDER BY market
"""

Q_DISTINCT = """
SELECT DISTINCT year
FROM sale
ORDER BY year
"""

Q_EXPRESSION_FILTER = """
SELECT market, 1.0 * profit / sale AS rate
FROM sale
WHERE 1.0 * profit / sale < :max_rate
ORDER BY rate
"""

Q_CASE_RECODE = """
SELECT trans_id, date, amount,
       CASE strftime('%w', date)
           WHEN '0' THEN '周末'
           WHEN '6' THEN '周末'
           ELSE '工作日'
       END AS day_type
FROM trans
ORDER BY trans_id
"""

Q_GROUP_HAVING = """
SELECT date, COUNT(account_id) AS trans_count,
       SUM(amount) AS total_amount
FROM trans
GROUP BY date
HAVING COUNT(account_id) > :min_count
ORDER BY date
"""

Q_CROSS_JOIN_FILTERED = """
SELECT table1.id AS id1, table1.tag AS tag1,
       table2.id AS id2, table2.tag AS tag2
FROM table1, table2
WHERE table1.id = table2.id
ORDER BY id1, id2
"""

Q_LEFT_JOIN = """
SELECT table1.id, table1.tag AS tag1, table2.tag AS tag2
FROM table1
LEFT JOIN table2 ON table1.id = table2.id
ORDER BY table1.id
"""

Q_SUBQUERY_IN = """
SELECT t.trans_id, t.account_id, t.date, t.amount
FROM trans AS t
WHERE t.account_id IN (
    SELECT account_id FROM loans WHERE status = :bad_status
)
ORDER BY t.account_id, t.trans_id
"""

Q_UNION_DISTINCT = """
SELECT id, tag FROM table1
UNION
SELECT id, tag FROM table2
ORDER BY id
"""

Q_UNION_ALL = """
SELECT id, tag FROM table1
UNION ALL
SELECT id, tag FROM table2
ORDER BY id
"""

Q_ROW_NUMBER_WINDOW = """
SELECT account_id, trans_id, amount,
       ROW_NUMBER() OVER (
           PARTITION BY account_id ORDER BY amount DESC, trans_id
       ) AS rn
FROM trans
ORDER BY account_id, rn
"""

Q_RANK_WINDOW = """
SELECT account_id, trans_id, amount,
       RANK() OVER (
           PARTITION BY account_id ORDER BY amount DESC
       ) AS rnk
FROM trans
ORDER BY account_id, rnk, trans_id
"""

Q_RUNNING_SUM_WINDOW = """
SELECT account_id, trans_id, date, amount,
       SUM(amount) OVER (
           PARTITION BY account_id ORDER BY date, trans_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_total
FROM trans
ORDER BY account_id, date, trans_id
"""
