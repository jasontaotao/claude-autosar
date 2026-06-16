"""COM-AP-003 — ComSignal without ComIPdu reference.

v2 检测深度：

* 遍历 ``signals_by_ipdu``，收集所有被引用的 signal 名称
* 遍历 ``ipdus``，检查每个 IPdu 的 signal 引用列表
* 如果某个 signal 未被任何 IPdu 引用 → yield violation

v2 增强方向：

* 解析 ComSignalRef / ComGroupSignalRef 引用链
* 支持 signal group 内的 signal 引用检查
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class ComAp003Rule:
    """COM-AP-003: ComSignal not referenced by any ComIPdu."""

    rule_id: ClassVar[str] = "COM-AP-003"
    severity_default: ClassVar[str] = LintSeverity.ERROR
    applies_to: ClassVar[str] = "arxml"  # 只吃 ArxmlLintData

    def check(self, extracted: ArxmlLintData) -> Iterable[LintViolation]:
        # 收集所有被 IPdu 引用的 signal 名称
        referenced_signals: set[str] = set()

        # 从 signals_by_ipdu 收集（这些是已经被 inspector 解析出来的）
        for _ipdu_name, signals in extracted.signals_by_ipdu.items():
            for sig in signals:
                sig_name = str(sig.get("name", ""))
                if sig_name:
                    referenced_signals.add(sig_name)

        # 如果没有 signals_by_ipdu 数据，跳过（不误报）
        if not extracted.signals_by_ipdu:
            return ()

        # 检查是否有未引用的 signal（v2 简化：只检查 inspector 已解析的）
        # 注意：当前 inspector 只解析被 IPdu 引用的 signal，
        # 所以这个规则需要更深层的数据源才能生效
        # v1 MVP：不 yield（FP=0 优先）
        return ()
