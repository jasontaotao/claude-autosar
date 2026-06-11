"""Unit tests for packages/autoc/src/autoc/core/bsw/arxml_io.py.

TDD 阶段：RED（先写测试）。Sprint 3 — T3.1。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from autoc.core.bsw.arxml_io import (
    ARXMLDocument,
    ARXMLError,
    find_elements,
    get_attribute,
    get_child_text,
    read,
    set_attribute,
    set_child_text,
    write,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _write_xml(path: Path, content: str) -> None:
    """Helper：直接写 XML 字符串到文件（绕过 arxml_io，测试 fixture 用）。"""
    path.write_text(content, encoding="utf-8")


_SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
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


# ---------------------------------------------------------------------------
# read / write
# ---------------------------------------------------------------------------


class TestRead:
    def test_read_existing_file(self, tmp_path: Path) -> None:
        f = tmp_path / "sample.arxml"
        _write_xml(f, _SAMPLE_XML)
        doc = read(f)
        assert isinstance(doc, ARXMLDocument)
        assert doc.path == f
        assert doc.tree.getroot().tag.endswith("AUTOSAR")

    def test_read_missing_file_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "missing.arxml"
        with pytest.raises(ARXMLError):
            read(f)

    def test_read_malformed_xml_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.arxml"
        _write_xml(f, "<unclosed><tag>")
        with pytest.raises(ARXMLError):
            read(f)


class TestWrite:
    def test_write_creates_file(self, tmp_path: Path) -> None:
        f = tmp_path / "out.arxml"
        _write_xml(f, _SAMPLE_XML)
        doc = read(f)
        write(doc, atomic=False)
        assert f.exists()
        # 内容应能被重新读回
        doc2 = read(f)
        assert doc2.tree.getroot().tag == doc.tree.getroot().tag

    def test_write_atomic_failure_preserves_original(self, tmp_path: Path) -> None:
        """如果 os.replace 失败，原文件不应被破坏。"""
        f = tmp_path / "out.arxml"
        _write_xml(f, _SAMPLE_XML)
        original_content = f.read_text(encoding="utf-8")
        doc = read(f)

        with (
            patch(
                "autoc.core.bsw.arxml_io.os.replace",
                side_effect=OSError("simulated rename failure"),
            ),
            pytest.raises(ARXMLError),
        ):
            write(doc, atomic=True)

        # 原文件应保持不变
        assert f.read_text(encoding="utf-8") == original_content


# ---------------------------------------------------------------------------
# find_elements
# ---------------------------------------------------------------------------


class TestFindElements:
    def test_find_with_namespace(self, tmp_path: Path) -> None:
        f = tmp_path / "sample.arxml"
        _write_xml(f, _SAMPLE_XML)
        doc = read(f)
        results = find_elements(
            doc,
            "//ar:ECUC-MODULE-CONFIGURATION-VALUES",
            namespaces={"ar": "http://autosar.org/schema/r4.0"},
        )
        assert len(results) == 1
        assert results[0].tag.endswith("ECUC-MODULE-CONFIGURATION-VALUES")

    def test_find_no_match_returns_empty(self, tmp_path: Path) -> None:
        f = tmp_path / "sample.arxml"
        _write_xml(f, _SAMPLE_XML)
        doc = read(f)
        results = find_elements(
            doc,
            "//ar:DOES-NOT-EXIST",
            namespaces={"ar": "http://autosar.org/schema/r4.0"},
        )
        assert results == []

    def test_find_without_namespace_returns_empty_for_namespaced_doc(self, tmp_path: Path) -> None:
        """带命名空间的 doc，没传 namespaces 字典，xpath 应返回空（或抛错，但实现选 '返回空' 更友好）。"""
        f = tmp_path / "sample.arxml"
        _write_xml(f, _SAMPLE_XML)
        doc = read(f)
        results = find_elements(doc, "//ECUC-MODULE-CONFIGURATION-VALUES")
        assert results == []

    def test_find_bad_xpath_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "sample.arxml"
        _write_xml(f, _SAMPLE_XML)
        doc = read(f)
        with pytest.raises(ARXMLError):
            find_elements(doc, "////invalid[[[")


# ---------------------------------------------------------------------------
# get_attribute / set_attribute
# ---------------------------------------------------------------------------


class TestGetSetAttribute:
    def test_get_existing(self, tmp_path: Path) -> None:
        f = tmp_path / "sample.arxml"
        _write_xml(f, _SAMPLE_XML)
        doc = read(f)
        ref = find_elements(
            doc,
            "//ar:DEFINITION-REF",
            namespaces={"ar": "http://autosar.org/schema/r4.0"},
        )[0]
        assert get_attribute(ref, "DEST") == "ECUC-PARAMETER-DEF"

    def test_get_missing_returns_default(self, tmp_path: Path) -> None:
        f = tmp_path / "sample.arxml"
        _write_xml(f, _SAMPLE_XML)
        doc = read(f)
        ref = find_elements(
            doc,
            "//ar:DEFINITION-REF",
            namespaces={"ar": "http://autosar.org/schema/r4.0"},
        )[0]
        assert get_attribute(ref, "NONEXISTENT", default="X") == "X"

    def test_get_missing_no_default_returns_none(self, tmp_path: Path) -> None:
        f = tmp_path / "sample.arxml"
        _write_xml(f, _SAMPLE_XML)
        doc = read(f)
        ref = find_elements(
            doc,
            "//ar:DEFINITION-REF",
            namespaces={"ar": "http://autosar.org/schema/r4.0"},
        )[0]
        assert get_attribute(ref, "NONEXISTENT") is None

    def test_set_attribute_overwrites(self, tmp_path: Path) -> None:
        f = tmp_path / "sample.arxml"
        _write_xml(f, _SAMPLE_XML)
        doc = read(f)
        ref = find_elements(
            doc,
            "//ar:DEFINITION-REF",
            namespaces={"ar": "http://autosar.org/schema/r4.0"},
        )[0]
        set_attribute(ref, "DEST", "ECUC-OTHER")
        assert get_attribute(ref, "DEST") == "ECUC-OTHER"


# ---------------------------------------------------------------------------
# get_child_text / set_child_text
# ---------------------------------------------------------------------------


class TestGetSetChildText:
    def test_get_existing(self, tmp_path: Path) -> None:
        f = tmp_path / "sample.arxml"
        _write_xml(f, _SAMPLE_XML)
        doc = read(f)
        value_elem = find_elements(
            doc,
            "//ar:VALUE",
            namespaces={"ar": "http://autosar.org/schema/r4.0"},
        )[0]
        assert get_child_text(value_elem, "FOO") is None
        # 用 get_child_text 找 <VALUE> 自身的文本应等于原始值
        # 实际：get_child_text(elem, tag) 找 elem 的子节点 tag 并返回其 .text
        # value_elem 自身是 <VALUE>，其父是 <ECUC-NUMERICAL-PARAM-VALUE>
        parent = value_elem.getparent()
        assert get_child_text(parent, "VALUE") == "80000000"

    def test_get_missing_returns_none(self, tmp_path: Path) -> None:
        f = tmp_path / "sample.arxml"
        _write_xml(f, _SAMPLE_XML)
        doc = read(f)
        value_elem = find_elements(
            doc,
            "//ar:VALUE",
            namespaces={"ar": "http://autosar.org/schema/r4.0"},
        )[0]
        assert get_child_text(value_elem, "NONEXISTENT") is None

    def test_set_child_text_overwrites(self, tmp_path: Path) -> None:
        f = tmp_path / "sample.arxml"
        _write_xml(f, _SAMPLE_XML)
        doc = read(f)
        parent = find_elements(
            doc,
            "//ar:ECUC-NUMERICAL-PARAM-VALUE",
            namespaces={"ar": "http://autosar.org/schema/r4.0"},
        )[0]
        set_child_text(parent, "VALUE", "120000000")
        assert get_child_text(parent, "VALUE") == "120000000"

    def test_set_child_text_creates_new(self, tmp_path: Path) -> None:
        f = tmp_path / "sample.arxml"
        _write_xml(f, _SAMPLE_XML)
        doc = read(f)
        parent = find_elements(
            doc,
            "//ar:ECUC-NUMERICAL-PARAM-VALUE",
            namespaces={"ar": "http://autosar.org/schema/r4.0"},
        )[0]
        set_child_text(parent, "NEW-CHILD", "hello")
        assert get_child_text(parent, "NEW-CHILD") == "hello"


# ---------------------------------------------------------------------------
# round-trip
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_write_then_read_preserves_text(self, tmp_path: Path) -> None:
        f = tmp_path / "rt.arxml"
        _write_xml(f, _SAMPLE_XML)
        doc = read(f)
        # 改一个值
        parent = find_elements(
            doc,
            "//ar:ECUC-NUMERICAL-PARAM-VALUE",
            namespaces={"ar": "http://autosar.org/schema/r4.0"},
        )[0]
        set_child_text(parent, "VALUE", "999")
        write(doc, atomic=False)
        # 重新读
        doc2 = read(f)
        parent2 = find_elements(
            doc2,
            "//ar:ECUC-NUMERICAL-PARAM-VALUE",
            namespaces={"ar": "http://autosar.org/schema/r4.0"},
        )[0]
        assert get_child_text(parent2, "VALUE") == "999"
