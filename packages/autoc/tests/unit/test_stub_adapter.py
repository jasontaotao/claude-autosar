"""adapters/stub.py Stub 实现测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_autosar.adapters.protocol import (
    CalcResult,
    EcuConfigProjectContext,
    SaveResult,
    VerifyResult,
)
from claude_autosar.adapters.stub import StubDavinciAdapter, StubTresosAdapter


@pytest.fixture
def sample_ctx(tmp_path: Path) -> EcuConfigProjectContext:
    """最小可用上下文。"""
    project = tmp_path / "p"
    project.mkdir()
    home = tmp_path / "h"
    home.mkdir()
    return EcuConfigProjectContext(
        project_path=project,
        tool_home=home,
        target="ARM",
        derivate="S32K344",
        pn="S32K344",
        autosar_version="4.4.0",
        enabled_modules=("Mcu",),
        available_plugins=(),
    )


# =============================================================================
# StubTresosAdapter
# =============================================================================


class TestStubTresosAdapter:
    """StubTresosAdapter 记录调用 + 返回预设。"""

    def test_discover_returns_preset(self, sample_ctx: EcuConfigProjectContext) -> None:
        """discover() 返回预设 context。"""
        stub = StubTresosAdapter(discover_response=sample_ctx)
        result = stub.discover(project_path=Path("/dummy"), tool_home=Path("/dummy"))
        assert result is sample_ctx

    def test_verify_records_call(self, sample_ctx: EcuConfigProjectContext) -> None:
        """verify() 记录 (ctx, module) 元组。"""
        stub = StubTresosAdapter(discover_response=sample_ctx)
        stub.verify(sample_ctx, module="Mcu")
        assert stub.verify_calls == [(sample_ctx, "Mcu")]

    def test_verify_returns_preset_in_order(self, sample_ctx: EcuConfigProjectContext) -> None:
        """verify() 依次返回预设响应。"""
        stub = StubTresosAdapter(
            discover_response=sample_ctx,
            verify_responses=[
                VerifyResult(success=True, returncode=0, stdout="first", stderr=""),
                VerifyResult(success=False, returncode=1, stdout="", stderr="err"),
            ],
        )
        r1 = stub.verify(sample_ctx, module="Mcu")
        r2 = stub.verify(sample_ctx, module="Port")
        assert r1.stdout == "first"
        assert r2.returncode == 1

    def test_verify_default_when_no_preset(self, sample_ctx: EcuConfigProjectContext) -> None:
        """verify() 无预设时返回 success=True 默认。"""
        stub = StubTresosAdapter(discover_response=sample_ctx)
        r = stub.verify(sample_ctx, module="Mcu")
        assert r.success is True
        assert r.returncode == 0

    def test_save_records_call(self, sample_ctx: EcuConfigProjectContext) -> None:
        """save() 记录 (ctx, module)。"""
        stub = StubTresosAdapter(discover_response=sample_ctx)
        stub.save(sample_ctx, module="Can")
        assert stub.save_calls == [(sample_ctx, "Can")]

    def test_save_returns_written_files(
        self, sample_ctx: EcuConfigProjectContext, tmp_path: Path
    ) -> None:
        """save() 正确返回 written_files。"""
        f1 = tmp_path / "Mcu.xdm"
        stub = StubTresosAdapter(
            discover_response=sample_ctx,
            save_responses=[
                SaveResult(
                    success=True,
                    returncode=0,
                    stdout="",
                    stderr="",
                    written_files=(f1,),
                )
            ],
        )
        r = stub.save(sample_ctx, module="Mcu")
        assert r.written_files == (f1,)

    def test_autocalc_records_call(self, sample_ctx: EcuConfigProjectContext) -> None:
        """autocalc() 记录 ctx。"""
        stub = StubTresosAdapter(discover_response=sample_ctx)
        stub.autocalc(sample_ctx)
        assert stub.autocalc_calls == [sample_ctx]

    def test_autocalc_returns_preset(self, sample_ctx: EcuConfigProjectContext) -> None:
        """autocalc() 返回预设。"""
        stub = StubTresosAdapter(
            discover_response=sample_ctx,
            autocalc_response=CalcResult(
                success=False, returncode=42, stdout="", stderr="calc-fail"
            ),
        )
        r = stub.autocalc(sample_ctx)
        assert r.returncode == 42


# =============================================================================
# StubDavinciAdapter
# =============================================================================


class TestStubDavinciAdapter:
    """StubDavinciAdapter 行为。"""

    def test_verify_records_call(self, sample_ctx: EcuConfigProjectContext) -> None:
        """verify() 记录。"""
        stub = StubDavinciAdapter()
        stub.verify(sample_ctx, module="PduR")
        assert stub.verify_calls == [(sample_ctx, "PduR")]

    def test_save_records_call(self, sample_ctx: EcuConfigProjectContext) -> None:
        """save() 记录。"""
        stub = StubDavinciAdapter()
        stub.save(sample_ctx)
        assert stub.save_calls == [(sample_ctx, None)]

    def test_verify_returns_preset(self, sample_ctx: EcuConfigProjectContext) -> None:
        """verify() 返回预设。"""
        stub = StubDavinciAdapter(
            verify_responses=[VerifyResult(success=False, returncode=99, stdout="", stderr="")]
        )
        r = stub.verify(sample_ctx, module="EcuC")
        assert r.returncode == 99
