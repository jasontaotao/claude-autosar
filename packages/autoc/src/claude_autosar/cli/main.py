"""AutoC 命令行入口（Sprint 5 — T5.1 dispatch 表 + 全局 --verbose/--no-color）。"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path
import sys
from typing import Any

__version__ = "0.3.0"

# Dispatch table: subcommand name -> (register_fn, run_fn).
# Driven by tests/unit/test_cli_main.py::_DISPATCH lookup.
_DISPATCH: dict[str, tuple[Callable[[Any], None], Callable[[argparse.Namespace], int]]] = {}


def _register_command(name: str, module: Any) -> None:
    """Register a command module into the dispatch table.

    Module must expose ``register(subparsers)`` and ``run(args) -> int``.
    """
    _DISPATCH[name] = (module.register, module.run)


# Importing command modules and registering into the dispatch table.
# Imported at module load (not lazily inside main()) so that callers/tests
# can introspect _DISPATCH.
from claude_autosar.cli.commands import (  # noqa: E402, PLC0415
    arxml_apply_template,
    arxml_inspect,
    bsw_inspect,
    bsw_verify,
    davinci,
    eb,
    export,
    init,
    lint,
    log,
    session,
    xdm_apply_template,
    xdm_inspect,
)

_register_command("eb", eb)
_register_command("davinci", davinci)
_register_command("session", session)
_register_command("log", log)
_register_command("export", export)
_register_command("init", init)
_register_command("arxml-inspect", arxml_inspect)
_register_command("xdm-inspect", xdm_inspect)
_register_command("bsw-inspect", bsw_inspect)
_register_command("lint", lint)
_register_command("bsw-verify", bsw_verify)
_register_command("arxml-apply-template", arxml_apply_template)
_register_command("xdm-apply-template", xdm_apply_template)


def build_parser() -> argparse.ArgumentParser:
    """构建 argparse 解析器。"""
    parser = argparse.ArgumentParser(
        prog="autoc",
        description="AutoC - AUTOSAR BSW AI 配置助手",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"claude-autosar {__version__}",
    )
    parser.add_argument(
        "--project",
        type=Path,
        default=None,
        help="BSW 工程根目录（默认：当前工作目录）",
    )
    # Sprint 5 — T5.1：全局 --verbose / --no-color，给 repl_skin 准备钩子
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="输出调试级日志（repl_skin 用）",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        default=False,
        help="禁用 ANSI 颜色（CI / 管道友好）",
    )

    subparsers = parser.add_subparsers(dest="command", required=False)
    for _name, (register_fn, _run_fn) in _DISPATCH.items():
        register_fn(subparsers)
    return parser


def _first_positional(argv: Sequence[str]) -> str | None:
    """返回 argv 中第一个非 flag / 非 flag-value 的位置 token。

    用于两阶段解析：先在白名单里查这个 token，决定走完整 parser 还是直接报
    "未知子命令"。简单启发式 — 不解析引号、不处理 ``--`` 分隔、不区分
    ``--key=value`` 与 ``--key value``；但对 autoc 现有的 5 个子命令而言足够。
    """
    skip_next = False
    for token in argv:
        if skip_next:
            skip_next = False
            continue
        if token.startswith("-"):
            # ``--key value`` 形式：value 不是 flag，要跳过当前 flag
            if "=" not in token and len(token) > 2 and not token.startswith("--"):
                # 短 flag 复合 (-abc) 不再展开，单字符短 flag 假定无值
                continue
            if "=" not in token:
                # 单 --long flag：尝试判断它是否 "需要值"
                # 安全起见：skip_next=True 让下一个 token 也跳过
                skip_next = True
            continue
        return token
    return None


def main(argv: list[str] | None = None) -> int:
    """主入口。"""
    argv_list: list[str] = sys.argv[1:] if argv is None else list(argv)
    # 两阶段解析：先扫第一个位置 token，命中白名单再走完整 parser。
    # 这样避开 argparse 内部对未知子命令抛 SystemExit(2) 的行为，
    # 让我们能输出自定义 "未知子命令" 提示并 exit 1。
    first = _first_positional(argv_list)
    if (
        first is not None
        and first not in _DISPATCH
        and first
        not in {
            "help",
        }
    ):
        print(f"未知子命令: {first}", file=sys.stderr)
        return 1

    parser = build_parser()
    args = parser.parse_args(argv_list)
    if args.command is None:
        # 无子命令：占位（保留 Sprint 3 前的行为）
        print(f"claude-autosar {__version__}（开发中）", file=sys.stderr)
        print(f"工作目录: {args.project or Path.cwd()}", file=sys.stderr)
        return 0

    if args.command in _DISPATCH:
        _, run_fn = _DISPATCH[args.command]
        return run_fn(args)

    print(f"未知子命令: {args.command}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
