"""Unit tests for packages/autoc/src/claude_autosar/cli/mcp_tools/validate_ops.py.

Sprint 10 — T10.6。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from claude_autosar.cli.mcp_tools.validate_ops import bsw_validate

pytestmark = pytest.mark.unit


class TestBswValidate:
    def test_validate_invalid_module_name(self) -> None:
        """非法模块名返回错误。"""
        result = bsw_validate("../evil")
        assert result["success"] is False
        assert "error" in result

    def test_validate_missing_module_file(self, tmp_path: Path) -> None:
        """模块文件不存在返回错误。"""
        result = bsw_validate("NonExistent", project=str(tmp_path))
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_validate_success_with_minimal_arxml(self, tmp_path: Path) -> None:
        """最小 ARXML 文件可正常校验。"""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES><AR-PACKAGE><SHORT-NAME>B</SHORT-NAME><ELEMENTS>
    <ECUC-MODULE-CONFIGURATION-VALUES>
      <SHORT-NAME>Mcu</SHORT-NAME>
      <CONTAINERS>
        <ECUC-PARAM-CONF-CONTAINER>
          <SHORT-NAME>Root</SHORT-NAME>
          <PARAMETER-VALUES>
            <ECUC-NUMERICAL-PARAM-VALUE>
              <DEFINITION-REF DEST="ECUC-INTEGER-PARAM-DEF">/Mcu/Root/Val</DEFINITION-REF>
              <VALUE>42</VALUE>
            </ECUC-NUMERICAL-PARAM-VALUE>
          </PARAMETER-VALUES>
        </ECUC-PARAM-CONF-CONTAINER>
      </CONTAINERS>
    </ECUC-MODULE-CONFIGURATION-VALUES>
  </ELEMENTS></AR-PACKAGE></AR-PACKAGES>
</AUTOSAR>
"""
        f = tmp_path / "Mcu.arxml"
        f.write_text(xml, encoding="utf-8")
        result = bsw_validate("Mcu", project=str(tmp_path))
        assert result["success"] is True
        assert result["module"] == "Mcu"
        assert "lint" in result

    def test_validate_respects_flags(self, tmp_path: Path) -> None:
        """include_lint/coverage/xref 标志可控制。"""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES><AR-PACKAGE><SHORT-NAME>B</SHORT-NAME><ELEMENTS>
    <ECUC-MODULE-CONFIGURATION-VALUES>
      <SHORT-NAME>Mcu</SHORT-NAME>
      <CONTAINERS>
        <ECUC-PARAM-CONF-CONTAINER>
          <SHORT-NAME>Root</SHORT-NAME>
          <PARAMETER-VALUES>
            <ECUC-NUMERICAL-PARAM-VALUE>
              <DEFINITION-REF DEST="ECUC-INTEGER-PARAM-DEF">/Mcu/Root/Val</DEFINITION-REF>
              <VALUE>42</VALUE>
            </ECUC-NUMERICAL-PARAM-VALUE>
          </PARAMETER-VALUES>
        </ECUC-PARAM-CONF-CONTAINER>
      </CONTAINERS>
    </ECUC-MODULE-CONFIGURATION-VALUES>
  </ELEMENTS></AR-PACKAGE></AR-PACKAGES>
</AUTOSAR>
"""
        f = tmp_path / "Mcu.arxml"
        f.write_text(xml, encoding="utf-8")

        # 只跑 lint，不跑 coverage 和 xref
        result = bsw_validate(
            "Mcu",
            project=str(tmp_path),
            include_coverage=False,
            include_xref=False,
        )
        assert result["success"] is True
        assert "lint" in result
        assert "coverage" not in result
        assert "xref" not in result
