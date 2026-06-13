"""Unit tests for :mod:`claude_autosar.core.bsw.dispatcher`.

Sprint 9.0 — T9.0.2 验收：3 个样本单测（plan §3.1）。
- detect_format on .arxml (AUTOSAR r4.0) → "arxml"
- detect_format on .xdm (DataModel2 root) → "xdm"
- detect_format on unknown / missing → 抛对应异常
- read() round-trip：dispatcher 不改字节
- expected_format mismatch → FormatMismatchError
- describe() error path 不抛
"""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_autosar.core.bsw.dispatcher import (
    AUTOSAR_NAMESPACES,
    DATAMODEL2_NAMESPACES,
    DispatcherError,
    FormatMismatchError,
    LoadedDocument,
    UnknownFormatError,
    detect_format,
    detect_format_from_tree,
    read,
    write,
    describe,
)

# ---------------------------------------------------------------------------
# Sample XML payloads（与 test_arxml_io / test_datamodel2_io 解耦；本测
# 试只关心 dispatcher 路由选择，不关心内容语义）
# ---------------------------------------------------------------------------

_AUTOSAR_R40_XML = """<?xml version='1.0' encoding='UTF-8'?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <AR-PACKAGES>
    <AR-PACKAGE><SHORT-NAME>BSW</SHORT-NAME></AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
"""

_AUTOSAR_R44_XML = """<?xml version='1.0' encoding='UTF-8'?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.4"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <AR-PACKAGES/>
</AUTOSAR>
"""

_DATAMODEL2_XML = """<?xml version='1.0' encoding='UTF-8'?>
<datamodel version="7.0"
           xmlns="http://www.tresos.de/_projects/DataModel2/16/root.xsd"
           xmlns:a="http://www.tresos.de/_projects/DataModel2/16/attribute.xsd"
           xmlns:d="http://www.tresos.de/_projects/DataModel2/06/data.xsd">
  <d:ctr type="AUTOSAR" factory="autosar">
    <d:lst type="TOP-LEVEL-PACKAGES">
      <d:ctr name="Can" type="AR-PACKAGE">
        <d:lst type="ELEMENTS">
          <d:chc name="Can" type="AR-ELEMENT" value="MODULE-CONFIGURATION"/>
        </d:lst>
      </d:ctr>
    </d:lst>
  </d:ctr>
</datamodel>
"""

_DATAMODEL2_1_0_ALIAS_XML = """<?xml version='1.0' encoding='UTF-8'?>
<DataModel xmlns="http://www.3soft.de/xml/tresos/datamodel/1.0">
  <Module name="Mcu"/>
</DataModel>
"""

_UNKNOWN_NS_XML = """<?xml version='1.0' encoding='UTF-8'?>
<RandomDoc xmlns="http://example.com/not/autosar-or-datamodel2">
  <Element/>
</RandomDoc>
"""

_NO_NS_XML = """<?xml version='1.0' encoding='UTF-8'?>
<NoNamespaceRoot><Child/></NoNamespaceRoot>
"""


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# detect_format
# ---------------------------------------------------------------------------


class TestDetectFormat:
    def test_autosar_r40_detected(self, tmp_path: Path) -> None:
        f = tmp_path / "Mcu.arxml"
        _write(f, _AUTOSAR_R40_XML)
        assert detect_format(f) == "arxml"

    def test_autosar_r44_detected(self, tmp_path: Path) -> None:
        f = tmp_path / "Mcu.arxml"
        _write(f, _AUTOSAR_R44_XML)
        assert detect_format(f) == "arxml"

    def test_datamodel2_root_detected(self, tmp_path: Path) -> None:
        f = tmp_path / "Can.xdm"
        _write(f, _DATAMODEL2_XML)
        assert detect_format(f) == "xdm"

    def test_datamodel2_1_0_alias_detected(self, tmp_path: Path) -> None:
        f = tmp_path / "old.xdm"
        _write(f, _DATAMODEL2_1_0_ALIAS_XML)
        assert detect_format(f) == "xdm"

    def test_unknown_namespace_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "weird.arxml"
        _write(f, _UNKNOWN_NS_XML)
        with pytest.raises(UnknownFormatError) as exc:
            detect_format(f)
        assert "http://example.com/not/autosar-or-datamodel2" in str(exc.value)

    def test_no_namespace_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "non.xml"
        _write(f, _NO_NS_XML)
        with pytest.raises(UnknownFormatError) as exc:
            detect_format(f)
        assert "no default namespace" in str(exc.value).lower()

    def test_missing_file_raises_filenotfound(self, tmp_path: Path) -> None:
        f = tmp_path / "ghost.xdm"
        with pytest.raises(FileNotFoundError):
            detect_format(f)

    def test_well_known_sets_have_real_uris(self) -> None:
        # 防止有人误删常量定义
        assert "http://autosar.org/schema/r4.0" in AUTOSAR_NAMESPACES
        assert "http://www.tresos.de/_projects/DataModel2/16/root.xsd" in DATAMODEL2_NAMESPACES
        assert "http://www.3soft.de/xml/tresos/datamodel/1.0" in DATAMODEL2_NAMESPACES


class TestDetectFormatFromTree:
    """从已加载 tree 探测（无 IO；ecuc.load_module 优化路径）。"""

    def test_arxml_tree(self) -> None:
        from lxml import etree

        # fromstring 返回 _Element；dispatcher 同时接受 _Element 和 _ElementTree
        root = etree.fromstring(_AUTOSAR_R40_XML.encode("utf-8"))
        assert detect_format_from_tree(root) == "arxml"

    def test_xdm_tree(self) -> None:
        from lxml import etree

        root = etree.fromstring(_DATAMODEL2_XML.encode("utf-8"))
        assert detect_format_from_tree(root) == "xdm"

    def test_elementtree_wrapper_arxml(self, tmp_path: Path) -> None:
        """ElementTree 包装（etree.parse 路径）也能 work。"""
        from lxml import etree

        f = tmp_path / "Mcu.arxml"
        f.write_text(_AUTOSAR_R40_XML, encoding="utf-8")
        tree = etree.parse(str(f))
        assert detect_format_from_tree(tree) == "arxml"

    def test_fallback_when_getroot_returns_none(self) -> None:
        """防御：getroot() 返回 None 时退回 tree 本身（死代码分支但保留）。"""
        # 构造一个伪 _ElementTree 替身：getroot() 返回 None
        class _FakeTree:
            def getroot(self) -> None:
                return None

        # 这会触发 line 128 fallback，但因 _FakeTree 无 nsmap，root = _FakeTree
        # 上仍没有 nsmap 属性 → _classify_uri 收到 None → 抛 UnknownFormatError
        with pytest.raises(UnknownFormatError):
            detect_format_from_tree(_FakeTree())


# ---------------------------------------------------------------------------
# read() — round-trip dispatcher
# ---------------------------------------------------------------------------


class TestRead:
    def test_read_arxml_returns_loaded_document(self, tmp_path: Path) -> None:
        f = tmp_path / "Mcu.arxml"
        _write(f, _AUTOSAR_R40_XML)
        doc = read(f)
        assert isinstance(doc, LoadedDocument)
        assert doc.format == "arxml"
        assert doc.path == f
        # tree 应可 getroot()
        root = doc.tree.getroot()
        assert root.tag.endswith("AUTOSAR")

    def test_read_xdm_returns_loaded_document(self, tmp_path: Path) -> None:
        f = tmp_path / "Can.xdm"
        _write(f, _DATAMODEL2_XML)
        doc = read(f)
        assert isinstance(doc, LoadedDocument)
        assert doc.format == "xdm"
        assert doc.path == f
        root = doc.tree.getroot()
        assert "DataModel2" in root.tag or root.tag == "datamodel"

    def test_read_with_expected_format_arxml_matches(self, tmp_path: Path) -> None:
        f = tmp_path / "Mcu.arxml"
        _write(f, _AUTOSAR_R40_XML)
        doc = read(f, expected_format="arxml")
        assert doc.format == "arxml"

    def test_read_with_expected_format_mismatch_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "Mcu.arxml"
        _write(f, _AUTOSAR_R40_XML)
        with pytest.raises(FormatMismatchError) as exc:
            read(f, expected_format="xdm")
        assert "xdm" in str(exc.value) and "arxml" in str(exc.value)

    def test_read_with_expected_format_xdm_on_xdm(self, tmp_path: Path) -> None:
        f = tmp_path / "Can.xdm"
        _write(f, _DATAMODEL2_XML)
        doc = read(f, expected_format="xdm")
        assert doc.format == "xdm"


# ---------------------------------------------------------------------------
# write() — round-trip preserves bytes
# ---------------------------------------------------------------------------


class TestWrite:
    def test_write_arxml_roundtrip(self, tmp_path: Path) -> None:
        f = tmp_path / "Mcu.arxml"
        _write(f, _AUTOSAR_R40_XML)
        doc = read(f)
        write(doc)  # 不改字节
        # 文件还能再 read，root tag 仍 AUTOSAR
        doc2 = read(f)
        assert doc2.format == "arxml"
        assert doc2.tree.getroot().tag.endswith("AUTOSAR")

    def test_write_xdm_roundtrip(self, tmp_path: Path) -> None:
        f = tmp_path / "Can.xdm"
        _write(f, _DATAMODEL2_XML)
        doc = read(f)
        write(doc)
        # byte-identity ≥ 99%（Sprint 8.E.5 验收同标准；这里只检查可 round-trip）
        after = f.read_bytes()
        assert b"DataModel2" in after  # 内容没丢
        # 不要求 byte-level 严格相等（surgical patch 允许 DOS/comment/PI 差异）

    def test_write_arxml_with_bare_elementtree_falls_back(self, tmp_path: Path) -> None:
        """doc.tree 是裸 _ElementTree（不是 ARXMLDocument）时，write() 走兜底分支。"""
        from lxml import etree

        f = tmp_path / "Mcu.arxml"
        _write(f, _AUTOSAR_R40_XML)
        bare_tree = etree.parse(str(f))
        doc = LoadedDocument(path=f, format="arxml", tree=bare_tree)
        write(doc)  # 走 line 209 兜底：包成 ARXMLDocument
        # 文件还在，root tag 是 AUTOSAR
        doc2 = read(f)
        assert doc2.format == "arxml"
        assert doc2.tree.getroot().tag.endswith("AUTOSAR")


# ---------------------------------------------------------------------------
# describe() — non-throwing wrapper
# ---------------------------------------------------------------------------


class TestDescribe:
    def test_describe_arxml(self, tmp_path: Path) -> None:
        f = tmp_path / "Mcu.arxml"
        _write(f, _AUTOSAR_R40_XML)
        out = describe(f)
        assert out["success"] is True
        assert out["format"] == "arxml"
        assert out["path"] == str(f)

    def test_describe_xdm(self, tmp_path: Path) -> None:
        f = tmp_path / "Can.xdm"
        _write(f, _DATAMODEL2_XML)
        out = describe(f)
        assert out["success"] is True
        assert out["format"] == "xdm"

    def test_describe_missing_file(self, tmp_path: Path) -> None:
        f = tmp_path / "ghost.xdm"
        out = describe(f)
        assert out["success"] is False
        assert "FileNotFoundError" in out["error"]

    def test_describe_unknown_format(self, tmp_path: Path) -> None:
        f = tmp_path / "weird.arxml"
        _write(f, _UNKNOWN_NS_XML)
        out = describe(f)
        assert out["success"] is False
        assert "neither AUTOSAR nor DataModel2" in out["error"]


# ---------------------------------------------------------------------------
# Error type hierarchy
# ---------------------------------------------------------------------------


class TestExceptions:
    def test_unknown_format_is_dispatcher_error(self) -> None:
        assert issubclass(UnknownFormatError, DispatcherError)

    def test_format_mismatch_is_dispatcher_error(self) -> None:
        assert issubclass(FormatMismatchError, DispatcherError)

    def test_format_mismatch_is_value_error(self) -> None:
        # DispatcherError 继承 ValueError，调用方 catch ValueError 即可
        assert issubclass(DispatcherError, ValueError)
