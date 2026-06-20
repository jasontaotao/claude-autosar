"""Unit tests for template apply add/delete operations.

Sprint 12 — T12.4。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_autosar.core.bsw.ecuc import ECUCDocument, ECUCValue, load_module
from claude_autosar.core.bsw.templates.apply import ApplyMode, apply_template_diff
from claude_autosar.core.bsw.templates.arxml_diff import (
    TemplateDiff,
    TemplateDiffResult,
)

pytestmark = pytest.mark.arxml


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


class TestApplyAddArxml:
    def test_add_new_param(self, tmp_path: Path) -> None:
        """add op 创建新参数节点。"""
        f = tmp_path / "Mcu.arxml"
        f.write_text(_MCU_V1, encoding="utf-8")

        diff = TemplateDiffResult(
            module_name="Mcu",
            diffs=(
                TemplateDiff(
                    path="Mcu/Root/ClockName",
                    current=None,
                    template=ECUCValue(path="Mcu/Root/ClockName", raw="PLL", type="STRING"),
                    op="add",
                ),
            ),
        )

        result = apply_template_diff(f, diff, mode=ApplyMode.APPLY)
        assert result.diffs_applied == 1

        # 验证新参数已添加
        doc = load_module(f, "Mcu")
        val = None
        for v in doc.values:
            if "ClockName" in v.path:
                val = v
                break
        assert val is not None
        assert val.raw == "PLL"


class TestApplyDeleteArxml:
    def test_delete_existing_param(self, tmp_path: Path) -> None:
        """delete op 删除现有参数节点。"""
        f = tmp_path / "Mcu.arxml"
        f.write_text(_MCU_V1, encoding="utf-8")

        diff = TemplateDiffResult(
            module_name="Mcu",
            diffs=(
                TemplateDiff(
                    path="Mcu/Root/ClockFreq",
                    current=ECUCValue(path="Mcu/Root/ClockFreq", raw="80000000", type="INTEGER"),
                    template=None,
                    op="delete",
                ),
            ),
        )

        result = apply_template_diff(f, diff, mode=ApplyMode.APPLY)
        assert result.diffs_applied == 1

        # 验证参数已删除
        doc = load_module(f, "Mcu")
        for v in doc.values:
            assert "ClockFreq" not in v.path, f"ClockFreq should be deleted but found: {v.path}"


class TestApplyMixedOps:
    def test_modify_and_add(self, tmp_path: Path) -> None:
        """同时 modify 和 add。"""
        f = tmp_path / "Mcu.arxml"
        f.write_text(_MCU_V1, encoding="utf-8")

        diff = TemplateDiffResult(
            module_name="Mcu",
            diffs=(
                TemplateDiff(
                    path="Mcu/Root/ClockFreq",
                    current=ECUCValue(path="Mcu/Root/ClockFreq", raw="80000000", type="INTEGER"),
                    template=ECUCValue(path="Mcu/Root/ClockFreq", raw="120000000", type="INTEGER"),
                    op="modify",
                ),
                TemplateDiff(
                    path="Mcu/Root/ClockName",
                    current=None,
                    template=ECUCValue(path="Mcu/Root/ClockName", raw="PLL", type="STRING"),
                    op="add",
                ),
            ),
        )

        result = apply_template_diff(f, diff, mode=ApplyMode.APPLY)
        assert result.diffs_applied == 2

        # 验证 modify
        doc = load_module(f, "Mcu")
        for v in doc.values:
            if "ClockFreq" in v.path:
                assert v.raw == "120000000"

        # 验证 add
        for v in doc.values:
            if "ClockName" in v.path:
                assert v.raw == "PLL"
