"""Sprint 4 集成 helper — 把 bsw_write 批改参记录到 current session。

设计要点：
- "current" session 由 ``~/.autoc/agent/sessions/.current`` 标记；不存在则新建
- 一次 ``eb save`` 写 1 user entry + N tool entries（每个 param 一条）
- parent_id 指向 session 最后一条 entry（保持树连续）
- 失败路径不写入（避免污染 timeline）
- 进程内并发安全：``threading.Lock`` 保护 ``.current`` 读写 + 整个 batch 写入
- 跨进程并发不保证安全（Sprint 4 范围外）
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from pathlib import Path
import threading
import uuid

from claude_autosar.core.bsw.config import BSWParam
from claude_autosar.core.session.store import (
    SessionEntry,
    SessionStore,
    SessionStoreError,
    new_session_id,
)

_CURRENT_FILE = ".current"
_LOG = logging.getLogger(__name__)

# 进程内全局锁：保护 ``.current`` 读/写 + batch 写入
# 跨进程并发（Sprint 4 范围外）不保证原子性
_RECORDER_LOCK = threading.Lock()


def _now_iso8601_utc() -> str:
    """返回当前 UTC 时间的 ISO 8601 字符串（毫秒精度 + ``Z`` 后缀）。"""
    now = datetime.now(UTC)
    return now.strftime("%Y-%m-%dT%H:%M:%S") + f".{now.microsecond // 1000:03d}Z"


def get_or_create_current_session(store: SessionStore) -> str:
    """返回 current session id；不存在则新建并写 ``.current`` 标记。

    线程安全：调用方需持有 ``_RECORDER_LOCK``，或单线程场景下也可直接调。
    """
    current_file = store.dir / _CURRENT_FILE
    if current_file.is_file():
        sid = current_file.read_text(encoding="utf-8").strip()
        if sid:
            return sid
    sid = new_session_id()
    current_file.write_text(sid, encoding="utf-8")
    return sid


def set_current_session(store: SessionStore, session_id: str) -> None:
    """显式设置 current session（用于 fork 后切换）。"""
    with _RECORDER_LOCK:
        current_file = store.dir / _CURRENT_FILE
        current_file.write_text(session_id, encoding="utf-8")


@dataclass(frozen=True)
class RecordResult:
    """record_bsw_write_batch 的返回：成功写入的 session id + entry 数。"""

    session_id: str
    user_entry_id: str
    tool_entry_ids: tuple[str, ...]


def record_bsw_write_batch(
    store: SessionStore,
    *,
    module: str,
    params: Iterable[BSWParam],
    success: bool,
) -> RecordResult | None:
    """记录一次 bsw_write 批改参到 current session。

    - ``success=False``：直接返回 None（不写入）
    - 1 user entry + N tool entry（每个 param 一条）
    - 复用 current session（通过 ``.current`` 标记）；parent 指向 session 末尾
    - 线程安全：整个 batch 在 ``_RECORDER_LOCK`` 内执行
    """
    if not success:
        return None
    params_list = list(params)
    if not params_list:
        return None

    with _RECORDER_LOCK:
        sid = get_or_create_current_session(store)
        # 找 parent：当前 session 最后一条 entry
        try:
            existing = store.read(sid)
            last_entry = existing.entries[-1] if existing.entries else None
        except SessionStoreError as e:
            # "session not found" = 首次写入（get_or_create 刚建的新 session）
            # 这种情况 parent 退化为 None 是正确行为，不算错
            if "not found" not in str(e):
                _LOG.warning("recorder: read current session failed: %s", e)
            last_entry = None
        except (OSError, ValueError) as e:
            # 损坏 JSONL / 权限错误 → 记日志但继续
            _LOG.warning("recorder: read current session failed: %s", e)
            last_entry = None
        parent_id = last_entry.id if last_entry else None
        now = _now_iso8601_utc()

        user_entry = SessionEntry(
            id=uuid.uuid4().hex,
            parent_id=parent_id,
            session_id=sid,
            timestamp=now,
            kind="user",
            content=f"批改参 {module}: {len(params_list)} 项",
        )
        store.append(user_entry)

        tool_ids: list[str] = []
        for p in params_list:
            rel_path = _strip_module_prefix(p.path, module)
            tool_entry = SessionEntry(
                id=uuid.uuid4().hex,
                parent_id=user_entry.id,
                session_id=sid,
                timestamp=now,
                kind="tool",
                content="bsw_write",
                tool_name="bsw_write",
                tool_args={
                    "module": module,
                    "path": rel_path,
                    "op": "modify",
                    "value": p.value.raw,
                    "old_value": None,
                },
                tool_result="ok",
            )
            store.append(tool_entry)
            tool_ids.append(tool_entry.id)

        return RecordResult(
            session_id=sid,
            user_entry_id=user_entry.id,
            tool_entry_ids=tuple(tool_ids),
        )


def _strip_module_prefix(path: str, module: str) -> str:
    """把 ``Mcu/Clock/ClockFreq`` 拆为 ``Clock/ClockFreq``。"""
    prefix = f"{module}/"
    if path.startswith(prefix):
        return path[len(prefix) :]
    return path


def get_current_session_path(store: SessionStore) -> Path:
    """返回 ``.current`` 文件路径（供测试/调试用）。"""
    return store.dir / _CURRENT_FILE
