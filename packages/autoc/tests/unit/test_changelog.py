"""T4.4 — changelog 单元测试。"""

from __future__ import annotations

from autoc.core.log.changelog import (
    Change,
    extract_changes,
    render_by_url,
    render_timeline,
)
from autoc.core.session.store import Session, SessionEntry
from autoc.core.session.tree import SessionTree


def _tool_entry(
    eid: str,
    *,
    parent: str | None,
    session: str,
    tool_name: str,
    tool_args: dict | None,
    timestamp: str,
) -> SessionEntry:
    return SessionEntry(
        id=eid,
        parent_id=parent,
        session_id=session,
        timestamp=timestamp,
        kind="tool",
        content=tool_name,
        tool_name=tool_name,
        tool_args=tool_args,
        tool_result="ok",
    )


def _user_entry(eid: str, *, parent: str | None, session: str, content: str) -> SessionEntry:
    return SessionEntry(
        id=eid,
        parent_id=parent,
        session_id=session,
        timestamp="2026-06-11T00:00:00.000Z",
        kind="user",
        content=content,
    )


# ---------------------------------------------------------------------------
# extract_changes
# ---------------------------------------------------------------------------


def test_extract_changes_skips_non_bsw_write() -> None:
    """非 bsw_write 的 tool entry 也要被跳过；user/assistant 一律跳过。"""
    entries = [
        _user_entry("u1", parent=None, session="s1", content="帮我配置 Mcu"),
        _tool_entry(
            "t1",
            parent="u1",
            session="s1",
            tool_name="list_modules",
            tool_args=None,
            timestamp="2026-06-11T00:00:01.000Z",
        ),
        _tool_entry(
            "t2",
            parent="u1",
            session="s1",
            tool_name="read_param",
            tool_args=None,
            timestamp="2026-06-11T00:00:02.000Z",
        ),
    ]
    tree = SessionTree(session=Session(id="s1", started_at="", entries=tuple(entries)))
    assert extract_changes(tree) == []


def test_extract_changes_picks_bsw_write_with_all_fields() -> None:
    """bsw_write entry 完整解析为 Change。"""
    entries = [
        _tool_entry(
            "t1",
            parent=None,
            session="s1",
            tool_name="bsw_write",
            tool_args={
                "module": "Mcu",
                "path": "Clock/ClockFreq",
                "value": 80000000,
                "old_value": 40000000,
                "op": "modify",
            },
            timestamp="2026-06-11T00:00:01.000Z",
        ),
    ]
    tree = SessionTree(session=Session(id="s1", started_at="", entries=tuple(entries)))
    changes = extract_changes(tree)
    assert len(changes) == 1
    c = changes[0]
    assert isinstance(c, Change)
    assert c.module == "Mcu"
    assert c.path == "Clock/ClockFreq"
    assert c.kind == "modify"
    assert c.new_value == 80000000
    assert c.old_value == 40000000
    assert c.entry_id == "t1"


def test_extract_changes_on_empty_tree_returns_empty() -> None:
    """空 tree → 空 list（不抛）。"""
    tree = SessionTree(session=Session(id="s1", started_at=""))
    assert extract_changes(tree) == []


def test_extract_changes_preserves_session_order() -> None:
    """多 bsw_write 按 session.entries 顺序返回（调用方自行排序）。"""
    entries = [
        _tool_entry(
            "t1",
            parent=None,
            session="s1",
            tool_name="bsw_write",
            tool_args={"module": "Mcu", "path": "A", "value": 1, "op": "modify"},
            timestamp="2026-06-11T00:00:01.000Z",
        ),
        _tool_entry(
            "t2",
            parent="t1",
            session="s1",
            tool_name="bsw_write",
            tool_args={"module": "Port", "path": "B", "value": 2, "op": "add"},
            timestamp="2026-06-11T00:00:02.000Z",
        ),
    ]
    tree = SessionTree(session=Session(id="s1", started_at="", entries=tuple(entries)))
    changes = extract_changes(tree)
    assert [c.path for c in changes] == ["A", "B"]


# ---------------------------------------------------------------------------
# render_timeline
# ---------------------------------------------------------------------------


def test_render_timeline_orders_by_timestamp_desc() -> None:
    """timeline 视图：最新改参排在最上。"""
    changes = [
        Change(
            timestamp="2026-06-11T00:00:01.000Z",
            module="Mcu",
            path="A",
            kind="modify",
            old_value=1,
            new_value=2,
            session_id="s1",
            entry_id="e1",
        ),
        Change(
            timestamp="2026-06-11T00:00:05.000Z",
            module="Port",
            path="B",
            kind="add",
            old_value=None,
            new_value=42,
            session_id="s1",
            entry_id="e2",
        ),
        Change(
            timestamp="2026-06-11T00:00:03.000Z",
            module="Can",
            path="C",
            kind="delete",
            old_value=99,
            new_value=None,
            session_id="s1",
            entry_id="e3",
        ),
    ]
    out = render_timeline(changes)
    # Port 改参（最新）应出现在 Mcu 之前
    assert out.index("Port/B") < out.index("Mcu/A")
    assert out.index("Can/C") < out.index("Mcu/A")


def test_render_timeline_marks_three_kinds() -> None:
    """timeline 文本中能区分 add/modify/delete。"""
    changes = [
        Change(
            timestamp="2026-06-11T00:00:01.000Z",
            module="Mcu",
            path="A",
            kind="modify",
            old_value=1,
            new_value=2,
            session_id="s1",
            entry_id="e1",
        ),
        Change(
            timestamp="2026-06-11T00:00:02.000Z",
            module="Mcu",
            path="B",
            kind="add",
            old_value=None,
            new_value=42,
            session_id="s1",
            entry_id="e2",
        ),
        Change(
            timestamp="2026-06-11T00:00:03.000Z",
            module="Mcu",
            path="C",
            kind="delete",
            old_value=99,
            new_value=None,
            session_id="s1",
            entry_id="e3",
        ),
    ]
    out = render_timeline(changes)
    # 三种 op 都要可见
    assert "ADD" in out
    assert "MOD" in out
    assert "DEL" in out


def test_render_timeline_empty() -> None:
    """空 changes 返回非空文本（带 header 引导）。"""
    out = render_timeline([])
    assert "改参" in out or "Timeline" in out
    assert "暂无" in out or "无" in out or "empty" in out.lower() or len(out.splitlines()) <= 3


# ---------------------------------------------------------------------------
# render_by_url
# ---------------------------------------------------------------------------


def test_render_by_url_groups_by_module_path() -> None:
    """by_url 视图：相同 (module, path) 的 Change 聚在一起。"""
    changes = [
        Change(
            timestamp="2026-06-11T00:00:01.000Z",
            module="Mcu",
            path="A",
            kind="modify",
            old_value=1,
            new_value=2,
            session_id="s1",
            entry_id="e1",
        ),
        Change(
            timestamp="2026-06-11T00:00:02.000Z",
            module="Mcu",
            path="A",
            kind="modify",
            old_value=2,
            new_value=3,
            session_id="s1",
            entry_id="e2",
        ),
        Change(
            timestamp="2026-06-11T00:00:03.000Z",
            module="Port",
            path="B",
            kind="add",
            old_value=None,
            new_value=42,
            session_id="s1",
            entry_id="e3",
        ),
    ]
    out = render_by_url(changes)
    # Mcu/A 段应包含两条 change
    lines = out.splitlines()
    mcu_a_section = []
    in_section = False
    for line in lines:
        if line.startswith("## "):
            in_section = "Mcu/A" in line
        elif in_section and line.strip():
            mcu_a_section.append(line)
    assert len(mcu_a_section) >= 2


def test_render_by_url_orders_groups_alphabetically() -> None:
    """by_url 视图：不同 URL 之间按字母序排列。"""
    changes = [
        Change(
            timestamp="2026-06-11T00:00:01.000Z",
            module="Zzz",
            path="Z",
            kind="modify",
            old_value=1,
            new_value=2,
            session_id="s1",
            entry_id="e1",
        ),
        Change(
            timestamp="2026-06-11T00:00:01.000Z",
            module="Aaa",
            path="A",
            kind="modify",
            old_value=1,
            new_value=2,
            session_id="s1",
            entry_id="e2",
        ),
    ]
    out = render_by_url(changes)
    assert out.index("Aaa/A") < out.index("Zzz/Z")


def test_render_by_url_empty() -> None:
    """空 changes → 不抛。"""
    out = render_by_url([])
    assert isinstance(out, str)
