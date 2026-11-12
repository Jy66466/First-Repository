"""BA-CH08-01 SQLite 数据库构建与查询执行。"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

import pandas as pd

__all__ = ["build_demo_database", "load_csv_into_sqlite", "run_query"]

_DEMO_SCHEMA = """
CREATE TABLE sale (
    year   INTEGER,
    market TEXT,
    sale   INTEGER,
    profit INTEGER
);
CREATE TABLE table1 (
    id  INTEGER,
    tag TEXT
);
CREATE TABLE table2 (
    id  INTEGER,
    tag TEXT
);
CREATE TABLE loans (
    loan_id    INTEGER,
    account_id INTEGER,
    date       TEXT,
    amount     INTEGER,
    status     TEXT
);
CREATE TABLE trans (
    trans_id   INTEGER,
    account_id INTEGER,
    date       TEXT,
    type       TEXT,
    amount     INTEGER,
    balance    INTEGER
);
"""


def _demo_rows() -> dict[str, list[tuple]]:
    """人工构造的演示数据（与教材真实数据无关，仅供公开运行示例）。"""
    sale = [
        (2010, "east", 1000, 60),
        (2010, "west", 800, 30),
        (2011, "east", 1200, 90),
        (2011, "west", 900, 20),
        (2012, "east", 1500, 200),
        (2012, "west", 1100, 250),
    ]
    table1 = [(1, "a"), (2, "b"), (3, "c"), (2, "b")]
    table2 = [(2, "x"), (3, "y"), (4, "z")]
    loans = [
        (1, 101, "2021-01-05", 50000, "A"),
        (2, 102, "2021-02-10", 30000, "B"),
        (3, 103, "2021-03-15", 80000, "A"),
        (4, 104, "2021-04-20", 12000, "B"),
    ]
    trans = [
        (1, 101, "2021-01-01", "借", 500, 4500),
        (2, 101, "2021-01-03", "贷", 200, 4700),
        (3, 102, "2021-01-05", "借", 1000, 9000),
        (4, 103, "2021-01-05", "借", 300, 7700),
        (5, 104, "2021-02-01", "贷", 400, 6400),
        (6, 104, "2021-02-01", "借", 100, 6500),
    ]
    return {"sale": sale, "table1": table1, "table2": table2, "loans": loans, "trans": trans}


def build_demo_database() -> sqlite3.Connection:
    """创建内存 SQLite 演示库并写入合成数据。"""
    conn = sqlite3.connect(":memory:")
    conn.executescript(_DEMO_SCHEMA)
    rows = _demo_rows()
    for table, data in rows.items():
        placeholders = ",".join("?" * len(data[0]))
        conn.executemany(
            f"INSERT INTO {table} VALUES ({placeholders})", data
        )
    conn.commit()
    return conn


def load_csv_into_sqlite(
    conn: sqlite3.Connection,
    table: str,
    csv_path: str | Path,
    columns: list[str] | None = None,
    encoding: str = "utf-8",
    replace_table: bool = True,
) -> int:
    """把 CSV 导入 SQLite 表（对应教材“数据导入”技能点）。

    使用 Python 标准库逐行读取，不依赖 MySQL 服务端。
    返回导入行数。``encoding`` 用于读取 GBK 等本地导出的 CSV。
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(str(csv_path))
    with csv_path.open(encoding=encoding, newline="") as fh:
        reader = csv.reader(fh)
        if columns is None:
            # 首行作为表头；显式提供 columns 时首行即数据行。
            header = next(reader)
            col_names = header
        else:
            col_names = list(columns)
        col_count = len(col_names)
        placeholders = ",".join("?" * col_count)
        quoted = ",".join(f'"{c}"' for c in col_names)
        if replace_table:
            conn.execute(f'DROP TABLE IF EXISTS "{table}"')
        conn.execute(f'CREATE TABLE "{table}" ({quoted})')
        inserted = 0
        for row in reader:
            if not row:
                continue
            values = row[:col_count] + [None] * (col_count - len(row))
            conn.execute(
                f'INSERT INTO "{table}" VALUES ({placeholders})', values
            )
            inserted += 1
    conn.commit()
    return inserted


def run_query(
    conn: sqlite3.Connection,
    sql: str,
    params: dict | None = None,
) -> pd.DataFrame:
    """执行查询并返回 DataFrame。"""
    return pd.read_sql_query(sql, conn, params=params or {})
