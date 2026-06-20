"""Sprint 8.E.1 coverage: write / set_value / modify_and_verify / config round-trip.

Targets: arxml_io.write() + ecuc.set_value() + validator.modify_and_verify() + config round-trip.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from lxml import etree
import pytest

from claude_autosar.core.bsw.arxml_io import (
    ARXMLError,
    read,
)
from claude_autosar.core.bsw.arxml_io import write as arxml_write
from claude_autosar.core.bsw.config import BSWModule, BSWParam, ParamType, ParamValue
from claude_autosar.core.bsw.ecuc import (
    load_module,
)
from claude_autosar.core.bsw.ecuc import set_value as ecuc_set_value
from claude_autosar.core.bsw.validator import (
    ModifyRequest,
    ValidatorError,
    modify_and_verify,
)


# Helpers


def _write_xdm(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


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


def _make_ctx(project_path: Path) -> MagicMock:
    ctx = MagicMock()
    ctx.project_path = project_path
    return ctx


def _stub_adapter(
    *,
    verify_success: bool = True,
    save_success: bool = True,
) -> MagicMock:
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


# arxml_io write paths


class TestSprint8E1CoverageArxmlIoWrite:
    """``write`` 各种 preserve_format / atomic 路径。"""

    def test_write_preserve_format_true_with_existing_file(self, tmp_path: Path) -> None:
        path = _make_module_xdm(tmp_path / "Cfg.xdm", "Mcu")
        tree = etree.parse(str(path))
        for value_elem in tree.iter("{*}VALUE"):
            value_elem.text = "999"
        arxml_write(tree, path, atomic=True, preserve_format=True)
        new_bytes = path.read_bytes()
        assert b"999" in new_bytes
        assert b"<?xml" in new_bytes

    def test_write_preserve_format_false_uses_tostring(self, tmp_path: Path) -> None:
        path = _make_module_xdm(tmp_path / "Cfg.xdm", "Mcu")
        tree = etree.parse(str(path))
        for value_elem in tree.iter("{*}VALUE"):
            value_elem.text = "555"
        arxml_write(tree, path, atomic=True, preserve_format=False)
        assert b"555" in path.read_bytes()

    def test_write_non_atomic_writes_directly(self, tmp_path: Path) -> None:
        path = _make_module_xdm(tmp_path / "Cfg.xdm", "Mcu")
        tree = etree.parse(str(path))
        for value_elem in tree.iter("{*}VALUE"):
            value_elem.text = "777"
        arxml_write(tree, path, atomic=False, preserve_format=False)
        assert b"777" in path.read_bytes()
        assert not (tmp_path / "Cfg.xdm.tmp").exists()

    def test_write_with_arxmldocument_target_uses_doc_path(self, tmp_path: Path) -> None:
        path = _make_module_xdm(tmp_path / "Cfg.xdm", "Mcu")
        doc = read(path)
        for value_elem in doc.tree.iter("{*}VALUE"):
            value_elem.text = "333"
        arxml_write(doc, atomic=True, preserve_format=False)
        assert b"333" in path.read_bytes()

    def test_write_with_tree_requires_explicit_path(self, tmp_path: Path) -> None:
        path = _make_module_xdm(tmp_path / "Cfg.xdm", "Mcu")
        tree = etree.parse(str(path))
        with pytest.raises(TypeError, match="requires explicit path"):
            arxml_write(tree, path=None, atomic=True)

    def test_write_surgical_patch_unavailable_falls_back(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = _make_module_xdm(tmp_path / "Cfg.xdm", "Mcu")
        tree = etree.parse(str(path))
        from claude_autosar.core.bsw import arxml_io as aio_mod
        orig = aio_mod._write_surgical_patch

        def _raise(*_a: Any, **_kw: Any) -> None:
            raise aio_mod._SurgicalPatchUnavailable("test")

        monkeypatch.setattr(aio_mod, "_write_surgical_patch", _raise)
        try:
            for value_elem in tree.iter("{*}VALUE"):
                value_elem.text = "111"
            arxml_write(tree, path, atomic=True, preserve_format=True)
            assert b"111" in path.read_bytes()
        finally:
            monkeypatch.setattr(aio_mod, "_write_surgical_patch", orig)


# ecuc set_value


class TestSprint8E1CoverageEcucSetValue:
    """``set_value`` 不可变改值。"""

    def test_set_value_changes_raw(self, tmp_path: Path) -> None:
        path = _make_module_xdm(tmp_path / "Mcu.xdm", "Mcu")
        doc = load_module(path, "Mcu")
        new_doc = ecuc_set_value(doc, "Mcu/Cfg/Freq", "999")
        freq_new = next(v for v in new_doc.values if v.path == "Mcu/Cfg/Freq")
        freq_old = next(v for v in doc.values if v.path == "Mcu/Cfg/Freq")
        assert freq_new.raw == "999"
        assert freq_old.raw == "100"

    def test_set_value_path_not_found_raises(self, tmp_path: Path) -> None:
        path = _make_module_xdm(tmp_path / "Mcu.xdm", "Mcu")
        doc = load_module(path, "Mcu")
        with pytest.raises(ValueError, match="not in ECUCDocument"):
            ecuc_set_value(doc, "Mcu/NonExistent/X", "100")

    def test_list_paths_returns_sorted(self, tmp_path: Path) -> None:
        path = _make_module_xdm(tmp_path / "Mcu.xdm", "Mcu")
        doc = load_module(path, "Mcu")
        from claude_autosar.core.bsw.ecuc import list_paths
        assert list_paths(doc) == tuple(sorted(p.path for p in doc.values))


# validator modify_and_verify


class TestSprint8E1CoverageValidatorModify:
    """``modify_and_verify`` 各种路径。"""

    def test_modify_empty_params_returns_success_immediately(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        ctx = _make_ctx(project)
        adapter = _stub_adapter()
        req = ModifyRequest(module="Mcu", params=())
        result = modify_and_verify(ctx, adapter, req)
        assert result.success is True
        assert result.written_files == ()
        adapter.verify.assert_not_called()
        adapter.save.assert_not_called()

    def test_modify_module_file_not_found_raises_validator_error(self, tmp_path: Path) -> None:
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

    def test_modify_bswmd_validation_fails_returns_modify_result_error(self, tmp_path: Path) -> None:
        from claude_autosar.core.bsw.bswmd import BSWMDRegistry, ContainerDef, ModuleDef, ParamDef
        project = tmp_path / "proj"
        _make_module_xdm(project / "Mcu.xdm", "Mcu")
        ctx = _make_ctx(project)
        adapter = _stub_adapter()
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
        param = BSWParam(
            path="Mcu/Cfg/Freq",
            value=ParamValue(raw="999", type=ParamType.INTEGER),
        )
        req = ModifyRequest(module="Mcu", params=(param,))
        result = modify_and_verify(ctx, adapter, req, bswmd_registry=bswmd)
        assert result.success is False
        assert result.rolled_back is False
        assert "BSWMD validation failed" in (result.error or "")
        adapter.verify.assert_not_called()
        adapter.save.assert_not_called()

    def test_modify_load_module_fails_raises_validator_error(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
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
        assert (project / "Mcu.xdm").read_bytes() == original

    def test_modify_save_success_returns_written_files(self, tmp_path: Path) -> None:
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
        assert b"77" in (project / "Mcu.xdm").read_bytes()

    def test_modify_save_failure_returns_error(self, tmp_path: Path) -> None:
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


# config BSWModule.from_ecuc / to_ecuc round-trip


class TestSprint8E1CoverageConfigRoundTrip:
    """``from_ecuc`` / ``to_ecuc`` 互转。"""

    def test_from_ecuc_converts_values(self, tmp_path: Path) -> None:
        path = _make_module_xdm(tmp_path / "Mcu.xdm", "Mcu")
        doc = load_module(path, "Mcu")
        module = BSWModule.from_ecuc(doc)
        assert module.name == "Mcu"
        assert any(p.path == "Mcu/Cfg/Freq" for p in module.params)
        freq_p = next(p for p in module.params if p.path == "Mcu/Cfg/Freq")
        assert freq_p.value.raw == "100"
        assert freq_p.value.type == ParamType.INTEGER

    def test_to_ecuc_serializes_back(self, tmp_path: Path) -> None:
        path = _make_module_xdm(tmp_path / "Mcu.xdm", "Mcu")
        doc = load_module(path, "Mcu")
        module = BSWModule.from_ecuc(doc)
        new_doc = module.to_ecuc(path)
        assert new_doc.module_name == "Mcu"
        assert any(v.path == "Mcu/Cfg/Freq" for v in new_doc.values)

    def test_to_ecuc_path_without_slash_raises(self) -> None:
        m = BSWModule(name="Mcu")
        bad_param = BSWParam.__new__(BSWParam)
        object.__setattr__(bad_param, "path", "NoSlash")
        object.__setattr__(
            bad_param,
            "value",
            ParamValue(raw="1", type=ParamType.INTEGER),
        )
        object.__setattr__(bad_param, "def_ref", None)
        object.__setattr__(m, "params", (bad_param,))
        with pytest.raises(ValueError, match="path must be hierarchical"):
            m.to_ecuc(Path("/tmp/x.xdm"))
