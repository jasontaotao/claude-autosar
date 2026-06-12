"""Sprint 8.E.1 coverage tests for ``arxml_io`` + ``validator`` + ``ecuc`` + ``config``.

Plan reference: Sprint 8.E.1 T8.E.1.4 — coverage backfill to ≥90% for the four
files Sprint 8.E modified.

Targets:
- ``core/bsw/arxml_io.py`` (84% → ≥90%): detect_namespaces() / build_default_nsmap()
  / resolve_namespaces() / write(preserve_format) / atomic / surgical patch
- ``core/bsw/validator.py`` (85% → ≥90%): modify_and_verify() BSWMD 集成 / 失败路径
- ``core/bsw/ecuc.py`` (87% → ≥90%): load_module() BSWMD / _infer_type() BSWMD 优先
  / set_value() / list_paths()
- ``core/bsw/config.py`` (86% → ≥90%): BSWParam.def_ref / BSWModule.with_def_ref
  / from_ecuc() / to_ecuc()

Contract 7: Test naming ``TestSprint8E1CoverageArxmlEcuc`` 类层级。

**禁 令**:
- 不改 arxml_io.py / validator.py / ecuc.py / config.py 源
- 不改 conftest.py
- 不引入新 pip 依赖
- 不 git commit（主 agent 统一组织）
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from lxml import etree
import pytest

from autoc.core.bsw.arxml_io import (
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
from autoc.core.bsw.arxml_io import write as arxml_write
from autoc.core.bsw.bswmd import BSWMDRegistry, ContainerDef, ModuleDef, ParamDef
from autoc.core.bsw.config import BSWModule, BSWParam, ParamType, ParamValue
from autoc.core.bsw.ecuc import (
    load_module,
)
from autoc.core.bsw.ecuc import set_value as ecuc_set_value
from autoc.core.bsw.validator import (
    ModifyRequest,
    ValidatorError,
    modify_and_verify,
)

# ===========================================================================
# Helpers
# ===========================================================================


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
    """造一个最小 fake ECUC xdm，含 1 个 INTEGER param。"""
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


def _make_ctx(project_path: Path) -> MagicMock:
    """造一个最小 EcuConfigProjectContext mock。"""
    ctx = MagicMock()
    ctx.project_path = project_path
    return ctx


def _stub_adapter(
    *,
    verify_success: bool = True,
    save_success: bool = True,
) -> MagicMock:
    """造一个 stub adapter，verify/save 都返回 success。"""

    def _verify(_ctx: Any, _module: str | None) -> Any:
        r = MagicMock()
        r.success = verify_success
        r.returncode = 0 if verify_success else 1
        r.stdout = ""
        r.stderr = "" if verify_success else "verify fail"
        return r

    def _save(_ctx: Any, _module: str | None) -> Any:
        r = MagicMock()
        r.success = save_success
        r.returncode = 0 if save_success else 1
        r.written_files = (Path("/tmp/out.xdm"),) if save_success else ()
        return r

    adapter = MagicMock()
    adapter.verify.side_effect = _verify
    adapter.save.side_effect = _save
    return adapter


# ===========================================================================
# arxml_io namespace detection / caching / xsi
# ===========================================================================


class TestSprint8E1CoverageArxmlIoNamespace:
    """``detect_namespaces`` / ``build_default_nsmap`` / ``resolve_namespaces``."""

    def test_detect_namespaces_r40_returns_ar_mapping(self, tmp_path: Path) -> None:
        """r4.0 xmlns 探测：默认 ns key 为 'ar'。"""
        path = _make_r40_xdm(tmp_path / "r40.xdm")
        nsmap = detect_namespaces(path)
        assert nsmap["ar"] == "http://autosar.org/schema/r4.0"
        assert "xsi" in nsmap  # 必含

    def test_detect_namespaces_r47_returns_r47_mapping(self, tmp_path: Path) -> None:
        """r4.7 xmlns 探测。"""
        path = _make_r47_xdm(tmp_path / "r47.xdm")
        nsmap = detect_namespaces(path)
        assert nsmap["ar"] == "http://autosar.org/schema/r4.7"

    def test_detect_namespaces_xsi_always_present(self, tmp_path: Path) -> None:
        """``xsi`` 必含（即便原文件没声明）。"""
        path = _make_r40_xdm(tmp_path / "x.xdm")
        nsmap = detect_namespaces(path)
        assert "xsi" in nsmap
        assert nsmap["xsi"] == "http://www.w3.org/2001/XMLSchema-instance"

    def test_detect_namespaces_file_not_found_raises(self, tmp_path: Path) -> None:
        """文件不存在 → ARXMLError（stat 失败）。"""
        with pytest.raises(ARXMLError, match="cannot stat"):
            detect_namespaces(tmp_path / "no_such.xdm")

    def test_detect_namespaces_malformed_xml_raises(self, tmp_path: Path) -> None:
        """畸形 XML → ARXMLError。"""
        bad = tmp_path / "bad.xdm"
        _write_xdm(bad, "not <valid> xml")
        with pytest.raises(ARXMLError, match="Malformed"):
            detect_namespaces(bad)

    def test_detect_namespaces_cache_invalidation_on_mtime(self, tmp_path: Path) -> None:
        """mtime 改变 → cache invalidate。"""
        path = _make_r40_xdm(tmp_path / "x.xdm")
        # 触发首次探测（populate cache）
        detect_namespaces(path)
        # 改文件内容 + mtime
        os.utime(path, ns=(path.stat().st_mtime_ns + 1_000_000_000,) * 2)
        _write_xdm(path, _make_r47_xdm(tmp_path / "r47.xdm").read_text(encoding="utf-8"))
        nsmap2 = detect_namespaces(path)
        assert nsmap2["ar"] == "http://autosar.org/schema/r4.7"

    def test_build_default_nsmap_handles_multi_namespace(self, tmp_path: Path) -> None:
        """多 namespace 根（默认 ns + 命名 prefix）→ nsmap 全收。"""
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
        """``resolve_namespaces`` 是 build 的包装。"""
        path = _make_r40_xdm(tmp_path / "x.xdm")
        tree = etree.parse(str(path))
        nsmap = resolve_namespaces(tree.getroot())
        assert nsmap["ar"] == "http://autosar.org/schema/r4.0"


class TestSprint8E1CoverageArxmlIoWellKnown:
    """``WELL_KNOWN_NAMESPACE_URIS`` 兼容 alias / 多版本 URI。"""

    def test_well_known_namespace_uris_has_6_r4x_versions(self) -> None:
        """r4.0/4.2/4.4/4.6/4.7/4.8 共 6 个。"""
        ar_uris = WELL_KNOWN_NAMESPACE_URIS["ar"]
        assert len(ar_uris) == 6
        assert "http://autosar.org/schema/r4.0" in ar_uris
        assert "http://autosar.org/schema/r4.8" in ar_uris

    def test_default_namespaces_alias_back_compat(self) -> None:
        """``DEFAULT_NAMESPACES`` 是 ``WELL_KNOWN_NAMESPACE_URIS`` 的 alias。"""
        from autoc.core.bsw.arxml_io import DEFAULT_NAMESPACES

        assert DEFAULT_NAMESPACES is WELL_KNOWN_NAMESPACE_URIS


# ===========================================================================
# arxml_io write paths
# ===========================================================================


class TestSprint8E1CoverageArxmlIoWrite:
    """``write`` 各种 preserve_format / atomic 路径。"""

    def test_write_preserve_format_true_with_existing_file(self, tmp_path: Path) -> None:
        """preserve_format=True + 现有文件 → 走 surgical patch（保留 PI 等）。"""
        path = _make_module_xdm(tmp_path / "Cfg.xdm", "Mcu")
        # 改文件树的 VALUE
        tree = etree.parse(str(path))
        for value_elem in tree.iter("{*}VALUE"):
            value_elem.text = "999"
        # 写：preserve_format=True + atomic=True
        arxml_write(tree, path, atomic=True, preserve_format=True)
        # 文件应当仍包含原字节（surgical patch 替换 VALUE 段）
        new_bytes = path.read_bytes()
        # "100" → "999" 的变化应被 patch 应用
        assert b"999" in new_bytes
        # PI / DOCTYPE 保留（我们的 fixture 无 PI，但格式应保持）
        assert b"<?xml" in new_bytes

    def test_write_preserve_format_false_uses_tostring(self, tmp_path: Path) -> None:
        """preserve_format=False → 走 tostring 软保真。"""
        path = _make_module_xdm(tmp_path / "Cfg.xdm", "Mcu")
        tree = etree.parse(str(path))
        for value_elem in tree.iter("{*}VALUE"):
            value_elem.text = "555"
        arxml_write(tree, path, atomic=True, preserve_format=False)
        new_bytes = path.read_bytes()
        assert b"555" in new_bytes

    def test_write_non_atomic_writes_directly(self, tmp_path: Path) -> None:
        """``atomic=False`` → 直接写，不走 .tmp。"""
        path = _make_module_xdm(tmp_path / "Cfg.xdm", "Mcu")
        tree = etree.parse(str(path))
        for value_elem in tree.iter("{*}VALUE"):
            value_elem.text = "777"
        arxml_write(tree, path, atomic=False, preserve_format=False)
        assert b"777" in path.read_bytes()
        # 没有 .tmp 残留
        assert not (tmp_path / "Cfg.xdm.tmp").exists()

    def test_write_with_arxmldocument_target_uses_doc_path(self, tmp_path: Path) -> None:
        """``write(ARXMLDocument, ...)`` → path 取自 doc.path。"""
        path = _make_module_xdm(tmp_path / "Cfg.xdm", "Mcu")
        doc = read(path)
        # 改 doc.tree
        for value_elem in doc.tree.iter("{*}VALUE"):
            value_elem.text = "333"
        arxml_write(doc, atomic=True, preserve_format=False)
        assert b"333" in path.read_bytes()

    def test_write_with_tree_requires_explicit_path(self, tmp_path: Path) -> None:
        """``write(tree, path=None)`` → TypeError（契约 3）。"""
        path = _make_module_xdm(tmp_path / "Cfg.xdm", "Mcu")
        tree = etree.parse(str(path))
        with pytest.raises(TypeError, match="requires explicit path"):
            arxml_write(tree, path=None, atomic=True)

    def test_write_surgical_patch_unavailable_falls_back(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """surgical patch 不可用 → 降级到 tostring。"""
        path = _make_module_xdm(tmp_path / "Cfg.xdm", "Mcu")
        tree = etree.parse(str(path))
        # 强制 _SurgicalPatchUnavailable 抛错
        from autoc.core.bsw import arxml_io as aio_mod

        orig = aio_mod._write_surgical_patch

        def _raise(*_a: Any, **_kw: Any) -> None:
            raise aio_mod._SurgicalPatchUnavailable("test")

        monkeypatch.setattr(aio_mod, "_write_surgical_patch", _raise)
        try:
            for value_elem in tree.iter("{*}VALUE"):
                value_elem.text = "111"
            # 应走 fallback 路径（不抛）
            arxml_write(tree, path, atomic=True, preserve_format=True)
            assert b"111" in path.read_bytes()
        finally:
            monkeypatch.setattr(aio_mod, "_write_surgical_patch", orig)


# ===========================================================================
# arxml_io high-level helpers
# ===========================================================================


class TestSprint8E1CoverageArxmlIoHelpers:
    """``read`` / ``find_elements`` / ``get_*`` / ``set_*``."""

    def test_read_file_not_found_raises(self, tmp_path: Path) -> None:
        """文件不存在 → ARXMLError。"""
        with pytest.raises(ARXMLError, match="not readable"):
            read(tmp_path / "no.xdm")

    def test_read_malformed_xml_raises(self, tmp_path: Path) -> None:
        """畸形 XML → ARXMLError。"""
        bad = tmp_path / "bad.xdm"
        _write_xdm(bad, "<not><closed>")
        with pytest.raises(ARXMLError, match="Malformed"):
            read(bad)

    def test_find_elements_no_namespace_xpath_with_prefix_raises(self, tmp_path: Path) -> None:
        """无 namespaces 参数 + xpath 引用 prefix → lxml 报 XPathEvalError
        被包装为 ARXMLError。"""
        path = _make_r40_xdm(tmp_path / "x.xdm")
        doc = read(path)
        with pytest.raises(ARXMLError, match="Invalid XPath"):
            find_elements(doc, "//ar:SHORT-NAME")  # 没传 ns

    def test_find_elements_with_namespace(self, tmp_path: Path) -> None:
        """传 namespaces → xpath 命中。"""
        path = _make_r40_xdm(tmp_path / "x.xdm")
        doc = read(path)
        nsmap = build_default_nsmap(doc.tree.getroot())
        result = find_elements(doc, "//ar:SHORT-NAME", namespaces=nsmap)
        assert len(result) >= 1

    def test_find_elements_invalid_xpath_raises(self, tmp_path: Path) -> None:
        """非法 xpath → ARXMLError。"""
        path = _make_r40_xdm(tmp_path / "x.xdm")
        doc = read(path)
        with pytest.raises(ARXMLError, match="Invalid XPath"):
            find_elements(doc, "[[[")

    def test_get_attribute_returns_value(self) -> None:
        """``get_attribute`` 读属性。"""
        root = etree.fromstring('<root attr="val"/>')
        assert get_attribute(root, "attr") == "val"
        assert get_attribute(root, "missing") is None
        assert get_attribute(root, "missing", default="def") == "def"

    def test_set_attribute_sets_value(self) -> None:
        """``set_attribute`` 写属性。"""
        root = etree.fromstring("<root/>")
        set_attribute(root, "x", "1")
        assert root.get("x") == "1"

    def test_get_child_text_returns_text(self) -> None:
        """``get_child_text`` 读子元素文本。"""
        root = etree.fromstring("<root><c>hello</c></root>")
        assert get_child_text(root, "c") == "hello"
        assert get_child_text(root, "missing") is None

    def test_set_child_text_creates_when_missing(self) -> None:
        """``set_child_text`` 子元素不存在 → 创建。"""
        root = etree.fromstring("<root/>")
        set_child_text(root, "c", "new")
        assert root.find("{*}c").text == "new"

    def test_set_child_text_overwrites_when_exists(self) -> None:
        """``set_child_text`` 子元素存在 → 覆盖文本。"""
        root = etree.fromstring("<root><c>old</c></root>")
        set_child_text(root, "c", "new")
        assert root.find("{*}c").text == "new"
        # 仍然只有 1 个 c 子元素
        assert len(root.findall("{*}c")) == 1


# ===========================================================================
# validator modify_and_verify
# ===========================================================================


class TestSprint8E1CoverageValidatorModify:
    """``modify_and_verify`` 各种路径。"""

    def test_modify_empty_params_returns_success_immediately(self, tmp_path: Path) -> None:
        """空 params → 直接返回 success。"""
        project = tmp_path / "proj"
        project.mkdir()
        ctx = _make_ctx(project)
        adapter = _stub_adapter()
        req = ModifyRequest(module="Mcu", params=())
        result = modify_and_verify(ctx, adapter, req)
        assert result.success is True
        assert result.written_files == ()
        # adapter 没被调
        adapter.verify.assert_not_called()
        adapter.save.assert_not_called()

    def test_modify_module_file_not_found_raises_validator_error(self, tmp_path: Path) -> None:
        """``_locate_module_file`` 返 None → ValidatorError。"""
        project = tmp_path / "proj"
        project.mkdir()
        ctx = _make_ctx(project)
        adapter = _stub_adapter()
        param = BSWParam(
            path="Mcu/Cfg/Freq",
            value=ParamValue(raw="100", type=ParamType.INTEGER),
        )
        req = ModifyRequest(module="NoSuchModule", params=(param,))
        with pytest.raises(ValidatorError, match="not found"):
            modify_and_verify(ctx, adapter, req)

    def test_modify_bswmd_validation_fails_returns_modify_result_error(
        self, tmp_path: Path
    ) -> None:
        """BSWMD 校验失败 → ModifyResult.error，不调 verify/save。"""
        project = tmp_path / "proj"
        _make_module_xdm(project / "Mcu.xdm", "Mcu")
        ctx = _make_ctx(project)
        adapter = _stub_adapter()
        # BSWMD: 限制 Freq 范围 [0, 50]（用 ContainerDef 装 ParamDef）
        container = ContainerDef(
            short_name="Cfg",
            full_path="/AUTOSAR/Mcu/Cfg",
            lower_multiplicity=0,
            upper_multiplicity=1,
            param_defs={
                "Freq": ParamDef(
                    short_name="Freq",
                    full_path="/AUTOSAR/Mcu/Cfg/Freq",
                    param_type="INTEGER",
                    min="0",
                    max="50",
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
        # 写一个越界值 999
        param = BSWParam(
            path="Mcu/Cfg/Freq",
            value=ParamValue(raw="999", type=ParamType.INTEGER),
        )
        req = ModifyRequest(module="Mcu", params=(param,))
        result = modify_and_verify(ctx, adapter, req, bswmd_registry=bswmd)
        assert result.success is False
        assert result.rolled_back is False
        assert "BSWMD validation failed" in (result.error or "")
        # verify / save 未被调
        adapter.verify.assert_not_called()
        adapter.save.assert_not_called()

    def test_modify_load_module_fails_raises_validator_error(self, tmp_path: Path) -> None:
        """``load_module`` 失败（畸形 xdm）→ ValidatorError + 还原。"""
        project = tmp_path / "proj"
        project.mkdir()
        # 写一个畸形 xdm（短内容但有 SHORT-NAME 缺 ECUC 元素）
        (project / "Mcu.xdm").write_text(
            "<?xml version='1.0'?><AUTOSAR xmlns='http://autosar.org/schema/r4.0'/>",
            encoding="utf-8",
        )
        ctx = _make_ctx(project)
        adapter = _stub_adapter()
        param = BSWParam(
            path="Mcu/Cfg/Freq",
            value=ParamValue(raw="100", type=ParamType.INTEGER),
        )
        req = ModifyRequest(module="Mcu", params=(param,))
        with pytest.raises(ValidatorError, match="Failed to load"):
            modify_and_verify(ctx, adapter, req)

    def test_modify_verify_failure_triggers_rollback(self, tmp_path: Path) -> None:
        """verify 失败 → 回滚 + ModifyResult.rolled_back=True。"""
        project = tmp_path / "proj"
        _make_module_xdm(project / "Mcu.xdm", "Mcu")
        ctx = _make_ctx(project)
        adapter = _stub_adapter(verify_success=False)
        param = BSWParam(
            path="Mcu/Cfg/Freq",
            value=ParamValue(raw="50", type=ParamType.INTEGER),
        )
        req = ModifyRequest(module="Mcu", params=(param,))
        original = (project / "Mcu.xdm").read_bytes()
        result = modify_and_verify(ctx, adapter, req)
        assert result.success is False
        assert result.rolled_back is True
        # 文件被还原
        assert (project / "Mcu.xdm").read_bytes() == original

    def test_modify_save_success_returns_written_files(self, tmp_path: Path) -> None:
        """save 成功 → ModifyResult.written_files 填充。"""
        project = tmp_path / "proj"
        _make_module_xdm(project / "Mcu.xdm", "Mcu")
        ctx = _make_ctx(project)
        adapter = _stub_adapter(verify_success=True, save_success=True)
        param = BSWParam(
            path="Mcu/Cfg/Freq",
            value=ParamValue(raw="77", type=ParamType.INTEGER),
        )
        req = ModifyRequest(module="Mcu", params=(param,))
        result = modify_and_verify(ctx, adapter, req)
        assert result.success is True
        assert len(result.written_files) >= 1
        # 文件确实改了
        assert b"77" in (project / "Mcu.xdm").read_bytes()

    def test_modify_save_failure_returns_error(self, tmp_path: Path) -> None:
        """save 失败 → ModifyResult.error（不回滚，因为已经写成功了）。"""
        project = tmp_path / "proj"
        _make_module_xdm(project / "Mcu.xdm", "Mcu")
        ctx = _make_ctx(project)
        adapter = _stub_adapter(verify_success=True, save_success=False)
        param = BSWParam(
            path="Mcu/Cfg/Freq",
            value=ParamValue(raw="42", type=ParamType.INTEGER),
        )
        req = ModifyRequest(module="Mcu", params=(param,))
        result = modify_and_verify(ctx, adapter, req)
        assert result.success is False
        assert "save failed" in (result.error or "")


# ===========================================================================
# ecuc load_module / set_value / list_paths with BSWMD
# ===========================================================================


class TestSprint8E1CoverageEcucLoadModule:
    """``load_module`` BSWMD registry / namespace handling。"""

    def test_load_module_default_nsmap_detected(self, tmp_path: Path) -> None:
        """``nsmap=None`` → 自动探测。"""
        path = _make_module_xdm(tmp_path / "Mcu.xdm", "Mcu")
        doc = load_module(path, "Mcu")
        assert doc.module_name == "Mcu"
        assert any(v.path == "Mcu/Cfg/Freq" for v in doc.values)

    def test_load_module_with_explicit_nsmap(self, tmp_path: Path) -> None:
        """``nsmap=非空`` → 显式提供（仍用 root 实际 nsmap 兜底）。"""
        path = _make_module_xdm(tmp_path / "Mcu.xdm", "Mcu")
        nsmap = {"ar": "http://autosar.org/schema/r4.0", "xsi": "..."}
        doc = load_module(path, "Mcu", nsmap=nsmap)
        assert doc.module_name == "Mcu"

    def test_load_module_with_bswmd_registry_uses_strict_types(self, tmp_path: Path) -> None:
        """``bswmd_registry=非空`` → BSWMD 严格类型推断。"""
        path = _make_module_xdm(tmp_path / "Mcu.xdm", "Mcu")
        # BSWMD 把 Freq 标记为 ENUMERATION（与 DEST 启发式 INTEGER 冲突）
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
        assert freq.type == "ENUMERATION"  # BSWMD 优先于 DEST 启发式 (INTEGER)

    def test_load_module_module_not_found_raises(self, tmp_path: Path) -> None:
        """找不到指定 module → ValueError。"""
        path = _make_module_xdm(tmp_path / "Mcu.xdm", "Mcu")
        with pytest.raises(ValueError, match="not found"):
            load_module(path, "NoSuchModule")

    def test_load_module_with_r47_namespace(self, tmp_path: Path) -> None:
        """r4.7 xmlns → load_module 正常工作。"""
        # 改 r4.0 模板为 r4.7
        r40 = _make_module_xdm(tmp_path / "Mcu.xdm", "Mcu")
        text = r40.read_text(encoding="utf-8").replace("r4.0", "r4.7")
        r40.write_text(text, encoding="utf-8")
        doc = load_module(r40, "Mcu")
        assert doc.module_name == "Mcu"


class TestSprint8E1CoverageEcucSetValue:
    """``set_value`` 不可变改值。"""

    def test_set_value_changes_raw(self, tmp_path: Path) -> None:
        """set_value 改 raw → 返回新 doc，原 doc 不变。"""
        path = _make_module_xdm(tmp_path / "Mcu.xdm", "Mcu")
        doc = load_module(path, "Mcu")
        new_doc = ecuc_set_value(doc, "Mcu/Cfg/Freq", "999")
        freq_new = next(v for v in new_doc.values if v.path == "Mcu/Cfg/Freq")
        freq_old = next(v for v in doc.values if v.path == "Mcu/Cfg/Freq")
        assert freq_new.raw == "999"
        assert freq_old.raw == "100"  # 原 doc 不变

    def test_set_value_path_not_found_raises(self, tmp_path: Path) -> None:
        """path 不在 doc.values → ValueError。"""
        path = _make_module_xdm(tmp_path / "Mcu.xdm", "Mcu")
        doc = load_module(path, "Mcu")
        with pytest.raises(ValueError, match="not in ECUCDocument"):
            ecuc_set_value(doc, "Mcu/NonExistent/X", "100")

    def test_list_paths_returns_sorted(self, tmp_path: Path) -> None:
        """``list_paths`` 排序。"""
        path = _make_module_xdm(tmp_path / "Mcu.xdm", "Mcu")
        doc = load_module(path, "Mcu")
        # 确认 list_paths 行为
        from autoc.core.bsw.ecuc import list_paths

        assert list_paths(doc) == tuple(sorted(p.path for p in doc.values))


class TestSprint8E1CoverageEcucInferType:
    """``_infer_type`` BSWMD 优先 vs DEST 启发式。"""

    def test_infer_type_bswmd_priority_over_dest(self) -> None:
        """BSWMD 命中 → 用 BSWMD 类型。"""
        from autoc.core.bsw.ecuc import _infer_type

        # BSWMD ParamDef.full_path 必须与 def_ref text 完全一致才会命中
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
        # BSWMD 优先 → ENUMERATION（不是 INTEGER 启发式）
        assert _infer_type(def_ref, bswmd_registry=bswmd) == "ENUMERATION"

    def test_infer_type_fallback_dest_heuristic(self) -> None:
        """BSWMD miss → DEST 启发式。"""
        from autoc.core.bsw.ecuc import _infer_type

        def_ref = etree.fromstring('<DEF DEST="ECUC-FLOAT-PARAM-DEF">/x</DEF>')
        # BSWMD 返 None（def_ref.text 路径 miss）
        bswmd = BSWMDRegistry()  # 空
        assert _infer_type(def_ref, bswmd_registry=bswmd) == "FLOAT"

    def test_infer_type_dest_vendor_extension_falls_back_to_string(self) -> None:
        """DEST 不匹配 → STRING（最安全 fallback）。"""
        from autoc.core.bsw.ecuc import _infer_type

        def_ref = etree.fromstring('<DEF DEST="ECUC-VENDOR-SPECIFIC">/x</DEF>')
        assert _infer_type(def_ref, bswmd_registry=None) == "STRING"

    def test_infer_type_bswmd_miss_falls_back_to_dest(self) -> None:
        """BSWMD 给了但 path miss → fallback DEST。"""
        from autoc.core.bsw.ecuc import _infer_type

        def_ref = etree.fromstring('<DEF DEST="ECUC-STRING-PARAM-DEF">/no/such/path</DEF>')
        # BSWMD 命中 /no/such/path 返 None
        bswmd = BSWMDRegistry(modules={"X": ModuleDef(short_name="X", full_path="/X")})
        # fallback → DEST 启发式
        assert _infer_type(def_ref, bswmd_registry=bswmd) == "STRING"

    def test_infer_type_bswmd_function_name_returns_string(self) -> None:
        """BSWMD param_type=FUNCTION_NAME（不在 ECUCType 范围）→ fallback DEST。"""
        from autoc.core.bsw.ecuc import _infer_type

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
        # FUNCTION_NAME 不在 ECUCType 映射 → fallback DEST
        assert _infer_type(def_ref, bswmd_registry=bswmd) == "STRING"


# ===========================================================================
# config BSWParam.def_ref / BSWModule.with_def_ref / from_ecuc / to_ecuc
# ===========================================================================


class TestSprint8E1CoverageConfigBSWParam:
    """``BSWParam.def_ref`` 字段。"""

    def test_bswparam_def_ref_default_none(self) -> None:
        """``def_ref`` 默认 None。"""
        p = BSWParam(path="Mcu/Cfg/Freq", value=ParamValue(raw="1", type=ParamType.INTEGER))
        assert p.def_ref is None

    def test_bswparam_def_ref_explicit(self) -> None:
        """``def_ref`` 显式给定。"""
        p = BSWParam(
            path="Mcu/Cfg/Freq",
            value=ParamValue(raw="1", type=ParamType.INTEGER),
            def_ref="/AUTOSAR/Mcu/Cfg/Freq",
        )
        assert p.def_ref == "/AUTOSAR/Mcu/Cfg/Freq"

    def test_bswparam_def_ref_must_be_str_or_none(self) -> None:
        """``def_ref`` 非 str/None → TypeError。"""
        with pytest.raises(TypeError, match="def_ref must be str or None"):
            BSWParam(
                path="Mcu/Cfg/Freq",
                value=ParamValue(raw="1", type=ParamType.INTEGER),
                def_ref=123,  # type: ignore[arg-type]
            )

    def test_paramvalue_raw_must_be_str(self) -> None:
        """``ParamValue.raw`` 非 str → TypeError。"""
        with pytest.raises(TypeError, match="raw must be str"):
            ParamValue(raw=123, type=ParamType.INTEGER)  # type: ignore[arg-type]

    def test_paramvalue_type_must_be_paramtype(self) -> None:
        """``ParamValue.type`` 非 ParamType → TypeError。"""
        with pytest.raises(TypeError, match="type must be ParamType"):
            ParamValue(raw="1", type="integer")  # type: ignore[arg-type]

    def test_paramvalue_as_accessors(self) -> None:
        """``as_int/as_float/as_bool/as_str`` 行为。"""
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
        """``as_int`` 在非 INTEGER 类型上抛 TypeError。"""
        p = ParamValue(raw="x", type=ParamType.STRING)
        with pytest.raises(TypeError):
            p.as_int()


class TestSprint8E1CoverageConfigBSWModule:
    """``BSWModule.with_def_ref`` / ``get`` / ``with_param``。"""

    def test_bswmodule_get_returns_param(self) -> None:
        """``get`` 命中。"""
        param = BSWParam(
            path="Mcu/Cfg/Freq",
            value=ParamValue(raw="1", type=ParamType.INTEGER),
        )
        m = BSWModule(name="Mcu", params=(param,))
        assert m.get("Mcu/Cfg/Freq") is param
        assert m.get("Mcu/Other") is None

    def test_bswmodule_with_param_replaces_existing(self) -> None:
        """``with_param`` 同 path → 替换。"""
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
        # 原 m 不变
        assert m.params == (old,)

    def test_bswmodule_with_param_appends_new(self) -> None:
        """``with_param`` 新 path → 追加。"""
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
        """``with_def_ref`` 替换已有 path 的 def_ref。"""
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
        """``with_def_ref`` path 不在 params → ValueError。"""
        m = BSWModule(name="Mcu")
        with pytest.raises(ValueError, match="not in params"):
            m.with_def_ref("Mcu/NonExistent", "/x")

    def test_bswmodule_empty_name_raises(self) -> None:
        """``BSWModule(name='')`` → ValueError。"""
        with pytest.raises(ValueError, match="name must be non-empty"):
            BSWModule(name="")

    def test_bswmodule_params_must_be_tuple(self) -> None:
        """``params`` 非 tuple → TypeError。"""
        with pytest.raises(TypeError, match="params must be a tuple"):
            BSWModule(name="Mcu", params=[])  # type: ignore[arg-type]

    def test_bswmodule_params_must_contain_bswparam_only(self) -> None:
        """``params`` 含非 BSWParam → TypeError。"""
        with pytest.raises(TypeError, match="must contain BSWParam"):
            BSWModule(name="Mcu", params=("not a BSWParam",))  # type: ignore[arg-type]

    def test_bswparam_empty_path_raises(self) -> None:
        """``BSWParam(path='')`` → ValueError（必须含 /）。"""
        with pytest.raises(ValueError, match="path must be hierarchical"):
            BSWParam(path="", value=ParamValue(raw="1", type=ParamType.INTEGER))

    def test_bswparam_path_without_slash_raises(self) -> None:
        """``BSWParam(path='Mcu')`` → ValueError（必须含 /）。"""
        with pytest.raises(ValueError, match="path must be hierarchical"):
            BSWParam(
                path="Mcu",
                value=ParamValue(raw="1", type=ParamType.INTEGER),
            )

    def test_bswparam_value_must_be_paramvalue(self) -> None:
        """``value`` 非 ParamValue → TypeError。"""
        with pytest.raises(TypeError, match="value must be ParamValue"):
            BSWParam(path="Mcu/Cfg", value="not a ParamValue")  # type: ignore[arg-type]


# ===========================================================================
# config BSWModule.from_ecuc / to_ecuc round-trip
# ===========================================================================


class TestSprint8E1CoverageConfigRoundTrip:
    """``from_ecuc`` / ``to_ecuc`` 互转。"""

    def test_from_ecuc_converts_values(self, tmp_path: Path) -> None:
        """``from_ecuc`` 把 ECUCValue 转 BSWParam。"""
        path = _make_module_xdm(tmp_path / "Mcu.xdm", "Mcu")
        doc = load_module(path, "Mcu")
        module = BSWModule.from_ecuc(doc)
        assert module.name == "Mcu"
        assert any(p.path == "Mcu/Cfg/Freq" for p in module.params)
        freq_p = next(p for p in module.params if p.path == "Mcu/Cfg/Freq")
        assert freq_p.value.raw == "100"
        assert freq_p.value.type == ParamType.INTEGER

    def test_to_ecuc_serializes_back(self, tmp_path: Path) -> None:
        """``to_ecuc`` 把 BSWModule 转 ECUCValue。"""
        path = _make_module_xdm(tmp_path / "Mcu.xdm", "Mcu")
        doc = load_module(path, "Mcu")
        module = BSWModule.from_ecuc(doc)
        new_doc = module.to_ecuc(path)
        assert new_doc.module_name == "Mcu"
        assert any(v.path == "Mcu/Cfg/Freq" for v in new_doc.values)

    def test_to_ecuc_path_without_slash_raises(self) -> None:
        """``to_ecuc`` 内部 BSWParam.path 不含 / → ValueError。

        注：BSWParam 自身 ``__post_init__`` 已经拒非法 path；但 to_ecuc 也有
        防御性检查。我们用 ``object.__new__`` 绕过 ``__post_init__`` 构造
        一个 BSWParam-shape 对象来验证 to_ecuc 的内部检查也会触发。
        """

        m = BSWModule(name="Mcu")
        # 构造"非法"BSWParam（绕过 __post_init__）
        bad_param = BSWParam.__new__(BSWParam)
        object.__setattr__(bad_param, "path", "NoSlash")
        object.__setattr__(
            bad_param,
            "value",
            ParamValue(raw="1", type=ParamType.INTEGER),
        )
        object.__setattr__(bad_param, "def_ref", None)
        # 注入到 params
        object.__setattr__(m, "params", (bad_param,))
        with pytest.raises(ValueError, match="path must be hierarchical"):
            m.to_ecuc(Path("/tmp/x.xdm"))


# ===========================================================================
# ecuc._walk / _emit_parameter / _emit_reference / _infer_type 边界
# ===========================================================================


class TestSprint8E1CoverageEcucWalkInternals:
    """``_walk`` / ``_emit_*`` / ``_infer_type`` 各 branch。"""

    def test_load_module_nsmap_mismatch_falls_back_to_actual(self, tmp_path: Path) -> None:
        """``nsmap`` 与 root 实际 nsmap 不一致 → 用 actual_nsmap 兜底（L136）。"""
        path = _make_module_xdm(tmp_path / "Mcu.xdm", "Mcu")
        # 故意传错 nsmap（prefix 名字对但 URI 是错的）
        bad_nsmap = {"ar": "http://WRONG", "xsi": "..."}
        # 不抛；用 root 实际 nsmap 兜底
        doc = load_module(path, "Mcu", nsmap=bad_nsmap)
        assert doc.module_name == "Mcu"
        # values 仍被解析
        assert any(v.path == "Mcu/Cfg/Freq" for v in doc.values)

    def test_emit_parameter_no_def_ref_skipped(self, tmp_path: Path) -> None:
        """``_emit_parameter`` 收到无 DEFINITION-REF 的 pv → skip（L254-258）。"""
        # 造一个没有 DEFINITION-REF 的 NUMERICAL-PARAM-VALUE
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
        # 只剩有 def-ref 的那条
        assert len(doc.values) == 1
        assert doc.values[0].path == "Mcu/Cfg/Freq"

    def test_emit_parameter_no_value_text_skipped(self, tmp_path: Path) -> None:
        """``_emit_parameter`` 收到 <VALUE> 缺失的 pv → skip（L261）。"""
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
        # value 缺 → 不收
        assert doc.values == ()

    def test_emit_reference_no_value_ref_text_empty(self, tmp_path: Path) -> None:
        """``_emit_reference`` 收到 <VALUE-REF> 缺失 → raw=empty string。"""
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
        assert ref.raw == ""  # 无 VALUE-REF → empty
        assert ref.type == "STRING"

    def test_emit_reference_with_value_ref(self, tmp_path: Path) -> None:
        """``_emit_reference`` 收到 <VALUE-REF> → raw 包含 target path。"""
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
        """``_walk`` 容器直接挂在 module 根下（无 wrapper）→ 命中（L237-241）。"""
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
        """``_walk`` 容器无 SHORT-NAME → skip（L232）。"""
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
        # 无 SHORT-NAME → skip
        assert doc.values == ()

    def test_emit_parameter_empty_def_ref_text_skipped(self, tmp_path: Path) -> None:
        """``_emit_parameter`` 收到 def-ref 但 text 为空 → skip（L286）。"""
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
        # def-ref 空 text → _definition_ref_short_name 返 None → skip
        assert doc.values == ()
