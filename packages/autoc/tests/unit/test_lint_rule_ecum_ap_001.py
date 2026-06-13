"""Sprint 9.4 T9.4-α — ECUM-AP-001 单测。"""

from __future__ import annotations

from claude_autosar.core.bsw.lint import ArxmlLintData, LintSeverity
from claude_autosar.core.bsw.lint.rules.arxml_rules.ecum_ap_001 import EcuMAp001Rule


def _mk_data(key_params: tuple[dict, ...] = ()) -> ArxmlLintData:
    return ArxmlLintData(
        module_name="EcuM",
        ipdus=(),
        signals_by_ipdu={},
        key_params=key_params,
    )


class TestEcuMAp001Rule:
    def test_empty_data_no_violation(self) -> None:
        assert list(EcuMAp001Rule().check(_mk_data())) == []

    def test_v1_stub_no_violation(self) -> None:
        data = _mk_data(
            key_params=(
                {"container": "EcuM/X",
                 "name": "EcuMComMChannels",
                 "value": "CanNetwork"},
            )
        )
        assert list(EcuMAp001Rule().check(data)) == []

    def test_rule_metadata(self) -> None:
        rule = EcuMAp001Rule()
        assert rule.rule_id == "ECUM-AP-001"
        assert rule.severity_default == LintSeverity.ERROR

    def test_returns_iterable(self) -> None:
        result = EcuMAp001Rule().check(_mk_data())
        assert result is not None
