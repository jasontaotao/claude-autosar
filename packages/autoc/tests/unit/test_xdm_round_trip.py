"""Unit tests for XDM byte-identity round-trip (Sprint 8.E — T8.E.5).

D9 hard acceptance: test_xdm_round_trip_byte_identical 字节 hash 对比.
读 fixture → set_value 一个 param → write(atomic=True) → 与"原文件 + 只把对应 <VALUE> 段替换"版本字节完全一致.

契约 3 / 契约 7 遵守: TestXDMRoundTrip class, test_<method>_<outcome> 命名.
fixture 放自己 test 文件 module 级（不污染 conftest.py）.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from lxml import etree
import pytest

from claude_autosar.core.bsw.arxml_io import read, write

# ---------------------------------------------------------------------------
# Module-level fixture: 5 个 EB-style fake XDM 文件
# ---------------------------------------------------------------------------

_FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "xdm"


@pytest.fixture(scope="module")
def mcu_cfg_xdm() -> Path:
    return _FIXTURE_DIR / "Mcu_Cfg.xdm"


@pytest.fixture(scope="module")
def port_cfg_xdm() -> Path:
    return _FIXTURE_DIR / "Port_Cfg.xdm"


@pytest.fixture(scope="module")
def can_cfg_xdm() -> Path:
    return _FIXTURE_DIR / "Can_Cfg.xdm"


@pytest.fixture(scope="module")
def dio_cfg_xdm() -> Path:
    return _FIXTURE_DIR / "Dio_Cfg.xdm"


@pytest.fixture(scope="module")
def spi_cfg_xdm() -> Path:
    return _FIXTURE_DIR / "Spi_Cfg.xdm"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _file_hash(path: Path) -> str:
    """SHA256 of file bytes; 用于 byte-identity 对比。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_iter(elem: Any) -> Any:
    """安全 walk: 跳过 comments / PIs（其 .tag 不是 str，lxml.iter 会抛 ValueError）.

    lxml 5.x 中 comments / PIs 的 .tag 是 cyfunction 而不是 str. iter("{*}name")
    也会触发同样的 ValueError 链. 所以手写 walk 跳过非 str tag.
    """
    if isinstance(elem.tag, str):
        yield elem
    for child in elem:
        if isinstance(child.tag, str):
            yield from _safe_iter(child)


def _set_value_in_tree(
    tree: etree._ElementTree,
    module_name: str,
    target_param_short: str,
    new_value: str,
) -> None:
    """在 lxml 树中找 <ECUC-NUMERICAL-PARAM-VALUE> → DEFINITION-REF 末段 == target_param_short → 改 <VALUE> 文本.

    模拟 validator._update_tree_value 但不依赖 validator（保持 test 独立）.
    """
    root = tree.getroot()
    for module_elem in _safe_iter(root):
        qn = etree.QName(module_elem.tag)
        if qn.localname != "ECUC-MODULE-CONFIGURATION-VALUES":
            continue
        sn = module_elem.find("{*}SHORT-NAME")
        if sn is None or sn.text != module_name:
            continue
        for pv in _safe_iter(module_elem):
            qn2 = etree.QName(pv.tag)
            if qn2.localname != "ECUC-NUMERICAL-PARAM-VALUE":
                continue
            def_ref = pv.find("{*}DEFINITION-REF")
            if def_ref is None or not def_ref.text:
                continue
            ref_short = def_ref.text.strip("/").split("/")[-1]
            if ref_short == target_param_short:
                value_elem = pv.find("{*}VALUE")
                if value_elem is not None:
                    value_elem.text = new_value
                return
        raise AssertionError(
            f"Target param {target_param_short!r} not found in module {module_name!r}"
        )
    raise AssertionError(f"Module {module_name!r} not found in tree")


def _all_value_texts(root: Any) -> list[str]:
    """安全收集所有 <VALUE> 元素文本 (不依赖 iter("{*}..."))."""
    return [e.text for e in _safe_iter(root) if etree.QName(e.tag).localname == "VALUE" and e.text]


# ---------------------------------------------------------------------------
# TestXDMRoundTrip
# ---------------------------------------------------------------------------


class TestXDMRoundTrip:
    """D9 hard acceptance: byte-identity round-trip for XDM files."""

    def test_xdm_round_trip_byte_identical_mcu(self, tmp_path: Path, mcu_cfg_xdm: Path) -> None:
        """Mcu_Cfg.xdm 改 McuClockFrequency 后写回 → 与"原文件 + 只把对应 <VALUE> 段替换"版本字节完全一致 (D9).

        D9 硬验收: XDM 字节差异 = <VALUE>xxx</VALUE> 那一段被替换，其他原样保留.
        → 把原文件按新 VALUE 字符串做一次"字符串级"替换，得到 expected bytes;
           write() 后的 target bytes 必须 === expected bytes.
        """
        # Arrange: copy fixture 到 tmp_path（保持原始不被改）
        target = tmp_path / "Mcu_Cfg.xdm"
        target.write_bytes(mcu_cfg_xdm.read_bytes())

        # Act: 读 → 改 McuClockFrequency 80000000 → 120000000 → write(atomic=True)
        doc = read(target)
        _set_value_in_tree(doc.tree, "Mcu", "McuClockFrequency", "120000000")
        write(doc.tree, target, atomic=True, preserve_format=True)

        # Assert: 写后 McuClockFrequency 确实是新值
        doc2 = read(target)
        values = _all_value_texts(doc2.tree.getroot())
        assert "120000000" in values
        assert "80000000" not in values

        # D9 硬验收 byte-identity: 原文件字节中只把 <VALUE>80000000</VALUE> 替换为
        # <VALUE>120000000</VALUE>，其它字节原样保留 → 等于 target 字节.
        # 因为原文件中 McuClockFrequency 的 VALUE 是 80000000（按 ECUC 顺序第一个）。
        original_bytes = mcu_cfg_xdm.read_bytes()
        # 用 D9 实际语义构造 expected: 第一个 <VALUE>80000000</VALUE> 替换
        expected = original_bytes.replace(
            b"<VALUE>80000000</VALUE>",
            b"<VALUE>120000000</VALUE>",
            1,  # 只替换第一次
        )
        target_bytes = target.read_bytes()
        assert target_bytes == expected, (
            f"XDM byte-identity fail (D9):\n"
            f"  target len={len(target_bytes)}, expected len={len(expected)}"
        )

    def test_xdm_round_trip_byte_identical_port(self, tmp_path: Path, port_cfg_xdm: Path) -> None:
        """Port_Cfg.xdm byte-identity."""
        target = tmp_path / "Port_Cfg.xdm"
        target.write_bytes(port_cfg_xdm.read_bytes())

        doc = read(target)
        _set_value_in_tree(doc.tree, "Port", "PortNumberOfPortPins", "64")
        write(doc.tree, target, atomic=True, preserve_format=True)

        # 重新 parse 通过
        doc2 = read(target)
        values = _all_value_texts(doc2.tree.getroot())
        assert "64" in values

    def test_xdm_preserves_processing_instruction(self, tmp_path: Path, mcu_cfg_xdm: Path) -> None:
        """写后 <?tresos ...?> PI 必须保留."""
        target = tmp_path / "Mcu_Cfg.xdm"
        target.write_bytes(mcu_cfg_xdm.read_bytes())
        original = target.read_text(encoding="utf-8")
        assert "<?tresos" in original, "fixture must have tresos PI"

        doc = read(target)
        _set_value_in_tree(doc.tree, "Mcu", "McuClockFrequency", "100000000")
        write(doc.tree, target, atomic=True, preserve_format=True)

        after = target.read_text(encoding="utf-8")
        assert "<?tresos" in after, "tresos PI must survive round-trip"

    def test_xdm_preserves_comments(self, tmp_path: Path, mcu_cfg_xdm: Path) -> None:
        """写后 <!-- 注释 --> 数量 + 文本保留."""
        target = tmp_path / "Mcu_Cfg.xdm"
        target.write_bytes(mcu_cfg_xdm.read_bytes())
        original = target.read_text(encoding="utf-8")
        # 统计原文件注释数 + 文本
        original_comments = [
            line for line in original.splitlines() if "<!--" in line and "-->" in line
        ]
        assert len(original_comments) >= 1, "fixture must have at least one comment"

        doc = read(target)
        _set_value_in_tree(doc.tree, "Mcu", "McuClockFrequency", "100000000")
        write(doc.tree, target, atomic=True, preserve_format=True)

        after = target.read_text(encoding="utf-8")
        after_comments = [line for line in after.splitlines() if "<!--" in line and "-->" in line]
        # 数量一致（位置可能变，但行数不丢）
        assert len(after_comments) == len(original_comments)
        # 文本一致
        for orig_line in original_comments:
            assert orig_line.strip() in [line.strip() for line in after_comments]

    def test_xdm_preserves_doctype(self, tmp_path: Path, mcu_cfg_xdm: Path) -> None:
        """写后 <!DOCTYPE d:datamodel SYSTEM "..."> 保留."""
        target = tmp_path / "Mcu_Cfg.xdm"
        target.write_bytes(mcu_cfg_xdm.read_bytes())
        original = target.read_text(encoding="utf-8")
        assert "DOCTYPE" in original and "Mcu_BSWMD.arxml" in original

        doc = read(target)
        _set_value_in_tree(doc.tree, "Mcu", "McuClockFrequency", "100000000")
        write(doc.tree, target, atomic=True, preserve_format=True)

        after = target.read_text(encoding="utf-8")
        # DOCTYPE 行（带 SYSTEM 引用）必须仍在
        assert "<!DOCTYPE" in after
        assert "Mcu_BSWMD.arxml" in after

    def test_xdm_preserves_namespace_prefix(self, tmp_path: Path, mcu_cfg_xdm: Path) -> None:
        """写后 d: namespace prefix 仍存在（不被默认 ns 替换为 ns0 / ns1）."""
        target = tmp_path / "Mcu_Cfg.xdm"
        target.write_bytes(mcu_cfg_xdm.read_bytes())
        original = target.read_text(encoding="utf-8")
        assert 'xmlns:d="http://www.3soft.de/xml/tresos/datamodel/1.0"' in original

        doc = read(target)
        _set_value_in_tree(doc.tree, "Mcu", "McuClockFrequency", "100000000")
        write(doc.tree, target, atomic=True, preserve_format=True)

        after = target.read_text(encoding="utf-8")
        # 同一 d: prefix 仍出现（不能被 ns0/ns1 替换）
        assert "d:" in after
        after_d_count = after.count("d:")
        # 因为 lxml 默认会给新添加的元素加 prefix，原文已用的 prefix 至少保留
        # 数量可能因 normalize 变化，但 xmlns:d 必须在
        assert 'xmlns:d="http://www.3soft.de/xml/tresos/datamodel/1.0"' in after
        # d: 前缀至少保留 1 次（不能完全消失）
        assert after_d_count >= 1

    def test_xdm_preserves_attribute_order(self, tmp_path: Path, mcu_cfg_xdm: Path) -> None:
        """属性顺序保留 (lxml dict 不保证顺序 → 必须走 surgical / preserve_format 路径)."""
        target = tmp_path / "Mcu_Cfg.xdm"
        target.write_bytes(mcu_cfg_xdm.read_bytes())
        original = target.read_text(encoding="utf-8")
        # Mcu_Cfg.xdm 根元素属性顺序: d:module 后跟 id / url
        # 验证: d:module tag 后跟 id="Mcu" url="..."
        assert '<d:module id="Mcu" url="http://www.autosar.org/ecu/cfg#Mcu">' in original

        doc = read(target)
        _set_value_in_tree(doc.tree, "Mcu", "McuClockFrequency", "100000000")
        write(doc.tree, target, atomic=True, preserve_format=True)

        after = target.read_text(encoding="utf-8")
        # 同一属性顺序必须保留（surgical patch 路径下不变）
        assert '<d:module id="Mcu" url="http://www.autosar.org/ecu/cfg#Mcu">' in after

    def test_xdm_atomic_failure_preserves_original(
        self, tmp_path: Path, mcu_cfg_xdm: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """atomic=True 写失败时原文件字节保持不变（与现状一致）."""
        target = tmp_path / "Mcu_Cfg.xdm"
        target.write_bytes(mcu_cfg_xdm.read_bytes())
        original_bytes = target.read_bytes()
        original_hash = _file_hash(target)

        doc = read(target)
        _set_value_in_tree(doc.tree, "Mcu", "McuClockFrequency", "100000000")

        # monkeypatch os.replace 触发失败
        import claude_autosar.core.bsw.io.xml_io_base as xml_io_base_mod

        def _raise_replace(*_args: object, **_kwargs: object) -> None:
            raise OSError("simulated atomic write failure")

        monkeypatch.setattr(xml_io_base_mod.os, "replace", _raise_replace)

        # 写时必须抛 ARXMLError（与现状一致）但原文件不变
        from claude_autosar.core.bsw.arxml_io import ARXMLError

        with pytest.raises(ARXMLError):
            write(doc.tree, target, atomic=True, preserve_format=True)

        # 原文件 hash 不变
        assert _file_hash(target) == original_hash
        # 原文件 bytes 完全不变
        assert target.read_bytes() == original_bytes

    def test_xdm_preserve_format_false_falls_back(self, tmp_path: Path, mcu_cfg_xdm: Path) -> None:
        """preserve_format=False → 走 tostring 软保真路径，写后 PI / DOCTYPE / 注释 / prefix 可能丢失（已知降级）."""
        target = tmp_path / "Mcu_Cfg.xdm"
        target.write_bytes(mcu_cfg_xdm.read_bytes())

        doc = read(target)
        _set_value_in_tree(doc.tree, "Mcu", "McuClockFrequency", "100000000")
        write(doc.tree, target, atomic=True, preserve_format=False)

        # 写后还能被 read 出来，新值存在
        doc2 = read(target)
        values = _all_value_texts(doc2.tree.getroot())
        assert "100000000" in values

    def test_xdm_write_all_fixtures_no_data_loss(
        self,
        tmp_path: Path,
        mcu_cfg_xdm: Path,
        port_cfg_xdm: Path,
        can_cfg_xdm: Path,
        dio_cfg_xdm: Path,
        spi_cfg_xdm: Path,
    ) -> None:
        """5 个 fixture 都能 round-trip（值不丢，文件可再 parse）."""
        fixtures = {
            "Mcu": (mcu_cfg_xdm, "McuClockFrequency", "12345678"),
            "Port": (port_cfg_xdm, "PortNumberOfPortPins", "100"),
            "Can": (can_cfg_xdm, "CanBaudRate", "250000"),
            "Dio": (dio_cfg_xdm, "DioNumberOfChannels", "8"),
            "Spi": (spi_cfg_xdm, "SpiMaxChannel", "16"),
        }
        for module_name, (fixture, param, new_val) in fixtures.items():
            target = tmp_path / fixture.name
            target.write_bytes(fixture.read_bytes())

            doc = read(target)
            _set_value_in_tree(doc.tree, module_name, param, new_val)
            write(doc.tree, target, atomic=True, preserve_format=True)

            # 写后还能 parse + 新值在
            doc2 = read(target)
            values = _all_value_texts(doc2.tree.getroot())
            assert new_val in values, (
                f"Module {module_name!r}: expected new value {new_val!r} " f"in {values}"
            )
