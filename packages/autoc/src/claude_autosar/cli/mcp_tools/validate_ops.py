"""``bsw_validate`` MCP tool — 一站式配置校验。

Sprint 10 — T10.6。串联 lint + coverage + xref，输出统一报告。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def bsw_validate(
    module: str,
    *,
    project: str = ".",
    include_xref: bool = True,
    include_coverage: bool = True,
    include_lint: bool = True,
) -> dict[str, Any]:
    """一站式 BSW 配置校验：lint + 覆盖率 + 引用完整性。

    Args:
        module: 模块名（如 ``Com``、``Mcu``）。
        project: 工程根目录（默认当前目录）。
        include_xref: 是否包含跨模块引用检查。
        include_coverage: 是否包含参数覆盖率报告。
        include_lint: 是否包含 lint 检查。

    Returns:
        ``{success, module, lint, coverage, xref, errors}`` 结构化报告。
    """
    from claude_autosar.cli.mcp_server import _resolve_safe_project
    from claude_autosar.cli.mcp_tools.validation import validate_module_name
    from claude_autosar.core.bsw.dispatcher import detect_format

    try:
        validate_module_name(module)
        # H4 路径防御（HIGH-9 修复）：用 _resolve_safe_project 替换
        # validate_no_traversal，确保 project 在 _ALLOWED_PROJECT_ROOTS 内
        # （单纯 validate_no_traversal 漏掉 ``/etc`` 这类绝对路径）。
        project_path = _resolve_safe_project(project)
    except (ValueError, PermissionError) as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}", "module": module}

    result: dict[str, Any] = {"success": True, "module": module}
    errors: list[str] = []

    # 定位模块文件（project_path 已 resolve，无需再 .resolve()）
    module_file = _locate_module_file(project_path, module)
    if module_file is None:
        return {
            "success": False,
            "error": f"Module file not found for {module!r} in {project_path}",
            "module": module,
        }

    fmt = detect_format(module_file)

    # 1. Lint
    if include_lint:
        lint_result = _run_lint(module_file, fmt)
        if lint_result is not None:
            result["lint"] = lint_result
        else:
            result["lint"] = {"total": 0, "errors": 0, "warnings": 0, "violations": []}

    # 2. Coverage
    if include_coverage:
        coverage_result = _run_coverage(module_file, module)
        if coverage_result is not None:
            result["coverage"] = coverage_result
        else:
            errors.append("coverage: BSWMD registry not available")

    # 3. Xref
    if include_xref:
        xref_result = _run_xref(project_path, module)
        if xref_result is not None:
            result["xref"] = xref_result
        else:
            errors.append("xref: failed to load modules")

    if errors:
        result["errors"] = errors

    return result


def _locate_module_file(project_path: Path, module: str) -> Path | None:
    """定位模块文件（.xdm 优先，.arxml 其次）。"""
    for suffix in (".xdm", ".arxml"):
        candidate = project_path / f"{module}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def _run_lint(module_file: Path, fmt: str) -> dict[str, Any] | None:
    """运行 lint 检查。"""
    try:
        from claude_autosar.core.bsw.lint import LintRunner
        from claude_autosar.core.bsw.lint.rules import rules_for_namespace
    except ImportError:
        return None

    try:
        if fmt == "arxml":
            from claude_autosar.core.bsw.lint.extract import extract_arxml_for_lint

            extracted = extract_arxml_for_lint(module_file)
            ns = "arxml"
        else:
            from claude_autosar.core.bsw.lint.extract import extract_xdm_for_lint

            extracted = extract_xdm_for_lint(module_file)
            ns = "xdm"

        rules = list(rules_for_namespace(ns))
        runner = LintRunner(rules=rules)
        violations = list(runner.run(extracted))
        summary = runner.summarize(violations)

        return {
            "total": summary.total,
            "errors": summary.errors,
            "warnings": summary.warnings,
            "infos": summary.infos,
            "violations": [
                {
                    "rule_id": v.rule_id,
                    "severity": str(v.severity),
                    "message": v.message,
                    "module": v.module,
                    "suggestion": v.suggestion or "",
                }
                for v in violations
            ],
        }
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def _run_coverage(module_file: Path, module: str) -> dict[str, Any] | None:
    """运行参数覆盖率检查。"""
    try:
        from claude_autosar.core.bsw.bswmd import BSWMDRegistry
        from claude_autosar.core.bsw.coverage import compute_coverage
        from claude_autosar.core.bsw.ecuc import load_module
        from claude_autosar.core.config.project_config import ProjectConfig

        config = ProjectConfig.load()
        registry = BSWMDRegistry.load_default(config)
        doc = load_module(module_file, module)
        report = compute_coverage(doc, registry)

        return {
            "total": report.total_params,
            "configured": report.configured_params,
            "missing": list(report.missing_params),
            "pct": report.coverage_pct,
        }
    except (OSError, ValueError, TypeError, ImportError, RuntimeError):
        return None


def _run_xref(project_path: Path, module: str) -> dict[str, Any] | None:
    """运行跨模块引用检查。"""
    try:
        from claude_autosar.core.bsw.ecuc import load_module
        from claude_autosar.core.bsw.xref import check_references

        # 加载工程中所有模块
        docs: dict[str, Any] = {}
        for suffix in (".xdm", ".arxml"):
            for f in project_path.glob(f"*{suffix}"):
                try:
                    from claude_autosar.core.bsw.dispatcher import detect_format

                    fmt = detect_format(f)
                    if fmt == "arxml":
                        # 从文件名提取模块名
                        mod_name = f.stem
                        docs[mod_name] = load_module(f, mod_name)
                except (ValueError, OSError):
                    continue

        if not docs:
            return None

        result = check_references(docs)
        return {
            "total": result.total_references,
            "resolved": result.resolved,
            "dangling": result.dangling,
            "violations": [
                {
                    "source": v.source_path,
                    "target": v.target_ref,
                    "reason": v.reason,
                }
                for v in result.violations
            ],
        }
    except (OSError, ValueError, TypeError, ImportError):
        return None
