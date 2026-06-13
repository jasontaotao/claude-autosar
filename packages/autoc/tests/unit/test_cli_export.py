"""T4.5c — `autoc export` CLI 单元测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from claude_autosar.cli.commands.export import build_parser, run
from claude_autosar.core.session.store import SessionEntry, SessionStore, new_session_id


def _patch_session_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    cfg_dir = tmp_path / "fake_agent"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "claude_autosar.utils.paths.user_config_dir",
        lambda *a, **kw: str(cfg_dir),
    )
    return cfg_dir / "sessions"


def _seed_session(monkeypatch, tmp_path, *, entries: list[SessionEntry] | None = None) -> str:
    _patch_session_dir(monkeypatch, tmp_path)
    store = SessionStore()
    sid = new_session_id()
    if entries is None:
        entries = [
            SessionEntry(
                id="u1",
                parent_id=None,
                session_id=sid,
                timestamp="2026-06-11T00:00:00.000Z",
                kind="user",
                content="hello",
            )
        ]
    for e in entries:
        store.append(e)
    return sid


# ---------------------------------------------------------------------------
# argparse
# ---------------------------------------------------------------------------


def test_argparse_requires_session_and_output() -> None:
    """export 必须有 --session 和 --output。"""
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["export"])
    with pytest.raises(SystemExit):
        parser.parse_args(["export", "--session", "s1"])
    with pytest.raises(SystemExit):
        parser.parse_args(["export", "--output", "x.html"])


# ---------------------------------------------------------------------------
# 成功路径
# ---------------------------------------------------------------------------


def test_export_writes_html_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    """export 成功写出 HTML 文件，stdout 返回 success 状态。"""
    sid = _seed_session(monkeypatch, tmp_path)
    out = tmp_path / "out.html"
    ns = build_parser().parse_args(
        [
            "export",
            "--session",
            sid,
            "--output",
            str(out),
        ]
    )
    code = run(ns)
    assert code == 0
    assert out.is_file()
    content = out.read_text(encoding="utf-8")
    assert "<html" in content.lower()
    # stdout 有 success 状态
    stdout = capsys.readouterr().out
    payload = json.loads(stdout)
    assert payload["success"] is True
    assert payload["session_id"] == sid


def test_export_creates_parent_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """输出路径父目录不存在时自动创建。"""
    sid = _seed_session(monkeypatch, tmp_path)
    out = tmp_path / "subdir" / "deep" / "out.html"
    ns = build_parser().parse_args(
        [
            "export",
            "--session",
            sid,
            "--output",
            str(out),
        ]
    )
    code = run(ns)
    assert code == 0
    assert out.is_file()


def test_export_latest_resolves(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """--session latest 解析为 mtime 最新。"""
    import time

    _seed_session(monkeypatch, tmp_path)
    time.sleep(0.05)
    _seed_session(
        monkeypatch,
        tmp_path,
        entries=[
            SessionEntry(
                id="u1",
                parent_id=None,
                session_id=new_session_id(),
                timestamp="2026-06-11T00:00:00.000Z",
                kind="user",
                content="latest content",
            )
        ],
    )
    out = tmp_path / "out.html"
    ns = build_parser().parse_args(
        [
            "export",
            "--session",
            "latest",
            "--output",
            str(out),
        ]
    )
    code = run(ns)
    assert code == 0
    content = out.read_text(encoding="utf-8")
    assert "latest content" in content


# ---------------------------------------------------------------------------
# 错误处理
# ---------------------------------------------------------------------------


def test_export_missing_session_returns_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    """session 不存在 → exit 1。"""
    _patch_session_dir(monkeypatch, tmp_path)
    out = tmp_path / "out.html"
    ns = build_parser().parse_args(
        [
            "export",
            "--session",
            "no-such-id",
            "--output",
            str(out),
        ]
    )
    code = run(ns)
    captured = capsys.readouterr()
    assert code == 1
    assert "no-such-id" in captured.err or "not found" in captured.err.lower()
    # 不应写出空文件
    assert not out.exists()
