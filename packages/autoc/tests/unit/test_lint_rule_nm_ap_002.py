"""v2.4.1 — NM-AP-002 单测（重写版）。

CanNmNodeDetectionEnabled=true 但无 CanNmNodeIdCallback → WARNING。
"""

from __future__ import annotations

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
)
from claude_autosar.core.bsw.lint.rules.arxml_rules.nm_ap_002 import NmAp002Rule


def _mk_data(
    key_params: tuple[dict, ...] = (),
    module_name: str = "CanNm",
) -> ArxmlLintData:
    return ArxmlLintData(
        module_name=module_name,
        ipdus=(),
        signals_by_ipdu={},
        key_params=key_params,
    )


def _ch_params(enabled: str, callback: str | None = None, ch: str = "Ch1") -> tuple[dict, ...]:
    """构建 CanNm channel 参数。"""
    params = [
        {"container": f"CanNm/{ch}", "name": "CanNmNodeDetectionEnabled", "value": enabled},
    ]
    if callback is not None:
        params.append(
            {"container": f"CanNm/{ch}", "name": "CanNmNodeIdCallback", "value": callback}
        )
    return tuple(params)


class TestNmAp002Rule:
    def test_detection_enabled_no_callback_fails(self) -> None:
        """CanNmNodeDetectionEnabled=true 但无 callback → WARNING。"""
        data = _mk_data(key_params=_ch_params("true"))
        v = list(NmAp002Rule().check(data))
        assert len(v) == 1
        assert v[0].rule_id == "NM-AP-002"
        assert v[0].severity == LintSeverity.WARNING
        assert "CanNmNodeDetectionEnabled" in v[0].message
        assert v[0].suggestion is not None

    def test_detection_enabled_with_callback_passes(self) -> None:
        """CanNmNodeDetectionEnabled=true 且有 callback → 不报。"""
        data = _mk_data(key_params=_ch_params("true", "MyCallback"))
        assert list(NmAp002Rule().check(data)) == []

    def test_detection_disabled_passes(self) -> None:
        """CanNmNodeDetectionEnabled=false → 不报。"""
        data = _mk_data(key_params=_ch_params("false"))
        assert list(NmAp002Rule().check(data)) == []

    def test_no_detection_param_passes(self) -> None:
        """无 CanNmNodeDetectionEnabled 参数 → 不报。"""
        data = _mk_data(key_params=(
            {"container": "CanNm/Ch1", "name": "CanNmNodeId", "value": "0x01"},
        ))
        assert list(NmAp002Rule().check(data)) == []

    def test_empty_key_params_passes(self) -> None:
        assert list(NmAp002Rule().check(_mk_data())) == []

    def test_rule_metadata(self) -> None:
        rule = NmAp002Rule()
        assert rule.rule_id == "NM-AP-002"
        assert rule.severity_default == LintSeverity.WARNING
        assert rule.applies_to == "arxml"
