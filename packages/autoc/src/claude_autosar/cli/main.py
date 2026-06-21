"""AutoC 命令行入口（Sprint 5 — T5.1 dispatch 表 + 全局 --verbose/--no-color）。"""

from __future__ import annotations

import argparse
import importlib
from collections.abc import Callable, Sequence
from pathlib import Path
import sys
from typing import Any

try:
    from importlib.metadata import version as _get_version
    __version__ = _get_version("claude-autosar")
except Exception:
    __version__ = "0.0.0-dev"

# ---------------------------------------------------------------------------
# Lazy command module registry
# ---------------------------------------------------------------------------
# Maps subcommand name -> fully qualified module path.  Modules are imported
# on demand so that lightweight commands like ``autoc --version`` avoid
# loading heavy dependencies (lxml, etc.) entirely.

_COMMAND_MODULES: dict[str, str] = {
    "eb": "claude_autosar.cli.commands.eb",
    "davinci": "claude_autosar.cli.commands.davinci",
    "session": "claude_autosar.cli.commands.session",
    "log": "claude_autosar.cli.commands.log",
    "export": "claude_autosar.cli.commands.export",
    "init": "claude_autosar.cli.commands.init",
    "arxml-inspect": "claude_autosar.cli.commands.arxml_inspect",
    "xdm-inspect": "claude_autosar.cli.commands.xdm_inspect",
    "bsw-inspect": "claude_autosar.cli.commands.bsw_inspect",
    "lint": "claude_autosar.cli.commands.lint",
    "bsw-verify": "claude_autosar.cli.commands.bsw_verify",
    "arxml-apply-template": "claude_autosar.cli.commands.arxml_apply_template",
    "xdm-apply-template": "claude_autosar.cli.commands.xdm_apply_template",
}


class _LazyDispatch(dict):  # type: ignore[type-arg]
    """Dispatch table that lazily imports command modules on first access.

    Backward-compatible with the old ``_DISPATCH`` dict — existing code that
    does ``"session" in _DISPATCH`` or ``_DISPATCH[name]`` continues to work
    without changes.  ``__contains__`` checks ``_COMMAND_MODULES`` (no
    import); ``__getitem__`` imports only the requested module;
    ``items()`` / ``__iter__`` bulk-load everything (needed by
    ``build_parser`` iteration).
    """

    def __contains__(self, key: object) -> bool:  # type: ignore[override]
        return key in _COMMAND_MODULES

    def __getitem__(self, key: str) -> tuple[Callable[[Any], None], Callable[[argparse.Namespace], int]]:
        if key not in dict.keys(self):
            if key not in _COMMAND_MODULES:
                raise KeyError(key)
            mod = importlib.import_module(_COMMAND_MODULES[key])
            dict.__setitem__(self, key, (mod.register, mod.run))
        return dict.__getitem__(self, key)

    def _load_all(self) -> None:
        """Import every command module (used by iteration / build_parser).

        If any import fails, roll back already-loaded entries so a
        subsequent call can retry from a clean state.
        """
        if not dict.__len__(self):
            loaded: list[str] = []
            try:
                for name, path in _COMMAND_MODULES.items():
                    mod = importlib.import_module(path)
                    dict.__setitem__(self, name, (mod.register, mod.run))
                    loaded.append(name)
            except Exception:
                # rollback: remove partially loaded entries
                for n in loaded:
                    dict.__delitem__(self, n)
                raise

    def items(self):  # type: ignore[override]
        self._load_all()
        return dict.items(self)

    def keys(self):  # type: ignore[override]
        return dict.keys(_COMMAND_MODULES)  # noqa: PLC2801

    def __iter__(self):  # type: ignore[override]
        return iter(_COMMAND_MODULES)

    def __len__(self) -> int:  # type: ignore[override]
        return len(_COMMAND_MODULES)


# Backward-compatible dispatch table (lazy-loaded).
_DISPATCH: dict[str, tuple[Callable[[Any], None], Callable[[argparse.Namespace], int]]] = _LazyDispatch()


# ---------------------------------------------------------------------------
# Registration / parser
# ---------------------------------------------------------------------------


def _register_command(subparsers: Any, cmd_name: str, module_path: str) -> None:
    """Register a command module into the parser.

    Module must expose ``register(subparsers)`` and ``run(args) -> int``.
    The module is imported on demand.
    """
    mod = importlib.import_module(module_path)
    mod.register(subparsers)


def build_parser(active_command: str | None = None) -> argparse.ArgumentParser:
    """构建 argparse 解析器。

    Parameters
    ----------
    active_command:
        If given, only register the subparser for this command (faster
        startup for single-command invocations).  If ``None``, register
        all subcommands (needed for ``--help``).
    """
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
    for cmd_name, module_path in _COMMAND_MODULES.items():
        if active_command is None or cmd_name == active_command:
            _register_command(subparsers, cmd_name, module_path)
    return parser


# ---------------------------------------------------------------------------
# Flag / positional parsing helpers
# ---------------------------------------------------------------------------


_VALUE_FLAGS: frozenset[str] = frozenset({
    "--project",
    "--tresos-home",
    "--module",
    "--param",
    "--adapter",
    "-o",
    "--output",
})


def _first_positional(argv: Sequence[str]) -> str | None:
    """返回 argv 中第一个非 flag / 非 flag-value 的位置 token。

    用于两阶段解析：先在白名单里查这个 token，决定走完整 parser 还是直接报
    "未知子命令"。简单启发式 — 不解析引号、不处理 ``--`` 分隔、不区分
    ``--key=value`` 与 ``--key value``；但对 autoc 现有的子命令而言足够。
    """
    skip_next = False
    for token in argv:
        if skip_next:
            skip_next = False
            continue
        if token.startswith("-"):
            # ``--key=value`` 形式：值在同一个 token 里，无需跳过下一个
            if "=" in token:
                continue
            # 已知需要值的 flag → 跳过下一个 token
            if token in _VALUE_FLAGS:
                skip_next = True
                continue
            # 其他 flag（--verbose, --help, -v 等）→ 不跳过
            continue
        return token
    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """主入口。"""
    argv_list: list[str] = sys.argv[1:] if argv is None else list(argv)

    # Fast path: --version 不需要加载任何命令模块（避免 lxml 等重型依赖）
    if "--version" in argv_list:
        print(f"claude-autosar {__version__}")
        raise SystemExit(0)

    # 两阶段解析：先扫第一个位置 token，命中白名单再走完整 parser。
    # 这样避开 argparse 内部对未知子命令抛 SystemExit(2) 的行为，
    # 让我们能输出自定义 "未知子命令" 提示并 exit 1。
    first = _first_positional(argv_list)
    if (
        first is not None
        and first not in _COMMAND_MODULES
        and first
        not in {
            "help",
        }
    ):
        print(f"未知子命令: {first}", file=sys.stderr)
        return 1

    # Only register the subparser for the requested command (faster startup).
    active = first if first in _COMMAND_MODULES else None
    parser = build_parser(active_command=active)
    args = parser.parse_args(argv_list)
    if args.command is None:
        # 无子命令：占位（保留 Sprint 3 前的行为）
        print(f"claude-autosar {__version__}（开发中）", file=sys.stderr)
        print(f"工作目录: {args.project or Path.cwd()}", file=sys.stderr)
        return 0

    if args.command in _COMMAND_MODULES:
        mod = importlib.import_module(_COMMAND_MODULES[args.command])
        return mod.run(args)

    print(f"未知子命令: {args.command}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
