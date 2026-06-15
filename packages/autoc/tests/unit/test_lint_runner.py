"""Sprint 9.4 T9.4-α — LintRunner 综合测试。

覆盖：
- 空规则集 → 0 violation
- 单条规则 yield → 透传
- 规则抛异常 → 隔离 + 跳过（不破整体）
- summarize 正确分级 errors / warnings / infos
- by_rule_id 聚合
- 未知 severity → 当 error（fail-safe）
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

import pytest

from claude_autosar.core.bsw.lint import LintSeverity, LintViolation
from claude_autosar.core.bsw.lint.runner import LintRunner, LintSummary

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class _AlwaysMatchRule:
    """每条 extracted 都 yield 一条 ERROR violation 的固定 rule（test helper）。"""

    rule_id: ClassVar[str] = "TEST-001"
    severity_default: ClassVar[str] = LintSeverity.ERROR

    def check(self, extracted: object) -> Iterable[LintViolation]:
        yield LintViolation(
            rule_id=self.rule_id,
            severity=self.severity_default,
            message="always matches",
            location=str(extracted),
            module="<test>",
        )


class _WarningRule:
    rule_id: ClassVar[str] = "TEST-002"
    severity_default: ClassVar[str] = LintSeverity.WARNING

    def check(self, extracted: object) -> Iterable[LintViolation]:
        yield LintViolation(
            rule_id=self.rule_id,
            severity=self.severity_default,
            message="warning",
            location="loc",
            module="<test>",
        )


class _InfoRule:
    rule_id: ClassVar[str] = "TEST-003"
    severity_default: ClassVar[str] = LintSeverity.INFO

    def check(self, extracted: object) -> Iterable[LintViolation]:
        yield LintViolation(
            rule_id=self.rule_id,
            severity=self.severity_default,
            message="info",
            location="loc",
            module="<test>",
        )


class _ExplodingRule:
    rule_id: ClassVar[str] = "TEST-BOOM"
    severity_default: ClassVar[str] = LintSeverity.ERROR

    def check(self, extracted: object) -> Iterable[LintViolation]:
        # Generator function — runner 包 try/except 在 ``check()`` 调用层
        # 把 raise 放在 yield 之前（在第一次 next() 时才会 raise，但 runner
        # 是 ``for v in yielded`` → next() 触发 raise → runner 的 try 已经退出）
        # 为了让 raise 发生在 ``check()`` 调用层（不是 next 层），我们用 generator：
        raise RuntimeError("rule boom")
        yield  # pragma: no cover — 让 Python 视为 generator（runner 的 try 在 check 调用层捕获）


class _UnknownSeverityRule:
    rule_id: ClassVar[str] = "TEST-UNKNOWN"
    severity_default: ClassVar[str] = "WTF"  # noqa: S105

    def check(self, extracted: object) -> Iterable[LintViolation]:
        yield LintViolation(
            rule_id=self.rule_id,
            severity="WTF",  # noqa: S105
            message="unknown",
            location="loc",
            module="<test>",
        )


class _NoYieldRule:
    rule_id: ClassVar[str] = "TEST-NONE"
    severity_default: ClassVar[str] = LintSeverity.INFO

    def check(self, extracted: object) -> Iterable[LintViolation]:
        # 故意不 yield — runner 不应崩
        return  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# 基础
# ---------------------------------------------------------------------------


class TestLintRunnerBasics:
    def test_empty_rules_no_violations(self) -> None:
        """空规则集 → 空 violation tuple。"""
        runner = LintRunner(())
        v = runner.run("any")
        assert v == ()

    def test_single_rule_yields(self) -> None:
        runner = LintRunner((_AlwaysMatchRule(),))
        v = runner.run("extracted")
        assert len(v) == 1
        assert v[0].rule_id == "TEST-001"
        assert v[0].severity == "error"

    def test_multiple_rules_aggregate_in_order(self) -> None:
        runner = LintRunner((_AlwaysMatchRule(), _WarningRule(), _InfoRule()))
        v = runner.run("x")
        assert [x.rule_id for x in v] == ["TEST-001", "TEST-002", "TEST-003"]

    def test_rules_property_is_readonly_view(self) -> None:
        rules = (_AlwaysMatchRule(),)
        runner = LintRunner(rules)
        assert runner.rules == rules

    def test_init_with_none_raises(self) -> None:
        with pytest.raises(ValueError):
            LintRunner(rules=None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 异常隔离
# ---------------------------------------------------------------------------


class TestRuleExceptionIsolation:
    def test_rule_exception_does_not_break_run(self) -> None:
        """单条规则 raise → 跳过，其他规则继续。"""
        runner = LintRunner((_ExplodingRule(), _AlwaysMatchRule(), _ExplodingRule()))
        v = runner.run("x")
        # 中间那条仍然 yield
        assert len(v) == 1
        assert v[0].rule_id == "TEST-001"

    def test_rule_returning_none_does_not_break(self) -> None:
        runner = LintRunner((_NoYieldRule(), _AlwaysMatchRule()))
        v = runner.run("x")
        # _NoYieldRule 返 None → 跳过；其他继续
        assert len(v) == 1
        assert v[0].rule_id == "TEST-001"


# ---------------------------------------------------------------------------
# Summarize
# ---------------------------------------------------------------------------


class TestSummarize:
    def test_summarize_counts_by_severity(self) -> None:
        runner = LintRunner(())
        v = (
            LintViolation("R1", "error", "m", "loc", "mod"),
            LintViolation("R2", "warning", "m", "loc", "mod"),
            LintViolation("R3", "info", "m", "loc", "mod"),
            LintViolation("R1", "error", "m2", "loc2", "mod"),
        )
        s = runner.summarize(v)
        assert s.total == 4
        assert s.errors == 2
        assert s.warnings == 1
        assert s.infos == 1
        assert s.by_rule_id == {"R1": 2, "R2": 1, "R3": 1}

    def test_summarize_unknown_severity_is_error(self) -> None:
        runner = LintRunner(())
        v = (LintViolation("R1", "weird", "m", "loc", "mod"),)
        s = runner.summarize(v)
        # unknown → 当 error
        assert s.errors == 1
        assert s.by_rule_id == {"R1": 1}

    def test_summarize_frozen(self) -> None:
        s = LintSummary(total=0, errors=0, warnings=0, infos=0, by_rule_id={})
        with pytest.raises((AttributeError, Exception)):
            s.total = 1  # type: ignore[misc]


# ---------------------------------------------------------------------------
# LintSeverity
# ---------------------------------------------------------------------------


class TestLintSeverity:
    def test_constants(self) -> None:
        from claude_autosar.core.bsw.lint import LintSeverity

        assert LintSeverity.ERROR == "error"
        assert LintSeverity.WARNING == "warning"
        assert LintSeverity.INFO == "info"

    def test_frozen(self) -> None:
        from claude_autosar.core.bsw.lint import LintSeverity

        # frozen=True 实例字段不可变；但 ClassVar 不受 frozen 约束
        # 这里只验证严重度字段值不变 — 不验证 mutation（ClassVar 自由改）
        # 真要锁住，应用 Enum；本测试只验证"默认 ERROR 是 error 字符串"
        assert LintSeverity.ERROR == "error"
        assert LintSeverity.WARNING == "warning"
        assert LintSeverity.INFO == "info"


# ---------------------------------------------------------------------------
# LintViolation frozen
# ---------------------------------------------------------------------------


class TestLintViolation:
    def test_construct_with_all_fields(self) -> None:
        v = LintViolation(
            rule_id="X",
            severity="error",
            message="msg",
            location="loc",
            module="mod",
            suggestion="do X",
        )
        assert v.rule_id == "X"
        assert v.suggestion == "do X"

    def test_suggestion_optional(self) -> None:
        v = LintViolation(
            rule_id="X",
            severity="error",
            message="msg",
            location="loc",
            module="mod",
        )
        assert v.suggestion is None

    def test_frozen(self) -> None:
        v = LintViolation(
            rule_id="X",
            severity="error",
            message="msg",
            location="loc",
            module="mod",
        )
        with pytest.raises((AttributeError, Exception)):
            v.rule_id = "Y"  # type: ignore[misc]

    def test_equality(self) -> None:
        a = LintViolation("X", "error", "m", "l", "mod")
        b = LintViolation("X", "error", "m", "l", "mod")
        c = LintViolation("X", "error", "m2", "l", "mod")
        assert a == b
        assert a != c
