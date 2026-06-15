"""``autoc arxml-apply-template`` 子命令 — Sprint 9.2 T9.2-γ.

读 ``.arxml`` 当前文件 + 模板 ``.arxml`` → 计算 template diff（add /
modify / delete）→ 可选 dry-run 或 ``--apply`` 写回。

复用 :mod:`claude_autosar.core.bsw.templates` 下的
:func:`diff_arxml_templates` 与 :func:`apply_template_diff`；本文件只做
argparse + 路径解析 + stderr 错误包装 + 可选 HTML 报告输出。

注：``apply_template_diff`` / ``ApplyMode`` 由并发任务 T9.2.1（apply.py）
实现，本文件延迟 import 以保留切片独立性。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, cast

__all__ = ["register", "run"]


def _detect_arxml_module_name(path: Path) -> str | None:
    """从 .arxml 文件取顶层 ECUC-MODULE-CONFIGURATION-VALUES 的 SHORT-NAME。

    任意失败（XML 畸形 / 无 module）一律返回 ``None``；caller 决定 fallback。
    """
    try:
        from lxml import etree

        from claude_autosar.core.bsw.arxml_io import detect_namespaces

        nsmap = detect_namespaces(path)
        ar_uri = nsmap.get("ar")
        if not ar_uri:
            return None
        tree = etree.parse(str(path))
        root = tree.getroot()
        modules = root.xpath(
            "//ar:ECUC-MODULE-CONFIGURATION-VALUES",
            namespaces={"ar": ar_uri},
        )
    except Exception:  # noqa: BLE001 - 任意 I/O / xpath 异常都返回 None
        return None
    if not modules:
        return None
    for m in modules:
        sn = m.find(f"{{{ar_uri}}}SHORT-NAME")
        if sn is not None and sn.text:
            return cast("str | None", sn.text)
    return None


def register(subparsers: Any) -> None:
    """挂载到主 argparse subparsers。"""
    p = subparsers.add_parser(
        "arxml-apply-template",
        help="读 .arxml current + template → diff（add/modify/delete）→ --apply 写回",
    )
    p.add_argument(
        "path",
        type=Path,
        help="输入 .arxml（当前）文件路径",
    )
    p.add_argument(
        "template",
        type=Path,
        help="模板 .arxml（期望）文件路径",
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
    """渲染最简 diff HTML 报告（路径 / op / current / template）。

    ``diff_rows`` = ``(path, op, current_raw, template_raw, note)`` 元组列表。
    自包含 inline CSS（复用 inspector summary-box 风格）。
    """
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
        f"<title>ARXML Template Diff</title><style>{css}</style></head>\n"
        f"<body>\n<h1>ARXML Template Diff</h1>\n"
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
    """``TemplateDiffResult.diffs`` → HTML table 行。

    每个 ``TemplateDiff`` 取出 ``path / op / current.raw / template.raw``；
    ``current`` 或 ``template`` 为 ``None`` 时对应 add / delete。
    """
    rows: list[tuple[str, str, str, str, str]] = []
    for d in diffs:
        cur_raw = getattr(d.current, "raw", "") if d.current is not None else ""
        tpl_raw = getattr(d.template, "raw", "") if d.template is not None else ""
        rows.append((d.path, d.op, cur_raw, tpl_raw, ""))
    return tuple(rows)


def run(args: argparse.Namespace) -> int:
    """执行 ``arxml-apply-template``。返回 exit code。"""
    from claude_autosar.core.bsw.arxml_io import ARXMLError
    from claude_autosar.core.bsw.dispatcher import (
        DispatcherError,
        FormatMismatchError,
        UnknownFormatError,
    )
    from claude_autosar.core.bsw.dispatcher import read as dispatcher_read
    from claude_autosar.core.bsw.ecuc import load_module as ecuc_load_module

    # 延迟 import：apply.py 由 T9.2.1 并发写
    from claude_autosar.core.bsw.templates.apply import (
        ApplyMode,
        apply_template_diff,
    )
    from claude_autosar.core.bsw.templates.arxml_diff import diff_arxml_templates

    src = Path(args.path).resolve()
    tpl = Path(args.template).resolve()
    output = getattr(args, "output", None)
    do_apply = bool(getattr(args, "apply", False))

    # 1) 用 dispatcher 验证两份都是 ARXML
    try:
        dispatcher_read(src, expected_format="arxml")
    except (FileNotFoundError, OSError) as e:
        print(
            json.dumps({"success": False, "error": f"{type(e).__name__}: {e}"}),
            file=sys.stderr,
        )
        return 1
    except (ARXMLError, DispatcherError, UnknownFormatError, FormatMismatchError) as e:
        print(
            json.dumps({"success": False, "error": f"{type(e).__name__}: {e}"}),
            file=sys.stderr,
        )
        return 1

    try:
        dispatcher_read(tpl, expected_format="arxml")
    except (FileNotFoundError, OSError) as e:
        print(
            json.dumps({"success": False, "error": f"{type(e).__name__}: {e}"}),
            file=sys.stderr,
        )
        return 1
    except (ARXMLError, DispatcherError, UnknownFormatError, FormatMismatchError) as e:
        print(
            json.dumps({"success": False, "error": f"{type(e).__name__}: {e}"}),
            file=sys.stderr,
        )
        return 1

    # 2) 自动探测 module_name（从 current 取；fallback template）
    module_name = _detect_arxml_module_name(src)
    if module_name is None:
        module_name = _detect_arxml_module_name(tpl)
    if module_name is None:
        print(
            json.dumps(
                {
                    "success": False,
                    "error": "ValueError: no ECUC-MODULE-CONFIGURATION-VALUES "
                    "in current/template",
                }
            ),
            file=sys.stderr,
        )
        return 1

    # 3) load_module → ECUCDocument（diff_arxml_templates 期望的形状）
    try:
        current_doc = ecuc_load_module(src, module_name)
        template_doc = ecuc_load_module(tpl, module_name)
    except (ARXMLError, ValueError) as e:
        print(
            json.dumps({"success": False, "error": f"{type(e).__name__}: {e}"}),
            file=sys.stderr,
        )
        return 1

    # 4) diff
    try:
        diff_result = diff_arxml_templates(current_doc, template_doc)
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

    # 5) apply（dry-run 或 apply）
    mode = ApplyMode.APPLY if do_apply else ApplyMode.DRY_RUN
    try:
        apply_result = apply_template_diff(src, diff_result, mode=mode)
    except (OSError, FileNotFoundError) as e:
        print(
            json.dumps({"success": False, "error": f"{type(e).__name__}: {e}"}),
            file=sys.stderr,
        )
        return 1
    except (ValueError, TypeError, NotImplementedError) as e:
        print(
            json.dumps({"success": False, "error": f"{type(e).__name__}: {e}"}),
            file=sys.stderr,
        )
        return 1

    # 4) 可选 HTML 报告
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

    # 5) stdout JSON
    print(
        json.dumps(
            {
                "success": True,
                "format": "arxml",
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


def _apply_result_to_dict(result: Any) -> dict[str, Any]:
    """把 ``ApplyResult`` 缩成 dict（避免硬依赖 dataclass field 顺序）。

    如果 ``result`` 是 frozen dataclass，用 ``dataclasses.asdict``；否则
    走 ``vars`` / 空 dict。
    """
    try:
        from dataclasses import asdict, is_dataclass

        if is_dataclass(result) and not isinstance(result, type):
            return asdict(cast(Any, result))  # mypy: asdict 不接受 type[DataclassInstance]
    except Exception:  # noqa: BLE001 - 兜底任何 dataclass 异常
        pass
    try:
        return dict(vars(result))
    except TypeError:
        return {}
