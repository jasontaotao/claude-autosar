"""T4.5a — `autoc session` CLI 单元测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from claude_autosar.cli.commands.session import build_parser, run
from claude_autosar.core.session.store import SessionEntry, SessionStore, new_session_id


def _patch_session_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    cfg_dir = tmp_path / "fake_agent"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "claude_autosar.utils.paths.user_config_dir",
        lambda *a, **kw: str(cfg_dir),
    )
    return cfg_dir / "sessions"


def _seed_session(monkeypatch, tmp_path, content: str = "hello") -> str:
    """塞一条 entry，返回 session id。"""
    _patch_session_dir(monkeypatch, tmp_path)
    store = SessionStore()
    sid = new_session_id()
    store.append(
        SessionEntry(
            id="e1",
            parent_id=None,
            session_id=sid,
            timestamp="2026-06-11T00:00:00.000Z",
            kind="user",
            content=content,
        )
    )
    return sid


# ---------------------------------------------------------------------------
# argparse
# ---------------------------------------------------------------------------


def test_argparse_has_list_show_fork_subcommands() -> None:
    """session 命令必须含 list/show/fork 3 个子命令。"""
    parser = build_parser()
    # 解析各子命令应不抛 SystemExit
    for argv, expected_cmd in [
        (["session", "list"], "list"),
        (["session", "show", "abc"], "show"),
        (["session", "fork", "e1", "--session", "s1"], "fork"),
    ]:
        ns = parser.parse_args(argv)
        assert ns.session_command == expected_cmd, f"failed for {argv}"


def test_show_requires_session_id() -> None:
    """session show 必须有 session id 参数。"""
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["session", "show"])


def test_fork_requires_entry_id() -> None:
    """session fork 必须有 entry id 参数。"""
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["session", "fork"])


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_list_finds_existing_sessions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    """list 列出所有 session id（JSON 输出）。"""
    sid = _seed_session(monkeypatch, tmp_path)
    ns = build_parser().parse_args(["session", "list"])
    code = run(ns)
    out = capsys.readouterr().out
    assert code == 0
    payload = json.loads(out)
    assert sid in payload["sessions"]


def test_list_empty_dir_returns_empty_sessions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    """空目录 → 空 sessions 列表，exit code 0。"""
    _patch_session_dir(monkeypatch, tmp_path)
    ns = build_parser().parse_args(["session", "list"])
    code = run(ns)
    out = capsys.readouterr().out
    assert code == 0
    payload = json.loads(out)
    assert payload["sessions"] == []


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


def test_show_existing_session(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    """show 已知 session → JSON 包含 id + entries。"""
    sid = _seed_session(monkeypatch, tmp_path, content="帮我改 Mcu")
    ns = build_parser().parse_args(["session", "show", sid])
    code = run(ns)
    out = capsys.readouterr().out
    assert code == 0
    payload = json.loads(out)
    assert payload["id"] == sid
    assert len(payload["entries"]) == 1
    assert payload["entries"][0]["content"] == "帮我改 Mcu"


def test_show_missing_session_returns_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    """show 不存在 session → 错误输出 + exit code 1。"""
    _patch_session_dir(monkeypatch, tmp_path)
    ns = build_parser().parse_args(["session", "show", "nonexistent-id"])
    code = run(ns)
    captured = capsys.readouterr()
    assert code == 1
    # 错误写到 stdout (JSON) or stderr；至少有一处说明
    combined = captured.out + captured.err
    assert "nonexistent-id" in combined or "not found" in combined.lower()


def test_show_latest_resolves_to_most_recent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    """show latest → 最近 mtime 的 session。"""
    import time

    _seed_session(monkeypatch, tmp_path, content="old")
    time.sleep(0.05)
    s_new = _seed_session(monkeypatch, tmp_path, content="new")
    ns = build_parser().parse_args(["session", "show", "latest"])
    code = run(ns)
    out = capsys.readouterr().out
    assert code == 0
    payload = json.loads(out)
    assert payload["id"] == s_new


# ---------------------------------------------------------------------------
# fork
# ---------------------------------------------------------------------------


def test_fork_creates_new_session_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    """fork 创建一个以 entry 为 parent 的新 session。"""
    sid = _seed_session(monkeypatch, tmp_path)
    ns = build_parser().parse_args(
        [
            "session",
            "fork",
            "e1",
            "--session",
            sid,
        ]
    )
    code = run(ns)
    out = capsys.readouterr().out
    assert code == 0
    payload = json.loads(out)
    new_sid = payload["new_session_id"]
    assert new_sid != sid
    # 新 session 文件存在
    store = SessionStore()
    new_tree = store.read(new_sid)
    assert new_tree.entries[0].parent_id == "e1"


def test_fork_missing_session_returns_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """fork 源 session 不存在 → exit 1。"""
    _patch_session_dir(monkeypatch, tmp_path)
    ns = build_parser().parse_args(
        [
            "session",
            "fork",
            "e1",
            "--session",
            "no-such-session",
        ]
    )
    code = run(ns)
    assert code == 1
