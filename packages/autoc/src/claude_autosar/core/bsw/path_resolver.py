"""ECUC 路径 typo 防御 + suggestion。

Sprint 8.E — T8.E.4。契约 4（frozen）：`BSWPathResolver` API。

设计原则：
  - 纯函数 / 静态方法类；不依赖 registry / ProjectConfig / 任何 IO
  - 内部用 `difflib.get_close_matches` 在 typo 时给候选（基于 ECUC 路径表，
    不基于 BSWMD 路径；按 R7 决定）
  - `fuzzy=False` 关闭 fuzzy 匹配（exact-only fast path）
  - `suggest_for_ecuc_set_value_error` 用 `list_paths(doc)` 作 valid_paths
"""

from __future__ import annotations

from dataclasses import dataclass
import difflib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from claude_autosar.core.bsw.ecuc import ECUCDocument


@dataclass(frozen=True)
class ResolverResult:
    """路径解析结果。

    exact: target 是否在 valid_paths 中（精确匹配）
    original: 原始输入（保留大小写 / 分隔符）
    suggestions: typo 时的候选列表（最多 3 个，按相似度降序）
    """

    exact: bool
    original: str
    suggestions: tuple[str, ...] = ()


class BSWPathResolver:
    """BSW/ECUC 路径 typo 防御 resolver（纯静态方法类）。

    用法：
      1. CLI 阶段拿到用户传错的 path → 调 `resolve(target, valid_paths)`
      2. result.suggestions 非空时 stderr 输出 "Did you mean: <s0>, <s1>, ...?"
      3. `suggest_for_ecuc_set_value_error(err_path, doc)` 是快捷方式
    """

    # 阈值常量（与 difflib.SequenceMatcher.ratio() 对齐；0.6 是经验值）
    _MIN_RATIO: float = 0.6

    @staticmethod
    def resolve(
        target: str,
        valid_paths: tuple[str, ...],
        *,
        fuzzy: bool = True,
    ) -> ResolverResult:
        """检查 target 是否在 valid_paths 中；fuzzy=True 时给 typo 候选。

        步骤：
          1. exact = target in valid_paths（O(n) 线性扫；valid_paths 数量 < 1000）
          2. exact 或 fuzzy=False：直接 return
          3. fuzzy=True：调 `difflib.get_close_matches(n=3, cutoff=0.6)`
        """
        if not target:
            return ResolverResult(exact=False, original=target, suggestions=())

        # Step 1: exact match
        for vp in valid_paths:
            if vp == target:
                return ResolverResult(exact=True, original=target, suggestions=())

        # Step 2: fuzzy disabled → fast path
        if not fuzzy:
            return ResolverResult(exact=False, original=target, suggestions=())

        # Step 3: fuzzy match (difflib stdlib)
        matches = difflib.get_close_matches(
            target,
            list(valid_paths),
            n=3,
            cutoff=BSWPathResolver._MIN_RATIO,
        )
        return ResolverResult(
            exact=False,
            original=target,
            suggestions=tuple(matches),
        )

    @staticmethod
    def suggest_for_ecuc_set_value_error(
        err_path: str,
        doc: ECUCDocument,
    ) -> tuple[str, ...]:
        """便利方法：捕获 `ecuc_set_value` 的 ValueError 后用 list_paths(doc) 找候选。

        抛出条件（调用方负责捕获）：`ecuc_set_value(doc, err_path, raw)` 抛
        ValueError "Path ... not in ECUCDocument ..."，调用方拿 err_path
        + 同一 doc 调本方法拿候选。
        """
        from claude_autosar.core.bsw.ecuc import list_paths

        valid_paths = list_paths(doc)
        result = BSWPathResolver.resolve(err_path, valid_paths, fuzzy=True)
        return result.suggestions
