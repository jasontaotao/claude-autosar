"""BSWMD 解析 helper 测试。

从 test_sprint8e_coverage_bswmd.py 拆分而来。
覆盖：_parse_module_def, _parse_module_body, _parse_container_def,
_parse_param_def, _parse_multiplicity, _descend。
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree
import pytest

from claude_autosar.core.bsw.bswmd import (
    BSWMDRegistry,
    ContainerDef,
    ParamDef,
)


# -- helpers ------------------------------------------------------------------


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _bswmd_xml(root_pkg: str = "AUTOSAR", body: str = "") -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>{root_pkg}</SHORT-NAME>
      {body}
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
"""


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "autoc-bswmd-cov-ws"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


# -- _parse_module_def 边界 ---------------------------------------------------


class TestBSWMDCoverageParseModule:
    """``_parse_module_def`` missing 分支。"""

    def test_module_without_short_name_returns_none(self) -> None:
        """行 572-574：module 无 SHORT-NAME → return None。"""
        from claude_autosar.core.bsw.bswmd_parser import _parse_module_def

        elem = etree.fromstring(
            '<ECUC-MODULE-DEF xmlns="http://autosar.org/schema/r4.0">'
            "<!-- no SHORT-NAME --></ECUC-MODULE-DEF>",
        )
        result = _parse_module_def(elem, root_pkg_name="AUTOSAR")
        assert result is None

    def test_module_with_empty_short_name_returns_none(self) -> None:
        """行 572-574：SHORT-NAME 为空字符串 → return None。"""
        from claude_autosar.core.bsw.bswmd_parser import _parse_module_def

        elem = etree.fromstring(
            '<ECUC-MODULE-DEF xmlns="http://autosar.org/schema/r4.0">'
            "<SHORT-NAME>   </SHORT-NAME></ECUC-MODULE-DEF>",
        )
        result = _parse_module_def(elem, root_pkg_name="AUTOSAR")
        assert result is None


# -- _parse_module_body 边界 --------------------------------------------------


class TestBSWMDCoverageParseModuleBody:
    """``_parse_module_body`` 行 603/608 的非字符串 tag 跳过。"""

    def test_module_with_comment_only_conts_block(self) -> None:
        """CONTAINERS 内只有注释子节点 → 不会抛。"""
        from claude_autosar.core.bsw.bswmd_parser import _parse_module_body

        elem = etree.fromstring(
            '<ECUC-MODULE-DEF xmlns="http://autosar.org/schema/r4.0">'
            "<SHORT-NAME>Mcu</SHORT-NAME>"
            "<CONTAINERS><!-- no children --></CONTAINERS>"
            "</ECUC-MODULE-DEF>",
        )
        containers, params = _parse_module_body(elem, "/A/Mcu")
        assert containers == {}
        assert params == {}


# -- _parse_container_def 边界 ------------------------------------------------


class TestBSWMDCoverageParseContainer:
    """``_parse_container_def`` missing 分支。"""

    def test_container_without_short_name_returns_none(self) -> None:
        """行 631-633：container 无 SHORT-NAME → None。"""
        from claude_autosar.core.bsw.bswmd_parser import _parse_container_def

        elem = etree.fromstring(
            '<ECUC-PARAM-CONF-CONTAINER-DEF xmlns="http://autosar.org/schema/r4.0">'
            "<!-- no SHORT-NAME --></ECUC-PARAM-CONF-CONTAINER-DEF>",
        )
        result = _parse_container_def(elem, parent_path="/A/Mcu")
        assert result is None

    def test_container_with_choice_container(self) -> None:
        """行 658-661：``ECUC-CHOICE-CONTAINER-DEF`` 也被解析为 ContainerDef。"""
        xml = _bswmd_xml(
            body="<ELEMENTS><ECUC-MODULE-DEF><SHORT-NAME>Mcu</SHORT-NAME>"
            "<CONTAINERS><ECUC-CHOICE-CONTAINER-DEF>"
            "<SHORT-NAME>Choice</SHORT-NAME>"
            "<LOWER-MULTIPLICITY>0</LOWER-MULTIPLICITY>"
            "<UPPER-MULTIPLICITY>1</UPPER-MULTIPLICITY>"
            "</ECUC-CHOICE-CONTAINER-DEF></CONTAINERS>"
            "</ECUC-MODULE-DEF></ELEMENTS>",
        )
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "choice.arxml"
            _write(path, xml)
            reg = BSWMDRegistry.load((path,))
        assert "Choice" in reg.modules["Mcu"].containers

    def test_container_sub_containers_recursion(self) -> None:
        """行 654-661：sub_containers 嵌套。"""
        xml = _bswmd_xml(
            body="<ELEMENTS><ECUC-MODULE-DEF><SHORT-NAME>Mcu</SHORT-NAME>"
            "<CONTAINERS><ECUC-PARAM-CONF-CONTAINER-DEF>"
            "<SHORT-NAME>Outer</SHORT-NAME>"
            "<SUB-CONTAINERS><ECUC-PARAM-CONF-CONTAINER-DEF>"
            "<SHORT-NAME>Inner</SHORT-NAME>"
            "</ECUC-PARAM-CONF-CONTAINER-DEF></SUB-CONTAINERS>"
            "</ECUC-PARAM-CONF-CONTAINER-DEF></CONTAINERS>"
            "</ECUC-MODULE-DEF></ELEMENTS>",
        )
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "nested.arxml"
            _write(path, xml)
            reg = BSWMDRegistry.load((path,))
        outer = reg.modules["Mcu"].containers["Outer"]
        assert "Inner" in outer.sub_container_defs


# -- _parse_param_def 边界 ----------------------------------------------------


class TestBSWMDCoverageParseParam:
    """``_parse_param_def`` missing 分支 + 全部 6 个 PARAM_TYPE。"""

    def test_unknown_param_def_type_returns_none(self) -> None:
        """行 683-685：未知 PARAM-DEF localname → None。"""
        from claude_autosar.core.bsw.bswmd_parser import _parse_param_def

        elem = etree.fromstring(
            '<ECUC-MY-CUSTOM-PARAM-DEF xmlns="http://autosar.org/schema/r4.0">'
            "<SHORT-NAME>Foo</SHORT-NAME></ECUC-MY-CUSTOM-PARAM-DEF>",
        )
        result = _parse_param_def(elem, parent_path="/A/M")
        assert result is None

    def test_param_def_without_short_name_returns_none(self) -> None:
        """行 687-689：param 无 SHORT-NAME → None。"""
        from claude_autosar.core.bsw.bswmd_parser import _parse_param_def

        elem = etree.fromstring(
            '<ECUC-INTEGER-PARAM-DEF xmlns="http://autosar.org/schema/r4.0">'
            "<!-- no SHORT-NAME --></ECUC-INTEGER-PARAM-DEF>",
        )
        result = _parse_param_def(elem, parent_path="/A/M")
        assert result is None

    def test_function_name_param_def(self) -> None:
        """FUNCTION_NAME PARAM_TYPE 解析。"""
        xml = _bswmd_xml(
            body="<ELEMENTS><ECUC-MODULE-DEF><SHORT-NAME>Mcu</SHORT-NAME>"
            "<CONTAINERS><ECUC-PARAM-CONF-CONTAINER-DEF>"
            "<SHORT-NAME>C</SHORT-NAME>"
            "<PARAMETERS><ECUC-FUNCTION-NAME-DEF>"
            "<SHORT-NAME>Fn</SHORT-NAME>"
            "</ECUC-FUNCTION-NAME-DEF></PARAMETERS>"
            "</ECUC-PARAM-CONF-CONTAINER-DEF></CONTAINERS>"
            "</ECUC-MODULE-DEF></ELEMENTS>",
        )
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fn.arxml"
            _write(path, xml)
            reg = BSWMDRegistry.load((path,))
        p = reg.modules["Mcu"].containers["C"].param_defs["Fn"]
        assert p.param_type == "FUNCTION_NAME"

    def test_default_value_rare_schema_with_direct_value_text(self) -> None:
        """行 702-704：``<DEFAULT-VALUE>`` 内直接是文本（罕见 schema）。"""
        xml = _bswmd_xml(
            body="<ELEMENTS><ECUC-MODULE-DEF><SHORT-NAME>M</SHORT-NAME>"
            "<CONTAINERS><ECUC-PARAM-CONF-CONTAINER-DEF>"
            "<SHORT-NAME>C</SHORT-NAME>"
            "<PARAMETERS><ECUC-INTEGER-PARAM-DEF>"
            "<SHORT-NAME>P</SHORT-NAME>"
            "<DEFAULT-VALUE>42</DEFAULT-VALUE>"
            "</ECUC-INTEGER-PARAM-DEF></PARAMETERS>"
            "</ECUC-PARAM-CONF-CONTAINER-DEF></CONTAINERS>"
            "</ECUC-MODULE-DEF></ELEMENTS>",
        )
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "dv.arxml"
            _write(path, xml)
            reg = BSWMDRegistry.load((path,))
        p = reg.modules["M"].containers["C"].param_defs["P"]
        assert p.default == "42"

    def test_min_max_parsing(self) -> None:
        """行 692-693：MIN / MAX 文本解析。"""
        xml = _bswmd_xml(
            body="<ELEMENTS><ECUC-MODULE-DEF><SHORT-NAME>M</SHORT-NAME>"
            "<CONTAINERS><ECUC-PARAM-CONF-CONTAINER-DEF>"
            "<SHORT-NAME>C</SHORT-NAME>"
            "<PARAMETERS><ECUC-INTEGER-PARAM-DEF>"
            "<SHORT-NAME>Lim</SHORT-NAME>"
            "<MIN>-100</MIN><MAX>200</MAX>"
            "</ECUC-INTEGER-PARAM-DEF></PARAMETERS>"
            "</ECUC-PARAM-CONF-CONTAINER-DEF></CONTAINERS>"
            "</ECUC-MODULE-DEF></ELEMENTS>",
        )
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "minmax.arxml"
            _write(path, xml)
            reg = BSWMDRegistry.load((path,))
        p = reg.modules["M"].containers["C"].param_defs["Lim"]
        assert p.min == "-100"
        assert p.max == "200"

    def test_enumeration_without_literals(self) -> None:
        """行 709-720：ENUMERATION 无 LITERALS → symbol_strings=()。"""
        xml = _bswmd_xml(
            body="<ELEMENTS><ECUC-MODULE-DEF><SHORT-NAME>M</SHORT-NAME>"
            "<CONTAINERS><ECUC-PARAM-CONF-CONTAINER-DEF>"
            "<SHORT-NAME>C</SHORT-NAME>"
            "<PARAMETERS><ECUC-ENUMERATION-PARAM-DEF>"
            "<SHORT-NAME>E</SHORT-NAME>"
            "</ECUC-ENUMERATION-PARAM-DEF></PARAMETERS>"
            "</ECUC-PARAM-CONF-CONTAINER-DEF></CONTAINERS>"
            "</ECUC-MODULE-DEF></ELEMENTS>",
        )
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "no_lit.arxml"
            _write(path, xml)
            reg = BSWMDRegistry.load((path,))
        p = reg.modules["M"].containers["C"].param_defs["E"]
        assert p.param_type == "ENUMERATION"
        assert p.symbol_strings == ()

    def test_enumeration_literal_without_short_name_skipped(self) -> None:
        """行 716-720：literal 无 SHORT-NAME 被跳过。"""
        xml = _bswmd_xml(
            body="<ELEMENTS><ECUC-MODULE-DEF><SHORT-NAME>M</SHORT-NAME>"
            "<CONTAINERS><ECUC-PARAM-CONF-CONTAINER-DEF>"
            "<SHORT-NAME>C</SHORT-NAME>"
            "<PARAMETERS><ECUC-ENUMERATION-PARAM-DEF>"
            "<SHORT-NAME>E</SHORT-NAME>"
            "<LITERALS>"
            "<ECUC-ENUMERATION-LITERAL-DEF><SHORT-NAME>A</SHORT-NAME></ECUC-ENUMERATION-LITERAL-DEF>"
            "<ECUC-ENUMERATION-LITERAL-DEF><!-- no SHORT-NAME --></ECUC-ENUMERATION-LITERAL-DEF>"
            "<ECUC-ENUMERATION-LITERAL-DEF><SHORT-NAME>B</SHORT-NAME></ECUC-ENUMERATION-LITERAL-DEF>"
            "</LITERALS>"
            "</ECUC-ENUMERATION-PARAM-DEF></PARAMETERS>"
            "</ECUC-PARAM-CONF-CONTAINER-DEF></CONTAINERS>"
            "</ECUC-MODULE-DEF></ELEMENTS>",
        )
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "mixed_lit.arxml"
            _write(path, xml)
            reg = BSWMDRegistry.load((path,))
        p = reg.modules["M"].containers["C"].param_defs["E"]
        assert p.symbol_strings == ("A", "B")


# -- _parse_multiplicity 异常路径 ---------------------------------------------


class TestBSWMDCoverageMultiplicity:
    """``_parse_multiplicity`` 异常 / 边界。"""

    def test_invalid_lower_text_falls_back_to_default(self) -> None:
        """行 540-541：LOWER-MULTIPLICITY 文本非整数 → lower_default。"""
        from claude_autosar.core.bsw.bswmd_parser import _parse_multiplicity

        elem = etree.fromstring(
            '<ELEM xmlns="http://x">'
            "<LOWER-MULTIPLICITY>not-a-number</LOWER-MULTIPLICITY>"
            "<UPPER-MULTIPLICITY>1</UPPER-MULTIPLICITY>"
            "</ELEM>",
        )
        lower, upper = _parse_multiplicity(elem)
        assert lower == 0
        assert upper == 1

    def test_invalid_upper_text_falls_back_to_default(self) -> None:
        """行 550-551：UPPER-MULTIPLICITY 文本非整数 → upper_default。"""
        from claude_autosar.core.bsw.bswmd_parser import _parse_multiplicity

        elem = etree.fromstring(
            '<ELEM xmlns="http://x">'
            "<LOWER-MULTIPLICITY>0</LOWER-MULTIPLICITY>"
            "<UPPER-MULTIPLICITY>some-junk</UPPER-MULTIPLICITY>"
            "</ELEM>",
        )
        lower, upper = _parse_multiplicity(elem)
        assert lower == 0
        assert upper == 1

    def test_unbounded_upper_via_uppercase(self) -> None:
        """``unbounded`` 大小写不敏感。"""
        from claude_autosar.core.bsw.bswmd_parser import _parse_multiplicity

        elem = etree.fromstring(
            '<ELEM xmlns="http://x">'
            "<LOWER-MULTIPLICITY>0</LOWER-MULTIPLICITY>"
            "<UPPER-MULTIPLICITY>UNBOUNDED</UPPER-MULTIPLICITY>"
            "</ELEM>",
        )
        _, upper = _parse_multiplicity(elem)
        assert upper == -1


# -- _descend 边界 ------------------------------------------------------------


class TestBSWMDCoverageDescend:
    """``_descend`` ParamDef 叶子 / ContainerDef param 命中。"""

    def test_descend_param_def_leaf_returns_none(self) -> None:
        """行 763-764：ParamDef 是叶子 → ``_descend`` 返回 None。"""
        from claude_autosar.core.bsw.bswmd_parser import _descend

        p = ParamDef(short_name="X", full_path="/A/X", param_type="INTEGER")
        result = _descend(p, "Anything", prefer_param=True)
        assert result is None

    def test_descend_container_prefers_subcontainer_over_param(self) -> None:
        """``_descend`` ContainerDef：sub_container 优先于 param。"""
        from claude_autosar.core.bsw.bswmd_parser import _descend

        sub = ContainerDef(
            short_name="Sub",
            full_path="/A/Sub",
            lower_multiplicity=0,
            upper_multiplicity=1,
        )
        c = ContainerDef(
            short_name="Main",
            full_path="/A/Main",
            lower_multiplicity=0,
            upper_multiplicity=1,
            sub_container_defs={"Sub": sub},
        )
        result = _descend(c, "Sub", prefer_param=False)
        assert result is sub

    def test_descend_container_falls_back_to_param_when_prefer_param(self) -> None:
        from claude_autosar.core.bsw.bswmd_parser import _descend

        p = ParamDef(short_name="P", full_path="/A/P", param_type="INTEGER")
        c = ContainerDef(
            short_name="C",
            full_path="/A/C",
            lower_multiplicity=0,
            upper_multiplicity=1,
            param_defs={"P": p},
        )
        result = _descend(c, "P", prefer_param=True)
        assert result is p

    def test_descend_container_no_match_returns_none(self) -> None:
        from claude_autosar.core.bsw.bswmd_parser import _descend

        c = ContainerDef(
            short_name="C",
            full_path="/A/C",
            lower_multiplicity=0,
            upper_multiplicity=1,
        )
        result = _descend(c, "X", prefer_param=False)
        assert result is None
