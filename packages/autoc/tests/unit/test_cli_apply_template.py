"""Unit tests for Sprint 9.2 T9.2-γ — ``autoc {arxml,xdm}-apply-template`` 子命令。

覆盖：

- 2 个新子命令 ``--help``（argparse sanity）
- argparse 参数：``path`` / ``template`` 位置参数 + ``-o/--output`` + ``--apply`` + ``--project``
- ``main()`` 路由到 2 个新子命令（dispatch 表注册）
- 不存在的文件 → exit 1 + stderr JSON error
- dry-run 模式 vs apply 模式

注：``apply_template_diff`` / ``ApplyMode`` / ``diff_arxml_templates`` 由
并发任务 T9.2.1 / T9.2.0b 实施。本文件用 :mod:`unittest.mock` patch ``run``
函数的子依赖以保持切片独立性。
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import types
from typing import Any

import pytest

from claude_autosar.cli.commands.arxml_apply_template import (
    build_parser as build_arxml_apply_parser,
)
from claude_autosar.cli.commands.xdm_apply_template import build_parser as build_xdm_apply_parser
from claude_autosar.cli.main import _DISPATCH, build_parser, main

pytestmark = pytest.mark.autosar


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
ARXML_FIXTURE = FIXTURES_DIR / "arxml" / "Com_Com.minimal.arxml"
XDM_FIXTURE = FIXTURES_DIR / "datamodel2" / "Can.xdm"


# ---------------------------------------------------------------------------
# Stub 注入：把 apply.py + arxml_diff.py 替换成最小可运行版本
# ---------------------------------------------------------------------------


class _ApplyModeStub:
    DRY_RUN = "dry_run"
    APPLY = "apply"


def _install_apply_template_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    """往 :mod:`claude_autosar.core.bsw.templates.apply` 注入 stub 模块。"""
    stub = types.ModuleType("claude_autosar.core.bsw.templates.apply")

    class _ApplyResult:
        def __init__(self, mode: str, written: bool) -> None:
            self.mode = mode
            self.written = written

    def _apply_template_diff(
        path: Any,  # noqa: ARG001
        diff: Any,  # noqa: ARG001
        *,
        mode: Any = _ApplyModeStub.DRY_RUN,
    ) -> _ApplyResult:
        return _ApplyResult(mode=str(mode), written=(str(mode) == _ApplyModeStub.APPLY))

    stub.ApplyMode = _ApplyModeStub
    stub.apply_template_diff = _apply_template_diff
    monkeypatch.setitem(sys.modules, "claude_autosar.core.bsw.templates.apply", stub)


def _install_arxml_diff_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    """往 :mod:`claude_autosar.core.bsw.templates.arxml_diff` 注入 stub 模块。"""
    stub = types.ModuleType("claude_autosar.core.bsw.templates.arxml_diff")

    class _DiffStub:
        def __init__(self, path: str, op: str) -> None:
            self.path = path
            self.op = op
            self.current = None
            self.template = None

    class _DiffResultStub:
        def __init__(self, diffs: tuple[_DiffStub, ...]) -> None:
            self.diffs = diffs

        @property
        def adds(self) -> tuple[_DiffStub, ...]:
            return tuple(d for d in self.diffs if d.op == "add")

        @property
        def modifies(self) -> tuple[_DiffStub, ...]:
            return tuple(d for d in self.diffs if d.op == "modify")

        @property
        def deletes(self) -> tuple[_DiffStub, ...]:
            return tuple(d for d in self.diffs if d.op == "delete")

    def _diff_arxml_templates(current: Any, template: Any) -> _DiffResultStub:  # noqa: ARG001
        return _DiffResultStub(diffs=(_DiffStub("Module/A", "modify"),))

    stub.diff_arxml_templates = _diff_arxml_templates
    monkeypatch.setitem(sys.modules, "claude_autosar.core.bsw.templates.arxml_diff", stub)


@pytest.fixture
def stub_template_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_apply_template_stub(monkeypatch)
    _install_arxml_diff_stub(monkeypatch)


# ---------------------------------------------------------------------------
# argparse help（最基础的 sanity）
# ---------------------------------------------------------------------------


class TestArgparseHelp:
    def test_arxml_apply_template_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        """arxml-apply-template --help 不崩。"""
        parser = build_arxml_apply_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--help"])
        assert exc_info.value.code == 0

    def test_xdm_apply_template_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        """xdm-apply-template --help 不崩。"""
        parser = build_xdm_apply_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--help"])
        assert exc_info.value.code == 0

    def test_arxml_apply_template_parser_args(
        self,
    ) -> None:
        """验证 argparse 参数 shape。"""
        parser = build_arxml_apply_parser()
        args = parser.parse_args(
            [
                "arxml-apply-template",
                "a.arxml",
                "b.arxml",
                "-o",
                "out.html",
                "--apply",
                "--project",
                "/p",
            ]
        )
        assert args.path == Path("a.arxml")
        assert args.template == Path("b.arxml")
        assert args.output == Path("out.html")
        assert args.apply is True
        assert args.project == "/p"

    def test_xdm_apply_template_parser_args(
        self,
    ) -> None:
        """验证 argparse 参数 shape（XDM 端）。"""
        parser = build_xdm_apply_parser()
        args = parser.parse_args(
            [
                "xdm-apply-template",
                "a.xdm",
                "b.xdm",
                "-o",
                "out.html",
            ]
        )
        assert args.path == Path("a.xdm")
        assert args.template == Path("b.xdm")
        assert args.output == Path("out.html")
        assert args.apply is False  # default
        assert args.project == "."  # default


# ---------------------------------------------------------------------------
# arxml-apply-template run（end-to-end via main()）
# ---------------------------------------------------------------------------


class TestArxmlApplyTemplateRun:
    def test_arxml_apply_template_dry_run(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        stub_template_modules: None,
    ) -> None:
        """arxml-apply-template 在 fixture 上跑通（dry-run 默认）。"""
        src = tmp_path / "Com_Com.minimal.arxml"
        src.write_bytes(ARXML_FIXTURE.read_bytes())
        tpl = tmp_path / "Com_Com.template.arxml"
        tpl.write_bytes(ARXML_FIXTURE.read_bytes())

        code = main(["arxml-apply-template", str(src), str(tpl)])
        captured = capsys.readouterr()

        assert code == 0
        payload = json.loads(captured.out.strip().splitlines()[-1])
        assert payload["success"] is True
        assert payload["format"] == "arxml"
        assert payload["applied"] is False
        assert payload["mode"] == _ApplyModeStub.DRY_RUN
        assert payload["path"] == str(src)
        assert payload["template"] == str(tpl)
        assert "diff_count" in payload
        assert "adds" in payload
        assert "modifies" in payload
        assert "deletes" in payload

    def test_arxml_apply_template_with_apply_flag(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        stub_template_modules: None,
    ) -> None:
        """arxml-apply-template --apply → applied=True + mode=APPLY。"""
        src = tmp_path / "Com_Com.minimal.arxml"
        src.write_bytes(ARXML_FIXTURE.read_bytes())
        tpl = tmp_path / "Com_Com.template.arxml"
        tpl.write_bytes(ARXML_FIXTURE.read_bytes())

        code = main(["arxml-apply-template", str(src), str(tpl), "--apply"])
        captured = capsys.readouterr()

        assert code == 0
        payload = json.loads(captured.out.strip().splitlines()[-1])
        assert payload["success"] is True
        assert payload["applied"] is True
        assert payload["mode"] == _ApplyModeStub.APPLY

    def test_arxml_apply_template_missing_current(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        stub_template_modules: None,
    ) -> None:
        """不存在的 current → exit 1 + stderr JSON error。"""
        tpl = tmp_path / "Com_Com.template.arxml"
        tpl.write_bytes(ARXML_FIXTURE.read_bytes())
        missing = tmp_path / "no_such.arxml"

        code = main(["arxml-apply-template", str(missing), str(tpl)])
        captured = capsys.readouterr()

        assert code == 1
        payload = json.loads(captured.err.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "error" in payload


# ---------------------------------------------------------------------------
# xdm-apply-template run
# ---------------------------------------------------------------------------


class TestXdmApplyTemplateRun:
    def test_xdm_apply_template_dry_run(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        stub_template_modules: None,
    ) -> None:
        """xdm-apply-template 在 fixture 上跑通（dry-run 默认）。"""
        src = tmp_path / "Can.xdm"
        src.write_bytes(XDM_FIXTURE.read_bytes())
        tpl = tmp_path / "Can_template.xdm"
        tpl.write_bytes(XDM_FIXTURE.read_bytes())

        code = main(["xdm-apply-template", str(src), str(tpl)])
        captured = capsys.readouterr()

        assert code == 0
        payload = json.loads(captured.out.strip().splitlines()[-1])
        assert payload["success"] is True
        assert payload["format"] == "xdm"
        assert payload["applied"] is False
        assert payload["mode"] == _ApplyModeStub.DRY_RUN
        assert "module_name" in payload

    def test_xdm_apply_template_with_apply_flag(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        stub_template_modules: None,
    ) -> None:
        """xdm-apply-template --apply → applied=True + mode=APPLY。"""
        src = tmp_path / "Can.xdm"
        src.write_bytes(XDM_FIXTURE.read_bytes())
        tpl = tmp_path / "Can_template.xdm"
        tpl.write_bytes(XDM_FIXTURE.read_bytes())

        code = main(["xdm-apply-template", str(src), str(tpl), "--apply"])
        captured = capsys.readouterr()

        assert code == 0
        payload = json.loads(captured.out.strip().splitlines()[-1])
        assert payload["success"] is True
        assert payload["applied"] is True

    def test_xdm_apply_template_missing_current(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        stub_template_modules: None,
    ) -> None:
        """不存在的 current → exit 1 + stderr JSON error。"""
        tpl = tmp_path / "Can_template.xdm"
        tpl.write_bytes(XDM_FIXTURE.read_bytes())
        missing = tmp_path / "no_such.xdm"

        code = main(["xdm-apply-template", str(missing), str(tpl)])
        captured = capsys.readouterr()

        assert code == 1
        payload = json.loads(captured.err.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "error" in payload


# ---------------------------------------------------------------------------
# main.py dispatch 表注册回归
# ---------------------------------------------------------------------------


class TestMainDispatch:
    """Sprint 9.2 T9.2-γ：dispatch 表新增 2 个 apply-template 子命令。"""

    def test_dispatch_includes_two_apply_template_subcommands(self) -> None:
        parser = build_parser()
        sub_action = next(
            a
            for a in parser._actions
            if hasattr(a, "choices") and a.choices  # type: ignore[attr-defined]
        )
        registered = set(sub_action.choices)
        assert "arxml-apply-template" in registered
        assert "xdm-apply-template" in registered

    def test_dispatch_routing_for_apply_template_subcommands(self) -> None:
        """dispatch 表能正确路由到 2 个 apply-template 子命令模块。"""
        assert "arxml-apply-template" in _DISPATCH
        assert "xdm-apply-template" in _DISPATCH
        for name in ("arxml-apply-template", "xdm-apply-template"):
            register_fn, run_fn = _DISPATCH[name]
            assert callable(register_fn)
            assert callable(run_fn)
            assert register_fn.__module__ in {
                "claude_autosar.cli.commands.arxml_apply_template",
                "claude_autosar.cli.commands.xdm_apply_template",
            }

    def test_arxml_apply_template_register_module_attr(self) -> None:
        """注册函数模块路径匹配（防止 copy-paste 错位）。"""
        register_fn, _ = _DISPATCH["arxml-apply-template"]
        assert register_fn.__module__ == "claude_autosar.cli.commands.arxml_apply_template"

    def test_xdm_apply_template_register_module_attr(self) -> None:
        """注册函数模块路径匹配（防止 copy-paste 错位）。"""
        register_fn, _ = _DISPATCH["xdm-apply-template"]
        assert register_fn.__module__ == "claude_autosar.cli.commands.xdm_apply_template"
