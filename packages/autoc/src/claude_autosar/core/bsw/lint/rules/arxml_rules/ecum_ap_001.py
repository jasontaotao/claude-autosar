"""ECUM-AP-001 — RunRequest 死锁 → 整车不能休眠。

v1 MVP 检测深度：

* 检查 EcuM 模块的 key_params，看是否有 ``EcuMComMChannels`` 引用图
* v1 数据源 key_params 不含 ComM 引用图 → 不 yield
* plan §4.2 表写"ComM 引用循环"，v2 需要图遍历

v2 增强方向：

* 解析 EcuM 模块下 ``EcuMComMChannel`` 引用 + ComM 自身 channel 定义
* 检测"channel A 唤醒 → channel B；channel B 唤醒 → channel A"循环
"""

from __future__ import annotations

from typing import ClassVar
from collections.abc import Iterable

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class EcuMAp001Rule:
    """ECUM-AP-001: RunRequest deadlock via ComM channel cycle."""

    rule_id: ClassVar[str] = "ECUM-AP-001"
    severity_default: ClassVar[str] = LintSeverity.ERROR
    applies_to: ClassVar[str] = "arxml"  # 只吃 ArxmlLintData

    _ECUM_COMM_PARAMS: ClassVar[tuple[str, ...]] = (
        "EcuMComMChannels",
        "EcuMComMNetworkHandle",
    )

    def check(
        self, extracted: ArxmlLintData
    ) -> Iterable[LintViolation]:
        # v1 MVP stub：key_params 没拆 EcuMComMChannels 引用图
        # → 不 yield（FP=0 优先）
        for _p in extracted.key_params:
            if _p.get("name") in self._ECUM_COMM_PARAMS:
                return ()
        return ()
