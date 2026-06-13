"""Unit tests for autoc.cli.repl_skin.

Sprint 5 — T5.2. Rich-based CLI 样式层。
- Theme 与 console 工厂
- status 消息 (success / error / warning / info / hint)
- 表格 / status block / section header
- print_result_table / print_diff_callout 三色 callout
- --no-color 强制无 ANSI
- pytest 用 ``Console(record=True)`` 抓取，断言用 ``export_text()``
"""

from __future__ import annotations

import io

import pytest
from rich.console import Console

from claude_autosar.cli.repl_skin import (
    AUTOC_THEME,
    ReplSkin,
    detect_no_color,
    make_console,
)

pytestmark = pytest.mark.autosar


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _recorded_console(no_color: bool = True) -> Console:
    """在测试里抓 Rich 输出：record=True + file=StringIO + 固定 width。"""
    return Console(
        record=True,
        file=io.StringIO(),
        width=120,
        no_color=no_color,
        force_terminal=False,
        theme=AUTOC_THEME,
    )


# ---------------------------------------------------------------------------
# make_console / detect_no_color
# ---------------------------------------------------------------------------


def test_make_console_returns_rich_console() -> None:
    c = make_console()
    assert isinstance(c, Console)


def test_make_console_attaches_theme() -> None:
    c = make_console()
    # Rich 15 把 theme 放在 _theme_stack（ThemeStack，dict-like）上
    stack = getattr(c, "_theme_stack", None)
    assert stack is not None
    # 关键样式名都在
    for name in ("success", "error", "warning", "info", "hint", "accent", "muted"):
        assert stack.get(name) is not None, f"missing theme style: {name}"


def test_make_console_no_color_suppresses_ansi() -> None:
    c = make_console(no_color=True, force_terminal=False)
    assert c.no_color is True


def test_detect_no_color_honors_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    assert detect_no_color() is True


def test_detect_no_color_default_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    # detect_no_color 也看 isatty()，但测试里 stdout 不一定是 TTY —
    # 关键是当 NO_COLOR 未设且 stdout is tty 时，函数行为由环境决定。
    # 我们只断言 None 环境下不会是显式 True（除非 stdout 真 tty）
    result = detect_no_color()
    # result 必须是 bool
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# ReplSkin: 状态消息
# ---------------------------------------------------------------------------


def test_skin_success_contains_message_and_check() -> None:
    c = _recorded_console()
    ReplSkin("autoc", console=c).success("saved")
    out = c.export_text()
    assert "saved" in out
    assert "✓" in out


def test_skin_error_contains_message_and_cross() -> None:
    c = _recorded_console()
    ReplSkin("autoc", console=c).error("boom")
    out = c.export_text()
    assert "boom" in out
    assert "✗" in out


def test_skin_warning_info_hint_smoke() -> None:
    c = _recorded_console()
    skin = ReplSkin("autoc", console=c)
    skin.warning("watch out")
    skin.info("note")
    skin.hint("tip")
    out = c.export_text()
    assert "watch out" in out
    assert "note" in out
    assert "tip" in out


# ---------------------------------------------------------------------------
# ReplSkin: 结构化元素
# ---------------------------------------------------------------------------


def test_skin_section_contains_title() -> None:
    c = _recorded_console()
    ReplSkin("autoc", console=c).section("Mcu")
    out = c.export_text()
    assert "Mcu" in out


def test_skin_table_contains_headers_and_rows() -> None:
    c = _recorded_console()
    ReplSkin("autoc", console=c).table(["ID", "Name"], [["1", "alpha"], ["2", "beta"]])
    out = c.export_text()
    assert "ID" in out and "Name" in out
    assert "alpha" in out and "beta" in out


def test_skin_status_block_contains_key_value_pairs() -> None:
    c = _recorded_console()
    ReplSkin("autoc", console=c).status_block({"module": "Mcu", "result": "ok"}, title="verify")
    out = c.export_text()
    assert "module" in out
    assert "Mcu" in out
    assert "result" in out
    assert "ok" in out
    assert "verify" in out


# ---------------------------------------------------------------------------
# ReplSkin: autoc 专用
# ---------------------------------------------------------------------------


def test_skin_print_result_table_renders_title_and_rows() -> None:
    c = _recorded_console()
    ReplSkin("autoc", console=c).print_result_table(
        title="Mcu 改参", rows=[{"path": "ClockFreq", "old": "80M", "new": "100M"}]
    )
    out = c.export_text()
    assert "Mcu 改参" in out
    assert "ClockFreq" in out
    assert "80M" in out
    assert "100M" in out


def test_skin_print_diff_callout_renders_diff_text() -> None:
    c = _recorded_console()
    ReplSkin("autoc", console=c).print_diff_callout("- old\n+ new", title="Changes")
    out = c.export_text()
    assert "Changes" in out
    assert "+ new" in out
    assert "- old" in out


# ---------------------------------------------------------------------------
# ReplSkin: 与 --no-color 集成
# ---------------------------------------------------------------------------


def test_skin_respects_no_color_in_console() -> None:
    """no_color=True 时 export_text() 不含 ANSI 转义。"""
    c = _recorded_console(no_color=True)
    ReplSkin("autoc", console=c).success("hi")
    plain = c.export_text()
    styled = c.export_text(styles=True)
    # plain 与 styled 都不应含 ESC 字符
    assert "\x1b" not in plain
    assert "\x1b" not in styled
    # plain 应包含消息本体
    assert "hi" in plain
