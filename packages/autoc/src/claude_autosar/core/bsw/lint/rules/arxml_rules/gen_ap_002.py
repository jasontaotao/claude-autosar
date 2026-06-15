"""GEN-AP-002 — BswM 自循环 = 启动 hang。

v1 MVP 检测深度：

* 检查 key_params 里 ``BswMAction`` / ``BswMRule`` 字段
* v1 数据源 key_params 不含 BswM action graph → 不 yield

v2 增强方向：

* 解析 BswM 模块下 ``BswMActionList`` / ``BswMEvent`` 引用图
* 检测"BswMAction 触发自己"（直接循环）+ 间接循环
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class GenAp002Rule:
    """GEN-AP-002: BswM action self-loop / cycle causing startup hang."""

    rule_id: ClassVar[str] = "GEN-AP-002"
    severity_default: ClassVar[str] = LintSeverity.ERROR
    applies_to: ClassVar[str] = "arxml"  # 只吃 ArxmlLintData

    _BSWM_PARAMS: ClassVar[tuple[str, ...]] = (
        "BswMActionList",
        "BswMRule",
    )

    def check(self, extracted: ArxmlLintData) -> Iterable[LintViolation]:
        # v1 MVP stub：inspector 没拆 BswM action graph
        # → 不 yield（FP=0 优先）
        for _p in extracted.key_params:
            if _p.get("name") in self._BSWM_PARAMS:
                return ()
        return ()
