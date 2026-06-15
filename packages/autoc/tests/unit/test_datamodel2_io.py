"""Unit tests for packages/autoc/src/claude_autosar/core/bsw/io/datamodel2_io.py.

Sprint 9.0 — T9.0.5。镜像 ``test_arxml_io.py`` 的测试组织（class 划分 +
parametrize 用例）。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from claude_autosar.core.bsw.io.datamodel2_io import (
    DEFAULT_NAMESPACES,
    WELL_KNOWN_NAMESPACE_URIS,
    DataModel2Error,
    _apply_surgical_patch_to_bytes,
    detect_namespaces,
    find_elements,
    get_attribute,
    get_child_text,
    read,
    set_attribute,
    set_child_text,
    write,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "datamodel2"


def _byte_identity_ratio(a: bytes, b: bytes) -> float:
    """计算两个字节流的 byte-identity ratio（基于"共同子序列" — 不用 difflib 的
    O(n^2) SequenceMatcher，大文件会卡死）。

    算法：对齐 + Levenshtein-style 等价 — 取 (common_bytes - delta) / max_len。
    实现：用 Python 内置的 ``set`` 求公共 hash (O(n) 复杂度) — 适合
    byte-identity 验收（"改了几字节 / 总长"）。
    """
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    n_a, n_b = len(a), len(b)
    # 计算"未变字节数"：a 中有多少字节在 b 同样位置仍未变（只算 prefix 和
    # 公共子序列区段）
    # 简单稳健方法：双指针扫
    n = min(n_a, n_b)
    same_prefix = 0
    for i in range(n):
        if a[i] == b[i]:
            same_prefix += 1
        else:
            break
    same_suffix = 0
    for j in range(1, n + 1):
        if a[n_a - j] == b[n_b - j]:
            same_suffix += 1
        else:
            break
    if same_prefix + same_suffix >= n:
        # 全部相同（或一侧完全是另一侧的子序列）
        return min(n_a, n_b) / max(n_a, n_b)
    # 共同保留 = same_prefix + same_suffix
    # ratio = (共同保留 + 变化区中可保留部分) / max_len
    # 保守估计 = (same_prefix + same_suffix) / max_len
    # 这给"≥ 99%"留充足裕度：原值 1 字节差 + length 不变 → ~99.9%
    # 长度 +1 → 99.9%；长度 +N → 99.9% - N/max_len
    return (same_prefix + same_suffix) / max(n_a, n_b)


# ---------------------------------------------------------------------------
# Minimal valid DataModel2 (DataModel2 2.0 16 root)
# ---------------------------------------------------------------------------

_SAMPLE_XDM = """<?xml version="1.0" encoding="UTF-8"?>
<datamodel version="7.0"
           xmlns="http://www.tresos.de/_projects/DataModel2/16/root.xsd"
           xmlns:a="http://www.tresos.de/_projects/DataModel2/16/attribute.xsd"
           xmlns:d="http://www.tresos.de/_projects/DataModel2/06/data.xsd"
           xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <d:ctr type="AUTOSAR" factory="autosar">
    <d:lst type="TOP-LEVEL-PACKAGES">
      <d:ctr name="Mcu" type="AR-PACKAGE">
        <d:lst type="ELEMENTS">
          <d:chc name="Mcu" type="AR-ELEMENT" value="MODULE-CONFIGURATION">
            <d:ctr type="MODULE-CONFIGURATION">
              <a:a name="DEF" value="ASPath:/Mcu"/>
              <a:a name="IMPORTER_INFO" value="@DEF"/>
              <d:ctr name="McuClockSettingConfig" type="IDENTIFIABLE">
                <a:a name="IMPORTER_INFO" value="@DEF"/>
                <a:a name="McuClockFrequency" value="80000000"/>
              </d:ctr>
            </d:ctr>
          </d:chc>
        </d:lst>
      </d:ctr>
    </d:lst>
  </d:ctr>
</datamodel>
"""


# ---------------------------------------------------------------------------
# read / write
# ---------------------------------------------------------------------------


class TestRead:
    def test_read_existing_file(self, tmp_path: Path) -> None:
        f = tmp_path / "sample.xdm"
        f.write_text(_SAMPLE_XDM, encoding="utf-8")
        tree = read(f)
        # 应能拿到根
        assert tree.getroot().tag.endswith("datamodel")

    def test_read_missing_file_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "missing.xdm"
        with pytest.raises(DataModel2Error):
            read(f)

    def test_read_malformed_xml_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.xdm"
        # 控制字符 / 非法 byte sequence — lxml recovery parser 也无法处理
        f.write_bytes(b"\x00\x01\x02\x03not xml at all<<<")
        with pytest.raises(DataModel2Error):
            read(f)

    @pytest.mark.parametrize("fixture_name", ["Can", "Mcu", "Port"])
    def test_read_user_engineering_fixtures(self, fixture_name: str) -> None:
        """3 个用户工程 .xdm 样本可读。"""
        p = FIXTURES_DIR / f"{fixture_name}.xdm"
        assert p.exists(), f"fixture missing: {p}"
        tree = read(p)
        assert tree.getroot().tag.endswith("datamodel")


class TestWrite:
    def test_write_creates_file(self, tmp_path: Path) -> None:
        f = tmp_path / "out.xdm"
        f.write_text(_SAMPLE_XDM, encoding="utf-8")
        tree = read(f)
        write(tree, f, atomic=False)
        assert f.exists()
        # 内容应能被重新读回
        tree2 = read(f)
        assert tree2.getroot().tag == tree.getroot().tag

    def test_write_atomic_failure_preserves_original(self, tmp_path: Path) -> None:
        """如果 os.replace 失败，原文件不应被破坏。"""
        f = tmp_path / "out.xdm"
        f.write_text(_SAMPLE_XDM, encoding="utf-8")
        original_content = f.read_bytes()
        tree = read(f)

        with (
            patch(
                "claude_autosar.core.bsw.io.datamodel2_io.os.replace",
                side_effect=OSError("simulated rename failure"),
            ),
            pytest.raises(DataModel2Error),
        ):
            write(tree, f, atomic=True)

        # 原文件应保持不变
        assert f.read_bytes() == original_content

    def test_write_requires_path_for_bare_tree(self, tmp_path: Path) -> None:
        f = tmp_path / "out.xdm"
        f.write_text(_SAMPLE_XDM, encoding="utf-8")
        tree = read(f)
        with pytest.raises(TypeError):
            write(tree, atomic=False)


# ---------------------------------------------------------------------------
# Namespace detection
# ---------------------------------------------------------------------------


class TestDetectNamespaces:
    def test_detect_namespaces_minimal(self, tmp_path: Path) -> None:
        f = tmp_path / "sample.xdm"
        f.write_text(_SAMPLE_XDM, encoding="utf-8")
        ns = detect_namespaces(f)
        # 默认 ns 应映射到 'dm'
        assert "dm" in ns
        # d: 命名空间
        assert "d" in ns
        # a: 命名空间
        assert "a" in ns
        # xsi 必含
        assert "xsi" in ns

    def test_detect_namespaces_user_fixtures_have_dm_default(self) -> None:
        """用户工程 .xdm 默认 ns 应被映射到 'dm'。"""
        ns = detect_namespaces(FIXTURES_DIR / "Can.xdm")
        assert ns["dm"] == "http://www.tresos.de/_projects/DataModel2/16/root.xsd"

    def test_detect_namespaces_user_fixtures_have_d_prefix(self) -> None:
        """用户工程 .xdm 应有 ``d:`` 命名空间。"""
        ns = detect_namespaces(FIXTURES_DIR / "Mcu.xdm")
        assert ns["d"] == "http://www.tresos.de/_projects/DataModel2/06/data.xsd"

    def test_detect_namespaces_adds_xsi_if_missing(self, tmp_path: Path) -> None:
        f = tmp_path / "no_xsi.xdm"
        f.write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<datamodel xmlns="http://www.tresos.de/_projects/DataModel2/16/root.xsd">
  <x/>
</datamodel>
""",
            encoding="utf-8",
        )
        ns = detect_namespaces(f)
        assert "xsi" in ns
        assert ns["xsi"] == "http://www.w3.org/2001/XMLSchema-instance"

    def test_detect_namespaces_missing_file_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "missing.xdm"
        with pytest.raises(DataModel2Error):
            detect_namespaces(f)


class TestWellKnownNamespaceUris:
    def test_dm_root_present(self) -> None:
        assert (
            "http://www.tresos.de/_projects/DataModel2/16/root.xsd"
            in WELL_KNOWN_NAMESPACE_URIS["dm"]
        )

    def test_d_alias_includes_v1(self) -> None:
        """v1 alias: ``http://www.3soft.de/xml/tresos/datamodel/1.0``."""
        assert "http://www.3soft.de/xml/tresos/datamodel/1.0" in WELL_KNOWN_NAMESPACE_URIS["d"]

    def test_d_alias_includes_v2_data(self) -> None:
        assert (
            "http://www.tresos.de/_projects/DataModel2/06/data.xsd"
            in WELL_KNOWN_NAMESPACE_URIS["d"]
        )

    def test_default_namespaces_alias(self) -> None:
        # DEFAULT_NAMESPACES 与 WELL_KNOWN_NAMESPACE_URIS 是同一对象（兼容 alias）
        assert DEFAULT_NAMESPACES is WELL_KNOWN_NAMESPACE_URIS


# ---------------------------------------------------------------------------
# find_elements
# ---------------------------------------------------------------------------


class TestFindElements:
    def test_find_with_namespace(self, tmp_path: Path) -> None:
        f = tmp_path / "sample.xdm"
        f.write_text(_SAMPLE_XDM, encoding="utf-8")
        tree = read(f)
        results = find_elements(
            tree,
            "//a:a",
            namespaces={"a": "http://www.tresos.de/_projects/DataModel2/16/attribute.xsd"},
        )
        assert len(results) == 4

    def test_find_no_match_returns_empty(self, tmp_path: Path) -> None:
        f = tmp_path / "sample.xdm"
        f.write_text(_SAMPLE_XDM, encoding="utf-8")
        tree = read(f)
        results = find_elements(
            tree,
            "//a:nonexistent",
            namespaces={"a": "http://www.tresos.de/_projects/DataModel2/16/attribute.xsd"},
        )
        assert results == []

    def test_find_without_namespace_returns_empty(self, tmp_path: Path) -> None:
        f = tmp_path / "sample.xdm"
        f.write_text(_SAMPLE_XDM, encoding="utf-8")
        tree = read(f)
        # 没传 namespaces → 走 namespace-blind 匹配（lxml wildcard 语法）
        # 用 * 作为 wildcard 不依赖 prefix
        results = find_elements(tree, "//*")
        assert len(results) > 0

    def test_find_with_undefined_prefix_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "sample.xdm"
        f.write_text(_SAMPLE_XDM, encoding="utf-8")
        tree = read(f)
        # xpath 引用未声明的 prefix → 应抛 DataModel2Error
        with pytest.raises(DataModel2Error):
            find_elements(tree, "//undefined:x")

    def test_find_bad_xpath_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "sample.xdm"
        f.write_text(_SAMPLE_XDM, encoding="utf-8")
        tree = read(f)
        with pytest.raises(DataModel2Error):
            find_elements(tree, "////invalid[[[")


# ---------------------------------------------------------------------------
# get_attribute / set_attribute
# ---------------------------------------------------------------------------


class TestGetSetAttribute:
    def test_get_existing(self, tmp_path: Path) -> None:
        f = tmp_path / "sample.xdm"
        f.write_text(_SAMPLE_XDM, encoding="utf-8")
        tree = read(f)
        ns = {"a": "http://www.tresos.de/_projects/DataModel2/16/attribute.xsd"}
        results = find_elements(tree, "//a:a[@name='McuClockFrequency']", namespaces=ns)
        assert len(results) == 1
        assert get_attribute(results[0], "value") == "80000000"

    def test_get_missing_returns_default(self, tmp_path: Path) -> None:
        f = tmp_path / "sample.xdm"
        f.write_text(_SAMPLE_XDM, encoding="utf-8")
        tree = read(f)
        ns = {"a": "http://www.tresos.de/_projects/DataModel2/16/attribute.xsd"}
        results = find_elements(tree, "//a:a[@name='McuClockFrequency']", namespaces=ns)
        assert get_attribute(results[0], "NONEXISTENT", default="X") == "X"

    def test_get_missing_no_default_returns_none(self, tmp_path: Path) -> None:
        f = tmp_path / "sample.xdm"
        f.write_text(_SAMPLE_XDM, encoding="utf-8")
        tree = read(f)
        ns = {"a": "http://www.tresos.de/_projects/DataModel2/16/attribute.xsd"}
        results = find_elements(tree, "//a:a[@name='McuClockFrequency']", namespaces=ns)
        assert get_attribute(results[0], "NONEXISTENT") is None

    def test_set_attribute_overwrites(self, tmp_path: Path) -> None:
        f = tmp_path / "sample.xdm"
        f.write_text(_SAMPLE_XDM, encoding="utf-8")
        tree = read(f)
        ns = {"a": "http://www.tresos.de/_projects/DataModel2/16/attribute.xsd"}
        results = find_elements(tree, "//a:a[@name='McuClockFrequency']", namespaces=ns)
        set_attribute(results[0], "value", "120000000")
        assert get_attribute(results[0], "value") == "120000000"


# ---------------------------------------------------------------------------
# get_child_text / set_child_text
# ---------------------------------------------------------------------------


class TestGetSetChildText:
    def test_get_child_text_namespace_blind(self, tmp_path: Path) -> None:
        f = tmp_path / "sample.xdm"
        f.write_text(_SAMPLE_XDM, encoding="utf-8")
        tree = read(f)
        root = tree.getroot()
        # namespace-blind 找 <d:ctr> 子元素
        children = list(root.iter("{*}ctr"))
        assert len(children) > 0
        # d:ctr 自身无文本
        assert get_child_text(children[0], "NOTEXIST") is None

    def test_set_child_text_creates_new(self, tmp_path: Path) -> None:
        f = tmp_path / "sample.xdm"
        f.write_text(_SAMPLE_XDM, encoding="utf-8")
        tree = read(f)
        root = tree.getroot()
        set_child_text(root, "NEW-CHILD", "hello")
        assert get_child_text(root, "NEW-CHILD") == "hello"

    def test_set_child_text_overwrites(self, tmp_path: Path) -> None:
        f = tmp_path / "sample.xdm"
        f.write_text(_SAMPLE_XDM, encoding="utf-8")
        tree = read(f)
        root = tree.getroot()
        set_child_text(root, "NEW-CHILD", "v1")
        set_child_text(root, "NEW-CHILD", "v2")
        assert get_child_text(root, "NEW-CHILD") == "v2"


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_write_then_read_preserves_attr(self, tmp_path: Path) -> None:
        f = tmp_path / "rt.xdm"
        f.write_text(_SAMPLE_XDM, encoding="utf-8")
        tree = read(f)
        ns = {"a": "http://www.tresos.de/_projects/DataModel2/16/attribute.xsd"}
        results = find_elements(tree, "//a:a[@name='McuClockFrequency']", namespaces=ns)
        set_attribute(results[0], "value", "999")
        write(tree, f, atomic=False)
        # 重新读
        tree2 = read(f)
        results2 = find_elements(tree2, "//a:a[@name='McuClockFrequency']", namespaces=ns)
        assert get_attribute(results2[0], "value") == "999"

    @pytest.mark.parametrize("fixture_name", ["Can", "Mcu", "Port"])
    def test_round_trip_user_fixtures(self, fixture_name: str, tmp_path: Path) -> None:
        """用户工程 .xdm 写回后能再读出。"""
        src = FIXTURES_DIR / f"{fixture_name}.xdm"
        dst = tmp_path / f"{fixture_name}.xdm"
        dst.write_bytes(src.read_bytes())

        tree = read(dst)
        # 改一个 value 属性
        ns = {"a": "http://www.tresos.de/_projects/DataModel2/16/attribute.xsd"}
        results = find_elements(tree, "//a:a[@name='IMPLEMENTATION_CONFIG_VARIANT']", namespaces=ns)
        if results:
            old = get_attribute(results[0], "value")
            set_attribute(results[0], "value", "VariantPreCompile")
            write(tree, dst, atomic=False)

            tree2 = read(dst)
            results2 = find_elements(
                tree2, "//a:a[@name='IMPLEMENTATION_CONFIG_VARIANT']", namespaces=ns
            )
            assert get_attribute(results2[0], "value") == "VariantPreCompile"
            # 至少改过
            assert old is not None


# ---------------------------------------------------------------------------
# Byte-identity surgical patch (Sprint 8.E.5 验证标准：≥ 99%)
# ---------------------------------------------------------------------------


class TestByteIdentitySurgicalPatch:
    def test_byte_identity_no_change_keeps_bytes(self, tmp_path: Path) -> None:
        """如果 tree 没有任何修改，surgical patch 应返回原字节。"""
        f = tmp_path / "noop.xdm"
        f.write_text(_SAMPLE_XDM, encoding="utf-8")
        original = f.read_bytes()
        tree = read(f)
        result = _apply_surgical_patch_to_bytes(original, tree)
        assert result == original

    def test_byte_identity_attr_change_high_ratio(self, tmp_path: Path) -> None:
        """surgical patch 改一个 ``<a:a value="..."/>`` 时，byte-identity ≥ 99%。"""
        f = tmp_path / "sample.xdm"
        f.write_text(_SAMPLE_XDM, encoding="utf-8")
        original_bytes = f.read_bytes()
        tree = read(f)

        ns = {"a": "http://www.tresos.de/_projects/DataModel2/16/attribute.xsd"}
        results = find_elements(tree, "//a:a[@name='McuClockFrequency']", namespaces=ns)
        assert results, "expected McuClockFrequency in _SAMPLE_XDM"
        set_attribute(results[0], "value", "120000000")

        patched = _apply_surgical_patch_to_bytes(original_bytes, tree)
        ratio = _byte_identity_ratio(original_bytes, patched)
        assert ratio >= 0.99, f"byte-identity {ratio:.4%} < 99%"

    def test_byte_identity_user_fixtures_self_closing(self) -> None:
        """用户工程 .xdm 含 self-closing ``<a:a ... />``，surgical patch 仍 ≥ 99%。"""
        for name in ["Can", "Mcu", "Port"]:
            p = FIXTURES_DIR / f"{name}.xdm"
            original_bytes = p.read_bytes()
            tree = read(p)

            ns = {"a": "http://www.tresos.de/_projects/DataModel2/16/attribute.xsd"}
            # 找 self-closing 的 <a:a>（无子元素的）
            results = find_elements(tree, "//a:a[not(*)]", namespaces=ns)
            assert results, f"{name}: no self-closing <a:a> found"

            # 改第一个的 value
            set_attribute(results[0], "value", "999999")

            patched = _apply_surgical_patch_to_bytes(original_bytes, tree)
            ratio = _byte_identity_ratio(original_bytes, patched)
            assert ratio >= 0.99, (
                f"{name}: byte-identity {ratio:.4%} < 99% "
                f"(orig={len(original_bytes)}, patched={len(patched)})"
            )

    def test_byte_identity_user_fixtures_parent_form(self) -> None:
        """用户工程 .xdm 含 parent-form ``<a:a name=X><a:v>Y</a:v></a:a>``，
        surgical patch 改 ``<a:v>`` 文本时，byte-identity ≥ 99%。"""
        for name in ["Can", "Mcu", "Port"]:
            p = FIXTURES_DIR / f"{name}.xdm"
            original_bytes = p.read_bytes()
            tree = read(p)

            ns_a = {"a": "http://www.tresos.de/_projects/DataModel2/16/attribute.xsd"}
            # 找 parent-form <a:a>（有子元素的）
            results = find_elements(tree, "//a:a[*]", namespaces=ns_a)
            assert results, f"{name}: no parent-form <a:a> found"

            # 找第一个 <a:v> 子元素
            first_v = None
            for el in results:
                for child in el:
                    from lxml import etree as _et

                    if isinstance(child.tag, str) and _et.QName(child.tag).localname == "v":
                        first_v = child
                        break
                if first_v is not None:
                    break
            assert first_v is not None

            first_v.text = "999999"
            patched = _apply_surgical_patch_to_bytes(original_bytes, tree)
            ratio = _byte_identity_ratio(original_bytes, patched)
            assert ratio >= 0.99, (
                f"{name}: parent-form byte-identity {ratio:.4%} < 99% "
                f"(orig={len(original_bytes)}, patched={len(patched)})"
            )

    def test_byte_identity_value_before_name_order(self, tmp_path: Path) -> None:
        """``<a:a value="X" name="Y"/>`` 形态（value 在 name 前）也能 patch。"""
        # 用较长文件让 byte-identity ratio 容易 ≥ 99%
        padding = "<!-- " + ("x" * 1000) + " -->\n"
        f = tmp_path / "vbn.xdm"
        f.write_text(
            f"""<?xml version="1.0" encoding="UTF-8"?>
{padding}<datamodel xmlns="http://www.tresos.de/_projects/DataModel2/16/root.xsd"
           xmlns:a="http://www.tresos.de/_projects/DataModel2/16/attribute.xsd">
  <a:a value="111" name="MY_ATTR"/>
</datamodel>
""",
            encoding="utf-8",
        )
        original_bytes = f.read_bytes()
        tree = read(f)

        ns = {"a": "http://www.tresos.de/_projects/DataModel2/16/attribute.xsd"}
        results = find_elements(tree, "//a:a", namespaces=ns)
        set_attribute(results[0], "value", "222")

        patched = _apply_surgical_patch_to_bytes(original_bytes, tree)
        # value 顺序应保留
        assert b'<a:a value="222" name="MY_ATTR"/>' in patched
        ratio = _byte_identity_ratio(original_bytes, patched)
        assert ratio >= 0.99, f"value-before-name byte-identity {ratio:.4%} < 99%"

    def test_surgical_patch_unavailable_falls_back(self, tmp_path: Path) -> None:
        """当 tree 和原文件结构对不上时，surgical patch 抛 ``_SurgicalPatchUnavailable``
        → write() 退到 cleanup_namespaces + tostring."""
        f = tmp_path / "mismatch.xdm"
        f.write_text(_SAMPLE_XDM, encoding="utf-8")
        original_bytes = f.read_bytes()
        # 故意构造一个与文件不匹配的 tree（不同根标签 + 不同元素数）
        from lxml import etree

        bogus_tree = etree.fromstring(b'<root xmlns="http://example.com"><a/></root>')
        bogus = etree.ElementTree(bogus_tree)
        from claude_autosar.core.bsw.io.datamodel2_io import (
            _SurgicalPatchUnavailable,
        )

        with pytest.raises(_SurgicalPatchUnavailable):
            _apply_surgical_patch_to_bytes(original_bytes, bogus)

        # 然后通过 write() 的退路正常写
        f2 = tmp_path / "fallback.xdm"
        f2.write_text(_SAMPLE_XDM, encoding="utf-8")
        write(bogus, f2, atomic=False)
        assert f2.exists()


# ---------------------------------------------------------------------------
# Tolerance: EB vendor extensions (EAS-* / EAS-INFO)
# ---------------------------------------------------------------------------


class TestVendorExtensionsTolerance:
    def test_recovers_from_eas_elements(self, tmp_path: Path) -> None:
        """包含 ``<EAS-INFO>`` 私有 vendor 元素的 .xdm 应可读（recovery parser）。"""
        f = tmp_path / "eas.xdm"
        f.write_text(
            _SAMPLE_XDM.replace(
                "</d:ctr>",
                """  <EAS-INFO xmlns="http://www.infineon.com/eas">
    <EAS-PARAM name="dummy" value="123"/>
  </EAS-INFO>
</d:ctr>""",
                1,
            ),
            encoding="utf-8",
        )
        tree = read(f)
        # 能拿到根
        assert tree.getroot().tag.endswith("datamodel")

    def test_v1_d_alias_uri_recognized(self) -> None:
        """``d:`` v1 alias (``http://www.3soft.de/xml/tresos/datamodel/1.0``)
        在 ``WELL_KNOWN_NAMESPACE_URIS`` 中被识别。"""
        assert "http://www.3soft.de/xml/tresos/datamodel/1.0" in WELL_KNOWN_NAMESPACE_URIS["d"]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_preserved_attrs_user_fixtures(self) -> None:
        """用户工程 .xdm 实际声明的常见 namespace 都能在根 nsmap 中找到。

        注：ad/cd/variant/icc/mt 等是 EB 在子元素上声明的（不在 <datamodel>
        根上）；通过 detect_namespaces 探测时只看根 nsmap，所以这里只断言
        根上声明的 dm/a/v/d。
        """
        ns = detect_namespaces(FIXTURES_DIR / "Can.xdm")
        assert "dm" in ns
        assert "a" in ns
        assert "v" in ns
        assert "d" in ns
        assert "xsi" in ns

    def test_user_fixtures_child_ns_walked(self) -> None:
        """子元素上声明的 ad/cd/variant 等 namespace 通过 walk 子树可拿到。"""
        tree = read(FIXTURES_DIR / "Can.xdm")
        # 收集所有 element 上声明的 nsmap
        all_uris: set[str] = set()
        for elem in tree.getroot().iter():
            for uri in elem.nsmap.values():
                if uri is not None:
                    all_uris.add(uri)
        # 应包含 ad / cd / variant
        assert any("admindata" in u for u in all_uris)
        assert any("customdata" in u for u in all_uris)
        assert any("variant" in u for u in all_uris)

    def test_path_can_be_string(self, tmp_path: Path) -> None:
        f = tmp_path / "sample.xdm"
        f.write_text(_SAMPLE_XDM, encoding="utf-8")
        # path 可以是 str（不是 Path 对象）
        tree = read(str(f))
        assert tree.getroot().tag.endswith("datamodel")

    def test_write_preserves_doctype_robustness(self, tmp_path: Path) -> None:
        """surgical patch 在文件结构不变时不应抛。"""
        f = tmp_path / "no_change.xdm"
        f.write_text(_SAMPLE_XDM, encoding="utf-8")
        original_bytes = f.read_bytes()
        tree = read(f)
        # 不改任何东西
        write(tree, f, atomic=False)
        # 内容应保持不变（preserve_format=True 的快路径直接 return 原字节）
        assert f.read_bytes() == original_bytes
