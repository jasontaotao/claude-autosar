"""AUTOSAR (.arxml) one-shot HTML report renderer — Sprint 9.1 — T9.1.2.

读 ``.arxml`` → 解析 ECUC 值树 → 出 HTML 报告（metadata + IPdu 表 +
Signal 表 + 关键参数容器如 ComGeneral）。

设计原则（对齐 plan §2.1 / §3.2 + R1-R3 风险）：

  - **不抽象 InstanceTree** — 独立解析 / 渲染，inspector 不引入新 ECUC walker
  - **复用 :mod:`core.bsw.arxml_io`** 低层 helpers（``read`` / ``find_elements``
    / ``get_child_text`` / ``detect_namespaces``），不绕过它们直接调 lxml
  - **IPdu / Signal 提取走 lxml xpath**（R3）— 不走 :mod:`core.bsw.ecuc` 高层
    walker（ECUC walker 对 Com/Signal 不通用）
  - **流式 + 8.6MB 可用 RAM**（R1）— 直接用 :func:`arxml_io.read`，lxml
    recovery parser + huge_tree 已 work（8.E.1 / 8.E.5 验过）

公共 API：

  - :func:`render_arxml_report` — 读 .arxml → 渲染 HTML 字符串
  - :func:`export_arxml_report` — 渲染 HTML 报告并写到文件，返回绝对路径

注：CSS 走**内联最小 CSS**（**有意不依赖** :mod:`claude_autosar.utils.html_utils`）。
inspector 报告有 inspector 专属样式（metadata-table / summary-box / type-tag /
ipdu-row / signal-row），跟 session export 走的 ``_CSS`` 模板差异较大；
保留独立 CSS 避免相互耦合。``html.escape`` 等通用 XSS 防御
仍走 :mod:`utils.html_utils`（如果未来需要）。
"""

from __future__ import annotations

from html import escape as _html_escape
import os
from pathlib import Path
from typing import Any

from claude_autosar.core.bsw.arxml_io import (
    ARXMLError,
    detect_namespaces,
    get_child_text,
)
from claude_autosar.core.bsw.arxml_io import read as _arxml_read

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

#: IPdu 容器 SHORT-NAME 列表（AUTOSAR Com 标准 + EAS 私有变种）。
#: 涵盖 Com / EAS / EB 私有命名空间下所有 IPdu 容器命名变体。
_IPDU_SHORT_NAMES: frozenset[str] = frozenset({"ComIPdu", "ComTxIPdu", "ComRxIPdu"})

#: Signal 容器 SHORT-NAME 列表（涵盖 Com 标准 + EAS 私有变种）。
_SIGNAL_SHORT_NAMES: frozenset[str] = frozenset({"ComSignal", "ComGroupSignal"})

#: IPdu 关键参数（按需提取的 leaf 文本）。
_IPDU_PARAM_TAGS: tuple[str, ...] = (
    "ComIPduHandleId",
    "ComIPduLength",
    "ComIPduCanId",
    "ComIPduDirection",
    "ComTxIPduHandleId",
    "ComTxIPduLength",
    "ComTxIPduCanId",
    "ComTxIPduDirection",
    "ComRxIPduHandleId",
    "ComRxIPduLength",
    "ComRxIPduCanId",
    "ComRxIPduDirection",
)

#: Signal 关键参数。
_SIGNAL_PARAM_TAGS: tuple[str, ...] = (
    "ComBitPosition",
    "ComBitSize",
    "ComSignalByteOrder",
    "ComSignalInitValue",
    "ComSignalLength",
    "ComSignalType",
)

#: 内联最小 CSS（自包含；离线可开；覆盖 IPdu / Signal 表样式）
_INSPECTOR_CSS = """
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
.kv-param th { width: 25%; }
.tag { font-family: ui-monospace, Menlo, Consolas, monospace;
       font-size: 0.9em; color: #444; }
.tag-missing { color: #999; font-style: italic; }
.summary-box { background: #fffbe6; border: 1px solid #ffe58f;
               padding: 0.6em 0.9em; border-radius: 4px; margin: 0.5em 0; }
.summary-box strong { color: #ad6800; }
""".strip()


# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------


def render_arxml_report(path: Path) -> str:
    """读 ``.arxml`` → 解析 ECUC 值树 → 渲染完整 HTML 报告。

    :param path: ``.arxml`` 文件路径
    :raises ARXMLError: 文件不存在 / XML 畸形 / 根 namespace 非 AUTOSAR
    :return: 自包含 HTML 字符串（含 inline CSS；离线可开）
    """
    p = Path(path)
    if not p.is_file():
        raise ARXMLError(f"ARXML file not readable: {p}: No such file")

    try:
        doc = _arxml_read(p)
    except ARXMLError:
        raise
    except (OSError, FileNotFoundError) as e:
        raise ARXMLError(f"ARXML file not readable: {p}: {e}") from e

    nsmap = detect_namespaces(p)
    default_ns = nsmap.get("ar", "")
    if not default_ns:
        raise ARXMLError(
            f"ARXML file {p} has no default namespace; " f"nsmap keys: {sorted(nsmap)}"
        )

    # 提取元数据 + 容器 / IPdu / Signal
    root = doc.tree.getroot()
    module_names = _extract_module_names(root, default_ns)
    file_size = p.stat().st_size
    ipdus = _extract_ipdus(root, default_ns)
    signals_by_ipdu = _extract_signals_by_ipdu(root, default_ns)
    key_params = _extract_key_params(root, default_ns)

    # 渲染
    return _render_html(p, default_ns, module_names, file_size, ipdus, signals_by_ipdu, key_params)


def export_arxml_report(path: Path, output: Path | None = None) -> Path:
    """渲染 HTML 报告并写到文件，返回绝对路径。

    :param path: 输入 ``.arxml`` 路径
    :param output: 输出 HTML 路径；``None`` = 默认 ``<input>.report.html``
    :return: 已写入文件的绝对路径
    :raises ARXMLError: 读 ARXML 失败
    :raises OSError: 写文件失败
    """
    html = render_arxml_report(path)
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


def _render_html(
    path: Path,
    default_ns: str,
    module_names: list[str],
    file_size: int,
    ipdus: list[dict[str, Any]],
    signals_by_ipdu: dict[str, list[dict[str, Any]]],
    key_params: list[dict[str, str]],
) -> str:
    parts: list[str] = []
    parts.append(_render_html_head(path.name))
    parts.append(f"<h1>ARXML Report — {_html_escape(path.name)}</h1>")
    parts.append(_render_metadata(path, default_ns, module_names, file_size))
    parts.append(_render_summary(ipdus, signals_by_ipdu))
    parts.append(_render_ipdus_table(ipdus, signals_by_ipdu))
    parts.append(_render_signals_table(signals_by_ipdu))
    parts.append(_render_key_params(key_params))
    parts.append(_render_html_tail())
    return "".join(parts)


def _render_html_head(file_name: str) -> str:
    title = f"ARXML Report — {_html_escape(file_name)}"
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        f"<title>{title}</title>\n"
        f"<style>{_INSPECTOR_CSS}</style>\n"
        "</head>\n"
        "<body>\n"
    )


def _render_html_tail() -> str:
    return (
        '<hr><p style="color:#888;font-size:0.85em;">'
        "Generated by claude-autosar arxml-inspect (Sprint 9.1 T9.1.2)"
        "</p>\n"
        "</body>\n"
        "</html>\n"
    )


def _render_metadata(
    path: Path,
    default_ns: str,
    module_names: list[str],
    file_size: int,
) -> str:
    rows: list[str] = []
    rows.append(_kv_row("Path", f"<code>{_html_escape(str(path.resolve()))}</code>"))
    rows.append(_kv_row("Format", "AUTOSAR ARXML"))
    rows.append(
        _kv_row(
            "Default namespace",
            f"<code>{_html_escape(default_ns)}</code>",
        )
    )
    modules_str = (
        ", ".join(_html_escape(m) for m in module_names) if module_names else "<em>none</em>"
    )
    rows.append(_kv_row("Modules", f"<code>{modules_str}</code>"))
    rows.append(_kv_row("File size", f"{file_size} bytes"))
    return (
        '<div class="metadata">\n'
        "<h2>Metadata</h2>\n"
        '<table class="metadata-table">\n' + "".join(rows) + "</table>\n"
        "</div>\n"
    )


def _render_summary(
    ipdus: list[dict[str, Any]],
    signals_by_ipdu: dict[str, list[dict[str, Any]]],
) -> str:
    """Summary box: 总 IPdu 数 + Signal 数。"""
    n_ipdus = len(ipdus)
    n_signals = sum(len(v) for v in signals_by_ipdu.values())
    return (
        '<div class="summary-box">'
        f"<strong>IPdu</strong>: {n_ipdus} &nbsp;&nbsp; "
        f"<strong>Signals</strong>: {n_signals}"
        "</div>\n"
    )


def _render_ipdus_table(
    ipdus: list[dict[str, Any]],
    signals_by_ipdu: dict[str, list[dict[str, Any]]],
) -> str:
    if not ipdus:
        return "<p><em>No IPdu containers detected.</em></p>\n"
    rows: list[str] = []
    for ipdu in ipdus:
        ipdu_name = ipdu.get("name", "")
        ipdu_type = ipdu.get("type", "")
        handle = ipdu.get("ComIPduHandleId")
        length = ipdu.get("ComIPduLength")
        can_id = ipdu.get("ComIPduCanId")
        direction = ipdu.get("ComIPduDirection")
        signals = signals_by_ipdu.get(ipdu_name, [])

        # Signal 列表显示数量（避免行过宽）
        sig_count = len(signals)

        rows.append(
            "<tr>"
            f"<td><code>{_html_escape(ipdu_name)}</code></td>"
            f"<td><span class='tag'>{_html_escape(ipdu_type)}</span></td>"
            f"<td>{_param_cell(handle)}</td>"
            f"<td>{_param_cell(length)}</td>"
            f"<td>{_param_cell(can_id)}</td>"
            f"<td>{_param_cell(direction)}</td>"
            f"<td>{sig_count}</td>"
            "</tr>"
        )
    return (
        "<h2>IPdu Table</h2>\n"
        "<table>\n"
        "<thead><tr>"
        "<th>Name</th><th>Type</th><th>HandleId</th><th>Length</th>"
        "<th>CanId</th><th>Direction</th><th>Signal Count</th>"
        "</tr></thead>\n"
        "<tbody>\n" + "".join(rows) + "</tbody>\n"
        "</table>\n"
    )


def _render_signals_table(
    signals_by_ipdu: dict[str, list[dict[str, Any]]],
) -> str:
    """Signal 详细参数表（按 IPdu 父级分组）。"""
    all_signals = [(ipdu_name, sig) for ipdu_name, sigs in signals_by_ipdu.items() for sig in sigs]
    if not all_signals:
        return "<h2>Signal Table</h2>\n<p><em>No Signal containers detected.</em></p>\n"
    rows: list[str] = []
    for ipdu_name, sig in all_signals:
        sig_name = sig.get("name", "")
        sig_type = sig.get("type", "")
        bit_pos = sig.get("ComBitPosition")
        bit_size = sig.get("ComBitSize")
        byte_order = sig.get("ComSignalByteOrder")
        init_value = sig.get("ComSignalInitValue")
        rows.append(
            "<tr>"
            f"<td><code>{_html_escape(ipdu_name)}</code></td>"
            f"<td><code>{_html_escape(sig_name)}</code></td>"
            f"<td><span class='tag'>{_html_escape(sig_type)}</span></td>"
            f"<td>{_param_cell(bit_pos)}</td>"
            f"<td>{_param_cell(bit_size)}</td>"
            f"<td>{_param_cell(byte_order)}</td>"
            f"<td>{_param_cell(init_value)}</td>"
            "</tr>"
        )
    return (
        "<h2>Signal Table</h2>\n"
        "<table>\n"
        "<thead><tr>"
        "<th>IPdu Parent</th><th>Signal Name</th><th>Type</th>"
        "<th>BitPosition</th><th>BitSize</th>"
        "<th>ByteOrder</th><th>InitValue</th>"
        "</tr></thead>\n"
        "<tbody>\n" + "".join(rows) + "</tbody>\n"
        "</table>\n"
    )


def _render_key_params(key_params: list[dict[str, str]]) -> str:
    if not key_params:
        return ""
    rows: list[str] = []
    for p in key_params:
        container = _html_escape(p.get("container", ""))
        name = _html_escape(p.get("name", ""))
        raw = p.get("value", "")
        value = _html_escape(raw) if raw else "<em>none</em>"
        rows.append(
            "<tr>"
            f"<td><code>{container}</code></td>"
            f"<td><code>{name}</code></td>"
            f"<td>{value}</td>"
            "</tr>"
        )
    return (
        "<h2>Key Parameters</h2>\n"
        "<table class='kv-param'>\n"
        "<thead><tr><th>Container</th><th>Parameter</th><th>Value</th></tr></thead>\n"
        "<tbody>\n" + "".join(rows) + "</tbody>\n"
        "</table>\n"
    )


def _kv_row(k: str, v: str) -> str:
    return f"<tr><th>{_html_escape(k)}</th><td>{v}</td></tr>\n"


def _param_cell(value: Any) -> str:
    """IPdu 关键参数 cell：值为 None / 空 → 灰色 italic 标签。"""
    if value is None or value == "":
        return "<span class='tag-missing'>—</span>"
    return _html_escape(str(value))


# ---------------------------------------------------------------------------
# 公共 API：ARXML 树提取（Sprint 11 T11.4 提取）
# ---------------------------------------------------------------------------
# lint/extract.py 等模块应调用这些公共函数，而非直接调用 _extract_* 私有函数。


def extract_module_names(root: Any, default_ns: str) -> list[str]:
    """收集顶层 ``<ECUC-MODULE-CONFIGURATION-VALUES>`` 的 SHORT-NAME。"""
    return _extract_module_names(root, default_ns)


def extract_ipdus(root: Any, default_ns: str) -> list[dict[str, Any]]:
    """提取 ComIPdu / ComTxIPdu / ComRxIPdu 容器的关键参数。"""
    return _extract_ipdus(root, default_ns)


def extract_signals_by_ipdu(
    root: Any, default_ns: str
) -> dict[str, list[dict[str, Any]]]:
    """按 IPdu 分组提取信号参数。"""
    return _extract_signals_by_ipdu(root, default_ns)


def extract_key_params(root: Any, default_ns: str) -> list[dict[str, str]]:
    """提取顶层容器的关键参数（非 IPdu）。"""
    return _extract_key_params(root, default_ns)


def extract_os_tasks(root: Any, default_ns: str) -> list[dict[str, Any]]:
    """提取 OsTask 容器的关键参数（name / priority / stack_size）。"""
    return _extract_containers_by_type(root, default_ns, "OsTask", ("OsTaskPriority", "OsTaskStackDepth"))


def extract_nvm_blocks(root: Any, default_ns: str) -> list[dict[str, Any]]:
    """提取 NvMBlockDescriptor 容器的关键参数（name / block_size / crc_type）。"""
    return _extract_containers_by_type(
        root, default_ns, "NvMBlockDescriptor",
        ("NvMBlockCrcType", "NvMBlockSize", "NvMBlockJobPriority"),
    )


def extract_fee_blocks(root: Any, default_ns: str) -> list[dict[str, Any]]:
    """提取 FeeBlockConfiguration 容器的关键参数（name / block_size）。"""
    return _extract_containers_by_type(
        root, default_ns, "FeeBlockConfiguration",
        ("FeeBlockSize", "FeeNumberOfShortSegments"),
    )


def _extract_containers_by_type(
    root: Any,
    default_ns: str,
    container_type: str,
    param_names: tuple[str, ...],
) -> list[dict[str, Any]]:
    """通用提取：按 container type 短名提取容器及其关键参数。"""
    nsmap = {"ar": default_ns}
    result: list[dict[str, Any]] = []

    # 找所有 ECUC-PARAM-CONF-CONTAINER
    for container in root.xpath(
        "//ar:ECUC-PARAM-CONF-CONTAINER", namespaces=nsmap
    ):
        # 检查 DEFINITION-REF 是否包含目标 container type
        def_ref = container.find("{*}DEFINITION-REF")
        if def_ref is None or def_ref.text is None:
            continue
        if f"/{container_type}" not in def_ref.text:
            continue

        sn = get_child_text(container, "SHORT-NAME")
        record: dict[str, Any] = {"name": sn or "<unknown>"}

        # 提取关键参数
        for pv in container.xpath(
            ".//ar:ECUC-NUMERICAL-PARAM-VALUE | .//ar:ECUC-TEXTUAL-PARAM-VALUE",
            namespaces=nsmap,
        ):
            pv_def_ref = pv.find("{*}DEFINITION-REF")
            if pv_def_ref is None or pv_def_ref.text is None:
                continue
            pv_short = pv_def_ref.text.rsplit("/", 1)[-1] if "/" in pv_def_ref.text else pv_def_ref.text
            if pv_short in param_names:
                val = pv.find("{*}VALUE")
                record[pv_short] = val.text if val is not None else None

        result.append(record)

    return result


# ---------------------------------------------------------------------------
# 内部：ARXML 树提取
# ---------------------------------------------------------------------------


def _extract_module_names(root: Any, default_ns: str) -> list[str]:
    """收集顶层 ``<ECUC-MODULE-CONFIGURATION-VALUES>`` 的 SHORT-NAME。

    顶层 = parent tag 不再是 ``ECUC-MODULE-CONFIGURATION-VALUES``。
    """
    nsmap = {"ar": default_ns}
    # 找所有 ECUC-MODULE-CONFIGURATION-VALUES（不限深度）
    all_modules = root.xpath(
        "//ar:ECUC-MODULE-CONFIGURATION-VALUES",
        namespaces=nsmap,
    )
    # 过滤：只保留顶层（祖先里没有同级）
    top: list[str] = []
    seen: set[int] = set()
    for m in all_modules:
        if id(m) in seen:
            continue
        # 父链无 ECUC-MODULE-CONFIGURATION-VALUES
        if _has_module_ancestor(m):
            continue
        seen.add(id(m))
        sn = get_child_text(m, "SHORT-NAME")
        if sn:
            top.append(sn)
    return top


def _extract_ipdus(root: Any, default_ns: str) -> list[dict[str, Any]]:
    """提取所有 IPdu 容器（ComIPdu / ComTxIPdu / ComRxIPdu）。

    返回 list of dict：每个 IPdu 包含 ``name`` / ``type`` + 关键 PARAM-VALUES。
    """
    nsmap = {"ar": default_ns}
    ipdus: list[dict[str, Any]] = []
    for sn in _IPDU_SHORT_NAMES:
        containers = root.xpath(
            f"//ar:ECUC-CONTAINER-VALUE[ar:SHORT-NAME='{sn}']",
            namespaces=nsmap,
        )
        for c in containers:
            name = get_child_text(c, "SHORT-NAME") or sn
            record: dict[str, Any] = {"name": name, "type": sn}
            # 提取 PARAM-VALUES（子元素是 ECUC-NUMERICAL-PARAM-VALUE 等）
            _populate_ipdu_params(c, record)
            ipdus.append(record)
    return ipdus


def _populate_ipdu_params(ipdu_elem: Any, record: dict[str, Any]) -> None:
    """从 IPdu 容器内提取关键 PARAM-VALUES（按 tag 找 ECUC-NUMERICAL/...）。"""
    for tag in _IPDU_PARAM_TAGS:
        # 找 <ECUC-NUMERICAL-PARAM-VALUE><DEFINITION-REF>.../<tag>...
        # 简化：直接看 IPdu 下的所有 ECUC-NUMERICAL-PARAM-VALUE 的 DEFINITION-REF 后缀
        # 拿第一个匹配的 VALUE 文本
        for pval in ipdu_elem.findall("{*}PARAMETER-VALUES/{*}ECUC-NUMERICAL-PARAM-VALUE"):
            dref = get_child_text(pval, "DEFINITION-REF")
            if dref and dref.endswith("/" + tag):
                val = get_child_text(pval, "VALUE")
                if val is not None and tag not in record:
                    record[tag] = val
                    break
        for pval in ipdu_elem.findall("{*}PARAMETER-VALUES/{*}ECUC-TEXTUAL-PARAM-VALUE"):
            dref = get_child_text(pval, "DEFINITION-REF")
            if dref and dref.endswith("/" + tag):
                val = get_child_text(pval, "VALUE")
                if val is not None and tag not in record:
                    record[tag] = val
                    break
    # 兼容字段名
    if "ComTxIPduHandleId" in record and "ComIPduHandleId" not in record:
        record["ComIPduHandleId"] = record["ComTxIPduHandleId"]
    if "ComRxIPduHandleId" in record and "ComIPduHandleId" not in record:
        record["ComIPduHandleId"] = record["ComRxIPduHandleId"]
    if "ComTxIPduLength" in record and "ComIPduLength" not in record:
        record["ComIPduLength"] = record["ComTxIPduLength"]
    if "ComRxIPduLength" in record and "ComIPduLength" not in record:
        record["ComIPduLength"] = record["ComRxIPduLength"]
    if "ComTxIPduCanId" in record and "ComIPduCanId" not in record:
        record["ComIPduCanId"] = record["ComTxIPduCanId"]
    if "ComRxIPduCanId" in record and "ComIPduCanId" not in record:
        record["ComIPduCanId"] = record["ComRxIPduCanId"]
    if "ComTxIPduDirection" in record and "ComIPduDirection" not in record:
        record["ComIPduDirection"] = record["ComTxIPduDirection"]
    if "ComRxIPduDirection" in record and "ComIPduDirection" not in record:
        record["ComIPduDirection"] = record["ComRxIPduDirection"]


def _extract_signals_by_ipdu(root: Any, default_ns: str) -> dict[str, list[dict[str, Any]]]:
    """提取所有 Signal 容器，按其最近 IPdu 祖先归组。

    返回 ``{ipdu_name: [signal_record, ...]}``。未被 IPdu 包裹的 Signal 归入
    ``__ungrouped__``。
    """
    nsmap = {"ar": default_ns}
    out: dict[str, list[dict[str, Any]]] = {}

    for sn in _SIGNAL_SHORT_NAMES:
        sigs = root.xpath(
            f"//ar:ECUC-CONTAINER-VALUE[ar:SHORT-NAME='{sn}']",
            namespaces=nsmap,
        )
        for s in sigs:
            name = get_child_text(s, "SHORT-NAME") or sn
            record: dict[str, Any] = {"name": name, "type": sn}
            _populate_signal_params(s, record)
            # 找最近 IPdu 祖先
            parent_ipdu = _find_nearest_ipdu_ancestor(s, default_ns)
            key = parent_ipdu if parent_ipdu else "__ungrouped__"
            out.setdefault(key, []).append(record)
    return out


def _populate_signal_params(sig_elem: Any, record: dict[str, Any]) -> None:
    """从 Signal 容器内提取关键 PARAM-VALUES。"""
    for tag in _SIGNAL_PARAM_TAGS:
        for pval in sig_elem.findall("{*}PARAMETER-VALUES/{*}ECUC-NUMERICAL-PARAM-VALUE"):
            dref = get_child_text(pval, "DEFINITION-REF")
            if dref and dref.endswith("/" + tag):
                val = get_child_text(pval, "VALUE")
                if val is not None and tag not in record:
                    record[tag] = val
                    break
        for pval in sig_elem.findall("{*}PARAMETER-VALUES/{*}ECUC-TEXTUAL-PARAM-VALUE"):
            dref = get_child_text(pval, "DEFINITION-REF")
            if dref and dref.endswith("/" + tag):
                val = get_child_text(pval, "VALUE")
                if val is not None and tag not in record:
                    record[tag] = val
                    break


def _find_nearest_ipdu_ancestor(elem: Any, default_ns: str) -> str | None:  # noqa: ARG001
    """从 elem 向上 walk ancestors，找最近 IPdu 容器，返回其 SHORT-NAME。

    ``default_ns`` 保留为签名一致性（其他提取函数统一接口）；当前实现用
    lxml 的 wildcard ``{*}`` 匹配，不需要显式 ns。
    """
    for anc in elem.iterancestors():
        sn = get_child_text(anc, "SHORT-NAME")
        if sn and sn in _IPDU_SHORT_NAMES:
            return get_child_text(anc, "SHORT-NAME")
    return None


def _has_module_ancestor(elem: Any) -> bool:
    """elem 祖先链里是否包含 ``ECUC-MODULE-CONFIGURATION-VALUES``（除自身）。"""
    for anc in elem.iterancestors():
        if etree_local_name(anc) == "ECUC-MODULE-CONFIGURATION-VALUES":
            return True
    return False


def _extract_key_params(root: Any, default_ns: str) -> list[dict[str, str]]:
    """提取顶层容器（ComGeneral 等）下的关键参数（不深入 IPdu 内部）。"""
    nsmap = {"ar": default_ns}
    params: list[dict[str, str]] = []
    # 找所有顶层 ECUC-MODULE-CONFIGURATION-VALUES 之下的 ECUC-CONTAINER-VALUE
    # （非 IPdu）
    all_modules = root.xpath(
        "//ar:ECUC-MODULE-CONFIGURATION-VALUES",
        namespaces=nsmap,
    )
    for mod in all_modules:
        if _has_module_ancestor(mod):
            continue
        mod_name = get_child_text(mod, "SHORT-NAME") or "<module>"
        for c in mod.findall("{*}CONTAINERS/{*}ECUC-CONTAINER-VALUE"):
            cname = get_child_text(c, "SHORT-NAME")
            if not cname or cname in _IPDU_SHORT_NAMES:
                continue
            # 取容器下 PARAM-VALUES（限制 1-2 层，避免 IPdu 嵌套）
            for pval in c.findall("{*}PARAMETER-VALUES/{*}ECUC-NUMERICAL-PARAM-VALUE"):
                dref = get_child_text(pval, "DEFINITION-REF")
                if dref is None:
                    continue
                short = dref.rsplit("/", 1)[-1]
                val = get_child_text(pval, "VALUE")
                if val is not None:
                    params.append(
                        {
                            "container": f"{mod_name}/{cname}",
                            "name": short,
                            "value": val,
                        }
                    )
            for pval in c.findall("{*}PARAMETER-VALUES/{*}ECUC-TEXTUAL-PARAM-VALUE"):
                dref = get_child_text(pval, "DEFINITION-REF")
                if dref is None:
                    continue
                short = dref.rsplit("/", 1)[-1]
                val = get_child_text(pval, "VALUE")
                if val is not None:
                    params.append(
                        {
                            "container": f"{mod_name}/{cname}",
                            "name": short,
                            "value": val,
                        }
                    )
    return params


# ---------------------------------------------------------------------------
# 内部：lxml 元素 local-name 工具
# ---------------------------------------------------------------------------


def etree_local_name(elem: Any) -> str:
    """lxml 元素 → local name（不依赖 lxml.QName 显式 import；用纯字符串切片）。"""
    tag = elem.tag
    if not isinstance(tag, str):
        return ""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


# ---------------------------------------------------------------------------
# Sprint 9.3 T9.3-γ — verify section 嵌入（独立切片）
# ---------------------------------------------------------------------------


def render_arxml_report_with_verify(
    path: Path,
    verify_issues: tuple[Any, ...] = (),
    verify_returncode: int = 0,
) -> str:
    """Sprint 9.3 T9.3-γ 入口：渲染 arxml 报告 + 嵌入 verify section HTML。

    Parameters
    ----------
    path:
        输入 ``.arxml`` 文件路径。
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
    * 不重写 :func:`render_arxml_report` 既有逻辑；本函数走
      ``render_arxml_report`` → 字符串拼接 verify section。
    * 嵌入失败（``</body>`` 不规整）→ graceful fallback：直接
      ``base + section`` 拼接（section 可能在 HTML 之外，但保留内容）。
    """
    base = render_arxml_report(path)
    if not verify_issues and verify_returncode == 0:
        return base
    # 延迟导入：避免 verify 包未实现时影响 arxml_report 自身 import
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
    "render_arxml_report",
    "export_arxml_report",
    "render_arxml_report_with_verify",
    "render_arxml_report_with_lint",
]


# ---------------------------------------------------------------------------
# Sprint 9.4 T9.4-β — lint section 嵌入（独立切片；不动 9.3-γ 的 verify）
# ---------------------------------------------------------------------------
# 给 9.4-β MCP `arxml_inspect(..., include_lint=True)` / CLI `arxml-inspect
# --lint` 复用。**append-only**：不改既有 `render_arxml_report` / 9.3-γ
# `render_arxml_report_with_verify`，独立渲染函数只在 base HTML 后追加
# lint section（reuse `_INSPECTOR_CSS` 的 `summary-box` + violations table；
# XSS 走 :func:`html.escape`）。duck-typed violations：``v.rule_id`` /
# ``v.severity`` / ``v.message`` / ``v.path`` / ``v.line``（与
# ``commands.lint._violation_to_dict`` 一致）。


def _render_arxml_lint_section_html(violations: tuple[Any, ...]) -> str:
    """Sprint 9.4-β：渲染 arxml 报告底部嵌入的 lint section。

    :param violations: 任意 duck-typed 对象序列（rule_id/severity/message/
        path/line 属性），空 tuple → 返空字符串
    :return: HTML string（含 ``summary-box`` + violations table）
    """
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


def render_arxml_report_with_lint(
    path: Path,
    violations: tuple[Any, ...] = (),
) -> str:
    """Sprint 9.4 T9.4-β 入口：arxml 报告 + lint section 嵌入。

    :param path: ``.arxml`` 文件路径
    :param violations: duck-typed lint violations；空 → 不嵌入 lint section
    :return: 自包含 HTML 字符串
    """
    base = render_arxml_report(path)
    if not violations:
        return base
    section = _render_arxml_lint_section_html(violations)
    if "</body>" in base:
        return base.replace("</body>", section + "</body>", 1)
    return base + "\n" + section
