"""session_show / session_export / log_export 覆盖测试。

从 ``test_mcp_server_extra_coverage.py`` 拆分而来。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.autosar


@pytest.fixture(autouse=True)
def _snapshot_mcp_server_globals() -> Any:
    """每个 test 后还原 _ALLOWED_PROJECT_ROOTS / _default_session_dir。"""
    from claude_autosar.cli import mcp_server

    original_roots = mcp_server._ALLOWED_PROJECT_ROOTS
    original_default_dir = mcp_server._default_session_dir
    original_tresos_home = mcp_server._default_tresos_home
    yield
    mcp_server._ALLOWED_PROJECT_ROOTS = original_roots
    mcp_server._default_session_dir = original_default_dir
    mcp_server._default_tresos_home = original_tresos_home


# ---------------------------------------------------------------------------
# session_show — SessionStoreError / happy
# ---------------------------------------------------------------------------


def test_session_show_session_store_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SessionStoreError 路径（line 695-696）。"""
    from claude_autosar.cli.mcp_server import session_show
    from claude_autosar.core.session.store import SessionStoreError

    monkeypatch.setattr("claude_autosar.cli.mcp_server._default_session_dir", lambda: tmp_path)

    def _raise_store(*_a: Any, **_kw: Any) -> None:
        raise SessionStoreError("corrupt jsonl")

    monkeypatch.setattr(
        "claude_autosar.core.session.store.SessionStore.read", _raise_store
    )
    r = session_show("s1", session_dir=str(tmp_path))
    assert r["success"] is False
    assert "corrupt jsonl" in r["error"]


def test_session_show_happy_with_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """happy path: 1 个 user entry → entries 序列化正确。"""
    from claude_autosar.cli.mcp_server import session_show
    from claude_autosar.core.session.store import SessionEntry, SessionStore

    monkeypatch.setattr("claude_autosar.cli.mcp_server._default_session_dir", lambda: tmp_path)
    store = SessionStore(dir=tmp_path)
    store.append(
        SessionEntry(
            id="e1",
            parent_id=None,
            session_id="s1",
            timestamp="2026-01-01T00:00:00+00:00",
            kind="user",
            content="hello",
        )
    )
    r = session_show("s1", session_dir=str(tmp_path))
    assert r["success"] is True
    assert r["session_id"] == "s1"
    assert len(r["entries"]) == 1
    assert r["entries"][0]["content"] == "hello"


# ---------------------------------------------------------------------------
# session_export — OSError / SessionStoreError
# ---------------------------------------------------------------------------


def test_session_export_oserror_writing_html(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """export_html 抛 OSError（line 748-749）。"""
    from claude_autosar.cli.mcp_server import session_export
    from claude_autosar.core.session.store import SessionEntry, SessionStore

    monkeypatch.setattr("claude_autosar.cli.mcp_server._default_session_dir", lambda: tmp_path)
    store = SessionStore(dir=tmp_path)
    store.append(
        SessionEntry(
            id="e1",
            parent_id=None,
            session_id="s1",
            timestamp="2026-01-01T00:00:00+00:00",
            kind="user",
            content="hi",
        )
    )

    def _raise_os(*_a: Any, **_kw: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("claude_autosar.core.session.exporter.export_html", _raise_os)
    r = session_export("s1", fmt="html", session_dir=str(tmp_path))
    assert r["success"] is False
    assert "OSError" in r["error"]
    assert "disk full" in r["error"]


def test_session_export_session_store_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SessionStoreError from SessionTree.from_session_id（line 744-745）。"""
    from claude_autosar.cli.mcp_server import session_export
    from claude_autosar.core.session.store import SessionStoreError

    monkeypatch.setattr("claude_autosar.cli.mcp_server._default_session_dir", lambda: tmp_path)

    def _raise_store(*_a: Any, **_kw: Any) -> None:
        raise SessionStoreError("no such session")

    monkeypatch.setattr(
        "claude_autosar.core.session.tree.SessionTree.from_session_id", _raise_store
    )
    r = session_export("s1", fmt="html", session_dir=str(tmp_path))
    assert r["success"] is False
    assert "no such session" in r["error"]


# ---------------------------------------------------------------------------
# log_export — SessionStoreError / by-url view
# ---------------------------------------------------------------------------


def test_log_export_session_store_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """log_export SessionStoreError 路径（line 781-782）。"""
    from claude_autosar.cli.mcp_server import log_export
    from claude_autosar.core.session.store import SessionStoreError

    monkeypatch.setattr("claude_autosar.cli.mcp_server._default_session_dir", lambda: tmp_path)

    def _raise_store(*_a: Any, **_kw: Any) -> None:
        raise SessionStoreError("missing session")

    monkeypatch.setattr(
        "claude_autosar.core.session.tree.SessionTree.from_session_id", _raise_store
    )
    r = log_export("s1", session_dir=str(tmp_path))
    assert r["success"] is False
    assert "missing session" in r["error"]


def test_log_export_by_url_view(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """view='by-url' 走 render_by_url（line 784）。"""
    from claude_autosar.cli.mcp_server import log_export
    from claude_autosar.core.session.store import SessionEntry, SessionStore

    monkeypatch.setattr("claude_autosar.cli.mcp_server._default_session_dir", lambda: tmp_path)
    store = SessionStore(dir=tmp_path)
    store.append(
        SessionEntry(
            id="e1",
            parent_id=None,
            session_id="s1",
            timestamp="2026-01-01T00:00:00+00:00",
            kind="user",
            content="x",
        )
    )
    r = log_export("s1", view="by-url", session_dir=str(tmp_path))
    assert r["success"] is True
    assert r["view"] == "by-url"
    # by-url 渲染输出含 'URL' 字样（保守检查；避免硬编码中文）
    assert "URL" in r["text"] or "url" in r["text"].lower() or r["change_count"] == 0
