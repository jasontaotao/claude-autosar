"""ARXML template diff — Sprint 9.2 M1-T — T9.2-β.

Immutable ``TemplateDiff`` / ``TemplateDiffResult`` dataclasses plus a
pure ``diff_arxml_templates`` function that compares two
:class:`claude_autosar.core.bsw.ecuc.ECUCDocument` snapshots and emits
per-path ``add`` / ``modify`` / ``delete`` operations.

Design notes (aligned with plan §2.1 / §2.2):

  - **Mirrors xdm_diff** — same dataclass shape, same op literals, same
    property accessors (``adds`` / ``modifies`` / ``deletes`` / ``is_empty``).
    The shared shape lets :mod:`claude_autosar.core.bsw.templates.apply`
    work on a unified ``TemplateDiff`` regardless of source format.
  - **ECUCValue-native** — the values are :class:`ECUCValue` (path / raw /
    type) — diffs are computed on ``ECUCValue.path`` alone.
  - **Three ops only** — ``add`` (in template, missing in current),
    ``modify`` (in both, different ``raw``), ``delete`` (in current,
    missing in template). Identical (path, raw) pairs are dropped.
  - **Immutability** — ``TemplateDiffResult.diffs`` is a tuple and the
    dataclass is ``frozen=True``.
  - **Pure function** — ``diff_arxml_templates`` does not mutate the
    inputs and does not call I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from claude_autosar.core.bsw.ecuc import ECUCValue, ECUCDocument

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

#: 三种 diff op：add（template 有 current 没）/ modify（都有但 raw 不同）/
#: delete（current 有 template 没）。
TemplateDiffOp = Literal["add", "modify", "delete"]


@dataclass(frozen=True)
class TemplateDiff:
    """一条 diff 记录：path + current/template side + op。

    current / template 一侧为 None 时，对应 add（template 有）或
    delete（current 有）。
    """

    path: str
    current: ECUCValue | None
    template: ECUCValue | None
    op: TemplateDiffOp


@dataclass(frozen=True)
class TemplateDiffResult:
    """不可变 diff 结果：diffs 元组 + 三个便利 property。

    module_name 在 result 上冗余保存（两条 :class:`ECUCDocument` 必须
    module_name 一致，否则视为 bug；保留以便 caller 报告）。
    """

    module_name: str
    diffs: tuple[TemplateDiff, ...]

    @property
    def adds(self) -> tuple[TemplateDiff, ...]:
        """op == "add" 的 diff 列表。"""
        return tuple(d for d in self.diffs if d.op == "add")

    @property
    def modifies(self) -> tuple[TemplateDiff, ...]:
        """op == "modify" 的 diff 列表。"""
        return tuple(d for d in self.diffs if d.op == "modify")

    @property
    def deletes(self) -> tuple[TemplateDiff, ...]:
        """op == "delete" 的 diff 列表。"""
        return tuple(d for d in self.diffs if d.op == "delete")

    def is_empty(self) -> bool:
        """没有任何 diff。"""
        return len(self.diffs) == 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def diff_arxml_templates(
    current: ECUCDocument,
    template: ECUCDocument,
) -> TemplateDiffResult:
    """比较两个 :class:`ECUCDocument`，返回 diff 集合（纯函数）。

    规则（plan §2.2 锁定）：

      - ``template`` 有 ``current`` 没有的 path → ``add``
      - ``current`` 有 ``template`` 没有的 path → ``delete``
      - 都在但 ``raw`` 不同 → ``modify``
      - 都在且 ``raw`` 相同 → 不记录

    :param current: 现状模块（snapshot）
    :param template: 模板 / 期望模块
    :return: 不可变 :class:`TemplateDiffResult`
    :raises ValueError: 两个 doc 的 module_name 不一致
    """
    if current.module_name != template.module_name:
        raise ValueError(
            f"diff_arxml_templates: module_name mismatch "
            f"(current={current.module_name!r}, "
            f"template={template.module_name!r})"
        )

    current_by_path: dict[str, ECUCValue] = {v.path: v for v in current.values}
    template_by_path: dict[str, ECUCValue] = {v.path: v for v in template.values}

    diffs: list[TemplateDiff] = []

    # add: in template, not in current
    for path, tval in template_by_path.items():
        if path not in current_by_path:
            diffs.append(
                TemplateDiff(
                    path=path,
                    current=None,
                    template=tval,
                    op="add",
                )
            )

    # delete: in current, not in template
    for path, cval in current_by_path.items():
        if path not in template_by_path:
            diffs.append(
                TemplateDiff(
                    path=path,
                    current=cval,
                    template=None,
                    op="delete",
                )
            )

    # modify: in both, different raw
    for path, tval in template_by_path.items():
        existing_cval = current_by_path.get(path)
        if existing_cval is None:
            continue  # already handled as add
        if existing_cval.raw != tval.raw:
            diffs.append(
                TemplateDiff(
                    path=path,
                    current=existing_cval,
                    template=tval,
                    op="modify",
                )
            )

    # 稳定排序：path 升序 → op 升序（add < delete < modify 按字典序）
    diffs.sort(key=lambda d: (d.path, d.op))
    return TemplateDiffResult(
        module_name=current.module_name,
        diffs=tuple(diffs),
    )


__all__ = [
    "TemplateDiffOp",
    "TemplateDiff",
    "TemplateDiffResult",
    "diff_arxml_templates",
]
