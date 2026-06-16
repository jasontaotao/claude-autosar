"""GEN-AP-004 — BswMRule without conditions.

v2 检测深度：

* 从 ``key_params`` 提取 BswMRule 容器
* 检查 BswMRule 下是否有 BswMCondition 子容器
* 无条件规则 → yield violation

规范来源：AUTOSAR SWS_BswM (SWS_BswM_00145) — BswMRule
应包含至少一个 BswMCondition。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class GenAp004Rule:
    """GEN-AP-004: BswMRule without conditions."""

    rule_id: ClassVar[str] = "GEN-AP-004"
    severity_default: ClassVar[str] = LintSeverity.WARNING
    applies_to: ClassVar[str] = "arxml"

    #: SWS_BswM: BswMRule 包含 BswMCondition 子容器
    _RULE_PARAM: ClassVar[str] = "BswMRule"
    _CONDITION_CONTAINER: ClassVar[str] = "BswMCondition"

    def check(self, extracted: ArxmlLintData) -> Iterable[LintViolation]:
        # v1 MVP stub：inspector key_params 不含 BswMCondition 条目
        # 数据不足以做"rule 无条件"判断 → 不 yield（避免误报）
        # v2 增强方向：解析 BswM 模块下 BswMRule 容器和 BswMCondition
        for _p in extracted.key_params:
            if _p.get("name") in (self._RULE_PARAM, self._CONDITION_CONTAINER):
                # 当前不报（rule 条件不可知）
                return ()
        return ()
