"""BSWMD 参数覆盖率报告。

Sprint 10 — T10.5。对比 BSWMD 定义的参数集合和已配置的参数集合，
输出每个模块的覆盖率。

设计：
- 纯函数，无副作用
- 输入：ECUCDocument + BSWMDRegistry
- 输出：CoverageReport（不可变 frozen dataclass）

HIGH-6 修复：将每个已配置 instance path 映射到 definition path（去掉实例下标
+ 加 root package 前缀），按完整 definition path 比较而非仅 short_name。
旧实现 ``parts[-1]`` 在 ``McuGeneral/Timeout`` 与 ``McuClockSettingConfig/Timeout``
这种同名 param 场景下会误报两 param 都已配。
"""

from __future__ import annotations

from dataclasses import dataclass

from claude_autosar.core.bsw.bsw_write_path import ecuc_path_to_def_ref
from claude_autosar.core.bsw.bswmd import BSWMDRegistry
from claude_autosar.core.bsw.ecuc import ECUCDocument


@dataclass(frozen=True)
class CoverageReport:
    """单个模块的参数覆盖率报告。"""

    module: str
    """模块名"""
    total_params: int
    """BSWMD 定义的参数总数"""
    configured_params: int
    """已配置的参数数"""
    missing_params: tuple[str, ...]
    """未配置的参数名列表"""
    coverage_pct: float
    """覆盖率百分比（0-100）"""


def compute_coverage(
    doc: ECUCDocument,
    bswmd_registry: BSWMDRegistry,
) -> CoverageReport:
    """计算单个模块的参数覆盖率。

    算法：
    1. 从 BSWMDRegistry 获取模块定义的所有参数路径（full_path）
    2. 从 ECUCDocument 获取已配置的参数路径（去重后的路径前缀）
    3. 对比两者，计算 missing = bswmd_params - configured_params

    Args:
        doc: 已加载的 ECUCDocument。
        bswmd_registry: BSWMD 注册表。

    Returns:
        CoverageReport 包含覆盖率统计。
    """
    module_def = bswmd_registry.lookup_module(doc.module_name)

    # BSWMD 中没有该模块定义 → 返回空报告
    if module_def is None:
        return CoverageReport(
            module=doc.module_name,
            total_params=0,
            configured_params=0,
            missing_params=(),
            coverage_pct=100.0,
        )

    # 收集 BSWMD 定义的所有参数 full_path
    bswmd_param_paths: set[str] = set()
    _collect_param_paths(module_def, bswmd_param_paths)

    if not bswmd_param_paths:
        return CoverageReport(
            module=doc.module_name,
            total_params=0,
            configured_params=0,
            missing_params=(),
            coverage_pct=100.0,
        )

    # 收集 ECUCDocument 中已配置的参数路径（按 definition path 匹配）
    # HIGH-6 修复：将 instance 路径映射到 definition 路径后比较
    configured_def_paths: set[str] = set()
    for v in doc.values:
        def_ref = ecuc_path_to_def_ref(v.path, bswmd_registry.root_package_name)
        configured_def_paths.add(def_ref)

    # 对比：BSWMD 参数的 full_path 是否在已配置的 def_path 集合中
    missing: list[str] = []
    configured_count = 0
    for param_path in sorted(bswmd_param_paths):
        if param_path in configured_def_paths:
            configured_count += 1
        else:
            missing.append(param_path)

    total = len(bswmd_param_paths)
    pct = (configured_count / total * 100.0) if total > 0 else 100.0

    return CoverageReport(
        module=doc.module_name,
        total_params=total,
        configured_params=configured_count,
        missing_params=tuple(missing),
        coverage_pct=round(pct, 2),
    )


def _collect_param_paths(
    node: object,
    out: set[str],
) -> None:
    """递归收集 ContainerDef / ModuleDef 下的所有 ParamDef full_path。"""
    from claude_autosar.core.bsw.bswmd import ContainerDef, ModuleDef, ParamDef

    if isinstance(node, ModuleDef):
        for param in node.params.values():
            out.add(param.full_path)
        for container in node.containers.values():
            _collect_param_paths(container, out)
    elif isinstance(node, ContainerDef):
        for param in node.param_defs.values():
            out.add(param.full_path)
        for sub in node.sub_container_defs.values():
            _collect_param_paths(sub, out)
