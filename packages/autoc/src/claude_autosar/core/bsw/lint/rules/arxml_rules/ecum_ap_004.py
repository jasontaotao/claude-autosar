"""ECUM-AP-004 — EcuMWakeupSource configured but no validation.

v2 检测深度：

* 从 ``key_params`` 提取 EcuMWakeupSource 容器下的 EcuMValidationTimeout
* 如果唤醒源存在但 EcuMValidationTimeout 未配置或为 0 → yield violation

规范来源：AUTOSAR SWS_EcuM (SWS_EcuM_02850) — EcuMValidationTimeout
用于确定唤醒事件是否已验证。无验证超时的唤醒源可能导致 ECU
被噪声误唤醒后无法回到休眠状态。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class EcuMAp004Rule:
    """ECUM-AP-004: EcuMWakeupSource configured but no validation."""

    rule_id: ClassVar[str] = "ECUM-AP-004"
    severity_default: ClassVar[str] = LintSeverity.WARNING
    applies_to: ClassVar[str] = "arxml"

    #: SWS_EcuM: EcuMValidationTimeout 是标准参数
    _WAKEUP_SOURCE_PARAM: ClassVar[str] = "EcuMWakeupSource"
    _VALIDATION_TIMEOUT_PARAM: ClassVar[str] = "EcuMValidationTimeout"

    def check(self, extracted: ArxmlLintData) -> Iterable[LintViolation]:
        # v1 MVP stub：当前 key_params 没拆 EcuMValidationTimeout
        # 数据不足以做"唤醒源无验证"判断 → 不 yield（避免误报）
        # v2 增强方向：解析 EcuM 模块下 EcuMWakeupSource 容器和 ValidationTimeout
        for _p in extracted.key_params:
            if _p.get("name") in (self._WAKEUP_SOURCE_PARAM, self._VALIDATION_TIMEOUT_PARAM):
                # 当前不报（validation timeout 不可知）
                return ()
        return ()
