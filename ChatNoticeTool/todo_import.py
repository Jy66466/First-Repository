"""Explicit bridge: exported chat text -> per-message desktop todos.

This is the ONLY sanctioned path from chat exports into the todo store. The
desktop widget itself never reads QQ/WeChat/DingTalk data; this one-shot
command turns already-exported, in-scope TEXT messages into todo items with
stable ids (repeat runs update instead of duplicating, and never clobber a
completed/removed state).

Positioning: offline, one-shot, no background work. It only reads this
project's own exports/ and writes this project's own state/todos.sqlite3.

License: Apache-2.0. See NOTICE.md.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from chatnotice import ROOT, project_path
from todo_store import TodoStore

MAX_TITLE = 80


def compact_title(text: str) -> str:
    one_line = re.sub(r"\s+", " ", text).strip()
    return one_line[:MAX_TITLE] + ("…" if len(one_line) > MAX_TITLE else "")


def load_export(export_dir: str) -> dict:
    candidate = Path(export_dir)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    candidate = candidate.resolve()
    exports_root = (ROOT / "exports").resolve()
    if not candidate.is_relative_to(exports_root):
        raise ValueError("只能读取本项目 exports 目录内的导出批次")
    data_file = project_path(str(candidate.relative_to(ROOT)) + "/messages.json")
    if not data_file.is_file():
        raise ValueError(f"导出目录缺少 messages.json: {data_file}")
    data = json.loads(data_file.read_text(encoding="utf-8"))
    if not data.get("request", {}).get("confirmed"):
        raise ValueError("该导出批次没有明确授权标记，拒绝导入")
    return data


def build_todo(message: dict) -> dict:
    text = message.get("text", "")
    return {
        "id": f"dingtalk:{message['group_id']}:{message['message_id']}",
        "title": compact_title(text) or "[空文本消息]",
        "note": f"[{message.get('sender', '')}] {message.get('time', '')}\n{text}",
        "source": f"钉钉群「{message.get('group_name', message['group_id'])}」· "
                  f"{message.get('time', '')}",
    }


def import_batch(store: TodoStore, data: dict, *, limit: int | None = None) -> dict:
    group_only = data.get("group_chats_only", False)
    messages = data.get("messages", [])
    skipped = 0
    todos = []
    for message in messages:
        if message.get("platform") != "dingtalk":
            skipped += 1
            continue
        if message.get("body_status") != "decoded" or not message.get("text"):
            skipped += 1  # empty or non-text bodies never become todos
            continue
        if not group_only:  # defence in depth: never import non-group messages
            skipped += 1
            continue
        todos.append(build_todo(message))
    if limit is not None:
        todos = todos[:limit]
    return {"todos": todos, "skipped_messages": skipped,
            "total_messages": len(messages)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="把已导出的群聊文本消息逐条写入桌面待办；稳定ID幂等，重复导入不重复")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--batch", help="导出批次目录，如 exports/20261015-103000-123456")
    source.add_argument("--latest", action="store_true", help="使用最近一次钉钉导出")
    parser.add_argument("--limit", type=int, help="最多导入前 N 条（调试用）")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不写入待办库")
    args = parser.parse_args(argv)
    try:
        if args.latest:
            pointer = project_path("state/latest-dingtalk-export.json")
            if not pointer.is_file():
                raise ValueError("尚无钉钉导出记录")
            args.batch = json.loads(pointer.read_text(encoding="utf-8"))["output_dir"]
        data = load_export(args.batch)
        store = TodoStore()
        plan = import_batch(store, data, limit=args.limit)
        if args.dry_run:
            print(f"待导入 {len(plan['todos'])} 条（跳过非文本 {plan['skipped_messages']} 条），未写入。")
            for todo in plan["todos"][:5]:
                print(f"- {todo['id']} | {todo['title']}")
            if len(plan["todos"]) > 5:
                print(f"… 其余 {len(plan['todos']) - 5} 条")
            return 0
        written = 0
        for todo in plan["todos"]:
            store.upsert(**todo)  # same id => update; done/removed state preserved
            written += 1
        print(json.dumps({
            "imported": written, "skipped_non_text": plan["skipped_messages"],
            "idempotent": True, "completed_states_preserved": True,
            "widget_reads_chat": False,
            "todo_db": "state/todos.sqlite3",
        }, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f"导入失败：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
