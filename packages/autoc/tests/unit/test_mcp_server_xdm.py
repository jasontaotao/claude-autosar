"""Sprint 9.0 — T9.0.3 unit tests for bsw_read XDM path via dispatcher.

重构 mcp_server.py bsw_read 后：
  - 探测文件根 namespace，自动选 arxml_io / datamodel2_io
  - .xdm → 走 ``_bsw_read_xdm``（扁平 ``<d:var>`` 提取，不走 ECUC walker）
  - 返回值加 ``format`` 字段
"""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_autosar.cli import mcp_server
from claude_autosar.cli.mcp_server import bsw_read


# ---------------------------------------------------------------------------
# Sample XDM payload（与 test_dispatcher 解耦；用真实 EB tresos 风格）
# ---------------------------------------------------------------------------

_SAMPLE_XDM = """<?xml version='1.0' encoding='UTF-8'?>
<datamodel version="7.0"
           xmlns="http://www.tresos.de/_projects/DataModel2/16/root.xsd"
           xmlns:a="http://www.tresos.de/_projects/DataModel2/16/attribute.xsd"
           xmlns:d="http://www.tresos.de/_projects/DataModel2/06/data.xsd">
  <d:ctr type="AUTOSAR" factory="autosar">
    <d:lst type="TOP-LEVEL-PACKAGES">
      <d:ctr name="Mcu" type="AR-PACKAGE">
        <d:lst type="ELEMENTS">
          <d:chc name="Mcu" type="AR-ELEMENT" value="MODULE-CONFIGURATION">
            <d:ctr type="MODULE-CONFIGURATION">
              <d:ctr name="McuClockSettingConfig_0" type="IDENTIFIABLE">
                <d:var name="McuClockFrequency" type="INTEGER" value="80000000"/>
                <d:var name="McuClockReferencePoint" type="ENUMERATION"
                       value="MCU_CLOCK_SOURCE_IRC"/>
              </d:ctr>
              <d:ctr name="McuModuleConfiguration" type="IDENTIFIABLE">
                <d:var name="McuDevErrorDetect" type="BOOLEAN" value="true"/>
              </d:ctr>
            </d:ctr>
          </d:chc>
        </d:lst>
      </d:ctr>
    </d:lst>
  </d:ctr>
</datamodel>
"""


@pytest.fixture
def xdm_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """创建一个含 Mcu.xdm 的 tmp project，绕过 H4 防御。"""
    f = tmp_path / "Mcu.xdm"
    f.write_text(_SAMPLE_XDM, encoding="utf-8")
    # 解除 H4 路径防御
    monkeypatch.setattr(mcp_server, "_ALLOWED_PROJECT_ROOTS", frozenset({tmp_path.resolve()}))
    return tmp_path


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestBswReadXdmHappyPath:
    def test_read_integer_value(self, xdm_project: Path) -> None:
        result = bsw_read("Mcu", "McuClockSettingConfig_0/McuClockFrequency", project=str(xdm_project))
        assert result["success"] is True
        assert result["format"] == "xdm"
        assert result["module"] == "Mcu"
        assert result["raw"] == "80000000"
        assert result["value"] == 80_000_000
        assert result["type"] == "INTEGER"

    def test_read_boolean_value(self, xdm_project: Path) -> None:
        result = bsw_read("Mcu", "McuModuleConfiguration/McuDevErrorDetect", project=str(xdm_project))
        assert result["success"] is True
        assert result["format"] == "xdm"
        assert result["value"] is True
        assert result["type"] == "BOOLEAN"

    def test_read_enumeration_value(self, xdm_project: Path) -> None:
        result = bsw_read("Mcu", "McuClockSettingConfig_0/McuClockReferencePoint", project=str(xdm_project))
        assert result["success"] is True
        assert result["format"] == "xdm"
        assert result["raw"] == "MCU_CLOCK_SOURCE_IRC"
        assert result["value"] == "MCU_CLOCK_SOURCE_IRC"
        assert result["type"] == "ENUMERATION"

    def test_path_with_module_prefix_works(self, xdm_project: Path) -> None:
        """调用方传完整路径 'Mcu/...' 也能命中（不强制要求 prefix）。"""
        result = bsw_read("Mcu", "Mcu/McuClockSettingConfig_0/McuClockFrequency", project=str(xdm_project))
        assert result["success"] is True
        assert result["raw"] == "80000000"


# ---------------------------------------------------------------------------
# 错误路径
# ---------------------------------------------------------------------------


class TestBswReadXdmErrors:
    def test_module_not_found(self, xdm_project: Path) -> None:
        result = bsw_read("Port", "SomePath", project=str(xdm_project))
        # 既不是 .xdm 也不是 .arxml → 走老路径返回 "module not found"
        assert result["success"] is False
        assert "Port" in result["error"]

    def test_path_segment_not_found(self, xdm_project: Path) -> None:
        result = bsw_read("Mcu", "McuClockSettingConfig_0/Nonexistent", project=str(xdm_project))
        assert result["success"] is False
        assert "not in module" in result["error"]
        assert "Nonexistent" in result["error"]

    def test_path_resolves_to_container_not_leaf(self, xdm_project: Path) -> None:
        """指向 d:ctr container 而非 d:var leaf → 友好错误。"""
        result = bsw_read("Mcu", "McuClockSettingConfig_0", project=str(xdm_project))
        assert result["success"] is False
        assert "container" in result["error"].lower() or "leaf" in result["error"].lower()


# ---------------------------------------------------------------------------
# H4 防御 + 既有契约（不 regression）
# ---------------------------------------------------------------------------


class TestBswReadContractPreserved:
    def test_arxml_path_still_uses_ecuc_walker(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """当文件是 .arxml 时，仍走 ecuc.load_module 路径（不 regression v1）。"""
        arxml = """<?xml version='1.0' encoding='UTF-8'?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
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
                  <DEFINITION-REF DEST="ECUC-PARAMETER-DEF">/Mcu/McuClockFrequency</DEFINITION-REF>
                  <VALUE>80000000</VALUE>
                </ECUC-NUMERICAL-PARAM-VALUE>
              </PARAMETER-VALUES>
            </ECUC-PARAM-CONF-CONTAINER>
          </CONTAINERS>
        </ECUC-MODULE-CONFIGURATION-VALUES>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
"""
        f = tmp_path / "Mcu.arxml"
        f.write_text(arxml, encoding="utf-8")
        monkeypatch.setattr(mcp_server, "_ALLOWED_PROJECT_ROOTS", frozenset({tmp_path.resolve()}))
        result = bsw_read("Mcu", "McuClockSettingConfig_0/McuClockFrequency", project=str(tmp_path))
        assert result["success"] is True
        assert result["format"] == "arxml"
        assert result["raw"] == "80000000"

    def test_format_field_always_present_on_success(self, xdm_project: Path) -> None:
        """MCP 契约：成功响应里 format 字段必有（"arxml" 或 "xdm"）。"""
        result = bsw_read("Mcu", "McuClockSettingConfig_0/McuClockFrequency", project=str(xdm_project))
        assert "format" in result
        assert result["format"] in {"arxml", "xdm"}


# ---------------------------------------------------------------------------
# 端到端：plan §0.1 / §3.1 T9.0.3 验收 — 在用户工程 Can.xdm 上能读出
# CanConfigSet 下的值（用 tests/fixtures/datamodel2/Can.xdm 替身）
# ---------------------------------------------------------------------------


class TestBswReadEndToEndCanXdm:
    """plan §0.1 验收：Can.xdm 真实 fixture 走 bsw_read 端到端。"""

    @pytest.fixture
    def can_xdm_project(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        src = Path(__file__).parent.parent / "fixtures" / "datamodel2" / "Can.xdm"
        dst = tmp_path / "Can.xdm"
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        monkeypatch.setattr(mcp_server, "_ALLOWED_PROJECT_ROOTS", frozenset({tmp_path.resolve()}))
        return tmp_path

    def test_read_can_configset_cancontroller_canhwchannel(self, can_xdm_project: Path) -> None:
        """端到端：读 CanConfigSet/CanController/BMS_J1939PT/CanHwChannel → FlexCAN_A"""
        r = bsw_read(
            "Can",
            "CanConfigSet/CanController/BMS_J1939PT/CanHwChannel",
            project=str(can_xdm_project),
        )
        assert r["success"] is True, f"FAIL: {r}"
        assert r["format"] == "xdm"
        assert r["raw"] == "FlexCAN_A"
        assert r["type"] == "ENUMERATION"

    def test_read_can_controller_activation_true(self, can_xdm_project: Path) -> None:
        """端到端：读 CanControllerActivation → true (BOOLEAN)"""
        r = bsw_read(
            "Can",
            "CanConfigSet/CanController/BMS_J1939PT/CanControllerActivation",
            project=str(can_xdm_project),
        )
        assert r["success"] is True
        assert r["value"] is True
        assert r["type"] == "BOOLEAN"

    def test_read_can_list_segment_does_not_break(self, can_xdm_project: Path) -> None:
        """d:lst（list/map of children）段也能下钻 — 用 d:lst / d:ctr 联合 xpath。"""
        # CanController 是 <d:lst name="CanController" type="MAP"> 节点
        # 不在 xpath 里就找不到（这个测试是 v9.0 T9.0.3 实测发现 bug 加的）
        r = bsw_read(
            "Can",
            "CanConfigSet/CanController",
            project=str(can_xdm_project),
        )
        # 路径指向 d:lst container（非 d:var leaf）→ 报"container not leaf"
        assert r["success"] is False
        # 关键是 bsw_read 不抛异常（v1 bsw_read 跑用户工程 XDM 时会抛）
        assert "container" in r["error"].lower() or "leaf" in r["error"].lower()
