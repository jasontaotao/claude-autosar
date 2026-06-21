"""Sprint 8.E.1 — coverage backfill for ``cli/commands/davinci.py``.

Plan reference: Sprint 8.E.1 Task A — rank 5 CLI command error path coverage.

Targets (see ``plan/steady-covering-phoenix.md`` §1):
  - ``cli/commands/davinci.py`` (47 missing → cover error paths):
    ``save`` / ``verify`` 错误路径, ``_parse_params`` 边界, ``StubDavinciAdapter``
    失败 mock, ``_maybe_typo_suggestion`` / ``_extract_err_path`` /
    ``_emit_did_you_mean`` helpers, ``_build_adapter`` 路径。

**禁 令**:
- 不改产品代码
- 不 git commit
- 不引入新 pip 依赖
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

from claude_autosar.adapters.protocol import (
    EcuConfigProjectContext,
    SaveResult,
    VerifyResult,
)
from claude_autosar.adapters.stub import StubDavinciAdapter
from claude_autosar.cli.commands import davinci

pytestmark = pytest.mark.autosar


# ---------------------------------------------------------------------------
# Helpers
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
# _parse_params helper
# ---------------------------------------------------------------------------


class TestParseParams:
    def test_relative_path_gets_module_prefix(self) -> None:
        out = davinci._parse_params(["Clock/ClockFreq=80000000"], "Mcu")
        assert len(out) == 1
        assert out[0].path == "Mcu/Clock/ClockFreq"
        assert out[0].value.raw == "80000000"

    def test_full_path_passes_through(self) -> None:
        out = davinci._parse_params(["Mcu/Clock/ClockFreq=999"], "Mcu")
        assert len(out) == 1
        assert out[0].path == "Mcu/Clock/ClockFreq"
        assert out[0].value.raw == "999"

    def test_param_without_equals_skipped_with_stderr(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        out = davinci._parse_params(["no_equals"], "Mcu")
        captured = capsys.readouterr()
        assert out == []
        assert "警告" in captured.err
        assert "no_equals" in captured.err

    def test_param_with_equals_in_value(self) -> None:
        out = davinci._parse_params(["Mcu/Key=a=b"], "Mcu")
        assert len(out) == 1
        assert out[0].value.raw == "a=b"

    def test_empty_list_returns_empty(self) -> None:
        assert davinci._parse_params([], "Mcu") == []

    def test_stripped_whitespace_in_path(self) -> None:
        out = davinci._parse_params(["  Mcu/Clock/F  =1  "], "Mcu")
        assert out[0].path == "Mcu/Clock/F"
        assert out[0].value.raw == "1"


# ---------------------------------------------------------------------------
# _build_adapter
# ---------------------------------------------------------------------------


class TestBuildAdapter:
    def test_stub_chosen_when_args_adapter_stub(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        args = argparse.Namespace(
            project=project,
            module="Mcu",
            davinci_home=None,
            adapter="stub",
        )
        adapter = davinci._build_adapter(args)
        assert isinstance(adapter, StubDavinciAdapter)

    def test_real_chosen_when_args_adapter_real(self) -> None:
        from claude_autosar.adapters.davinci import DavinciAdapter

        args = argparse.Namespace(
            project=Path("/nonexistent"),
            module="Mcu",
            davinci_home=None,
            adapter="real",
        )
        adapter = davinci._build_adapter(args)
        assert isinstance(adapter, DavinciAdapter)


# ---------------------------------------------------------------------------
# run() — discover ctx setup / unknown subcommand
# ---------------------------------------------------------------------------


class TestRunUnknownSubcommand:
    def test_unknown_davinci_command_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        project = _make_project(tmp_path)
        args = argparse.Namespace(
            command="davinci",
            davinci_command="autocalc",  # davinci 没有 autocalc
            project=project,
            module="Mcu",
            davinci_home=None,
            param=[],
            adapter="stub",
        )
        adapter = StubDavinciAdapter()
        code = davinci.run(args, adapter_override=adapter)
        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.err.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "unknown subcommand" in payload["error"]


# ---------------------------------------------------------------------------
# run() — verify / save failure paths
# ---------------------------------------------------------------------------


class TestRunVerifyFailure:
    def test_verify_failure_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        project = _make_project(tmp_path)
        adapter = StubDavinciAdapter(
            verify_responses=[
                VerifyResult(success=False, returncode=2, stdout="", stderr="dv validate failed")
            ],
        )
        args = argparse.Namespace(
            command="davinci",
            davinci_command="verify",
            project=project,
            module="Mcu",
            davinci_home=None,
            param=[],
            adapter="stub",
        )
        code = davinci.run(args, adapter_override=adapter)
        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.out.strip().splitlines()[-1])
        assert payload["success"] is False
        assert payload["returncode"] == 2
        assert payload["stderr"] == "dv validate failed"


class TestRunSaveFailures:
    def test_save_raises_valueerror_with_typo_suggestion(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """modify_and_verify 抛 ValueError 含 path → exit 1 + 候选 + Did you mean。"""
        from claude_autosar.core.bsw.validator import ValidatorError

        project = _make_project(tmp_path)

        class _OkAdapter:
            def verify(self, *a: Any, **kw: Any) -> Any:
                return VerifyResult(success=True, returncode=0, stdout="", stderr="")

            def save(self, *a: Any, **kw: Any) -> Any:
                return SaveResult(success=True, returncode=0, stdout="", stderr="", written_files=())

        # typo path
        args = argparse.Namespace(
            command="davinci",
            davinci_command="save",
            project=project,
            module="Mcu",
            davinci_home=None,
            param=["Mcu/Clock/ClockFrq=80000000"],
            adapter="stub",
        )

        from claude_autosar.cli.commands import davinci as dav_mod

        def _raise_modify_verify(
            _ctx: Any, _adapter: Any, _req: Any
        ) -> Any:
            raise ValidatorError("Path 'Mcu/Clock/ClockFrq' not in ECUCDocument for module 'Mcu'")

        orig = dav_mod.modify_and_verify
        dav_mod.modify_and_verify = _raise_modify_verify
        try:
            code = davinci.run(args, adapter_override=_OkAdapter())
        finally:
            dav_mod.modify_and_verify = orig

        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.err.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "ClockFrq" in payload["error"]
        assert "suggestions" in payload
        assert "Mcu/Clock/ClockFreq" in payload["suggestions"]
        assert "Did you mean:" in captured.err

    def test_save_raises_valueerror_no_suggestion_when_module_file_missing(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        project = _make_project(tmp_path)
        (project / "Mcu.xdm").unlink()

        class _OkAdapter:
            def verify(self, *a: Any, **kw: Any) -> Any:
                return VerifyResult(success=True, returncode=0, stdout="", stderr="")

            def save(self, *a: Any, **kw: Any) -> Any:
                return SaveResult(success=True, returncode=0, stdout="", stderr="", written_files=())

        args = argparse.Namespace(
            command="davinci",
            davinci_command="save",
            project=project,
            module="Mcu",
            davinci_home=None,
            param=["Mcu/Clock/ClockFrq=80000000"],
            adapter="stub",
        )

        from claude_autosar.cli.commands import davinci as dav_mod
        from claude_autosar.core.bsw.validator import ValidatorError

        def _raise_modify_verify(
            _ctx: Any, _adapter: Any, _req: Any
        ) -> Any:
            raise ValidatorError("Path 'Mcu/Clock/ClockFrq' not in tree")

        orig = dav_mod.modify_and_verify
        dav_mod.modify_and_verify = _raise_modify_verify
        try:
            code = davinci.run(args, adapter_override=_OkAdapter())
        finally:
            dav_mod.modify_and_verify = orig

        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.err.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "suggestions" not in payload
        assert "Did you mean:" not in captured.err

    def test_save_raises_valueerror_with_no_err_path(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        project = _make_project(tmp_path)

        class _OkAdapter:
            def verify(self, *a: Any, **kw: Any) -> Any:
                return VerifyResult(success=True, returncode=0, stdout="", stderr="")

            def save(self, *a: Any, **kw: Any) -> Any:
                return SaveResult(success=True, returncode=0, stdout="", stderr="", written_files=())

        args = argparse.Namespace(
            command="davinci",
            davinci_command="save",
            project=project,
            module="Mcu",
            davinci_home=None,
            param=["Mcu/Clock/ClockFreq=80000000"],
            adapter="stub",
        )

        from claude_autosar.cli.commands import davinci as dav_mod
        from claude_autosar.core.bsw.validator import ValidatorError

        def _raise_modify_verify(
            _ctx: Any, _adapter: Any, _req: Any
        ) -> Any:
            raise ValidatorError("totally generic error: no path")

        orig = dav_mod.modify_and_verify
        dav_mod.modify_and_verify = _raise_modify_verify
        try:
            code = davinci.run(args, adapter_override=_OkAdapter())
        finally:
            dav_mod.modify_and_verify = orig

        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.err.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "suggestions" not in payload
        assert "Did you mean:" not in captured.err

    def test_save_session_record_failure_continues(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """save 成功但 session 记录失败 → 仍 exit 0 + payload 含 session_record_error。"""
        project = _make_project(tmp_path)
        adapter = StubDavinciAdapter(
            verify_responses=[VerifyResult(success=True, returncode=0, stdout="", stderr="")],
            save_responses=[
                SaveResult(
                    success=True,
                    returncode=0,
                    stdout="",
                    stderr="",
                    written_files=(project / "Mcu.xdm",),
                )
            ],
        )
        args = argparse.Namespace(
            command="davinci",
            davinci_command="save",
            project=project,
            module="Mcu",
            davinci_home=None,
            param=["Mcu/Clock/ClockFreq=80000000"],
            adapter="stub",
        )

        # patch recorder module's function (used by _run_save's lazy import)
        from claude_autosar.core.session import recorder as recorder_mod

        def _raise_record(*_a: Any, **_kw: Any) -> Any:
            raise OSError("disk full for session")

        monkeypatch.setattr(recorder_mod, "record_bsw_write_batch", _raise_record)

        code = davinci.run(args, adapter_override=adapter)
        captured = capsys.readouterr()
        assert code == 0
        payload = json.loads(captured.out.strip().splitlines()[-1])
        assert payload["success"] is True
        assert "session_record_error" in payload

    def test_save_success_with_session(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """save 成功 + session 成功 → 完整 happy path。"""
        cfg_dir = tmp_path / "agent_cfg"
        cfg_dir.mkdir()
        monkeypatch.setattr(
            "claude_autosar.utils.paths.user_config_dir",
            lambda *a, **kw: str(cfg_dir),
        )

        project = _make_project(tmp_path)
        adapter = StubDavinciAdapter(
            verify_responses=[VerifyResult(success=True, returncode=0, stdout="", stderr="")],
            save_responses=[
                SaveResult(
                    success=True,
                    returncode=0,
                    stdout="",
                    stderr="",
                    written_files=(project / "Mcu.xdm",),
                )
            ],
        )
        args = argparse.Namespace(
            command="davinci",
            davinci_command="save",
            project=project,
            module="Mcu",
            davinci_home=None,
            param=["Mcu/Clock/ClockFreq=80000000"],
            adapter="stub",
        )
        code = davinci.run(args, adapter_override=adapter)
        captured = capsys.readouterr()
        assert code == 0
        payload = json.loads(captured.out.strip().splitlines()[-1])
        assert payload["success"] is True
        assert "session_id" in payload

    def test_save_with_no_params_skips_session(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        project = _make_project(tmp_path)
        adapter = StubDavinciAdapter(
            verify_responses=[VerifyResult(success=True, returncode=0, stdout="", stderr="")],
            save_responses=[
                SaveResult(success=True, returncode=0, stdout="", stderr="", written_files=())
            ],
        )
        args = argparse.Namespace(
            command="davinci",
            davinci_command="save",
            project=project,
            module="Mcu",
            davinci_home=None,
            param=[],
            adapter="stub",
        )
        code = davinci.run(args, adapter_override=adapter)
        captured = capsys.readouterr()
        assert code == 0
        payload = json.loads(captured.out.strip().splitlines()[-1])
        assert payload["success"] is True
        assert "session_id" not in payload


# ---------------------------------------------------------------------------
# _extract_err_path / _emit_did_you_mean / _maybe_typo_suggestion
# ---------------------------------------------------------------------------


class TestExtractErrPath:
    def test_extracts_single_quoted_path(self) -> None:
        assert davinci._extract_err_path("Path 'Mcu/Foo' not in tree") == "Mcu/Foo"

    def test_extracts_lowercase_path(self) -> None:
        assert davinci._extract_err_path("path 'Mcu/Bar' not found") == "Mcu/Bar"

    def test_extracts_double_quoted(self) -> None:
        assert davinci._extract_err_path('"Mcu/Baz" not in document') == "Mcu/Baz"

    def test_returns_none_when_no_pattern(self) -> None:
        assert davinci._extract_err_path("totally generic error") is None

    def test_returns_none_for_empty_string(self) -> None:
        assert davinci._extract_err_path("") is None


class TestEmitDidYouMean:
    def test_empty_suggestions_noop(self, capsys: pytest.CaptureFixture[str]) -> None:
        davinci._emit_did_you_mean(())
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_single_suggestion(self, capsys: pytest.CaptureFixture[str]) -> None:
        davinci._emit_did_you_mean(("Mcu/Clock/ClockFreq",))
        captured = capsys.readouterr()
        assert "Did you mean: Mcu/Clock/ClockFreq?" in captured.err

    def test_multiple_suggestions_joined(self, capsys: pytest.CaptureFixture[str]) -> None:
        davinci._emit_did_you_mean(("A", "B", "C"))
        captured = capsys.readouterr()
        assert "Did you mean: A, B, C?" in captured.err


class TestMaybeTypoSuggestion:
    def test_module_file_missing_returns_empty(
        self, tmp_path: Path
    ) -> None:
        ctx = _make_ctx(tmp_path)
        (tmp_path / "bsw-project" / "Mcu.xdm").unlink(missing_ok=True)
        ex = ValueError("Path 'X' not in tree")
        assert davinci._maybe_typo_suggestion(ex, ctx, "Mcu") == ()

    def test_load_module_raises_returns_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ctx = _make_ctx(tmp_path)
        from claude_autosar.core.bsw import ecuc as ecuc_mod

        def _raise_load(_p: Any, _m: str) -> Any:
            raise RuntimeError("parse failed")

        monkeypatch.setattr(ecuc_mod, "load_module", _raise_load)
        ex = ValueError("Path 'Mcu/Clock/ClockFrq' not in tree")
        assert davinci._maybe_typo_suggestion(ex, ctx, "Mcu") == ()

    def test_returns_empty_when_err_path_is_none(
        self, tmp_path: Path
    ) -> None:
        project = _make_project(tmp_path)
        ctx = _make_ctx(project)
        ex = ValueError("generic error no path")
        assert davinci._maybe_typo_suggestion(ex, ctx, "Mcu") == ()

    def test_returns_suggestions_on_typo(
        self, tmp_path: Path
    ) -> None:
        project = _make_project(tmp_path)
        ctx = _make_ctx(project)
        ex = ValueError("Path 'Mcu/Clock/ClockFrq' not in tree")
        sugg = davinci._maybe_typo_suggestion(ex, ctx, "Mcu")
        assert len(sugg) >= 1
        assert "Mcu/Clock/ClockFreq" in sugg


# ---------------------------------------------------------------------------
# argparse — defaults
# ---------------------------------------------------------------------------


class TestArgparseDefaults:
    def test_default_adapter_is_real(self) -> None:
        parser = davinci.build_parser()
        args = parser.parse_args(["davinci", "save", "--module", "Mcu"])
        assert args.adapter == "real"

    def test_default_davinci_home_is_none(self) -> None:
        parser = davinci.build_parser()
        args = parser.parse_args(["davinci", "save", "--module", "Mcu"])
        assert args.davinci_home is None
