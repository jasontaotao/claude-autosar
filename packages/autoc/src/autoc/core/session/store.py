"""T4.1 — 会话 JSONL append-only 存储。

约定：
- 每个 session 一个文件 ``<session_id>.jsonl``，每行一条 ``SessionEntry`` JSON。
- append 写入走 ``flush() + os.fsync()`` 保证 Windows 强持久。
- ``SessionStore(dir=None)`` 默认用 ``global_session_dir()`` 解析路径。
- 读不存在文件抛 ``SessionStoreError``（明确失败，不静默）。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
from typing import Any
import uuid

from autoc.utils.paths import global_session_dir


class SessionStoreError(RuntimeError):
    """SessionStore 操作的明确失败（文件不存在、JSON 损坏等）。"""


@dataclass(frozen=True)
class SessionEntry:
    """单条会话节点。frozen 保证不可变。"""

    id: str
    parent_id: str | None
    session_id: str
    timestamp: str
    kind: str
    content: str
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    tool_result: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """转 dict（asdict + None 过滤掉 None 字段以减小 JSONL 体积）。"""
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SessionEntry:
        """从 dict 重建。None 字段用 dataclass 默认。"""
        return cls(
            id=d["id"],
            parent_id=d.get("parent_id"),
            session_id=d["session_id"],
            timestamp=d["timestamp"],
            kind=d["kind"],
            content=d["content"],
            tool_name=d.get("tool_name"),
            tool_args=d.get("tool_args"),
            tool_result=d.get("tool_result"),
        )


@dataclass(frozen=True)
class Session:
    """一个 session 的元数据 + 所有 entry。

    started_at 默认等于 entries[0].timestamp，但允许构造时显式覆盖。
    """

    id: str
    started_at: str
    title: str = ""
    entries: tuple[SessionEntry, ...] = field(default_factory=tuple)


class SessionStore:
    """JSONL append-only 存储。"""

    def __init__(self, dir: Path | str | None = None) -> None:
        if dir is None:
            self.dir: Path = global_session_dir()
        else:
            self.dir = Path(dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        return self.dir / f"{session_id}.jsonl"

    def append(self, entry: SessionEntry) -> None:
        """追加一条 entry 到对应 session 文件。"""
        path = self._path(entry.session_id)
        # 序列化：None 字段剔除，确保中文原样（ensure_ascii=False）
        line = json.dumps(entry.to_dict(), ensure_ascii=False, sort_keys=True)
        # append-binary 模式 + 行结束符
        with path.open("ab") as f:
            f.write(line.encode("utf-8"))
            f.write(b"\n")
            f.flush()
            os.fsync(f.fileno())

    def read(self, session_id: str) -> Session:
        """读取整个 session。不存在文件抛 SessionStoreError。"""
        path = self._path(session_id)
        if not path.is_file():
            raise SessionStoreError(f"session not found: {session_id}")
        entries = self._parse_lines(_read_lines(path))
        if not entries:
            return Session(id=session_id, started_at="", entries=())
        return Session(
            id=session_id,
            started_at=entries[0].timestamp,
            entries=tuple(entries),
        )

    def tail(self, session_id: str, n: int) -> list[SessionEntry]:
        """返回最后 n 条 entry（n<=0 返回空）。"""
        if n <= 0:
            return []
        path = self._path(session_id)
        if not path.is_file():
            raise SessionStoreError(f"session not found: {session_id}")
        entries = self._parse_lines(_read_lines(path))
        return entries[-n:]

    def list_session_ids(self) -> list[str]:
        """枚举所有 <id>.jsonl 文件中的 session id。"""
        if not self.dir.is_dir():
            return []
        return sorted(p.stem for p in self.dir.iterdir() if p.is_file() and p.suffix == ".jsonl")

    @staticmethod
    def _parse_lines(lines: Iterable[str]) -> list[SessionEntry]:
        out: list[SessionEntry] = []
        for i, line in enumerate(lines, start=1):
            if not line.strip():
                continue  # 跳过空行（防御性）
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise SessionStoreError(f"corrupt JSONL at line {i}: {e}") from e
            out.append(SessionEntry.from_dict(obj))
        return out


def new_session_id() -> str:
    """生成 32 字符 hex session id（UUID4 去 dash）。"""
    return uuid.uuid4().hex


def _read_lines(path: Path) -> list[str]:
    """读所有行（保持尾随换行不参与 splitlines 后的逻辑由调用方处理）。"""
    return path.read_text(encoding="utf-8").splitlines()


def resolve_latest_session_id(sessions_dir: Path) -> str | None:
    """按 mtime 倒序找最新 session id（``autoc session show latest`` 语义）。

    :param sessions_dir: 指向 ``*.jsonl`` 文件目录的 :class:`Path`
    :return: 最新 mtime 的 session 文件 stem（不含 ``.jsonl``），目录为空时返回 ``None``
    """
    if not sessions_dir.is_dir():
        return None
    files = [p for p in sessions_dir.iterdir() if p.is_file() and p.suffix == ".jsonl"]
    if not files:
        return None
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0].stem
