"""``autoc init`` 子命令 — 配置 EB tresos 工程并复制 BSWMD 模板。

Sprint 8.E — T8.E.0a。交互流程（Rich Prompt.ask 三步）：
    1. 工程根目录（必填，校验 ``.prefs/`` 存在）
    2. tresos_home（可选，回车 = 平台默认）
    3. 是否复制 BSWMD（Y/n） — 如选 Y，遍历 ``<tresos_home>/BSWMD`` 下的 ``*_Bswmd.arxml``
       复制到 ``<project_root>/.autoc/bswmd/r22/<module>/``（mtime 未变则跳过；``--refresh-bswmd`` 强制重 copy）

工程验证：扫描 ``<project_root>/.prefs/`` 下的 ``*.xdm`` / ``*.arxml``，打印找到的模块列表。
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from autoc.core.config.project_config import (
    ProjectConfig,
    ProjectConfigError,
    default_tresos_home,
    load_yaml,
)

__all__ = ["register", "run"]

# BSWMD 副本目标子目录
_BSWMD_TARGET_SUBDIR = Path("autoc") / "bswmd" / "r22"

# .prefs/ 工程下 xdm / arxml 文件候选
_MODULE_XDM_GLOB = "*.xdm"
_MODULE_ARXML_GLOB = "*.arxml"


def register(subparsers: Any) -> None:
    """挂载到主 argparse subparsers。"""
    p = subparsers.add_parser(
        "init",
        help="配置 EB tresos 工程（写 .autoc/autoc.yaml + 复制 BSWMD）",
    )
    p.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="EB tresos 工程根目录（含 .prefs/）；缺省走交互问答",
    )
    p.add_argument(
        "--tresos-home",
        type=Path,
        default=None,
        help="EB tresos 安装目录；缺省走平台默认探测或交互问答",
    )
    p.add_argument(
        "--non-interactive",
        action="store_true",
        default=False,
        help="非交互模式：缺字段即报错（CI / 脚本友好）",
    )
    p.add_argument(
        "--no-bswmd",
        action="store_true",
        default=False,
        help="跳过 BSWMD 复制（仅写 autoc.yaml）",
    )
    p.add_argument(
        "--refresh-bswmd",
        action="store_true",
        default=False,
        help="强制重新复制 BSWMD（即便 mtime 未变）",
    )


def run(args: argparse.Namespace) -> int:
    """执行 ``autoc init``。返回 exit code。"""
    console = Console()
    try:
        return _run_init(
            console=console,
            project_root_arg=args.project_root,
            tresos_home_arg=args.tresos_home,
            non_interactive=bool(getattr(args, "non_interactive", False)),
            no_bswmd=bool(getattr(args, "no_bswmd", False)),
            refresh_bswmd=bool(getattr(args, "refresh_bswmd", False)),
        )
    except ProjectConfigError as e:
        console.print(f"[red]Error:[/red] {e}")
        return 1
    except KeyboardInterrupt:
        console.print("\n[yellow]已取消。[/yellow]")
        return 130


# =============================================================================
# 主流程
# =============================================================================


def _run_init(
    *,
    console: Console,
    project_root_arg: Path | None,
    tresos_home_arg: Path | None,
    non_interactive: bool,
    no_bswmd: bool,
    refresh_bswmd: bool,
) -> int:
    """主流程：问答 → 校验 → 写 yaml → 复制 BSWMD → 验证。"""
    # 1. 工程根目录
    if project_root_arg is not None:
        project_root = project_root_arg.expanduser().resolve()
    else:
        if non_interactive:
            raise ProjectConfigError(
                "非交互模式必须提供 --project-root。",
            )
        project_root = _ask_project_root(console)
    _validate_project_root(project_root, console)

    # 2. tresos_home
    if tresos_home_arg is not None:
        tresos_home: Path | None = tresos_home_arg.expanduser().resolve()
    elif non_interactive:
        tresos_home = default_tresos_home()
    else:
        tresos_home = _ask_tresos_home(console)
    _warn_if_tresos_home_missing(tresos_home, console)

    # 3. BSWMD 复制
    copy_bswmd = False
    if not no_bswmd and tresos_home is not None:
        if non_interactive:
            copy_bswmd = True
        else:
            answer = Prompt.ask(
                "复制完整 BSWMD 模板到 .autoc/bswmd/?",
                choices=["Y", "n"],
                default="Y",
                console=console,
            )
            copy_bswmd = answer == "Y"

    # 4. 写 .autoc/autoc.yaml
    config = ProjectConfig(
        project_root=project_root,
        tresos_home=tresos_home,
        bswmd_root=(project_root / _BSWMD_TARGET_SUBDIR).resolve(),
        extra_bswmd_paths=(),
    )
    config_path = project_root / ".autoc" / "autoc.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(config.to_yaml(), encoding="utf-8")
    console.print(f"[green]✓[/green] 已写入 {config_path}")

    # 5. 复制 BSWMD（如有）
    if copy_bswmd and tresos_home is not None:
        copied, skipped, errors = _copy_bswmd_files(
            tresos_home=tresos_home,
            target_root=config.bswmd_root,
            refresh=refresh_bswmd,
        )
        if errors:
            for err in errors:
                console.print(f"[yellow]! {err}[/yellow]")
        console.print(
            f"[green]✓[/green] 复制 {copied} 个 BSWMD 文件（跳过 {skipped}）",
        )

    # 6. 工程验证
    modules = _scan_project_modules(project_root)
    if modules:
        console.print(
            Panel(
                ", ".join(modules),
                title=f"工程验证通过: 找到 {len(modules)} 个模块",
                border_style="green",
            ),
        )
    else:
        console.print(
            "[yellow]! 未在 .prefs/ 找到任何 .xdm / .arxml 文件；"
            "请确认这是 EB tresos 工程目录。[/yellow]",
        )

    return 0


# =============================================================================
# 交互问答
# =============================================================================


def _ask_project_root(console: Console) -> Path:
    """Rich Prompt.ask 询问工程根目录。"""
    default = Path.cwd()
    while True:
        raw = Prompt.ask(
            "EB tresos 工程根目录",
            default=str(default),
            console=console,
        )
        path = Path(raw).expanduser().resolve()
        if path.is_dir():
            return path
        console.print(f"[red]目录不存在: {path}[/red]")


def _ask_tresos_home(console: Console) -> Path | None:
    """Rich Prompt.ask 询问 tresos_home（回车 = 平台默认）。"""
    default = default_tresos_home()
    default_str = str(default) if default is not None else ""
    raw = Prompt.ask(
        "EB tresos 安装目录 (回车用默认)",
        default=default_str,
        console=console,
        show_default=bool(default_str),
    )
    if not raw.strip():
        return default
    path = Path(raw).expanduser().resolve()
    return path


# =============================================================================
# 校验
# =============================================================================


def _validate_project_root(project_root: Path, console: Console) -> None:
    """校验工程根目录是否含 ``.prefs/``；缺失给警告（不强制失败）。"""
    prefs = project_root / ".prefs"
    if not prefs.is_dir():
        console.print(
            f"[yellow]! 警告: {prefs} 不存在；可能不是 EB tresos 工程。[/yellow]",
        )


def _warn_if_tresos_home_missing(tresos_home: Path | None, console: Console) -> None:
    """tresos_home 缺失时给警告（D 部分降级 — 仍可用 ``.prefs/`` 值文件）。"""
    if tresos_home is None or not tresos_home.is_dir():
        console.print(
            "[yellow]! 警告: tresos_home 不可用；将跳过 BSWMD 复制。"
            "工程验证仍可工作（仅读 .prefs/ 值文件）。[/yellow]",
        )


# =============================================================================
# BSWMD 复制
# =============================================================================


def _copy_bswmd_files(
    *,
    tresos_home: Path,
    target_root: Path,
    refresh: bool,
) -> tuple[int, int, list[str]]:
    """从 ``<tresos_home>/BSWMD`` 复制所有 ``*_Bswmd.arxml`` 到 ``<target_root>/<module>/``。

    Returns:
        (copied_count, skipped_count, errors)
    """
    src_root = tresos_home / "BSWMD"
    if not src_root.is_dir():
        return 0, 0, [f"未找到 BSWMD 源目录: {src_root}"]

    # 候选：<src_root>/**/*_Bswmd.arxml
    sources: list[Path] = sorted(src_root.rglob("*_Bswmd.arxml"))
    if not sources:
        return 0, 0, [f"未在 {src_root} 下找到 *_Bswmd.arxml 文件"]

    target_root.mkdir(parents=True, exist_ok=True)

    copied = 0
    skipped = 0
    errors: list[str] = []

    def _copy_one(src: Path) -> tuple[bool, str | None]:
        # 模块名：<Module>_Bswmd.arxml -> <Module>
        module = src.stem.replace("_Bswmd", "")
        dst = target_root / module / src.name
        if dst.exists() and not refresh:
            try:
                if dst.stat().st_mtime_ns >= src.stat().st_mtime_ns:
                    return False, None
            except OSError:
                pass
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        except OSError as e:
            return False, f"复制失败: {src} -> {dst}: {e}"
        return True, None

    with ThreadPoolExecutor(max_workers=4) as ex:
        for was_copied, err in ex.map(_copy_one, sources):
            if err is not None:
                errors.append(err)
            elif was_copied:
                copied += 1
            else:
                skipped += 1
    return copied, skipped, errors


# =============================================================================
# 工程验证
# =============================================================================


def _scan_project_modules(project_root: Path) -> list[str]:
    """扫描 ``<project_root>/.prefs/`` 下的 xdm / arxml 文件名（去后缀）。"""
    prefs = project_root / ".prefs"
    if not prefs.is_dir():
        return []
    seen: set[str] = set()
    for pattern in (_MODULE_XDM_GLOB, _MODULE_ARXML_GLOB):
        for p in prefs.glob(pattern):
            stem = p.stem
            # 去除常见后缀（Mcu_Cfg.xdm -> Mcu）
            for suffix in ("_Cfg", "_cfg"):
                if stem.endswith(suffix):
                    stem = stem[: -len(suffix)]
                    break
            seen.add(stem)
    return sorted(seen)


# =============================================================================
# 内部辅助（test 用）
# =============================================================================


def _read_existing_config(project_root: Path) -> dict[str, object]:
    """读已存在的 ``.autoc/autoc.yaml``（供 re-init 检测）。"""
    return load_yaml(project_root / ".autoc" / "autoc.yaml")


__all__ = [
    "register",
    "run",
    "_ask_project_root",
    "_ask_tresos_home",
    "_copy_bswmd_files",
    "_scan_project_modules",
    "_read_existing_config",
]
