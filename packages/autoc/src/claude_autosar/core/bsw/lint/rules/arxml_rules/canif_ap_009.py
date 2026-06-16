"""CANIF-AP-009 — CanIfHrhSoftwareFilter with no HRH configured.

v2 检测深度：

* 检查 ``key_params`` 里 ``CanIfHrhSoftwareFilter`` 是否启用
* 检查 ``CanIfHrhDefinition`` 容器数量
* 如果软件过滤启用但没有 HRH 定义 → yield violation

v2 增强方向：

* 解析 CanIfInitCfg 子容器里的 CanIfHrhDefinition 实际 count
* 跨字段联合：software_enabled && hrh_count == 0 → violation
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class CanIfAp009Rule:
    """CANIF-AP-009: CanIfHrhSoftwareFilter enabled but no HRH configured."""

    rule_id: ClassVar[str] = "CANIF-AP-009"
    severity_default: ClassVar[str] = LintSeverity.WARNING
    applies_to: ClassVar[str] = "arxml"  # 只吃 ArxmlLintData

    #: HRH 软件过滤相关参数
    _HRH_PARAMS: ClassVar[tuple[str, ...]] = (
        "CanIfHrhSoftwareFilter",
        "CanIfHrhDefinition",
    )

    def check(self, extracted: ArxmlLintData) -> Iterable[LintViolation]:
        # v1 MVP stub：inspector key_params 不含 CanIfHrhDefinition 计数
        # 数据不足以做"软件过滤启用但无 HRH 定义"判断 → 不 yield（避免误报）
        # v2 增强方向：解析 CanIfInitCfg 子容器里的 CanIfHrhDefinition count
        for _p in extracted.key_params:
            if _p.get("name") in self._HRH_PARAMS:
                # 当前不报（hrh count 不可知）
                return ()
        return ()
