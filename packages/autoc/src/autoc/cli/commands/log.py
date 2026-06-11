"""`autoc log` 子命令 — 改参 changelog 渲染。

Sprint 4 — T4.5b。从指定 session 提取 bsw_write entry 并按 timeline
或 by-url 两种视图输出。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from autoc.core.log.changelog import (
    extract_changes,
    render_by_url,
    render_timeline,
)
from autoc.core.session.store import SessionStore, SessionStoreError
from autoc.core.session.tree import SessionTree


def register(subparsers: Any) -> None:
    """挂载到主 argparse subparsers。"""
    p = subparsers.add_parser("log", help="改参 changelog")
    p.add_argument(
        "--session",
        dest="session_id",
        required=True,
        help="session id 或 'latest'",
    )
    p.add_argument(
        "--view",
        choices=["timeline", "by-url"],
        required=True,
        help="渲染视图",
    )


def build_parser() -> argparse.ArgumentParser:
    """为单元测试提供独立 parser（含 log 子命令）。"""
    parser = argparse.ArgumentParser(prog="autoc")
    sub = parser.add_subparsers(dest="command", required=False)
    register(sub)
    return parser


def run(args: argparse.Namespace) -> int:
    """执行 log 子命令。返回 exit code。"""
    store = SessionStore()
    sid = args.session_id
    if sid == "latest":
        resolved = _resolve_latest(store)
        if resolved is None:
            print(
                json.dumps({"success": False, "error": "no sessions found"}),
                file=sys.stderr,
            )
            return 1
        sid = resolved
    try:
        session = store.read(sid)
    except SessionStoreError as e:
        print(
            json.dumps({"success": False, "error": str(e), "session_id": sid}),
            file=sys.stderr,
        )
        return 1
    tree = SessionTree(session=session)
    changes = extract_changes(tree)
    if args.view == "timeline":
        print(render_timeline(changes))
    else:
        print(render_by_url(changes))
    return 0


def _resolve_latest(store: SessionStore) -> str | None:
    """按 mtime 找最新 session id。"""
    sessions_dir: Path = store.dir
    files = [p for p in sessions_dir.iterdir() if p.is_file() and p.suffix == ".jsonl"]
    if not files:
        return None
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0].stem
