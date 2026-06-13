"""COM-AP-002 — E2E Profile 缺失 → 安全功能降级。

v1 MVP 检测深度：

* 检查 Com module 的 key_params 里是否有 ``ComE2EProtectionEnabled``
  或者 IPdu 上有 E2E 配置
* v1 数据源：inspector key_params（顶层 ComGeneral 等）；E2E 配置
  通常在 IPdu 级别的 ``ComIPdu`` 子节点里 — 现有数据不一定覆盖
* 没数据 → 不报（FP=0 优先）

v2 增强方向：

* 解析 IPdu 子树里的 ``E2EProtectionProps`` / ``ComIPduE2EProtection``
* 区分 safety-relevant IPdu（need E2E）vs 普通 IPdu
"""

from __future__ import annotations

from typing import ClassVar
from collections.abc import Iterable

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class ComAp002Rule:
    """COM-AP-002: safety-relevant ComSignal/ComIPdu missing E2E profile."""

    rule_id: ClassVar[str] = "COM-AP-002"
    severity_default: ClassVar[str] = LintSeverity.WARNING
    applies_to: ClassVar[str] = "arxml"  # 只吃 ArxmlLintData

    _E2E_PARAMS: ClassVar[tuple[str, ...]] = (
        "ComE2EProtectionEnabled",
        "ComIPduE2EProtection",
    )

    def check(
        self, extracted: ArxmlLintData
    ) -> Iterable[LintViolation]:
        # v1 MVP stub：当前 key_params 没拆 E2E 配置 + 无 safety-relevant
        # 标记 → 不 yield
        for _p in extracted.key_params:
            if _p.get("name") in self._E2E_PARAMS:
                return ()
        return ()
