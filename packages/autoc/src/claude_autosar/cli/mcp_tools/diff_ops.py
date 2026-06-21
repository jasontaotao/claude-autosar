"""``bsw_diff`` MCP tool — ARXML/XDM 参数级 diff。

Sprint 11 — T11.1。暴露已有 diff 引擎为 MCP tool。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def bsw_diff(
    module: str,
    file_a: str,
    file_b: str,
    *,
    project: str = ".",
) -> dict[str, Any]:
    """对比两个 ARXML/XDM 文件的参数差异。

    Args:
        module: 模块名（如 ``Com``、``Mcu``）。
        file_a: 基准文件路径。
        file_b: 对比文件路径。
        project: 工程根目录（默认当前目录）。

    Returns:
        ``{success, module, diff_count, adds, modifies, deletes}`` 结构化 diff。
    """
    from claude_autosar.cli.mcp_server import _resolve_safe_project
    from claude_autosar.cli.mcp_tools.validation import (
        validate_module_name,
        validate_no_traversal,
    )
    from claude_autosar.core.bsw.dispatcher import detect_format

    try:
        validate_module_name(module)
        # 路径遍历检查（traversal-only，允许绝对路径用于文件系统操作）
        if ".." in file_a:
            raise ValueError(f"Path traversal not allowed: {file_a!r}")
        if ".." in file_b:
            raise ValueError(f"Path traversal not allowed: {file_b!r}")
        # H4 路径防御（HIGH-9 修复）：用 _resolve_safe_project 替换
        # validate_no_traversal(project)，确保 project 在 allowed roots 内
        # （单纯 validate_no_traversal 漏掉 ``/etc`` 这类绝对路径）。
        project_path = _resolve_safe_project(project)
    except (ValueError, PermissionError) as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}", "module": module}

    path_a = Path(file_a).resolve()
    path_b = Path(file_b).resolve()

    if not path_a.is_file():
        return {"success": False, "error": f"File not found: {path_a}", "module": module}
    if not path_b.is_file():
        return {"success": False, "error": f"File not found: {path_b}", "module": module}

    try:
        fmt_a = detect_format(path_a)
        fmt_b = detect_format(path_b)
    except (ValueError, OSError) as e:
        return {"success": False, "error": f"Format detection failed: {e}", "module": module}

    # 两个文件格式必须一致
    if fmt_a != fmt_b:
        return {
            "success": False,
            "error": f"Format mismatch: {fmt_a} vs {fmt_b}",
            "module": module,
        }

    try:
        if fmt_a == "arxml":
            return _diff_arxml(module, path_a, path_b)
        else:
            return _diff_xdm(module, path_a, path_b)
    except (OSError, ValueError, TypeError) as e:
        return {"success": False, "error": str(e), "module": module}


def _diff_arxml(module: str, path_a: Path, path_b: Path) -> dict[str, Any]:
    """ARXML 格式 diff。"""
    from claude_autosar.core.bsw.ecuc import load_module
    from claude_autosar.core.bsw.templates.arxml_diff import diff_arxml_templates

    doc_a = load_module(path_a, module)
    doc_b = load_module(path_b, module)
    result = diff_arxml_templates(doc_a, doc_b)

    return _result_to_dict(result, module)


def _diff_xdm(module: str, path_a: Path, path_b: Path) -> dict[str, Any]:
    """XDM 格式 diff。"""
    from claude_autosar.core.bsw.templates.xdm_diff import diff_xdm_templates
    from claude_autosar.core.bsw.templates.xdm_value import load_xdm_module

    doc_a = load_xdm_module(path_a, module)
    doc_b = load_xdm_module(path_b, module)
    result = diff_xdm_templates(doc_a, doc_b)

    return {
        "success": True,
        "module": module,
        "format": "xdm",
        "diff_count": len(result.diffs),
        "adds": [
            {"path": d.path, "value": d.template.raw if d.template else None}
            for d in result.adds
        ],
        "modifies": [
            {
                "path": d.path,
                "old": d.current.raw if d.current else None,
                "new": d.template.raw if d.template else None,
            }
            for d in result.modifies
        ],
        "deletes": [
            {"path": d.path, "value": d.current.raw if d.current else None}
            for d in result.deletes
        ],
    }


def _result_to_dict(result: Any, module: str) -> dict[str, Any]:
    """将 TemplateDiffResult 转为 MCP tool 返回格式。"""
    return {
        "success": True,
        "module": module,
        "format": "arxml",
        "diff_count": len(result.diffs),
        "adds": [
            {"path": d.path, "value": d.template.raw if d.template else None}
            for d in result.adds
        ],
        "modifies": [
            {
                "path": d.path,
                "old": d.current.raw if d.current else None,
                "new": d.template.raw if d.template else None,
            }
            for d in result.modifies
        ],
        "deletes": [
            {"path": d.path, "value": d.current.raw if d.current else None}
            for d in result.deletes
        ],
    }
