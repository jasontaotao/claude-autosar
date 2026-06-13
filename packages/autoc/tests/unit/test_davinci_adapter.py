"""DavinciAdapter subprocess 包装测试。"""

from __future__ import annotations

from pathlib import Path
import subprocess
from unittest.mock import patch

import pytest

from claude_autosar.adapters.davinci import DavinciAdapter, DavinciAdapterError
from claude_autosar.adapters.protocol import EcuConfigProjectContext


class TestDavinciInitValidation:
    """``__init__`` 参数校验。"""

    @pytest.mark.parametrize("bad", [0, -1, -100])
    def test_non_positive_timeout_rejected(self, bad: int) -> None:
        """``default_timeout_s <= 0`` 抛 ValueError。"""
        with pytest.raises(ValueError, match="default_timeout_s must be > 0"):
            DavinciAdapter(default_timeout_s=bad)

    def test_positive_timeout_accepted(self) -> None:
        """正数 timeout 正常接受。"""
        DavinciAdapter(default_timeout_s=1)
        DavinciAdapter(default_timeout_s=300)


def _make_ctx(project: Path, tool_home: Path) -> EcuConfigProjectContext:
    """最小 DaVinci ctx。"""
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


def _build_fake_davinci(home: Path) -> None:
    """在 home 下建 fake DVCfgCmd.exe。"""
    core = home / "Core"
    core.mkdir(parents=True, exist_ok=True)
    (core / "DVCfgCmd.exe").write_text("@echo off\n", encoding="utf-8")


class TestDvcfgPath:
    """_dvcfg_path 跨平台查找。"""

    def test_finds_exe_on_windows(self, tmp_path: Path) -> None:
        """Windows 上找 DVCfgCmd.exe。"""
        _build_fake_davinci(tmp_path)
        if __import__("os").name == "nt":
            result = DavinciAdapter()._dvcfg_path(_make_ctx(tmp_path, tmp_path))
            assert result == tmp_path / "Core" / "DVCfgCmd.exe"

    def test_finds_no_suffix_on_unix(self, tmp_path: Path) -> None:
        """非 Windows 上找 DVCfgCmd（无后缀）。"""
        core = tmp_path / "Core"
        core.mkdir()
        (core / "DVCfgCmd").write_text("#!/bin/sh\n", encoding="utf-8")
        if __import__("os").name != "nt":
            result = DavinciAdapter()._dvcfg_path(_make_ctx(tmp_path, tmp_path))
            assert result == tmp_path / "Core" / "DVCfgCmd"

    def test_missing_executable_raises(self, tmp_path: Path) -> None:
        """找不到 DVCfgCmd 抛 DavinciAdapterError。"""
        with pytest.raises(DavinciAdapterError, match="DVCfgCmd not found"):
            DavinciAdapter()._dvcfg_path(_make_ctx(tmp_path, tmp_path))


class TestDavinciSubprocess:
    """verify / save subprocess 包装（mock subprocess.run）。"""

    @patch("claude_autosar.adapters.davinci.subprocess.run")
    def test_verify_runs_autocverify(self, mock_run: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """verify() 调 ``AutocVerify``。"""
        _build_fake_davinci(tmp_path)
        ctx = _make_ctx(tmp_path, tmp_path)
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="OK", stderr=""
        )
        result = DavinciAdapter().verify(ctx, module="PduR")
        assert result.success is True
        assert "AutocVerify" in mock_run.call_args[0][0]
        assert "PduR" in mock_run.call_args[0][0]

    @patch("claude_autosar.adapters.davinci.subprocess.run")
    def test_save_runs_save(self, mock_run: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """save() 调 ``Save``。"""
        _build_fake_davinci(tmp_path)
        ctx = _make_ctx(tmp_path, tmp_path)
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        result = DavinciAdapter().save(ctx, module="EcuC")
        assert result.success is True
        assert "Save" in mock_run.call_args[0][0]
        assert "EcuC" in mock_run.call_args[0][0]

    @patch("claude_autosar.adapters.davinci.subprocess.run")
    def test_save_extracts_written_files_arxml(
        self, mock_run: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """save() 解析 stdout 中 ``Wrote: <path>`` 模式（DaVinci 写 .arxml）。"""
        _build_fake_davinci(tmp_path)
        ctx = _make_ctx(tmp_path, tmp_path)
        # DaVinci 写出的标准格式
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="Wrote: Config/ECUC/EcuC.arxml\nWrote: Config/ECUC/Com.arxml\n",
            stderr="",
        )
        result = DavinciAdapter().save(ctx)
        assert result.success is True
        assert len(result.written_files) == 2
        names = {p.name for p in result.written_files}
        assert "EcuC.arxml" in names
        assert "Com.arxml" in names

    @patch("claude_autosar.adapters.davinci.subprocess.run")
    def test_save_handles_no_written_files(
        self, mock_run: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """save() 输出无 Wrote 模式时，written_files 仍为默认空 tuple。"""
        _build_fake_davinci(tmp_path)
        ctx = _make_ctx(tmp_path, tmp_path)
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="Save complete.\n",
            stderr="",
        )
        result = DavinciAdapter().save(ctx)
        assert result.success is True
        assert result.written_files == ()

    @patch("claude_autosar.adapters.davinci.subprocess.run")
    def test_save_ignores_natural_language_wrote_saved(
        self, mock_run: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """save() 不误匹配 stdout 自然语言中的 "wrote/saved"。

        回归保护：旧正则 ``(wrote|saved)\\s+(\\S+)`` 会把
        "Configuration was not saved due to errors" 中的 "due" 解析为路径。
        新正则要求行首 + .arxml/.xdm 扩展名，避开这种误匹配。
        """
        _build_fake_davinci(tmp_path)
        ctx = _make_ctx(tmp_path, tmp_path)
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout=(
                "Validation started...\n"
                "Configuration was not saved due to validation errors.\n"
                "No file was written by DVCfgCmd.\n"
                "Wrote: Config/ECUC/EcuC.arxml\n"  # 唯一一个真正的文件
            ),
            stderr="",
        )
        result = DavinciAdapter().save(ctx)
        # 唯一被识别的真实写入文件
        assert len(result.written_files) == 1
        assert result.written_files[0].name == "EcuC.arxml"

    @patch("claude_autosar.adapters.davinci.subprocess.run")
    def test_verify_failure_captured(self, mock_run: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """失败时 success=False。"""
        _build_fake_davinci(tmp_path)
        ctx = _make_ctx(tmp_path, tmp_path)
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="verify fail"
        )
        result = DavinciAdapter().verify(ctx)
        assert result.success is False

    @patch("claude_autosar.adapters.davinci.subprocess.run")
    def test_timeout_raises(self, mock_run: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """subprocess 超时抛 DavinciAdapterError。"""
        _build_fake_davinci(tmp_path)
        ctx = _make_ctx(tmp_path, tmp_path)
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="DVCfgCmd", timeout=1.0)
        with pytest.raises(DavinciAdapterError, match="timed out"):
            DavinciAdapter(default_timeout_s=1).verify(ctx)

    @patch("claude_autosar.adapters.davinci.subprocess.run")
    def test_filenotfound_raises(self, mock_run: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """subprocess 不存在抛 DavinciAdapterError。"""
        _build_fake_davinci(tmp_path)
        ctx = _make_ctx(tmp_path, tmp_path)
        mock_run.side_effect = FileNotFoundError()
        with pytest.raises(DavinciAdapterError, match="FileNotFoundError"):
            DavinciAdapter().verify(ctx)

    @patch("claude_autosar.adapters.davinci.subprocess.run")
    def test_permissionerror_raises(self, mock_run: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """subprocess 抛 PermissionError 时包成 DavinciAdapterError。"""
        _build_fake_davinci(tmp_path)
        ctx = _make_ctx(tmp_path, tmp_path)
        mock_run.side_effect = PermissionError("Access is denied")
        with pytest.raises(DavinciAdapterError, match="PermissionError"):
            DavinciAdapter().verify(ctx)
