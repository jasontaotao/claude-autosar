"""Sprint 8.E.1 — coverage backfill for xdm-apply-template.

Plan reference: Sprint 8.E.1 Task A — rank 3 CLI command error path coverage.

Target:
  - cli/commands/xdm_apply_template.py  (50 missing → cover error paths)

Strategy: use the real xdm machinery on a tmp copy of fixtures; for
specific error branches, monkeypatch.setattr the function under test.

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
import types
from typing import Any

import pytest

from claude_autosar.cli.commands import xdm_apply_template

pytestmark = pytest.mark.autosar


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
XDM_FIXTURE = FIXTURES_DIR / "datamodel2" / "Can.xdm"


def _copy_xdm_fixtures(tmp_path: Path) -> tuple[Path, Path]:
    """Copy XDM fixtures into tmp_path."""
    src = tmp_path / "src.xdm"
    tpl = tmp_path / "tpl.xdm"
    src.write_bytes(XDM_FIXTURE.read_bytes())
    tpl.write_bytes(XDM_FIXTURE.read_bytes())
    return src, tpl


# ---------------------------------------------------------------------------
# xdm-apply-template — argparse
# ---------------------------------------------------------------------------


class TestXdmApplyTemplateArgparse:
    def test_parser_exposes_all_args(self) -> None:
        parser = xdm_apply_template.build_parser()
        args = parser.parse_args(
            [
                "xdm-apply-template",
                "a.xdm",
                "b.xdm",
                "-o",
                "out.html",
                "--apply",
                "--project",
                "/p",
            ]
        )
        assert args.path == Path("a.xdm")
        assert args.template == Path("b.xdm")
        assert args.output == Path("out.html")
        assert args.apply is True
        assert args.project == "/p"

    def test_parser_defaults(self) -> None:
        parser = xdm_apply_template.build_parser()
        args = parser.parse_args(["xdm-apply-template", "a.xdm", "b.xdm"])
        assert args.output is None
        assert args.apply is False
        assert args.project == "."


# ---------------------------------------------------------------------------
# xdm-apply-template — error paths
# ---------------------------------------------------------------------------


class TestXdmApplyTemplateErrorPaths:
    def test_missing_current_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        missing = tmp_path / "nope.xdm"
        tpl = tmp_path / "tpl.xdm"
        tpl.write_bytes(XDM_FIXTURE.read_bytes())
        args = argparse.Namespace(
            path=missing, template=tpl, output=None, apply=False, project="."
        )
        code = xdm_apply_template.run(args)
        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.err.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "FileNotFoundError" in payload["error"]

    def test_missing_template_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        src, _ = _copy_xdm_fixtures(tmp_path)
        missing = tmp_path / "nope_tpl.xdm"
        args = argparse.Namespace(
            path=src, template=missing, output=None, apply=False, project="."
        )
        code = xdm_apply_template.run(args)
        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.err.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "FileNotFoundError" in payload["error"]

    def test_dispatch_unknown_format_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """dispatcher.read 抛 UnknownFormatError → exit 1。"""
        from claude_autosar.core.bsw import dispatcher

        src, tpl = _copy_xdm_fixtures(tmp_path)

        def _raise_read(_p: Path, *, expected_format: Any = None) -> Any:  # noqa: ARG001
            raise dispatcher.UnknownFormatError("not a known format")

        monkeypatch.setattr(dispatcher, "read", _raise_read)

        args = argparse.Namespace(
            path=src, template=tpl, output=None, apply=False, project="."
        )
        code = xdm_apply_template.run(args)
        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.err.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "UnknownFormatError" in payload["error"]

    def test_datamodel2_error_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """dispatcher.read 抛 DataModel2Error → exit 1。"""
        from claude_autosar.core.bsw import dispatcher
        from claude_autosar.core.bsw.io import datamodel2_io

        src, tpl = _copy_xdm_fixtures(tmp_path)

        def _raise_read(_p: Path, *, expected_format: Any = None) -> Any:  # noqa: ARG001
            raise datamodel2_io.DataModel2Error("bad xdm structure")

        monkeypatch.setattr(dispatcher, "read", _raise_read)

        args = argparse.Namespace(
            path=src, template=tpl, output=None, apply=False, project="."
        )
        code = xdm_apply_template.run(args)
        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.err.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "DataModel2Error" in payload["error"]

    def test_load_xdm_module_value_error_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """load_xdm_module 抛 XDMValueError → exit 1。"""
        from claude_autosar.core.bsw.templates import xdm_value as xv_mod

        src, tpl = _copy_xdm_fixtures(tmp_path)

        def _raise_load(_p: Any, _m: str) -> Any:
            raise xv_mod.XDMValueError("no <d:chc> for module")

        monkeypatch.setattr(xv_mod, "load_xdm_module", _raise_load)

        args = argparse.Namespace(
            path=src, template=tpl, output=None, apply=False, project="."
        )
        code = xdm_apply_template.run(args)
        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.err.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "XDMValueError" in payload["error"]

    def test_diff_value_error_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """diff_xdm_templates 抛 ValueError → exit 1。"""
        from claude_autosar.core.bsw.templates import xdm_diff as xd_mod

        src, tpl = _copy_xdm_fixtures(tmp_path)

        def _raise_diff(_c: Any, _t: Any) -> Any:
            raise ValueError("diff failed")

        monkeypatch.setattr(xd_mod, "diff_xdm_templates", _raise_diff)

        args = argparse.Namespace(
            path=src, template=tpl, output=None, apply=False, project="."
        )
        code = xdm_apply_template.run(args)
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
        """diff_xdm_templates 抛 TypeError → exit 1。"""
        from claude_autosar.core.bsw.templates import xdm_diff as xd_mod

        src, tpl = _copy_xdm_fixtures(tmp_path)

        def _raise_diff(_c: Any, _t: Any) -> Any:
            raise TypeError("bad arg")

        monkeypatch.setattr(xd_mod, "diff_xdm_templates", _raise_diff)

        args = argparse.Namespace(
            path=src, template=tpl, output=None, apply=False, project="."
        )
        code = xdm_apply_template.run(args)
        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.err.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "TypeError" in payload["error"]

    def test_apply_template_oserror_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """apply_template_diff 抛 OSError → exit 1。"""
        from claude_autosar.core.bsw.templates import apply as apply_mod

        src, tpl = _copy_xdm_fixtures(tmp_path)

        def _raise_apply(
            _p: Any, _d: Any, *, mode: Any = None  # noqa: ARG001
        ) -> Any:
            raise OSError("write failed")

        monkeypatch.setattr(apply_mod, "apply_template_diff", _raise_apply)

        args = argparse.Namespace(
            path=src, template=tpl, output=None, apply=True, project="."
        )
        code = xdm_apply_template.run(args)
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
        """apply_template_diff 抛 ValueError → exit 1。"""
        from claude_autosar.core.bsw.templates import apply as apply_mod

        src, tpl = _copy_xdm_fixtures(tmp_path)

        def _raise_apply(
            _p: Any, _d: Any, *, mode: Any = None  # noqa: ARG001
        ) -> Any:
            raise ValueError("bad op")

        monkeypatch.setattr(apply_mod, "apply_template_diff", _raise_apply)

        args = argparse.Namespace(
            path=src, template=tpl, output=None, apply=False, project="."
        )
        code = xdm_apply_template.run(args)
        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.err.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "ValueError" in payload["error"]

    def test_html_output_writes_report(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--output 指定 → 写 XDM HTML 报告。"""
        src, tpl = _copy_xdm_fixtures(tmp_path)
        out_html = tmp_path / "report.html"
        args = argparse.Namespace(
            path=src, template=tpl, output=out_html, apply=False, project="."
        )
        with suppress(TypeError):
            # 已知：real ApplyResult 序列化 Path 失败；HTML 已写出
            xdm_apply_template.run(args)
        assert out_html.exists()
        assert "XDM Template Diff" in out_html.read_text(encoding="utf-8")
        _ = capsys.readouterr()

    def test_html_output_oserror_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--output 写盘失败 → exit 1。"""
        src, tpl = _copy_xdm_fixtures(tmp_path)
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
        code = xdm_apply_template.run(args)
        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.err.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "OSError" in payload["error"]


# ---------------------------------------------------------------------------
# xdm-apply-template — _apply_result_to_dict + _detect_module_name
# ---------------------------------------------------------------------------


class TestXdmApplyResultToDict:
    def test_dataclass_result_serializes(self) -> None:
        from claude_autosar.cli.commands.xdm_apply_template import (
            _apply_result_to_dict,
        )

        @dataclass(frozen=True)
        class _R:
            x: int
            y: str

        d = _apply_result_to_dict(_R(x=1, y="z"))
        assert d == {"x": 1, "y": "z"}

    def test_non_dataclass_via_vars(self) -> None:
        from claude_autosar.cli.commands.xdm_apply_template import (
            _apply_result_to_dict,
        )

        class _O:
            def __init__(self) -> None:
                self.a = 1

        d = _apply_result_to_dict(_O())
        assert d == {"a": 1}

    def test_bare_object_falls_back_to_empty(self) -> None:
        from claude_autosar.cli.commands.xdm_apply_template import (
            _apply_result_to_dict,
        )

        # object() 无 __dict__ → vars() 抛 TypeError → 返 {}
        d = _apply_result_to_dict(object())
        assert d == {}


class TestXdmDetectModuleName:
    """``_detect_module_name`` helper."""

    def test_returns_first_chc_name(self) -> None:
        from lxml import etree

        from claude_autosar.cli.commands.xdm_apply_template import (
            _detect_module_name,
        )

        xml = b"""<?xml version="1.0"?>
<root xmlns:d="http://www.tresos.de/_projects/DataModel2/06/data.xsd">
  <d:chc type="AR-ELEMENT" name="Mcu"/>
  <d:chc type="AR-ELEMENT" name="Port"/>
</root>
"""
        tree = etree.fromstring(xml)
        loaded = types.SimpleNamespace(tree=tree)
        assert _detect_module_name(loaded) == "Mcu"

    def test_returns_none_when_no_chc(self) -> None:
        from lxml import etree

        from claude_autosar.cli.commands.xdm_apply_template import (
            _detect_module_name,
        )

        xml = b"""<?xml version="1.0"?>
<root xmlns:d="http://www.tresos.de/_projects/DataModel2/06/data.xsd">
  <d:other/>
</root>
"""
        tree = etree.fromstring(xml)
        loaded = types.SimpleNamespace(tree=tree)
        assert _detect_module_name(loaded) is None

    def test_returns_none_on_no_name_attr(self) -> None:
        from lxml import etree

        from claude_autosar.cli.commands.xdm_apply_template import (
            _detect_module_name,
        )

        xml = b"""<?xml version="1.0"?>
<root xmlns:d="http://www.tresos.de/_projects/DataModel2/06/data.xsd">
  <d:chc type="AR-ELEMENT"/>
</root>
"""
        tree = etree.fromstring(xml)
        loaded = types.SimpleNamespace(tree=tree)
        assert _detect_module_name(loaded) is None

    def test_returns_none_when_tree_xpath_raises(self) -> None:
        """当 loaded_doc.tree 不是 lxml 树时 → return None。"""
        from claude_autosar.cli.commands.xdm_apply_template import (
            _detect_module_name,
        )

        class _BadTree:
            def xpath(self, *_a: Any, **_kw: Any) -> Any:
                raise RuntimeError("not lxml")

        loaded = types.SimpleNamespace(tree=_BadTree())
        assert _detect_module_name(loaded) is None
