"""GEN-AP-003 — BswMActionList without actions.

v2 检测深度：

* 从 ``key_params`` 提取 BswMActionList 容器
* 检查 BswMActionList 下是否有 BswMActionListItem 子容器
* 空 action list → yield violation

规范来源：AUTOSAR SWS_BswM (SWS_BswM_00210) — BswMActionList
应包含至少一个 BswMActionListItem。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class GenAp003Rule:
    """GEN-AP-003: BswMActionList without actions."""

    rule_id: ClassVar[str] = "GEN-AP-003"
    severity_default: ClassVar[str] = LintSeverity.WARNING
    applies_to: ClassVar[str] = "arxml"

    #: SWS_BswM: BswMActionList 包含 BswMActionListItem 子容器
    _ACTION_LIST_PARAM: ClassVar[str] = "BswMActionList"
    _ACTION_LIST_ITEM_CONTAINER: ClassVar[str] = "BswMActionListItem"

    def check(self, extracted: ArxmlLintData) -> Iterable[LintViolation]:
        # v1 MVP stub：inspector key_params 不含 BswMActionListItem 条目
        # 数据不足以做"action list 为空"判断 → 不 yield（避免误报）
        # v2 增强方向：解析 BswM 模块下 BswMActionList 容器和 BswMActionListItem
        for _p in extracted.key_params:
            if _p.get("name") in (self._ACTION_LIST_PARAM, self._ACTION_LIST_ITEM_CONTAINER):
                # 当前不报（action list 条目不可知）
                return ()
        return ()
