"""跨模块引用解析（Cross-Reference Resolver）。

Sprint 10 — T10.4。遍历所有已加载模块的 ECUC-REFERENCE-VALUE，
验证目标容器/参数是否存在，输出 dangling reference 报告。

设计：
- 纯函数，无副作用
- 输入：已加载的 ECUCDocument 字典
- 输出：XrefResult（不可变 frozen dataclass）
"""

from __future__ import annotations

from dataclasses import dataclass

from claude_autosar.core.bsw.ecuc import ECUCDocument, ECUCValue


@dataclass(frozen=True)
class XrefViolation:
    """一条悬空引用记录。"""

    source_path: str
    """引用所在路径（如 Mcu/McuClockSettingConfig_0/McuClockReferencePoint）"""
    target_ref: str
    """VALUE-REF 文本（如 /Port/PortConfig/PortPin_0）"""
    reason: str
    """violation 原因描述"""


@dataclass(frozen=True)
class XrefResult:
    """引用检查结果。"""

    violations: tuple[XrefViolation, ...]
    total_references: int
    resolved: int

    @property
    def dangling(self) -> int:
        """悬空引用数量。"""
        return self.total_references - self.resolved


def check_references(
    docs: dict[str, ECUCDocument],
) -> XrefResult:
    """检查所有模块的引用完整性。

    遍历每个 ECUCDocument 的 values，找到 type=="STRING" 且 raw 以 "/" 开头
    的值（即引用路径），验证目标路径在已加载模块集合中是否存在。

    Args:
        docs: 模块名 → ECUCDocument 的映射。

    Returns:
        XrefResult 包含 violations 列表和统计信息。
    """
    if not docs:
        return XrefResult(violations=(), total_references=0, resolved=0)

    # 构建全局路径集合：所有模块的所有 value path
    all_paths: set[str] = set()
    for doc in docs.values():
        for v in doc.values:
            all_paths.add(v.path)

    violations: list[XrefViolation] = []
    total_refs = 0
    resolved = 0

    for doc in docs.values():
        for v in doc.values:
            if not _is_reference(v):
                continue
            total_refs += 1
            target = v.raw.strip()
            if not target:
                # 空引用 → 视为 dangling
                violations.append(
                    XrefViolation(
                        source_path=v.path,
                        target_ref="",
                        reason="empty reference",
                    )
                )
                continue

            # 尝试多种格式匹配目标：
            # 1. 完整路径（如 /Port/PortConfig/PortPin_0）→ 去掉前导 / 后匹配
            # 2. 短名匹配（如 PortPin_0）→ 在所有路径中搜索
            if _target_exists(target, all_paths, docs):
                resolved += 1
            else:
                violations.append(
                    XrefViolation(
                        source_path=v.path,
                        target_ref=target,
                        reason="target not found in loaded modules",
                    )
                )

    return XrefResult(
        violations=tuple(violations),
        total_references=total_refs,
        resolved=resolved,
    )


def _is_reference(v: ECUCValue) -> bool:
    """判断一个 ECUCValue 是否为引用类型。

    引用特征：type == "STRING" 且 raw 以 "/" 开头（ECUC 路径格式）。
    """
    return v.type == "STRING" and v.raw.startswith("/")


def _target_exists(
    target: str,
    all_paths: set[str],
    docs: dict[str, ECUCDocument],
) -> bool:
    """验证引用目标是否存在。

    匹配策略：
    1. 去掉前导 "/" 后在 all_paths 中查找（如 /Port/PortConfig/PortPin_0 → Port/PortConfig/PortPin_0）
    2. 检查目标路径是否是某个已知路径的前缀（即目标是一个容器，其下有子参数）
    """
    # 策略 1：去掉前导 / 后直接匹配
    stripped = target.lstrip("/")
    if stripped in all_paths:
        return True

    # 策略 2：目标路径是某个已知路径的前缀（容器 → 子参数关系）
    # 例如 /Port/PortConfig/PortPin_0 是 Port/PortConfig/PortPin_0/PortPinId 的前缀
    prefix = stripped + "/"
    for p in all_paths:
        if p.startswith(prefix):
            return True

    return False
