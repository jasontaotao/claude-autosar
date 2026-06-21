"""Session / log export tools — moved from mcp_server.py."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from claude_autosar.cli.mcp_tools.validation import validate_no_traversal


def session_list(*, session_dir: str | None = None) -> list[str] | dict[str, Any]:
    """列出所有 session id。

    :return: session id 列表；路径校验失败时返回 error dict。
    """
    from claude_autosar.cli.mcp_server import _default_session_dir, _resolve_safe_project
    from claude_autosar.core.session.store import SessionStore

    if session_dir:
        try:
            validate_no_traversal(session_dir)
            _resolve_safe_project(session_dir)
        except ValueError as e:
            return {"success": False, "error": str(e)}
        except PermissionError as e:
            return {"success": False, "error": f"{type(e).__name__}: {e}"}
    d = Path(session_dir) if session_dir else _default_session_dir()
    return SessionStore(dir=d).list_session_ids()


def session_show(session_id: str, *, session_dir: str | None = None) -> dict[str, Any]:
    """读单个 session 全部 entry。

    支持特殊值 ``"latest"``：解析为 session_dir 下 mtime 最大的 session。
    """
    from claude_autosar.cli.mcp_server import _default_session_dir, _resolve_safe_project
    from claude_autosar.core.session.store import SessionStore, SessionStoreError

    if session_dir:
        try:
            _resolve_safe_project(session_dir)
        except (ValueError, PermissionError) as e:
            return {"success": False, "error": f"{type(e).__name__}: {e}"}
    # M9: 校验 session_id 路径遍历（防止 dir/session_id.jsonl 逃逸）
    if session_id != "latest":
        try:
            validate_no_traversal(session_id)
        except ValueError as e:
            return {"success": False, "error": str(e)}
    d = Path(session_dir) if session_dir else _default_session_dir()
    if session_id == "latest":
        from claude_autosar.core.session.store import resolve_latest_session_id

        latest = resolve_latest_session_id(d)
        if latest is None:
            return {"success": False, "error": "no sessions found"}
        session_id = latest
    try:
        sess = SessionStore(dir=d).read(session_id)
    except SessionStoreError as e:
        return {"success": False, "error": str(e)}
    return {
        "success": True,
        "session_id": sess.id,
        "started_at": sess.started_at,
        "title": sess.title,
        "entries": [
            {
                "id": e.id,
                "parent_id": e.parent_id,
                "session_id": e.session_id,
                "timestamp": e.timestamp,
                "kind": e.kind,
                "content": e.content,
                "tool_name": e.tool_name,
                "tool_args": e.tool_args,
                "tool_result": e.tool_result,
            }
            for e in sess.entries
        ],
    }


def session_export(
    session_id: str,
    fmt: str = "html",
    *,
    output: str | None = None,
    session_dir: str | None = None,
) -> dict[str, Any]:
    """导出 session 为 ``fmt`` 格式（当前仅支持 ``html``）。"""
    from claude_autosar.cli.mcp_server import _default_session_dir, _resolve_safe_project
    from claude_autosar.core.session.exporter import export_html
    from claude_autosar.core.session.store import SessionStore, SessionStoreError
    from claude_autosar.core.session.tree import SessionTree

    if fmt != "html":
        return {"success": False, "error": f"unsupported fmt: {fmt!r} (only 'html')"}
    if session_dir:
        try:
            _resolve_safe_project(session_dir)
        except (ValueError, PermissionError) as e:
            return {"success": False, "error": f"{type(e).__name__}: {e}"}
    # M9: 校验 session_id 路径遍历
    if session_id != "latest":
        try:
            validate_no_traversal(session_id)
        except ValueError as e:
            return {"success": False, "error": str(e)}
    # HIGH-3 修复：自定义 output 必须通过 H4 containment check
    # （默认 output = d/<id>.html 已在 d 内，d 已通过 _resolve_safe_project）
    if output:
        try:
            _resolve_safe_project(output)
        except PermissionError as e:
            return {"success": False, "error": f"{type(e).__name__}: {e}"}
    d = Path(session_dir) if session_dir else _default_session_dir()
    if session_id == "latest":
        from claude_autosar.core.session.store import resolve_latest_session_id

        latest = resolve_latest_session_id(d)
        if latest is None:
            return {"success": False, "error": "no sessions found"}
        session_id = latest
    out_path = Path(output) if output else d / f"{session_id}.html"
    try:
        tree = SessionTree.from_session_id(session_id, SessionStore(dir=d))
    except SessionStoreError as e:
        return {"success": False, "error": str(e)}
    try:
        written = export_html(tree, out_path)
    except OSError as e:
        return {"success": False, "error": f"OSError: {e}"}
    return {
        "success": True,
        "session_id": session_id,
        "format": fmt,
        "path": str(written),
    }


def log_export(
    session_id: str,
    view: str = "timeline",
    *,
    session_dir: str | None = None,
) -> dict[str, Any]:
    """从 session 提取 ``bsw_write`` entry，渲染成 timeline / by-url 文本。"""
    from claude_autosar.cli.mcp_server import _default_session_dir, _resolve_safe_project
    from claude_autosar.core.log.changelog import extract_changes, render_by_url, render_timeline
    from claude_autosar.core.session.store import SessionStore, SessionStoreError
    from claude_autosar.core.session.tree import SessionTree

    if view not in {"timeline", "by-url"}:
        return {"success": False, "error": f"unsupported view: {view!r}"}
    if session_dir:
        try:
            _resolve_safe_project(session_dir)
        except (ValueError, PermissionError) as e:
            return {"success": False, "error": f"{type(e).__name__}: {e}"}
    # M9: 校验 session_id 路径遍历
    if session_id != "latest":
        try:
            validate_no_traversal(session_id)
        except ValueError as e:
            return {"success": False, "error": str(e)}
    d = Path(session_dir) if session_dir else _default_session_dir()
    if session_id == "latest":
        from claude_autosar.core.session.store import resolve_latest_session_id

        latest = resolve_latest_session_id(d)
        if latest is None:
            return {"success": False, "error": "no sessions found"}
        session_id = latest
    try:
        tree = SessionTree.from_session_id(session_id, SessionStore(dir=d))
    except SessionStoreError as e:
        return {"success": False, "error": str(e)}
    changes = extract_changes(tree)
    text = render_timeline(changes) if view == "timeline" else render_by_url(changes)
    return {
        "success": True,
        "session_id": session_id,
        "view": view,
        "change_count": len(changes),
        "text": text,
    }
