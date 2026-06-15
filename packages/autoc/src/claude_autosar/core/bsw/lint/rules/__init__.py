"""Sprint 9.4 T9.4-α — 10 条 lint 规则注册。

公共 API：

- :data:`ALL_RULES` — tuple of all 10 rules，按规则 ID 字母序排序
- 单独 import 可用于测试 / 单独启用
"""

from __future__ import annotations

from typing import cast

from claude_autosar.core.bsw.lint import LintRule

# ArXML 规则（8 条 — plan §4.1）
from claude_autosar.core.bsw.lint.rules.arxml_rules.canif_ap_007 import (
    CanIfAp007Rule,
)
from claude_autosar.core.bsw.lint.rules.arxml_rules.canif_ap_008 import (
    CanIfAp008Rule,
)
from claude_autosar.core.bsw.lint.rules.arxml_rules.com_ap_001 import ComAp001Rule
from claude_autosar.core.bsw.lint.rules.arxml_rules.com_ap_002 import ComAp002Rule
from claude_autosar.core.bsw.lint.rules.arxml_rules.ecum_ap_001 import EcuMAp001Rule
from claude_autosar.core.bsw.lint.rules.arxml_rules.ecum_ap_003 import EcuMAp003Rule
from claude_autosar.core.bsw.lint.rules.arxml_rules.gen_ap_002 import GenAp002Rule
from claude_autosar.core.bsw.lint.rules.arxml_rules.nm_ap_001 import NmAp001Rule

# XDM 规则（2 条 — DEM 配置）
from claude_autosar.core.bsw.lint.rules.xdm_rules.dem_ap_001 import DemAp001Rule
from claude_autosar.core.bsw.lint.rules.xdm_rules.dem_ap_004 import DemAp004Rule

__all__ = [
    "ComAp001Rule",
    "CanIfAp007Rule",
    "CanIfAp008Rule",
    "ComAp002Rule",
    "EcuMAp001Rule",
    "EcuMAp003Rule",
    "NmAp001Rule",
    "GenAp002Rule",
    "DemAp001Rule",
    "DemAp004Rule",
    "ALL_RULES",
    "rules_for_namespace",
]


#: 全部 10 条规则 tuple — 按 rule_id 字母序（稳定顺序）
ALL_RULES: tuple[LintRule, ...] = cast(
    tuple[LintRule, ...],
    (
        CanIfAp007Rule(),
        CanIfAp008Rule(),
        ComAp001Rule(),
        ComAp002Rule(),
        DemAp001Rule(),
        DemAp004Rule(),
        EcuMAp001Rule(),
        EcuMAp003Rule(),
        GenAp002Rule(),
        NmAp001Rule(),
    ),
)


def rules_for_namespace(ns: str) -> tuple[LintRule, ...]:
    """按 :attr:`LintRule.applies_to` tag 过滤规则。

    :param ns: ``"arxml"`` / ``"xdm"``；``"both"`` / 未声明 tag 的规则
        在两个 namespace 都会跑（向后兼容）
    :return: 过滤后的规则 tuple（保持 :data:`ALL_RULES` 的稳定顺序）
    :raises ValueError: ns 不是 ``"arxml"`` / ``"xdm"``
    """
    if ns not in ("arxml", "xdm"):
        raise ValueError(f"ns must be 'arxml' or 'xdm', got {ns!r}")
    return tuple(rule for rule in ALL_RULES if getattr(rule, "applies_to", "both") in (ns, "both"))
