"""Unit tests for packages/autoc/src/autoc/cli/commands/davinci.py.

TDD 阶段：RED（先写测试）。Sprint 3 — T3.6。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from autoc.adapters.protocol import (
    EcuConfigProjectContext,
    SaveResult,
    VerifyResult,
)
from autoc.adapters.stub import StubDavinciAdapter
from autoc.cli.commands.davinci import build_parser, run

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
    tool_home = project.parent / "fake-davinci"
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
        args = parser.parse_args(
            ["davinci", "save", "--module", "Mcu", "--param", "Mcu/Clock/ClockFreq=80000000"]
        )
        assert args.command == "davinci"
        assert args.davinci_command == "save"
        assert args.module == "Mcu"

    def test_verify_subcommand(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["davinci", "verify", "--module", "Mcu"])
        assert args.davinci_command == "verify"

    def test_no_autocalc_subcommand(self) -> None:
        """Davinci 没有 autocalc 子命令（Protocol 不含 autocalc）。"""
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["davinci", "autocalc", "--module", "Mcu"])

    def test_davinci_home_arg(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            ["davinci", "verify", "--module", "Mcu", "--davinci-home", "/opt/dv"]
        )
        assert args.davinci_home == Path("/opt/dv")


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------


def _args_for_save(project: Path, *, adapter: str = "stub") -> argparse.Namespace:
    return argparse.Namespace(
        command="davinci",
        davinci_command="save",
        project=project,
        module="Mcu",
        davinci_home=None,
        param=["Mcu/Clock/ClockFreq=80000000"],
        adapter=adapter,
    )


def _args_for_verify(project: Path, *, adapter: str = "stub") -> argparse.Namespace:
    return argparse.Namespace(
        command="davinci",
        davinci_command="verify",
        project=project,
        module="Mcu",
        davinci_home=None,
        param=[],
        adapter=adapter,
    )


def _stub_for() -> StubDavinciAdapter:
    return StubDavinciAdapter(
        verify_responses=[VerifyResult(success=True, returncode=0, stdout="OK", stderr="")],
        save_responses=[
            SaveResult(success=True, returncode=0, stdout="", stderr="", written_files=())
        ],
    )


class TestRunSave:
    def test_save_happy_path_exit_0(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        project = _make_project(tmp_path)
        args = _args_for_save(project)
        adapter = _stub_for()
        exit_code = run(args, adapter_override=adapter)
        assert exit_code == 0
        captured = capsys.readouterr()
        assert '"success": true' in captured.out

    def test_save_verify_fail_exit_1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        project = _make_project(tmp_path)
        args = _args_for_save(project)
        adapter = StubDavinciAdapter(
            verify_responses=[
                VerifyResult(success=False, returncode=1, stdout="", stderr="dv fail")
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
        adapter = _stub_for()
        exit_code = run(args, adapter_override=adapter)
        assert exit_code == 0
        assert len(adapter.verify_calls) == 1
