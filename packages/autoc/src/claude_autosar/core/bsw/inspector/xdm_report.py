"""DataModel2 (.xdm) one-shot HTML report renderer — Sprint 9.1 — T9.1.3.

读 ``.xdm`` → 扁平化 DataModel2 树 → 出 HTML 报告（metadata +
CanConfigSet / CanGeneral 容器表 + 关键参数列表）。

设计原则（对齐 plan §2.1 / §0.2.3 / §3.2）：

  - **不抽象 InstanceTree** — 每个格式独立解析 / 渲染。
  - **DataModel2 跟 ECUC 不兼容** — 用 ``<d:chc>/<d:ctr>/<d:lst>/<d:var>``
    树直接走 lxml xpath 提取，不走 ``core/bsw/ecuc.py``。
  - **双 namespace**（R4 陷阱）：``d:`` 固定指向 DataModel2 data xsd；
    ``dm:`` 默认 ns 从根 ``xmlns`` 探测（**不要硬编码**）。
  - **复用 _bsw_read_xdm 模式**（:mod:`claude_autosar.cli.mcp_server`）：
    ``d_ns = "http://www.tresos.de/_projects/DataModel2/06/data.xsd"``
    + ``dm_ns = root.nsmap[None]``（探测）+ ``iterancestors`` 防上跳。

公共 API：

  - :func:`render_xdm_report` — 读 .xdm → 渲染 HTML 字符串
  - :func:`export_xdm_report` — 渲染 HTML 报告并写到文件，返回绝对路径

注：CSS 走**内联最小 CSS**（**有意不依赖** :mod:`claude_autosar.utils.html_utils`）。
inspector 报告有 inspector 专属样式（metadata-table / summary-box / type-tag），
跟 session export 走的 ``_CSS`` 模板差异较大；保留独立 CSS 避免相互耦合。
``html.escape`` / URL 白名单 / 三色 callout 等通用 XSS 防御
仍复用 :mod:`utils.html_utils`（如果未来需要）。
"""

from __future__ import annotations

from html import escape as _html_escape
import os
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

#: DataModel2 data namespace (固定 d 前缀)
D_NS = "http://www.tresos.de/_projects/DataModel2/06/data.xsd"

#: DataModel2 root namespace（探测时用，**不要硬编码**到 xpath 字符串外）
DM_ROOT_NS = "http://www.tresos.de/_projects/DataModel2/16/root.xsd"

#: 内联最小 CSS（自包含；离线可开；不依赖 html_utils 模块）
_INLINE_CSS = """
body { font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
       margin: 2em; line-height: 1.5; color: #1a1a1a; }
h1 { border-bottom: 2px solid #444; padding-bottom: 0.3em; }
h2 { margin-top: 1.5em; color: #2a2a2a; border-left: 4px solid #0066cc;
     padding-left: 0.5em; }
table { border-collapse: collapse; margin: 1em 0; width: 100%; }
th, td { border: 1px solid #ccc; padding: 0.4em 0.6em; text-align: left;
         vertical-align: top; }
th { background: #f0f0f0; font-weight: bold; }
tr:nth-child(even) td { background: #fafafa; }
.metadata { background: #f5f5f5; padding: 1em; border-radius: 4px;
            border: 1px solid #ddd; }
.metadata td { border: none; }
.leaf-value-enum { color: #0066cc; font-weight: 500; }
.leaf-value-int { color: #008800; }
.leaf-value-bool { color: #cc6600; }
.leaf-value-str { color: #444; }
.leaf-type { color: #888; font-size: 0.9em; }
.doc-text { color: #555; font-style: italic; margin: 0.3em 0; }
code { background: #f4f4f4; padding: 0.1em 0.3em; border-radius: 2px; }
"""


# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------


def render_xdm_report(path: Path) -> str:
    """读 ``.xdm`` → 扁平化 DataModel2 树 → 渲染完整 HTML 报告。

    :param path: ``.xdm`` 文件路径
    :raises DataModel2Error: 文件不存在 / XML 畸形
    :return: 自包含 HTML 字符串（含 inline CSS；离线可开）
    """
    from claude_autosar.core.bsw.io.datamodel2_io import (
        DataModel2Error,
    )
    from claude_autosar.core.bsw.io.datamodel2_io import read as _xdm_read

    p = Path(path)
    if not p.is_file():
        raise DataModel2Error(f"XDM file not readable: {p}: No such file")

    try:
        tree = _xdm_read(p)
    except DataModel2Error:
        raise
    except (OSError, FileNotFoundError) as e:
        raise DataModel2Error(f"XDM file not readable: {p}: {e}") from e

    root = tree.getroot() if hasattr(tree, "getroot") else tree

    # 探测默认 namespace（R4 陷阱：从根 xmlns 探测，不硬编码）
    nsmap = dict(root.nsmap) if getattr(root, "nsmap", None) else {}
    default_ns = nsmap.get(None, "")

    # 提取模块名（从 <d:chc name=X type=AR-ELEMENT>）
    module_name = _extract_module_name(root, default_ns)
    if module_name is None:
        module_name = "<unknown-module>"

    # 收集容器 + 叶子
    containers, leaves = _flatten_module_tree(root, module_name, default_ns)

    # 关键参数
    file_size = p.stat().st_size
    parts: list[str] = []
    parts.append(_render_html_head(p.name))
    parts.append(f"<h1>DataModel2 Report: {_html_escape(module_name)}</h1>")
    parts.append(_render_metadata(p, default_ns, module_name, file_size))
    parts.append(_render_containers(containers))
    parts.append(_render_leaves(leaves))
    parts.append(_render_html_tail())
    return "".join(parts)


def export_xdm_report(path: Path, output: Path | None = None) -> Path:
    """渲染 HTML 报告并写到文件，返回绝对路径。

    :param path: 输入 ``.xdm`` 路径
    :param output: 输出 HTML 路径；``None`` = 默认 ``<input>.report.html``
    :return: 已写入文件的绝对路径
    :raises DataModel2Error: 读 XDM 失败
    :raises OSError: 写文件失败
    """
    html = render_xdm_report(path)
    out = Path(path).with_name(Path(path).name + ".report.html") if output is None else Path(output)
    out = out.resolve()
    # 原子写：先写 tmp，再 replace；失败时原文件不动
    tmp = out.with_suffix(out.suffix + ".tmp")
    try:
        tmp.write_text(html, encoding="utf-8")
        os.replace(tmp, out)
    except OSError:
        # 清理可能残留的 .tmp
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise
    return out


# ---------------------------------------------------------------------------
# 内部：HTML 渲染块
# ---------------------------------------------------------------------------


def _render_html_head(file_name: str) -> str:
    title = f"XDM Report — {_html_escape(file_name)}"
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        f"<title>{title}</title>\n"
        f"<style>{_INLINE_CSS}</style>\n"
        "</head>\n"
        "<body>\n"
    )


def _render_html_tail() -> str:
    return (
        '<hr><p style="color:#888;font-size:0.85em;">'
        "Generated by claude-autosar xdm-inspect (Sprint 9.1 T9.1.3)"
        "</p>\n"
        "</body>\n"
        "</html>\n"
    )


def _render_metadata(path: Path, default_ns: str, module_name: str, file_size: int) -> str:
    rows: list[str] = []
    rows.append(_kv_row("Path", f"<code>{_html_escape(str(path.resolve()))}</code>"))
    rows.append(_kv_row("Format", "DataModel2 (.xdm)"))
    rows.append(_kv_row("Default namespace", _html_escape(default_ns or "<none>")))
    rows.append(_kv_row("Module", f"<code>{_html_escape(module_name)}</code>"))
    rows.append(_kv_row("File size", f"{file_size} bytes"))
    return (
        '<div class="metadata">\n'
        "<h2>Metadata</h2>\n"
        '<table class="metadata-table">\n' + "".join(rows) + "</table>\n"
        "</div>\n"
    )


def _render_containers(containers: list[dict[str, str]]) -> str:
    if not containers:
        return "<p><em>No top-level containers detected.</em></p>\n"
    rows: list[str] = []
    for c in containers:
        name = _html_escape(c["name"])
        ctype = _html_escape(c.get("type", ""))
        doc = _html_escape(c.get("doc", "") or "")
        path = _html_escape(c.get("path", ""))
        rows.append(
            "<tr>"
            f"<td><code>{name}</code></td>"
            f"<td>{ctype}</td>"
            f"<td><code>{path}</code></td>"
            f"<td class='doc-text'>{doc}</td>"
            "</tr>"
        )
    return (
        "<h2>Top-Level Containers</h2>\n"
        "<table>\n"
        "<thead><tr><th>Name</th><th>Type</th><th>Path</th>"
        "<th>Description</th></tr></thead>\n"
        "<tbody>\n" + "".join(rows) + "</tbody>\n"
        "</table>\n"
    )


def _render_leaves(leaves: list[dict[str, str]]) -> str:
    if not leaves:
        return "<p><em>No leaf variables detected.</em></p>\n"
    # 按 path 排序（同 prefix 的叶子聚在一起）
    leaves_sorted = sorted(leaves, key=lambda leaf: leaf["path"])
    rows: list[str] = []
    for leaf in leaves_sorted:
        path = _html_escape(leaf["path"])
        name = _html_escape(leaf["name"])
        vtype = _html_escape(leaf.get("type", "") or "")
        value = _html_escape(leaf.get("value", "") or "")
        css_class = _value_css_class(leaf.get("type", ""))
        rows.append(
            "<tr>"
            f"<td><code>{path}</code></td>"
            f"<td>{name}</td>"
            f"<td class='leaf-type'>{vtype}</td>"
            f"<td class='{css_class}'>{value}</td>"
            "</tr>"
        )
    return (
        "<h2>Leaf Variables</h2>\n"
        "<table>\n"
        "<thead><tr><th>Path</th><th>Name</th><th>Type</th>"
        "<th>Value</th></tr></thead>\n"
        "<tbody>\n" + "".join(rows) + "</tbody>\n"
        "</table>\n"
    )


def _kv_row(k: str, v: str) -> str:
    return f"<tr><th>{_html_escape(k)}</th><td>{v}</td></tr>\n"


def _value_css_class(vtype: str) -> str:
    """根据 vtype 给 value cell 一个 CSS class（颜色编码）。"""
    t = (vtype or "").upper()
    if t == "ENUMERATION":
        return "leaf-value-enum"
    if t == "INTEGER":
        return "leaf-value-int"
    if t == "BOOLEAN":
        return "leaf-value-bool"
    return "leaf-value-str"


# ---------------------------------------------------------------------------
# 公共 API：DataModel2 树提取（Sprint 11 T11.4 提取）
# ---------------------------------------------------------------------------


def extract_module_name(root: Any, default_ns: str) -> str | None:
    """找 ``<d:chc name=X type=AR-ELEMENT>`` 返回 X。"""
    return _extract_module_name(root, default_ns)


def flatten_module_tree(
    root: Any, module_name: str, default_ns: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """扁平化 DataModel2 树，返回 (containers, leaves)。"""
    return _flatten_module_tree(root, module_name, default_ns)


# ---------------------------------------------------------------------------
# 内部：DataModel2 树扁平化
# ---------------------------------------------------------------------------


def _extract_module_name(root: Any, default_ns: str) -> str | None:
    """找 ``<d:chc name=X type=AR-ELEMENT>`` 返回 X。"""
    namespaces: dict[str, str] = {"d": D_NS}
    if default_ns:
        namespaces["dm"] = default_ns
    elems = root.xpath('.//d:chc[@type="AR-ELEMENT"]/@name', namespaces=namespaces)
    if elems:
        first = elems[0]
        if isinstance(first, str):
            return first
        # lxml may return _ElementUnicodeResult (str-compatible)
        return str(first)
    return None


def _flatten_module_tree(
    root: Any, module_name: str, default_ns: str
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """扁平化 ``<d:chc name=module>`` 下的树。

    返回:
      - containers: 第一层 ``<d:ctr name=X>`` / ``<d:lst name=X>``
                    （含 ``<d:doc>`` 子节点文本如果存在）
      - leaves: 所有叶子 ``<d:var name=X type=Y value=Z>``（含路径前缀）
    """
    namespaces: dict[str, str] = {"d": D_NS}
    if default_ns:
        namespaces["dm"] = default_ns

    # 1) 找 module root
    module_elems = root.xpath(f'.//d:chc[@name="{module_name}"]', namespaces=namespaces)
    if not module_elems:
        return [], []
    module_elem = module_elems[0]

    # 2) 第一层 container（d:ctr / d:lst with name attr），在 module 之下
    containers: list[dict[str, str]] = []
    seen_container_paths: set[str] = set()
    first_layer = module_elem.xpath(".//d:ctr[@name] | .//d:lst[@name]", namespaces={"d": D_NS})
    for ctr in first_layer:
        # 用 iterancestors 检查 ctr 是 module_elem 的后代（防 xpath 上跳）
        if not _is_descendant_of(ctr, module_elem):
            continue
        cname = ctr.get("name", "")
        ctype = ctr.get("type", "")
        # 取 <d:doc> 子节点文本（如有）
        doc_text = _extract_doc_text(ctr)
        # 计算 path（这里用 module/ctrname）
        path = f"{module_name}/{cname}"
        if path in seen_container_paths:
            continue
        seen_container_paths.add(path)
        containers.append({"name": cname, "type": ctype, "doc": doc_text, "path": path})

    # 3) 所有叶子 <d:var>，含路径
    leaves: list[dict[str, str]] = []
    var_elems = module_elem.xpath(".//d:var[@name]", namespaces={"d": D_NS})
    for var in var_elems:
        if not _is_descendant_of(var, module_elem):
            continue
        vname = var.get("name", "")
        vtype = var.get("type", "")
        value = var.get("value", "")
        # 路径：module/<container...>/<varname>
        path = _build_path(var, module_name)
        leaves.append({"name": vname, "type": vtype, "value": value, "path": path})

    return containers, leaves


def _extract_doc_text(elem: Any) -> str:
    """取 ``<d:doc>`` 子节点文本（如果存在）。"""
    doc_elems = elem.xpath("./d:doc", namespaces={"d": D_NS})
    if not doc_elems:
        return ""
    text = "".join(doc_elems[0].itertext()).strip()
    return text


def _build_path(leaf: Any, module_name: str) -> str:
    """从 leaf 向上 walk ancestors，收集 ``name`` 属性，拼成路径。

    例: ``Can/CanConfigSet/CanController/CanHwChannel``
    """
    parts: list[str] = [module_name]
    # lxml iterancestors() 从近到远；我们要从远到近
    ancestors = list(leaf.iterancestors())
    # 倒序（从 root 一侧开始）
    ancestors.reverse()
    for anc in ancestors:
        # 跳过 module_elem（name 已在外），跳过非 d 前缀的（防 root）
        # 简化：只接受有 name 属性且 d: namespace 的元素
        if not isinstance(anc.tag, str):
            continue
        # lxml tag 形如 "{ns}local"
        tag = anc.tag
        if not tag.startswith(f"{{{D_NS}}}"):
            continue
        anc_name = anc.get("name")
        if anc_name and anc_name != module_name:
            parts.append(anc_name)
    parts.append(leaf.get("name", ""))
    return "/".join(p for p in parts if p)


def _is_descendant_of(candidate: Any, ancestor: Any) -> bool:
    """判断 ``candidate`` 是否是 ``ancestor`` 的后代（lxml ``iterancestors``）。"""
    try:
        return any(a is ancestor for a in candidate.iterancestors())
    except (AttributeError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Sprint 9.3 T9.3-γ — verify section 嵌入（独立切片）
# ---------------------------------------------------------------------------


def render_xdm_report_with_verify(
    path: Path,
    verify_issues: tuple[Any, ...] = (),
    verify_returncode: int = 0,
) -> str:
    """Sprint 9.3 T9.3-γ 入口：渲染 xdm 报告 + 嵌入 verify section HTML。

    Parameters
    ----------
    path:
        输入 ``.xdm`` 文件路径。
    verify_issues:
        :class:`TresosVerifyIssue` 元组（duck-typing）；
        空 + returncode=0 → 不嵌入 verify section。
    verify_returncode:
        tresos_cmd returncode；非 0 即使 issues 空也会嵌入（标记失败）。

    Returns
    -------
    str:
        完整 HTML 报告（含 verify section 嵌入到 ``</body>`` 之前）。

    Notes
    -----
    * 不重写 :func:`render_xdm_report` 既有逻辑；本函数走
      ``render_xdm_report`` → 字符串拼接 verify section。
    * 嵌入失败（``</body>`` 不规整）→ graceful fallback：直接
      ``base + section`` 拼接（section 可能在 HTML 之外，但保留内容）。
    """
    base = render_xdm_report(path)
    if not verify_issues and verify_returncode == 0:
        return base
    # 延迟导入：避免 verify 包未实现时影响 xdm_report 自身 import
    from claude_autosar.core.bsw.verify.report_section import (
        render_verify_section_html,
    )

    section = render_verify_section_html(
        verify_issues,
        returncode=verify_returncode,
    )
    # 尝试插入到 </body> 之前；找不到 → 简单拼接
    if "</body>" in base:
        return base.replace("</body>", section + "</body>", 1)
    return base + section


__all__ = [
    "render_xdm_report",
    "export_xdm_report",
    "render_xdm_report_with_verify",
    "render_xdm_report_with_lint",
]


# ---------------------------------------------------------------------------
# Sprint 9.4 T9.4-β — lint section 嵌入（独立切片；不动 9.3-γ 的 verify）
# ---------------------------------------------------------------------------
# 给 9.4-β MCP `xdm_inspect(..., include_lint=True)` / CLI `xdm-inspect
# --lint` 复用。**append-only**：不改既有 `render_xdm_report` / 9.3-γ
# `render_xdm_report_with_verify`，独立渲染函数只在 base HTML 后追加
# lint section（reuse `summary-box` + violations table；XSS 走
# :func:`html.escape`）。duck-typed violations 同 arxml_report 注释。


def _render_xdm_lint_section_html(violations: tuple[Any, ...]) -> str:
    """Sprint 9.4-β：渲染 xdm 报告底部嵌入的 lint section。"""
    if not violations:
        return ""

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
        rule_id = _html_escape(str(getattr(v, "rule_id", "")))
        severity = _html_escape(str(getattr(v, "severity", "")))
        message = _html_escape(str(getattr(v, "message", "")))
        path_str = _html_escape(str(getattr(v, "path", "") or "-"))
        line_raw = getattr(v, "line", None)
        line_str = _html_escape("" if line_raw is None else str(line_raw))
        rows.append(
            "<tr>"
            f"<td>{rule_id}</td>"
            f"<td>{severity}</td>"
            f"<td>{path_str}:{line_str}</td>"
            f"<td>{message}</td>"
            "</tr>"
        )

    return (
        '<section class="lint-section">\n'
        "<h2>Lint Violations</h2>\n"
        '<div class="summary-box">\n'
        f"<strong>{len(violations)}</strong> violation(s)\n"
        "</div>\n"
        "<table>\n"
        "<thead><tr><th>Rule</th><th>Severity</th><th>Location</th>"
        "<th>Message</th></tr></thead>\n"
        "<tbody>\n" + "\n".join(rows) + "\n</tbody>\n"
        "</table>\n"
        "</section>\n"
    )


def render_xdm_report_with_lint(
    path: Path,
    violations: tuple[Any, ...] = (),
) -> str:
    """Sprint 9.4 T9.4-β 入口：xdm 报告 + lint section 嵌入。

    :param path: ``.xdm`` 文件路径
    :param violations: duck-typed lint violations；空 → 不嵌入 lint section
    :return: 自包含 HTML 字符串
    """
    base = render_xdm_report(path)
    if not violations:
        return base
    section = _render_xdm_lint_section_html(violations)
    if "</body>" in base:
        return base.replace("</body>", section + "</body>", 1)
    return base + "\n" + section
