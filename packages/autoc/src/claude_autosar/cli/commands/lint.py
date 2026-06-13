"""``autoc lint`` 子命令 — Sprint 9.4 M4 (T9.4-β).

读单个 ``.arxml`` / ``.xdm`` 文件 → 走 :mod:`claude_autosar.core.bsw.lint`
框架跑 LintRule 全集 → 输出 JSON (stdout) + 可选 HTML 报告 (--output)。

设计要点（plan §4.3 + 9.1 inspect 子命令样板）：

  - **dispatcher.detect_format 决定走 arxml 还是 xdm extractor**
  - **duck-typed LintRunner**：9.4-α 在并发写 ``core.bsw.lint.*``，本 sprint
    通过 ``try/except ImportError`` 优雅降级：lint 模块未到位时返
    ``{"success": True, "lint_unavailable": True, ...}`` 而不是崩
  - **filter**：``--rule`` (可重复) + ``--severity``
  - **HTML 报告 (--output)**：reuse :mod:`core.bsw.inspector.*_report` 的
    ``_INSPECTOR_CSS`` summary-box + violations table（XSS escape 走
    :func:`html.escape`）
  - **exit code**：异常 → 1；正常 → 0（即使有 violations；用户拿 JSON
    summary 自行判断；这与 ``bsw-verify`` 风格保持一致）
"""

from __future__ import annotations

import argparse
import html as _html
import json
from pathlib import Path
import sys
from typing import Any

__all__ = ["register", "run"]


# ---------------------------------------------------------------------------
# Lint 框架桥接 (duck-typed，9.4-α 在并发写)
# ---------------------------------------------------------------------------


def _try_import_lint() -> tuple[Any, Any, Any]:
    """尝试导入 lint 框架三件套；任一失败就返 ``(None, None, None)``。

    9.4-α 在另一个 branch 上写 ``core.bsw.lint``；本文件按 duck typing
    设计，确保 ``lint`` 子命令在 lint 框架未并入时也能注册 + arg-parse
    跑通（只是 ``run()`` 会返 ``lint_unavailable=True``）。
    """
    try:
        from claude_autosar.core.bsw.lint import LintRunner, LintSummary
        from claude_autosar.core.bsw.lint.rules import ALL_RULES
    except ImportError:
        return (None, None, None)
    return (LintRunner, LintSummary, ALL_RULES)


def _try_extract(path: Path, fmt: str) -> Any:
    """按 fmt 调对应 ``extract_*_for_lint``；失败返 ``None``。"""
    try:
        if fmt == "arxml":
            from claude_autosar.core.bsw.lint.extract import (
                extract_arxml_for_lint,
            )

            return extract_arxml_for_lint(path)
        from claude_autosar.core.bsw.lint.extract import extract_xdm_for_lint

        return extract_xdm_for_lint(path)
    except ImportError:
        return None
    except (OSError, ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# HTML report helpers (XSS-safe，reuse inspector 风格的 summary-box)
# ---------------------------------------------------------------------------


def _render_lint_html(violations: list[Any]) -> str:
    """渲染 violations table HTML (escape 防 XSS，reuse inspector CSS 类名)。"""
    # 按 severity 排序：error > warning > info (降序)
    severity_rank = {"error": 0, "warning": 1, "info": 2}
    sorted_v = sorted(
        violations,
        key=lambda v: (
            severity_rank.get(str(getattr(v, "severity", "info")).lower(), 99),
            str(getattr(v, "rule_id", "")),
        ),
    )

    rows: list[str] = []
    for v in sorted_v:
        rule_id = _html.escape(str(getattr(v, "rule_id", "")))
        severity = _html.escape(str(getattr(v, "severity", "")))
        message = _html.escape(str(getattr(v, "message", "")))
        path_str = _html.escape(str(getattr(v, "path", "") or "-"))
        line_str = str(getattr(v, "line", "") or "-")
        rows.append(
            "<tr>"
            f"<td>{rule_id}</td>"
            f"<td>{severity}</td>"
            f"<td>{path_str}:{line_str}</td>"
            f"<td>{message}</td>"
            "</tr>"
        )

    body = (
        '<section class="lint-section">\n'
        '<h2>Lint Violations</h2>\n'
        '<div class="summary-box">\n'
        f'<strong>{len(violations)}</strong> violation(s)\n'
        '</div>\n'
        '<table>\n'
        "<thead><tr><th>Rule</th><th>Severity</th><th>Location</th>"
        "<th>Message</th></tr></thead>\n"
        "<tbody>\n" + "\n".join(rows) + "\n</tbody>\n"
        "</table>\n"
        "</section>\n"
    )
    return body


def _violation_to_dict(v: Any) -> dict[str, Any]:
    """把 LintViolation duck-type 转成 JSON-serializable dict。"""
    return {
        "rule_id": str(getattr(v, "rule_id", "")),
        "severity": str(getattr(v, "severity", "")),
        "message": str(getattr(v, "message", "")),
        "path": str(getattr(v, "path", "") or ""),
        "line": getattr(v, "line", None),
    }


def _summary_to_dict(s: Any) -> dict[str, Any]:
    """把 LintSummary duck-type 转成 JSON dict。"""
    if s is None:
        return {"total": 0, "by_severity": {}}
    # duck type: attribute access
    return {
        "total": int(getattr(s, "total", 0)),
        "by_severity": dict(getattr(s, "by_severity", {}) or {}),
    }


# ---------------------------------------------------------------------------
# Argparse + run
# ---------------------------------------------------------------------------


def register(subparsers: Any) -> None:
    """挂载到主 argparse subparsers。"""
    p = subparsers.add_parser(
        "lint",
        help="对单个 .arxml / .xdm 跑 lint 规则集 → JSON stdout + 可选 HTML 报告",
    )
    p.add_argument(
        "path",
        type=Path,
        help="输入文件路径（按根 xmlns 自动选 arxml / xdm）",
    )
    p.add_argument(
        "-o",
        "--output",
        dest="output",
        type=Path,
        default=None,
        help="输出 HTML 报告路径；缺省不写文件",
    )
    p.add_argument(
        "--rule",
        action="append",
        default=[],
        metavar="RULE_ID",
        help="只跑指定 rule_id（可重复）",
    )
    p.add_argument(
        "--severity",
        choices=["error", "warning", "info"],
        default=None,
        help="按 severity 过滤",
    )
    p.add_argument(
        "--project",
        default=".",
        help="工程根目录（默认 cwd；当前仅占位）",
    )


def build_parser() -> argparse.ArgumentParser:
    """为单元测试提供独立 parser。"""
    parser = argparse.ArgumentParser(prog="autoc")
    sub = parser.add_subparsers(dest="command", required=False)
    register(sub)
    return parser


def _filter_violations(
    violations: list[Any], rules: list[str], severity: str | None
) -> list[Any]:
    """按 --rule / --severity 过滤；都不指定 → 不过滤。"""

    def keep(v: Any) -> bool:
        if rules:
            rid = str(getattr(v, "rule_id", ""))
            if rid not in rules:
                return False
        if severity is not None:
            sev = str(getattr(v, "severity", "")).lower()
            if sev != severity.lower():
                return False
        return True

    return [v for v in violations if keep(v)]


def run(args: argparse.Namespace) -> int:
    """执行 ``lint``。返回 exit code。"""
    src = Path(args.path)
    output = getattr(args, "output", None)
    rule_filter: list[str] = list(getattr(args, "rule", []) or [])
    severity_filter: str | None = getattr(args, "severity", None)

    # 1) detect format
    try:
        from claude_autosar.core.bsw.dispatcher import detect_format
    except ImportError as e:  # pragma: no cover - dispatcher is core
        print(
            json.dumps({"success": False, "error": f"ImportError: {e}"}),
            file=sys.stderr,
        )
        return 1

    try:
        fmt = detect_format(src)
    except FileNotFoundError as e:
        print(
            json.dumps({"success": False, "error": f"FileNotFoundError: {e}"}),
            file=sys.stderr,
        )
        return 1
    except (OSError, ValueError, TypeError) as e:
        print(
            json.dumps({"success": False, "error": f"{type(e).__name__}: {e}"}),
            file=sys.stderr,
        )
        return 1

    # 2) lint 框架就位检查
    LintRunner, _LintSummary, ALL_RULES = _try_import_lint()
    if LintRunner is None:
        # 9.4-α 未并入；返 lint_unavailable 而不是崩
        print(
            json.dumps(
                {
                    "success": True,
                    "lint_unavailable": True,
                    "reason": "core.bsw.lint not yet implemented (Sprint 9.4-α in progress)",
                    "format": fmt,
                    "path": str(src),
                }
            )
        )
        return 0

    # 3) 提取 + 跑 lint
    extracted = _try_extract(src, fmt)
    if extracted is None:
        print(
            json.dumps({"success": False, "error": "lint extract failed"}),
            file=sys.stderr,
        )
        return 1

    try:
        rules = list(ALL_RULES) if ALL_RULES else []
        runner = LintRunner(rules=rules)
        violations = list(runner.run(extracted))
        # 过滤
        violations = _filter_violations(violations, rule_filter, severity_filter)
        summary = runner.summarize(violations)
    except (OSError, ValueError, TypeError, AttributeError) as e:
        print(
            json.dumps({"success": False, "error": f"{type(e).__name__}: {e}"}),
            file=sys.stderr,
        )
        return 1

    # 4) 可选 HTML 报告
    if output is not None:
        try:
            from claude_autosar.core.bsw.inspector.arxml_report import (
                render_arxml_report,
            )

            # dispatch 到对应 inspector 拿 base HTML
            if fmt == "arxml":
                base_html = render_arxml_report(src)
            else:
                from claude_autosar.core.bsw.inspector.xdm_report import (
                    render_xdm_report,
                )

                base_html = render_xdm_report(src)
            section = _render_lint_html(violations)
            if "</body>" in base_html:
                full = base_html.replace("</body>", section + "</body>", 1)
            else:
                full = base_html + "\n" + section
            Path(output).write_text(full, encoding="utf-8")
        except (OSError, ValueError, TypeError) as e:
            print(
                json.dumps(
                    {
                        "success": False,
                        "error": f"HTML export failed: {type(e).__name__}: {e}",
                    }
                ),
                file=sys.stderr,
            )
            return 1

    # 5) stdout JSON
    print(
        json.dumps(
            {
                "success": True,
                "lint_unavailable": False,
                "format": fmt,
                "path": str(src),
                "report_path": str(output) if output else None,
                "summary": _summary_to_dict(summary),
                "violations": [_violation_to_dict(v) for v in violations],
            }
        )
    )
    return 0
