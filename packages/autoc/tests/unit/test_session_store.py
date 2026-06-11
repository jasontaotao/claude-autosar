"""T4.1 — session store 单元测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from autoc.core.session.store import (
    SessionEntry,
    SessionStore,
    SessionStoreError,
    new_session_id,
)

# ---------------------------------------------------------------------------
# SessionEntry 不可变 + round-trip
# ---------------------------------------------------------------------------


def test_session_entry_is_frozen() -> None:
    """SessionEntry 必须是 frozen dataclass（沿用 Sprint 1–3 不可变约定）。"""
    entry = SessionEntry(
        id="abc",
        parent_id=None,
        session_id="s1",
        timestamp="2026-06-11T00:00:00.000Z",
        kind="user",
        content="hello",
    )
    with pytest.raises((AttributeError, Exception)):  # FrozenInstanceError subclass
        entry.content = "world"  # type: ignore[misc]


def test_session_entry_to_dict_and_back() -> None:
    """to_dict / from_dict round-trip 保持字段一致。"""
    original = SessionEntry(
        id="e1",
        parent_id="e0",
        session_id="s1",
        timestamp="2026-06-11T00:00:00.000Z",
        kind="tool",
        content="bsw_write",
        tool_name="bsw_write",
        tool_args={"path": "Mcu/ClockFreq", "value": 80000000},
        tool_result="ok",
    )
    d = original.to_dict()
    restored = SessionEntry.from_dict(d)
    assert restored == original


# ---------------------------------------------------------------------------
# SessionStore 基本读写
# ---------------------------------------------------------------------------


def _patch_session_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """把 platformdirs 指向 tmp_path 下的虚拟 config dir，让 global_session_dir() 用它。"""
    cfg_dir = tmp_path / "fake_agent"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "autoc.utils.paths.user_config_dir",
        lambda *a, **kw: str(cfg_dir),
    )
    return cfg_dir / "sessions"


def test_session_store_append_creates_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """append 第一次写时自动创建文件 + 父目录。"""
    sessions_dir = _patch_session_dir(monkeypatch, tmp_path)
    store = SessionStore(sessions_dir)
    sid = new_session_id()
    entry = SessionEntry(
        id="e1",
        parent_id=None,
        session_id=sid,
        timestamp="2026-06-11T00:00:00.000Z",
        kind="user",
        content="hi",
    )
    store.append(entry)

    target = sessions_dir / f"{sid}.jsonl"
    assert target.is_file(), f"expected file at {target}"
    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    import json

    parsed = json.loads(lines[0])
    assert parsed["id"] == "e1"
    assert parsed["kind"] == "user"
    assert parsed["session_id"] == sid


def test_session_store_read_round_trip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """append + read 完整 round-trip：写两条，读两条，顺序与内容一致。"""
    _patch_session_dir(monkeypatch, tmp_path)
    store = SessionStore()
    sid = new_session_id()

    e1 = SessionEntry(
        id="e1",
        parent_id=None,
        session_id=sid,
        timestamp="2026-06-11T00:00:00.000Z",
        kind="user",
        content="first",
    )
    e2 = SessionEntry(
        id="e2",
        parent_id="e1",
        session_id=sid,
        timestamp="2026-06-11T00:00:01.000Z",
        kind="assistant",
        content="ack",
    )
    store.append(e1)
    store.append(e2)

    session = store.read(sid)
    assert session.id == sid
    assert [e.id for e in session.entries] == ["e1", "e2"]
    assert session.entries[0].content == "first"
    assert session.entries[1].parent_id == "e1"


def test_session_store_read_missing_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """读不存在的 session id 应抛 SessionStoreError（明确失败）。"""
    _patch_session_dir(monkeypatch, tmp_path)
    store = SessionStore()
    with pytest.raises(SessionStoreError):
        store.read("nonexistent-session-id")


def test_session_store_tail_returns_last_n(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """tail(n) 返回最后 n 条 entry。"""
    _patch_session_dir(monkeypatch, tmp_path)
    store = SessionStore()
    sid = new_session_id()
    for i in range(5):
        store.append(
            SessionEntry(
                id=f"e{i}",
                parent_id=None,
                session_id=sid,
                timestamp=f"2026-06-11T00:00:0{i}.000Z",
                kind="user",
                content=f"msg-{i}",
            )
        )
    last3 = store.tail(sid, n=3)
    assert [e.id for e in last3] == ["e2", "e3", "e4"]


def test_session_store_utf8_chinese_content(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """中文 content 必须原样持久（ensure_ascii=False 验证）。"""
    _patch_session_dir(monkeypatch, tmp_path)
    store = SessionStore()
    sid = new_session_id()
    e = SessionEntry(
        id="e1",
        parent_id=None,
        session_id=sid,
        timestamp="2026-06-11T00:00:00.000Z",
        kind="user",
        content="帮我把 Mcu 时钟改成 80 MHz",
    )
    store.append(e)
    # 直接读 raw 文本，中文必须可读
    raw = (store.dir / f"{sid}.jsonl").read_text(encoding="utf-8")
    assert "帮我把" in raw
    assert "Mcu 时钟" in raw
    # 读回 round-trip
    restored = store.read(sid).entries[0]
    assert restored.content == "帮我把 Mcu 时钟改成 80 MHz"


def test_session_store_multi_entry_preserves_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """顺序敏感：append 必须按调用顺序写到文件。"""
    _patch_session_dir(monkeypatch, tmp_path)
    store = SessionStore()
    sid = new_session_id()
    for i in range(10):
        store.append(
            SessionEntry(
                id=f"e{i}",
                parent_id=None,
                session_id=sid,
                timestamp=f"2026-06-11T00:00:{i:02d}.000Z",
                kind="user",
                content=str(i),
            )
        )
    entries = store.read(sid).entries
    assert [e.content for e in entries] == [str(i) for i in range(10)]


def test_session_store_dir_uses_global_session_dir_when_unspecified(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """不传 dir 参数时，SessionStore 必须用 global_session_dir() 解析路径。"""
    _patch_session_dir(monkeypatch, tmp_path)
    store = SessionStore()
    assert store.dir == Path(tmp_path / "fake_agent" / "sessions")


def test_new_session_id_is_unique_hex() -> None:
    """new_session_id 必须返回 32 字符 hex（UUID4 hex no dash）。"""
    a = new_session_id()
    b = new_session_id()
    assert a != b
    assert len(a) == 32
    assert all(c in "0123456789abcdef" for c in a)


# ---------------------------------------------------------------------------
# 路径 / dir 解析
# ---------------------------------------------------------------------------


def test_list_session_ids_finds_existing_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """list_session_ids 枚举所有 <id>.jsonl 文件。"""
    _patch_session_dir(monkeypatch, tmp_path)
    store = SessionStore()
    s1 = new_session_id()
    s2 = new_session_id()
    store.append(
        SessionEntry(
            id="x",
            parent_id=None,
            session_id=s1,
            timestamp="2026-06-11T00:00:00.000Z",
            kind="user",
            content="a",
        )
    )
    store.append(
        SessionEntry(
            id="x",
            parent_id=None,
            session_id=s2,
            timestamp="2026-06-11T00:00:00.000Z",
            kind="user",
            content="b",
        )
    )
    ids = store.list_session_ids()
    assert s1 in ids
    assert s2 in ids
