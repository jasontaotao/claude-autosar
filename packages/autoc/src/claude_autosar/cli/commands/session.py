"""`autoc session` 子命令 — 会话查询与 fork。

Sprint 4 — T4.5a。提供 list / show / fork 三个子命令。
- list: 枚举 ``~/.autoc/agent/sessions/*.jsonl``
- show <id|latest>: 打印 session 详情（latest 解析为 mtime 最新）
- fork <entry_id> --session <sid>: 创建新 session，root 指向原 entry
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

def register(subparsers: Any) -> None:
    """挂载到主 argparse subparsers。"""
    p = subparsers.add_parser("session", help="会话查询与 fork")
    sub = p.add_subparsers(dest="session_command", required=True)

    # list
    sub.add_parser("list", help="列出所有 session id")

    # show
    sp = sub.add_parser("show", help="查看 session 详情")
    sp.add_argument("session_id", help="session id 或 'latest'")

    # fork
    sp = sub.add_parser("fork", help="从某 entry fork 新 session")
    sp.add_argument("entry_id", help="要 fork 的原 entry id")
    sp.add_argument(
        "--session",
        dest="source_session",
        required=True,
        help="源 session id",
    )


def build_parser() -> argparse.ArgumentParser:
    """为单元测试提供独立 parser（含 session 子命令）。"""
    parser = argparse.ArgumentParser(prog="autoc")
    sub = parser.add_subparsers(dest="command", required=False)
    register(sub)
    return parser


def run(args: argparse.Namespace) -> int:
    """执行 session 子命令。返回 exit code。"""
    from claude_autosar.core.session.store import (
        SessionStore,
        SessionStoreError,
        new_session_id,
    )
    from claude_autosar.core.session.tree import SessionTree

    store = SessionStore()
    cmd = args.session_command

    if cmd == "list":
        return _run_list(store)
    if cmd == "show":
        return _run_show(store, args.session_id)
    if cmd == "fork":
        return _run_fork(store, args.source_session, args.entry_id)

    print(json.dumps({"success": False, "error": f"unknown subcommand {cmd!r}"}))
    return 1


def _run_list(store: SessionStore) -> int:
    ids = store.list_session_ids()
    print(json.dumps({"success": True, "sessions": ids}))
    return 0


def _run_show(store: SessionStore, session_id: str) -> int:
    from claude_autosar.core.session.store import SessionStoreError

    if session_id == "latest":
        resolved = _resolve_latest(store)
        if resolved is None:
            print(
                json.dumps({"success": False, "error": "no sessions found"}),
                file=sys.stderr,
            )
            return 1
        session_id = resolved
    try:
        session = store.read(session_id)
    except SessionStoreError as e:
        print(
            json.dumps({"success": False, "error": str(e), "session_id": session_id}),
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "success": True,
                "id": session.id,
                "title": session.title,
                "started_at": session.started_at,
                "entries": [
                    {
                        "id": e.id,
                        "parent_id": e.parent_id,
                        "timestamp": e.timestamp,
                        "kind": e.kind,
                        "content": e.content,
                        "tool_name": e.tool_name,
                        "tool_args": e.tool_args,
                        "tool_result": e.tool_result,
                    }
                    for e in session.entries
                ],
            },
            ensure_ascii=False,
        )
    )
    return 0


def _run_fork(store: SessionStore, source_session: str, entry_id: str) -> int:
    from claude_autosar.core.session.store import SessionStoreError, new_session_id
    from claude_autosar.core.session.tree import SessionTree

    try:
        source_tree = SessionTree.from_session_id(source_session, store)
    except SessionStoreError as e:
        print(
            json.dumps({"success": False, "error": str(e)}),
            file=sys.stderr,
        )
        return 1
    new_sid = new_session_id()
    forked = source_tree.fork(parent_entry_id=entry_id, new_session_id=new_sid)
    # 把新 root 落盘（fork_root 是唯一 entry，append 即写入）
    store.append(forked.session.entries[0])
    print(
        json.dumps(
            {
                "success": True,
                "new_session_id": new_sid,
                "parent_entry_id": entry_id,
                "source_session_id": source_session,
            }
        )
    )
    return 0


def _resolve_latest(store: SessionStore) -> str | None:
    """按 mtime 找最新 session id。Sprint 5：委托给 :func:`resolve_latest_session_id`。"""
    from claude_autosar.core.session.store import resolve_latest_session_id

    return resolve_latest_session_id(store.dir)
