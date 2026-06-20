"""Unit tests for packages/autoc/src/claude_autosar/cli/mcp_tools/diff_ops.py.

Sprint 11 — T11.1。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_autosar.cli.mcp_tools.diff_ops import bsw_diff

pytestmark = pytest.mark.unit


_MCU_V1 = """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES><AR-PACKAGE><SHORT-NAME>B</SHORT-NAME><ELEMENTS>
    <ECUC-MODULE-CONFIGURATION-VALUES>
      <SHORT-NAME>Mcu</SHORT-NAME>
      <CONTAINERS>
        <ECUC-PARAM-CONF-CONTAINER>
          <SHORT-NAME>Root</SHORT-NAME>
          <PARAMETER-VALUES>
            <ECUC-NUMERICAL-PARAM-VALUE>
              <DEFINITION-REF DEST="ECUC-INTEGER-PARAM-DEF">/Mcu/Root/ClockFreq</DEFINITION-REF>
              <VALUE>80000000</VALUE>
            </ECUC-NUMERICAL-PARAM-VALUE>
          </PARAMETER-VALUES>
        </ECUC-PARAM-CONF-CONTAINER>
      </CONTAINERS>
    </ECUC-MODULE-CONFIGURATION-VALUES>
  </ELEMENTS></AR-PACKAGE></AR-PACKAGES>
</AUTOSAR>
"""

_MCU_V2 = """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES><AR-PACKAGE><SHORT-NAME>B</SHORT-NAME><ELEMENTS>
    <ECUC-MODULE-CONFIGURATION-VALUES>
      <SHORT-NAME>Mcu</SHORT-NAME>
      <CONTAINERS>
        <ECUC-PARAM-CONF-CONTAINER>
          <SHORT-NAME>Root</SHORT-NAME>
          <PARAMETER-VALUES>
            <ECUC-NUMERICAL-PARAM-VALUE>
              <DEFINITION-REF DEST="ECUC-INTEGER-PARAM-DEF">/Mcu/Root/ClockFreq</DEFINITION-REF>
              <VALUE>120000000</VALUE>
            </ECUC-NUMERICAL-PARAM-VALUE>
            <ECUC-TEXTUAL-PARAM-VALUE>
              <DEFINITION-REF DEST="ECUC-STRING-PARAM-DEF">/Mcu/Root/ClockName</DEFINITION-REF>
              <VALUE>PLL</VALUE>
            </ECUC-TEXTUAL-PARAM-VALUE>
          </PARAMETER-VALUES>
        </ECUC-PARAM-CONF-CONTAINER>
      </CONTAINERS>
    </ECUC-MODULE-CONFIGURATION-VALUES>
  </ELEMENTS></AR-PACKAGE></AR-PACKAGES>
</AUTOSAR>
"""


class TestBswDiff:
    def test_diff_detects_modify(self, tmp_path: Path) -> None:
        """检测到参数值修改。"""
        f_a = tmp_path / "Mcu_v1.arxml"
        f_a.write_text(_MCU_V1, encoding="utf-8")
        f_b = tmp_path / "Mcu_v2.arxml"
        f_b.write_text(_MCU_V2, encoding="utf-8")

        result = bsw_diff("Mcu", str(f_a), str(f_b), project=str(tmp_path))
        assert result["success"] is True
        assert result["diff_count"] > 0
        # ClockFreq 从 80000000 改为 120000000
        modifies = result["modifies"]
        assert any("ClockFreq" in m["path"] for m in modifies)

    def test_diff_detects_add(self, tmp_path: Path) -> None:
        """检测到新增参数。"""
        f_a = tmp_path / "Mcu_v1.arxml"
        f_a.write_text(_MCU_V1, encoding="utf-8")
        f_b = tmp_path / "Mcu_v2.arxml"
        f_b.write_text(_MCU_V2, encoding="utf-8")

        result = bsw_diff("Mcu", str(f_a), str(f_b), project=str(tmp_path))
        adds = result["adds"]
        assert any("ClockName" in a["path"] for a in adds)

    def test_diff_identical_files(self, tmp_path: Path) -> None:
        """相同文件无 diff。"""
        f = tmp_path / "Mcu.arxml"
        f.write_text(_MCU_V1, encoding="utf-8")

        result = bsw_diff("Mcu", str(f), str(f), project=str(tmp_path))
        assert result["success"] is True
        assert result["diff_count"] == 0

    def test_diff_invalid_module_name(self) -> None:
        """非法模块名返回错误。"""
        result = bsw_diff("../evil", "a.arxml", "b.arxml")
        assert result["success"] is False

    def test_diff_file_not_found(self, tmp_path: Path) -> None:
        """文件不存在返回错误。"""
        result = bsw_diff("Mcu", str(tmp_path / "a.arxml"), str(tmp_path / "b.arxml"))
        assert result["success"] is False
        assert "not found" in result["error"].lower()
