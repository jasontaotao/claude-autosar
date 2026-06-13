"""T4.5b — `autoc log` CLI 单元测试。"""

from __future__ import annotations

from pathlib import Path
import time

import pytest

from claude_autosar.cli.commands.log import build_parser, run
from claude_autosar.core.session.store import SessionEntry, SessionStore, new_session_id


def _patch_session_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    cfg_dir = tmp_path / "fake_agent"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "claude_autosar.utils.paths.user_config_dir",
        lambda *a, **kw: str(cfg_dir),
    )
    return cfg_dir / "sessions"


def _seed_bsw_write_session(monkeypatch, tmp_path, *, changes: list[dict]) -> str:
    """塞一个含 bsw_write entry 的 session。

    changes: list of {module, path, op, value, old_value}
    """
    _patch_session_dir(monkeypatch, tmp_path)
    store = SessionStore()
    sid = new_session_id()
    store.append(
        SessionEntry(
            id="root",
            parent_id=None,
            session_id=sid,
            timestamp="2026-06-11T00:00:00.000Z",
            kind="user",
            content="帮我改",
        )
    )
    for i, ch in enumerate(changes):
        store.append(
            SessionEntry(
                id=f"t{i}",
                parent_id="root",
                session_id=sid,
                timestamp=f"2026-06-11T00:00:0{i + 1}.000Z",
                kind="tool",
                content="bsw_write",
                tool_name="bsw_write",
                tool_args=ch,
                tool_result="ok",
            )
        )
    return sid


# ---------------------------------------------------------------------------
# argparse
# ---------------------------------------------------------------------------


def test_argparse_requires_session_and_view() -> None:
    """log 必须有 --session 和 --view。"""
    parser = build_parser()
    # 缺 --view
    with pytest.raises(SystemExit):
        parser.parse_args(["log", "--session", "s1"])
    # 缺 --session
    with pytest.raises(SystemExit):
        parser.parse_args(["log", "--view", "timeline"])


def test_argparse_view_choices() -> None:
    """view 必须是 timeline 或 by-url。"""
    parser = build_parser()
    ns = parser.parse_args(["log", "--session", "s1", "--view", "timeline"])
    assert ns.view == "timeline"
    ns2 = parser.parse_args(["log", "--session", "s1", "--view", "by-url"])
    assert ns2.view == "by-url"
    # 非法 view
    with pytest.raises(SystemExit):
        parser.parse_args(["log", "--session", "s1", "--view", "wrong"])


# ---------------------------------------------------------------------------
# timeline
# ---------------------------------------------------------------------------


def test_log_timeline_prints_changes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    """timeline 视图打印 render_timeline 输出（含改参 URL）。"""
    sid = _seed_bsw_write_session(
        monkeypatch,
        tmp_path,
        changes=[
            {
                "module": "Mcu",
                "path": "ClockFreq",
                "op": "modify",
                "value": 80000000,
                "old_value": 40000000,
            },
        ],
    )
    ns = build_parser().parse_args(["log", "--session", sid, "--view", "timeline"])
    code = run(ns)
    out = capsys.readouterr().out
    assert code == 0
    assert "Mcu/ClockFreq" in out
    assert "MOD" in out


def test_log_by_url_groups_changes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    """by-url 视图按 URL 分组。"""
    sid = _seed_bsw_write_session(
        monkeypatch,
        tmp_path,
        changes=[
            {"module": "Mcu", "path": "A", "op": "modify", "value": 1, "old_value": 0},
            {"module": "Mcu", "path": "A", "op": "modify", "value": 2, "old_value": 1},
            {"module": "Port", "path": "B", "op": "add", "value": 42, "old_value": None},
        ],
    )
    ns = build_parser().parse_args(["log", "--session", sid, "--view", "by-url"])
    code = run(ns)
    out = capsys.readouterr().out
    assert code == 0
    assert "## Mcu/A" in out
    assert "## Port/B" in out


# ---------------------------------------------------------------------------
# 错误处理
# ---------------------------------------------------------------------------


def test_log_missing_session_returns_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    """session 不存在 → exit 1 + stderr 错误信息。"""
    _patch_session_dir(monkeypatch, tmp_path)
    ns = build_parser().parse_args(["log", "--session", "no-such-id", "--view", "timeline"])
    code = run(ns)
    captured = capsys.readouterr()
    assert code == 1
    assert "no-such-id" in captured.err or "not found" in captured.err.lower()


def test_log_latest_resolves(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    """log --session latest 解析为 mtime 最新。"""
    _seed_bsw_write_session(
        monkeypatch,
        tmp_path,
        changes=[{"module": "X", "path": "Y", "op": "add", "value": 1, "old_value": None}],
    )
    time.sleep(0.05)
    _seed_bsw_write_session(
        monkeypatch,
        tmp_path,
        changes=[
            {"module": "Mcu", "path": "ClockFreq", "op": "modify", "value": 80, "old_value": 40}
        ],
    )
    ns = build_parser().parse_args(["log", "--session", "latest", "--view", "timeline"])
    code = run(ns)
    out = capsys.readouterr().out
    assert code == 0
    assert "Mcu/ClockFreq" in out  # 来自最近的 session


def test_log_empty_changes_prints_placeholder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    """session 内无 bsw_write entry → 打印 "暂无" 占位，不抛。"""
    _patch_session_dir(monkeypatch, tmp_path)
    store = SessionStore()
    sid = new_session_id()
    store.append(
        SessionEntry(
            id="u1",
            parent_id=None,
            session_id=sid,
            timestamp="2026-06-11T00:00:00.000Z",
            kind="user",
            content="hi",
        )
    )
    ns = build_parser().parse_args(["log", "--session", sid, "--view", "timeline"])
    code = run(ns)
    out = capsys.readouterr().out
    assert code == 0
    assert "暂无" in out or "Timeline" in out
