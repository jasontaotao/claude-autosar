"""Unit tests for Sprint 9.1 T9.1.4 — ``autoc {arxml,xdm,bsw}-inspect`` 子命令。

覆盖：

- 3 个子命令都能接受 ``--help``（argparse sanity）
- ``arxml-inspect`` 在最小 fixture 上跑通（end-to-end）
- ``xdm-inspect`` 在 fixture 上跑通
- ``bsw-inspect`` 在 arxml fixture 上自动选 ``arxml``
- 不存在的文件 → exit 1 + stderr JSON error
- 自定义 ``-o`` 输出路径
- main.py dispatch 表注册到 9 个子命令（含 3 个新 inspect 子命令）
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from claude_autosar.cli.commands.arxml_inspect import build_parser as build_arxml_parser
from claude_autosar.cli.commands.bsw_inspect import build_parser as build_bsw_parser
from claude_autosar.cli.commands.xdm_inspect import build_parser as build_xdm_parser
from claude_autosar.cli.main import build_parser, main

pytestmark = pytest.mark.autosar


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
ARXML_FIXTURE = FIXTURES_DIR / "arxml" / "Com_Com.minimal.arxml"
XDM_FIXTURE = FIXTURES_DIR / "datamodel2" / "Can.xdm"


# ---------------------------------------------------------------------------
# argparse help（最基础的 sanity）
# ---------------------------------------------------------------------------


class TestArgparseHelp:
    def test_arxml_inspect_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        """arxml-inspect --help 不崩。"""
        parser = build_arxml_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--help"])
        assert exc_info.value.code == 0

    def test_xdm_inspect_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        parser = build_xdm_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--help"])
        assert exc_info.value.code == 0

    def test_bsw_inspect_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        parser = build_bsw_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--help"])
        assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# arxml-inspect run
# ---------------------------------------------------------------------------


class TestArxmlInspectRun:
    def test_arxml_inspect_run_success(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """arxml-inspect 在 fixture 上跑通 + 默认输出 + stdout JSON。"""
        # 复制 fixture 到 tmp_path（避免污染源；minimizes coupling with other tests）
        src = tmp_path / "Com_Com.minimal.arxml"
        src.write_bytes(ARXML_FIXTURE.read_bytes())

        # 通过 main() 走完整 dispatch（CI 更接近真实路径）
        code = main(["arxml-inspect", str(src)])
        captured = capsys.readouterr()

        assert code == 0
        # stdout 是 JSON
        payload = json.loads(captured.out.strip().splitlines()[-1])
        assert payload["success"] is True
        assert payload["format"] == "arxml"
        assert payload["path"] == str(src)
        # report_path 指向默认 <input>.report.html
        assert payload["report_path"].endswith("Com_Com.minimal.arxml.report.html")
        # HTML 文件存在
        out_path = Path(payload["report_path"])
        assert out_path.exists()
        content = out_path.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "ARXML Report" in content

    def test_arxml_inspect_run_missing_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """不存在的文件 → exit 1 + stderr JSON error。"""
        missing = tmp_path / "no_such.arxml"
        code = main(["arxml-inspect", str(missing)])
        captured = capsys.readouterr()

        assert code == 1
        # stderr 末行是 JSON
        payload = json.loads(captured.err.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "error" in payload

    def test_arxml_inspect_custom_output(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """``-o custom.html`` 写到指定路径。"""
        src = tmp_path / "Com_Com.minimal.arxml"
        src.write_bytes(ARXML_FIXTURE.read_bytes())
        out = tmp_path / "my-report.html"

        code = main(["arxml-inspect", str(src), "-o", str(out)])
        captured = capsys.readouterr()

        assert code == 0
        payload = json.loads(captured.out.strip().splitlines()[-1])
        assert payload["success"] is True
        # 报告路径匹配 custom output
        assert Path(payload["report_path"]).resolve() == out.resolve()
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content


# ---------------------------------------------------------------------------
# xdm-inspect run
# ---------------------------------------------------------------------------


class TestXdmInspectRun:
    def test_xdm_inspect_run_success(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """xdm-inspect 在 fixture 上跑通。"""
        src = tmp_path / "Can.xdm"
        src.write_bytes(XDM_FIXTURE.read_bytes())

        code = main(["xdm-inspect", str(src)])
        captured = capsys.readouterr()

        assert code == 0
        payload = json.loads(captured.out.strip().splitlines()[-1])
        assert payload["success"] is True
        assert payload["format"] == "xdm"
        out_path = Path(payload["report_path"])
        assert out_path.exists()
        content = out_path.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "XDM Report" in content or "DataModel2 Report" in content


# ---------------------------------------------------------------------------
# bsw-inspect run（dispatcher 自动选）
# ---------------------------------------------------------------------------


class TestBswInspectRun:
    def test_bsw_inspect_auto_dispatch_arxml(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """bsw-inspect 自动选 arxml（fixture 是 .arxml）。"""
        src = tmp_path / "sample.arxml"
        src.write_bytes(ARXML_FIXTURE.read_bytes())

        code = main(["bsw-inspect", str(src)])
        captured = capsys.readouterr()

        assert code == 0
        payload = json.loads(captured.out.strip().splitlines()[-1])
        assert payload["success"] is True
        assert payload["format"] == "arxml"
        out_path = Path(payload["report_path"])
        assert out_path.exists()


# ---------------------------------------------------------------------------
# main.py dispatch 表注册回归
# ---------------------------------------------------------------------------


def test_main_dispatch_includes_three_inspect_subcommands() -> None:
    """Sprint 9.1 T9.1.4：dispatch 表新增 3 个 inspect 子命令。"""
    parser = build_parser()
    sub_action = next(
        a for a in parser._actions if hasattr(a, "choices") and a.choices  # type: ignore[attr-defined]
    )
    registered = set(sub_action.choices)
    assert "arxml-inspect" in registered
    assert "xdm-inspect" in registered
    assert "bsw-inspect" in registered


def test_main_dispatch_routing_for_inspect_subcommands() -> None:
    """Sprint 9.1 T9.1.4：dispatch 表能正确路由到 3 个 inspect 子命令模块。"""
    from claude_autosar.cli.main import _DISPATCH  # type: ignore[attr-defined]

    assert "arxml-inspect" in _DISPATCH
    assert "xdm-inspect" in _DISPATCH
    assert "bsw-inspect" in _DISPATCH
    for name in ("arxml-inspect", "xdm-inspect", "bsw-inspect"):
        register_fn, run_fn = _DISPATCH[name]
        assert callable(register_fn)
        assert callable(run_fn)
        # 每个 register 应该是 3 个 inspect 模块之一
        assert register_fn.__module__ in {
            "claude_autosar.cli.commands.arxml_inspect",
            "claude_autosar.cli.commands.xdm_inspect",
            "claude_autosar.cli.commands.bsw_inspect",
        }
