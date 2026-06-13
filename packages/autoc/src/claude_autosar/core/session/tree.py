"""T4.2 — session tree 树形操作。

不可变（frozen dataclass + with_X 模式）。
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime
import uuid

from claude_autosar.core.session.store import Session, SessionEntry, SessionStore


def _now_iso8601_utc() -> str:
    """返回当前 UTC 时间的 ISO 8601 字符串（毫秒精度 + ``Z`` 后缀）。"""
    now = datetime.now(UTC)
    return now.strftime("%Y-%m-%dT%H:%M:%S") + f".{now.microsecond // 1000:03d}Z"


@dataclass(frozen=True)
class SessionTree:
    """基于 parent_id 的不可变 session 树。

    不维护显式树结构——靠遍历 ``session.entries`` 派生出 root/children/walk。
    优势：append-only JSONL 写入和内存表示保持一致。
    """

    session: Session

    # ----- 查询 -----

    def root(self) -> SessionEntry:
        """返回"本 tree 的起点 entry"。

        正常 tree：parent_id is None 的 entry。
        Fork 后的 tree：parent_id 指向原 session（不在本 tree 内的 entry）的 entry。
        空 tree：抛 ValueError。
        """
        if not self.session.entries:
            raise ValueError(f"session {self.session.id!r} is empty")
        ids = {e.id for e in self.session.entries}
        for entry in self.session.entries:
            if entry.parent_id is None or entry.parent_id not in ids:
                return entry
        # 防御：cycles 不应存在；保底返回首条
        return self.session.entries[0]

    def children(self, entry_id: str) -> list[SessionEntry]:
        """返回所有 parent_id == entry_id 的直接子节点（保序）。"""
        return [e for e in self.session.entries if e.parent_id == entry_id]

    def find(self, entry_id: str) -> SessionEntry | None:
        """按 id 查找 entry；找不到返回 None。"""
        for entry in self.session.entries:
            if entry.id == entry_id:
                return entry
        return None

    def walk(self) -> Iterator[SessionEntry]:
        """DFS pre-order 遍历所有 entry。空 tree 直接结束。"""
        try:
            r = self.root()
        except ValueError:
            return
        yield r
        # 显式 stack 避免 Python 递归深度问题
        stack = list(reversed(self.children(r.id)))
        while stack:
            node = stack.pop()
            yield node
            stack.extend(reversed(self.children(node.id)))

    # ----- 不可变变更 -----

    def with_entry(self, entry: SessionEntry) -> SessionTree:
        """追加 entry 到 session 末尾；跨 session 注入抛 ValueError。"""
        if entry.session_id != self.session.id:
            raise ValueError(
                f"entry.session_id={entry.session_id!r} != " f"tree.session.id={self.session.id!r}"
            )
        new_session = replace(
            self.session,
            entries=self.session.entries + (entry,),
        )
        return SessionTree(session=new_session)

    def with_session_meta(self, title: str) -> SessionTree:
        """返回新 tree，title 覆盖（其它字段不变）。"""
        return SessionTree(
            session=replace(self.session, title=title),
        )

    def fork(self, parent_entry_id: str, new_session_id: str) -> SessionTree:
        """创建新 session tree，以新 root entry 指向原 tree 的某 entry。

        新 root entry 的 parent_id 指向原 tree 的 entry id（不是新 session 内的）。
        """
        if self.find(parent_entry_id) is None:
            raise ValueError(
                f"parent_entry_id {parent_entry_id!r} not found in session " f"{self.session.id!r}"
            )
        now = _now_iso8601_utc()
        fork_root = SessionEntry(
            id=uuid.uuid4().hex,
            parent_id=parent_entry_id,
            session_id=new_session_id,
            timestamp=now,
            kind="user",
            content="",
        )
        new_session = Session(
            id=new_session_id,
            started_at=now,
            entries=(fork_root,),
        )
        return SessionTree(session=new_session)

    # ----- 构造便利 -----

    @classmethod
    def from_session_id(cls, session_id: str, store: SessionStore) -> SessionTree:
        """从 SessionStore 读取并构造 tree。"""
        return cls(session=store.read(session_id))
