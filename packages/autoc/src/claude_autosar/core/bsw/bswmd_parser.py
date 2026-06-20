"""BSWMD XML 解析辅助函数 — 从 ``bswmd.py`` 拆分。

提供 ``<ECUC-MODULE-DEF>`` / ``<ECUC-PARAM-CONF-CONTAINER-DEF>`` /
``<ECUC-*-PARAM-DEF>`` 的 lxml 全深度解析。namespace prefix 不敏感
（用 ``localname`` 匹配）。
"""

from __future__ import annotations

from lxml import etree

from claude_autosar.core.bsw.types import ParamType

# Re-export data classes for type annotations in this module.
# The actual definitions live in bswmd.py; we only need ParamType here.
from claude_autosar.core.bsw.bswmd import (
    ContainerDef,
    ModuleDef,
    ParamDef,
)

__all__ = [
    # 常量
    "LOCAL_MODULE_DEF",
    "LOCAL_CONTAINER_DEF",
    "LOCAL_CHOICE_CONTAINER_DEF",
    "PARAM_TYPE_FROM_LOCAL",
    # 解析辅助
    "_find_short_name",
    "_iter_ar_packages",
    "_iter_children_by_localname",
    "_find_child_by_localname",
    "_get_child_text",
    "_parse_multiplicity",
    "_root_pkg_for_module",
    "_parse_module_def",
    "_parse_module_body",
    "_parse_container_def",
    "_parse_param_def",
    "_descend",
]


# =============================================================================
# BSWMD 元素 localname 白名单
# =============================================================================

LOCAL_MODULE_DEF = "ECUC-MODULE-DEF"
LOCAL_CONTAINER_DEF = "ECUC-PARAM-CONF-CONTAINER-DEF"
LOCAL_CHOICE_CONTAINER_DEF = "ECUC-CHOICE-CONTAINER-DEF"

# 私有别名（保持内部调用点不变）
_LOCAL_MODULE_DEF = LOCAL_MODULE_DEF
_LOCAL_CONTAINER_DEF = LOCAL_CONTAINER_DEF
_LOCAL_CHOICE_CONTAINER_DEF = LOCAL_CHOICE_CONTAINER_DEF

# ECUC-*-PARAM-DEF localname → ParamType 映射
PARAM_TYPE_FROM_LOCAL: dict[str, ParamType] = {
    "ECUC-INTEGER-PARAM-DEF": ParamType.INTEGER,
    "ECUC-FLOAT-PARAM-DEF": ParamType.FLOAT,
    "ECUC-STRING-PARAM-DEF": ParamType.STRING,
    "ECUC-BOOLEAN-PARAM-DEF": ParamType.BOOLEAN,
    "ECUC-ENUMERATION-PARAM-DEF": ParamType.ENUMERATION,
    "ECUC-FUNCTION-NAME-DEF": ParamType.FUNCTION_NAME,
}
_PARAM_TYPE_FROM_LOCAL = PARAM_TYPE_FROM_LOCAL


# =============================================================================
# XML 元素遍历
# =============================================================================


def _find_short_name(elem: etree._Element) -> str | None:
    """从 ECUC 元素的子节点读 ``<SHORT-NAME>`` 文本。

    Args:
        elem: lxml Element。

    Returns:
        SHORT-NAME 文本；缺省或找不到 → ``None``。
    """
    for child in elem:
        if isinstance(child.tag, str) and etree.QName(child.tag).localname == "SHORT-NAME":
            return (child.text or "").strip() or None
    return None


def _iter_ar_packages(root: etree._Element) -> list[etree._Element]:
    """返回 root 下所有 ``<AR-PACKAGE>`` 元素（深度优先）。

    BSWMD 模板结构：``<AUTOSAR> → <AR-PACKAGES> → <AR-PACKAGE> 兄弟节点（可能多层）``。
    我们要解析所有兄弟包（多包 vendor 模板）。
    """
    return [
        e
        for e in root.iter()
        if isinstance(e.tag, str) and etree.QName(e.tag).localname == "AR-PACKAGE"
    ]


def _iter_children_by_localname(
    elem: etree._Element,
    local: str,
) -> list[etree._Element]:
    """返回 elem 的直接子元素中 localname == ``local`` 的列表。"""
    return [c for c in elem if isinstance(c.tag, str) and etree.QName(c.tag).localname == local]


def _find_child_by_localname(
    elem: etree._Element,
    local: str,
) -> etree._Element | None:
    """返回 elem 的直接子元素中 localname == ``local`` 的第一个。"""
    for c in elem:
        if isinstance(c.tag, str) and etree.QName(c.tag).localname == local:
            return c
    return None


def _get_child_text(elem: etree._Element, local: str) -> str | None:
    """取 elem 下第一个 localname == ``local`` 的子元素的文本。"""
    child = _find_child_by_localname(elem, local)
    if child is None:
        return None
    return (child.text or "").strip() or None


# =============================================================================
# Multiplicity 解析
# =============================================================================


def _parse_multiplicity(
    elem: etree._Element,
    *,
    lower_default: int = 0,
    upper_default: int = 1,
) -> tuple[int, int]:
    """从 ``<LOWER-MULTIPLICITY>`` / ``<UPPER-MULTIPLICITY>`` 读整数。

    D5 决定：
        - 缺省 lower=0 / upper=1
        - upper=``"unbounded"`` → ``-1``
        - 任何非整数 upper → 1（容错）

    Returns:
        ``(lower_multiplicity, upper_multiplicity)``
    """
    lower_text = _get_child_text(elem, "LOWER-MULTIPLICITY")
    upper_text = _get_child_text(elem, "UPPER-MULTIPLICITY")

    try:
        lower = int(lower_text) if lower_text is not None else lower_default
    except ValueError:
        lower = lower_default

    if upper_text is None:
        upper = upper_default
    elif upper_text.strip().lower() == "unbounded":
        upper = -1
    else:
        try:
            upper = int(upper_text)
        except ValueError:
            upper = upper_default

    return lower, upper


# =============================================================================
# Module / Container / Param 递归解析
# =============================================================================


def _root_pkg_for_module(
    pkg: etree._Element,
    *,
    fallback: str,
) -> str:
    """取 AR-PACKAGE 的 SHORT-NAME 作为其内部 module 的根包名。"""
    sn = _find_short_name(pkg)
    return sn if sn else fallback


def _parse_module_def(
    elem: etree._Element,
    *,
    root_pkg_name: str,
) -> ModuleDef | None:
    """解析 ``<ECUC-MODULE-DEF>`` 元素为 ``ModuleDef``。"""
    sn = _find_short_name(elem)
    if not sn:
        return None

    full_path = f"/{root_pkg_name}/{sn}"
    containers, params = _parse_module_body(elem, full_path)
    return ModuleDef(
        short_name=sn,
        full_path=full_path,
        containers=containers,
        params=params,
    )


def _parse_module_body(
    elem: etree._Element,
    full_path: str,
) -> tuple[dict[str, ContainerDef], dict[str, ParamDef]]:
    """解析 ``<ECUC-MODULE-DEF>`` 体内的 ``<CONTAINERS>`` 和顶层 ``<PARAMETERS>``。

    BSWMD 模板里 ``<ECUC-MODULE-DEF>`` 的结构可能是：
        - ``<CONTAINERS> → <ECUC-PARAM-CONF-CONTAINER-DEF> 兄弟``
        - ``<CONTAINERS> → <ECUC-CHOICE-CONTAINER-DEF>``（CHOICE 本任务不展开子集，
          但 CHOICE 自身被解析为 ``ContainerDef`` 上层）
        - 顶层 ``<PARAMETERS> → <ECUC-*-PARAM-DEF> 兄弟``
    """
    containers: dict[str, ContainerDef] = {}
    params: dict[str, ParamDef] = {}

    for child in elem:
        if not isinstance(child.tag, str):
            continue
        local = etree.QName(child.tag).localname
        if local == "CONTAINERS":
            for container_elem in child:
                if not isinstance(container_elem.tag, str):
                    continue
                c_local = etree.QName(container_elem.tag).localname
                if c_local in (_LOCAL_CONTAINER_DEF, _LOCAL_CHOICE_CONTAINER_DEF):
                    cd = _parse_container_def(container_elem, full_path)
                    if cd is not None:
                        containers[cd.short_name] = cd
        elif local == "PARAMETERS":
            for param_elem in child:
                if not isinstance(param_elem.tag, str):
                    continue
                p_local = etree.QName(param_elem.tag).localname
                if p_local.endswith("-PARAM-DEF") or p_local == "ECUC-FUNCTION-NAME-DEF":
                    pd = _parse_param_def(param_elem, full_path)
                    if pd is not None:
                        params[pd.short_name] = pd
    return containers, params


def _parse_container_def(
    elem: etree._Element,
    parent_path: str,
) -> ContainerDef | None:
    """递归解析 ``<ECUC-PARAM-CONF-CONTAINER-DEF>`` 元素为 ``ContainerDef``。"""
    sn = _find_short_name(elem)
    if not sn:
        return None
    full_path = f"{parent_path}/{sn}"
    lower, upper = _parse_multiplicity(elem)

    param_defs: dict[str, ParamDef] = {}
    sub_container_defs: dict[str, ContainerDef] = {}

    for child in elem:
        if not isinstance(child.tag, str):
            continue
        local = etree.QName(child.tag).localname
        if local == "PARAMETERS":
            for param_elem in child:
                if not isinstance(param_elem.tag, str):
                    continue
                p_local = etree.QName(param_elem.tag).localname
                if p_local.endswith("-PARAM-DEF") or p_local == "ECUC-FUNCTION-NAME-DEF":
                    pd = _parse_param_def(param_elem, full_path)
                    if pd is not None:
                        param_defs[pd.short_name] = pd
        elif local == "SUB-CONTAINERS":
            for sub_elem in child:
                if not isinstance(sub_elem.tag, str):
                    continue
                s_local = etree.QName(sub_elem.tag).localname
                if s_local in (_LOCAL_CONTAINER_DEF, _LOCAL_CHOICE_CONTAINER_DEF):
                    sub_cd = _parse_container_def(sub_elem, full_path)
                    if sub_cd is not None:
                        sub_container_defs[sub_cd.short_name] = sub_cd
    return ContainerDef(
        short_name=sn,
        full_path=full_path,
        lower_multiplicity=lower,
        upper_multiplicity=upper,
        param_defs=param_defs,
        sub_container_defs=sub_container_defs,
    )


def _parse_param_def(
    elem: etree._Element,
    parent_path: str,
) -> ParamDef | None:
    """解析 ``<ECUC-*-PARAM-DEF>`` 元素为 ``ParamDef``。

    元素类型 → ``param_type`` 的映射见 ``_PARAM_TYPE_FROM_LOCAL``。
    ENUMERATION 解析 ``<LITERALS> → <ECUC-ENUMERATION-LITERAL-DEF> → <SHORT-NAME>``。
    """
    local = etree.QName(elem.tag).localname
    param_type = _PARAM_TYPE_FROM_LOCAL.get(local)
    if param_type is None:
        # 未知 PARAM-DEF 类型 → 跳过（不抛，向后兼容）
        return None

    sn = _find_short_name(elem)
    if not sn:
        return None
    full_path = f"{parent_path}/{sn}"

    min_text = _get_child_text(elem, "MIN")
    max_text = _get_child_text(elem, "MAX")
    default_text: str | None = None
    # <DEFAULT-VALUE> 是 wrapper，<ECUC-NUMERICAL-PARAM-VALUE> 在内
    dv = _find_child_by_localname(elem, "DEFAULT-VALUE")
    if dv is not None:
        for sub in dv:
            if isinstance(sub.tag, str) and etree.QName(sub.tag).localname == "VALUE":
                default_text = (sub.text or "").strip() or None
                break
        if default_text is None:
            # 直接是 ECUC-*-PARAM-VALUE 的 text（少见 schema 变体）
            default_text = (dv.text or "").strip() or None

    lower, upper = _parse_multiplicity(elem)

    symbol_strings: tuple[str, ...] = ()
    if param_type is ParamType.ENUMERATION:
        symbols: list[str] = []
        literals = _find_child_by_localname(elem, "LITERALS")
        if literals is not None:
            for lit in literals:
                if not isinstance(lit.tag, str):
                    continue
                if etree.QName(lit.tag).localname == "ECUC-ENUMERATION-LITERAL-DEF":
                    lit_sn = _find_short_name(lit)
                    if lit_sn:
                        symbols.append(lit_sn)
        symbol_strings = tuple(symbols)

    return ParamDef(
        short_name=sn,
        full_path=full_path,
        param_type=param_type,
        min=min_text,
        max=max_text,
        default=default_text,
        lower_multiplicity=lower,
        upper_multiplicity=upper,
        symbol_strings=symbol_strings,
    )


def _descend(
    node: ModuleDef | ContainerDef | ParamDef,
    short_name: str,
    *,
    prefer_param: bool = False,
) -> ModuleDef | ContainerDef | ParamDef | None:
    """在 module / container / param 内按 SHORT-NAME 找下一个节点。

    ModuleDef：
        - 在 ``containers`` 中找
        - 也可命中顶层 ``params``（BSWMD module 偶尔有顶层 param）
    ContainerDef：
        - 优先在 ``sub_container_defs`` 中找
        - ``prefer_param=True`` 时（如最后一段），可在 ``param_defs`` 中找
    ParamDef：是叶子，return None（不能再下钻）
    """
    if isinstance(node, ModuleDef):
        sub = node.containers.get(short_name)
        if sub is not None:
            return sub
        return node.params.get(short_name)
    if isinstance(node, ContainerDef):
        sub = node.sub_container_defs.get(short_name)
        if sub is not None:
            return sub
        if prefer_param:
            return node.param_defs.get(short_name)
        return None
    # ParamDef is a leaf — can't descend
    return None
