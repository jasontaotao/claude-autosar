"""`autoc export` 子命令 — 导出 session 为 HTML。

Sprint 4 — T4.5c。把指定 session 渲染为自包含 HTML（含改参 callout）。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from autoc.core.session.exporter import export_html
from autoc.core.session.store import SessionStore, SessionStoreError
from autoc.core.session.tree import SessionTree


def register(subparsers: Any) -> None:
    """挂载到主 argparse subparsers。"""
    p = subparsers.add_parser("export", help="导出 session 为 HTML")
    p.add_argument(
        "--session",
        dest="session_id",
        required=True,
        help="session id 或 'latest'",
    )
    p.add_argument(
        "--output",
        dest="output_path",
        required=True,
        type=Path,
        help="输出 HTML 路径",
    )


def build_parser() -> argparse.ArgumentParser:
    """为单元测试提供独立 parser。"""
    parser = argparse.ArgumentParser(prog="autoc")
    sub = parser.add_subparsers(dest="command", required=False)
    register(sub)
    return parser


def run(args: argparse.Namespace) -> int:
    """执行 export 子命令。返回 exit code。"""
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
    try:
        out_path = export_html(tree, args.output_path)
    except OSError as e:
        print(
            json.dumps({"success": False, "error": f"write failed: {e}"}),
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "success": True,
                "session_id": sid,
                "output_path": str(out_path),
            }
        )
    )
    return 0


def _resolve_latest(store: SessionStore) -> str | None:
    """按 mtime 找最新 session id。Sprint 5：委托给 :func:`resolve_latest_session_id`。"""
    from autoc.core.session.store import resolve_latest_session_id

    return resolve_latest_session_id(store.dir)
