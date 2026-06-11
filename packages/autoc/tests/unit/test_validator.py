"""Unit tests for packages/autoc/src/autoc/core/bsw/validator.py.

TDD 阶段：RED（先写测试）。Sprint 3 — T3.3。
"""

from __future__ import annotations

import contextlib
from pathlib import Path

import pytest

from autoc.adapters.protocol import (
    EcuConfigProjectContext,
    SaveResult,
    VerifyResult,
)
from autoc.adapters.stub import StubTresosAdapter
from autoc.core.bsw.config import BSWParam, ParamType, ParamValue
from autoc.core.bsw.validator import (
    ModifyRequest,
    ValidatorError,
    modify_and_verify,
)

pytestmark = pytest.mark.autosar


# ---------------------------------------------------------------------------
# helpers / fixtures
# ---------------------------------------------------------------------------


_MCU_XML = """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES><AR-PACKAGE><SHORT-NAME>B</SHORT-NAME><ELEMENTS>
    <ECUC-MODULE-CONFIGURATION-VALUES>
      <SHORT-NAME>Mcu</SHORT-NAME>
      <CONTAINERS>
        <ECUC-PARAM-CONF-CONTAINER>
          <SHORT-NAME>Root</SHORT-NAME>
          <PARAMETER-VALUES>
            <ECUC-NUMERICAL-PARAM-VALUE>
              <DEFINITION-REF DEST="ECUC-INTEGER-PARAM-DEF">/Mcu/Root/ClockFreq</DEFINITION-REF>
              <VALUE>80000000</VALUE>
            </ECUC-NUMERICAL-PARAM-VALUE>
          </PARAMETER-VALUES>
        </ECUC-PARAM-CONF-CONTAINER>
      </CONTAINERS>
    </ECUC-MODULE-CONFIGURATION-VALUES>
  </ELEMENTS></AR-PACKAGE></AR-PACKAGES>
</AUTOSAR>
"""


def _make_project(tmp_path: Path) -> Path:
    project = tmp_path / "bsw-project"
    project.mkdir()
    (project / "Mcu.xdm").write_text(_MCU_XML, encoding="utf-8")
    return project


def _make_ctx(project: Path) -> EcuConfigProjectContext:
    # tool_home 必须是真实目录（EcuConfigProjectContext.__post_init__ 校验）
    tool_home = project.parent / "fake-tresos"
    tool_home.mkdir(exist_ok=True)
    return EcuConfigProjectContext(
        project_path=project,
        tool_home=tool_home,
        target="S32K3",
        derivate="S32K344",
        pn="ARM",
        autosar_version="4.4.0",
        enabled_modules=("Mcu",),
        available_plugins=(),
    )


def _stub_for_ctx(ctx: EcuConfigProjectContext) -> StubTresosAdapter:
    """构造 StubTresosAdapter，必填 discover_response 用 ctx 填。"""
    return StubTresosAdapter(discover_response=ctx)


def _freq_path() -> str:
    return "Mcu/Root/ClockFreq"


def _freq_param(new_raw: str = "120000000") -> BSWParam:
    return BSWParam(_freq_path(), ParamValue(new_raw, ParamType.INTEGER))


# ---------------------------------------------------------------------------
# happy_path
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_modify_and_verify_success(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        ctx = _make_ctx(project)
        adapter = StubTresosAdapter(
            discover_response=ctx,
            verify_responses=[VerifyResult(success=True, returncode=0, stdout="OK", stderr="")],
            save_responses=[
                SaveResult(
                    success=True,
                    returncode=0,
                    stdout="wrote Mcu.xdm",
                    stderr="",
                    written_files=(project / "Mcu.xdm",),
                )
            ],
        )
        result = modify_and_verify(
            ctx, adapter, ModifyRequest(module="Mcu", params=(_freq_param(),))
        )
        assert result.success is True
        assert result.rolled_back is False
        assert result.error is None
        assert result.written_files == (project / "Mcu.xdm",)

        # 文件内容应被改了
        from autoc.core.bsw.ecuc import load_module

        doc = load_module(project / "Mcu.xdm", "Mcu")
        val = next(v for v in doc.values if v.path == _freq_path())
        assert val.raw == "120000000"

    def test_modify_does_not_pollute_project_dir(self, tmp_path: Path) -> None:
        """happy path 完成后，project 根目录不应有 .autoc-snapshot/。"""
        project = _make_project(tmp_path)
        ctx = _make_ctx(project)
        adapter = StubTresosAdapter(
            discover_response=ctx,
            verify_responses=[VerifyResult(success=True, returncode=0, stdout="OK", stderr="")],
            save_responses=[
                SaveResult(success=True, returncode=0, stdout="", stderr="", written_files=())
            ],
        )
        modify_and_verify(ctx, adapter, ModifyRequest(module="Mcu", params=(_freq_param(),)))
        assert not (project / ".autoc-snapshot").exists()


# ---------------------------------------------------------------------------
# verify 失败 → 回滚
# ---------------------------------------------------------------------------


class TestVerifyFailure:
    def test_verify_fail_rolls_back(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        ctx = _make_ctx(project)
        original_xml = (project / "Mcu.xdm").read_text(encoding="utf-8")

        adapter = StubTresosAdapter(
            discover_response=ctx,
            verify_responses=[
                VerifyResult(success=False, returncode=1, stdout="", stderr="validation failed")
            ],
            save_responses=[
                SaveResult(success=True, returncode=0, stdout="", stderr="", written_files=())
            ],
        )
        result = modify_and_verify(
            ctx, adapter, ModifyRequest(module="Mcu", params=(_freq_param(),))
        )
        assert result.success is False
        assert result.rolled_back is True
        assert "validation failed" in (result.verify_output or "")

        # 文件应被还原到原始内容
        assert (project / "Mcu.xdm").read_text(encoding="utf-8") == original_xml

    def test_verify_fail_no_save_called(self, tmp_path: Path) -> None:
        """verify 失败后不应该调 save。"""
        project = _make_project(tmp_path)
        ctx = _make_ctx(project)
        adapter = StubTresosAdapter(
            discover_response=ctx,
            verify_responses=[VerifyResult(success=False, returncode=1, stdout="", stderr="")],
            save_responses=[
                SaveResult(
                    success=True,
                    returncode=0,
                    stdout="",
                    stderr="",
                    written_files=(Path("/should/not/be/called"),),
                )
            ],
        )
        modify_and_verify(ctx, adapter, ModifyRequest(module="Mcu", params=(_freq_param(),)))
        assert len(adapter.save_calls) == 0


# ---------------------------------------------------------------------------
# no_change skip
# ---------------------------------------------------------------------------


class TestNoChangeSkip:
    def test_empty_params_skips(self, tmp_path: Path) -> None:
        """ModifyRequest.params 为空时短路：不调 verify / save。"""
        project = _make_project(tmp_path)
        ctx = _make_ctx(project)
        adapter = StubTresosAdapter(
            discover_response=ctx,
            verify_responses=[VerifyResult(success=True, returncode=0, stdout="", stderr="")],
        )
        result = modify_and_verify(ctx, adapter, ModifyRequest(module="Mcu", params=()))
        assert result.success is True
        assert result.rolled_back is False
        assert result.written_files == ()
        assert len(adapter.verify_calls) == 0
        assert len(adapter.save_calls) == 0


# ---------------------------------------------------------------------------
# 错误路径
# ---------------------------------------------------------------------------


class TestErrorPaths:
    def test_module_file_not_found_raises(self, tmp_path: Path) -> None:
        """module 的 .xdm / .arxml 都不存在 → ValidatorError。"""
        project = tmp_path / "empty-project"
        project.mkdir()
        ctx = _make_ctx(project)
        adapter = StubTresosAdapter(discover_response=ctx)
        with pytest.raises(ValidatorError, match="Mcu.*not found"):
            modify_and_verify(ctx, adapter, ModifyRequest(module="Mcu", params=(_freq_param(),)))

    def test_param_path_not_in_doc_raises_validator_error(self, tmp_path: Path) -> None:
        """param.path 在 ECUC 文档里不存在 → ValidatorError。"""
        project = _make_project(tmp_path)
        ctx = _make_ctx(project)
        adapter = StubTresosAdapter(discover_response=ctx)
        with pytest.raises(ValidatorError, match="ClockFreqXY"):
            modify_and_verify(
                ctx,
                adapter,
                ModifyRequest(
                    module="Mcu",
                    params=(
                        BSWParam(
                            "Mcu/Root/ClockFreqXY",
                            ParamValue("1", ParamType.INTEGER),
                        ),
                    ),
                ),
            )

    def test_snapshot_dir_cleaned_on_error(self, tmp_path: Path) -> None:
        """错误路径下，tempfile.mkdtemp 创建的 snapshot 目录应被清理。"""
        import tempfile

        project = _make_project(tmp_path)
        ctx = _make_ctx(project)
        adapter = StubTresosAdapter(discover_response=ctx)

        # 触发 error 路径（param path 不存在）
        with contextlib.suppress(ValidatorError):
            modify_and_verify(
                ctx,
                adapter,
                ModifyRequest(
                    module="Mcu",
                    params=(BSWParam("Mcu/Nonexistent", ParamValue("1", ParamType.INTEGER)),),
                ),
            )

        # 临时目录里不应有 autoc-snapshot-* 残留
        td = Path(tempfile.gettempdir())
        leftovers = list(td.glob("autoc-snapshot-*"))
        assert leftovers == [], f"snapshot dirs not cleaned: {leftovers}"


# ---------------------------------------------------------------------------
# .arxml 备选
# ---------------------------------------------------------------------------


class TestArxmlFallback:
    def test_module_file_arxml_extension(self, tmp_path: Path) -> None:
        """如果 .xdm 不存在但 .arxml 存在，validator 应走 .arxml。"""
        project = _make_project(tmp_path)
        (project / "Mcu.xdm").unlink()  # 移除 .xdm
        (project / "Mcu.arxml").write_text(_MCU_XML, encoding="utf-8")
        ctx = _make_ctx(project)
        adapter = StubTresosAdapter(
            discover_response=ctx,
            verify_responses=[VerifyResult(success=True, returncode=0, stdout="OK", stderr="")],
            save_responses=[
                SaveResult(success=True, returncode=0, stdout="", stderr="", written_files=())
            ],
        )
        result = modify_and_verify(
            ctx, adapter, ModifyRequest(module="Mcu", params=(_freq_param(),))
        )
        assert result.success is True
