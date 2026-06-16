"""Sprint 9.4 + v2.4.1 — 38 条 lint 规则注册（修正版）。

公共 API：

- :data:`ALL_RULES` — tuple of all 38 rules，按规则 ID 字母序排序
- 单独 import 可用于测试 / 单独启用

v2.4.1 变更：
- 删除 ECUM-AP-005（概念错误，不可静态检测）
- 重写 NM-AP-002（改为 CanNmNodeDetection 检查）
- 重写 PORT-AP-002（改为 output pin 缺少初始值检查）
- 修正 4 条规则的参数名（ECUM-004, NM-003, GEN-003, GEN-004）
- 调整 3 条规则的 severity（CANIF-010, PDUR-002, PORT-001）
"""

from __future__ import annotations

from typing import cast

from claude_autosar.core.bsw.lint import LintRule

# ──────────────────────────────────────────────────────────────
# ArXML 规则（29 条 — 原 8 条 + v2.4.1 新增 21 条）
# ──────────────────────────────────────────────────────────────

# Sprint 9.4 原有
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

# v2.4.1 新增
from claude_autosar.core.bsw.lint.rules.arxml_rules.cantp_ap_001 import CanTpAp001Rule
from claude_autosar.core.bsw.lint.rules.arxml_rules.cantp_ap_002 import CanTpAp002Rule
from claude_autosar.core.bsw.lint.rules.arxml_rules.canif_ap_009 import CanIfAp009Rule
from claude_autosar.core.bsw.lint.rules.arxml_rules.canif_ap_010 import CanIfAp010Rule
from claude_autosar.core.bsw.lint.rules.arxml_rules.com_ap_003 import ComAp003Rule
from claude_autosar.core.bsw.lint.rules.arxml_rules.com_ap_004 import ComAp004Rule
from claude_autosar.core.bsw.lint.rules.arxml_rules.com_ap_005 import ComAp005Rule
from claude_autosar.core.bsw.lint.rules.arxml_rules.dem_ap_002 import DemAp002Rule
from claude_autosar.core.bsw.lint.rules.arxml_rules.dem_ap_003 import DemAp003Rule
from claude_autosar.core.bsw.lint.rules.arxml_rules.ecum_ap_004 import EcuMAp004Rule
from claude_autosar.core.bsw.lint.rules.arxml_rules.ethif_ap_001 import EthIfAp001Rule
from claude_autosar.core.bsw.lint.rules.arxml_rules.ethif_ap_002 import EthIfAp002Rule
from claude_autosar.core.bsw.lint.rules.arxml_rules.frif_ap_001 import FrIfAp001Rule
from claude_autosar.core.bsw.lint.rules.arxml_rules.gen_ap_003 import GenAp003Rule
from claude_autosar.core.bsw.lint.rules.arxml_rules.gen_ap_004 import GenAp004Rule
from claude_autosar.core.bsw.lint.rules.arxml_rules.j1939tp_ap_001 import (
    J1939TpAp001Rule,
)
from claude_autosar.core.bsw.lint.rules.arxml_rules.linif_ap_001 import LinIfAp001Rule
from claude_autosar.core.bsw.lint.rules.arxml_rules.nm_ap_002 import NmAp002Rule
from claude_autosar.core.bsw.lint.rules.arxml_rules.nm_ap_003 import NmAp003Rule
from claude_autosar.core.bsw.lint.rules.arxml_rules.pdur_ap_001 import PduRAp001Rule
from claude_autosar.core.bsw.lint.rules.arxml_rules.pdur_ap_002 import PduRAp002Rule

# ──────────────────────────────────────────────────────────────
# XDM 规则（9 条 — 原 2 条 + v2.4.1 新增 7 条）
# ──────────────────────────────────────────────────────────────

# Sprint 9.4 原有
from claude_autosar.core.bsw.lint.rules.xdm_rules.dem_ap_001 import DemAp001Rule
from claude_autosar.core.bsw.lint.rules.xdm_rules.dem_ap_004 import DemAp004Rule

# v2.4.1 新增
from claude_autosar.core.bsw.lint.rules.xdm_rules.dio_ap_001 import DioAp001Rule
from claude_autosar.core.bsw.lint.rules.xdm_rules.mcu_ap_001 import McuAp001Rule
from claude_autosar.core.bsw.lint.rules.xdm_rules.mcu_ap_002 import McuAp002Rule
from claude_autosar.core.bsw.lint.rules.xdm_rules.port_ap_001 import PortAp001Rule
from claude_autosar.core.bsw.lint.rules.xdm_rules.port_ap_002 import PortAp002Rule
from claude_autosar.core.bsw.lint.rules.xdm_rules.spi_ap_001 import SpiAp001Rule
from claude_autosar.core.bsw.lint.rules.xdm_rules.spi_ap_002 import SpiAp002Rule

__all__ = [
    # arxml — 原有
    "CanIfAp007Rule",
    "CanIfAp008Rule",
    "ComAp001Rule",
    "ComAp002Rule",
    "EcuMAp001Rule",
    "EcuMAp003Rule",
    "GenAp002Rule",
    "NmAp001Rule",
    # arxml — v2.4.1 新增
    "CanTpAp001Rule",
    "CanTpAp002Rule",
    "CanIfAp009Rule",
    "CanIfAp010Rule",
    "ComAp003Rule",
    "ComAp004Rule",
    "ComAp005Rule",
    "DemAp002Rule",
    "DemAp003Rule",
    "EcuMAp004Rule",
    "EthIfAp001Rule",
    "EthIfAp002Rule",
    "FrIfAp001Rule",
    "GenAp003Rule",
    "GenAp004Rule",
    "J1939TpAp001Rule",
    "LinIfAp001Rule",
    "NmAp002Rule",
    "NmAp003Rule",
    "PduRAp001Rule",
    "PduRAp002Rule",
    # xdm — 原有
    "DemAp001Rule",
    "DemAp004Rule",
    # xdm — v2.4.1 新增
    "DioAp001Rule",
    "McuAp001Rule",
    "McuAp002Rule",
    "PortAp001Rule",
    "PortAp002Rule",
    "SpiAp001Rule",
    "SpiAp002Rule",
    "ALL_RULES",
    "rules_for_namespace",
]


#: 全部 38 条规则 tuple — 按 rule_id 字母序（稳定顺序）
ALL_RULES: tuple[LintRule, ...] = cast(
    tuple[LintRule, ...],
    (
        # arxml — 原有
        CanIfAp007Rule(),
        CanIfAp008Rule(),
        CanTpAp001Rule(),
        CanTpAp002Rule(),
        CanIfAp009Rule(),
        CanIfAp010Rule(),
        ComAp001Rule(),
        ComAp002Rule(),
        ComAp003Rule(),
        ComAp004Rule(),
        ComAp005Rule(),
        DemAp001Rule(),
        DemAp002Rule(),
        DemAp003Rule(),
        DemAp004Rule(),
        EcuMAp001Rule(),
        EcuMAp003Rule(),
        EcuMAp004Rule(),
        EthIfAp001Rule(),
        EthIfAp002Rule(),
        FrIfAp001Rule(),
        GenAp002Rule(),
        GenAp003Rule(),
        GenAp004Rule(),
        J1939TpAp001Rule(),
        LinIfAp001Rule(),
        NmAp001Rule(),
        NmAp002Rule(),
        NmAp003Rule(),
        PduRAp001Rule(),
        PduRAp002Rule(),
        # xdm
        DioAp001Rule(),
        McuAp001Rule(),
        McuAp002Rule(),
        PortAp001Rule(),
        PortAp002Rule(),
        SpiAp001Rule(),
        SpiAp002Rule(),
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
