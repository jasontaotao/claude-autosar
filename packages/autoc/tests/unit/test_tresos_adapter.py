"""TresosAdapter subprocess 包装测试（除路径发现外不调真实工具）。"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
from unittest.mock import patch

import pytest
from tests.conftest import _build_fake_tresos

from autoc.adapters.tresos import TresosAdapter, TresosAdapterError

# =============================================================================
# __init__ 参数校验
# =============================================================================


class TestTresosInitValidation:
    """``__init__`` 参数校验。"""

    @pytest.mark.parametrize("bad", [0, -1, -100])
    def test_non_positive_timeout_rejected(self, bad: int) -> None:
        """``default_timeout_s <= 0`` 抛 ValueError。"""
        with pytest.raises(ValueError, match="default_timeout_s must be > 0"):
            TresosAdapter(default_timeout_s=bad)

    def test_positive_timeout_accepted(self) -> None:
        """正数 timeout 正常接受。"""
        TresosAdapter(default_timeout_s=1)
        TresosAdapter(default_timeout_s=300)


# =============================================================================
# subprocess 路径发现
# =============================================================================


class TestTresosCmdPath:
    """_tresos_cmd_path 跨平台查找。"""

    def test_finds_bat_on_windows(self, tmp_path: Path) -> None:
        """Windows 上找 ``tresos_cmd.bat``。"""
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        (bin_dir / "tresos_cmd.bat").write_text("@echo off", encoding="utf-8")
        ctx_path = bin_dir / "tresos_cmd.bat"
        # Windows 上 os.name == "nt"
        if os.name == "nt":
            result = TresosAdapter()._tresos_cmd_path(_make_ctx(tmp_path, tmp_path))
            assert result == ctx_path

    def test_finds_sh_on_unix(self, tmp_path: Path) -> None:
        """非 Windows 上找 ``tresos_cmd.sh``。"""
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        (bin_dir / "tresos_cmd.sh").write_text("#!/bin/sh\n", encoding="utf-8")
        if os.name != "nt":
            result = TresosAdapter()._tresos_cmd_path(_make_ctx(tmp_path, tmp_path))
            assert result == bin_dir / "tresos_cmd.sh"

    def test_missing_executable_raises(self, tmp_path: Path) -> None:
        """找不到 tresos_cmd 抛 TresosAdapterError。"""
        with pytest.raises(TresosAdapterError, match="tresos_cmd not found"):
            TresosAdapter()._tresos_cmd_path(_make_ctx(tmp_path, tmp_path))


# =============================================================================
# subprocess.run 包装（mock subprocess，不真跑）
# =============================================================================


class TestSubprocessWrappers:
    """verify / save / autocalc 的 subprocess 包装（mock subprocess.run）。"""

    @patch("autoc.adapters.tresos.subprocess.run")
    def test_verify_runs_validate_subcommand(
        self, mock_run: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """verify() 调用 ``--validate`` 子命令。"""
        _build_fake_tresos(tmp_path, chip_id="X", enabled_modules=["Mcu"])
        ctx = _make_ctx(tmp_path, tmp_path)
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="OK", stderr=""
        )
        result = TresosAdapter().verify(ctx, module="Mcu")
        assert result.success is True
        # 验证调用了 --validate --module Mcu
        call_args = mock_run.call_args[0][0]
        assert "--validate" in call_args
        assert "--module" in call_args
        assert "Mcu" in call_args

    @patch("autoc.adapters.tresos.subprocess.run")
    def test_windows_bat_uses_cmd_exe_not_shell(
        self, mock_run: pytest.MonkeyPatch, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        r"""Windows + .bat：用 ``cmd.exe /c <bat> <args>`` 包装，``shell=False``。

        解决 ``C:\Program Files\EB tresos`` 带空格路径下 ``shell=True`` 引发的解析问题。
        """
        # 强制走 Windows 路径
        monkeypatch.setattr("os.name", "nt")
        _build_fake_tresos(tmp_path, chip_id="X", enabled_modules=[])
        ctx = _make_ctx(tmp_path, tmp_path)
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        TresosAdapter().verify(ctx)
        # shell 必须为 False（cmd 显式启动）
        assert mock_run.call_args.kwargs.get("shell") is False
        # 命令应以 cmd.exe + /c + bat 路径开头
        cmd = mock_run.call_args[0][0]
        assert cmd[0].lower().endswith("cmd.exe")
        assert cmd[1] == "/c"
        assert cmd[2].lower().endswith("tresos_cmd.bat")

    @patch("autoc.adapters.tresos.subprocess.run")
    def test_non_windows_runs_bat_directly(
        self, mock_run: pytest.MonkeyPatch, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """非 Windows：直接执行 sh 路径，``shell=False``。"""
        monkeypatch.setattr("os.name", "posix")
        # 非 Windows 需要 tresos_cmd.sh
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        (bin_dir / "tresos_cmd.sh").write_text("#!/bin/sh\n", encoding="utf-8")
        ctx = _make_ctx(tmp_path, tmp_path)
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        TresosAdapter().verify(ctx)
        assert mock_run.call_args.kwargs.get("shell") is False
        # 非 Windows 不经过 cmd.exe 包装
        cmd = mock_run.call_args[0][0]
        assert not cmd[0].lower().endswith("cmd.exe")
        assert cmd[0].endswith("tresos_cmd.sh")

    @patch("autoc.adapters.tresos.subprocess.run")
    def test_verify_without_module_runs_full_validate(
        self, mock_run: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """verify(module=None) 只传 ``--validate``。"""
        _build_fake_tresos(tmp_path, chip_id="X", enabled_modules=[])
        ctx = _make_ctx(tmp_path, tmp_path)
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        TresosAdapter().verify(ctx)
        call_args = mock_run.call_args[0][0]
        assert "--validate" in call_args
        assert "--module" not in call_args

    @patch("autoc.adapters.tresos.subprocess.run")
    def test_save_returns_written_files(self, mock_run: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """save() 解析 stdout 中的 "wrote *.xdm" 模式。"""
        _build_fake_tresos(tmp_path, chip_id="X", enabled_modules=["Mcu"])
        ctx = _make_ctx(tmp_path, tmp_path)
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="wrote Mcu.xdm\nwrote Port.xdm\n",
            stderr="",
        )
        result = TresosAdapter().save(ctx, module="Mcu")
        assert result.success is True
        assert len(result.written_files) == 2
        names = {p.name for p in result.written_files}
        assert "Mcu.xdm" in names
        assert "Port.xdm" in names

    @patch("autoc.adapters.tresos.subprocess.run")
    def test_save_failure_captured(self, mock_run: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """save() 失败时 success=False。"""
        _build_fake_tresos(tmp_path, chip_id="X", enabled_modules=[])
        ctx = _make_ctx(tmp_path, tmp_path)
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="save failed"
        )
        result = TresosAdapter().save(ctx)
        assert result.success is False
        assert result.returncode == 1

    @patch("autoc.adapters.tresos.subprocess.run")
    def test_autocalc_runs_autocalc_subcommand(
        self, mock_run: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """autocalc() 调 ``--autocalc``。"""
        _build_fake_tresos(tmp_path, chip_id="X", enabled_modules=[])
        ctx = _make_ctx(tmp_path, tmp_path)
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="calc OK", stderr=""
        )
        result = TresosAdapter().autocalc(ctx)
        assert result.success is True
        assert "--autocalc" in mock_run.call_args[0][0]

    @patch("autoc.adapters.tresos.subprocess.run")
    def test_timeout_raises(self, mock_run: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """subprocess 超时抛 TresosAdapterError。"""
        _build_fake_tresos(tmp_path, chip_id="X", enabled_modules=[])
        ctx = _make_ctx(tmp_path, tmp_path)
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="tresos", timeout=1.0)
        with pytest.raises(TresosAdapterError, match="timed out"):
            TresosAdapter(default_timeout_s=1).verify(ctx)

    @patch("autoc.adapters.tresos.subprocess.run")
    def test_filenotfound_raises(self, mock_run: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """subprocess 不存在抛 TresosAdapterError。"""
        _build_fake_tresos(tmp_path, chip_id="X", enabled_modules=[])
        ctx = _make_ctx(tmp_path, tmp_path)
        mock_run.side_effect = FileNotFoundError()
        with pytest.raises(TresosAdapterError, match="FileNotFoundError"):
            TresosAdapter().verify(ctx)

    @patch("autoc.adapters.tresos.subprocess.run")
    def test_permissionerror_raises(self, mock_run: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """subprocess 抛 PermissionError（如 tool_home 无执行权限）时包成 TresosAdapterError。"""
        _build_fake_tresos(tmp_path, chip_id="X", enabled_modules=[])
        ctx = _make_ctx(tmp_path, tmp_path)
        mock_run.side_effect = PermissionError("Access is denied")
        with pytest.raises(TresosAdapterError, match="PermissionError"):
            TresosAdapter().verify(ctx)


# =============================================================================
# .project 解析
# =============================================================================


class TestParseProjectXml:
    """_parse_project_xml 行为。"""

    def test_tresos_style_extracts_properties(self, tmp_path: Path) -> None:
        """EB tresos 风格：``<tresos:property name="X">V</tresos:property>``。"""
        project_xml = tmp_path / ".project"
        # 直接写原始 XML，lxml 的 Element 构造对带前缀 tag 不友好
        project_xml.write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<tresos:project xmlns:tresos="http://www.tresos.de/xsd/tresos_002">
  <tresos:property name="target">ARM</tresos:property>
  <tresos:property name="derivate">S32K344</tresos:property>
  <tresos:property name="pn">S32K344</tresos:property>
  <tresos:property name="AutosarVersion">4.4.0</tresos:property>
</tresos:project>
""",
            encoding="utf-8",
        )
        props = TresosAdapter._parse_project_xml(project_xml)
        assert props.get("target") == "ARM"
        assert props.get("derivate") == "S32K344"
        assert props.get("AutosarVersion") == "4.4.0"

    def test_simple_style_extracts_elements(self, tmp_path: Path) -> None:
        """简化风格：``<target>V</target>``。"""
        project_xml = tmp_path / ".project"
        project_xml.write_text(
            """<?xml version="1.0"?>
<project>
  <target>RH850</target>
  <derivate>R7F701Z3</derivate>
  <pn>R7F701Z3</pn>
  <autosarVersion>4.0.3</autosarVersion>
</project>
""",
            encoding="utf-8",
        )
        props = TresosAdapter._parse_project_xml(project_xml)
        assert props.get("target") == "RH850"
        assert props.get("derivate") == "R7F701Z3"
        assert props.get("autosarVersion") == "4.0.3"

    def test_malformed_xml_raises(self, tmp_path: Path) -> None:
        """非法 XML 抛 TresosAdapterError。"""
        project_xml = tmp_path / ".project"
        project_xml.write_text("not valid xml<", encoding="utf-8")
        with pytest.raises(TresosAdapterError, match="malformed"):
            TresosAdapter._parse_project_xml(project_xml)

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        """不存在的文件抛 TresosAdapterError。"""
        with pytest.raises(TresosAdapterError, match="not found"):
            TresosAdapter._parse_project_xml(tmp_path / "nope")


# =============================================================================
# Helper
# =============================================================================


def _make_ctx(project: Path, tool_home: Path):  # type: ignore[no-untyped-def]
    """构造最小 EcuConfigProjectContext（仅用于路径/适配器测试）。"""
    from autoc.adapters.protocol import EcuConfigProjectContext

    return EcuConfigProjectContext(
        project_path=project,
        tool_home=tool_home,
        target="TEST",
        derivate="TEST",
        pn="TEST",
        autosar_version="4.4.0",
        enabled_modules=(),
        available_plugins=(),
    )
