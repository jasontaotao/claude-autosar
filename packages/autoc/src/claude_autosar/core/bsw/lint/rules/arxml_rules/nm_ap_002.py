"""NM-AP-002 — CanNmNodeDetectionEnabled without CanNmNodeIdCallback.

v2 检测深度：

* 从 ``key_params`` 提取 CanNmNodeDetectionEnabled
* 如果值为 true，检查 CanNmNodeIdCallback 是否配置
* 启用节点检测但没有回调 → yield violation

规范来源：AUTOSAR SWS_CanNm — Node Detection 是 CanNm 特定功能，
回调函数用于通知上层模块（ComM / Nm User）节点加入/离开事件。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class NmAp002Rule:
    """NM-AP-002: CanNmNodeDetectionEnabled but no CanNmNodeIdCallback."""

    rule_id: ClassVar[str] = "NM-AP-002"
    severity_default: ClassVar[str] = LintSeverity.WARNING
    applies_to: ClassVar[str] = "arxml"

    #: CanNm Node Detection 相关参数
    _NODE_DETECTION_ENABLED: ClassVar[str] = "CanNmNodeDetectionEnabled"
    _NODE_ID_CALLBACK: ClassVar[str] = "CanNmNodeIdCallback"

    def check(self, extracted: ArxmlLintData) -> Iterable[LintViolation]:
        # 按 container 分组收集参数
        detection_by_container: dict[str, str] = {}
        callback_by_container: dict[str, str] = {}

        for p in extracted.key_params:
            name = str(p.get("name", ""))
            container = str(p.get("container", ""))
            value = str(p.get("value", ""))
            if name == self._NODE_DETECTION_ENABLED:
                detection_by_container[container] = value
            elif name == self._NODE_ID_CALLBACK:
                callback_by_container[container] = value

        # 检查同一 container 下的组合
        for container, enabled in detection_by_container.items():
            if enabled.lower() != "true":
                continue
            callback = callback_by_container.get(container)
            if callback is None or callback == "":
                yield LintViolation(
                    rule_id=self.rule_id,
                    severity=self.severity_default,
                    message=(
                        f"CanNmNodeDetectionEnabled=true but no "
                        f"CanNmNodeIdCallback configured in '{container}'"
                    ),
                    location=container,
                    module=extracted.module_name,
                    suggestion=(
                        "Configure CanNmNodeIdCallback to receive "
                        "node detection events, or disable node detection"
                    ),
                )
