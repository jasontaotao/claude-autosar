"""Unit tests for packages/autoc/src/claude_autosar/core/bsw/xref.py.

TDD 阶段：RED（先写测试）。Sprint 10 — T10.4。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_autosar.core.bsw.ecuc import ECUCDocument, ECUCValue, load_module
from claude_autosar.core.bsw.xref import XrefResult, XrefViolation, check_references

pytestmark = pytest.mark.arxml


# ---------------------------------------------------------------------------
# helpers / fixture
# ---------------------------------------------------------------------------

_MCU_XML = """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>BSW</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-CONFIGURATION-VALUES>
          <SHORT-NAME>Mcu</SHORT-NAME>
          <CONTAINERS>
            <ECUC-PARAM-CONF-CONTAINER>
              <SHORT-NAME>McuClockSettingConfig_0</SHORT-NAME>
              <PARAMETER-VALUES>
                <ECUC-NUMERICAL-PARAM-VALUE>
                  <DEFINITION-REF DEST="ECUC-INTEGER-PARAM-DEF">/Mcu/McuClockFrequency</DEFINITION-REF>
                  <VALUE>80000000</VALUE>
                </ECUC-NUMERICAL-PARAM-VALUE>
              </PARAMETER-VALUES>
              <REFERENCE-VALUES>
                <ECUC-REFERENCE-VALUE>
                  <DEFINITION-REF DEST="ECUC-REFERENCE-DEF">/Mcu/McuClockReferencePoint</DEFINITION-REF>
                  <VALUE-REF DEST="ECUC-PARAM-CONF-CONTAINER">/Port/PortConfig/PortPin_0</VALUE-REF>
                </ECUC-REFERENCE-VALUE>
              </REFERENCE-VALUES>
            </ECUC-PARAM-CONF-CONTAINER>
          </CONTAINERS>
        </ECUC-MODULE-CONFIGURATION-VALUES>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
"""

_PORT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>BSW</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-CONFIGURATION-VALUES>
          <SHORT-NAME>Port</SHORT-NAME>
          <CONTAINERS>
            <ECUC-PARAM-CONF-CONTAINER>
              <SHORT-NAME>PortConfig</SHORT-NAME>
              <SUB-CONTAINERS>
                <ECUC-PARAM-CONF-CONTAINER>
                  <SHORT-NAME>PortPin_0</SHORT-NAME>
                  <PARAMETER-VALUES>
                    <ECUC-NUMERICAL-PARAM-VALUE>
                      <DEFINITION-REF DEST="ECUC-INTEGER-PARAM-DEF">/Port/PortPin/PortPinId</DEFINITION-REF>
                      <VALUE>0</VALUE>
                    </ECUC-NUMERICAL-PARAM-VALUE>
                  </PARAMETER-VALUES>
                </ECUC-PARAM-CONF-CONTAINER>
              </SUB-CONTAINERS>
            </ECUC-PARAM-CONF-CONTAINER>
          </CONTAINERS>
        </ECUC-MODULE-CONFIGURATION-VALUES>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
"""


def _load_docs(tmp_path: Path) -> dict[str, ECUCDocument]:
    """加载 Mcu + Port 两个模块。"""
    mcu_file = tmp_path / "Mcu.xdm"
    mcu_file.write_text(_MCU_XML, encoding="utf-8")
    port_file = tmp_path / "Port.xdm"
    port_file.write_text(_PORT_XML, encoding="utf-8")
    return {
        "Mcu": load_module(mcu_file, "Mcu"),
        "Port": load_module(port_file, "Port"),
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCheckReferences:
    def test_valid_reference_resolves(self, tmp_path: Path) -> None:
        """引用目标存在时，无 violation。"""
        docs = _load_docs(tmp_path)
        result = check_references(docs)
        assert isinstance(result, XrefResult)
        assert result.total_references > 0
        assert result.resolved == result.total_references
        assert len(result.violations) == 0

    def test_dangling_reference_detected(self, tmp_path: Path) -> None:
        """引用目标不存在时，检测到 dangling reference。"""
        docs = _load_docs(tmp_path)
        # 删除 Port 模块 → Mcu 的引用变成 dangling
        del docs["Port"]
        result = check_references(docs)
        assert len(result.violations) > 0
        assert any("PortPin_0" in v.target_ref for v in result.violations)

    def test_no_references_returns_empty(self, tmp_path: Path) -> None:
        """无引用的模块返回空结果。"""
        port_file = tmp_path / "Port.xdm"
        port_file.write_text(_PORT_XML, encoding="utf-8")
        docs = {"Port": load_module(port_file, "Port")}
        result = check_references(docs)
        assert result.total_references == 0
        assert result.resolved == 0
        assert len(result.violations) == 0

    def test_violation_has_source_path(self, tmp_path: Path) -> None:
        """violation 包含引用来源路径。"""
        docs = _load_docs(tmp_path)
        del docs["Port"]
        result = check_references(docs)
        assert len(result.violations) > 0
        v = result.violations[0]
        assert isinstance(v, XrefViolation)
        assert "McuClockReferencePoint" in v.source_path
        assert v.reason  # 非空

    def test_empty_docs(self) -> None:
        """空文档字典返回空结果。"""
        result = check_references({})
        assert result.total_references == 0
        assert result.resolved == 0
        assert len(result.violations) == 0
