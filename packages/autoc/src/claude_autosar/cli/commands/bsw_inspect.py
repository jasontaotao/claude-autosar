"""``autoc bsw-inspect`` 子命令 — Sprint 9.1 T9.1.4.

dispatcher wrapper：自动按文件根 namespace 选 arxml / xdm 渲染器。

不强制要求文件后缀是 ``.arxml`` / ``.xdm``；通过
:func:`claude_autosar.core.bsw.dispatcher.detect_format` 探测，然后路由
到对应 inspector 的 :func:`export_arxml_report` /
:func:`export_xdm_report`。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

__all__ = ["register", "run"]


def register(subparsers: Any) -> None:
    """挂载到主 argparse subparsers。"""
    p = subparsers.add_parser(
        "bsw-inspect",
        help="dispatcher：自动按 namespace 选 arxml / xdm 渲染 HTML 报告",
    )
    p.add_argument(
        "path",
        type=Path,
        help="输入文件路径（按根 xmlns 自动选 arxml / xdm，不依赖后缀）",
    )
    p.add_argument(
        "-o",
        "--output",
        dest="output",
        type=Path,
        default=None,
        help="输出 HTML 路径；缺省 = <input>.report.html",
    )
    p.add_argument(
        "--lint",
        action="store_true",
        default=False,
        help="Enable lint check (Sprint 9.4 M4)",
    )


def build_parser() -> argparse.ArgumentParser:
    """为单元测试提供独立 parser。"""
    parser = argparse.ArgumentParser(prog="autoc")
    sub = parser.add_subparsers(dest="command", required=False)
    register(sub)
    return parser


def run(args: argparse.Namespace) -> int:
    """执行 ``bsw-inspect``。返回 exit code。"""
    from claude_autosar.core.bsw.dispatcher import (
        DispatcherError,
        UnknownFormatError,
        detect_format,
    )
    from claude_autosar.core.bsw.inspector.arxml_report import export_arxml_report
    from claude_autosar.core.bsw.inspector.xdm_report import export_xdm_report

    src = Path(args.path)
    output = getattr(args, "output", None)

    # 1) 探测格式（dispatcher）
    try:
        fmt = detect_format(src)
    except FileNotFoundError as e:
        print(
            json.dumps({"success": False, "error": f"FileNotFoundError: {e}"}),
            file=sys.stderr,
        )
        return 1
    except UnknownFormatError as e:
        print(
            json.dumps({"success": False, "error": f"UnknownFormatError: {e}"}),
            file=sys.stderr,
        )
        return 1
    except DispatcherError as e:
        print(
            json.dumps({"success": False, "error": f"{type(e).__name__}: {e}"}),
            file=sys.stderr,
        )
        return 1

    # 2) 按格式路由到对应 inspector
    try:
        if fmt == "arxml":
            written = export_arxml_report(src, output=output)
        else:  # fmt == "xdm"
            written = export_xdm_report(src, output=output)
    except FileNotFoundError as e:
        print(
            json.dumps({"success": False, "error": f"FileNotFoundError: {e}"}),
            file=sys.stderr,
        )
        return 1
    except OSError as e:
        print(
            json.dumps({"success": False, "error": f"OSError: {e}"}),
            file=sys.stderr,
        )
        return 1
    except (ValueError, TypeError) as e:
        print(
            json.dumps({"success": False, "error": f"{type(e).__name__}: {e}"}),
            file=sys.stderr,
        )
        return 1

    print(
        json.dumps(
            {
                "success": True,
                "format": fmt,
                "path": str(src),
                "report_path": str(written),
            }
        )
    )
    return 0
