from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from sql_fundamentals import (
    Q_GROUP_HAVING,
    Q_RANK_WINDOW,
    Q_SELECT_FILTER_ORDER,
    build_demo_database,
    run_query,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="BA-CH08-01 SQL 基础演示（SQLite）")
    parser.add_argument("--output", default="outputs/sql_demo_summary.json")
    args = parser.parse_args()

    conn = build_demo_database()
    filtered = run_query(conn, Q_SELECT_FILTER_ORDER, {"year": 2012})
    grouped = run_query(conn, Q_GROUP_HAVING, {"min_count": 1})
    ranked = run_query(conn, Q_RANK_WINDOW)
    summary = {
        "experiment": "BA-CH08-01",
        "filter_2012_rows": int(len(filtered)),
        "group_having_rows": int(len(grouped)),
        "rank_rows": int(len(ranked)),
        "top_transaction_amount_per_account": {
            str(int(r.account_id)): int(r.amount)
            for r in ranked.loc[ranked["rnk"] == 1].itertuples()
        },
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
