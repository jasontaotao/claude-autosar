"""Sprint 8.E.1 — coverage backfill for ``cli/commands/eb.py``.

Plan reference: Sprint 8.E.1 Task A — rank 4 CLI command error path coverage.

Targets (see ``plan/steady-covering-phoenix.md`` §1):
  - ``cli/commands/eb.py`` (48 missing → cover error paths):
    ``save`` / ``verify`` / ``autocalc`` error paths,
    ``_parse_params`` boundaries, ``StubTresosAdapter`` 失败 mock,
    ``_maybe_typo_suggestion`` / ``_extract_err_path`` / ``_emit_did_you_mean``
    helpers, ``_build_adapter`` / ``_fake_ctx_for_stub`` paths.

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
    CalcResult,
    EcuConfigProjectContext,
    SaveResult,
    VerifyResult,
)
from claude_autosar.adapters.stub import StubTresosAdapter
from claude_autosar.cli.commands import eb
from claude_autosar.core.bsw.config import ParamType

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
# _parse_params helper
# ---------------------------------------------------------------------------


class TestParseParams:
    def test_relative_path_gets_module_prefix(self) -> None:
        out = eb._parse_params(["Clock/ClockFreq=80000000"], "Mcu")
        assert len(out) == 1
        assert out[0].path == "Mcu/Clock/ClockFreq"
        assert out[0].value.raw == "80000000"

    def test_full_path_passes_through(self) -> None:
        out = eb._parse_params(["Mcu/Clock/ClockFreq=999"], "Mcu")
        assert len(out) == 1
        assert out[0].path == "Mcu/Clock/ClockFreq"
        assert out[0].value.raw == "999"

    def test_param_without_equals_skipped_with_stderr(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """``key=value`` 缺 '=' → 跳过 + stderr 警告。"""
        out = eb._parse_params(["no_equals"], "Mcu")
        captured = capsys.readouterr()
        assert out == []
        assert "警告" in captured.err
        assert "no_equals" in captured.err

    def test_param_with_equals_in_value(self) -> None:
        """value 里含 '=' → split 只切第一个。"""
        out = eb._parse_params(["Mcu/Key=a=b"], "Mcu")
        assert len(out) == 1
        assert out[0].value.raw == "a=b"

    def test_empty_list_returns_empty(self) -> None:
        assert eb._parse_params([], "Mcu") == []

    def test_stripped_whitespace_in_path(self) -> None:
        out = eb._parse_params(["  Mcu/Clock/F  =1  "], "Mcu")
        assert out[0].path == "Mcu/Clock/F"
        assert out[0].value.raw == "1"


# ---------------------------------------------------------------------------
# _infer_param_type — 类型推断辅助函数
# ---------------------------------------------------------------------------


class TestInferParamType:
    """``_infer_param_type`` 必须按值内容推断 ParamType，不再硬编码 INTEGER。"""

    def test_integer_value(self) -> None:
        assert eb._infer_param_type("100") is ParamType.INTEGER

    def test_integer_zero(self) -> None:
        assert eb._infer_param_type("0") is ParamType.INTEGER

    def test_integer_negative(self) -> None:
        assert eb._infer_param_type("-5") is ParamType.INTEGER

    def test_float_value(self) -> None:
        assert eb._infer_param_type("3.14") is ParamType.FLOAT

    def test_float_scientific_notation(self) -> None:
        assert eb._infer_param_type("1e10") is ParamType.FLOAT

    def test_float_negative(self) -> None:
        assert eb._infer_param_type("-0.5") is ParamType.FLOAT

    def test_boolean_true(self) -> None:
        assert eb._infer_param_type("true") is ParamType.BOOLEAN

    def test_boolean_false(self) -> None:
        assert eb._infer_param_type("false") is ParamType.BOOLEAN

    def test_boolean_case_insensitive(self) -> None:
        assert eb._infer_param_type("True") is ParamType.BOOLEAN
        assert eb._infer_param_type("FALSE") is ParamType.BOOLEAN

    def test_string_value(self) -> None:
        assert eb._infer_param_type("HSI") is ParamType.STRING

    def test_string_mixed_alphanumeric(self) -> None:
        assert eb._infer_param_type("XTAL123") is ParamType.STRING

    def test_string_empty(self) -> None:
        """空字符串不是数字也不是布尔 → STRING。"""
        assert eb._infer_param_type("") is ParamType.STRING

    def test_one_point_zero_is_float(self) -> None:
        """'1.0' 含小数点 → float，不是 int。"""
        assert eb._infer_param_type("1.0") is ParamType.FLOAT


class TestParseParamsTypeInference:
    """``_parse_params`` 必须根据值内容推断类型（不再是硬编码 INTEGER）。"""

    def test_integer_param(self) -> None:
        out = eb._parse_params(["Mcu/Clock/Freq=100"], "Mcu")
        assert out[0].value.type is ParamType.INTEGER

    def test_float_param(self) -> None:
        out = eb._parse_params(["Mcu/Clock/Ratio=3.14"], "Mcu")
        assert out[0].value.type is ParamType.FLOAT

    def test_boolean_param(self) -> None:
        out = eb._parse_params(["Mcu/Clock/Enabled=true"], "Mcu")
        assert out[0].value.type is ParamType.BOOLEAN

    def test_string_param(self) -> None:
        out = eb._parse_params(["Mcu/Clock/ClockName=HSI"], "Mcu")
        assert out[0].value.type is ParamType.STRING

    def test_negative_integer(self) -> None:
        out = eb._parse_params(["Mcu/Clock/Offset=-5"], "Mcu")
        assert out[0].value.type is ParamType.INTEGER

    def test_scientific_notation_is_float(self) -> None:
        out = eb._parse_params(["Mcu/Clock/Freq=1e10"], "Mcu")
        assert out[0].value.type is ParamType.FLOAT

    def test_zero_is_integer(self) -> None:
        out = eb._parse_params(["Mcu/Clock/Val=0"], "Mcu")
        assert out[0].value.type is ParamType.INTEGER


# ---------------------------------------------------------------------------
# _build_adapter / _fake_ctx_for_stub
# ---------------------------------------------------------------------------


class TestBuildAdapter:
    def test_stub_chosen_when_args_adapter_stub(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        args = argparse.Namespace(
            project=project,
            module="Mcu",
            tresos_home=None,
            adapter="stub",
        )
        adapter = eb._build_adapter(args)
        assert isinstance(adapter, StubTresosAdapter)

    def test_real_chosen_when_args_adapter_real(self) -> None:
        from claude_autosar.adapters.tresos import TresosAdapter

        args = argparse.Namespace(
            project=Path("/tmp/proj"),
            module="Mcu",
            tresos_home=None,
            adapter="real",
        )
        adapter = eb._build_adapter(args)
        assert isinstance(adapter, TresosAdapter)


class TestFakeCtxForStub:
    def test_uses_args_tresos_home_if_given(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        home = tmp_path / "my_tresos"
        args = argparse.Namespace(
            project=project,
            module="Mcu",
            tresos_home=home,
        )
        ctx = eb._fake_ctx_for_stub(args)
        assert ctx.tool_home == home
        assert ctx.project_path == project
        assert ctx.enabled_modules == ("Mcu",)
        assert home.exists()  # 自动 mkdir

    def test_uses_project_under_tresos_dir_when_no_home(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        args = argparse.Namespace(
            project=project,
            module="Can",
            tresos_home=None,
        )
        ctx = eb._fake_ctx_for_stub(args)
        # project/fake-tresos 应当被自动创建
        assert ctx.tool_home == project / "fake-tresos"
        assert (project / "fake-tresos").exists()
        assert ctx.enabled_modules == ("Can",)


# ---------------------------------------------------------------------------
# run() — discover failure / unknown subcommand
# ---------------------------------------------------------------------------


class TestRunDiscoverFailure:
    def test_discover_exception_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """adapter.discover 抛异常 → exit 1 + stdout JSON error。"""

        class _RaisingAdapter:
            def discover(self, *a: Any, **kw: Any) -> Any:
                raise RuntimeError("subprocess exploded")

        project = _make_project(tmp_path)
        args = argparse.Namespace(
            command="eb",
            eb_command="save",
            project=project,
            module="Mcu",
            tresos_home=None,
            param=["Mcu/Clock/ClockFreq=80000000"],
            adapter="stub",
        )
        code = eb.run(args, adapter_override=_RaisingAdapter())
        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.out.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "discover failed" in payload["error"]


class TestRunUnknownSubcommand:
    def test_unknown_eb_command_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        args = argparse.Namespace(
            command="eb",
            eb_command="totally_made_up",
            project=tmp_path,
            module="Mcu",
            tresos_home=None,
            param=[],
            adapter="stub",
        )
        ctx = _make_ctx(tmp_path)
        adapter = StubTresosAdapter(discover_response=ctx)
        code = eb.run(args, adapter_override=adapter)
        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.out.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "unknown subcommand" in payload["error"]


# ---------------------------------------------------------------------------
# run() — verify / autocalc failure paths
# ---------------------------------------------------------------------------


class TestRunVerifyAutocalcFailures:
    def test_verify_failure_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        project = _make_project(tmp_path)
        ctx = _make_ctx(project)
        adapter = StubTresosAdapter(
            discover_response=ctx,
            verify_responses=[
                VerifyResult(success=False, returncode=2, stdout="", stderr="validate failed")
            ],
        )
        args = argparse.Namespace(
            command="eb",
            eb_command="verify",
            project=project,
            module="Mcu",
            tresos_home=None,
            param=[],
            adapter="stub",
        )
        code = eb.run(args, adapter_override=adapter)
        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.out.strip().splitlines()[-1])
        assert payload["success"] is False
        assert payload["returncode"] == 2
        assert payload["stderr"] == "validate failed"

    def test_autocalc_failure_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        project = _make_project(tmp_path)
        ctx = _make_ctx(project)
        adapter = StubTresosAdapter(
            discover_response=ctx,
            autocalc_response=CalcResult(
                success=False, returncode=3, stdout="", stderr="calc failed"
            ),
        )
        args = argparse.Namespace(
            command="eb",
            eb_command="autocalc",
            project=project,
            module="Mcu",
            tresos_home=None,
            param=[],
            adapter="stub",
        )
        code = eb.run(args, adapter_override=adapter)
        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.out.strip().splitlines()[-1])
        assert payload["success"] is False
        assert payload["returncode"] == 3
        assert payload["stderr"] == "calc failed"
        assert payload["module"] == "Mcu"


# ---------------------------------------------------------------------------
# run() — save error paths (modify_and_verify 失败)
# ---------------------------------------------------------------------------


class TestRunSaveFailures:
    def test_save_raises_valueerror_with_typo_suggestion(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """modify_and_verify 抛 ValueError 含 path → exit 1 + 候选 + Did you mean。"""
        from claude_autosar.core.bsw.validator import ValidatorError

        project = _make_project(tmp_path)
        ctx = _make_ctx(project)

        class _RaisingAdapter:
            def discover(self, *a: Any, **kw: Any) -> Any:
                return ctx

            def verify(self, *a: Any, **kw: Any) -> Any:
                return VerifyResult(success=True, returncode=0, stdout="", stderr="")

            def save(self, *a: Any, **kw: Any) -> Any:
                return SaveResult(success=True, returncode=0, stdout="", stderr="", written_files=())

            def autocalc(self, *a: Any, **kw: Any) -> Any:
                return CalcResult(success=True, returncode=0, stdout="", stderr="")

        # 触发 ValueError，path 写成 "Mcu/Clock/ClockFrq"（typo），doc 里是 ClockFreq
        args = argparse.Namespace(
            command="eb",
            eb_command="save",
            project=project,
            module="Mcu",
            tresos_home=None,
            param=["Mcu/Clock/ClockFrq=80000000"],  # typo
            adapter="stub",
        )

        # patch modify_and_verify 直接抛 ValueError
        from claude_autosar.cli.commands import eb as eb_mod

        def _raise_modify_verify(
            _ctx: Any, _adapter: Any, _req: Any
        ) -> Any:
            raise ValidatorError("Path 'Mcu/Clock/ClockFrq' not in ECUCDocument for module 'Mcu'")

        orig = eb_mod.modify_and_verify
        eb_mod.modify_and_verify = _raise_modify_verify
        try:
            code = eb.run(args, adapter_override=_RaisingAdapter())
        finally:
            eb_mod.modify_and_verify = orig

        captured = capsys.readouterr()
        assert code == 1
        # stdout JSON
        payload = json.loads(captured.out.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "ClockFrq" in payload["error"]
        # 候选应被添加（ClockFreq 是真名）
        assert "suggestions" in payload
        assert "Mcu/Clock/ClockFreq" in payload["suggestions"]
        # stderr 含 "Did you mean:"
        assert "Did you mean:" in captured.err

    def test_save_raises_valueerror_no_suggestion_when_module_file_missing(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """module file 不存在 → 候选空（target_file is None 分支）。"""
        project = _make_project(tmp_path)
        # 删掉 Mcu.xdm 制造 target_file=None
        (project / "Mcu.xdm").unlink()
        ctx = _make_ctx(project)

        class _OkAdapter:
            def discover(self, *a: Any, **kw: Any) -> Any:
                return ctx

            def verify(self, *a: Any, **kw: Any) -> Any:
                return VerifyResult(success=True, returncode=0, stdout="", stderr="")

            def save(self, *a: Any, **kw: Any) -> Any:
                return SaveResult(success=True, returncode=0, stdout="", stderr="", written_files=())

            def autocalc(self, *a: Any, **kw: Any) -> Any:
                return CalcResult(success=True, returncode=0, stdout="", stderr="")

        args = argparse.Namespace(
            command="eb",
            eb_command="save",
            project=project,
            module="Mcu",
            tresos_home=None,
            param=["Mcu/Clock/ClockFrq=80000000"],
            adapter="stub",
        )

        from claude_autosar.cli.commands import eb as eb_mod
        from claude_autosar.core.bsw.validator import ValidatorError

        def _raise_modify_verify(
            _ctx: Any, _adapter: Any, _req: Any
        ) -> Any:
            raise ValidatorError("Path 'Mcu/Clock/ClockFrq' not in tree")

        orig = eb_mod.modify_and_verify
        eb_mod.modify_and_verify = _raise_modify_verify
        try:
            code = eb.run(args, adapter_override=_OkAdapter())
        finally:
            eb_mod.modify_and_verify = orig

        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.out.strip().splitlines()[-1])
        assert payload["success"] is False
        # target_file=None → suggestions 空
        assert "suggestions" not in payload
        # Did you mean 不应被 stderr 写出
        assert "Did you mean:" not in captured.err

    def test_save_raises_valueerror_with_no_err_path(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """异常 msg 不含 path 模式 → suggestions 空（_extract_err_path 返 None）。"""
        project = _make_project(tmp_path)
        ctx = _make_ctx(project)

        class _OkAdapter:
            def discover(self, *a: Any, **kw: Any) -> Any:
                return ctx

            def verify(self, *a: Any, **kw: Any) -> Any:
                return VerifyResult(success=True, returncode=0, stdout="", stderr="")

            def save(self, *a: Any, **kw: Any) -> Any:
                return SaveResult(success=True, returncode=0, stdout="", stderr="", written_files=())

            def autocalc(self, *a: Any, **kw: Any) -> Any:
                return CalcResult(success=True, returncode=0, stdout="", stderr="")

        args = argparse.Namespace(
            command="eb",
            eb_command="save",
            project=project,
            module="Mcu",
            tresos_home=None,
            param=["Mcu/Clock/ClockFreq=80000000"],
            adapter="stub",
        )

        from claude_autosar.cli.commands import eb as eb_mod
        from claude_autosar.core.bsw.validator import ValidatorError

        def _raise_modify_verify(
            _ctx: Any, _adapter: Any, _req: Any
        ) -> Any:
            # msg 不含 'path' / 'Path' / '"..." not in'
            raise ValidatorError("totally generic error: no path here")

        orig = eb_mod.modify_and_verify
        eb_mod.modify_and_verify = _raise_modify_verify
        try:
            code = eb.run(args, adapter_override=_OkAdapter())
        finally:
            eb_mod.modify_and_verify = orig

        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.out.strip().splitlines()[-1])
        assert payload["success"] is False
        # 候选空
        assert "suggestions" not in payload
        # Did you mean 不写出
        assert "Did you mean:" not in captured.err

    def test_save_session_record_failure_continues(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """save 成功但 session 记录失败 → 仍 exit 0 + payload 含 session_record_error。

        ``record_bsw_write_batch`` 在 eb._run_save 内部延迟 import；要 patch
        模块 ``claude_autosar.core.session.recorder`` 里的函数。
        """
        project = _make_project(tmp_path)
        ctx = _make_ctx(project)
        adapter = StubTresosAdapter(
            discover_response=ctx,
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
            command="eb",
            eb_command="save",
            project=project,
            module="Mcu",
            tresos_home=None,
            param=["Mcu/Clock/ClockFreq=80000000"],
            adapter="stub",
        )

        # patch the recorder module's function (used by _run_save's lazy import)
        from claude_autosar.core.session import recorder as recorder_mod

        def _raise_record(*_a: Any, **_kw: Any) -> Any:
            raise OSError("disk full for session")

        monkeypatch.setattr(recorder_mod, "record_bsw_write_batch", _raise_record)

        code = eb.run(args, adapter_override=adapter)
        captured = capsys.readouterr()
        # save 仍然成功（session 失败 best-effort，不阻塞）
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
        """save 成功 + session 也成功 → 完整 happy path 覆盖 L182。"""
        # 重定向 user config
        cfg_dir = tmp_path / "agent_cfg"
        cfg_dir.mkdir()
        monkeypatch.setattr(
            "claude_autosar.utils.paths.user_config_dir",
            lambda *a, **kw: str(cfg_dir),
        )

        project = _make_project(tmp_path)
        ctx = _make_ctx(project)
        adapter = StubTresosAdapter(
            discover_response=ctx,
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
            command="eb",
            eb_command="save",
            project=project,
            module="Mcu",
            tresos_home=None,
            param=["Mcu/Clock/ClockFreq=80000000"],
            adapter="stub",
        )
        code = eb.run(args, adapter_override=adapter)
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
        """save 成功 + params=[] → session 不写（参数是空时不写 session 记录）。"""
        project = _make_project(tmp_path)
        ctx = _make_ctx(project)
        adapter = StubTresosAdapter(
            discover_response=ctx,
            verify_responses=[VerifyResult(success=True, returncode=0, stdout="", stderr="")],
            save_responses=[
                SaveResult(
                    success=True,
                    returncode=0,
                    stdout="",
                    stderr="",
                    written_files=(),
                )
            ],
        )
        args = argparse.Namespace(
            command="eb",
            eb_command="save",
            project=project,
            module="Mcu",
            tresos_home=None,
            param=[],
            adapter="stub",
        )
        code = eb.run(args, adapter_override=adapter)
        captured = capsys.readouterr()
        assert code == 0
        payload = json.loads(captured.out.strip().splitlines()[-1])
        assert payload["success"] is True
        assert "session_id" not in payload


# ---------------------------------------------------------------------------
# _extract_err_path / _emit_did_you_mean helpers
# ---------------------------------------------------------------------------


class TestExtractErrPath:
    def test_extracts_single_quoted_path(self) -> None:
        assert eb._extract_err_path("Path 'Mcu/Foo' not in tree") == "Mcu/Foo"

    def test_extracts_lowercase_path(self) -> None:
        assert eb._extract_err_path("path 'Mcu/Bar' not found") == "Mcu/Bar"

    def test_extracts_double_quoted(self) -> None:
        assert eb._extract_err_path('"Mcu/Baz" not in document') == "Mcu/Baz"

    def test_returns_none_when_no_pattern(self) -> None:
        assert eb._extract_err_path("totally generic error") is None

    def test_returns_none_for_empty_string(self) -> None:
        assert eb._extract_err_path("") is None


class TestEmitDidYouMean:
    def test_empty_suggestions_noop(self, capsys: pytest.CaptureFixture[str]) -> None:
        eb._emit_did_you_mean(())
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_single_suggestion(self, capsys: pytest.CaptureFixture[str]) -> None:
        eb._emit_did_you_mean(("Mcu/Clock/ClockFreq",))
        captured = capsys.readouterr()
        assert "Did you mean: Mcu/Clock/ClockFreq?" in captured.err

    def test_multiple_suggestions_joined(self, capsys: pytest.CaptureFixture[str]) -> None:
        eb._emit_did_you_mean(("A", "B", "C"))
        captured = capsys.readouterr()
        assert "Did you mean: A, B, C?" in captured.err


# ---------------------------------------------------------------------------
# _maybe_typo_suggestion helper
# ---------------------------------------------------------------------------


class TestMaybeTypoSuggestion:
    def test_module_file_missing_returns_empty(
        self, tmp_path: Path
    ) -> None:
        ctx = _make_ctx(tmp_path)
        # 删 Mcu.xdm
        (tmp_path / "bsw-project" / "Mcu.xdm").unlink(missing_ok=True)
        ex = ValueError("Path 'X' not in tree")
        assert eb._maybe_typo_suggestion(ex, ctx, "Mcu") == ()

    def test_load_module_raises_returns_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """load_module 抛异常 → 返 () (line 258-259)。"""
        ctx = _make_ctx(tmp_path)
        from claude_autosar.core.bsw import ecuc as ecuc_mod

        def _raise_load(_p: Any, _m: str) -> Any:
            raise RuntimeError("parse failed")

        monkeypatch.setattr(ecuc_mod, "load_module", _raise_load)
        ex = ValueError("Path 'Mcu/Clock/ClockFrq' not in tree")
        assert eb._maybe_typo_suggestion(ex, ctx, "Mcu") == ()

    def test_returns_empty_when_err_path_is_none(
        self, tmp_path: Path
    ) -> None:
        """msg 里无 path 模式 → err_path=None → 返 ()。"""
        project = _make_project(tmp_path)
        ctx = _make_ctx(project)
        ex = ValueError("generic error no path")
        assert eb._maybe_typo_suggestion(ex, ctx, "Mcu") == ()

    def test_returns_suggestions_on_typo(
        self, tmp_path: Path
    ) -> None:
        """typo 'Mcu/Clock/ClockFrq' → 建议 'Mcu/Clock/ClockFreq'。"""
        project = _make_project(tmp_path)
        ctx = _make_ctx(project)
        ex = ValueError("Path 'Mcu/Clock/ClockFrq' not in tree")
        sugg = eb._maybe_typo_suggestion(ex, ctx, "Mcu")
        # 至少有一条候选
        assert len(sugg) >= 1
        # 时钟候选应该出现
        assert "Mcu/Clock/ClockFreq" in sugg


# ---------------------------------------------------------------------------
# argparse — save default adapter=real
# ---------------------------------------------------------------------------


class TestArgparseDefaults:
    def test_default_adapter_is_real(self) -> None:
        parser = eb.build_parser()
        args = parser.parse_args(["eb", "save", "--module", "Mcu"])
        assert args.adapter == "real"

    def test_default_tresos_home_is_none(self) -> None:
        parser = eb.build_parser()
        args = parser.parse_args(["eb", "save", "--module", "Mcu"])
        assert args.tresos_home is None
