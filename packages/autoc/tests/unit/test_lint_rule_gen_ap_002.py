"""Sprint 9.4 T9.4-α — GEN-AP-002 单测。"""

from __future__ import annotations

from claude_autosar.core.bsw.lint import ArxmlLintData, LintSeverity
from claude_autosar.core.bsw.lint.rules.arxml_rules.gen_ap_002 import GenAp002Rule


def _mk_data(key_params: tuple[dict, ...] = ()) -> ArxmlLintData:
    return ArxmlLintData(
        module_name="BswM",
        ipdus=(),
        signals_by_ipdu={},
        key_params=key_params,
    )


class TestGenAp002Rule:
    def test_empty_data_no_violation(self) -> None:
        assert list(GenAp002Rule().check(_mk_data())) == []

    def test_v1_stub_no_violation(self) -> None:
        data = _mk_data(key_params=({"container": "BswM/X", "name": "BswMRule", "value": "Rule1"},))
        assert list(GenAp002Rule().check(data)) == []

    def test_rule_metadata(self) -> None:
        rule = GenAp002Rule()
        assert rule.rule_id == "GEN-AP-002"
        assert rule.severity_default == LintSeverity.ERROR

    def test_returns_iterable(self) -> None:
        result = GenAp002Rule().check(_mk_data())
        assert result is not None
