"""Unit tests for packages/autoc/src/autoc/core/bsw/ecuc.py.

TDD 阶段：RED（先写测试）。Sprint 3 — T3.2。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from autoc.core.bsw.arxml_io import ARXMLError
from autoc.core.bsw.bswmd import BSWMDRegistry
from autoc.core.bsw.ecuc import (
    ECUCType,
    get_value,
    list_paths,
    load_module,
    set_value,
)

pytestmark = pytest.mark.arxml


# ---------------------------------------------------------------------------
# helpers / fixture
# ---------------------------------------------------------------------------


_S32K3_MCU_XML = """<?xml version="1.0" encoding="UTF-8"?>
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
                <ECUC-NUMERICAL-PARAM-VALUE>
                  <DEFINITION-REF DEST="ECUC-FLOAT-PARAM-DEF">/Mcu/McuClockTolerance</DEFINITION-REF>
                  <VALUE>0.01</VALUE>
                </ECUC-NUMERICAL-PARAM-VALUE>
                <ECUC-TEXTUAL-PARAM-VALUE>
                  <DEFINITION-REF DEST="ECUC-STRING-PARAM-DEF">/Mcu/McuClockName</DEFINITION-REF>
                  <VALUE>XTAL</VALUE>
                </ECUC-TEXTUAL-PARAM-VALUE>
                <ECUC-NUMERICAL-PARAM-VALUE>
                  <DEFINITION-REF DEST="ECUC-BOOLEAN-PARAM-DEF">/Mcu/McuClockEnabled</DEFINITION-REF>
                  <VALUE>true</VALUE>
                </ECUC-NUMERICAL-PARAM-VALUE>
                <ECUC-TEXTUAL-PARAM-VALUE>
                  <DEFINITION-REF DEST="ECUC-ENUMERATION-PARAM-DEF">/Mcu/McuClockSource</DEFINITION-REF>
                  <VALUE>PLL</VALUE>
                </ECUC-TEXTUAL-PARAM-VALUE>
              </PARAMETER-VALUES>
              <REFERENCE-VALUES>
                <ECUC-REFERENCE-VALUE>
                  <DEFINITION-REF DEST="ECUC-REFERENCE-DEF">/Mcu/McuClockReferencePoint</DEFINITION-REF>
                  <VALUE-REF DEST="ECUC-PARAM-CONF-CONTAINER">/Port/PortConfig/PortPin_0</VALUE-REF>
                </ECUC-REFERENCE-VALUE>
              </REFERENCE-VALUES>
              <SUB-CONTAINERS>
                <ECUC-PARAM-CONF-CONTAINER>
                  <SHORT-NAME>NestedChild</SHORT-NAME>
                  <PARAMETER-VALUES>
                    <ECUC-NUMERICAL-PARAM-VALUE>
                      <DEFINITION-REF DEST="ECUC-INTEGER-PARAM-DEF">/Mcu/NestedChild/Counter</DEFINITION-REF>
                      <VALUE>42</VALUE>
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


def _write_s32k3_mcu(tmp_path: Path) -> Path:
    f = tmp_path / "Mcu.xdm"
    f.write_text(_S32K3_MCU_XML, encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# load_module
# ---------------------------------------------------------------------------


class TestLoadModule:
    def test_load_existing_module(self, tmp_path: Path) -> None:
        f = _write_s32k3_mcu(tmp_path)
        doc = load_module(f, "Mcu")
        assert doc.path == f
        assert doc.module_name == "Mcu"
        assert len(doc.values) > 0

    def test_load_wrong_module_name_raises(self, tmp_path: Path) -> None:
        f = _write_s32k3_mcu(tmp_path)
        with pytest.raises(ValueError, match="Mcu"):
            load_module(f, "Port")

    def test_load_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ARXMLError):
            load_module(tmp_path / "missing.xdm", "Mcu")


# ---------------------------------------------------------------------------
# Type inference
# ---------------------------------------------------------------------------


class TestTypeInference:
    """5 种类型各一例 + 未知 fallback STRING。"""

    @pytest.mark.parametrize(
        ("path_suffix", "expected_type", "expected_raw"),
        [
            ("McuClockFrequency", "INTEGER", "80000000"),
            ("McuClockTolerance", "FLOAT", "0.01"),
            ("McuClockName", "STRING", "XTAL"),
            ("McuClockEnabled", "BOOLEAN", "true"),
            ("McuClockSource", "ENUMERATION", "PLL"),
        ],
    )
    def test_type_inference(
        self,
        tmp_path: Path,
        path_suffix: str,
        expected_type: ECUCType,
        expected_raw: str,
    ) -> None:
        f = _write_s32k3_mcu(tmp_path)
        doc = load_module(f, "Mcu")
        val = get_value(doc, f"Mcu/McuClockSettingConfig_0/{path_suffix}")
        assert val is not None
        assert val.type == expected_type
        assert val.raw == expected_raw

    def test_unknown_definition_ref_falls_back_to_string(self, tmp_path: Path) -> None:
        """未匹配的 DEFINITION-REF 默认 STRING。"""
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
              <DEFINITION-REF DEST="ECUC-CUSTOM-UNKNOWN-TYPE">/Mcu/Root/Custom</DEFINITION-REF>
              <VALUE>hello</VALUE>
            </ECUC-NUMERICAL-PARAM-VALUE>
          </PARAMETER-VALUES>
        </ECUC-PARAM-CONF-CONTAINER>
      </CONTAINERS>
    </ECUC-MODULE-CONFIGURATION-VALUES>
  </ELEMENTS></AR-PACKAGE></AR-PACKAGES>
</AUTOSAR>
"""
        f = tmp_path / "Mcu.xdm"
        f.write_text(xml, encoding="utf-8")
        doc = load_module(f, "Mcu")
        val = get_value(doc, "Mcu/Root/Custom")
        assert val is not None
        assert val.type == "STRING"
        assert val.raw == "hello"

    def test_bswmd_registry_strict_inference(self, tmp_path: Path) -> None:
        """T8.E.2: 传 BSWMDRegistry 时优先按 BSWMD 严格推断（不依赖 DEST）。"""
        from autoc.core.bsw.bswmd import (
            BSWMDRegistry,
            ContainerDef,
            ModuleDef,
            ParamDef,
        )

        # 写一个 DEST 错误但 BSWMD 有正确类型的 xdm
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
              <DEFINITION-REF DEST="ECUC-CUSTOM-WRONG">/Mcu/Root/Mystery</DEFINITION-REF>
              <VALUE>42</VALUE>
            </ECUC-NUMERICAL-PARAM-VALUE>
          </PARAMETER-VALUES>
        </ECUC-PARAM-CONF-CONTAINER>
      </CONTAINERS>
    </ECUC-MODULE-CONFIGURATION-VALUES>
  </ELEMENTS></AR-PACKAGE></AR-PACKAGES>
</AUTOSAR>
"""
        f = tmp_path / "Mcu.xdm"
        f.write_text(xml, encoding="utf-8")

        # BSWMD 声明 Mystery 是 BOOLEAN
        reg = BSWMDRegistry(
            modules={
                "Mcu": ModuleDef(
                    short_name="Mcu",
                    full_path="/B/Mcu",
                    containers={
                        "Root": ContainerDef(
                            short_name="Root",
                            full_path="/B/Mcu/Root",
                            lower_multiplicity=0,
                            upper_multiplicity=1,
                            param_defs={
                                "Mystery": ParamDef(
                                    short_name="Mystery",
                                    full_path="/B/Mcu/Root/Mystery",
                                    param_type="BOOLEAN",
                                ),
                            },
                        ),
                    },
                ),
            },
        )

        # 不传 BSWMDRegistry → 启发式 fallback STRING（dest 不匹配）
        doc_no_bswmd = load_module(f, "Mcu")
        val_no_bswmd = get_value(doc_no_bswmd, "Mcu/Root/Mystery")
        assert val_no_bswmd is not None
        assert val_no_bswmd.type == "STRING"  # fallback

        # 传 BSWMDRegistry → 严格推断 BOOLEAN
        doc_with_bswmd = load_module(f, "Mcu", bswmd_registry=reg)
        val_with_bswmd = get_value(doc_with_bswmd, "Mcu/Root/Mystery")
        assert val_with_bswmd is not None
        assert val_with_bswmd.type == "BOOLEAN"

    def test_bswmd_registry_miss_falls_back_to_dest_heuristic(
        self,
        tmp_path: Path,
    ) -> None:
        """T8.E.2: BSWMD miss 时 fallback 到 DEST 启发式（向后兼容）。"""
        # 用真实 BSWMD 加载（同 _S32K3_MCU_XML fixture）
        f = _write_s32k3_mcu(tmp_path)

        # 空 registry（没有任何 module）→ 全部 fallback
        empty_reg = BSWMDRegistry()
        doc = load_module(f, "Mcu", bswmd_registry=empty_reg)
        val = get_value(doc, "Mcu/McuClockSettingConfig_0/McuClockFrequency")
        assert val is not None
        assert val.type == "INTEGER"  # DEST 启发式（ECUC-INTEGER-PARAM-DEF）


# ---------------------------------------------------------------------------
# Reference value
# ---------------------------------------------------------------------------


class TestReferenceValue:
    def test_reference_value_is_path(self, tmp_path: Path) -> None:
        f = _write_s32k3_mcu(tmp_path)
        doc = load_module(f, "Mcu")
        val = get_value(doc, "Mcu/McuClockSettingConfig_0/McuClockReferencePoint")
        assert val is not None
        # REFERENCE-VALUE 推断为 STRING（值是 ECUC 路径）
        assert val.type == "STRING"
        assert val.raw == "/Port/PortConfig/PortPin_0"


# ---------------------------------------------------------------------------
# Nested containers
# ---------------------------------------------------------------------------


class TestNestedContainers:
    def test_nested_container_value(self, tmp_path: Path) -> None:
        f = _write_s32k3_mcu(tmp_path)
        doc = load_module(f, "Mcu")
        val = get_value(doc, "Mcu/McuClockSettingConfig_0/NestedChild/Counter")
        assert val is not None
        assert val.raw == "42"
        assert val.type == "INTEGER"


# ---------------------------------------------------------------------------
# set_value
# ---------------------------------------------------------------------------


class TestSetValue:
    def test_set_value_returns_new_doc(self, tmp_path: Path) -> None:
        f = _write_s32k3_mcu(tmp_path)
        doc = load_module(f, "Mcu")
        path = "Mcu/McuClockSettingConfig_0/McuClockFrequency"
        new_doc = set_value(doc, path, "120000000")

        # 不可变：新 doc 改变了
        val_new = get_value(new_doc, path)
        assert val_new is not None
        assert val_new.raw == "120000000"

        # 原 doc 不变
        val_old = get_value(doc, path)
        assert val_old is not None
        assert val_old.raw == "80000000"

    def test_set_value_missing_path_raises(self, tmp_path: Path) -> None:
        f = _write_s32k3_mcu(tmp_path)
        doc = load_module(f, "Mcu")
        with pytest.raises(ValueError, match="NONEXISTENT"):
            set_value(doc, "Mcu/McuClockSettingConfig_0/NONEXISTENT", "0")

    def test_set_value_preserves_other_values(self, tmp_path: Path) -> None:
        f = _write_s32k3_mcu(tmp_path)
        doc = load_module(f, "Mcu")
        new_doc = set_value(doc, "Mcu/McuClockSettingConfig_0/McuClockFrequency", "999")
        # 其他值没变
        other = get_value(new_doc, "Mcu/McuClockSettingConfig_0/McuClockName")
        assert other is not None
        assert other.raw == "XTAL"


# ---------------------------------------------------------------------------
# list_paths
# ---------------------------------------------------------------------------


class TestListPaths:
    def test_list_paths_sorted(self, tmp_path: Path) -> None:
        f = _write_s32k3_mcu(tmp_path)
        doc = load_module(f, "Mcu")
        paths = list_paths(doc)
        assert paths == tuple(sorted(paths))
        # 至少包含这几个
        assert "Mcu/McuClockSettingConfig_0/McuClockFrequency" in paths
        assert "Mcu/McuClockSettingConfig_0/McuClockName" in paths
        assert "Mcu/McuClockSettingConfig_0/NestedChild/Counter" in paths
