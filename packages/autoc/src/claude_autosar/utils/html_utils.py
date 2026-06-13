"""Sprint 9.1 T9.1.1 — 共享 HTML 工具。

封装 HTML 自包含文档生成所需的所有原子操作，供 inspector (T9.1.2/3)
与 session exporter 共用。

设计要点：
- **XSS-safe**：所有动态字符串经 ``html.escape``；URL scheme 白名单过滤
- **轻量 inline Markdown**（**bold** / `code` / [link](url)），不引外部 lib
- **三色 callout**：add=绿、modify=黄、delete=红
- **纯函数**：不依赖 inspector / session；只接受 string 拼 HTML 块
"""

from __future__ import annotations

import html
import re

# ---------------------------------------------------------------------------
# 轻量 inline Markdown
# ---------------------------------------------------------------------------

# 顺序很重要：先 link，再 code，再 bold（避免 `code` 误匹配 link 内的方括号）
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_MD_CODE_RE = re.compile(r"`([^`]+)`")
_MD_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")

# URL scheme 白名单：拒掉 javascript: / data: / vbscript: 等可执行 scheme。
# 文件:// 本地浏览器导航可接受（用户主动打开的本地 HTML）。
ALLOWED_URL_SCHEMES: tuple[str, ...] = (
    "http://",
    "https://",
    "mailto:",
    "file:",
)


def is_safe_url(url: str) -> bool:
    """URL scheme 必须在白名单中（大小写不敏感），否则视为不安全。"""
    lower = url.strip().lower()
    return any(lower.startswith(scheme) for scheme in ALLOWED_URL_SCHEMES)


def render_inline_md(text: str) -> str:
    """把 inline markdown 子集转 HTML。已 escape。"""
    # 先收集所有匹配的位置，避免后续替换破坏已写入的标签
    # 简化：分阶段替换，每阶段用占位符，结束后还原
    placeholders: list[str] = []

    def _stash(html_fragment: str) -> str:
        placeholders.append(html_fragment)
        return f"\x00PH{len(placeholders) - 1}\x00"

    s = text
    # link — scheme 白名单过滤
    s = _MD_LINK_RE.sub(
        lambda m: _stash(
            (
                f'<a href="{html.escape(m.group(2), quote=True)}'
                f'" rel="noopener noreferrer">'
                f"{html.escape(m.group(1))}</a>"
            )
            if is_safe_url(m.group(2))
            else html.escape(m.group(1))  # scheme 不安全 → 只显示 link text
        ),
        s,
    )
    # code
    s = _MD_CODE_RE.sub(
        lambda m: _stash(f"<code>{html.escape(m.group(1))}</code>"),
        s,
    )
    # bold
    s = _MD_BOLD_RE.sub(
        lambda m: _stash(f"<strong>{html.escape(m.group(1))}</strong>"),
        s,
    )
    # escape 剩余的纯文本
    s = html.escape(s)
    # 还原占位符
    s = re.sub(
        r"\x00PH(\d+)\x00",
        lambda m: placeholders[int(m.group(1))],
        s,
    )
    # 行内换行
    s = s.replace("\n", "<br>")
    return s


# ---------------------------------------------------------------------------
# CSS（inline）
# ---------------------------------------------------------------------------

_CSS = """
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    max-width: 960px;
    margin: 2rem auto;
    padding: 0 1rem;
    color: #1a1a1a;
    line-height: 1.5;
    background: #fafafa;
}
h1, h2, h3 { color: #222; }
.meta { color: #666; font-size: 0.9em; margin-bottom: 1.5rem; }
.entry {
    border-left: 3px solid #ccc;
    padding: 0.5rem 0.75rem;
    margin: 0.75rem 0;
    background: #fff;
}
.entry.user { border-color: #4a90e2; }
.entry.assistant { border-color: #888; }
.entry.tool { border-color: #f5a623; }
.entry.tool_result { border-color: #aaa; }
.entry .ts { color: #999; font-size: 0.8em; }
.callout {
    display: inline-block;
    padding: 0.25rem 0.6rem;
    border-radius: 4px;
    font-weight: bold;
    margin: 0.25rem 0;
    font-family: ui-monospace, Menlo, Consolas, monospace;
    font-size: 0.9em;
}
.callout.add    { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
.callout.modify { background: #fff3cd; color: #856404; border: 1px solid #ffeeba; }
.callout.delete { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
.changes-section { margin-top: 2rem; }
.changes-section pre {
    background: #fff;
    padding: 0.75rem;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    overflow-x: auto;
    font-size: 0.9em;
}
.footer { margin-top: 3rem; color: #999; font-size: 0.8em; text-align: center; }
""".strip()


# ---------------------------------------------------------------------------
# 三色 callout
# ---------------------------------------------------------------------------

_ALLOWED_CALLOUT_OPS: tuple[str, ...] = ("add", "modify", "delete")


def render_callout(op: str, label: str, detail: str = "") -> str:
    """封装三色 callout HTML 生成。

    Args:
        op: 操作类型 ∈ ``{"add", "modify", "delete"}``；其他值降级为 ``modify``（黄色）。
        label: 主标签（已 escape）。通常格式如 ``"Mcu/ClockFreq"``。
        detail: 额外说明（已 escape）。如 ``"= 80000000"`` 或 ``"40 → 80"``。

    Returns:
        ``<div class="callout <op>">LABEL DETAIL</div>``。
    """
    op_class = op if op in _ALLOWED_CALLOUT_OPS else "modify"
    safe_label = html.escape(label)
    safe_detail = html.escape(detail) if detail else ""
    spacing = " " if safe_detail else ""
    return f'<div class="callout {op_class}">{safe_label}{spacing}{safe_detail}</div>'


# ---------------------------------------------------------------------------
# HTML 文档组装
# ---------------------------------------------------------------------------


def render_html_doc(
    title: str,
    body_parts: list[str],
    css: str | None = None,
    footer: str = "",
) -> str:
    """组装完整 HTML 文档：doctype + html + head + style + body + footer。

    Args:
        title: ``<title>`` 文本（已 escape）。
        body_parts: 已渲染好的 body HTML 片段列表。
        css: 自定义 CSS；不传则用内置 ``_CSS``。
        footer: 页脚 HTML 片段（已 escape）；空字符串则跳过。

    Returns:
        完整 HTML 字符串，以 ``\\n`` 结尾。
    """
    style = css if css is not None else _CSS
    parts: list[str] = [
        "<!DOCTYPE html>",
        '<html lang="zh-CN">',
        "<head>",
        '<meta charset="utf-8">',
        f"<title>{html.escape(title)}</title>",
        f"<style>{style}</style>",
        "</head>",
        "<body>",
    ]
    parts.extend(body_parts)
    if footer:
        parts.append(footer)
    parts.append("</body></html>")
    return "\n".join(parts) + "\n"


__all__ = [
    "ALLOWED_URL_SCHEMES",
    "is_safe_url",
    "render_inline_md",
    "render_callout",
    "render_html_doc",
]
