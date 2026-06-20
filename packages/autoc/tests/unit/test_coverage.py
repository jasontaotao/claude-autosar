"""Unit tests for packages/autoc/src/claude_autosar/core/bsw/coverage.py.

TDD 阶段：RED（先写测试）。Sprint 10 — T10.5。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_autosar.core.bsw.bswmd import (
    BSWMDRegistry,
    ContainerDef,
    ModuleDef,
    ParamDef,
)
from claude_autosar.core.bsw.coverage import CoverageReport, compute_coverage
from claude_autosar.core.bsw.ecuc import ECUCDocument, ECUCValue, load_module

pytestmark = pytest.mark.arxml


# ---------------------------------------------------------------------------
# helpers / fixture
# ---------------------------------------------------------------------------

_MCU_XML = """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES><AR-PACKAGE><SHORT-NAME>BSW</SHORT-NAME><ELEMENTS>
    <ECUC-MODULE-CONFIGURATION-VALUES>
      <SHORT-NAME>Mcu</SHORT-NAME>
      <CONTAINERS>
        <ECUC-PARAM-CONF-CONTAINER>
          <SHORT-NAME>McuClockSettingConfig_0</SHORT-NAME>
          <PARAMETER-VALUES>
            <ECUC-NUMERICAL-PARAM-VALUE>
              <DEFINITION-REF DEST="ECUC-INTEGER-PARAM-DEF">/Mcu/McuClockSettingConfig/McuClockFrequency</DEFINITION-REF>
              <VALUE>80000000</VALUE>
            </ECUC-NUMERICAL-PARAM-VALUE>
            <ECUC-TEXTUAL-PARAM-VALUE>
              <DEFINITION-REF DEST="ECUC-STRING-PARAM-DEF">/Mcu/McuClockSettingConfig/McuClockName</DEFINITION-REF>
              <VALUE>XTAL</VALUE>
            </ECUC-TEXTUAL-PARAM-VALUE>
          </PARAMETER-VALUES>
        </ECUC-PARAM-CONF-CONTAINER>
      </CONTAINERS>
    </ECUC-MODULE-CONFIGURATION-VALUES>
  </ELEMENTS></AR-PACKAGE></AR-PACKAGES>
</AUTOSAR>
"""


def _make_bswmd_registry() -> BSWMDRegistry:
    """创建一个 BSWMD registry，定义 Mcu 模块有 3 个参数。

    HIGH-6 修复：paths 用 ``/AUTOSAR/...`` 前缀，与 BSWMDRegistry 默认
    ``root_package_name="AUTOSAR"`` 一致，使 ``_ecuc_path_to_def_ref`` 转换后能匹配。
    """
    return BSWMDRegistry(
        modules={
            "Mcu": ModuleDef(
                short_name="Mcu",
                full_path="/AUTOSAR/Mcu",
                containers={
                    "McuClockSettingConfig": ContainerDef(
                        short_name="McuClockSettingConfig",
                        full_path="/AUTOSAR/Mcu/McuClockSettingConfig",
                        lower_multiplicity=0,
                        upper_multiplicity=-1,
                        param_defs={
                            "McuClockFrequency": ParamDef(
                                short_name="McuClockFrequency",
                                full_path="/AUTOSAR/Mcu/McuClockSettingConfig/McuClockFrequency",
                                param_type="INTEGER",
                            ),
                            "McuClockName": ParamDef(
                                short_name="McuClockName",
                                full_path="/AUTOSAR/Mcu/McuClockSettingConfig/McuClockName",
                                param_type="STRING",
                            ),
                            "McuClockSource": ParamDef(
                                short_name="McuClockSource",
                                full_path="/AUTOSAR/Mcu/McuClockSettingConfig/McuClockSource",
                                param_type="ENUMERATION",
                            ),
                        },
                    ),
                },
            ),
        },
    )


def _load_mcu_doc(tmp_path: Path) -> ECUCDocument:
    f = tmp_path / "Mcu.xdm"
    f.write_text(_MCU_XML, encoding="utf-8")
    return load_module(f, "Mcu")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestComputeCoverage:
    def test_full_coverage(self, tmp_path: Path) -> None:
        """所有 BSWMD 定义的参数都已配置 → 100%。"""
        doc = _load_mcu_doc(tmp_path)
        # BSWMD 只定义 2 个参数（与 XML 匹配）；paths 用 /AUTOSAR/ 前缀
        reg = BSWMDRegistry(
            modules={
                "Mcu": ModuleDef(
                    short_name="Mcu",
                    full_path="/AUTOSAR/Mcu",
                    containers={
                        "McuClockSettingConfig": ContainerDef(
                            short_name="McuClockSettingConfig",
                            full_path="/AUTOSAR/Mcu/McuClockSettingConfig",
                            lower_multiplicity=0,
                            upper_multiplicity=-1,
                            param_defs={
                                "McuClockFrequency": ParamDef(
                                    short_name="McuClockFrequency",
                                    full_path="/AUTOSAR/Mcu/McuClockSettingConfig/McuClockFrequency",
                                    param_type="INTEGER",
                                ),
                                "McuClockName": ParamDef(
                                    short_name="McuClockName",
                                    full_path="/AUTOSAR/Mcu/McuClockSettingConfig/McuClockName",
                                    param_type="STRING",
                                ),
                            },
                        ),
                    },
                ),
            },
        )
        report = compute_coverage(doc, reg)
        assert isinstance(report, CoverageReport)
        assert report.module == "Mcu"
        assert report.total_params == 2
        assert report.configured_params == 2
        assert report.coverage_pct == 100.0
        assert len(report.missing_params) == 0

    def test_partial_coverage(self, tmp_path: Path) -> None:
        """部分参数未配置 → 按比例。"""
        doc = _load_mcu_doc(tmp_path)
        reg = _make_bswmd_registry()  # 定义 3 个参数，XML 只配了 2 个
        report = compute_coverage(doc, reg)
        assert report.total_params == 3
        assert report.configured_params == 2
        assert abs(report.coverage_pct - 66.67) < 0.1
        # HIGH-6 修复后：missing 元素是完整 definition path（不再是 short_name）
        assert any(
            "McuClockSource" in m for m in report.missing_params
        ), f"McuClockSource expected in {report.missing_params}"

    def test_empty_bswmd(self, tmp_path: Path) -> None:
        """BSWMD 无参数定义 → 100%（无参数可配）。"""
        doc = _load_mcu_doc(tmp_path)
        reg = BSWMDRegistry(modules={})
        report = compute_coverage(doc, reg)
        assert report.total_params == 0
        assert report.coverage_pct == 100.0

    def test_report_is_frozen(self, tmp_path: Path) -> None:
        """CoverageReport 是不可变的。"""
        doc = _load_mcu_doc(tmp_path)
        reg = _make_bswmd_registry()
        report = compute_coverage(doc, reg)
        with pytest.raises(AttributeError):
            report.total_params = 999  # type: ignore[misc]
