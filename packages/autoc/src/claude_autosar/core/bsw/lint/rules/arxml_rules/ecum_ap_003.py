"""ECUM-AP-003 — POSTBUILD variant 缺失 = 出货即返工。

v1 MVP 检测深度：

* 检查 key_params 里是否有 ``EcuMConfigurationId`` / ``EcuMBuildVariant``
* POSTBUILD variant 用 ECUC-POST-BUILD-VARIANT-CONF-CONTAINER 标记
* v1 数据源 key_params 不含 ECUC-POST-BUILD-VARIANT 信息 → 不 yield

v2 增强方向：

* 解析 module 根下所有 container 的 DEFINITION-REF 看是否带
  ``/PostBuild/`` 后缀
"""

from __future__ import annotations

from typing import ClassVar
from collections.abc import Iterable

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class EcuMAp003Rule:
    """ECUM-AP-003: missing POSTBUILD variant."""

    rule_id: ClassVar[str] = "ECUM-AP-003"
    severity_default: ClassVar[str] = LintSeverity.WARNING
    applies_to: ClassVar[str] = "arxml"  # 只吃 ArxmlLintData

    _POSTBUILD_PARAMS: ClassVar[tuple[str, ...]] = (
        "EcuMConfigurationId",
        "EcuMBuildVariant",
    )

    def check(
        self, extracted: ArxmlLintData
    ) -> Iterable[LintViolation]:
        # v1 MVP stub：inspector 没拆 PostBuild variant 标签
        # → 不 yield（FP=0 优先）
        for _p in extracted.key_params:
            if _p.get("name") in self._POSTBUILD_PARAMS:
                return ()
        return ()
