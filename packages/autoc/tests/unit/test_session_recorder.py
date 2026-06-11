"""Sprint 4 集成 — session recorder 单元测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from autoc.core.bsw.config import BSWParam, ParamType, ParamValue
from autoc.core.session.recorder import (
    get_current_session_path,
    get_or_create_current_session,
    record_bsw_write_batch,
    set_current_session,
)
from autoc.core.session.store import SessionStore, new_session_id


def _patch_session_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    cfg_dir = tmp_path / "fake_agent"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "autoc.utils.paths.user_config_dir",
        lambda *a, **kw: str(cfg_dir),
    )
    return cfg_dir / "sessions"


def _param(path: str, value: str) -> BSWParam:
    return BSWParam(path, ParamValue(value, ParamType.INTEGER))


# ---------------------------------------------------------------------------
# get_or_create_current_session
# ---------------------------------------------------------------------------


def test_get_or_create_creates_and_persists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """第一次调用创建新 session id 并写 .current 文件。"""
    _patch_session_dir(monkeypatch, tmp_path)
    store = SessionStore()
    sid = get_or_create_current_session(store)
    assert len(sid) == 32
    assert get_current_session_path(store).read_text(encoding="utf-8").strip() == sid


def test_get_or_create_reuses_existing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """第二次调用复用 .current 中的 session id。"""
    _patch_session_dir(monkeypatch, tmp_path)
    store = SessionStore()
    sid1 = get_or_create_current_session(store)
    sid2 = get_or_create_current_session(store)
    assert sid1 == sid2


def test_set_current_session_switches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """set_current_session 后 get_or_create 返回新值。"""
    _patch_session_dir(monkeypatch, tmp_path)
    store = SessionStore()
    sid1 = get_or_create_current_session(store)
    new_sid = new_session_id()
    set_current_session(store, new_sid)
    assert get_or_create_current_session(store) == new_sid
    assert get_or_create_current_session(store) != sid1


# ---------------------------------------------------------------------------
# record_bsw_write_batch
# ---------------------------------------------------------------------------


def test_record_writes_user_and_tool_entries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """成功路径写 1 user + N tool entry 到 current session。"""
    _patch_session_dir(monkeypatch, tmp_path)
    store = SessionStore()
    result = record_bsw_write_batch(
        store,
        module="Mcu",
        params=[
            _param("Mcu/ClockFreq", "80000000"),
            _param("Mcu/ClockDivider", "2"),
        ],
        success=True,
    )
    assert result is not None
    assert len(result.tool_entry_ids) == 2

    session = store.read(result.session_id)
    kinds = [e.kind for e in session.entries]
    assert kinds == ["user", "tool", "tool"]

    user = session.entries[0]
    assert user.parent_id is None  # 首次
    assert "Mcu" in user.content
    assert "2" in user.content  # 2 项

    tool1 = session.entries[1]
    assert tool1.tool_name == "bsw_write"
    assert tool1.parent_id == user.id
    assert tool1.tool_args["module"] == "Mcu"
    assert tool1.tool_args["path"] == "ClockFreq"  # 去掉 module 前缀
    assert tool1.tool_args["op"] == "modify"
    assert tool1.tool_args["value"] == "80000000"


def test_record_failure_returns_none(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """success=False 不写入。"""
    _patch_session_dir(monkeypatch, tmp_path)
    store = SessionStore()
    result = record_bsw_write_batch(
        store,
        module="Mcu",
        params=[_param("Mcu/ClockFreq", "80")],
        success=False,
    )
    assert result is None
    # session 列表应为空
    assert store.list_session_ids() == []


def test_record_empty_params_returns_none(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """空 params 列表 → 不写入。"""
    _patch_session_dir(monkeypatch, tmp_path)
    store = SessionStore()
    result = record_bsw_write_batch(
        store,
        module="Mcu",
        params=[],
        success=True,
    )
    assert result is None
    assert store.list_session_ids() == []


def test_record_chains_parent_id_across_calls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """多次 record 共用 current session，第二次的 user 父指向第一次的 tool。"""
    _patch_session_dir(monkeypatch, tmp_path)
    store = SessionStore()

    r1 = record_bsw_write_batch(
        store,
        module="Mcu",
        params=[_param("Mcu/ClockFreq", "80")],
        success=True,
    )
    r2 = record_bsw_write_batch(
        store,
        module="Port",
        params=[_param("Port/Pin1", "5")],
        success=True,
    )
    assert r1 is not None and r2 is not None
    assert r1.session_id == r2.session_id

    session = store.read(r1.session_id)
    # 顺序：u1, t1, u2, t2
    assert [e.kind for e in session.entries] == ["user", "tool", "user", "tool"]
    # u2.parent_id = t1.id
    assert session.entries[2].parent_id == session.entries[1].id


def test_record_strips_module_prefix(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """tool_args['path'] 必须去掉 module 前缀。"""
    _patch_session_dir(monkeypatch, tmp_path)
    store = SessionStore()
    r = record_bsw_write_batch(
        store,
        module="Mcu",
        params=[_param("Mcu/Clock/ClockFreq", "80")],
        success=True,
    )
    assert r is not None
    session = store.read(r.session_id)
    tool = session.entries[1]
    assert tool.tool_args["path"] == "Clock/ClockFreq"
