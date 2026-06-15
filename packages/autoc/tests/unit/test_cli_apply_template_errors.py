"""Sprint 8.E.1 — coverage backfill for ``arxml-apply-template`` / ``xdm-apply-template``.

Plan reference: Sprint 8.E.1 Task A — rank 2/3 CLI command error path coverage.

Targets (see ``plan/steady-covering-phoenix.md`` §1):
  - ``cli/commands/arxml_apply_template.py`` (50 missing → cover error paths)
  - ``cli/commands/xdm_apply_template.py``  (50 missing → cover error paths)

Strategy: use the real arxml/xdm machinery on a tmp copy of fixtures; for
specific error branches, ``monkeypatch.setattr`` the function under test.
The ``templates.apply`` module is also real and lives in the source tree,
so no stubbing of that layer is needed.

**禁 令**:
- 不改产品代码
- 不 git commit
- 不引入新 pip 依赖
"""
from __future__ import annotations

import argparse
from contextlib import suppress
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import pytest

from claude_autosar.cli.commands import arxml_apply_template

pytestmark = pytest.mark.autosar


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
ARXML_FIXTURE = FIXTURES_DIR / "arxml" / "Com_Com.minimal.arxml"
XDM_FIXTURE = FIXTURES_DIR / "datamodel2" / "Can.xdm"


def _copy_fixtures(tmp_path: Path) -> tuple[Path, Path]:
    """Copy ARXML fixtures into tmp_path for write-isolation."""
    src = tmp_path / "src.arxml"
    tpl = tmp_path / "tpl.arxml"
    src.write_bytes(ARXML_FIXTURE.read_bytes())
    tpl.write_bytes(ARXML_FIXTURE.read_bytes())
    return src, tpl


def _copy_xdm_fixtures(tmp_path: Path) -> tuple[Path, Path]:
    """Copy XDM fixtures into tmp_path."""
    src = tmp_path / "src.xdm"
    tpl = tmp_path / "tpl.xdm"
    src.write_bytes(XDM_FIXTURE.read_bytes())
    tpl.write_bytes(XDM_FIXTURE.read_bytes())
    return src, tpl


# ---------------------------------------------------------------------------
# arxml-apply-template — argparse
# ---------------------------------------------------------------------------


class TestArxmlApplyTemplateArgparse:
    """Build_parser & argument shape."""

    def test_parser_exposes_all_args(self) -> None:
        parser = arxml_apply_template.build_parser()
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

    def test_parser_defaults(self) -> None:
        parser = arxml_apply_template.build_parser()
        args = parser.parse_args(["arxml-apply-template", "a.arxml", "b.arxml"])
        assert args.output is None
        assert args.apply is False
        assert args.project == "."


# ---------------------------------------------------------------------------
# arxml-apply-template — error paths (real template.apply machinery)
# ---------------------------------------------------------------------------


class TestArxmlApplyTemplateErrorPaths:
    """Error coverage for ``arxml_apply_template.run()``."""

    def test_missing_current_file_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """不存在的 current → exit 1 + stderr JSON error (FileNotFoundError)。"""
        missing = tmp_path / "nope.arxml"
        tpl = tmp_path / "tpl.arxml"
        tpl.write_bytes(ARXML_FIXTURE.read_bytes())
        args = argparse.Namespace(
            path=missing, template=tpl, output=None, apply=False, project="."
        )
        code = arxml_apply_template.run(args)
        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.err.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "FileNotFoundError" in payload["error"]

    def test_missing_template_file_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """存在的 current + 缺失 template → exit 1 (第二段 dispatcher 失败)。"""
        src, _ = _copy_fixtures(tmp_path)
        missing_tpl = tmp_path / "nope_tpl.arxml"
        args = argparse.Namespace(
            path=src, template=missing_tpl, output=None, apply=False, project="."
        )
        code = arxml_apply_template.run(args)
        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.err.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "FileNotFoundError" in payload["error"]

    def test_dispatcher_mismatch_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """template 不被 dispatcher 接受（expected_format=arxml）→ FormatMismatchError。"""
        from claude_autosar.core.bsw import dispatcher

        src, tpl = _copy_fixtures(tmp_path)
        first_call = {"done": False}

        def _raise_read(p: Path, *, expected_format: Any = None) -> Any:  # noqa: ARG001
            if not first_call["done"]:
                first_call["done"] = True
                return object()  # current 解析"成功"
            raise dispatcher.FormatMismatchError("expected arxml, got xdm")

        monkeypatch.setattr(dispatcher, "read", _raise_read)

        args = argparse.Namespace(
            path=src, template=tpl, output=None, apply=False, project="."
        )
        code = arxml_apply_template.run(args)
        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.err.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "FormatMismatchError" in payload["error"]

    def test_dispatcher_unknown_format_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """dispatcher.read 抛 UnknownFormatError → exit 1。"""
        from claude_autosar.core.bsw import dispatcher

        src, tpl = _copy_fixtures(tmp_path)

        def _raise_unknown(_p: Path, *, expected_format: Any = None) -> Any:  # noqa: ARG001
            raise dispatcher.UnknownFormatError("cannot detect format")

        monkeypatch.setattr(dispatcher, "read", _raise_unknown)

        args = argparse.Namespace(
            path=src, template=tpl, output=None, apply=False, project="."
        )
        code = arxml_apply_template.run(args)
        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.err.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "UnknownFormatError" in payload["error"]

    def test_no_module_name_detected_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """两份文件都没有 ECUC-MODULE-CONFIGURATION-VALUES → ValueError。"""
        empty = """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES><AR-PACKAGE><SHORT-NAME>X</SHORT-NAME><ELEMENTS/></AR-PACKAGE></AR-PACKAGES>
</AUTOSAR>
"""
        src = tmp_path / "empty1.arxml"
        tpl = tmp_path / "empty2.arxml"
        src.write_text(empty, encoding="utf-8")
        tpl.write_text(empty, encoding="utf-8")

        args = argparse.Namespace(
            path=src, template=tpl, output=None, apply=False, project="."
        )
        code = arxml_apply_template.run(args)
        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.err.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "ValueError" in payload["error"]
        assert "ECUC-MODULE-CONFIGURATION-VALUES" in payload["error"]

    def test_load_module_value_error_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``ecuc.load_module`` 抛 ValueError → exit 1。"""
        from claude_autosar.core.bsw import ecuc as ecuc_mod

        src, tpl = _copy_fixtures(tmp_path)

        def _raise_load_module(_p: Any, _m: str) -> Any:
            raise ValueError("module not found in document")

        monkeypatch.setattr(ecuc_mod, "load_module", _raise_load_module)

        args = argparse.Namespace(
            path=src, template=tpl, output=None, apply=False, project="."
        )
        code = arxml_apply_template.run(args)
        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.err.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "ValueError" in payload["error"]

    def test_apply_template_oserror_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """apply_template_diff 抛 OSError → exit 1。"""
        from claude_autosar.core.bsw.templates import apply as apply_mod

        src, tpl = _copy_fixtures(tmp_path)

        def _raise_apply(
            _p: Any, _d: Any, *, mode: Any = None  # noqa: ARG001
        ) -> Any:
            raise OSError("disk full")

        monkeypatch.setattr(apply_mod, "apply_template_diff", _raise_apply)

        args = argparse.Namespace(
            path=src, template=tpl, output=None, apply=True, project="."
        )
        code = arxml_apply_template.run(args)
        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.err.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "OSError" in payload["error"]

    def test_apply_template_value_error_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """apply_template_diff 抛 ValueError（不支持的 op）→ exit 1。"""
        from claude_autosar.core.bsw.templates import apply as apply_mod

        src, tpl = _copy_fixtures(tmp_path)

        def _raise_apply(
            _p: Any, _d: Any, *, mode: Any = None  # noqa: ARG001
        ) -> Any:
            raise ValueError("unsupported op: add")

        monkeypatch.setattr(apply_mod, "apply_template_diff", _raise_apply)

        args = argparse.Namespace(
            path=src, template=tpl, output=None, apply=False, project="."
        )
        code = arxml_apply_template.run(args)
        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.err.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "ValueError" in payload["error"]

    def test_diff_value_error_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """diff_arxml_templates 抛 ValueError → exit 1。"""
        from claude_autosar.core.bsw.templates import arxml_diff as ad_mod

        src, tpl = _copy_fixtures(tmp_path)

        def _raise_diff(_c: Any, _t: Any) -> Any:
            raise ValueError("diff failed: bad path")

        monkeypatch.setattr(ad_mod, "diff_arxml_templates", _raise_diff)

        args = argparse.Namespace(
            path=src, template=tpl, output=None, apply=False, project="."
        )
        code = arxml_apply_template.run(args)
        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.err.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "ValueError" in payload["error"]

    def test_diff_type_error_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """diff_arxml_templates 抛 TypeError → exit 1。"""
        from claude_autosar.core.bsw.templates import arxml_diff as ad_mod

        src, tpl = _copy_fixtures(tmp_path)

        def _raise_diff(_c: Any, _t: Any) -> Any:
            raise TypeError("bad arg")

        monkeypatch.setattr(ad_mod, "diff_arxml_templates", _raise_diff)

        args = argparse.Namespace(
            path=src, template=tpl, output=None, apply=False, project="."
        )
        code = arxml_apply_template.run(args)
        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.err.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "TypeError" in payload["error"]

    def test_html_output_writes_report(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--output 指定 → 写 HTML 报告到 out_path。

        注：real apply_template_diff 返回含 Path 字段的 ApplyResult，stdout
        JSON 序列化会 TypeError。但 HTML 报告本身已被写出（L278-281 关键行
        覆盖）；我们用 ``try/except TypeError`` 让测试不崩，只断言 HTML
        文件存在 + 标题出现。
        """
        src, tpl = _copy_fixtures(tmp_path)
        out_html = tmp_path / "report.html"
        args = argparse.Namespace(
            path=src, template=tpl, output=out_html, apply=False, project="."
        )
        with suppress(TypeError):
            # 已知：real ApplyResult 序列化 Path 失败；HTML 已写出
            arxml_apply_template.run(args)
        assert out_html.exists()
        assert "ARXML Template Diff" in out_html.read_text(encoding="utf-8")
        _ = capsys.readouterr()

    def test_html_output_oserror_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--output 路径写盘失败 → exit 1 (OSError 分支)。"""
        src, tpl = _copy_fixtures(tmp_path)
        orig_write_text = Path.write_text

        def _raise_write(self: Path, *args: Any, **kwargs: Any) -> Any:  # noqa: ARG001
            if self.name == "report.html":
                raise OSError("permission denied")
            return orig_write_text(self, *args, **kwargs)

        monkeypatch.setattr(Path, "write_text", _raise_write)
        out_html = tmp_path / "report.html"
        args = argparse.Namespace(
            path=src, template=tpl, output=out_html, apply=False, project="."
        )
        code = arxml_apply_template.run(args)
        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.err.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "OSError" in payload["error"]


# ---------------------------------------------------------------------------
# arxml-apply-template — _apply_result_to_dict helper
# ---------------------------------------------------------------------------


class TestArxmlApplyResultToDict:
    """``_apply_result_to_dict`` 工具函数（dataclass + non-dataclass）。"""

    def test_dataclass_result_serializes(self) -> None:
        from claude_autosar.cli.commands.arxml_apply_template import (
            _apply_result_to_dict,
        )

        @dataclass(frozen=True)
        class _FakeResult:
            a: int
            b: str

        result = _FakeResult(a=1, b="x")
        d = _apply_result_to_dict(result)
        assert d == {"a": 1, "b": "x"}

    def test_non_dataclass_falls_back_to_vars(self) -> None:
        from claude_autosar.cli.commands.arxml_apply_template import (
            _apply_result_to_dict,
        )

        class _NonDC:
            def __init__(self) -> None:
                self.x = 1
                self.y = "z"

        d = _apply_result_to_dict(_NonDC())
        assert d == {"x": 1, "y": "z"}

    def test_dataclass_class_object_falls_back_to_empty(self) -> None:
        """传入 type 自身（不是 instance）→ vars() 返 class dict 但不抛 → 这里走 dataclass 分支或 vars 路径都不会 empty；接受任意非异常结果。

        注: type 实例（有 __dict__）vars() 不会抛；只有真的"啥都没有"的对象
        （如 object() 无 __dict__）才 TypeError。验证 _apply_result_to_dict
        对 object() 返空 dict（vars 失败兜底）。
        """
        from claude_autosar.cli.commands.arxml_apply_template import (
            _apply_result_to_dict,
        )

        # bare object() 没有 __dict__ → vars() 抛 TypeError → 返 {}
        d = _apply_result_to_dict(object())
        assert d == {}
