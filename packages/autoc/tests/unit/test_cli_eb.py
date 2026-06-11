"""Unit tests for packages/autoc/src/autoc/cli/commands/eb.py.

TDD 阶段：RED（先写测试）。Sprint 3 — T3.5。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from autoc.adapters.protocol import (
    CalcResult,
    EcuConfigProjectContext,
    SaveResult,
    VerifyResult,
)
from autoc.adapters.stub import StubTresosAdapter
from autoc.cli.commands.eb import build_parser, run

pytestmark = pytest.mark.autosar


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


_MCU_XML = """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES><AR-PACKAGE><SHORT-NAME>B</SHORT-NAME><ELEMENTS>
    <ECUC-MODULE-CONFIGURATION-VALUES>
      <SHORT-NAME>Mcu</SHORT-NAME>
      <CONTAINERS>
        <ECUC-PARAM-CONF-CONTAINER>
          <SHORT-NAME>Clock</SHORT-NAME>
          <PARAMETER-VALUES>
            <ECUC-NUMERICAL-PARAM-VALUE>
              <DEFINITION-REF DEST="ECUC-INTEGER-PARAM-DEF">/Mcu/Clock/ClockFreq</DEFINITION-REF>
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


# ---------------------------------------------------------------------------
# argparse
# ---------------------------------------------------------------------------


class TestArgparse:
    def test_save_subcommand(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["eb", "save", "--module", "Mcu", "--param", "ClockFreq=80000000"])
        assert args.command == "eb"
        assert args.eb_command == "save"
        assert args.module == "Mcu"
        assert args.param == ["ClockFreq=80000000"]

    def test_save_multiple_params(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "eb",
                "save",
                "--module",
                "Mcu",
                "--param",
                "McuClockSettingConfig_0/ClockFreq=80000000",
                "--param",
                "McuClockSettingConfig_0/ClockName=XTAL",
            ]
        )
        assert args.param == [
            "McuClockSettingConfig_0/ClockFreq=80000000",
            "McuClockSettingConfig_0/ClockName=XTAL",
        ]

    def test_verify_subcommand(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["eb", "verify", "--module", "Mcu"])
        assert args.eb_command == "verify"
        assert args.module == "Mcu"

    def test_autocalc_subcommand(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["eb", "autocalc", "--module", "Mcu"])
        assert args.eb_command == "autocalc"

    def test_adapter_choice(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["eb", "save", "--module", "Mcu", "--adapter", "stub"])
        assert args.adapter == "stub"

    def test_no_command_fails(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["eb"])


# ---------------------------------------------------------------------------
# run() — happy path / verify fail / autocalc
# ---------------------------------------------------------------------------


def _args_for_save(project: Path, *, adapter: str = "stub") -> argparse.Namespace:
    return argparse.Namespace(
        command="eb",
        eb_command="save",
        project=project,
        module="Mcu",
        tresos_home=None,
        param=["Mcu/Clock/ClockFreq=80000000"],
        adapter=adapter,
    )


def _args_for_verify(project: Path, *, adapter: str = "stub") -> argparse.Namespace:
    return argparse.Namespace(
        command="eb",
        eb_command="verify",
        project=project,
        module="Mcu",
        tresos_home=None,
        param=[],
        adapter=adapter,
    )


def _args_for_autocalc(project: Path, *, adapter: str = "stub") -> argparse.Namespace:
    return argparse.Namespace(
        command="eb",
        eb_command="autocalc",
        project=project,
        module="Mcu",
        tresos_home=None,
        param=[],
        adapter=adapter,
    )


def _stub_for(project: Path) -> StubTresosAdapter:
    ctx = _make_ctx(project)
    return StubTresosAdapter(
        discover_response=ctx,
        verify_responses=[VerifyResult(success=True, returncode=0, stdout="OK", stderr="")],
        save_responses=[
            SaveResult(success=True, returncode=0, stdout="", stderr="", written_files=())
        ],
        autocalc_response=CalcResult(success=True, returncode=0, stdout="OK", stderr=""),
    )


class TestRunSave:
    def test_save_happy_path_exit_0(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        project = _make_project(tmp_path)
        args = _args_for_save(project)
        adapter = _stub_for(project)
        exit_code = run(args, adapter_override=adapter)
        assert exit_code == 0
        captured = capsys.readouterr()
        assert '"success": true' in captured.out

    def test_save_verify_fail_exit_1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        project = _make_project(tmp_path)
        args = _args_for_save(project)
        ctx = _make_ctx(project)
        adapter = StubTresosAdapter(
            discover_response=ctx,
            verify_responses=[
                VerifyResult(success=False, returncode=1, stdout="", stderr="validation failed")
            ],
        )
        exit_code = run(args, adapter_override=adapter)
        assert exit_code == 1
        captured = capsys.readouterr()
        assert '"rolled_back": true' in captured.out


class TestRunVerify:
    def test_verify_runs_adapter(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        project = _make_project(tmp_path)
        args = _args_for_verify(project)
        adapter = _stub_for(project)
        exit_code = run(args, adapter_override=adapter)
        assert exit_code == 0
        assert len(adapter.verify_calls) == 1


class TestRunSaveSession:
    """Sprint 4 — eb save 成功路径必须写 session entry。"""

    def test_save_writes_session_entry_on_success(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """完整路径：eb save (stub) → modify_and_verify success → recorder 写 session。"""
        # 重定向 session 目录到 tmp
        cfg_dir = tmp_path / "fake_agent"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(
            "autoc.utils.paths.user_config_dir",
            lambda *a, **kw: str(cfg_dir),
        )

        project = _make_project(tmp_path)
        args = _args_for_save(project)
        adapter = _stub_for(project)
        exit_code = run(args, adapter_override=adapter)
        assert exit_code == 0

        captured = capsys.readouterr()
        # JSON 输出必须含 session_id
        import json

        payload = json.loads(captured.out)
        assert payload["success"] is True
        assert "session_id" in payload

        # session 文件应已写入
        from autoc.core.session.store import SessionStore

        store = SessionStore()
        session = store.read(payload["session_id"])
        # 1 user + 1 tool = 2 entries
        assert len(session.entries) == 2
        tool = session.entries[1]
        assert tool.tool_name == "bsw_write"
        assert tool.tool_args["module"] == "Mcu"
        assert tool.tool_args["path"] == "Clock/ClockFreq"
        assert tool.tool_args["value"] == "80000000"

    def test_save_failure_does_not_write_session(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """verify 失败 → modify_and_verify rolled_back → session 不写。"""
        cfg_dir = tmp_path / "fake_agent"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(
            "autoc.utils.paths.user_config_dir",
            lambda *a, **kw: str(cfg_dir),
        )

        project = _make_project(tmp_path)
        args = _args_for_save(project)
        ctx = _make_ctx(project)
        adapter = StubTresosAdapter(
            discover_response=ctx,
            verify_responses=[
                VerifyResult(success=False, returncode=1, stdout="", stderr="validation failed")
            ],
        )
        exit_code = run(args, adapter_override=adapter)
        assert exit_code == 1

        from autoc.core.session.store import SessionStore

        store = SessionStore()
        assert store.list_session_ids() == []


class TestRunAutocalc:
    def test_autocalc_runs_adapter(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        project = _make_project(tmp_path)
        args = _args_for_autocalc(project)
        adapter = _stub_for(project)
        exit_code = run(args, adapter_override=adapter)
        assert exit_code == 0
        assert len(adapter.autocalc_calls) == 1
