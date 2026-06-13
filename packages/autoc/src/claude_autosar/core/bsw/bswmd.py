"""``BSWMDRegistry`` — BSWMD 模板全深度解析 + 多源合并 + lookup API。

Sprint 8.E — T8.E.0b + T8.E.2 合并实现。契约 2 锁定：frozen dataclass 数据模型 +
``load_default(project_config)`` + ``load(paths)`` + ``merge`` + ``lookup_*`` + 容器协议。

加载顺序（D14 决定的 4 级优先级，``load_default``）：
    1. ``<project_root>/.autoc/bswmd/r22/``            # 完整 BSWMD 副本（autoc init 复制的）
    2. ``<project_root>/.prefs/*.arxml``               # EB tresos 工程的精确副本
    3. ``<project_root>/<extra_bswmd_paths>/*/*.arxml``  # 三方 CDD BSWMD
    4. （兜底）``<tresos_home>/BSWMD/AUTOSAR_R22/EcucDefs/``  # EB tresos 安装目录

全深度解析（T8.E.2）：
    - ``<ECUC-MODULE-DEF>`` → ``ModuleDef``（含 containers / params）
    - ``<ECUC-PARAM-CONF-CONTAINER-DEF>`` → ``ContainerDef``（递归 sub_containers）
    - ``<ECUC-*-PARAM-DEF>`` → ``ParamDef``（类型 / min / max / default / multiplicity /
      ENUMERATION 的 symbol_strings）
    - LOWER-MULTIPLICITY 缺省 ``0``；UPPER-MULTIPLICITY 缺省 ``1``，``unbounded`` → ``-1``
    - 跳过 ``<AR-PACKAGE>`` 兄弟节点（即不递归跨包；BSWMD 模板内一个 module 必然在
      根包内）
    - namespace prefix 不敏感（用 localname 匹配；``arx:ECUC-MODULE-DEF`` 和
      ``ECUC-MODULE-DEF`` 等价）

Lookup API（T8.E.2）：
    - ``lookup_param(def_ref_path)`` — 命中 ParamDef 或 None（不抛）
    - ``lookup_container(def_ref_path)`` — 命中 ContainerDef 或 None
    - ``lookup_module(module_name)`` — 命中 ModuleDef 或 None
    - ``__contains__(def_ref_path)`` — 命中 module / container / param 都算 True
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path
from typing import Literal

from lxml import etree

# ProjectConfig 消费契约 1
from claude_autosar.core.config.project_config import ProjectConfig

__all__ = [
    "ParamType",
    "ParamDef",
    "ContainerDef",
    "ModuleDef",
    "BSWMDRegistry",
    "BSWMDError",
]


# =============================================================================
# 类型别名
# =============================================================================


ParamType = Literal["INTEGER", "FLOAT", "STRING", "BOOLEAN", "ENUMERATION", "FUNCTION_NAME"]


# BSWMD 元素 localname 白名单（按 AUTOSAR / EB tresos 标准）
_LOCAL_MODULE_DEF = "ECUC-MODULE-DEF"
_LOCAL_CONTAINER_DEF = "ECUC-PARAM-CONF-CONTAINER-DEF"
_LOCAL_CHOICE_CONTAINER_DEF = "ECUC-CHOICE-CONTAINER-DEF"

# ECUC-*-PARAM-DEF localname → ParamType 映射
_PARAM_TYPE_FROM_LOCAL: dict[str, ParamType] = {
    "ECUC-INTEGER-PARAM-DEF": "INTEGER",
    "ECUC-FLOAT-PARAM-DEF": "FLOAT",
    "ECUC-STRING-PARAM-DEF": "STRING",
    "ECUC-BOOLEAN-PARAM-DEF": "BOOLEAN",
    "ECUC-ENUMERATION-PARAM-DEF": "ENUMERATION",
    "ECUC-FUNCTION-NAME-DEF": "FUNCTION_NAME",
}


# =============================================================================
# 错误类型
# =============================================================================


class BSWMDError(RuntimeError):
    """``BSWMDRegistry`` 加载 / 解析失败。"""


# =============================================================================
# 数据模型（frozen dataclass；契约 2 锁定）
# =============================================================================


@dataclass(frozen=True)
class ParamDef:
    """BSWMD 模板里的单个参数定义（不可变）。

    Attributes:
        short_name: 参数的 SHORT-NAME。
        full_path: DEFINITION-REF 路径（``<AR-PACKAGE>`` 链），例:
            ``/AUTOSAR/Mcu/McuClockSettingConfig/McuClockFrequency``。
        param_type: 类型（``INTEGER`` / ``FLOAT`` / ``STRING`` / ``BOOLEAN`` /
            ``ENUMERATION`` / ``FUNCTION_NAME``）。
        min: 最小值字面量（``None`` = 未指定）。
        max: 最大值字面量（``None`` = 未指定）。
        default: 默认值字面量（``None`` = 未指定）。
        lower_multiplicity: 至少出现次数；缺省 ``0``。
        upper_multiplicity: 最多出现次数；``-1`` = ``unbounded``；缺省 ``1``。
        symbol_strings: ENUMERATION 的合法字面量（仅 ENUMERATION 用）。
    """

    short_name: str
    full_path: str
    param_type: ParamType
    min: str | None = None
    max: str | None = None
    default: str | None = None
    lower_multiplicity: int = 0
    upper_multiplicity: int = 1
    symbol_strings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContainerDef:
    """BSWMD 模板里的单个容器定义（不可变）。

    Attributes:
        short_name: 容器的 SHORT-NAME。
        full_path: DEFINITION-REF 路径。
        lower_multiplicity: 至少出现次数。
        upper_multiplicity: 最多出现次数；``-1`` = ``unbounded``。
        param_defs: 直接子参数定义表（key = SHORT-NAME）。
        sub_container_defs: 直接子容器定义表（key = SHORT-NAME）。
    """

    short_name: str
    full_path: str
    lower_multiplicity: int
    upper_multiplicity: int
    param_defs: dict[str, ParamDef] = field(default_factory=dict)
    sub_container_defs: dict[str, ContainerDef] = field(default_factory=dict)


@dataclass(frozen=True)
class ModuleDef:
    """BSWMD 模板里的单个模块定义（不可变）。

    Attributes:
        short_name: 模块的 SHORT-NAME（如 ``Mcu``）。
        full_path: DEFINITION-REF 路径。
        containers: 子容器定义表（key = SHORT-NAME）。
        params: 顶层参数定义表（key = SHORT-NAME）。
    """

    short_name: str
    full_path: str
    containers: dict[str, ContainerDef] = field(default_factory=dict)
    params: dict[str, ParamDef] = field(default_factory=dict)


@dataclass(frozen=True)
class BSWMDRegistry:
    """BSWMD 解析结果不可变视图；多源加载走 ``.merge()``。

    Attributes:
        modules: 模块定义表（key = 模块 SHORT-NAME）。
        root_package_name: 探测到的 BSWMD 根 ``<AR-PACKAGE>`` SHORT-NAME。
        source_paths: 实际加载的文件路径（用于诊断 / 调试）。
    """

    modules: dict[str, ModuleDef] = field(default_factory=dict)
    root_package_name: str = "AUTOSAR"
    source_paths: tuple[Path, ...] = field(default_factory=tuple)

    # ------------------------------------------------------------------
    # 加载入口
    # ------------------------------------------------------------------

    @classmethod
    def load_default(cls, project_config: ProjectConfig) -> BSWMDRegistry:
        """按 4 级优先级加载（D14 决定）。

        顺序：
            1. ``<project_root>/.autoc/bswmd/r22/``  完整 BSWMD 副本（autoc init 复制的）
            2. ``<project_root>/.prefs/*.arxml``     EB tresos 工程的精确副本
            3. ``<project_root>/<extra_bswmd_paths>/*/*.arxml``  三方 CDD BSWMD
            4. （兜底）``<tresos_home>/BSWMD/AUTOSAR_R22/EcucDefs/``  EB tresos 安装目录

        同名模块后加载覆盖前加载（D11 决定：``/AUTOSAR/`` 与 ``/Vendor/NXP/`` 不冲突）。

        Args:
            project_config: 工程配置（契约 1）。

        Returns:
            合并后的 ``BSWMDRegistry``；没扫到任何文件时返回空 registry（``modules == {}``）。
        """
        logger = logging.getLogger(__name__)

        # 4 级优先级
        candidate_roots: list[Path] = []
        candidate_roots.append(project_config.bswmd_root)
        prefs = project_config.project_root / ".prefs"
        if prefs.is_dir():
            candidate_roots.append(prefs)
        candidate_roots.extend(project_config.extra_bswmd_paths)
        if project_config.tresos_home is not None:
            fallback = project_config.tresos_home / "BSWMD" / "AUTOSAR_R22" / "EcucDefs"
            if fallback.is_dir():
                candidate_roots.append(fallback)

        # 扫每级 root
        merged = BSWMDRegistry()
        for root in candidate_roots:
            if not root.exists():
                logger.debug("BSWMD scan skip (not exists): %s", root)
                continue
            arxml_files = sorted(root.rglob("*.arxml"))
            if not arxml_files:
                logger.debug("BSWMD scan skip (no .arxml): %s", root)
                continue
            logger.info("BSWMD scan: %s -> %d files", root, len(arxml_files))
            for arxml in arxml_files:
                try:
                    single = cls.load((arxml,))
                except (BSWMDError, ValueError, OSError) as exc:
                    logger.warning("BSWMD parse failed: %s (%s)", arxml, exc)
                    continue
                merged = merged.merge(single)

        if not merged.modules:
            logger.info(
                "BSWMDRegistry.load_default: no modules loaded (project_root=%s, tresos_home=%s)",
                project_config.project_root,
                project_config.tresos_home,
            )
        return merged

    @classmethod
    def load(
        cls,
        paths: tuple[Path, ...],
        *,
        nsmap: dict[str, str] | None = None,  # noqa: ARG003 — 保留为 API 一致性
    ) -> BSWMDRegistry:
        """通用加载：单 / 多路径；用 ``lxml.iterparse`` 控内存（D8 决定）。

        解析策略（契约 2 锁定 + plan T8.E.2 RED 段）：
            - ``paths`` 为空 → ``ValueError``
            - 路径不存在 → ``ValueError`` / ``FileNotFoundError``
            - 扫每个 ``<AR-PACKAGE>`` 兄弟节点下的 ``<ECUC-MODULE-DEF>``
            - 每个 module 全深度解析：containers / params / sub_containers
            - namespace prefix 不敏感（用 ``localname`` 匹配）

        Args:
            paths: 一个或多个 ``.arxml`` 路径。
            nsmap: 调用方提供的 namespace 表（仅用于显式控制；
                ``None`` 时走 ``etree.parse`` 自动探测）。

        Returns:
            合并后的 ``BSWMDRegistry``。
        """
        if not paths:
            raise ValueError("BSWMDRegistry.load: paths is empty")

        modules: dict[str, ModuleDef] = {}
        root_pkg_name = "AUTOSAR"
        loaded_sources: list[Path] = []

        for path in paths:
            if not path.exists():
                raise ValueError(f"BSWMD file not found: {path}")
            try:
                tree = etree.parse(str(path))
            except (etree.XMLSyntaxError, OSError) as exc:
                raise BSWMDError(f"failed to parse {path}: {exc}") from exc

            root = tree.getroot()
            if root is None:
                raise BSWMDError(f"empty root in {path}")

            # 探测根 <AR-PACKAGE> SHORT-NAME
            # BSWMD 根结构: <AUTOSAR> → <AR-PACKAGES> → <AR-PACKAGE> 兄弟
            # 我们要的是第一个 <AR-PACKAGE> 的 SHORT-NAME（不是其他兄弟 AR-PACKAGE）
            for elem in root.iter():
                tag = etree.QName(elem.tag).localname
                if tag == "AR-PACKAGE":
                    sn = _find_short_name(elem)
                    if sn:
                        root_pkg_name = sn
                        break

            # 扫所有 <AR-PACKAGE> 兄弟节点（不只根包）→ 收集所有 ECUC-MODULE-DEF
            # plan RED 段要求："扫每个 <AR-PACKAGE> 兄弟节点"（T8.E.2 多包）
            for pkg in _iter_ar_packages(root):
                pkg_root_name = _root_pkg_for_module(pkg, fallback=root_pkg_name)
                # ECUC-MODULE-DEF 在 AR-PACKAGE/ELEMENTS 兄弟节点下（标准 schema）
                for elements_block in _iter_children_by_localname(pkg, "ELEMENTS"):
                    for module_elem in _iter_children_by_localname(
                        elements_block,
                        _LOCAL_MODULE_DEF,
                    ):
                        module = _parse_module_def(
                            module_elem,
                            root_pkg_name=pkg_root_name,
                        )
                        if module is not None:
                            # 同名 module 后加载覆盖前加载（D11）
                            modules[module.short_name] = module
                # 兼容老 schema：ECUC-MODULE-DEF 直接在 AR-PACKAGE 下（罕见）
                for module_elem in _iter_children_by_localname(pkg, _LOCAL_MODULE_DEF):
                    module = _parse_module_def(
                        module_elem,
                        root_pkg_name=pkg_root_name,
                    )
                    if module is not None:
                        modules[module.short_name] = module

            loaded_sources.append(path)

        return BSWMDRegistry(
            modules=modules,
            root_package_name=root_pkg_name,
            source_paths=tuple(loaded_sources),
        )

    # ------------------------------------------------------------------
    # 不可变合并
    # ------------------------------------------------------------------

    def merge(self, other: BSWMDRegistry) -> BSWMDRegistry:
        """不可变合并：``other.modules`` 覆盖 ``self.modules`` 同名 key。

        Args:
            other: 另一个 registry；后加载的赢（D11 决定）。

        Returns:
            新的 ``BSWMDRegistry`` 实例。
        """
        if not isinstance(other, BSWMDRegistry):
            return NotImplemented
        merged_modules: dict[str, ModuleDef] = dict(self.modules)
        for k, v in other.modules.items():
            merged_modules[k] = v
        merged_sources = (*self.source_paths, *other.source_paths)
        # 根包名：other 优先（如果 other 有 modules）
        root_name = other.root_package_name if other.modules else self.root_package_name
        return BSWMDRegistry(
            modules=merged_modules,
            root_package_name=root_name,
            source_paths=merged_sources,
        )

    # ------------------------------------------------------------------
    # Lookup API
    # ------------------------------------------------------------------

    def lookup_param(self, def_ref_path: str) -> ParamDef | None:
        """按 DEFINITION-REF 路径查 ``ParamDef``。

        Args:
            def_ref_path: 形如 ``/AUTOSAR/Mcu/McuClockSettingConfig/McuClockFrequency``。

        Returns:
            命中的 ``ParamDef``；未命中返回 ``None``（不抛，向后兼容）。
        """
        node = self._walk_path(def_ref_path)
        if isinstance(node, ParamDef):
            return node
        return None

    def lookup_container(self, def_ref_path: str) -> ContainerDef | None:
        """按 DEFINITION-REF 路径查 ``ContainerDef``。

        Returns:
            命中的 ``ContainerDef``；未命中返回 ``None``。
        """
        node = self._walk_path(def_ref_path)
        if isinstance(node, ContainerDef):
            return node
        return None

    def lookup_module(self, module_name: str) -> ModuleDef | None:
        """按 SHORT-NAME 查模块。"""
        return self.modules.get(module_name)

    # ------------------------------------------------------------------
    # 容器协议
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self.modules)

    def __contains__(self, def_ref_path: str) -> bool:
        """``def_ref_path in reg`` — 命中 module / container / param 都算 True。

        也兼容老的 ``"Mcu" in reg`` 用法（按 module name 判断）。
        """
        if def_ref_path in self.modules:
            return True
        return self._walk_path(def_ref_path) is not None

    # ------------------------------------------------------------------
    # 内部：路径 walk
    # ------------------------------------------------------------------

    def _walk_path(self, def_ref_path: str) -> ParamDef | ContainerDef | ModuleDef | None:
        """通用 path walk：split + 逐层下钻。

        算法（plan R4.a 锁定）：
            1. ``split('/')`` 去掉空段 → parts
            2. 第一段是 root package（不消费，仅校验或跳过）
            3. 第二段是 module name → ``self.modules[parts[1]]``
            4. 剩余 parts 在 module / container 树中按 SHORT-NAME 逐层下钻
               （container 优先；最后一段可命中 param）
            5. 命中末段时返回 ParamDef / ContainerDef

        返回类型可能为 ParamDef / ContainerDef / ModuleDef；调用方按需 cast。
        """
        if not def_ref_path:
            return None
        parts = [p for p in def_ref_path.split("/") if p]
        if not parts:
            return None

        # 路径首段是根包名（"AUTOSAR" / "Vendor"），从 parts 跳掉
        if parts[0] == self.root_package_name:
            parts = parts[1:]
        # else: 路径首段不是根包 → 整段视为 [module, container..., param]

        if not parts:
            return None

        # 找 module
        module = self.modules.get(parts[0])
        if module is None:
            return None
        if len(parts) == 1:
            return module

        # 剩余在 module 内下钻（module 自身有 containers + 顶层 params）
        current: ModuleDef | ContainerDef | ParamDef = module
        is_last = False
        for i, segment in enumerate(parts[1:], start=1):
            is_last = i == len(parts) - 1
            next_node = _descend(current, segment, prefer_param=is_last)
            if next_node is None:
                return None
            current = next_node
        return current

    # ------------------------------------------------------------------
    # 序列化（调试用）
    # ------------------------------------------------------------------

    def __repr__(self) -> str:  # pragma: no cover — 调试
        return (
            f"BSWMDRegistry(modules={list(self.modules.keys())!r}, "
            f"root_package_name={self.root_package_name!r}, "
            f"source_paths={len(self.source_paths)} files)"
        )


# =============================================================================
# 内部：解析辅助
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
    if param_type == "ENUMERATION":
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
