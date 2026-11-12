"""BA-CH08-01 SQL 基础、导入与开窗函数练习（SQLite 本地实现）。"""

from .core import (
    build_demo_database,
    load_csv_into_sqlite,
    run_query,
)
from .queries import (
    Q_CASE_RECODE,
    Q_CROSS_JOIN_FILTERED,
    Q_DISTINCT,
    Q_EXPRESSION_FILTER,
    Q_GROUP_HAVING,
    Q_LEFT_JOIN,
    Q_RANK_WINDOW,
    Q_RUNNING_SUM_WINDOW,
    Q_ROW_NUMBER_WINDOW,
    Q_SELECT_FILTER_ORDER,
    Q_SUBQUERY_IN,
    Q_UNION_ALL,
    Q_UNION_DISTINCT,
)

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
    "build_demo_database",
    "load_csv_into_sqlite",
    "run_query",
]
