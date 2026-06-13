"""Sprint 9.4 T9.4-α — NM-AP-001 单测。"""

from __future__ import annotations

from claude_autosar.core.bsw.lint import ArxmlLintData, LintSeverity
from claude_autosar.core.bsw.lint.rules.arxml_rules.nm_ap_001 import NmAp001Rule


def _mk_data(key_params: tuple[dict, ...] = ()) -> ArxmlLintData:
    return ArxmlLintData(
        module_name="CanNm",
        ipdus=(),
        signals_by_ipdu={},
        key_params=key_params,
    )


class TestNmAp001Rule:
    def test_empty_data_no_violation(self) -> None:
        assert list(NmAp001Rule().check(_mk_data())) == []

    def test_v1_stub_no_violation(self) -> None:
        data = _mk_data(
            key_params=(
                {"container": "CanNm/X",
                 "name": "CanNmNodeId",
                 "value": "1"},
            )
        )
        assert list(NmAp001Rule().check(data)) == []

    def test_rule_metadata(self) -> None:
        rule = NmAp001Rule()
        assert rule.rule_id == "NM-AP-001"
        assert rule.severity_default == LintSeverity.ERROR

    def test_returns_iterable(self) -> None:
        result = NmAp001Rule().check(_mk_data())
        assert result is not None
