"""DEM-AP-004 — Snapshot > 255 byte UDS 标准不兼容。

v1 MVP 检测深度：

* 检查 XDM leaves 路径中含 ``DemEventParameter`` + ``SnapshotDataLength``
* 阈值：255 byte（ISO 14229 UDS 0x1904 / 0x1906 上限）
* v1 fixture 无 Dem → 不 yield（FP=0 优先）

v2 增强方向：

* 解析 ``DemEventParameter`` 容器下 ``DemSnapshotDataRecord`` 列表
* 累加每个 record 的 size vs 上限
"""

from __future__ import annotations

from typing import Any, ClassVar
from collections.abc import Iterable

from claude_autosar.core.bsw.lint import (
    LintSeverity,
    LintViolation,
    XdmLintData,
)

# Snapshot data byte 上限（ISO 14229-1 / UDS 0x1904 0x1906 标准）
_SNAPSHOT_BYTE_LIMIT = 255


class DemAp004Rule:
    """DEM-AP-004: DemEventParameter snapshot size > 255 byte (UDS limit)."""

    rule_id: ClassVar[str] = "DEM-AP-004"
    severity_default: ClassVar[str] = LintSeverity.ERROR
    applies_to: ClassVar[str] = "xdm"  # 只吃 XdmLintData

    _DEM_EVENT_KEYWORDS: ClassVar[tuple[str, ...]] = (
        "DemEventParameter",
        "SnapshotDataLength",
    )

    def check(
        self, extracted: Any
    ) -> Iterable[LintViolation]:
        # XDM-only rule — skip silently if data is not XdmLintData
        if not isinstance(extracted, XdmLintData):
            return ()
        # v1 MVP stub：XDM fixture 无 Dem 数据 → 不 yield
        for _leaf in extracted.leaves:
            path = str(_leaf.get("path", ""))
            if any(kw in path for kw in self._DEM_EVENT_KEYWORDS):
                # 当前不报（v2 解析后再 yield）
                _ = _SNAPSHOT_BYTE_LIMIT
                return ()
        return ()
