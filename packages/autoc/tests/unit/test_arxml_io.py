"""Unit tests for packages/autoc/src/autoc/core/bsw/arxml_io.py.

TDD 阶段：RED（先写测试）。Sprint 3 — T3.1。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from claude_autosar.core.bsw.arxml_io import (
    ARXMLDocument,
    ARXMLError,
    _cached_parse,
    _invalidate_cache,
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
                "claude_autosar.core.bsw.io.xml_io_base.os.replace",
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


# ---------------------------------------------------------------------------
# parse cache (_cached_parse / _invalidate_cache)
# ---------------------------------------------------------------------------


class TestParseCache:
    """Document-level parse cache: _cached_parse with mtime-based invalidation."""

    def setup_method(self) -> None:
        """每个测试前清空缓存，避免跨测试干扰。"""
        _cached_parse.cache_clear()

    def test_read_cache_hit(self, tmp_path: Path) -> None:
        """读同一文件两次，_safe_parse 只应被调用一次（第二次走缓存）。"""
        f = tmp_path / "cached.arxml"
        _write_xml(f, _SAMPLE_XML)

        with patch(
            "claude_autosar.core.bsw.arxml_io._safe_parse",
            wraps=__import__(
                "claude_autosar.core.bsw.arxml_io", fromlist=["_safe_parse"]
            )._safe_parse,
        ) as mock_parse:
            doc1 = read(f)
            doc2 = read(f)

        # _safe_parse 只调一次（第二次命中缓存）
        assert mock_parse.call_count == 1
        # 两次返回的 tree 应该是同一个对象（缓存命中）
        assert doc1.tree is doc2.tree

    def test_read_cache_miss_on_mtime_change(self, tmp_path: Path) -> None:
        """文件 mtime 变化后，缓存应失效，读到新内容。"""
        f = tmp_path / "mtime.arxml"
        _write_xml(f, _SAMPLE_XML)

        doc1 = read(f)
        root1 = doc1.tree.getroot()

        # 修改文件内容（mtime 会随之变化）
        new_xml = _SAMPLE_XML.replace("<VALUE>80000000</VALUE>", "<VALUE>99999999</VALUE>")
        _write_xml(f, new_xml)

        doc2 = read(f)
        root2 = doc2.tree.getroot()

        # 新文件应包含修改后的值
        value_elems = root2.iter()
        found_new_value = False
        for elem in value_elems:
            if isinstance(elem.tag, str) and elem.text == "99999999":
                found_new_value = True
                break
        assert found_new_value, "缓存未失效：读到的仍是旧内容"
        # tree 不应是同一个对象
        assert doc1.tree is not doc2.tree

    def test_write_invalidates_cache(self, tmp_path: Path) -> None:
        """write() 后再 read() 应该拿到新内容（缓存被清除）。"""
        f = tmp_path / "write_inv.arxml"
        _write_xml(f, _SAMPLE_XML)

        doc = read(f)
        # 修改值
        parent = find_elements(
            doc,
            "//ar:ECUC-NUMERICAL-PARAM-VALUE",
            namespaces={"ar": "http://autosar.org/schema/r4.0"},
        )[0]
        set_child_text(parent, "VALUE", "42")
        write(doc, atomic=False)

        # 重新读 —— 应该拿到写入的新值
        doc2 = read(f)
        parent2 = find_elements(
            doc2,
            "//ar:ECUC-NUMERICAL-PARAM-VALUE",
            namespaces={"ar": "http://autosar.org/schema/r4.0"},
        )[0]
        assert get_child_text(parent2, "VALUE") == "42"

    def test_cache_size_limit(self, tmp_path: Path) -> None:
        """读 65 个不同文件后，缓存满（maxsize=64），最早的条目应被 evict。"""
        _cached_parse.cache_clear()
        assert _cached_parse.cache_info().maxsize == 64

        paths: list[Path] = []
        for i in range(65):
            f = tmp_path / f"file_{i}.arxml"
            _write_xml(f, _SAMPLE_XML)
            paths.append(f)

        # 依次读取 65 个文件
        for p in paths:
            read(p)

        info = _cached_parse.cache_info()
        # 缓存满，hits + misses 应该反映了 65 次 miss
        assert info.misses == 65
        assert info.currsize <= 64

    def test_invalidate_cache_clears_all(self, tmp_path: Path) -> None:
        """_invalidate_cache 应清空整个缓存。"""
        f = tmp_path / "inv.arxml"
        _write_xml(f, _SAMPLE_XML)
        read(f)
        assert _cached_parse.cache_info().currsize >= 1

        _invalidate_cache(f)
        assert _cached_parse.cache_info().currsize == 0
