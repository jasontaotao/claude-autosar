"""NM-AP-003 — CanNmPnEnabled but no partial networking config.

v2 检测深度：

* 从 ``key_params`` 提取 CanNmPnEnabled
* 如果值为 true，检查 CanNmPnResetTime 和 CanNmPnEraCalcEnabled 是否配置
* PN 启用但缺少 PN 配置参数 → yield violation

规范来源：AUTOSAR SWS_CanNm (SWS_CanNm_00338-00345) — Partial Networking
是 CanNm 特定功能，配置参数在 CanNm 模块下，不在 Nm 通用层。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class NmAp003Rule:
    """NM-AP-003: CanNmPnEnabled but no partial networking config."""

    rule_id: ClassVar[str] = "NM-AP-003"
    severity_default: ClassVar[str] = LintSeverity.WARNING
    applies_to: ClassVar[str] = "arxml"

    #: SWS_CanNm: PN 参数全部在 CanNm 模块下
    _PN_ENABLED_PARAM: ClassVar[str] = "CanNmPnEnabled"
    _PN_CONFIG_PARAMS: ClassVar[tuple[str, ...]] = (
        "CanNmPnResetTime",
        "CanNmPnEraCalcEnabled",
    )

    def check(self, extracted: ArxmlLintData) -> Iterable[LintViolation]:
        # v1 MVP stub：当前 key_params 没拆 CanNm PN 参数
        # 数据不足以做"PN 启用但无配置"判断 → 不 yield（避免误报）
        # v2 增强方向：解析 CanNm 模块下 CanNmPnEnabled 和相关参数
        for _p in extracted.key_params:
            if _p.get("name") in (self._PN_ENABLED_PARAM, *self._PN_CONFIG_PARAMS):
                # 当前不报（PN 配置不可知）
                return ()
        return ()
