"""Unit tests for autoc.cli.mcp_server.

Sprint 5 — T5.3。10 个 MCP 工具的注册 + 行为。

- FastMCP 实例上能查到全部 10 个 tool
- 至少 3 个工具走 happy path（dbc_parse / session_list / log_export）
- 错误路径返回 dict（不抛异常），让 MCP 客户端能拿到结构化错误
"""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_autosar.cli.mcp_server import (
    _TOOL_NAMES,
    build_mcp_server,
)

pytestmark = pytest.mark.autosar


# ---------------------------------------------------------------------------
# Tool 注册
# ---------------------------------------------------------------------------


_EXPECTED_TOOLS = {
    "bsw_read",
    "bsw_write",
    "bsw_verify",
    "bsw_autocalc",
    "arxml_validate",
    "dbc_parse",
    "session_list",
    "session_show",
    "session_export",
    "log_export",
}


def test_build_mcp_server_returns_fastmcp_instance() -> None:
    """Sanity：build_mcp_server 返回 FastMCP 实例（来自 mcp.server.fastmcp）。"""
    from mcp.server.fastmcp import FastMCP

    server = build_mcp_server()
    assert isinstance(server, FastMCP)


def test_tool_names_constant_matches_spec() -> None:
    """_TOOL_NAMES 是 T3.1 节规定的 10 个 tool 名集合（顺序独立）。"""
    assert set(_TOOL_NAMES) == _EXPECTED_TOOLS
    assert len(_TOOL_NAMES) == 10


def test_mcp_server_registers_all_ten_tools() -> None:
    """FastMCP 内部 _tool_manager 能查到全部 10 个 tool。"""
    server = build_mcp_server()
    tm = getattr(server, "_tool_manager", None)
    assert tm is not None
    # FastMCP 1.27.x: _tool_manager._tools 是 dict[str, Tool]
    tools_dict = getattr(tm, "_tools", None) or {}
    registered = set(tools_dict.keys())
    missing = _EXPECTED_TOOLS - registered
    assert not missing, f"missing tools: {missing}"


# ---------------------------------------------------------------------------
# Tool 函数：直接调用（绕过 FastMCP transport，测业务逻辑）
# ---------------------------------------------------------------------------


def test_dbc_parse_returns_messages_dict(tmp_path: Path) -> None:
    """dbc_parse happy path：返回 messages 数组。"""
    from claude_autosar.cli.mcp_server import dbc_parse

    dbc = tmp_path / "test.dbc"
    dbc.write_text(
        """
VERSION ""


NS_ :

BS_:

BU_: ECU1 ECU2

BO_ 100 Msg1: 8 ECU1
 SG_ Sig1 : 0|16@1+ (0.1,0) [0|65535] "rpm" ECU2
 SG_ Sig2 : 16|8@1+ (1,-40) [-40|215] "degC" ECU2

BO_ 200 Msg2: 4 ECU1
 SG_ Sig3 : 0|8@1+ (1,0) [0|255] "" ECU2
""",
        encoding="utf-8",
    )
    result = dbc_parse(str(dbc))
    assert result["success"] is True
    assert result["path"] == str(dbc)
    names = {m["name"] for m in result["messages"]}
    assert "Msg1" in names and "Msg2" in names
    sig1 = next(
        s
        for m in result["messages"]
        if m["name"] == "Msg1"
        for s in m["signals"]
        if s["name"] == "Sig1"
    )
    assert sig1["unit"] == "rpm"
    assert sig1["scale"] == pytest.approx(0.1)


def test_dbc_parse_invalid_file_returns_error_dict(tmp_path: Path) -> None:
    """dbc_parse 错误路径：返回 success=False + error 字段。"""
    from claude_autosar.cli.mcp_server import dbc_parse

    not_a_dbc = tmp_path / "garbage.dbc"
    not_a_dbc.write_text("this is not a valid DBC", encoding="utf-8")
    result = dbc_parse(str(not_a_dbc))
    assert result["success"] is False
    assert "error" in result


def test_dbc_parse_missing_file_returns_error_dict(tmp_path: Path) -> None:
    from claude_autosar.cli.mcp_server import dbc_parse

    result = dbc_parse(str(tmp_path / "no_such.dbc"))
    assert result["success"] is False


# ---------------------------------------------------------------------------
# bsw_read / bsw_write 路径防御（H4）+ 参数 schema（H3）
# ---------------------------------------------------------------------------


def test_bsw_read_rejects_path_traversal() -> None:
    """H4 回归：bsw_read project 必须在允许的根之下。"""
    from claude_autosar.cli.mcp_server import bsw_read

    result = bsw_read("Mcu", "ClockFreq", project="/etc")
    assert result["success"] is False
    assert "PermissionError" in result["error"] or "outside" in result["error"]


def test_bsw_write_rejects_path_traversal() -> None:
    """H4 回归：bsw_write project 路径穿越被拒。"""
    from claude_autosar.cli.mcp_server import bsw_write

    result = bsw_write(
        "Mcu",
        [{"path": "Mcu/Clock/ClockFreq", "value": 80000000, "type": "integer"}],
        project="/nonexistent_root_for_test",
    )
    assert result["success"] is False


def test_bsw_write_rejects_bad_param_with_index() -> None:
    """H3 回归：bsw_write 缺字段时返回 param_index 帮 LLM 定位。"""
    from claude_autosar.cli.mcp_server import bsw_write

    result = bsw_write(
        "Mcu",
        [
            {"path": "Mcu/Clock/ClockFreq", "value": 1, "type": "integer"},
            {"name": "wrong_key"},  # 缺 path / value
        ],
        project=".",
    )
    assert result["success"] is False
    assert result.get("param_index") == 1
    assert result.get("field") in {"path", "value"}


def test_bsw_write_rejects_unknown_type() -> None:
    """H3 补充：未知 ParamType 给出可读错误 + param_index。"""
    from claude_autosar.cli.mcp_server import bsw_write

    result = bsw_write(
        "Mcu",
        [
            {"path": "Mcu/Clock/ClockFreq", "value": 1, "type": "integer"},
            {"path": "Mcu/Clock/ClockFreq2", "value": 2, "type": "bool"},
        ],
        project=".",
    )
    assert result["success"] is False
    assert result.get("param_index") == 1
    assert result.get("field") == "type"
    assert "bool" in result["error"]


# ---------------------------------------------------------------------------
# Session tool 行为
# ---------------------------------------------------------------------------


def test_session_list_empty_store_returns_empty_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """空 store → session_list 返回 []。"""
    from claude_autosar.cli.mcp_server import session_list

    monkeypatch.setattr("claude_autosar.cli.mcp_server._default_session_dir", lambda: tmp_path)
    result = session_list()
    assert result == []


def test_session_show_returns_dict_with_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """session_show happy：返回 dict 包含 id/started_at/entries。"""
    from claude_autosar.cli.mcp_server import session_show

    monkeypatch.setattr("claude_autosar.cli.mcp_server._default_session_dir", lambda: tmp_path)
    store = _build_store(tmp_path)
    _append_user_entry(store, "s1", "hello")
    _append_tool_entry(store, "s1", tool_name="bsw_write", tool_args={"x": 1})

    result = session_show("s1")
    assert result["success"] is True
    assert result["session_id"] == "s1"
    assert "entries" in result
    assert len(result["entries"]) == 2


def test_session_show_latest_resolves_by_mtime_not_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M19 / H1 回归：``latest`` 必须按 mtime 排序解析，而非字母序。

    排序：``zzz`` 字母序在前，但 mtime 旧；``aaa`` 字母序在后，但 mtime 新。
    期望 ``session_show("latest")`` 返回 ``aaa``。
    """
    import os

    from claude_autosar.cli.mcp_server import session_show

    monkeypatch.setattr("claude_autosar.cli.mcp_server._default_session_dir", lambda: tmp_path)
    store = _build_store(tmp_path)
    # 先建 zzz（旧 mtime）
    _append_user_entry(store, "zzz", "old")
    # 再建 aaa（新 mtime）
    _append_user_entry(store, "aaa", "new")
    # 把 zzz 的 mtime 调旧一点
    zzz_path = tmp_path / "zzz.jsonl"
    old_time = 1_000_000  # 2001-09-09
    os.utime(zzz_path, (old_time, old_time))

    result = session_show("latest")
    assert result["success"] is True
    # 必须是 mtime 新的 aaa，不是字母序的 zzz
    assert result["session_id"] == "aaa"


def test_session_show_missing_returns_error_dict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from claude_autosar.cli.mcp_server import session_show

    monkeypatch.setattr("claude_autosar.cli.mcp_server._default_session_dir", lambda: tmp_path)
    result = session_show("nonexistent_session_id_xyz")
    assert result["success"] is False
    assert "error" in result


# ---------------------------------------------------------------------------
# log_export 行为
# ---------------------------------------------------------------------------


def test_log_export_timeline_produces_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """log_export(view=timeline)：返回 dict 含 rendered text。"""
    from claude_autosar.cli.mcp_server import log_export

    monkeypatch.setattr("claude_autosar.cli.mcp_server._default_session_dir", lambda: tmp_path)
    store = _build_store(tmp_path)
    _append_user_entry(store, "s1", "go")
    _append_tool_entry(
        store,
        "s1",
        tool_name="bsw_write",
        tool_args={"module": "Mcu", "path": "Clock/ClockFreq", "value": "80000000"},
    )

    result = log_export("s1", view="timeline")
    assert result["success"] is True
    assert "Mcu" in result["text"] or "ClockFreq" in result["text"]


def test_log_export_by_url_produces_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from claude_autosar.cli.mcp_server import log_export

    monkeypatch.setattr("claude_autosar.cli.mcp_server._default_session_dir", lambda: tmp_path)
    store = _build_store(tmp_path)
    _append_user_entry(store, "s1", "go")
    _append_tool_entry(
        store,
        "s1",
        tool_name="bsw_write",
        tool_args={"module": "Mcu", "path": "Clock/ClockFreq", "value": "80000000"},
    )

    result = log_export("s1", view="by-url")
    assert result["success"] is True
    assert isinstance(result["text"], str)
    assert len(result["text"]) > 0


# ---------------------------------------------------------------------------
# arxml_validate
# ---------------------------------------------------------------------------


def test_arxml_validate_happy_path(tmp_path: Path) -> None:
    """arxml_validate happy：返回 success=True + root tag + 元素数。"""
    from claude_autosar.cli.mcp_server import arxml_validate

    arxml = tmp_path / "ok.arxml"
    arxml.write_text(
        '<?xml version="1.0"?><root><a/></root>',
        encoding="utf-8",
    )
    result = arxml_validate(str(arxml))
    assert result["success"] is True
    assert result["path"] == str(arxml)
    assert "root_tag" in result
    assert "element_count" in result


def test_arxml_validate_broken_xml(tmp_path: Path) -> None:
    """arxml_validate broken：返回 success=False + error。"""
    from claude_autosar.cli.mcp_server import arxml_validate

    bad = tmp_path / "bad.arxml"
    bad.write_text("<<not xml>>", encoding="utf-8")
    result = arxml_validate(str(bad))
    assert result["success"] is False


# ---------------------------------------------------------------------------
# helpers (test-only)
# ---------------------------------------------------------------------------


def _build_store(tmp_path: Path):
    """构造一个指向 tmp_path 的 SessionStore。"""
    from claude_autosar.core.session.store import SessionStore

    return SessionStore(dir=tmp_path)


def _append_user_entry(store, session_id: str, content: str) -> None:
    from claude_autosar.core.session.store import SessionEntry

    e = SessionEntry(
        id="e1",
        parent_id=None,
        session_id=session_id,
        timestamp="2026-01-01T00:00:00+00:00",
        kind="user",
        content=content,
    )
    store.append(e)


def _append_tool_entry(
    store,
    session_id: str,
    *,
    tool_name: str,
    tool_args: dict | None = None,
    tool_result: str | None = None,
) -> None:
    from claude_autosar.core.session.store import SessionEntry

    e = SessionEntry(
        id="e2",
        parent_id="e1",
        session_id=session_id,
        timestamp="2026-01-01T00:00:01+00:00",
        kind="tool",
        content="",
        tool_name=tool_name,
        tool_args=tool_args or {},
        tool_result=tool_result,
    )
    store.append(e)
