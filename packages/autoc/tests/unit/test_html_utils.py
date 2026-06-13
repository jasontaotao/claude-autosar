"""Sprint 9.1 T9.1.1 — ``utils.html_utils`` 单元测试。

覆盖：
- 5 类 XSS 攻击字符串全 escape（script / javascript: URL / 双引号 / 实体 / 引号嵌套）
- 三色 callout（add / modify / delete + 非法 op 降级）
- URL scheme 白名单（http/https/mailto/file 通过；javascript/data/vbscript 拒）
- inline md 渲染（link / code / bold / 嵌套）
- render_html_doc 组装（标题 / body / footer / css 注入）

按 plan §T9.1.1 与 §Verification 第 4 项硬指标。
"""

from __future__ import annotations

import re

import pytest

from claude_autosar.utils.html_utils import (
    ALLOWED_URL_SCHEMES,
    is_safe_url,
    render_callout,
    render_html_doc,
    render_inline_md,
)


# =============================================================================
# URL scheme 白名单 — 11 个 case
# =============================================================================


@pytest.mark.parametrize(
    "url, expected",
    [
        # 通过的白名单 scheme
        ("http://example.com", True),
        ("https://example.com/path?x=1", True),
        ("mailto:user@example.com", True),
        ("file:///C:/Users/test/file.html", True),
        # 大小写不敏感
        ("HTTPS://EXAMPLE.COM", True),
        ("Http://example.com", True),
        # 拒绝的 scheme
        ("javascript:alert(1)", False),
        ("JavaScript:alert(1)", False),
        ("data:text/html,<script>alert(1)</script>", False),
        ("vbscript:msgbox(1)", False),
        ("file-no-scheme-relative/path", False),
    ],
)
def test_is_safe_url(url: str, expected: bool) -> None:
    assert is_safe_url(url) is expected


def test_allowed_url_schemes_constant() -> None:
    """ALLOWED_URL_SCHEMES 必须包含 4 个 scheme，顺序固定。"""
    assert ALLOWED_URL_SCHEMES == ("http://", "https://", "mailto:", "file:")


def test_is_safe_url_strips_whitespace() -> None:
    """URL 前后空白应被忽略（scheme 探测时）。"""
    assert is_safe_url("  https://example.com  ") is True
    assert is_safe_url("\tjavascript:alert(1)\n") is False


# =============================================================================
# XSS escape — 5 类攻击字符串
# =============================================================================


# --- 类 1：<script>alert(1)</script> ---


def test_render_inline_md_escapes_script_in_text() -> None:
    """text 中的 <script>alert(1)</script> 必须 escape（标签破坏）。"""
    out = render_inline_md("<script>alert(1)</script>")
    assert "<script>alert" not in out
    assert "&lt;script&gt;alert" in out
    assert "alert(1)" in out  # 文本内容保留


def test_render_callout_escapes_script_in_label() -> None:
    """label 中的 <script>alert(1)</script> 必须 escape。"""
    out = render_callout("add", "<script>alert(1)</script>")
    assert "<script>alert" not in out
    assert "&lt;script&gt;alert" in out


def test_render_callout_escapes_script_in_detail() -> None:
    """detail 中的 <script>alert(1)</script> 必须 escape。"""
    out = render_callout("modify", "x", "<script>alert(1)</script>")
    assert "<script>alert" not in out
    assert "&lt;script&gt;alert" in out


# --- 类 2：javascript: URL ---


def test_render_inline_md_rejects_javascript_url() -> None:
    """[link](javascript:...) 必须只显示 link text，href 不出现。"""
    out = render_inline_md("[click](javascript:alert(1))")
    assert "href=" not in out
    assert "javascript:" not in out
    assert "click" in out


# --- 类 3：双引号 "onerror="alert(1) ---


def test_render_inline_md_escapes_quote_in_text() -> None:
    """text 中的双引号必须 escape（防 attribute breakout）。"""
    out = render_inline_md('"onerror="alert(1)')
    assert '"onerror="alert(1)' not in out
    assert "&quot;onerror=&quot;alert(1)" in out


def test_render_callout_escapes_quote_in_label() -> None:
    """label 中的双引号必须 escape。"""
    out = render_callout("delete", 'evil"injection')
    assert 'evil"injection' not in out
    assert "evil&quot;injection" in out


# --- 类 4：HTML 实体 & < > " ---


def test_render_inline_md_escapes_ampersand() -> None:
    """& 必须转义为 &amp;（包括双重转义：&amp; → &amp;amp;）。"""
    out = render_inline_md("&")
    assert "&amp;" in out
    assert "&" not in out.replace("&amp;", "").replace("&lt;", "").replace(
        "&gt;", ""
    ).replace("&quot;", "")


def test_render_inline_md_escapes_lt_gt() -> None:
    """< > 必须转义为 &lt; &gt;。"""
    out = render_inline_md("<tag>")
    assert "&lt;tag&gt;" in out
    assert "<tag>" not in out


def test_render_inline_md_escapes_double_quote() -> None:
    """双引号必须转义为 &quot;。"""
    out = render_inline_md('"quoted"')
    assert "&quot;quoted&quot;" in out
    # 原始未转义双引号不应出现（占位符还原前后都不行）
    assert '"quoted"' not in out


def test_render_inline_md_mixed_entities() -> None:
    """混合 & < > 全部 escape。"""
    out = render_inline_md("1 < 2 & 3 > 0")
    assert "1 &lt; 2 &amp; 3 &gt; 0" in out


def test_render_callout_escapes_html_entities() -> None:
    """callout label/detail 也要 escape HTML 实体。"""
    out = render_callout("modify", "<&>", '"d"')
    assert "<&>" not in out
    assert "&lt;&amp;&gt;" in out
    assert '"d"' not in out


# --- 类 5：引号嵌套 "foo"bar"baz" ---


def test_render_inline_md_handles_nested_quotes() -> None:
    """引号嵌套不破坏 link 渲染（quote=True 让 href 也 escape）。"""
    out = render_inline_md('[a"b"c](https://example.com/?q="x")')
    # link 标签必须存在（说明 attribute 未被注入破坏）
    assert "<a href=" in out
    assert 'rel="noopener noreferrer"' in out
    # href 中双引号应被 html.escape(quote=True) 处理
    assert 'href="https://example.com/?q=&quot;x&quot;"' in out


# =============================================================================
# 三色 callout — 5 个 case
# =============================================================================


def test_render_callout_add_is_green() -> None:
    """op=add → class="callout add"。"""
    out = render_callout("add", "Mcu/ClockFreq", "= 80000000")
    assert 'class="callout add"' in out
    assert "Mcu/ClockFreq" in out


def test_render_callout_modify_is_yellow() -> None:
    """op=modify → class="callout modify"。"""
    out = render_callout("modify", "Mcu/ClockFreq", "40 → 80")
    assert 'class="callout modify"' in out


def test_render_callout_delete_is_red() -> None:
    """op=delete → class="callout delete"。"""
    out = render_callout("delete", "Mcu/ClockFreq", "(was: 80)")
    assert 'class="callout delete"' in out


def test_render_callout_unknown_op_falls_back_to_modify() -> None:
    """非法 op 应降级为 modify（黄色），不抛错。"""
    out = render_callout("weird_op", "Mcu/X")
    assert 'class="callout modify"' in out


def test_render_callout_empty_detail_no_trailing_space() -> None:
    """detail 为空字符串时不留额外空格。"""
    out = render_callout("add", "Mcu/ClockFreq")
    assert 'class="callout add"' in out
    # 不应有尾部空格（在 div 关闭前）
    assert "add\">Mcu/ClockFreq</div>" in out


# =============================================================================
# inline md 渲染 — 5 个 case
# =============================================================================


def test_render_inline_md_link_safe() -> None:
    """[link](http://...) 必须渲染为带 rel 的 <a>。"""
    out = render_inline_md("[docs](http://example.com)")
    assert '<a href="http://example.com"' in out
    assert 'rel="noopener noreferrer"' in out
    assert ">docs</a>" in out


def test_render_inline_md_bold() -> None:
    """**bold** 必须渲染为 <strong>。"""
    out = render_inline_md("use **Mcu** module")
    assert "<strong>Mcu</strong>" in out


def test_render_inline_md_code() -> None:
    """`code` 必须渲染为 <code>。"""
    out = render_inline_md("set `ClockFreq=80`")
    assert "<code>ClockFreq=80</code>" in out


def test_render_inline_md_combined() -> None:
    """bold + code + link 一起渲染（验证阶段顺序不互相破坏）。"""
    md = "Use **Mcu** set `Freq=80` see [docs](http://x.com)"
    out = render_inline_md(md)
    assert "<strong>Mcu</strong>" in out
    assert "<code>Freq=80</code>" in out
    assert '<a href="http://x.com"' in out


def test_render_inline_md_newline_to_br() -> None:
    """行内换行 \\n → <br>（单换行）。"""
    out = render_inline_md("line1\nline2")
    assert "line1<br>line2" in out


def test_render_inline_md_link_in_text_preserves_surrounding() -> None:
    """link 周围的纯文本应被 escape 后保留。"""
    out = render_inline_md("see [docs](http://x.com) now")
    assert "see " in out
    assert " now" in out


# =============================================================================
# render_html_doc 组装 — 6 个 case
# =============================================================================


def test_render_html_doc_minimal() -> None:
    """最小调用：title + 空 body + 无 footer → 仍输出有效 HTML 骨架。"""
    out = render_html_doc(title="Test", body_parts=[])
    assert out.startswith("<!DOCTYPE html>")
    assert '<html lang="zh-CN">' in out
    assert "<title>Test</title>" in out
    assert "<body>" in out
    assert "</body></html>" in out
    assert out.endswith("\n")


def test_render_html_doc_body_parts_joined() -> None:
    """body_parts 多段必须按顺序嵌入 <body>。"""
    out = render_html_doc(
        title="T",
        body_parts=["<h1>x</h1>", "<p>a</p>", "<p>b</p>"],
    )
    # body 内顺序：h1 在 p a 前，p a 在 p b 前
    body_start = out.index("<body>")
    body_end = out.index("</body>")
    body = out[body_start:body_end]
    assert body.index("<h1>x</h1>") < body.index("<p>a</p>") < body.index("<p>b</p>")


def test_render_html_doc_includes_default_css() -> None:
    """不传 css 参数时使用内置 _CSS（包含 .callout.add 规则）。"""
    out = render_html_doc(title="T", body_parts=[])
    assert "<style>" in out
    assert ".callout.add" in out  # 内置 CSS 特征
    assert "</style>" in out


def test_render_html_doc_custom_css_replaces_default() -> None:
    """传 css 参数时用自定义 CSS（不包含默认 .callout.add 规则）。"""
    custom = "body { background: red; }"
    out = render_html_doc(title="T", body_parts=[], css=custom)
    assert "background: red" in out
    assert ".callout.add" not in out  # 默认 CSS 已被替换


def test_render_html_doc_footer_appears_in_body() -> None:
    """footer 字符串必须出现在 body 内部、</body> 之前。"""
    out = render_html_doc(
        title="T",
        body_parts=["<p>main</p>"],
        footer='<div class="footer">F</div>',
    )
    body_start = out.index("<body>")
    body_end = out.index("</body>")
    body = out[body_start:body_end]
    assert body.index("<p>main</p>") < body.index('<div class="footer">F</div>')


def test_render_html_doc_empty_footer_skips_block() -> None:
    """footer 为空字符串时不插入任何额外块。"""
    out = render_html_doc(title="T", body_parts=["<p>x</p>"], footer="")
    # body 内部应只有 <p>x</p>（不再附加空 footer）
    body_start = out.index("<body>")
    body_end = out.index("</body>")
    body = out[body_start:body_end]
    # body 内容应只含 <p>x</p> 一个片段
    assert "<p>x</p>" in body
    assert "footer" not in body
    assert body.count("<p>") == 1


# =============================================================================
# 集成 / 回归 — 1 个 case
# =============================================================================


def test_render_inline_md_url_quote_attr_safe_for_xss() -> None:
    """href 中含双引号场景下，html.escape(quote=True) 应处理。

    注意：URL 中不能有空白（markdown link regex ``[^)\\s]+`` 拒绝），
    所以使用 ``/`` 替代 `` `` 模拟 attribute breakout 攻击。
    """
    # URL 含双引号（构造 attribute breakout 攻击；用 / 代替空格避免 markdown regex 拒绝）
    out = render_inline_md('[x](http://a.com/?q="/><img/src=x/onerror=alert(1)>)')
    # link 必须存在且 href 内双引号已 escape
    assert '<a href="http://a.com/?q=' in out
    # 关键：href 属性值内的双引号必须为 &quot;
    # 否则双引号会破坏 <a href="..."> 边界注入新属性
    assert '<img' not in out  # img 标签不应被注入
    # 整个 href 字符串应被 escape 包裹
    href_match = re.search(r'href="([^"]*)"', out)
    assert href_match is not None
    # href 内部不应再含未转义双引号
    assert '"' not in href_match.group(1)


# =============================================================================
# 导入路径（re-export）— 2 个 case
# =============================================================================


def test_utils_package_exports_html_utils() -> None:
    """utils/__init__.py 必须 re-export 公共 API。"""
    from claude_autosar.utils import (
        render_callout as rc,
        render_html_doc as rhd,
        render_inline_md as rim,
    )

    # 同一个函数引用（不是同名别名）
    from claude_autosar.utils import html_utils

    assert rc is html_utils.render_callout
    assert rhd is html_utils.render_html_doc
    assert rim is html_utils.render_inline_md
