"""AutoC 命令行入口（Sprint 4 — 新增 session / log / export 子命令）。"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

__version__ = "0.1.0"


def build_parser() -> argparse.ArgumentParser:
    """构建 argparse 解析器。"""
    parser = argparse.ArgumentParser(
        prog="autoc",
        description="AutoC - AUTOSAR BSW AI 配置助手",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"autoc {__version__}",
    )
    parser.add_argument(
        "--project",
        type=Path,
        default=None,
        help="BSW 工程根目录（默认：当前工作目录）",
    )
    # Sprint 3 — T3.5/T3.6：注册 eb / davinci 子命令
    # Sprint 4 — T4.5a/b/c：注册 session / log / export 子命令
    from autoc.cli.commands import davinci, eb, export, log, session  # noqa: PLC0415

    subparsers = parser.add_subparsers(dest="command", required=False)
    eb.register(subparsers)
    davinci.register(subparsers)
    session.register(subparsers)
    log.register(subparsers)
    export.register(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    """主入口。"""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        # 无子命令：占位（保留 Sprint 3 前的行为）
        print(f"autoc {__version__}（开发中）", file=sys.stderr)
        print(f"工作目录: {args.project or Path.cwd()}", file=sys.stderr)
        return 0

    # Sprint 3 — T3.5/T3.6：dispatch 到子命令
    if args.command == "eb":
        from autoc.cli.commands.eb import run as eb_run  # noqa: PLC0415

        return eb_run(args)
    if args.command == "davinci":
        from autoc.cli.commands.davinci import run as davinci_run  # noqa: PLC0415

        return davinci_run(args)

    # Sprint 4 — T4.5a/b/c：dispatch session / log / export
    if args.command == "session":
        from autoc.cli.commands.session import run as session_run  # noqa: PLC0415

        return session_run(args)
    if args.command == "log":
        from autoc.cli.commands.log import run as log_run  # noqa: PLC0415

        return log_run(args)
    if args.command == "export":
        from autoc.cli.commands.export import run as export_run  # noqa: PLC0415

        return export_run(args)

    print(f"未知子命令: {args.command}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
