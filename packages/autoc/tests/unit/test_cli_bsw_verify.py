"""Unit tests for `autoc bsw-verify` CLI subcommand (Sprint 9.3 — T9.3-β).

测试范围：
* argparse：6 个参数（--project / --module / --tresos-home / --chip-derivative
  / --mcal-vendor / --mcal-vendor-home / --as-json）解析正确。
* run()：happy path（mock 掉 bsw_verify tool 自身，验证 CLI 包装正确）；
  异常路径（tool 抛异常 → stderr JSON + return 1）。
* 跟 `eb` / `davinci` 一致：print JSON 到 stdout，异常 JSON 到 stderr。
"""

from __future__ import annotations

import argparse
import json
from unittest import mock

import pytest

pytestmark = pytest.mark.autosar


# ---------------------------------------------------------------------------
# argparse
# ---------------------------------------------------------------------------


class TestArgparse:
    def test_minimal_required_only(self) -> None:
        """只 --module：其他默认。"""
        from claude_autosar.cli.commands.bsw_verify import build_parser

        parser = build_parser()
        args = parser.parse_args(["bsw-verify", "--module", "Mcu"])
        assert args.command == "bsw-verify"
        assert args.module == "Mcu"
        assert args.project == "."
        assert args.tresos_home is None
        assert args.chip_derivative is None
        assert args.mcal_vendor is None
        assert args.mcal_vendor_home is None
        assert args.as_json is False

    def test_all_optional_flags(self) -> None:
        """全 flag。"""
        from claude_autosar.cli.commands.bsw_verify import build_parser

        parser = build_parser()
        args = parser.parse_args(
            [
                "bsw-verify",
                "--module",
                "Mcu",
                "--project",
                "/tmp/proj",
                "--tresos-home",
                "/tmp/tresos",
                "--chip-derivative",
                "Mcu_s32k148_lqfp176.epd",
                "--mcal-vendor",
                "nxp",
                "--mcal-vendor-home",
                "/tmp/nxp",
                "--as-json",
            ]
        )
        assert args.project == "/tmp/proj"
        assert args.module == "Mcu"
        assert args.tresos_home == "/tmp/tresos"
        assert args.chip_derivative == "Mcu_s32k148_lqfp176.epd"
        assert args.mcal_vendor == "nxp"
        assert args.mcal_vendor_home == "/tmp/nxp"
        assert args.as_json is True

    def test_as_json_flag_absent_defaults_false(self) -> None:
        """--as-json 缺省 → False。"""
        from claude_autosar.cli.commands.bsw_verify import build_parser

        parser = build_parser()
        args = parser.parse_args(["bsw-verify", "--module", "Port"])
        assert args.as_json is False

    def test_missing_module_fails(self) -> None:
        """--module 必填，缺失应报错。"""
        from claude_autosar.cli.commands.bsw_verify import build_parser

        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["bsw-verify"])

    def test_chip_derivative_dest(self) -> None:
        """`--chip-derivative` dest 必须是 chip_derivative（snake_case）。"""
        from claude_autosar.cli.commands.bsw_verify import build_parser

        parser = build_parser()
        args = parser.parse_args(["bsw-verify", "--module", "Mcu", "--chip-derivative", "foo.epd"])
        assert hasattr(args, "chip_derivative")
        assert args.chip_derivative == "foo.epd"
        # 错误写法 chipDerivative 应不存在
        assert not hasattr(args, "chipDerivative")


# ---------------------------------------------------------------------------
# run() happy path
# ---------------------------------------------------------------------------


def _args(**overrides: object) -> argparse.Namespace:
    """构造最小 Namespace；测试只关心 run() 调用 tool 的方式。"""
    base: dict[str, object] = {
        "project": ".",
        "module": "Mcu",
        "tresos_home": None,
        "chip_derivative": None,
        "mcal_vendor": None,
        "mcal_vendor_home": None,
        "as_json": False,
    }
    base.update(overrides)
    return argparse.Namespace(**base)  # type: ignore[arg-type]


class TestRunHappy:
    def test_happy_pass_through_to_mcp_tool(self, capsys: pytest.CaptureFixture[str]) -> None:
        """run() 把所有 args 原样转发给 mcp_server.bsw_verify。"""
        from claude_autosar.cli.commands import bsw_verify as cli_mod

        fake_result = {
            "success": True,
            "module": "Mcu",
            "returncode": 0,
            "report": {"issue_count": 0, "has_errors": False, "has_warnings": False},
            "v2_paths": {},
        }
        args = _args(
            project="/tmp/proj",
            tresos_home="/tmp/tresos",
            chip_derivative="Mcu.epd",
            mcal_vendor="nxp",
            mcal_vendor_home="/tmp/nxp",
        )
        with mock.patch("claude_autosar.cli.mcp_server.bsw_verify", return_value=fake_result) as m:
            exit_code = cli_mod.run(args)
        assert exit_code == 0
        m.assert_called_once_with(
            "Mcu",
            project="/tmp/proj",
            tresos_home="/tmp/tresos",
            chip_derivative="Mcu.epd",
            mcal_vendor="nxp",
            mcal_vendor_home="/tmp/nxp",
            as_json=False,
        )
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["success"] is True
        assert payload["module"] == "Mcu"

    def test_happy_as_json_true(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--as-json 透传：True。"""
        from claude_autosar.cli.commands import bsw_verify as cli_mod

        fake_result = {"success": True, "module": "Mcu", "report": {"has_errors": False}}
        args = _args(as_json=True)
        with mock.patch("claude_autosar.cli.mcp_server.bsw_verify", return_value=fake_result) as m:
            exit_code = cli_mod.run(args)
        assert exit_code == 0
        # kwargs 透传
        _, kwargs = m.call_args
        assert kwargs["as_json"] is True

    def test_prints_json_to_stdout(self, capsys: pytest.CaptureFixture[str]) -> None:
        """CLI 把 result dict 序列化打印到 stdout（无副作用到 stderr）。"""
        from claude_autosar.cli.commands import bsw_verify as cli_mod

        fake_result = {"success": False, "module": "Port", "error": "boom"}
        with mock.patch("claude_autosar.cli.mcp_server.bsw_verify", return_value=fake_result):
            cli_mod.run(_args(module="Port"))
        captured = capsys.readouterr()
        # stdout 含 JSON
        assert '"success": false' in captured.out
        # stderr 为空（happy path 不写错误）
        assert captured.err == ""


# ---------------------------------------------------------------------------
# run() error path
# ---------------------------------------------------------------------------


class TestRunError:
    def test_exception_writes_json_to_stderr_and_returns_1(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """tool 抛异常 → stderr JSON + exit 1（与 eb/davinci CLI 一致）。"""
        from claude_autosar.cli.commands import bsw_verify as cli_mod

        with mock.patch("claude_autosar.cli.mcp_server.bsw_verify", side_effect=RuntimeError("boom")):
            exit_code = cli_mod.run(_args())
        assert exit_code == 1
        captured = capsys.readouterr()
        # stdout 应空（异常不走 stdout）
        assert captured.out == ""
        # stderr 含 JSON error
        payload = json.loads(captured.err)
        assert payload["success"] is False
        assert "RuntimeError" in payload["error"]
        assert "boom" in payload["error"]


# ---------------------------------------------------------------------------
# CLI 通过 mcp_server 调用（非重复实现）
# ---------------------------------------------------------------------------


def test_cli_imports_bsw_verify_from_mcp_server() -> None:
    """CLI 不重复实现 bsw_verify 业务逻辑；从 mcp_server import（延迟 import 模式）。"""
    from claude_autosar.cli import mcp_server

    # run() 内部延迟 import claude_autosar.cli.mcp_server.bsw_verify
    # 验证 mcp_server 模块确实导出了 bsw_verify 函数
    assert callable(mcp_server.bsw_verify)
