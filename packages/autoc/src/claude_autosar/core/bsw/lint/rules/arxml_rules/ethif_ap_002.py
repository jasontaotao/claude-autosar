"""ETHIF-AP-002 — EthIfSwitchPortGroup empty but switching enabled.

v2 检测深度：

* 检查 ``key_params`` 里 EthIfSwitchPortGroup 相关参数
* 检查 switch port group 是否有端口条目
* 如果启用 switching 但 port group 为空 → yield violation

v2 增强方向：

* 解析 EthIf 模块下 EthIfSwitchPortGroup 容器
* 检查 port group 的端口条目数量
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class EthIfAp002Rule:
    """ETHIF-AP-002: EthIfSwitchPortGroup empty but switching enabled."""

    rule_id: ClassVar[str] = "ETHIF-AP-002"
    severity_default: ClassVar[str] = LintSeverity.WARNING
    applies_to: ClassVar[str] = "arxml"  # 只吃 ArxmlLintData

    #: EthIf switch 相关参数
    _ETHIF_SWITCH_PARAMS: ClassVar[tuple[str, ...]] = (
        "EthIfSwitchPortGroup",
        "EthIfSwitchEnabled",
        "EthIfSwitchPortRef",
    )

    def check(self, extracted: ArxmlLintData) -> Iterable[LintViolation]:
        # v1 MVP stub：inspector key_params 不含 EthIfSwitchPortGroup 详情
        # 数据不足以做"switching 启用但 port group 为空"判断 → 不 yield（避免误报）
        # v2 增强方向：解析 EthIf 模块下 switch 配置并检查 port group
        for _p in extracted.key_params:
            if _p.get("name") in self._ETHIF_SWITCH_PARAMS:
                # 当前不报（port group 条目不可知）
                return ()
        return ()
