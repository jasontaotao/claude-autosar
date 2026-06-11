"""adapters/protocol.py 数据模型与协议结构化子类型测试。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from autoc.adapters.protocol import (
    CalcResult,
    DavinciAdapter,
    EcuConfigProjectContext,
    SaveResult,
    TresosAdapter,
    VerifyResult,
)

# =============================================================================
# EcuConfigProjectContext
# =============================================================================


class TestEcuConfigProjectContext:
    """EcuConfigProjectContext 字段校验。"""

    def test_minimal_context(self, tmp_path: Path) -> None:
        """最小可构造。"""
        project = tmp_path / "p"
        project.mkdir()
        home = tmp_path / "h"
        home.mkdir()
        ctx = EcuConfigProjectContext(
            project_path=project,
            tool_home=home,
            target="ARM",
            derivate="S32K344",
            pn="S32K344",
            autosar_version="4.4.0",
            enabled_modules=("Mcu", "Port"),
            available_plugins=(),
        )
        assert ctx.derivate == "S32K344"
        assert ctx.enabled_modules == ("Mcu", "Port")

    def test_project_path_must_be_dir(self, tmp_path: Path) -> None:
        """project_path 必须是目录。"""
        with pytest.raises(ValueError, match="project_path is not a directory"):
            EcuConfigProjectContext(
                project_path=tmp_path / "nope",
                tool_home=tmp_path,
                target="ARM",
                derivate="X",
                pn="X",
                autosar_version="4.4.0",
                enabled_modules=(),
                available_plugins=(),
            )

    def test_tool_home_must_be_dir(self, tmp_path: Path) -> None:
        """tool_home 必须是目录。"""
        project = tmp_path / "p"
        project.mkdir()
        with pytest.raises(ValueError, match="tool_home is not a directory"):
            EcuConfigProjectContext(
                project_path=project,
                tool_home=tmp_path / "nope",
                target="ARM",
                derivate="X",
                pn="X",
                autosar_version="4.4.0",
                enabled_modules=(),
                available_plugins=(),
            )

    @pytest.mark.parametrize(
        ("target", "derivate", "autosar"),
        [
            ("", "X", "4.4.0"),
            ("ARM", "", "4.4.0"),
            ("ARM", "X", ""),
        ],
    )
    def test_required_fields_non_empty(
        self, tmp_path: Path, target: str, derivate: str, autosar: str
    ) -> None:
        """target / derivate / autosar_version 不能为空。"""
        project = tmp_path / "p"
        project.mkdir()
        home = tmp_path / "h"
        home.mkdir()
        with pytest.raises(ValueError, match="must be non-empty"):
            EcuConfigProjectContext(
                project_path=project,
                tool_home=home,
                target=target,
                derivate=derivate,
                pn="X",
                autosar_version=autosar,
                enabled_modules=(),
                available_plugins=(),
            )

    def test_frozen(self, tmp_path: Path) -> None:
        """frozen 不可修改。"""
        project = tmp_path / "p"
        project.mkdir()
        home = tmp_path / "h"
        home.mkdir()
        ctx = EcuConfigProjectContext(
            project_path=project,
            tool_home=home,
            target="ARM",
            derivate="S32K344",
            pn="S32K344",
            autosar_version="4.4.0",
            enabled_modules=(),
            available_plugins=(),
        )
        with pytest.raises(FrozenInstanceError):
            ctx.derivate = "TC38XQ"  # type: ignore[misc]


# =============================================================================
# Result dataclasses
# =============================================================================


class TestResultDataclasses:
    """VerifyResult / SaveResult / CalcResult。"""

    def test_verify_result_fields(self) -> None:
        """VerifyResult 字段。"""
        r = VerifyResult(success=True, returncode=0, stdout="ok", stderr="")
        assert r.success is True
        assert r.returncode == 0
        assert r.stdout == "ok"

    def test_save_result_with_written_files(self, tmp_path: Path) -> None:
        """SaveResult 包含 written_files。"""
        f1 = tmp_path / "a.xdm"
        f2 = tmp_path / "b.xdm"
        r = SaveResult(
            success=True,
            returncode=0,
            stdout="wrote a.xdm wrote b.xdm",
            stderr="",
            written_files=(f1, f2),
        )
        assert r.written_files == (f1, f2)

    def test_save_result_default_empty_written_files(self) -> None:
        """SaveResult written_files 默认空 tuple。"""
        r = SaveResult(success=False, returncode=1, stdout="", stderr="fail")
        assert r.written_files == ()

    def test_calc_result_fields(self) -> None:
        """CalcResult 字段。"""
        r = CalcResult(success=True, returncode=0, stdout="", stderr="")
        assert r.success is True


# =============================================================================
# Protocol 结构化子类型
# =============================================================================


class TestProtocols:
    """TresosAdapter / DavinciAdapter 是运行时可检查的 Protocol。"""

    def test_stub_tresos_is_protocol(self) -> None:
        """Stub 实现满足 TresosAdapter Protocol（runtime_checkable）。"""
        from autoc.adapters.stub import StubTresosAdapter

        assert issubclass(StubTresosAdapter, TresosAdapter)

    def test_stub_davinci_is_protocol(self) -> None:
        """Stub 实现满足 DavinciAdapter Protocol。"""
        from autoc.adapters.stub import StubDavinciAdapter

        assert issubclass(StubDavinciAdapter, DavinciAdapter)

    def test_real_tresos_is_protocol(self) -> None:
        """真实 TresosAdapter 满足 Protocol。"""
        from autoc.adapters.tresos import TresosAdapter as RealTresos

        assert issubclass(RealTresos, TresosAdapter)

    def test_real_davinci_is_protocol(self) -> None:
        """真实 DavinciAdapter 满足 Protocol。"""
        from autoc.adapters.davinci import DavinciAdapter as RealDavinci

        assert issubclass(RealDavinci, DavinciAdapter)

    def test_ctx_is_shared_between_protocols(self, tmp_path: Path) -> None:
        """EcuConfigProjectContext 是 Tresos + DaVinci 共用 DTO。

        锁定 T3.1 重命名的核心动机：``EcuConfigProjectContext`` 必须能被两个
        协议共同消费，不允许未来把 DTO 拆成 ``TresosProjectContext`` /
        ``DavinciProjectContext`` 两个子类。
        """
        from autoc.adapters.stub import StubDavinciAdapter, StubTresosAdapter

        project = tmp_path / "p"
        project.mkdir()
        home = tmp_path / "h"
        home.mkdir()
        ctx = EcuConfigProjectContext(
            project_path=project,
            tool_home=home,
            target="ARM",
            derivate="S32K344",
            pn="S32K344",
            autosar_version="4.4.0",
            enabled_modules=(),
            available_plugins=(),
        )

        tresos_stub = StubTresosAdapter(discover_response=ctx)
        davinci_stub = StubDavinciAdapter()
        # 同一个 ctx 既走 Tresos 又走 DaVinci
        tresos_stub.verify(ctx, module="Mcu")
        davinci_stub.verify(ctx, module="Mcu")
        assert tresos_stub.verify_calls[0][0] is ctx
        assert davinci_stub.verify_calls[0][0] is ctx
