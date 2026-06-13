"""Sprint 9.4 T9.4-α — COM-AP-001 单测。

ComSignal > 8 byte 走经典 CAN → ERROR。
"""

from __future__ import annotations


from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
)
from claude_autosar.core.bsw.lint.rules.arxml_rules.com_ap_001 import ComAp001Rule


def _mk_data(
    signals_by_ipdu: dict[str, tuple[dict, ...]] | None = None,
    module_name: str = "Com",
) -> ArxmlLintData:
    return ArxmlLintData(
        module_name=module_name,
        ipdus=(),
        signals_by_ipdu=signals_by_ipdu or {},
        key_params=(),
    )


class TestComAp001Rule:
    def test_signal_length_8_passes(self) -> None:
        """ComSignalLength = 8 → 不报。"""
        data = _mk_data(
            signals_by_ipdu={
                "TxPdu": ({"name": "S1", "ComSignalLength": "8"},),
            }
        )
        rule = ComAp001Rule()
        assert list(rule.check(data)) == []

    def test_signal_length_9_fails(self) -> None:
        """ComSignalLength = 9 → ERROR。"""
        data = _mk_data(
            signals_by_ipdu={
                "TxPdu": ({"name": "S1", "ComSignalLength": "9"},),
            }
        )
        rule = ComAp001Rule()
        v = list(rule.check(data))
        assert len(v) == 1
        assert v[0].rule_id == "COM-AP-001"
        assert v[0].severity == LintSeverity.ERROR
        assert v[0].location == "TxPdu/S1"
        assert v[0].module == "Com"
        assert "9" in v[0].message
        assert v[0].suggestion is not None

    def test_signal_length_16_fails(self) -> None:
        data = _mk_data(
            signals_by_ipdu={
                "TxPdu": ({"name": "BigSig", "ComSignalLength": "16"},),
            }
        )
        v = list(ComAp001Rule().check(data))
        assert len(v) == 1
        assert v[0].message.startswith("ComSignal length 16")

    def test_missing_length_skipped(self) -> None:
        """没 ComSignalLength → skip（不误报）。"""
        data = _mk_data(
            signals_by_ipdu={"TxPdu": ({"name": "S1"},)}
        )
        assert list(ComAp001Rule().check(data)) == []

    def test_non_int_length_skipped(self) -> None:
        """非数字 ComSignalLength → skip。"""
        data = _mk_data(
            signals_by_ipdu={
                "TxPdu": ({"name": "S1", "ComSignalLength": "abc"},)
            }
        )
        assert list(ComAp001Rule().check(data)) == []

    def test_multiple_signals(self) -> None:
        """多 IPdu × 多 signal — 只报 length > 8。"""
        data = _mk_data(
            signals_by_ipdu={
                "PduA": (
                    {"name": "S1", "ComSignalLength": "8"},
                    {"name": "S2", "ComSignalLength": "32"},
                ),
                "PduB": (
                    {"name": "S3", "ComSignalLength": "4"},
                ),
            }
        )
        v = list(ComAp001Rule().check(data))
        assert len(v) == 1
        assert v[0].location == "PduA/S2"

    def test_rule_metadata(self) -> None:
        rule = ComAp001Rule()
        assert rule.rule_id == "COM-AP-001"
        assert rule.severity_default == LintSeverity.ERROR

    def test_iterable_returned(self) -> None:
        data = _mk_data()
        result = ComAp001Rule().check(data)
        # 必须是可迭代（非 None）
        assert result is not None
        # 可以迭代多次 — generator 或 tuple
        assert list(result) == []
