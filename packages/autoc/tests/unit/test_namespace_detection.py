"""Unit tests for arxml_io dynamic namespace detection (T8.E.1).

Plan reference: Sprint 8.E T8.E.1 — `arxml_io.detect_namespaces()` dynamic probe.
Contract 3: arxml_io namespace detection API (r4.0/r4.2/r4.4/r4.6/r4.7).
Contract 7: test naming + file layout (`TestNamespaceDetection`).

5 namespace fixtures (module-level, **not** in conftest.py) sample r4.0 / r4.2 /
r4.4 / r4.6 / r4.7 URI variants. Each is a minimal ARXML document with a
single ECUC-MODULE-CONFIGURATION-VALUES for unit testing the namespace probe
and downstream xpath/find behavior.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree
import pytest

from autoc.core.bsw.arxml_io import (
    DEFAULT_NAMESPACES,
    WELL_KNOWN_NAMESPACE_URIS,
    build_default_nsmap,
    detect_namespaces,
    find_elements,
    read,
    resolve_namespaces,
)

# ---------------------------------------------------------------------------
# Module-level fixtures: 5 namespace versions (r4.0 / r4.2 / r4.4 / r4.6 / r4.7)
# ---------------------------------------------------------------------------


def _make_module_arxml(uri: str) -> str:
    """生成最小 ARXML（包含一个 ECUC 模块）。"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="{uri}" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>Ecuc</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-CONFIGURATION-VALUES>
          <SHORT-NAME>Mcu</SHORT-NAME>
          <PARAMETER-VALUES>
            <ECUC-NUMERICAL-PARAM-VALUE>
              <DEFINITION-REF DEST="ECUC-INTEGER-PARAM-DEF">/AUTOSAR/EcucDefs/Mcu/McuClockFrequency</DEFINITION-REF>
              <VALUE>80000000</VALUE>
            </ECUC-NUMERICAL-PARAM-VALUE>
          </PARAMETER-VALUES>
        </ECUC-MODULE-CONFIGURATION-VALUES>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
"""


@pytest.fixture
def sample_arxml_r40(tmp_path: Path) -> Path:
    """r4.0 namespace URI 样例。"""
    p = tmp_path / "r40.arxml"
    p.write_text(_make_module_arxml("http://autosar.org/schema/r4.0"), encoding="utf-8")
    return p


@pytest.fixture
def sample_arxml_r42(tmp_path: Path) -> Path:
    """r4.2 namespace URI 样例。"""
    p = tmp_path / "r42.arxml"
    p.write_text(_make_module_arxml("http://autosar.org/schema/r4.2"), encoding="utf-8")
    return p


@pytest.fixture
def sample_arxml_r44(tmp_path: Path) -> Path:
    """r4.4 namespace URI 样例。"""
    p = tmp_path / "r44.arxml"
    p.write_text(_make_module_arxml("http://autosar.org/schema/r4.4"), encoding="utf-8")
    return p


@pytest.fixture
def sample_arxml_r46(tmp_path: Path) -> Path:
    """r4.6 namespace URI 样例。"""
    p = tmp_path / "r46.arxml"
    p.write_text(_make_module_arxml("http://autosar.org/schema/r4.6"), encoding="utf-8")
    return p


@pytest.fixture
def sample_arxml_r47(tmp_path: Path) -> Path:
    """r4.7 namespace URI 样例。"""
    p = tmp_path / "r47.arxml"
    p.write_text(_make_module_arxml("http://autosar.org/schema/r4.7"), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# WELL_KNOWN_NAMESPACE_URIS / DEFAULT_NAMESPACES constant
# ---------------------------------------------------------------------------


class TestWellKnownNamespaceConstants:
    def test_well_known_uris_includes_all_five_versions(self) -> None:
        """WELL_KNOWN_NAMESPACE_URIS 必须含 r4.0/4.2/4.4/4.6/4.7/4.8。"""
        ar_uris = WELL_KNOWN_NAMESPACE_URIS["ar"]
        assert "http://autosar.org/schema/r4.0" in ar_uris
        assert "http://autosar.org/schema/r4.2" in ar_uris
        assert "http://autosar.org/schema/r4.4" in ar_uris
        assert "http://autosar.org/schema/r4.6" in ar_uris
        assert "http://autosar.org/schema/r4.7" in ar_uris
        assert "http://autosar.org/schema/r4.8" in ar_uris

    def test_well_known_uris_includes_xsi(self) -> None:
        """xsi (XMLSchema-instance) 必含。"""
        assert "xsi" in WELL_KNOWN_NAMESPACE_URIS
        assert "http://www.w3.org/2001/XMLSchema-instance" in WELL_KNOWN_NAMESPACE_URIS["xsi"]

    def test_well_known_uris_includes_tresos_d(self) -> None:
        """3soft / EB tresos datamodel 私有 ns 必须含。"""
        assert "d" in WELL_KNOWN_NAMESPACE_URIS
        assert "http://www.3soft.de/xml/tresos/datamodel/1.0" in WELL_KNOWN_NAMESPACE_URIS["d"]

    def test_default_namespaces_alias_matches_well_known(self) -> None:
        """DEFAULT_NAMESPACES 是 WELL_KNOWN_NAMESPACE_URIS 的 alias（向后兼容）。"""
        assert DEFAULT_NAMESPACES is WELL_KNOWN_NAMESPACE_URIS


# ---------------------------------------------------------------------------
# build_default_nsmap
# ---------------------------------------------------------------------------


class TestBuildDefaultNsmap:
    def test_returns_xsi_when_root_has_no_nsmap(self) -> None:
        """空 nsmap 至少含 xsi（per contract）。"""
        root = etree.Element("Root")
        nsmap = build_default_nsmap(root)
        assert "xsi" in nsmap
        assert nsmap["xsi"] == "http://www.w3.org/2001/XMLSchema-instance"

    def test_extracts_default_namespace_as_ar(self) -> None:
        """根 xmlns 默认 ns 必以 'ar' 为 key。"""
        root = etree.Element(
            "AUTOSAR",
            nsmap={None: "http://autosar.org/schema/r4.4"},
        )
        nsmap = build_default_nsmap(root)
        assert nsmap["ar"] == "http://autosar.org/schema/r4.4"

    def test_extracts_xsi_when_present(self) -> None:
        """xsi 在 nsmap 里出现 → 提取。"""
        root = etree.Element(
            "AUTOSAR",
            nsmap={
                None: "http://autosar.org/schema/r4.0",
                "xsi": "http://www.w3.org/2001/XMLSchema-instance",
            },
        )
        nsmap = build_default_nsmap(root)
        assert nsmap["ar"] == "http://autosar.org/schema/r4.0"
        assert nsmap["xsi"] == "http://www.w3.org/2001/XMLSchema-instance"

    def test_preserves_existing_prefixes(self) -> None:
        """自定义 prefix（如 arx）保留。"""
        root = etree.Element(
            "Root",
            nsmap={
                None: "http://autosar.org/schema/r4.2",
                "arx": "http://example.com/custom",
            },
        )
        nsmap = build_default_nsmap(root)
        assert nsmap["arx"] == "http://example.com/custom"


# ---------------------------------------------------------------------------
# resolve_namespaces
# ---------------------------------------------------------------------------


class TestResolveNamespaces:
    def test_returns_dict(self) -> None:
        """resolve_namespaces 走 build_default_nsmap，返回 dict 形态。"""
        root = etree.Element(
            "AUTOSAR",
            nsmap={None: "http://autosar.org/schema/r4.0"},
        )
        nsmap = resolve_namespaces(root)
        assert isinstance(nsmap, dict)
        assert "ar" in nsmap
        assert "xsi" in nsmap


# ---------------------------------------------------------------------------
# detect_namespaces — 5 版本探测
# ---------------------------------------------------------------------------


class TestDetectNamespaces:
    def test_detect_r40_default_namespace(self, sample_arxml_r40: Path) -> None:
        nsmap = detect_namespaces(sample_arxml_r40)
        assert nsmap["ar"] == "http://autosar.org/schema/r4.0"

    def test_detect_r42_default_namespace(self, sample_arxml_r42: Path) -> None:
        nsmap = detect_namespaces(sample_arxml_r42)
        assert nsmap["ar"] == "http://autosar.org/schema/r4.2"

    def test_detect_r44_default_namespace(self, sample_arxml_r44: Path) -> None:
        nsmap = detect_namespaces(sample_arxml_r44)
        assert nsmap["ar"] == "http://autosar.org/schema/r4.4"

    def test_detect_r46_default_namespace(self, sample_arxml_r46: Path) -> None:
        nsmap = detect_namespaces(sample_arxml_r46)
        assert nsmap["ar"] == "http://autosar.org/schema/r4.6"

    def test_detect_r47_default_namespace(self, sample_arxml_r47: Path) -> None:
        nsmap = detect_namespaces(sample_arxml_r47)
        assert nsmap["ar"] == "http://autosar.org/schema/r4.7"

    def test_detect_includes_xsi_always(self, sample_arxml_r44: Path) -> None:
        """xsi 必含（contract 3）。"""
        nsmap = detect_namespaces(sample_arxml_r44)
        assert "xsi" in nsmap
        assert nsmap["xsi"] == "http://www.w3.org/2001/XMLSchema-instance"

    def test_detect_5_of_5_versions(self) -> None:
        """5 个版本全部探测成功（D1 硬验收之一）。"""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            uris = [
                ("r40", "http://autosar.org/schema/r4.0"),
                ("r42", "http://autosar.org/schema/r4.2"),
                ("r44", "http://autosar.org/schema/r4.4"),
                ("r46", "http://autosar.org/schema/r4.6"),
                ("r47", "http://autosar.org/schema/r4.7"),
            ]
            for name, uri in uris:
                p = td_path / f"{name}.arxml"
                p.write_text(_make_module_arxml(uri), encoding="utf-8")
                nsmap = detect_namespaces(p)
                assert nsmap["ar"] == uri, f"{name} URI not detected correctly"


# ---------------------------------------------------------------------------
# detect_namespaces — cache
# ---------------------------------------------------------------------------


class TestDetectNamespacesCache:
    def test_cache_returns_same_dict_for_same_path(self, sample_arxml_r40: Path) -> None:
        """LRU cache：同 path 重复调用返回的 dict 相等。"""
        nsmap1 = detect_namespaces(sample_arxml_r40)
        nsmap2 = detect_namespaces(sample_arxml_r40)
        assert nsmap1 == nsmap2

    def test_cache_recomputes_when_file_modified(self, sample_arxml_r40: Path) -> None:
        """mtime 变化 → cache invalidate → 重新探测。"""
        nsmap1 = detect_namespaces(sample_arxml_r40)
        # 改文件内容 + mtime
        sample_arxml_r40.write_text(
            _make_module_arxml("http://autosar.org/schema/r4.6"),
            encoding="utf-8",
        )
        nsmap2 = detect_namespaces(sample_arxml_r40)
        assert nsmap2["ar"] == "http://autosar.org/schema/r4.6"
        assert nsmap1["ar"] == "http://autosar.org/schema/r4.0"


# ---------------------------------------------------------------------------
# detect_namespaces + find_elements 集成（5 个版本 xpath 命中）
# ---------------------------------------------------------------------------


class TestDetectNamespacesIntegration:
    def test_find_with_detected_nsmap_r40(self, sample_arxml_r40: Path) -> None:
        """detect_namespaces + find_elements：r4.0 xpath 命中。"""
        nsmap = detect_namespaces(sample_arxml_r40)
        doc = read(sample_arxml_r40)
        results = find_elements(
            doc,
            "//ar:ECUC-MODULE-CONFIGURATION-VALUES",
            namespaces=nsmap,
        )
        assert len(results) == 1

    def test_find_with_detected_nsmap_r44(self, sample_arxml_r44: Path) -> None:
        """detect_namespaces + find_elements：r4.4 xpath 命中（旧代码 r4.0 硬编码会 miss）。"""
        nsmap = detect_namespaces(sample_arxml_r44)
        doc = read(sample_arxml_r44)
        results = find_elements(
            doc,
            "//ar:ECUC-MODULE-CONFIGURATION-VALUES",
            namespaces=nsmap,
        )
        assert len(results) == 1

    def test_find_with_detected_nsmap_r47(self, sample_arxml_r47: Path) -> None:
        """detect_namespaces + find_elements：r4.7 xpath 命中。"""
        nsmap = detect_namespaces(sample_arxml_r47)
        doc = read(sample_arxml_r47)
        results = find_elements(
            doc,
            "//ar:VALUE",
            namespaces=nsmap,
        )
        assert len(results) == 1
        assert results[0].text == "80000000"


# ---------------------------------------------------------------------------
# ecuc.load_module 多版本支持
# ---------------------------------------------------------------------------


class TestEcucLoadModuleMultiVersion:
    """ecuc.load_module 必须能从任意 r4.x URI 探测 + 解析。"""

    def test_load_module_r42(self, sample_arxml_r42: Path) -> None:
        from autoc.core.bsw.ecuc import load_module

        doc = load_module(sample_arxml_r42, "Mcu")
        assert doc.module_name == "Mcu"
        assert any(v.path.endswith("McuClockFrequency") for v in doc.values)

    def test_load_module_r46(self, sample_arxml_r46: Path) -> None:
        from autoc.core.bsw.ecuc import load_module

        doc = load_module(sample_arxml_r46, "Mcu")
        assert any("McuClockFrequency" in v.path for v in doc.values)

    def test_load_module_r47(self, sample_arxml_r47: Path) -> None:
        from autoc.core.bsw.ecuc import load_module

        doc = load_module(sample_arxml_r47, "Mcu")
        freq = next((v for v in doc.values if v.path.endswith("McuClockFrequency")), None)
        assert freq is not None
        assert freq.raw == "80000000"
        assert freq.type == "INTEGER"

    def test_set_value_with_explicit_nsmap_r44(self, sample_arxml_r44: Path) -> None:
        """ecuc.set_value 接受显式 nsmap kw（不破坏向后兼容）。"""
        from autoc.core.bsw.ecuc import load_module, set_value

        doc = load_module(sample_arxml_r44, "Mcu")
        # 不传 nsmap → 用默认探测路径；旧调用方不破
        new_doc = set_value(doc, "Mcu/McuClockFrequency", "120000000")
        freq = next(v for v in new_doc.values if v.path.endswith("McuClockFrequency"))
        assert freq.raw == "120000000"
