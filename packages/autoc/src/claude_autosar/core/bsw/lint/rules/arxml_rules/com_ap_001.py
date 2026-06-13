"""COM-AP-001 — ComSignal > 8 byte 在 classic CAN 必定失败。

v1 MVP 检测深度：

* 遍历 ``signals_by_ipdu``，对每个 signal 看 ``ComSignalLength``
* ``ComSignalLength > 8`` → yield violation（severity = ERROR）
* IPdu 方向不是 CAN（CANFD）也报（plan §4.2 文字"ComSignal > 8 byte 走经典 CAN = 100% 失败"）

v2 增强方向：

* 区分 classic CAN / CAN-FD — 看 IPdu 的 ``ComIPduDirection`` + 新增
  ``ComTxIPduCanFdFrameType`` 等扩展字段
* 看 ComGroupSignal（group signal 不直接走 CAN）— 略过
"""

from __future__ import annotations

from typing import ClassVar
from collections.abc import Iterable

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class ComAp001Rule:
    """COM-AP-001: ComSignal length > 8 byte in classic CAN."""

    rule_id: ClassVar[str] = "COM-AP-001"
    severity_default: ClassVar[str] = LintSeverity.ERROR
    applies_to: ClassVar[str] = "arxml"  # 只吃 ArxmlLintData

    #: classic CAN 单帧最大 payload = 8 byte
    _MAX_CLASSIC_CAN_PAYLOAD: ClassVar[int] = 8

    def check(
        self, extracted: ArxmlLintData
    ) -> Iterable[LintViolation]:
        for ipdu_name, signals in extracted.signals_by_ipdu.items():
            for sig in signals:
                # ComSignalLength 可能在 PARAM-VALUES 里以字符串存
                length_str = sig.get("ComSignalLength")
                if length_str is None:
                    # 没设 length → 跳过（不误报）
                    continue
                try:
                    length = int(length_str)
                except (TypeError, ValueError):
                    continue
                if length > self._MAX_CLASSIC_CAN_PAYLOAD:
                    sig_name = str(sig.get("name", "?"))
                    yield LintViolation(
                        rule_id=self.rule_id,
                        severity=self.severity_default,
                        message=(
                            f"ComSignal length {length} > "
                            f"{self._MAX_CLASSIC_CAN_PAYLOAD} byte in classic CAN"
                        ),
                        location=f"{ipdu_name}/{sig_name}",
                        module=extracted.module_name,
                        suggestion="use CAN-FD or split signal",
                    )
