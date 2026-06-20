"""Inspect / validate / dbc tools — moved from mcp_server.py.

Sprint 9.1 T9.1.4 inspector tools (ARXML / XDM / dispatcher wrapper).
Sprint 9.4 M4 (T9.4-beta) ``include_lint`` 激活。

Monkeypatch 兼容：inspect tool 函数通过 ``import claude_autosar.cli.mcp_server``
模块引用来调用 _run_lint_for_inspect，确保
``monkeypatch.setattr("claude_autosar.cli.mcp_server._run_lint_for_inspect", ...)``
对 tool 内部调用也生效。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _inspect_resolve_input(path: str, *, project: str = ".") -> Path:
    """解析 inspector 工具的 path 输入 + 校验 project 在允许根内。

    :raises PermissionError: project 不在 allowed roots
    :raises FileNotFoundError: 输入文件不存在
    :raises ValueError: path 含路径遍历序列
    """
    from claude_autosar.cli.mcp_server import _resolve_safe_project
    from claude_autosar.cli.mcp_tools.validation import validate_no_traversal

    validate_no_traversal(path)
    _resolve_safe_project(project)
    src = Path(path).resolve()
    if not src.is_file():
        raise FileNotFoundError(f"file not found: {src}")
    return src


def _run_lint_for_inspect(src: Path, fmt: str) -> dict[str, Any] | None:
    """走 LintRunner 跑 lint，返回 {violations, lint_summary} 或 None。

    duck-typed：框架未就位时返 None。任何 IO / 类型异常都收敛到 None。
    """
    try:
        from claude_autosar.core.bsw.lint import LintRunner
        from claude_autosar.core.bsw.lint.rules import rules_for_namespace
    except ImportError:
        return None

    try:
        if fmt == "arxml":
            from claude_autosar.core.bsw.lint.extract import extract_arxml_for_lint

            extracted: Any = extract_arxml_for_lint(src)
            ns = "arxml"
        else:
            from claude_autosar.core.bsw.lint.extract import extract_xdm_for_lint

            extracted = extract_xdm_for_lint(src)
            ns = "xdm"
    except (ImportError, OSError, ValueError, TypeError):
        return None

    try:
        rules = list(rules_for_namespace(ns))
        runner = LintRunner(rules=rules)
        violations = list(runner.run(extracted))
        summary = runner.summarize(violations)
    except (OSError, ValueError, TypeError, AttributeError):
        return None

    return {
        "violations": [
            {
                "rule_id": str(getattr(v, "rule_id", "")),
                "severity": str(getattr(v, "severity", "")),
                "message": str(getattr(v, "message", "")),
                "path": str(getattr(v, "path", "") or ""),
                "line": getattr(v, "line", None),
            }
            for v in violations
        ],
        "lint_summary": (
            {
                "total": int(getattr(summary, "total", 0)),
                "by_severity": dict(getattr(summary, "by_severity", {}) or {}),
            }
            if summary is not None
            else {"total": len(violations), "by_severity": {}}
        ),
    }


def arxml_validate(path: str) -> dict[str, Any]:
    """ARXML 解析校验（parse-only）。"""
    from claude_autosar.cli.mcp_tools.validation import validate_no_traversal
    from claude_autosar.core.bsw.arxml_io import ARXMLError, read

    try:
        validate_no_traversal(path)
    except ValueError as e:
        return {"success": False, "error": str(e)}

    p = Path(path)
    if not p.is_file():
        return {"success": False, "error": f"file not found: {path}"}
    try:
        doc = read(p)
    except ARXMLError as e:
        return {"success": False, "error": f"ARXMLError: {e}"}
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": f"{type(e).__name__}: {e}"}
    root = doc.tree.getroot()
    return {
        "success": True,
        "path": str(p),
        "root_tag": root.tag,
        "element_count": len(root.xpath("//*")),
    }


def dbc_parse(path: str) -> dict[str, Any]:
    """DBC 解析：返回 messages + signals 的 JSON 友好 dict。"""
    from claude_autosar.cli.mcp_tools.validation import validate_no_traversal

    try:
        import cantools
    except ImportError:
        return {"success": False, "error": "cantools not installed"}

    try:
        validate_no_traversal(path)
    except ValueError as e:
        return {"success": False, "error": str(e)}

    p = Path(path)
    if not p.is_file():
        return {"success": False, "error": f"file not found: {path}"}
    try:
        db = cantools.database.load_file(str(p))
    except Exception as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}
    if not hasattr(db, "messages"):
        return {"success": False, "error": "DBC parsed as non-CAN database (no messages)"}
    return {
        "success": True,
        "path": str(p),
        "version": getattr(db, "version", None),
        "messages": [
            {
                "name": m.name,
                "frame_id": m.frame_id,
                "is_extended": m.is_extended_frame,
                "length": m.length,
                "signals": [
                    {
                        "name": s.name,
                        "start_bit": s.start,
                        "length": s.length,
                        "byte_order": (
                            "little_endian" if s.byte_order == "little_endian" else "big_endian"
                        ),
                        "is_signed": s.is_signed,
                        "scale": s.scale,
                        "offset": s.offset,
                        "unit": s.unit or "",
                        "minimum": s.minimum,
                        "maximum": s.maximum,
                    }
                    for s in m.signals
                ],
            }
            for m in db.messages
        ],
    }


def arxml_inspect(
    path: str,
    output: str | None = None,
    *,
    include_lint: bool = False,
    project: str = ".",
) -> dict[str, Any]:
    """读单个 .arxml -> 渲染一页式 HTML 报告。

    :param path: .arxml 文件路径
    :param output: 输出 HTML 路径；None = input.report.html
    :param include_lint: True 时附加 LintRunner 全集
    :param project: 工程根目录（默认 cwd）
    """
    import claude_autosar.cli.mcp_server as _mcp

    from claude_autosar.core.bsw.inspector.arxml_report import export_arxml_report

    try:
        src = _inspect_resolve_input(path, project=project)
    except PermissionError as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}
    except FileNotFoundError as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    out_path = Path(output) if output else None
    # HIGH-4 修复：自定义 output 必须通过 H4 containment check，
    # 防止 MCP 客户端指定 ``/etc/cron.d/evil.html`` 等任意路径写入。
    if out_path is not None:
        try:
            _mcp._resolve_safe_project(output)  # type: ignore[arg-type]
        except PermissionError as e:
            return {"success": False, "error": f"{type(e).__name__}: {e}"}
    try:
        written = export_arxml_report(src, output=out_path)
    except (OSError, ValueError, TypeError) as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    result: dict[str, Any] = {
        "success": True,
        "format": "arxml",
        "path": str(src),
        "report_path": str(written),
    }

    if include_lint:
        lint_result = _mcp._run_lint_for_inspect(src, "arxml")
        if lint_result is None:
            result["lint_unavailable"] = True
        else:
            result["violations"] = lint_result["violations"]
            result["lint_summary"] = lint_result["lint_summary"]

    return result


def xdm_inspect(
    path: str,
    output: str | None = None,
    *,
    include_lint: bool = False,
    project: str = ".",
) -> dict[str, Any]:
    """读单个 .xdm (DataModel2) -> 渲染一页式 HTML 报告。

    :param path: .xdm 文件路径
    :param output: 输出 HTML 路径
    :param include_lint: True 时附加 LintRunner 全集
    :param project: 工程根目录（默认 cwd）
    """
    import claude_autosar.cli.mcp_server as _mcp

    from claude_autosar.core.bsw.inspector.xdm_report import export_xdm_report

    try:
        src = _inspect_resolve_input(path, project=project)
    except PermissionError as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}
    except FileNotFoundError as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    out_path = Path(output) if output else None
    # HIGH-4 修复：见 arxml_inspect 注释
    if out_path is not None:
        try:
            _mcp._resolve_safe_project(output)  # type: ignore[arg-type]
        except PermissionError as e:
            return {"success": False, "error": f"{type(e).__name__}: {e}"}
    try:
        written = export_xdm_report(src, output=out_path)
    except (OSError, ValueError, TypeError) as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    result: dict[str, Any] = {
        "success": True,
        "format": "xdm",
        "path": str(src),
        "report_path": str(written),
    }

    if include_lint:
        lint_result = _mcp._run_lint_for_inspect(src, "xdm")
        if lint_result is None:
            result["lint_unavailable"] = True
        else:
            result["violations"] = lint_result["violations"]
            result["lint_summary"] = lint_result["lint_summary"]

    return result


def bsw_inspect(
    path: str,
    output: str | None = None,
    *,
    include_lint: bool = False,
    project: str = ".",
) -> dict[str, Any]:
    """dispatcher：按文件根 namespace 自动选 arxml / xdm 渲染器。

    :param path: 输入文件路径（按根 xmlns 自动选，不依赖后缀）
    :param output: 输出 HTML 路径
    :param include_lint: True 时附加 LintRunner 全集
    :param project: 工程根目录（默认 cwd）
    """
    import claude_autosar.cli.mcp_server as _mcp

    from claude_autosar.core.bsw.dispatcher import (
        DispatcherError,
        UnknownFormatError,
        detect_format,
    )
    from claude_autosar.core.bsw.inspector.arxml_report import export_arxml_report
    from claude_autosar.core.bsw.inspector.xdm_report import export_xdm_report

    try:
        src = _inspect_resolve_input(path, project=project)
    except PermissionError as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}
    except FileNotFoundError as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    try:
        fmt = detect_format(src)
    except (UnknownFormatError, DispatcherError) as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}
    except FileNotFoundError as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    out_path = Path(output) if output else None
    # HIGH-4 修复：见 arxml_inspect 注释
    if out_path is not None:
        try:
            _mcp._resolve_safe_project(output)  # type: ignore[arg-type]
        except PermissionError as e:
            return {"success": False, "error": f"{type(e).__name__}: {e}"}
    try:
        if fmt == "arxml":
            written = export_arxml_report(src, output=out_path)
        else:
            written = export_xdm_report(src, output=out_path)
    except (OSError, ValueError, TypeError) as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    result: dict[str, Any] = {
        "success": True,
        "format": fmt,
        "path": str(src),
        "report_path": str(written),
    }

    if include_lint:
        lint_result = _mcp._run_lint_for_inspect(src, fmt)
        if lint_result is None:
            result["lint_unavailable"] = True
        else:
            result["violations"] = lint_result["violations"]
            result["lint_summary"] = lint_result["lint_summary"]

    return result
