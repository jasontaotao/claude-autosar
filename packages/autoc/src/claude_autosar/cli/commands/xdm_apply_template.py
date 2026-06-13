"""``autoc xdm-apply-template`` 子命令 — Sprint 9.2 T9.2-γ.

读 ``.xdm`` 当前文件 + 模板 ``.xdm`` → 计算 template diff（add /
modify / delete）→ 可选 dry-run 或 ``--apply`` 写回。

XDM 端走 :mod:`claude_autosar.core.bsw.templates.xdm_diff` 的
:func:`diff_xdm_templates`；apply 走 :func:`apply_template_diff`（由 T9.2.1
并发写）。module_name 自动从 ``.xdm`` 根探测；未指定时取第一个
``<d:chc type="AR-ELEMENT">`` 的 ``name``。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, cast

__all__ = ["register", "run"]


def register(subparsers: Any) -> None:
    """挂载到主 argparse subparsers。"""
    p = subparsers.add_parser(
        "xdm-apply-template",
        help="读 .xdm current + template → diff（add/modify/delete）→ --apply 写回",
    )
    p.add_argument(
        "path",
        type=Path,
        help="输入 .xdm（当前）文件路径",
    )
    p.add_argument(
        "template",
        type=Path,
        help="模板 .xdm（期望）文件路径",
    )
    p.add_argument(
        "-o",
        "--output",
        dest="output",
        type=Path,
        default=None,
        help="输出 HTML 报告路径；缺省 = 不输出",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="真正写回；缺省 = dry-run（只算 diff 不改文件）",
    )
    p.add_argument(
        "--project",
        type=str,
        default=".",
        help="工程根目录（默认 cwd；保留 R6 路径防御）",
    )


def build_parser() -> argparse.ArgumentParser:
    """为单元测试提供独立 parser。"""
    parser = argparse.ArgumentParser(prog="autoc")
    sub = parser.add_subparsers(dest="command", required=False)
    register(sub)
    return parser


def _render_diff_html(
    path: Path,
    template: Path,
    diff_rows: tuple[tuple[str, str, str, str, str], ...],
) -> str:
    """渲染最简 diff HTML 报告（路径 / op / current / template）。"""
    css = """
body { font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
       margin: 2em; line-height: 1.5; color: #1a1a1a; }
h1 { border-bottom: 2px solid #444; padding-bottom: 0.3em; }
table { border-collapse: collapse; margin: 1em 0; width: 100%; }
th, td { border: 1px solid #ccc; padding: 0.4em 0.6em; text-align: left;
         vertical-align: top; font-family: ui-monospace, Menlo, Consolas, monospace;
         font-size: 0.9em; }
th { background: #f0f0f0; }
tr:nth-child(even) td { background: #fafafa; }
.op-add { color: #22863a; font-weight: bold; }
.op-modify { color: #b08800; font-weight: bold; }
.op-delete { color: #b31d28; font-weight: bold; }
.summary-box { background: #fffbe6; border: 1px solid #ffe58f;
               padding: 0.6em 0.9em; border-radius: 4px; margin: 0.5em 0; }
""".strip()
    rows_html = "\n".join(
        f"<tr><td>{path_e}</td><td class='op-{op}'>{op}</td>"
        f"<td>{cur or ''}</td><td>{tpl or ''}</td><td>{note}</td></tr>"
        for (path_e, op, cur, tpl, note) in diff_rows
    )
    return (
        f"<!DOCTYPE html>\n<html><head><meta charset='utf-8'>"
        f"<title>XDM Template Diff</title><style>{css}</style></head>\n"
        f"<body>\n<h1>XDM Template Diff</h1>\n"
        f"<div class='summary-box'><strong>current:</strong> {path} &nbsp; "
        f"<strong>template:</strong> {template}</div>\n"
        f"<table><thead><tr><th>path</th><th>op</th><th>current</th>"
        f"<th>template</th><th>note</th></tr></thead>"
        f"<tbody>\n{rows_html}\n</tbody></table>\n"
        f"</body></html>\n"
    )


def _diff_to_rows(
    diffs: Any,
) -> tuple[tuple[str, str, str, str, str], ...]:
    """``TemplateDiffResult.diffs`` → HTML table 行。"""
    rows: list[tuple[str, str, str, str, str]] = []
    for d in diffs:
        cur_raw = getattr(d.current, "raw", "") if d.current is not None else ""
        tpl_raw = getattr(d.template, "raw", "") if d.template is not None else ""
        rows.append((d.path, d.op, cur_raw, tpl_raw, ""))
    return tuple(rows)


def run(args: argparse.Namespace) -> int:
    """执行 ``xdm-apply-template``。返回 exit code。"""
    from claude_autosar.core.bsw.dispatcher import (
        DispatcherError,
        FormatMismatchError,
        UnknownFormatError,
        read as dispatcher_read,
    )
    from claude_autosar.core.bsw.io.datamodel2_io import DataModel2Error
    # 延迟 import：apply.py 由 T9.2.1 并发写
    from claude_autosar.core.bsw.templates.apply import (
        ApplyMode,
        apply_template_diff,
    )
    from claude_autosar.core.bsw.templates.xdm_value import (
        XDMValueError,
        load_xdm_module,
    )
    from claude_autosar.core.bsw.templates.xdm_diff import diff_xdm_templates

    src = Path(args.path).resolve()
    tpl = Path(args.template).resolve()
    output = getattr(args, "output", None)
    do_apply = bool(getattr(args, "apply", False))

    # 1) 用 dispatcher 验证两份 .xdm 都能被解析（探测格式 + 兼容）
    try:
        current_doc = dispatcher_read(src, expected_format="xdm")
    except (FileNotFoundError, OSError) as e:
        print(
            json.dumps({"success": False, "error": f"{type(e).__name__}: {e}"}),
            file=sys.stderr,
        )
        return 1
    except (DataModel2Error, DispatcherError, UnknownFormatError,
            FormatMismatchError) as e:
        print(
            json.dumps({"success": False, "error": f"{type(e).__name__}: {e}"}),
            file=sys.stderr,
        )
        return 1

    try:
        template_doc = dispatcher_read(tpl, expected_format="xdm")
    except (FileNotFoundError, OSError) as e:
        print(
            json.dumps({"success": False, "error": f"{type(e).__name__}: {e}"}),
            file=sys.stderr,
        )
        return 1
    except (DataModel2Error, DispatcherError, UnknownFormatError,
            FormatMismatchError) as e:
        print(
            json.dumps({"success": False, "error": f"{type(e).__name__}: {e}"}),
            file=sys.stderr,
        )
        return 1

    # 2) 加载两个 XDMModule（module_name 需对齐；current + template 必须是
    #    同一模块；如果 path 不一致走 XDMValueError）
    module_name = _detect_module_name(current_doc) or _detect_module_name(
        template_doc
    )
    if not module_name:
        print(
            json.dumps(
                {
                    "success": False,
                    "error": "XDMValueError: no <d:chc type=AR-ELEMENT> found "
                    "in current/template",
                }
            ),
            file=sys.stderr,
        )
        return 1

    try:
        current_mod = load_xdm_module(src, module_name)
    except XDMValueError as e:
        print(
            json.dumps({"success": False, "error": f"XDMValueError: {e}"}),
            file=sys.stderr,
        )
        return 1
    try:
        template_mod = load_xdm_module(tpl, module_name)
    except XDMValueError as e:
        print(
            json.dumps({"success": False, "error": f"XDMValueError: {e}"}),
            file=sys.stderr,
        )
        return 1

    # 3) diff（XDM 端是纯函数 diff_xdm_templates）
    try:
        diff_result = diff_xdm_templates(current_mod, template_mod)
    except (ValueError, TypeError, AttributeError) as e:
        print(
            json.dumps({"success": False, "error": f"{type(e).__name__}: {e}"}),
            file=sys.stderr,
        )
        return 1

    diffs = diff_result.diffs
    adds = diff_result.adds
    modifies = diff_result.modifies
    deletes = diff_result.deletes

    # 4) apply
    mode = ApplyMode.APPLY if do_apply else ApplyMode.DRY_RUN
    try:
        apply_result = apply_template_diff(src, diff_result, mode=mode)
    except (OSError, FileNotFoundError) as e:
        print(
            json.dumps({"success": False, "error": f"{type(e).__name__}: {e}"}),
            file=sys.stderr,
        )
        return 1
    except (ValueError, TypeError) as e:
        print(
            json.dumps({"success": False, "error": f"{type(e).__name__}: {e}"}),
            file=sys.stderr,
        )
        return 1

    # 5) 可选 HTML 报告
    if output is not None:
        try:
            html = _render_diff_html(src, tpl, _diff_to_rows(diffs))
            out_path = Path(output).resolve()
            out_path.write_text(html, encoding="utf-8")
        except OSError as e:
            print(
                json.dumps({"success": False, "error": f"OSError: {e}"}),
                file=sys.stderr,
            )
            return 1

    # 6) stdout JSON
    print(
        json.dumps(
            {
                "success": True,
                "format": "xdm",
                "mode": str(mode),
                "path": str(src),
                "template": str(tpl),
                "module_name": module_name,
                "diff_count": len(diffs),
                "adds": len(adds),
                "modifies": len(modifies),
                "deletes": len(deletes),
                "applied": bool(do_apply),
                "report_path": str(Path(output).resolve()) if output else None,
                "result": _apply_result_to_dict(apply_result),
            }
        )
    )
    return 0


def _detect_module_name(loaded_doc: Any) -> str | None:
    """从 dispatcher 加载的 XDM tree 找第一个 ``<d:chc type="AR-ELEMENT">``。

    用 lxml xpath 直接查；如果 tree 不是 lxml 树或没找到，返回 ``None``。
    """
    try:
        tree = loaded_doc.tree
        root = tree.getroot() if hasattr(tree, "getroot") else tree
        ns = {"d": "http://www.tresos.de/_projects/DataModel2/06/data.xsd"}
        elems = root.xpath(
            './/d:chc[@type="AR-ELEMENT"]', namespaces=ns
        )
    except Exception:  # noqa: BLE001 - 任何 xpath / attribute 异常都退回 None
        return None
    if not elems:
        return None
    name = elems[0].get("name")
    return name or None


def _apply_result_to_dict(result: Any) -> dict[str, Any]:
    """把 ``ApplyResult`` 缩成 dict（避免硬依赖 dataclass field 顺序）。"""
    try:
        from dataclasses import asdict, is_dataclass

        if is_dataclass(result) and not isinstance(result, type):
            return asdict(cast(Any, result))  # mypy: asdict 不接受 type[DataclassInstance]
    except Exception:  # noqa: BLE001
        pass
    try:
        return dict(vars(result))
    except TypeError:
        return {}
