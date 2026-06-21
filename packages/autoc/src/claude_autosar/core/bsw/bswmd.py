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

解析辅助函数已拆分至 ``bswmd_parser.py``。
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path

from lxml import etree

# ProjectConfig 消费契约 1
from claude_autosar.core.config.project_config import ProjectConfig
from claude_autosar.core.bsw.types import ParamType

__all__ = [
    "ParamType",
    "ParamDef",
    "ContainerDef",
    "ModuleDef",
    "BSWMDRegistry",
    "BSWMDError",
]

# 缓存未命中标记（区分 "缓存了 None" 和 "未缓存"）
_SENTINEL = object()


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

    内部维护 ``_lookup_cache``，缓存 ``_walk_path`` 的结果以避免重复树遍历。
    该字段不参与 __init__ / __repr__ / __eq__，对外完全透明。
    """

    modules: dict[str, ModuleDef] = field(default_factory=dict)
    root_package_name: str = "AUTOSAR"
    source_paths: tuple[Path, ...] = field(default_factory=tuple)
    _lookup_cache: dict[str, ParamDef | ContainerDef | ModuleDef | None] = field(
        init=False, repr=False, compare=False, default_factory=dict
    )

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
                ``None`` 时走 ``_safe_parse`` 自动探测）。

        Returns:
            合并后的 ``BSWMDRegistry``。
        """
        # 延迟导入解析辅助（避免循环依赖；bswmd_parser 在模块级导入本模块数据类）
        from claude_autosar.core.bsw.bswmd_parser import (
            LOCAL_MODULE_DEF,
            _find_short_name,
            _iter_ar_packages,
            _iter_children_by_localname,
            _parse_module_def,
            _root_pkg_for_module,
        )
        from claude_autosar.core.bsw.xml_safe import _safe_parse

        if not paths:
            raise ValueError("BSWMDRegistry.load: paths is empty")

        modules: dict[str, ModuleDef] = {}
        root_pkg_name = "AUTOSAR"
        loaded_sources: list[Path] = []

        for path in paths:
            if not path.exists():
                raise ValueError(f"BSWMD file not found: {path}")
            try:
                tree = _safe_parse(path, recover=False)
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
                        LOCAL_MODULE_DEF,
                    ):
                        module = _parse_module_def(
                            module_elem,
                            root_pkg_name=pkg_root_name,
                        )
                        if module is not None:
                            # 同名 module 后加载覆盖前加载（D11）
                            modules[module.short_name] = module
                # 兼容老 schema：ECUC-MODULE-DEF 直接在 AR-PACKAGE 下（罕见）
                for module_elem in _iter_children_by_localname(pkg, LOCAL_MODULE_DEF):
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
            raise TypeError(f"expected BSWMDRegistry, got {type(other).__name__}")
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
        """通用 path walk：split + 逐层下钻。结果缓存在 ``_lookup_cache``。

        算法（plan R4.a 锁定）：
            1. ``split('/')`` 去掉空段 → parts
            2. 第一段是 root package（不消费，仅校验或跳过）
            3. 第二段是 module name → ``self.modules[parts[1]]``
            4. 剩余 parts 在 module / container 树中按 SHORT-NAME 逐层下钻
               （container 优先；最后一段可命中 param）
            5. 命中末段时返回 ParamDef / ContainerDef

        返回类型可能为 ParamDef / ContainerDef / ModuleDef；调用方按需 cast。
        """
        # 缓存命中 → 直接返回（用 _SENTINEL 区分"缓存了 None"和"未缓存"）
        if def_ref_path in self._lookup_cache:
            return self._lookup_cache[def_ref_path]

        result = self._walk_path_inner(def_ref_path)
        self._lookup_cache[def_ref_path] = result
        return result

    def _walk_path_inner(
        self, def_ref_path: str
    ) -> ParamDef | ContainerDef | ModuleDef | None:
        """实际的 path walk 逻辑（不含缓存）。"""
        # 延迟导入（避免循环依赖）
        from claude_autosar.core.bsw.bswmd_parser import _descend

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
