"""Sprint 8.E.1 coverage: read / load / walk / namespace / infer_type.

Targets: arxml_io (namespace detection, read, helpers) + ecuc (load_module, _infer_type).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from lxml import etree
import pytest

from claude_autosar.core.bsw.arxml_io import (
    WELL_KNOWN_NAMESPACE_URIS,
    ARXMLError,
    build_default_nsmap,
    detect_namespaces,
    find_elements,
    get_attribute,
    get_child_text,
    read,
    resolve_namespaces,
    set_attribute,
    set_child_text,
)
from claude_autosar.core.bsw.bswmd import BSWMDRegistry, ContainerDef, ModuleDef, ParamDef
from claude_autosar.core.bsw.ecuc import (
    load_module,
)
from claude_autosar.core.bsw.ecuc import set_value as ecuc_set_value


# Helpers


def _write_xdm(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_r40_xdm(path: Path, body: str = "") -> Path:
    _write_xdm(
        path,
        f"""<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>AUTOSAR</SHORT-NAME>
      {body}
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
""",
    )
    return path


def _make_r47_xdm(path: Path, body: str = "") -> Path:
    _write_xdm(
        path,
        f"""<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.7">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>AUTOSAR</SHORT-NAME>
      {body}
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
""",
    )
    return path


def _make_module_xdm(path: Path, module_name: str = "Mcu") -> Path:
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>AUTOSAR</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-CONFIGURATION-VALUES>
          <SHORT-NAME>{module_name}</SHORT-NAME>
          <CONTAINERS>
            <ECUC-PARAM-CONF-CONTAINER>
              <SHORT-NAME>Cfg</SHORT-NAME>
              <PARAMETER-VALUES>
                <ECUC-NUMERICAL-PARAM-VALUE>
                  <DEFINITION-REF DEST="ECUC-INTEGER-PARAM-DEF">/AUTOSAR/{module_name}/Cfg/Freq</DEFINITION-REF>
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
"""
    _write_xdm(path, xml)
    return path


# arxml_io namespace detection / caching / xsi


class TestSprint8E1CoverageArxmlIoNamespace:
    """``detect_namespaces`` / ``build_default_nsmap`` / ``resolve_namespaces``."""

    def test_detect_namespaces_r40_returns_ar_mapping(self, tmp_path: Path) -> None:
        path = _make_r40_xdm(tmp_path / "r40.xdm")
        nsmap = detect_namespaces(path)
        assert nsmap["ar"] == "http://autosar.org/schema/r4.0"
        assert "xsi" in nsmap

    def test_detect_namespaces_r47_returns_r47_mapping(self, tmp_path: Path) -> None:
        path = _make_r47_xdm(tmp_path / "r47.xdm")
        nsmap = detect_namespaces(path)
        assert nsmap["ar"] == "http://autosar.org/schema/r4.7"

    def test_detect_namespaces_xsi_always_present(self, tmp_path: Path) -> None:
        path = _make_r40_xdm(tmp_path / "x.xdm")
        nsmap = detect_namespaces(path)
        assert "xsi" in nsmap
        assert nsmap["xsi"] == "http://www.w3.org/2001/XMLSchema-instance"

    def test_detect_namespaces_file_not_found_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ARXMLError, match="cannot stat"):
            detect_namespaces(tmp_path / "no_such.xdm")

    def test_detect_namespaces_malformed_xml_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.xdm"
        _write_xdm(bad, "not <valid> xml")
        with pytest.raises(ARXMLError, match="Malformed"):
            detect_namespaces(bad)

    def test_detect_namespaces_cache_invalidation_on_mtime(self, tmp_path: Path) -> None:
        path = _make_r40_xdm(tmp_path / "x.xdm")
        detect_namespaces(path)
        os.utime(path, ns=(path.stat().st_mtime_ns + 1_000_000_000,) * 2)
        _write_xdm(path, _make_r47_xdm(tmp_path / "r47.xdm").read_text(encoding="utf-8"))
        nsmap2 = detect_namespaces(path)
        assert nsmap2["ar"] == "http://autosar.org/schema/r4.7"

    def test_build_default_nsmap_handles_multi_namespace(self, tmp_path: Path) -> None:
        path = tmp_path / "multi.xdm"
        _write_xdm(
            path,
            """<?xml version="1.0"?>
<root xmlns="http://autosar.org/schema/r4.0"
      xmlns:custom="http://vendor.example.com/v1"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<elem/>
</root>
""",
        )
        tree = etree.parse(str(path))
        nsmap = build_default_nsmap(tree.getroot())
        assert nsmap["ar"] == "http://autosar.org/schema/r4.0"
        assert nsmap["custom"] == "http://vendor.example.com/v1"
        assert "xsi" in nsmap

    def test_resolve_namespaces_returns_dict(self, tmp_path: Path) -> None:
        path = _make_r40_xdm(tmp_path / "x.xdm")
        tree = etree.parse(str(path))
        nsmap = resolve_namespaces(tree.getroot())
        assert nsmap["ar"] == "http://autosar.org/schema/r4.0"


class TestSprint8E1CoverageArxmlIoWellKnown:
    """``WELL_KNOWN_NAMESPACE_URIS`` 兼容 alias / 多版本 URI。"""

    def test_well_known_namespace_uris_has_6_r4x_versions(self) -> None:
        ar_uris = WELL_KNOWN_NAMESPACE_URIS["ar"]
        assert len(ar_uris) == 6
        assert "http://autosar.org/schema/r4.0" in ar_uris
        assert "http://autosar.org/schema/r4.8" in ar_uris

    def test_default_namespaces_alias_back_compat(self) -> None:
        from claude_autosar.core.bsw.arxml_io import DEFAULT_NAMESPACES
        assert DEFAULT_NAMESPACES is WELL_KNOWN_NAMESPACE_URIS


# arxml_io high-level helpers (read / find_elements / get / set)


class TestSprint8E1CoverageArxmlIoHelpers:
    """``read`` / ``find_elements`` / ``get_*`` / ``set_*``."""

    def test_read_file_not_found_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ARXMLError, match="not readable"):
            read(tmp_path / "no.xdm")

    def test_read_malformed_xml_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.xdm"
        _write_xdm(bad, "<not><closed>")
        with pytest.raises(ARXMLError, match="Malformed"):
            read(bad)

    def test_find_elements_no_namespace_xpath_with_prefix_raises(self, tmp_path: Path) -> None:
        path = _make_r40_xdm(tmp_path / "x.xdm")
        doc = read(path)
        with pytest.raises(ARXMLError, match="Invalid XPath"):
            find_elements(doc, "//ar:SHORT-NAME")

    def test_find_elements_with_namespace(self, tmp_path: Path) -> None:
        path = _make_r40_xdm(tmp_path / "x.xdm")
        doc = read(path)
        nsmap = build_default_nsmap(doc.tree.getroot())
        result = find_elements(doc, "//ar:SHORT-NAME", namespaces=nsmap)
        assert len(result) >= 1

    def test_find_elements_invalid_xpath_raises(self, tmp_path: Path) -> None:
        path = _make_r40_xdm(tmp_path / "x.xdm")
        doc = read(path)
        with pytest.raises(ARXMLError, match="Invalid XPath"):
            find_elements(doc, "[[[")

    def test_get_attribute_returns_value(self) -> None:
        root = etree.fromstring('<root attr="val"/>')
        assert get_attribute(root, "attr") == "val"
        assert get_attribute(root, "missing") is None
        assert get_attribute(root, "missing", default="def") == "def"

    def test_set_attribute_sets_value(self) -> None:
        root = etree.fromstring("<root/>")
        set_attribute(root, "x", "1")
        assert root.get("x") == "1"

    def test_get_child_text_returns_text(self) -> None:
        root = etree.fromstring("<root><c>hello</c></root>")
        assert get_child_text(root, "c") == "hello"
        assert get_child_text(root, "missing") is None

    def test_set_child_text_creates_when_missing(self) -> None:
        root = etree.fromstring("<root/>")
        set_child_text(root, "c", "new")
        assert root.find("{*}c").text == "new"

    def test_set_child_text_overwrites_when_exists(self) -> None:
        root = etree.fromstring("<root><c>old</c></root>")
        set_child_text(root, "c", "new")
        assert root.find("{*}c").text == "new"
        assert len(root.findall("{*}c")) == 1


# ecuc load_module / list_paths with BSWMD


class TestSprint8E1CoverageEcucLoadModule:
    """``load_module`` BSWMD registry / namespace handling。"""

    def test_load_module_default_nsmap_detected(self, tmp_path: Path) -> None:
        path = _make_module_xdm(tmp_path / "Mcu.xdm", "Mcu")
        doc = load_module(path, "Mcu")
        assert doc.module_name == "Mcu"
        assert any(v.path == "Mcu/Cfg/Freq" for v in doc.values)

    def test_load_module_with_explicit_nsmap(self, tmp_path: Path) -> None:
        path = _make_module_xdm(tmp_path / "Mcu.xdm", "Mcu")
        nsmap = {"ar": "http://autosar.org/schema/r4.0", "xsi": "..."}
        doc = load_module(path, "Mcu", nsmap=nsmap)
        assert doc.module_name == "Mcu"

    def test_load_module_with_bswmd_registry_uses_strict_types(self, tmp_path: Path) -> None:
        path = _make_module_xdm(tmp_path / "Mcu.xdm", "Mcu")
        container = ContainerDef(
            short_name="Cfg",
            full_path="/AUTOSAR/Mcu/Cfg",
            lower_multiplicity=0,
            upper_multiplicity=1,
            param_defs={
                "Freq": ParamDef(
                    short_name="Freq",
                    full_path="/AUTOSAR/Mcu/Cfg/Freq",
                    param_type="ENUMERATION",
                )
            },
        )
        bswmd = BSWMDRegistry(
            modules={
                "Mcu": ModuleDef(
                    short_name="Mcu",
                    full_path="/AUTOSAR/Mcu",
                    containers={"Cfg": container},
                )
            },
        )
        doc = load_module(path, "Mcu", bswmd_registry=bswmd)
        freq = next(v for v in doc.values if v.path == "Mcu/Cfg/Freq")
        assert freq.type == "ENUMERATION"

    def test_load_module_module_not_found_raises(self, tmp_path: Path) -> None:
        path = _make_module_xdm(tmp_path / "Mcu.xdm", "Mcu")
        with pytest.raises(ValueError, match="not found"):
            load_module(path, "NoSuchModule")

    def test_load_module_with_r47_namespace(self, tmp_path: Path) -> None:
        r40 = _make_module_xdm(tmp_path / "Mcu.xdm", "Mcu")
        text = r40.read_text(encoding="utf-8").replace("r4.0", "r4.7")
        r40.write_text(text, encoding="utf-8")
        doc = load_module(r40, "Mcu")
        assert doc.module_name == "Mcu"

    def test_load_module_nsmap_mismatch_falls_back_to_actual(self, tmp_path: Path) -> None:
        path = _make_module_xdm(tmp_path / "Mcu.xdm", "Mcu")
        bad_nsmap = {"ar": "http://WRONG", "xsi": "..."}
        doc = load_module(path, "Mcu", nsmap=bad_nsmap)
        assert doc.module_name == "Mcu"
        assert any(v.path == "Mcu/Cfg/Freq" for v in doc.values)


# ecuc _infer_type BSWMD 优先 vs DEST 启发式


class TestSprint8E1CoverageEcucInferType:
    """``_infer_type`` BSWMD 优先 vs DEST 启发式。"""

    def test_infer_type_bswmd_priority_over_dest(self) -> None:
        from claude_autosar.core.bsw.ecuc import _infer_type
        def_ref = etree.fromstring('<DEF REF="x" DEST="ECUC-INTEGER-PARAM-DEF">/AUTOSAR/X/x</DEF>')
        bswmd = BSWMDRegistry(
            modules={
                "X": ModuleDef(
                    short_name="X",
                    full_path="/AUTOSAR/X",
                    params={
                        "x": ParamDef(
                            short_name="x",
                            full_path="/AUTOSAR/X/x",
                            param_type="ENUMERATION",
                        )
                    },
                )
            }
        )
        assert _infer_type(def_ref, bswmd_registry=bswmd) == "ENUMERATION"

    def test_infer_type_fallback_dest_heuristic(self) -> None:
        from claude_autosar.core.bsw.ecuc import _infer_type
        def_ref = etree.fromstring('<DEF DEST="ECUC-FLOAT-PARAM-DEF">/x</DEF>')
        bswmd = BSWMDRegistry()
        assert _infer_type(def_ref, bswmd_registry=bswmd) == "FLOAT"

    def test_infer_type_dest_vendor_extension_falls_back_to_string(self) -> None:
        from claude_autosar.core.bsw.ecuc import _infer_type
        def_ref = etree.fromstring('<DEF DEST="ECUC-VENDOR-SPECIFIC">/x</DEF>')
        assert _infer_type(def_ref, bswmd_registry=None) == "STRING"

    def test_infer_type_bswmd_miss_falls_back_to_dest(self) -> None:
        from claude_autosar.core.bsw.ecuc import _infer_type
        def_ref = etree.fromstring('<DEF DEST="ECUC-STRING-PARAM-DEF">/no/such/path</DEF>')
        bswmd = BSWMDRegistry(modules={"X": ModuleDef(short_name="X", full_path="/X")})
        assert _infer_type(def_ref, bswmd_registry=bswmd) == "STRING"

    def test_infer_type_bswmd_function_name_returns_string(self) -> None:
        from claude_autosar.core.bsw.ecuc import _infer_type
        def_ref = etree.fromstring('<DEF DEST="ECUC-FUNCTION-NAME-DEF">/X/x</DEF>')
        bswmd = BSWMDRegistry(
            modules={
                "X": ModuleDef(
                    short_name="X",
                    full_path="/X",
                    params={
                        "x": ParamDef(
                            short_name="x",
                            full_path="/X/x",
                            param_type="FUNCTION_NAME",  # type: ignore[arg-type]
                        )
                    },
                )
            }
        )
        assert _infer_type(def_ref, bswmd_registry=bswmd) == "STRING"
