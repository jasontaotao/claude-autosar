"""T4.4 — 改参 changelog 提取与渲染。

从 ``SessionTree`` 提取所有 ``kind="tool"`` 且 ``tool_name="bsw_write"`` 的
entry 转为 ``Change`` 记录，再渲染为 timeline 或 by-url 两种文本视图。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from autoc.core.session.tree import SessionTree


@dataclass(frozen=True)
class Change:
    """一条改参记录。"""

    timestamp: str
    module: str
    path: str
    kind: str  # "add" | "modify" | "delete"
    old_value: Any
    new_value: Any
    session_id: str
    entry_id: str


_OP_LABEL: dict[str, str] = {
    "add": "+ ADD",
    "modify": "~ MOD",
    "delete": "- DEL",
}


def extract_changes(tree: SessionTree) -> list[Change]:
    """从 session tree 提取所有 bsw_write entry 为 Change。

    - 跳过非 ``kind="tool"`` 的 entry
    - 跳过 ``tool_name != "bsw_write"`` 的 entry
    - 保留 session.entries 顺序（调用方自行排序）
    """
    out: list[Change] = []
    for entry in tree.session.entries:
        if entry.kind != "tool" or entry.tool_name != "bsw_write":
            continue
        args = entry.tool_args or {}
        out.append(
            Change(
                timestamp=entry.timestamp,
                module=str(args.get("module", "")),
                path=str(args.get("path", "")),
                kind=str(args.get("op", "modify")),
                old_value=args.get("old_value"),
                new_value=args.get("value"),
                session_id=entry.session_id,
                entry_id=entry.id,
            )
        )
    return out


def render_timeline(changes: list[Change]) -> str:
    """按 timestamp 倒序（最新在上）渲染 timeline 文本。"""
    if not changes:
        return "# 改参 Timeline\n\n(暂无改参记录)\n"
    sorted_changes = sorted(changes, key=lambda c: c.timestamp, reverse=True)
    lines: list[str] = ["# 改参 Timeline", ""]
    for c in sorted_changes:
        op_label = _OP_LABEL.get(c.kind, c.kind)
        url = _format_url(c.module, c.path)
        lines.append(f"[{c.timestamp}] {op_label}  {url}")
        if c.kind == "modify" and c.old_value is not None:
            lines.append(f"    {c.old_value} → {c.new_value}")
        elif c.kind == "add":
            lines.append(f"    = {c.new_value}")
        elif c.kind == "delete":
            lines.append(f"    (was: {c.old_value})")
    return "\n".join(lines) + "\n"


def render_by_url(changes: list[Change]) -> str:
    """按 (module, path) 分组渲染。组内按 timestamp 倒序，组间按 URL 字母序。"""
    if not changes:
        return "# 改参 By URL\n\n(暂无改参记录)\n"
    groups: dict[tuple[str, str], list[Change]] = {}
    for c in changes:
        groups.setdefault((c.module, c.path), []).append(c)
    lines: list[str] = ["# 改参 By URL", ""]
    for (module, path), group_changes in sorted(groups.items()):
        lines.append(f"## {_format_url(module, path)}")
        for c in sorted(group_changes, key=lambda c: c.timestamp, reverse=True):
            op_mark = {"add": "+", "modify": "~", "delete": "-"}.get(c.kind, "?")
            value = c.new_value if c.new_value is not None else c.old_value
            lines.append(f"  [{c.timestamp}] {op_mark} {value}")
        lines.append("")
    return "\n".join(lines)


def _format_url(module: str, path: str) -> str:
    """组合 module + path 为 ``Mcu/Clock/ClockFreq`` 形式。"""
    if not module:
        return path
    if not path:
        return module
    if path.startswith(f"{module}/"):
        return path
    return f"{module}/{path}"
