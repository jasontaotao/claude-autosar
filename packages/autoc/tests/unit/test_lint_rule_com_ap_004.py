"""v2.4.1 — COM-AP-004 单测。

Duplicate ComIPdu handle IDs → ERROR。
"""

from __future__ import annotations

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
)
from claude_autosar.core.bsw.lint.rules.arxml_rules.com_ap_004 import ComAp004Rule


def _mk_data(
    ipdus: tuple[dict, ...] = (),
    module_name: str = "Com",
) -> ArxmlLintData:
    return ArxmlLintData(
        module_name=module_name,
        ipdus=ipdus,
        signals_by_ipdu={},
        key_params=(),
    )


class TestComAp004Rule:
    def test_unique_handle_ids_no_violation(self) -> None:
        """唯一 handle ID → 不报。"""
        data = _mk_data(
            ipdus=(
                {"name": "PduA", "ComIPduHandleId": "1"},
                {"name": "PduB", "ComIPduHandleId": "2"},
            )
        )
        assert list(ComAp004Rule().check(data)) == []

    def test_duplicate_handle_ids_fails(self) -> None:
        """重复 handle ID → ERROR。"""
        data = _mk_data(
            ipdus=(
                {"name": "PduA", "ComIPduHandleId": "1"},
                {"name": "PduB", "ComIPduHandleId": "1"},
            )
        )
        v = list(ComAp004Rule().check(data))
        assert len(v) == 1
        assert v[0].rule_id == "COM-AP-004"
        assert v[0].severity == LintSeverity.ERROR
        assert "PduA" in v[0].message
        assert v[0].suggestion is not None

    def test_missing_handle_id_skipped(self) -> None:
        """缺少 handle ID → skip（不误报）。"""
        data = _mk_data(
            ipdus=(
                {"name": "PduA"},
                {"name": "PduB", "ComIPduHandleId": "1"},
            )
        )
        assert list(ComAp004Rule().check(data)) == []

    def test_empty_ipdus_no_violation(self) -> None:
        """无 IPdu → 不报。"""
        data = _mk_data()
        assert list(ComAp004Rule().check(data)) == []

    def test_rule_metadata(self) -> None:
        rule = ComAp004Rule()
        assert rule.rule_id == "COM-AP-004"
        assert rule.severity_default == LintSeverity.ERROR
        assert rule.applies_to == "arxml"
