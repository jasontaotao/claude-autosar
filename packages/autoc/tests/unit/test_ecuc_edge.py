"""Sprint 8.E.1 coverage: edge cases / error paths / BSWParam-BSWModule validation.

Targets: config (BSWParam/BSWModule validation) + ecuc (_walk / _emit_* internals).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_autosar.core.bsw.config import BSWModule, BSWParam, ParamType, ParamValue
from claude_autosar.core.bsw.ecuc import (
    load_module,
)


# Helpers


def _write_xdm(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# config BSWParam validation edge cases


class TestSprint8E1CoverageConfigBSWParam:
    """``BSWParam.def_ref`` 字段及 ParamValue 校验。"""

    def test_bswparam_def_ref_default_none(self) -> None:
        p = BSWParam(path="Mcu/Cfg/Freq", value=ParamValue(raw="1", type=ParamType.INTEGER))
        assert p.def_ref is None

    def test_bswparam_def_ref_explicit(self) -> None:
        p = BSWParam(
            path="Mcu/Cfg/Freq",
            value=ParamValue(raw="1", type=ParamType.INTEGER),
            def_ref="/AUTOSAR/Mcu/Cfg/Freq",
        )
        assert p.def_ref == "/AUTOSAR/Mcu/Cfg/Freq"

    def test_bswparam_def_ref_must_be_str_or_none(self) -> None:
        with pytest.raises(TypeError, match="def_ref must be str or None"):
            BSWParam(
                path="Mcu/Cfg/Freq",
                value=ParamValue(raw="1", type=ParamType.INTEGER),
                def_ref=123,  # type: ignore[arg-type]
            )

    def test_paramvalue_raw_must_be_str(self) -> None:
        with pytest.raises(TypeError, match="raw must be str"):
            ParamValue(raw=123, type=ParamType.INTEGER)  # type: ignore[arg-type]

    def test_paramvalue_type_must_be_paramtype(self) -> None:
        with pytest.raises(TypeError, match="type must be ParamType"):
            ParamValue(raw="1", type="integer")  # type: ignore[arg-type]

    def test_paramvalue_as_accessors(self) -> None:
        p_int = ParamValue(raw="42", type=ParamType.INTEGER)
        assert p_int.as_int() == 42
        assert p_int.as_str() == "42"
        with pytest.raises(TypeError):
            p_int.as_float()

        p_float = ParamValue(raw="3.14", type=ParamType.FLOAT)
        assert p_float.as_float() == 3.14

        p_bool = ParamValue(raw="true", type=ParamType.BOOLEAN)
        assert p_bool.as_bool() is True
        p_bool2 = ParamValue(raw="no", type=ParamType.BOOLEAN)
        assert p_bool2.as_bool() is False

    def test_paramvalue_as_int_wrong_type_raises(self) -> None:
        p = ParamValue(raw="x", type=ParamType.STRING)
        with pytest.raises(TypeError):
            p.as_int()


# config BSWModule validation edge cases


class TestSprint8E1CoverageConfigBSWModule:
    """``BSWModule.with_def_ref`` / ``get`` / ``with_param`` + validation。"""

    def test_bswmodule_get_returns_param(self) -> None:
        param = BSWParam(
            path="Mcu/Cfg/Freq",
            value=ParamValue(raw="1", type=ParamType.INTEGER),
        )
        m = BSWModule(name="Mcu", params=(param,))
        assert m.get("Mcu/Cfg/Freq") is param
        assert m.get("Mcu/Other") is None

    def test_bswmodule_with_param_replaces_existing(self) -> None:
        old = BSWParam(
            path="Mcu/Cfg/Freq",
            value=ParamValue(raw="1", type=ParamType.INTEGER),
        )
        new = BSWParam(
            path="Mcu/Cfg/Freq",
            value=ParamValue(raw="2", type=ParamType.INTEGER),
        )
        m = BSWModule(name="Mcu", params=(old,))
        m2 = m.with_param(new)
        assert m2.params == (new,)
        assert m.params == (old,)

    def test_bswmodule_with_param_appends_new(self) -> None:
        p1 = BSWParam(
            path="Mcu/Cfg/A",
            value=ParamValue(raw="1", type=ParamType.INTEGER),
        )
        p2 = BSWParam(
            path="Mcu/Cfg/B",
            value=ParamValue(raw="2", type=ParamType.INTEGER),
        )
        m = BSWModule(name="Mcu", params=(p1,))
        m2 = m.with_param(p2)
        assert m2.params == (p1, p2)

    def test_bswmodule_with_def_ref_replaces(self) -> None:
        param = BSWParam(
            path="Mcu/Cfg/Freq",
            value=ParamValue(raw="1", type=ParamType.INTEGER),
        )
        m = BSWModule(name="Mcu", params=(param,))
        m2 = m.with_def_ref("Mcu/Cfg/Freq", "/AUTOSAR/Mcu/Cfg/Freq")
        new_param = m2.params[0]
        assert new_param.def_ref == "/AUTOSAR/Mcu/Cfg/Freq"
        assert new_param.path == "Mcu/Cfg/Freq"

    def test_bswmodule_with_def_ref_path_not_in_params_raises(self) -> None:
        m = BSWModule(name="Mcu")
        with pytest.raises(ValueError, match="not in params"):
            m.with_def_ref("Mcu/NonExistent", "/x")

    def test_bswmodule_empty_name_raises(self) -> None:
        with pytest.raises(ValueError, match="name must be non-empty"):
            BSWModule(name="")

    def test_bswmodule_params_must_be_tuple(self) -> None:
        with pytest.raises(TypeError, match="params must be a tuple"):
            BSWModule(name="Mcu", params=[])  # type: ignore[arg-type]

    def test_bswmodule_params_must_contain_bswparam_only(self) -> None:
        with pytest.raises(TypeError, match="must contain BSWParam"):
            BSWModule(name="Mcu", params=("not a BSWParam",))  # type: ignore[arg-type]

    def test_bswparam_empty_path_raises(self) -> None:
        with pytest.raises(ValueError, match="path must be hierarchical"):
            BSWParam(path="", value=ParamValue(raw="1", type=ParamType.INTEGER))

    def test_bswparam_path_without_slash_raises(self) -> None:
        with pytest.raises(ValueError, match="path must be hierarchical"):
            BSWParam(
                path="Mcu",
                value=ParamValue(raw="1", type=ParamType.INTEGER),
            )

    def test_bswparam_value_must_be_paramvalue(self) -> None:
        with pytest.raises(TypeError, match="value must be ParamValue"):
            BSWParam(path="Mcu/Cfg", value="not a ParamValue")  # type: ignore[arg-type]


# ecuc._walk / _emit_parameter / _emit_reference internals


class TestSprint8E1CoverageEcucWalkInternals:
    """``_walk`` / ``_emit_*`` / ``_infer_type`` 各 branch。"""

    def test_emit_parameter_no_def_ref_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "no_def_ref.xdm"
        _write_xdm(
            path,
            """<?xml version="1.0"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>AUTOSAR</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-CONFIGURATION-VALUES>
          <SHORT-NAME>Mcu</SHORT-NAME>
          <CONTAINERS>
            <ECUC-PARAM-CONF-CONTAINER>
              <SHORT-NAME>Cfg</SHORT-NAME>
              <PARAMETER-VALUES>
                <ECUC-NUMERICAL-PARAM-VALUE>
                  <!-- no DEFINITION-REF -->
                  <VALUE>999</VALUE>
                </ECUC-NUMERICAL-PARAM-VALUE>
                <ECUC-NUMERICAL-PARAM-VALUE>
                  <DEFINITION-REF DEST="ECUC-INTEGER-PARAM-DEF">/AUTOSAR/Mcu/Cfg/Freq</DEFINITION-REF>
                  <VALUE>100</VALUE>
                </ECUC-NUMERICAL-PARAM-VALUE>
              </PARAMETER-VALUES>
            </ECUC-PARAM-CONF-CONTAINER>
          </CONTAINERS>
        </ECUC-MODULE-CONFIGURATION-VALUES>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
""",
        )
        doc = load_module(path, "Mcu")
        assert len(doc.values) == 1
        assert doc.values[0].path == "Mcu/Cfg/Freq"

    def test_emit_parameter_no_value_text_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "no_value.xdm"
        _write_xdm(
            path,
            """<?xml version="1.0"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>AUTOSAR</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-CONFIGURATION-VALUES>
          <SHORT-NAME>Mcu</SHORT-NAME>
          <CONTAINERS>
            <ECUC-PARAM-CONF-CONTAINER>
              <SHORT-NAME>Cfg</SHORT-NAME>
              <PARAMETER-VALUES>
                <ECUC-NUMERICAL-PARAM-VALUE>
                  <DEFINITION-REF DEST="ECUC-INTEGER-PARAM-DEF">/AUTOSAR/Mcu/Cfg/Freq</DEFINITION-REF>
                  <!-- no <VALUE> -->
                </ECUC-NUMERICAL-PARAM-VALUE>
              </PARAMETER-VALUES>
            </ECUC-PARAM-CONF-CONTAINER>
          </CONTAINERS>
        </ECUC-MODULE-CONFIGURATION-VALUES>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
""",
        )
        doc = load_module(path, "Mcu")
        assert doc.values == ()

    def test_emit_reference_no_value_ref_text_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "no_value_ref.xdm"
        _write_xdm(
            path,
            """<?xml version="1.0"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>AUTOSAR</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-CONFIGURATION-VALUES>
          <SHORT-NAME>Mcu</SHORT-NAME>
          <CONTAINERS>
            <ECUC-PARAM-CONF-CONTAINER>
              <SHORT-NAME>Cfg</SHORT-NAME>
              <REFERENCE-VALUES>
                <ECUC-REFERENCE-VALUE>
                  <DEFINITION-REF DEST="ECUC-PARAM-CONF-CONTAINER-DEF">/AUTOSAR/Mcu/Cfg/Target</DEFINITION-REF>
                  <!-- no VALUE-REF -->
                </ECUC-REFERENCE-VALUE>
              </REFERENCE-VALUES>
            </ECUC-PARAM-CONF-CONTAINER>
          </CONTAINERS>
        </ECUC-MODULE-CONFIGURATION-VALUES>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
""",
        )
        doc = load_module(path, "Mcu")
        assert len(doc.values) == 1
        ref = doc.values[0]
        assert ref.path == "Mcu/Cfg/Target"
        assert ref.raw == ""
        assert ref.type == "STRING"

    def test_emit_reference_with_value_ref(self, tmp_path: Path) -> None:
        path = tmp_path / "with_ref.xdm"
        _write_xdm(
            path,
            """<?xml version="1.0"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>AUTOSAR</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-CONFIGURATION-VALUES>
          <SHORT-NAME>Mcu</SHORT-NAME>
          <CONTAINERS>
            <ECUC-PARAM-CONF-CONTAINER>
              <SHORT-NAME>Cfg</SHORT-NAME>
              <REFERENCE-VALUES>
                <ECUC-REFERENCE-VALUE>
                  <DEFINITION-REF DEST="ECUC-PARAM-CONF-CONTAINER-DEF">/AUTOSAR/Mcu/Cfg/Target</DEFINITION-REF>
                  <VALUE-REF>/AUTOSAR/Other/Ecu/Instance</VALUE-REF>
                </ECUC-REFERENCE-VALUE>
              </REFERENCE-VALUES>
            </ECUC-PARAM-CONF-CONTAINER>
          </CONTAINERS>
        </ECUC-MODULE-CONFIGURATION-VALUES>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
""",
        )
        doc = load_module(path, "Mcu")
        assert len(doc.values) == 1
        assert doc.values[0].raw == "/AUTOSAR/Other/Ecu/Instance"

    def test_walk_container_directly_under_module_root(self, tmp_path: Path) -> None:
        path = tmp_path / "direct_container.xdm"
        _write_xdm(
            path,
            """<?xml version="1.0"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>AUTOSAR</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-CONFIGURATION-VALUES>
          <SHORT-NAME>Mcu</SHORT-NAME>
          <ECUC-PARAM-CONF-CONTAINER>
            <SHORT-NAME>Direct</SHORT-NAME>
            <PARAMETER-VALUES>
              <ECUC-NUMERICAL-PARAM-VALUE>
                <DEFINITION-REF DEST="ECUC-INTEGER-PARAM-DEF">/AUTOSAR/Mcu/Direct/F</DEFINITION-REF>
                <VALUE>42</VALUE>
              </ECUC-NUMERICAL-PARAM-VALUE>
            </PARAMETER-VALUES>
          </ECUC-PARAM-CONF-CONTAINER>
        </ECUC-MODULE-CONFIGURATION-VALUES>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
""",
        )
        doc = load_module(path, "Mcu")
        assert len(doc.values) == 1
        assert doc.values[0].path == "Mcu/Direct/F"

    def test_walk_container_missing_short_name_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "no_sn.xdm"
        _write_xdm(
            path,
            """<?xml version="1.0"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>AUTOSAR</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-CONFIGURATION-VALUES>
          <SHORT-NAME>Mcu</SHORT-NAME>
          <CONTAINERS>
            <ECUC-PARAM-CONF-CONTAINER>
              <!-- no SHORT-NAME -->
              <PARAMETER-VALUES>
                <ECUC-NUMERICAL-PARAM-VALUE>
                  <DEFINITION-REF DEST="ECUC-INTEGER-PARAM-DEF">/x</DEFINITION-REF>
                  <VALUE>1</VALUE>
                </ECUC-NUMERICAL-PARAM-VALUE>
              </PARAMETER-VALUES>
            </ECUC-PARAM-CONF-CONTAINER>
          </CONTAINERS>
        </ECUC-MODULE-CONFIGURATION-VALUES>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
""",
        )
        doc = load_module(path, "Mcu")
        assert doc.values == ()

    def test_emit_parameter_empty_def_ref_text_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "empty_def.xdm"
        _write_xdm(
            path,
            """<?xml version="1.0"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>AUTOSAR</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-CONFIGURATION-VALUES>
          <SHORT-NAME>Mcu</SHORT-NAME>
          <CONTAINERS>
            <ECUC-PARAM-CONF-CONTAINER>
              <SHORT-NAME>Cfg</SHORT-NAME>
              <PARAMETER-VALUES>
                <ECUC-NUMERICAL-PARAM-VALUE>
                  <DEFINITION-REF DEST="ECUC-INTEGER-PARAM-DEF"></DEFINITION-REF>
                  <VALUE>999</VALUE>
                </ECUC-NUMERICAL-PARAM-VALUE>
              </PARAMETER-VALUES>
            </ECUC-PARAM-CONF-CONTAINER>
          </CONTAINERS>
        </ECUC-MODULE-CONFIGURATION-VALUES>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
""",
        )
        doc = load_module(path, "Mcu")
        assert doc.values == ()
