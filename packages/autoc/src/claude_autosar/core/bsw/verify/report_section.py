"""``report_section`` — Sprint 9.3 T9.3-γ verify 报告嵌入段。

把 :class:`TresosVerifyReport` 的 issues 渲染成可嵌入到 inspector
HTML 报告（:mod:`core.bsw.inspector.arxml_report` /
:mod:`core.bsw.inspector.xdm_report`）的 ``<section>`` HTML 字符串。

设计原则（对齐 plan §3.1）：

* **独立可嵌入** — 输出是完整 ``<section>`` 片段，调用方决定插入位置
  （典型用法：在已有 inspector HTML 的 ``</body>`` 前 ``replace`` 插入）。
* **duck typing** — 不强依赖 :class:`TresosVerifyReport`，只读字段
  ``severity`` / ``code`` / ``message`` / ``module`` / ``file`` / ``line``，
  因此本模块在 ``TresosVerifyReport`` 尚未实现时也能 import 通过。
  ``isinstance`` 检查失败时降级为对象属性访问。
* **XSS 防御** — 所有 issue 字段（code / message / module / file / line）
  都过 :func:`html.escape`（同 :mod:`core.bsw.inspector.arxml_report`
  现有约定）。恶意构造 ``<script>alert(1)</script>`` message 在渲染后
  只剩字面量 ``&lt;script&gt;``，不会被解析为 HTML。
* **空 issues 处理** — 零 issues 且 returncode == 0 → 返
  ``<section>Verify section: 0 issues</section>``（最小占位），调用方
  可选择跳过嵌入。
* **severity 排序** — ERROR > WARNING > INFO，便于人眼优先扫到错误。
* **不重写 inspector 既有渲染** — 本模块只提供 ``<section>`` 字符串
  生成；调用方负责拼接。

公共 API：

* :func:`render_verify_section_html` — issues + returncode → HTML 字符串
"""

from __future__ import annotations

from html import escape as _html_escape
from typing import Any

__all__ = ["render_verify_section_html"]


#: severity 显示顺序（最高优先级在前）
_SEVERITY_ORDER: dict[str, int] = {
    "ERROR": 0,
    "WARNING": 1,
    "INFO": 2,
}


def _coerce_severity(value: Any) -> str:
    """duck-typing 提取 severity 字段。

    接受字符串 / Literal["ERROR","WARNING","INFO"]；其他 → "INFO"（保守 fallback）。
    """
    if isinstance(value, str):
        upper = value.upper()
        if upper in _SEVERITY_ORDER:
            return upper
    return "INFO"


def _coerce_optional_str(value: Any) -> str:
    """duck-typing 提取可选 str 字段。None / 非字符串 → 空字符串（XSS 在 escape 时做）。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _coerce_optional_int(value: Any) -> int | None:
    """duck-typing 提取可选 int 行号。None / 非 int → None（XSS safe）。"""
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _location_text(file: str | None, line: int | None) -> str:
    """拼 ``file:line`` location 字符串（escape 在调用方做）。"""
    file_esc = _html_escape(file) if file else ""
    line_esc = str(line) if line is not None else ""
    if file_esc and line_esc:
        return f"{file_esc}:{line_esc}"
    if file_esc:
        return file_esc
    return "—"


def _sort_key(issue: Any) -> tuple[int, int]:
    """按 severity 升序、保持原顺序（在原始 sequence 上做 stable sort）。"""
    sev = _coerce_severity(getattr(issue, "severity", "INFO"))
    return (_SEVERITY_ORDER[sev], 0)


def render_verify_section_html(
    issues: tuple[Any, ...],
    *,
    returncode: int = 0,
) -> str:
    """渲染 verify section HTML（独立可嵌入片段）。

    Parameters
    ----------
    issues:
        :class:`TresosVerifyIssue` 元组（duck-typing：只读
        ``severity`` / ``code`` / ``message`` / ``module`` /
        ``file`` / ``line`` 字段）。空 → 仅渲染 summary + 占位行。
    returncode:
        tresos_cmd returncode（默认 ``0``）。非 ``0`` → 在 summary 框标红。

    Returns
    -------
    str:
        完整 ``<section class="verify-section">...</section>`` HTML
        字符串。XSS-safe（所有 issue 字段过 :func:`html.escape`）。

    Notes
    -----
    * severity 排序：ERROR > WARNING > INFO；同 severity 保持原顺序（stable）。
    * 空 issues + returncode=0 → 渲染 ``"Verify section: 0 issues"``
      占位行；调用方可基于此判断是否嵌入。
    """
    parts: list[str] = []

    # 统计 severity 计数（用于 summary box）
    n_error = 0
    n_warning = 0
    n_info = 0
    for issue in issues:
        sev = _coerce_severity(getattr(issue, "severity", "INFO"))
        if sev == "ERROR":
            n_error += 1
        elif sev == "WARNING":
            n_warning += 1
        else:
            n_info += 1

    # 1) summary-box（沿用 inspector 既有 class）
    rc_class = "verify-rc-nonzero" if returncode != 0 else "verify-rc-zero"
    summary_text = (
        f"<strong>returncode</strong>: {_html_escape(str(returncode))} "
        f"&nbsp;&nbsp; "
        f"<strong>errors</strong>: {n_error} &nbsp;&nbsp; "
        f"<strong>warnings</strong>: {n_warning} &nbsp;&nbsp; "
        f"<strong>infos</strong>: {n_info}"
    )
    parts.append(
        f'<div class="summary-box {rc_class}">'
        f"{summary_text}"
        f"</div>\n"
    )

    # 2) issues table（沿用 metadata-table class）
    if not issues:
        parts.append(
            "<p><em>Verify section: 0 issues</em></p>\n"
        )
    else:
        # severity 排序（ERROR → WARNING → INFO，stable）
        sorted_issues = sorted(
            issues,
            key=_sort_key,
        )
        rows: list[str] = []
        for issue in sorted_issues:
            sev = _coerce_severity(getattr(issue, "severity", "INFO"))
            code = _coerce_optional_str(getattr(issue, "code", ""))
            module = _coerce_optional_str(getattr(issue, "module", ""))
            message = _coerce_optional_str(getattr(issue, "message", ""))
            file_raw = getattr(issue, "file", None)
            file_value = file_raw if isinstance(file_raw, str) else (
                None if file_raw is None else str(file_raw)
            )
            line = _coerce_optional_int(getattr(issue, "line", None))
            location = _location_text(file_value, line)
            rows.append(
                "<tr>"
                f"<td><span class='tag tag-{sev.lower()}'>"
                f"{_html_escape(sev)}"
                f"</span></td>"
                f"<td><code>{_html_escape(code)}</code></td>"
                f"<td><code>{_html_escape(module)}</code></td>"
                f"<td>{_html_escape(message)}</td>"
                f"<td><code>{location}</code></td>"
                "</tr>"
            )
        parts.append(
            "<table class='metadata-table verify-issues-table'>\n"
            "<thead><tr>"
            "<th>Severity</th><th>Code</th><th>Module</th>"
            "<th>Message</th><th>Location</th>"
            "</tr></thead>\n"
            "<tbody>\n"
            + "".join(rows)
            + "</tbody>\n"
            "</table>\n"
        )

    section_body = "".join(parts)
    return (
        '<section class="verify-section">\n'
        "<h2>Verify</h2>\n"
        f"{section_body}"
        "</section>\n"
    )
