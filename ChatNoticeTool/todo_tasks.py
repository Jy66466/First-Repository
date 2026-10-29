"""Refactored pipeline: exported group text -> ACTION-REQUIRED messages ->
merged task records -> per-task desktop todos.

Stages (each explicit, one-shot, offline; reads only this project's exports/,
writes only this project's exports/<batch>/ reports and state/todos.sqlite3):

1. FILTER   keep decoded group text messages that contain an action
            requirement (imperative cues, deadlines, to-do markers, @mentions).
2. CLUSTER  actionable messages that refer to the SAME task (same sender,
            within --gap minutes, content similarity >= --min-sim, or a strong
            shared-keyword match) are merged into ONE task record; messages
            about different tasks stay in separate records.
3. TODO     each task record becomes exactly one todo. Provenance of every
            original message (platform / group / message id / sender / time)
            is kept inside the record and the todo note, so nothing of the
            action requirement is lost and every claim is traceable.

Ids are stable (hash of the sorted member message ids), so repeat runs
update instead of duplicating and never clobber a completed/removed state.

The older todo_import.py (per-message 1:1 import) is left untouched; this
module is the task-level path. The widget itself still never reads chat data.

License: Apache-2.0. See NOTICE.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from chatnotice import ROOT, project_path
from todo_import import compact_title, load_export
from todo_store import TodoStore

# ---------------------------------------------------------------- action cues
ACTION_PATTERNS = [
    r"请[^。；\n]{0,14}(帮忙|处理|确认|提交|填写|发送|提供|核对|审|修改|安排|跟进|落实|准备|回复|反馈|上报|看下|看看|查)",
    r"(麻烦|拜托|辛苦)[^。；\n]{0,10}(帮忙|处理|确认|发|看下|回复|填|核|跟进)",
    r"(需要|需)\s*[^。；\n]{0,10}(完成|提交|回复|确认|提供|反馈|上报|填写|处理|准备|补充|更新)",
    r"(记得|别忘了|别忘记|切记|务必|一定要|必须|尽快|抓紧|赶紧|及时|马上)",
    r"(截止|deadline|期限|之前完成|前完成|前交|日内完成|本周内|下周前)",
    r"(待办|待处理|待确认|待回复|待跟进|todo|action item)",
    r"@[^\s@，。；]+",
    r"(大家|各位|所有人|群里|同学们|小伙伴们)[^。；\n]{0,10}(帮忙|看下|处理|回复|确认|注意|查收)",
]
_ACTION_RE = re.compile("|".join(f"(?:{p})" for p in ACTION_PATTERNS), re.IGNORECASE)

_GAP_DEFAULT_MIN = 30
_MIN_SIM_DEFAULT = 0.30
_STRONG_SIM = 0.55  # cross-sender merge needs stronger evidence
_FOLLOWUP_RE = re.compile(r"(回复|收到|查收|补充|另外|还有|更正|综上|转述|代发)")
_FOLLOWUP_MAX_LEN = 24  # a short follow-up of the same sender belongs to the burst


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def is_actionable(text: str) -> bool:
    return len(text.strip()) >= 3 and bool(_ACTION_RE.search(text))


def bigrams(text: str) -> set:
    chars = re.sub(r"\s+", "", text)
    return {chars[i:i + 2] for i in range(len(chars) - 1)} or {chars}


def similarity(a: str, b: str) -> float:
    ga, gb = bigrams(a), bigrams(b)
    return len(ga & gb) / len(ga | gb)


# ------------------------------------------------------------------- stage 1
def filter_actionable(data: dict) -> tuple[list[dict], int]:
    """Return (actionable messages with cue annotation, skipped count)."""
    kept, skipped = [], 0
    for m in data.get("messages", []):
        if (m.get("platform") != "dingtalk" or m.get("body_status") != "decoded"
                or not m.get("text") or not data.get("group_chats_only")):
            skipped += 1
            continue
        if not is_actionable(m["text"]):
            skipped += 1
            continue
        kept.append(m)
    kept.sort(key=lambda m: (m.get("time", ""), m.get("message_id", "")))
    return kept, skipped


# ------------------------------------------------------------------- stage 2
def cluster_tasks(messages: list[dict], *, gap_min: int,
                  min_sim: float) -> list[list[dict]]:
    """Greedy clustering: same sender + time window + similar content.
    A short same-sender follow-up ("收到请回复1" / "补充：...") joins the burst
    it answers. Cross-sender merge only at strong similarity (same ask reposted)."""
    clusters: list[list[dict]] = []
    for m in messages:
        t = parse_time(m["time"])
        placed = False
        for c in clusters:
            last = c[-1]
            if (t - parse_time(last["time"])).total_seconds() > gap_min * 60:
                continue  # window closed; message belongs to a later burst
            same_sender = m.get("sender") == last.get("sender")
            best = max(similarity(m["text"], x["text"]) for x in c)
            followup = (same_sender and len(m["text"]) <= _FOLLOWUP_MAX_LEN and (
                bool(_FOLLOWUP_RE.search(m["text"]))
                or re.fullmatch(r"(?:@[^\s@，。；]+\s*)+", m["text"])))
            if (same_sender and best >= min_sim) or best >= _STRONG_SIM or followup:
                c.append(m)
                placed = True
                break
        if not placed:
            clusters.append([m])
    return clusters


def build_task_record(cluster: list[dict]) -> dict:
    first = cluster[0]
    digest = hashlib.sha1("|".join(sorted(str(m["message_id"]) for m in cluster))
                          .encode("utf-8")).hexdigest()[:12]
    sources = [{
        "platform": m.get("platform"), "group_id": m.get("group_id"),
        "group_name": m.get("group_name"), "message_id": m.get("message_id"),
        "sender": m.get("sender"), "time": m.get("time"),
    } for m in cluster]
    lines = [f"{i}. [{m.get('sender', '')} {m.get('time', '')}] {m['text']}"
             for i, m in enumerate(cluster, 1)]
    return {
        "task_id": f"dingtalk-task:{first['group_id']}:{digest}",
        "platform": first.get("platform"),
        "group_id": first.get("group_id"),
        "group_name": first.get("group_name"),
        "message_count": len(cluster),
        "time_range": [first.get("time"), cluster[-1].get("time")],
        "senders": sorted({m.get("sender", "") for m in cluster}),
        "description": "\n".join(lines),
        "sources": sources,
    }


def build_todo(record: dict) -> dict:
    head_text = max((s for s in (ln.split("] ", 1)[-1] for ln in
                                 record["description"].split("\n"))),
                    key=len, default="")
    title = compact_title(head_text)
    if record["message_count"] > 1:
        title = compact_title(f"{head_text}（同任务 {record['message_count']} 条合并）")
    return {
        "id": record["task_id"],
        "title": title or "[空文本消息]",
        "note": (f"任务记录（合并 {record['message_count']} 条消息，原始来源见下）：\n"
                 f"{record['description']}\n\n"
                 f"来源：钉钉群「{record.get('group_name', record['group_id'])}」 "
                 f"{record['time_range'][0]} ~ {record['time_range'][-1]}"),
        "source": (f"钉钉群「{record.get('group_name', record['group_id'])}」· "
                   f"{record['time_range'][0]}"),
    }


# ------------------------------------------------------------------- stage 3
def run(batch: str, *, gap_min: int, min_sim: float) -> dict:
    data = load_export(batch)
    actionable, skipped = filter_actionable(data)
    clusters = cluster_tasks(actionable, gap_min=gap_min, min_sim=min_sim)
    records = [build_task_record(c) for c in clusters]
    todos = [build_todo(r) for r in records]
    return {"batch": str(batch), "total_messages": len(data.get("messages", [])),
            "skipped_non_actionable": skipped, "filtered": actionable,
            "task_records": records, "todos": todos}


def write_reports(batch_dir: Path, result: dict) -> None:
    (batch_dir / "filtered_messages.json").write_text(json.dumps(
        result["filtered"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (batch_dir / "task_records.json").write_text(json.dumps(
        result["task_records"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=(
        "任务级导入：筛选含行动要求的消息 → 同任务多消息合并为一条任务记录 → "
        "每条任务一个待办；稳定ID幂等，保留每条消息原始来源"))
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--batch", help="导出批次目录，如 exports/20261015-103000-123456")
    source.add_argument("--latest", action="store_true", help="使用最近一次钉钉导出")
    parser.add_argument("--gap", type=int, default=_GAP_DEFAULT_MIN,
                        help=f"同发送者合并时间窗（分钟，默认 {_GAP_DEFAULT_MIN}）")
    parser.add_argument("--min-sim", type=float, default=_MIN_SIM_DEFAULT,
                        help=f"内容相似度阈值 0~1（默认 {_MIN_SIM_DEFAULT}）")
    parser.add_argument("--dry-run", action="store_true", help="只预览与写报告，不写入待办库")
    args = parser.parse_args(argv)
    try:
        if args.latest:
            pointer = project_path("state/latest-dingtalk-export.json")
            if not pointer.is_file():
                raise ValueError("尚无钉钉导出记录")
            args.batch = json.loads(pointer.read_text(encoding="utf-8"))["output_dir"]
        result = run(args.batch, gap_min=args.gap, min_sim=args.min_sim)
        batch_dir = (ROOT / result["batch"]).resolve()
        write_reports(batch_dir, result)

        print(f"== ① 筛选后消息列表：{len(result['filtered'])} 条"
              f"（跳过非行动要求 {result['skipped_non_actionable']} 条） ==")
        for m in result["filtered"]:
            print(f"  [{m.get('time','')[5:16]}] {m.get('sender','')}: {m['text'][:60]}")
        print(f"\n== ② 合并后任务记录：{len(result['task_records'])} 条 ==")
        for r in result["task_records"]:
            who = "/".join(r["senders"])
            print(f"  {r['task_id'][-12:]} | {r['message_count']}条 | {who} | "
                  f"{r['time_range'][0][5:16]}~{r['time_range'][-1][5:16]}")
        print(f"\n== ③ 按任务划分的待办清单：{len(result['todos'])} 项"
              f"{'（dry-run 未写入）' if args.dry_run else ''} ==")
        for t in result["todos"]:
            print(f"  {t['id']}\n    {t['title']}")

        if args.dry_run:
            return 0
        store = TodoStore()
        for todo in result["todos"]:
            store.upsert(**todo)  # same id => update; done/removed preserved
        print(json.dumps({
            "imported_tasks": len(result["todos"]),
            "filtered_messages": len(result["filtered"]),
            "idempotent": True, "completed_states_preserved": True,
            "reports": [str(batch_dir / "filtered_messages.json"),
                        str(batch_dir / "task_records.json")],
            "todo_db": "state/todos.sqlite3",
        }, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f"任务级导入失败：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
