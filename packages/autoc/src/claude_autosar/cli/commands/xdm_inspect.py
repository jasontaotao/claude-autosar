"""``autoc xdm-inspect`` 子命令 — Sprint 9.1 T9.1.4.

读单个 ``.xdm`` (DataModel2) 文件 → 调用
:func:`claude_autosar.core.bsw.inspector.xdm_report.export_xdm_report`
渲染一页式 HTML 报告。

复用 inspector 内部 API；本文件只做 argparse + stderr 错误包装。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from claude_autosar.core.bsw.io.datamodel2_io import DataModel2Error
from claude_autosar.core.bsw.inspector.xdm_report import export_xdm_report

__all__ = ["register", "run"]


def register(subparsers: Any) -> None:
    """挂载到主 argparse subparsers。"""
    p = subparsers.add_parser(
        "xdm-inspect",
        help="读 .xdm (DataModel2) 单文件 → 渲染一页式 HTML 报告（容器 / 叶子参数）",
    )
    p.add_argument(
        "path",
        type=Path,
        help="输入 .xdm 文件路径",
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
    """执行 ``xdm-inspect``。返回 exit code。"""
    src = Path(args.path)
    output = getattr(args, "output", None)
    try:
        written = export_xdm_report(src, output=output)
    except DataModel2Error as e:
        print(
            json.dumps({"success": False, "error": f"DataModel2Error: {e}"}),
            file=sys.stderr,
        )
        return 1
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
                "format": "xdm",
                "path": str(src),
                "report_path": str(written),
            }
        )
    )
    return 0
