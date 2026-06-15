"""Sprint 9.4 T9.4-α — CANIF-AP-007 单测。

v1 MVP stub — 数据不足时 0 误报。
"""

from __future__ import annotations

from claude_autosar.core.bsw.lint import ArxmlLintData, LintSeverity
from claude_autosar.core.bsw.lint.rules.arxml_rules.canif_ap_007 import (
    CanIfAp007Rule,
)


def _mk_data(
    key_params: tuple[dict, ...] = (),
    module_name: str = "CanIf",
) -> ArxmlLintData:
    return ArxmlLintData(
        module_name=module_name,
        ipdus=(),
        signals_by_ipdu={},
        key_params=key_params,
    )


class TestCanIfAp007Rule:
    def test_empty_data_no_violation(self) -> None:
        data = _mk_data()
        rule = CanIfAp007Rule()
        assert list(rule.check(data)) == []

    def test_with_unrelated_key_params_no_violation(self) -> None:
        """没 CanIf 软件使能参数 → 不报。"""
        data = _mk_data(
            key_params=(
                {"container": "CanIf/CanIfInitCfg", "name": "CanIfMaxRxMailboxCount", "value": "8"},
            )
        )
        assert list(CanIfAp007Rule().check(data)) == []

    def test_with_sw_enable_param_no_violation_in_v1(self) -> None:
        """v1 即使有 software enable 参数，hw count 不可知 → 0 报。"""
        data = _mk_data(
            key_params=(
                {
                    "container": "CanIf/CanIfDispatchCfg",
                    "name": "CanIfTxConfirmationDispatch",
                    "value": "TRUE",
                },
            )
        )
        # v1 MVP stub — FP=0 优先
        assert list(CanIfAp007Rule().check(data)) == []

    def test_rule_metadata(self) -> None:
        rule = CanIfAp007Rule()
        assert rule.rule_id == "CANIF-AP-007"
        assert rule.severity_default == LintSeverity.ERROR

    def test_returns_iterable(self) -> None:
        result = CanIfAp007Rule().check(_mk_data())
        assert result is not None
        assert list(result) == []
