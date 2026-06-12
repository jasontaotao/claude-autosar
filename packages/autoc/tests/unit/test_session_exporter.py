"""T4.3 — HTML exporter 单元测试。"""

from __future__ import annotations

from pathlib import Path
import re

from autoc.core.session.exporter import export_html, render_html
from autoc.core.session.store import Session, SessionEntry
from autoc.core.session.tree import SessionTree


def _user(
    eid: str, parent: str | None, session: str, content: str, ts: str = "2026-06-11T00:00:00.000Z"
) -> SessionEntry:
    return SessionEntry(
        id=eid,
        parent_id=parent,
        session_id=session,
        timestamp=ts,
        kind="user",
        content=content,
    )


def _tool_bsw(
    eid: str,
    parent: str,
    session: str,
    *,
    module: str,
    path: str,
    op: str,
    value: object,
    old_value: object = None,
    ts: str,
) -> SessionEntry:
    return SessionEntry(
        id=eid,
        parent_id=parent,
        session_id=session,
        timestamp=ts,
        kind="tool",
        content="bsw_write",
        tool_name="bsw_write",
        tool_args={
            "module": module,
            "path": path,
            "op": op,
            "value": value,
            "old_value": old_value,
        },
        tool_result="ok",
    )


def _build_tree(entries: list[SessionEntry], *, title: str = "") -> SessionTree:
    return SessionTree(
        session=Session(
            id=entries[0].session_id if entries else "s1",
            started_at=entries[0].timestamp if entries else "",
            title=title,
            entries=tuple(entries),
        )
    )


# ---------------------------------------------------------------------------
# 基本结构
# ---------------------------------------------------------------------------


def test_render_html_returns_self_contained_html() -> None:
    """render_html 返回有效 HTML 字符串：DOCTYPE + <html> + 包含 session id。"""
    tree = _build_tree([_user("u1", None, "s1", "hello")])
    html = render_html(tree)
    assert "<!DOCTYPE" in html or "<!doctype" in html.lower()
    assert "<html" in html.lower()
    assert "s1" in html  # session id 出现


def test_render_html_self_contained_no_external_url() -> None:
    """自包含：无 http:// 或 https:// 外部资源引用（inline CSS only）。"""
    tree = _build_tree([_user("u1", None, "s1", "hello")])
    html = render_html(tree)
    # 排除 xmlns 之类的标准命名空间
    cleaned = re.sub(r'xmlns(:\w+)?="[^"]*"', "", html)
    assert "http://" not in cleaned, "found http:// in HTML"
    assert "https://" not in cleaned, "found https:// in HTML"


def test_render_html_empty_tree() -> None:
    """空 tree 也能渲染（不抛）。"""
    tree = SessionTree(session=Session(id="empty", started_at=""))
    html = render_html(tree)
    assert isinstance(html, str)
    assert "<html" in html.lower()
    assert "empty" in html


# ---------------------------------------------------------------------------
# 内容渲染
# ---------------------------------------------------------------------------


def test_render_html_includes_entry_content() -> None:
    """entry 的 content 必须出现在 HTML 中。"""
    tree = _build_tree([_user("u1", None, "s1", "帮我配置 Mcu 时钟到 80MHz")])
    html = render_html(tree)
    assert "帮我配置 Mcu 时钟到 80MHz" in html


def test_render_html_escapes_xss_payload() -> None:
    """XSS 注入测试：content 中的 <script> 必须被转义。"""
    payload = '<script>alert("xss")</script>'
    tree = _build_tree([_user("u1", None, "s1", payload)])
    html = render_html(tree)
    # 转义后 < > 变 &lt; &gt;；原始字符串不应出现
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html


# ---------------------------------------------------------------------------
# 改参 callout 三色
# ---------------------------------------------------------------------------


def test_render_html_bsw_write_callout_green_for_add() -> None:
    """op=add 的 bsw_write 渲染为绿色 callout。"""
    tree = _build_tree(
        [
            _user("u1", None, "s1", "新增"),
            _tool_bsw(
                "t1",
                "u1",
                "s1",
                module="Mcu",
                path="ClockFreq",
                op="add",
                value=80000000,
                ts="2026-06-11T00:00:01.000Z",
            ),
        ]
    )
    html = render_html(tree)
    assert 'class="callout add"' in html or "callout-add" in html
    assert "Mcu/ClockFreq" in html
    assert "80000000" in html


def test_render_html_bsw_write_callout_yellow_for_modify() -> None:
    """op=modify 的 bsw_write 渲染为黄色 callout。"""
    tree = _build_tree(
        [
            _user("u1", None, "s1", "改"),
            _tool_bsw(
                "t1",
                "u1",
                "s1",
                module="Mcu",
                path="ClockFreq",
                op="modify",
                value=80,
                old_value=40,
                ts="2026-06-11T00:00:01.000Z",
            ),
        ]
    )
    html = render_html(tree)
    assert "callout" in html
    assert "modify" in html  # class 标识


def test_render_html_bsw_write_callout_red_for_delete() -> None:
    """op=delete 的 bsw_write 渲染为红色 callout。"""
    tree = _build_tree(
        [
            _user("u1", None, "s1", "删"),
            _tool_bsw(
                "t1",
                "u1",
                "s1",
                module="Mcu",
                path="ClockFreq",
                op="delete",
                value=None,
                old_value=80,
                ts="2026-06-11T00:00:01.000Z",
            ),
        ]
    )
    html = render_html(tree)
    assert "callout" in html
    assert "delete" in html  # class 标识


# ---------------------------------------------------------------------------
# Markdown 渲染
# ---------------------------------------------------------------------------


def test_render_html_supports_inline_markdown() -> None:
    """轻量 Markdown：**bold** + `code` + [link](url) 必须渲染。"""
    md_content = (
        "Use **Mcu** module, set `ClockFreq=80`, see [docs](http://example.com) for details"
    )
    tree = _build_tree([_user("u1", None, "s1", md_content)])
    html = render_html(tree)
    assert "<strong>Mcu</strong>" in html
    assert "<code>ClockFreq=80</code>" in html
    assert '<a href="http://example.com"' in html or 'href="http://example.com"' in html


def test_render_html_blocks_javascript_url_xss() -> None:
    """XSS 防御：markdown link URL scheme 必须在白名单内，否则只渲染 link text。"""
    md_content = "[click me](javascript:alert('xss'))"
    tree = _build_tree([_user("u1", None, "s1", md_content)])
    html = render_html(tree)
    # href 中的 javascript: 必须不存在
    assert 'href="javascript:' not in html
    assert "href='javascript:" not in html
    # scheme 拒绝时只保留 link text
    assert "click me" in html


def test_render_html_blocks_data_and_vbscript_url() -> None:
    """data: 与 vbscript: scheme 也必须被拒绝。"""
    for url in ("data:text/html,<script>alert(1)</script>", "vbscript:msgbox(1)"):
        tree = _build_tree([_user("u1", None, "s1", f"[x]({url})")])
        html = render_html(tree)
        assert "href=" not in html or 'href="data:' not in html
        assert 'href="vbscript:' not in html


def test_render_html_adds_rel_noopener_noreferrer() -> None:
    """安全 link 必须带 rel='noopener noreferrer'（防 tabnabbing）。"""
    tree = _build_tree([_user("u1", None, "s1", "[a](https://example.com)")])
    html = render_html(tree)
    assert 'rel="noopener noreferrer"' in html


# ---------------------------------------------------------------------------
# export_html (写文件)
# ---------------------------------------------------------------------------


def test_export_html_writes_file(tmp_path: Path) -> None:
    """export_html 写出文件，返回路径，文件含 <html 标签。"""
    tree = _build_tree([_user("u1", None, "abc123", "hello")])
    out = tmp_path / "out.html"
    result = export_html(tree, out)
    assert result == out
    assert out.is_file()
    content = out.read_text(encoding="utf-8")
    assert "<html" in content.lower()
    assert "abc123" in content


def test_export_html_creates_parent_dir(tmp_path: Path) -> None:
    """输出目录不存在时自动创建。"""
    tree = _build_tree([_user("u1", None, "s1", "x")])
    out = tmp_path / "subdir" / "deep" / "out.html"
    export_html(tree, out)
    assert out.is_file()
