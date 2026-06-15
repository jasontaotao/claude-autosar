"""NM-AP-001 — CanNm 报文不在 ComM 引用 = 网络起不来。

v1 MVP 检测深度：

* 检查 key_params 里 ``CanNmChannel`` / ``ComMChannel`` 字段
* v1 数据源 key_params 不含 Nm 引用图 → 不 yield

v2 增强方向：

* 解析 Nm 模块下 CanNm 容器 + ComM 模块下 ComMChannel 容器
* 检测"CanNmChannel 数量 > 0 但无任何 ComMChannel 引用"
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class NmAp001Rule:
    """NM-AP-001: CanNm message not referenced by any ComM channel."""

    rule_id: ClassVar[str] = "NM-AP-001"
    severity_default: ClassVar[str] = LintSeverity.ERROR
    applies_to: ClassVar[str] = "arxml"  # 只吃 ArxmlLintData

    _NM_PARAMS: ClassVar[tuple[str, ...]] = (
        "CanNmChannel",
        "CanNmNodeId",
    )

    def check(self, extracted: ArxmlLintData) -> Iterable[LintViolation]:
        # v1 MVP stub：inspector 没拆 Nm / ComM 交叉引用
        # → 不 yield（FP=0 优先）
        for _p in extracted.key_params:
            if _p.get("name") in self._NM_PARAMS:
                return ()
        return ()
