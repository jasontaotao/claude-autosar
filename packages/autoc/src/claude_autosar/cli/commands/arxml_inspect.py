"""``autoc arxml-inspect`` 子命令 — Sprint 9.1 T9.1.4.

读单个 ``.arxml`` 文件 → 调用
:func:`claude_autosar.core.bsw.inspector.arxml_report.export_arxml_report`
渲染一页式 HTML 报告。

复用 inspector 内部 API；本文件只做 argparse + stderr 错误包装。
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
        "arxml-inspect",
        help="读 .arxml 单文件 → 渲染一页式 HTML 报告（IPdu / Signal / 关键参数）",
    )
    p.add_argument(
        "path",
        type=Path,
        help="输入 .arxml 文件路径",
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
    """执行 ``arxml-inspect``。返回 exit code。"""
    from claude_autosar.core.bsw.arxml_io import ARXMLError
    from claude_autosar.core.bsw.inspector.arxml_report import export_arxml_report

    src = Path(args.path)
    output = getattr(args, "output", None)
    try:
        written = export_arxml_report(src, output=output)
    except ARXMLError as e:
        print(
            json.dumps({"success": False, "error": f"ARXMLError: {e}"}),
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
        # 其他 ARXML 解析 / 类型错误兜底
        print(
            json.dumps({"success": False, "error": f"{type(e).__name__}: {e}"}),
            file=sys.stderr,
        )
        return 1

    print(
        json.dumps(
            {
                "success": True,
                "format": "arxml",
                "path": str(src),
                "report_path": str(written),
            }
        )
    )
    return 0
