"""Sprint 9.4 T9.4-α — COM-AP-002 单测。"""

from __future__ import annotations

from claude_autosar.core.bsw.lint import ArxmlLintData, LintSeverity
from claude_autosar.core.bsw.lint.rules.arxml_rules.com_ap_002 import ComAp002Rule


def _mk_data(
    key_params: tuple[dict, ...] = (),
) -> ArxmlLintData:
    return ArxmlLintData(
        module_name="Com",
        ipdus=(),
        signals_by_ipdu={},
        key_params=key_params,
    )


class TestComAp002Rule:
    def test_empty_data_no_violation(self) -> None:
        assert list(ComAp002Rule().check(_mk_data())) == []

    def test_v1_stub_no_violation(self) -> None:
        """v1 即使有 E2E 参数 → 不报（v2 增强方向）"""
        data = _mk_data(
            key_params=({"container": "Com/X", "name": "ComE2EProtectionEnabled", "value": "TRUE"},)
        )
        assert list(ComAp002Rule().check(data)) == []

    def test_rule_metadata(self) -> None:
        rule = ComAp002Rule()
        assert rule.rule_id == "COM-AP-002"
        # COM-AP-002 是 WARNING（plan §4.2 表）
        assert rule.severity_default == LintSeverity.WARNING

    def test_returns_iterable(self) -> None:
        result = ComAp002Rule().check(_mk_data())
        assert result is not None
