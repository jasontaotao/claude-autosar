"""T4.2 — session tree 单元测试。"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from autoc.core.session.store import Session, SessionEntry
from autoc.core.session.tree import SessionTree


def _entry(
    eid: str,
    *,
    parent: str | None = None,
    session: str = "s1",
    kind: str = "user",
    content: str = "",
) -> SessionEntry:
    return SessionEntry(
        id=eid,
        parent_id=parent,
        session_id=session,
        timestamp="2026-06-11T00:00:00.000Z",
        kind=kind,
        content=content or eid,
    )


def _build_tree(entries: list[SessionEntry]) -> SessionTree:
    """用 entry list 构造 session tree（按 entries 顺序）。"""
    return SessionTree(
        session=Session(
            id="s1",
            started_at=entries[0].timestamp if entries else "",
            entries=tuple(entries),
        )
    )


# ---------------------------------------------------------------------------
# root / children / find
# ---------------------------------------------------------------------------


def test_root_returns_entry_with_no_parent() -> None:
    """root() 返回 parent_id=None 的 entry。"""
    root = _entry("r0", parent=None)
    child = _entry("c1", parent="r0")
    tree = _build_tree([root, child])

    assert tree.root().id == "r0"


def test_root_on_empty_tree_raises() -> None:
    """空 tree 调 root() 抛 ValueError。"""
    tree = SessionTree(session=Session(id="s1", started_at=""))
    with pytest.raises(ValueError):
        tree.root()


def test_children_returns_direct_children() -> None:
    """children(parent) 返回 parent_id 指向该 parent 的所有 entry。"""
    r = _entry("r")
    a = _entry("a", parent="r")
    b = _entry("b", parent="r")
    c = _entry("c", parent="a")  # 孙子
    tree = _build_tree([r, a, b, c])

    kids = tree.children("r")
    assert sorted(e.id for e in kids) == ["a", "b"]
    assert tree.children("a") == [c]
    assert tree.children("c") == []  # 叶子


def test_find_returns_entry_or_none() -> None:
    r = _entry("r")
    a = _entry("a", parent="r")
    tree = _build_tree([r, a])
    assert tree.find("a") is not None
    assert tree.find("a").id == "a"  # type: ignore[union-attr]
    assert tree.find("nonexistent") is None


# ---------------------------------------------------------------------------
# walk DFS
# ---------------------------------------------------------------------------


def test_walk_yields_entries_in_dfs_pre_order() -> None:
    """walk() 按 DFS pre-order 遍历（root → child → grandchild）。"""
    r = _entry("r")
    a = _entry("a", parent="r")
    a1 = _entry("a1", parent="a")
    b = _entry("b", parent="r")
    tree = _build_tree([r, a, a1, b])

    order = [e.id for e in tree.walk()]
    # r 优先；a 在 a1 之前（pre-order）；b 在最后
    assert order[0] == "r"
    assert order[-1] == "b"
    # a 必须在 a1 之前
    assert order.index("a") < order.index("a1")


def test_walk_returns_iterator() -> None:
    """walk() 返回 Iterator（不是 list——支持 lazy）。"""
    tree = _build_tree([_entry("r")])
    it = tree.walk()
    assert isinstance(it, Iterator)


# ---------------------------------------------------------------------------
# 不可变 + with_X
# ---------------------------------------------------------------------------


def test_with_entry_returns_new_tree_with_entry_appended() -> None:
    """with_entry 返回新 tree，session.entries 末尾追加。"""
    tree = _build_tree([_entry("r")])
    new_entry = _entry("a", parent="r")
    new_tree = tree.with_entry(new_entry)

    assert new_tree is not tree
    assert len(new_tree.session.entries) == 2
    assert new_tree.session.entries[-1].id == "a"
    # 原 tree 不变
    assert len(tree.session.entries) == 1


def test_with_entry_on_tree_with_different_session_id_raises() -> None:
    """with_entry 拒绝跨 session 注入（防御）。"""
    tree = _build_tree([_entry("r", session="s1")])
    bad = _entry("a", parent="r", session="s2")
    with pytest.raises(ValueError):
        tree.with_entry(bad)


def test_with_session_meta_replaces_title() -> None:
    """with_session_meta 返回新 tree，title 覆盖。"""
    tree = _build_tree([_entry("r")])
    new_tree = tree.with_session_meta("帮我配置 Mcu")
    assert new_tree.session.title == "帮我配置 Mcu"
    # 原 tree 不变
    assert tree.session.title == ""


# ---------------------------------------------------------------------------
# fork
# ---------------------------------------------------------------------------


def test_fork_creates_new_session_with_parent_reference() -> None:
    """fork(parent_id, new_sid) 返回 SessionTree，session 切换为 new_sid，
    含 1 条 root entry（parent_id=原 parent_id）。"""
    r = _entry("r")
    a = _entry("a", parent="r")
    tree = _build_tree([r, a])

    forked = tree.fork(parent_entry_id="a", new_session_id="s2")
    assert forked.session.id == "s2"
    assert len(forked.session.entries) == 1
    fork_root = forked.root()
    assert fork_root.session_id == "s2"
    assert fork_root.parent_id == "a"  # 指向原 session 的 entry
    assert fork_root.kind in ("user", "tool", "assistant", "tool_result")


def test_fork_preserves_original_tree() -> None:
    """fork 不可变：原 tree 不被修改。"""
    tree = _build_tree([_entry("r")])
    _ = tree.fork(parent_entry_id="r", new_session_id="s2")
    assert len(tree.session.entries) == 1


def test_fork_unknown_parent_raises() -> None:
    """fork 时 parent_entry_id 在原 tree 里找不到则抛 ValueError。"""
    tree = _build_tree([_entry("r")])
    with pytest.raises(ValueError):
        tree.fork(parent_entry_id="nonexistent", new_session_id="s2")


# ---------------------------------------------------------------------------
# 构造便利
# ---------------------------------------------------------------------------


def test_tree_from_session_id_uses_store(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """SessionTree.from_session_id(sid, store=...) 用 store.read 构造。"""
    from autoc.core.session.store import SessionEntry, SessionStore
    from autoc.core.session.tree import SessionTree

    cfg_dir = tmp_path / "fake_agent"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "autoc.utils.paths.user_config_dir",
        lambda *a, **kw: str(cfg_dir),
    )
    store = SessionStore()
    sid = "abcdef0123456789abcdef0123456789"
    store.append(
        SessionEntry(
            id="e1",
            parent_id=None,
            session_id=sid,
            timestamp="2026-06-11T00:00:00.000Z",
            kind="user",
            content="hi",
        )
    )
    tree = SessionTree.from_session_id(sid, store=store)
    assert tree.session.id == sid
    assert tree.root().id == "e1"
