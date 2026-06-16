"""FRIF-AP-001 — FrIfCluster without FrIfController.

v2 检测深度：

* 检查 ``key_params`` 里 FrIfCluster 相关参数
* 检查 cluster 是否有 controller 引用
* 如果没有 controller → yield violation

v2 增强方向：

* 解析 FrIf 模块下 FrIfCluster 容器
* 检查 FrIfControllerRef 引用
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class FrIfAp001Rule:
    """FRIF-AP-001: FrIfCluster without FrIfController."""

    rule_id: ClassVar[str] = "FRIF-AP-001"
    severity_default: ClassVar[str] = LintSeverity.ERROR
    applies_to: ClassVar[str] = "arxml"  # 只吃 ArxmlLintData

    #: FrIf cluster 相关参数
    _FRIF_CLUSTER_PARAMS: ClassVar[tuple[str, ...]] = (
        "FrIfCluster",
        "FrIfController",
        "FrIfControllerRef",
    )

    def check(self, extracted: ArxmlLintData) -> Iterable[LintViolation]:
        # v1 MVP stub：inspector key_params 不含 FrIfCluster 详情
        # 数据不足以做"cluster 无 controller"判断 → 不 yield（避免误报）
        # v2 增强方向：解析 FrIf 模块下 FrIfCluster 容器和 controller 引用
        for _p in extracted.key_params:
            if _p.get("name") in self._FRIF_CLUSTER_PARAMS:
                # 当前不报（controller 引用不可知）
                return ()
        return ()
