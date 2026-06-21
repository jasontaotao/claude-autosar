"""LintRunner + LintSummary — Sprint 9.4 T9.4-α。

设计要点（plan smooth-spinning-dolphin §4.2）：

* :class:`LintRunner` 接受 ``tuple[LintRule, ...]`` 不可变规则集
* ``run(extracted)`` 顺序遍历每条规则、聚合 violation；任何单条规则抛异常
  会**吞掉**（不破整体）；v1 MVP 简化 — 不做 per-rule 错误统计（plan §10
  风险未单列）
* :class:`LintSummary` 是只读统计视图（errors / warnings / infos + by_rule_id），
  **frozen=True** — 适合做 cache key 或 snapshot
* 不做异步 — lint 是 CPU-bound 但单文件 < 50ms，串行足够
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any

from claude_autosar.core.bsw.lint import LintRule, LintSeverity, LintViolation

__all__ = ["LintRunner", "LintSummary"]


_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 统计视图
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LintSummary:
    """lint 结果统计（frozen — 适合做 snapshot）。

    :param total: 总违规数
    :param errors: ERROR 级别计数
    :param warnings: WARNING 级别计数
    :param infos: INFO 级别计数
    :param by_rule_id: ``{rule_id: count}`` 计数
    :param rule_errors: 执行期间抛异常的规则数
    """

    total: int
    errors: int
    warnings: int
    infos: int
    by_rule_id: dict[str, int] = field(default_factory=dict)
    rule_errors: int = 0


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class LintRunner:
    """不可变规则集的 lint 编排器。

    :param rules: 规则 tuple（顺序 = 执行顺序）；通常来自
                  :data:`claude_autosar.core.bsw.lint.rules.ALL_RULES`
    """

    __slots__ = ("_rules", "_rule_errors")

    def __init__(self, rules: tuple[LintRule, ...]) -> None:
        # 显式转 tuple 防外部 list 突变；不接受 None
        if rules is None:
            raise ValueError("rules must be a tuple, not None")
        self._rules: tuple[LintRule, ...] = tuple(rules)
        self._rule_errors: int = 0

    @property
    def rules(self) -> tuple[LintRule, ...]:
        """暴露只读视图（防外部误改内部状态）。"""
        return self._rules

    def run(self, extracted: Any) -> tuple[LintViolation, ...]:
        """顺序跑每条规则，聚合 violation。

        单条规则抛异常 → 记日志 + 跳过（不破整体）。
        规则返回 generator 也接受 — 用 list 展平。

        :param extracted: ``ArxmlLintData`` / ``XdmLintData``（duck typing）
        :return: (全部 violation tuple, 规则执行异常数)
        """
        all_violations: list[LintViolation] = []
        self._rule_errors = 0
        for rule in self._rules:
            try:
                yielded = rule.check(extracted)
            except Exception as exc:  # noqa: BLE001 — 规则级隔离
                self._rule_errors += 1
                _logger.error(
                    "lint rule %r raised on %r: %s",
                    getattr(rule, "rule_id", "<unknown>"),
                    extracted,
                    exc,
                    exc_info=True,
                )
                continue
            if yielded is None:
                # rule 返回 None（generator function 没 yield / 普通函数忘了 return）
                _logger.warning(
                    "lint rule %r returned None (expected Iterable); skipping",
                    getattr(rule, "rule_id", "<unknown>"),
                )
                continue
            try:
                for v in yielded:
                    if not isinstance(v, LintViolation):
                        _logger.warning(
                            "rule %r yielded non-LintViolation %r",
                            getattr(rule, "rule_id", "<unknown>"),
                            v,
                        )
                        continue
                    all_violations.append(v)
            except Exception as exc:  # noqa: BLE001 — 规则级隔离（generator raise）
                self._rule_errors += 1
                _logger.error(
                    "lint rule %r raised during iteration on %r: %s",
                    getattr(rule, "rule_id", "<unknown>"),
                    extracted,
                    exc,
                    exc_info=True,
                )
        return tuple(all_violations)

    def summarize(self, violations: tuple[LintViolation, ...]) -> LintSummary:
        """把 violation tuple 折成 :class:`LintSummary`。

        :param violations: :meth:`run` 输出
        :return: 统计视图（frozen）
        """
        errors = 0
        warnings = 0
        infos = 0
        by_rule: dict[str, int] = {}
        for v in violations:
            sev = v.severity
            if sev == LintSeverity.ERROR:
                errors += 1
            elif sev == LintSeverity.WARNING:
                warnings += 1
            elif sev == LintSeverity.INFO:
                infos += 1
            else:
                # 未知 severity → 算 error（fail-safe）
                _logger.warning(
                    "unknown severity %r on rule %r; treating as error",
                    sev,
                    v.rule_id,
                )
                errors += 1
            by_rule[v.rule_id] = by_rule.get(v.rule_id, 0) + 1
        return LintSummary(
            total=len(violations),
            errors=errors,
            warnings=warnings,
            infos=infos,
            by_rule_id=by_rule,
            rule_errors=getattr(self, "_rule_errors", 0),
        )
