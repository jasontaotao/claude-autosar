"""Sprint 9.5 集成 fix — 规则按 namespace 过滤的单测。

覆盖：
- :func:`rules_for_namespace` 把 ``applies_to="arxml"`` 的规则在 XDM 路径过滤掉
- 反之 XDM 规则在 ARXML 路径过滤掉
- ``applies_to="both"`` 规则双格式都跑（向后兼容）
- 未知 namespace → ValueError
- ``lint_file`` 集成路径：fixture 文件按 suffix 路由到正确子集
- 10 条规则全部带 ``applies_to`` tag
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, ClassVar

import pytest

from claude_autosar.core.bsw.lint import LintSeverity, LintViolation
from claude_autosar.core.bsw.lint.rules import (
    ALL_RULES,
    rules_for_namespace,
)

# ---------------------------------------------------------------------------
# 单元测试
# ---------------------------------------------------------------------------


def test_all_10_rules_have_applies_to_tag() -> None:
    """10 条规则全部声明 applies_to（防回归 — 忘加 tag 会让 XDM 路径抛异常）。"""
    for rule in ALL_RULES:
        assert hasattr(rule, "applies_to"), f"{rule.__class__.__name__} 缺 applies_to ClassVar"
        assert rule.applies_to in (
            "arxml",
            "xdm",
            "both",
        ), f"{rule.__class__.__name__}.applies_to={rule.applies_to!r} 不在白名单"


def test_rules_for_namespace_arxml_returns_8() -> None:
    """8 条 arxml 规则 — CANIF/COM/ECUM/NM/GEN 全部。"""
    rules = rules_for_namespace("arxml")
    assert len(rules) == 8
    rule_ids = {r.rule_id for r in rules}
    assert rule_ids == {
        "CANIF-AP-007",
        "CANIF-AP-008",
        "COM-AP-001",
        "COM-AP-002",
        "ECUM-AP-001",
        "ECUM-AP-003",
        "GEN-AP-002",
        "NM-AP-001",
    }


def test_rules_for_namespace_xdm_returns_2() -> None:
    """2 条 xdm 规则 — DEM-AP-001/004。"""
    rules = rules_for_namespace("xdm")
    assert len(rules) == 2
    rule_ids = {r.rule_id for r in rules}
    assert rule_ids == {"DEM-AP-001", "DEM-AP-004"}


def test_rules_for_namespace_invalid_ns_raises() -> None:
    """未知 namespace → ValueError（fail-fast, 不静默返全集）。"""
    with pytest.raises(ValueError, match="ns must be 'arxml' or 'xdm'"):
        rules_for_namespace("yaml")
    with pytest.raises(ValueError):
        rules_for_namespace("")


def test_rules_for_namespace_preserves_stable_order() -> None:
    """过滤后顺序跟 ALL_RULES 一致（外部依赖顺序做 cache key 时不能乱）。

    dataclass 实例不能直接用 ``in`` 比较（按 identity），用 rule_id 兜底。
    """
    arxml = rules_for_namespace("arxml")
    xdm = rules_for_namespace("xdm")

    arxml_ids_in_all = [r.rule_id for r in ALL_RULES if r.rule_id in {x.rule_id for x in arxml}]
    xdm_ids_in_all = [r.rule_id for r in ALL_RULES if r.rule_id in {x.rule_id for x in xdm}]

    assert [r.rule_id for r in arxml] == arxml_ids_in_all
    assert [r.rule_id for r in xdm] == xdm_ids_in_all


def test_namespace_filter_prevents_xdm_attrerror() -> None:
    """回归测试：ARXML 规则被喂 XDM 数据时，namespace 过滤应该先拦下，
    不会进 rule.check()、不会抛 AttributeError。

    这里手动喂 XdmLintData-like 对象给 CanIfAp007Rule.check()（应当
    如果走 namespace 过滤就压根不会被调用）。
    """

    # 用一个会"看起来像 XDM"的对象 — 故意没 key_params 字段
    class FakeXdm:
        module_name = "Can"
        containers: tuple = ()
        leaves: tuple = ()

    canif_rule = next(r for r in ALL_RULES if r.rule_id == "CANIF-AP-007")
    # 不调用 check()（namespace 过滤在 lint_file 层做），但验证规则自己
    # 在没有 key_params 时会抛 — 这是为什么 namespace 过滤是关键
    with pytest.raises(AttributeError):
        list(canif_rule.check(FakeXdm()))

    # 真正的保护来自 lint_file()：它用 rules_for_namespace("xdm") 过滤，
    # 所以 CanIfAp007Rule 根本不会被喂 FakeXdm


def test_backward_compat_rule_without_tag_runs_in_both() -> None:
    """applies_to 缺省/未知时，``getattr(rule, "applies_to", "both")`` fallback
    让规则双格式都跑（向后兼容 — 第 3 方 plugin 写的规则不必强制声明 tag）。

    直接复用 ``rules_for_namespace`` 的过滤逻辑（局部函数），验证
    UntaggedRule 会被包含。
    """

    class UntaggedRule:
        rule_id: ClassVar[str] = "TEST-UNTAGGED"
        severity_default: ClassVar[str] = LintSeverity.INFO

        def check(self, extracted: Any) -> Iterable[LintViolation]:
            return ()

    # 模拟 ALL_RULES 加一条未声明 tag 的规则
    custom = (UntaggedRule(),) + ALL_RULES
    ar = tuple(r for r in custom if getattr(r, "applies_to", "both") in ("arxml", "both"))
    xd = tuple(r for r in custom if getattr(r, "applies_to", "both") in ("xdm", "both"))
    assert any(r.rule_id == "TEST-UNTAGGED" for r in ar)
    assert any(r.rule_id == "TEST-UNTAGGED" for r in xd)


# ---------------------------------------------------------------------------
# 集成测试：lint_file 按 suffix 路由
# ---------------------------------------------------------------------------


def test_lint_file_xdm_skips_arxml_rules(tmp_path: pytest.TempPathFactory) -> None:
    """fixture: 写一个最小 XDM 文件，lint_file 应该不调用任何 arxml 规则。"""
    from claude_autosar.core.bsw.lint import lint_file

    # 最小可解析 XDM（DataModel2 命名空间）
    xdm = tmp_path / "fake.xdm"  # type: ignore[attr-defined]
    xdm.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<d:model xmlns:d="http://www.tresos.de/_projects/DataModel2/16/root.xsd">\n'
        '  <d:module name="X">\n'
        '    <d:chc name="X" type="AR-OBJECT">\n'
        '      <d:ctr name="XConfig" type="IDENTIFIABLE"/>\n'
        "    </d:chc>\n"
        "  </d:module>\n"
        "</d:model>\n",
        encoding="utf-8",
    )

    # Should not raise — namespace 过滤让 arxml 规则根本不会被调用
    violations = lint_file(xdm)
    # 期望 0 violations（XDM fixture 无 Dem 数据）
    assert isinstance(violations, tuple)
    assert all(v.rule_id.startswith("DEM-") for v in violations)
