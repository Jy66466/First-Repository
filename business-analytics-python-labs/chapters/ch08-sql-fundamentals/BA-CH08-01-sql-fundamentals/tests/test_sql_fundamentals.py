from __future__ import annotations

import sqlite3

import pandas as pd
import pytest

from sql_fundamentals import (
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
    build_demo_database,
    load_csv_into_sqlite,
    run_query,
)


@pytest.fixture()
def conn() -> sqlite3.Connection:
    return build_demo_database()


# ---------------------------------------------------------------------------
# 基础查询
# ---------------------------------------------------------------------------

def test_select_filter_order(conn):
    result = run_query(conn, Q_SELECT_FILTER_ORDER, {"year": 2012})
    assert len(result) == 2
    assert list(result["market"]) == ["east", "west"]
    assert set(result.columns) == {"year", "market", "sale", "profit"}


def test_distinct(conn):
    result = run_query(conn, Q_DISTINCT)
    assert list(result["year"]) == [2010, 2011, 2012]


def test_expression_filter(conn):
    result = run_query(conn, Q_EXPRESSION_FILTER, {"max_rate": 0.05})
    rates = result["rate"].tolist()
    assert all(r < 0.05 for r in rates)
    # 演示数据中只有 west 2010 (30/800=0.0375) 与 west 2011 (20/900≈0.0222) 低于 5%。
    assert len(result) == 2


# ---------------------------------------------------------------------------
# CASE 重编码与分组
# ---------------------------------------------------------------------------

def test_case_recode_weekend(conn):
    result = run_query(conn, Q_CASE_RECODE)
    # 2021-01-01 是周五、2021-01-03 是周日、2021-02-01 是周一。
    by_id = result.set_index("trans_id")["day_type"]
    assert by_id.loc[1] == "工作日"
    assert by_id.loc[2] == "周末"
    assert by_id.loc[5] == "工作日"


def test_group_by_having(conn):
    result = run_query(conn, Q_GROUP_HAVING, {"min_count": 1})
    # 只有 2021-01-05 与 2021-02-01 各有 2 笔交易。
    assert list(result["date"]) == ["2021-01-05", "2021-02-01"]
    assert list(result["trans_count"]) == [2, 2]
    assert result.loc[result["date"] == "2021-02-01", "total_amount"].iloc[0] == 500


# ---------------------------------------------------------------------------
# 连接与子查询
# ---------------------------------------------------------------------------

def test_cross_join_filtered_equals_inner(conn):
    result = run_query(conn, Q_CROSS_JOIN_FILTERED)
    # table1 中 id=2 出现两次，连接结果保留 3 行（2,2,3）。
    assert len(result) == 3
    assert list(result["id1"]) == [2, 2, 3]
    assert list(result["tag2"]) == ["x", "x", "y"]


def test_left_join_keeps_unmatched(conn):
    result = run_query(conn, Q_LEFT_JOIN)
    unmatched = result.loc[result["id"] == 1]
    assert len(unmatched) == 1
    assert pd.isna(unmatched["tag2"].iloc[0])
    # id=2 在 table1 出现两次，左连接保留两行。
    assert len(result.loc[result["id"] == 2]) == 2


def test_subquery_in(conn):
    result = run_query(conn, Q_SUBQUERY_IN, {"bad_status": "B"})
    # 违约账户为 102 和 104；trans 中属于它们的交易为 3、5、6。
    assert sorted(result["trans_id"]) == [3, 5, 6]


# ---------------------------------------------------------------------------
# 集合操作
# ---------------------------------------------------------------------------

def test_union_distinct(conn):
    result = run_query(conn, Q_UNION_DISTINCT)
    # table1 中 (2,'b') 重复去重；两表 6 个不同元组全部保留。
    assert sorted(map(tuple, result.to_numpy())) == [
        (1, "a"), (2, "b"), (2, "x"), (3, "c"), (3, "y"), (4, "z"),
    ]


def test_union_all(conn):
    result = run_query(conn, Q_UNION_ALL)
    assert len(result) == len(run_query(conn, "SELECT id, tag FROM table1")) + len(
        run_query(conn, "SELECT id, tag FROM table2")
    )
    assert len(result) == 7


# ---------------------------------------------------------------------------
# 窗口函数
# ---------------------------------------------------------------------------

def test_row_number_window(conn):
    result = run_query(conn, Q_ROW_NUMBER_WINDOW)
    acc104 = result.loc[result["account_id"] == 104]
    # 账户 104：amount 400 排第一、100 排第二（tie-break 用 trans_id）。
    assert int(acc104.loc[acc104["rn"] == 1, "trans_id"].iloc[0]) == 5


def test_rank_window_ties_share_rank(conn):
    result = run_query(conn, Q_RANK_WINDOW)
    # 账户 104 两笔交易金额不同；账户 101 金额 500 > 200。
    acc101 = result.loc[result["account_id"] == 101].sort_values("rnk")
    assert acc101["amount"].tolist() == [500, 200]


def test_running_sum_window(conn):
    result = run_query(conn, Q_RUNNING_SUM_WINDOW)
    acc101 = result.loc[result["account_id"] == 101].sort_values("trans_id")
    assert acc101["running_total"].tolist() == [500, 700]


# ---------------------------------------------------------------------------
# CSV 导入
# ---------------------------------------------------------------------------

def test_load_csv_into_sqlite(tmp_path):
    csv_file = tmp_path / "mini.csv"
    csv_file.write_text("id,tag\n1,a\n2,b\n", encoding="utf-8")
    conn = sqlite3.connect(":memory:")
    count = load_csv_into_sqlite(conn, "mini", csv_file)
    assert count == 2
    result = run_query(conn, "SELECT * FROM mini ORDER BY id")
    assert list(result["tag"]) == ["a", "b"]


def test_load_csv_into_sqlite_gbk_and_missing(tmp_path):
    csv_file = tmp_path / "gbk.csv"
    csv_file.write_text("1,甲\n", encoding="gbk")
    conn = sqlite3.connect(":memory:")
    # 无表头 CSV：显式指定列名时首行即数据行。
    assert load_csv_into_sqlite(conn, "gbk", csv_file, columns=["id", "tag"], encoding="gbk") == 1
    with pytest.raises(FileNotFoundError):
        load_csv_into_sqlite(conn, "x", tmp_path / "missing.csv")
