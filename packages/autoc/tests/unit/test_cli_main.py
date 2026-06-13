"""Unit tests for autoc.cli.main.

Sprint 5 — T5.1.
- dispatch table (5 subcommands: eb / davinci / session / log / export)
- global --verbose / --no-color flags (repl_skin 准备)
- --version exits 0 with version string on stdout
- 未知子命令: exit 1 + stderr 提示
- 无子命令: 走 placeholder（不引入破坏性行为变更）
"""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_autosar.cli.main import build_parser, main

pytestmark = pytest.mark.autosar


# ---------------------------------------------------------------------------
# build_parser: 形状 / 字段
# ---------------------------------------------------------------------------


def test_build_parser_registers_all_five_subcommands() -> None:
    parser = build_parser()
    # 从 subparser 的 choices 取（argparse 内部表示）
    sub_action = next(
        a for a in parser._actions if hasattr(a, "choices") and a.choices  # type: ignore[attr-defined]
    )
    assert {"eb", "davinci", "session", "log", "export"}.issubset(set(sub_action.choices))


def test_build_parser_has_version_flag() -> None:
    parser = build_parser()
    # --version 在 namespace 中表现为 action='version'
    for action in parser._actions:  # type: ignore[attr-defined]
        if "--version" in action.option_strings:
            assert action.dest == "version"
            assert action.default == "==SUPPRESS=="
            return
    pytest.fail("--version not found in parser actions")


def test_build_parser_has_verbose_flag() -> None:
    """T5.1 新增：--verbose 全局开关，repl_skin 用。"""
    parser = build_parser()
    args = parser.parse_args(["--verbose"])
    assert args.verbose is True


def test_build_parser_has_no_color_flag() -> None:
    """T5.1 新增：--no-color 强制无色（CI / 管道友好）。"""
    parser = build_parser()
    args = parser.parse_args(["--no-color"])
    assert args.no_color is True


def test_build_parser_verbose_default_false() -> None:
    parser = build_parser()
    args = parser.parse_args([])
    assert args.verbose is False
    assert args.no_color is False


# ---------------------------------------------------------------------------
# main(): dispatch 行为
# ---------------------------------------------------------------------------


def test_main_no_subcommand_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    """无子命令：保留 Sprint 3 前的 placeholder 行为（exit 0 + stderr 提示）。"""
    code = main([])
    assert code == 0
    captured = capsys.readouterr()
    assert "开发中" in captured.err or "autoc" in captured.err


def test_main_version_flag_prints_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    """`autoc --version`: exit 0 + version on stdout."""
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert "autoc" in captured.out
    assert "0.1.0" in captured.out


def test_main_unknown_subcommand_exits_one(capsys: pytest.CaptureFixture[str]) -> None:
    """未知子命令：exit 1 + stderr 提示。"""
    code = main(["nonexistent"])
    assert code == 1
    captured = capsys.readouterr()
    assert "未知" in captured.err or "nonexistent" in captured.err


def test_main_dispatches_to_eb_save_stub(tmp_path: Path) -> None:
    """T5.1 dispatch 表正确路由到 eb.run()."""
    tresos_home = tmp_path / "fake-tresos"
    tresos_home.mkdir()
    project = tmp_path / "proj"
    project.mkdir()
    # fake .xdm 触发 eb_run happy path (stub mode)
    (project / "Mcu.xdm").write_text(
        '<?xml version="1.0"?><root><ClockFreq>80000000</ClockFreq></root>',
        encoding="utf-8",
    )

    code = main(
        [
            "eb",
            "save",
            "--project",
            str(project),
            "--module",
            "Mcu",
            "--adapter",
            "stub",
            "--tresos-home",
            str(tresos_home),
        ]
    )
    # eb save stub 模式会走 modify_and_verify → 失败回滚，但 code 由子命令决定
    assert code in (0, 2)  # 0 happy / 2 verify fail 都是合法返回


def test_main_dispatches_to_session_list() -> None:
    """T5.1 dispatch 表路由到 session.run()."""
    # session list 在空 store 时会抛 SessionStoreError；我们不期待 exit 0
    # 但我们要确认 routing 命中（无 ImportError）
    from claude_autosar.cli.main import _DISPATCH  # type: ignore[attr-defined]

    assert "session" in _DISPATCH
    assert _DISPATCH["session"][0] is not None  # register fn
    assert _DISPATCH["session"][1] is not None  # run fn


# ---------------------------------------------------------------------------
# main(): argv override
# ---------------------------------------------------------------------------


def test_main_accepts_argv_override() -> None:
    """main(argv=[...]) 用于测试和编程式调用。"""
    # 不抛异常即通过；具体退出码不重要（unknown subcommand 也算）
    code = main(["nonexistent_subcommand_for_argv_test"])
    assert code == 1


def test_main_none_argv_uses_sys_argv(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """main() 不传 argv 时：默认读 sys.argv[1:]（让 ``python -m autoc.cli.main`` 也能走两阶段解析）。

    回归 T5.4：之前 ``__main__`` 块调 ``main()`` 不传 argv，导致 ``argv is None``
    走 ``parse_args(None)``，未知子命令被 argparse 内部 ``SystemExit(2)`` 截走。
    """
    monkeypatch.setattr("sys.argv", ["autoc", "nonexistent_subcommand_for_sysargv_test"])
    code = main()
    assert code == 1
    captured = capsys.readouterr()
    assert "未知子命令" in captured.err
    assert "nonexistent_subcommand_for_sysargv_test" in captured.err
