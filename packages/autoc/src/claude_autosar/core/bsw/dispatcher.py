"""Sprint 9.0 — T9.0.2 BSW I/O dispatcher.

按文件根命名空间（``xmlns``）自动选择 :mod:`claude_autosar.core.bsw.arxml_io`
（AUTOSAR r4.x）或 :mod:`claude_autosar.core.bsw.io.datamodel2_io`
（EB tresos DataModel2）作为底层 parser / writer。

设计原则（plan v2 §2.1 / §0.2.1）：

  - **不抽象 InstanceTree** —— 每个格式独立解析 / 序列化 / 渲染
  - **dispatcher 只是个薄壳**：探测格式 + 转发到对应 io 模块
  - **不复制 logic**：高层 ECUC walker 仍走 ``core/bsw/ecuc.py``（只对 .arxml
    生效），DataModel2 配置数据走 lxml 直读 + ``d:var`` 扁平提取
  - **写回**用各自 IO 模块的 surgical patch：保留 99% 字节（对齐 Sprint
    8.E.5 XDM byte-identity 验收）

支持的命名空间（探测根 tag 的 ``xmlns``）：

  - DataModel2 root: ``http://www.tresos.de/_projects/DataModel2/16/root.xsd``
  - DataModel2 1.0 旧 alias: ``http://www.3soft.de/xml/tresos/datamodel/1.0``
  - AUTOSAR r4.0/4.2/4.4/4.6/4.7/4.8: ``http://autosar.org/schema/r4.X``

.. note::

   T9.0.2 范围是**路由**（detect + dispatch），不是写新的 ECUC walker。XDM
   高层 ECUC 解析在 Sprint 9.1 的 ``inspector/xdm_report.py`` 实施（用
   ``d:var`` 扁平提取 + BswM 路径展开）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Public type aliases
# ---------------------------------------------------------------------------

Format = Literal["arxml", "xdm"]
"""BSW 配置 / 报告文件格式。"""

# Well-known namespace URIs（对齐 arxml_io / datamodel2_io 各自定义）
AUTOSAR_NAMESPACES: frozenset[str] = frozenset(
    {
        "http://autosar.org/schema/r4.0",
        "http://autosar.org/schema/r4.2",
        "http://autosar.org/schema/r4.4",
        "http://autosar.org/schema/r4.6",
        "http://autosar.org/schema/r4.7",
        "http://autosar.org/schema/r4.8",
    }
)

DATAMODEL2_NAMESPACES: frozenset[str] = frozenset(
    {
        # DataModel2 2.0 root
        "http://www.tresos.de/_projects/DataModel2/16/root.xsd",
        # DataModel2 1.0 alias（v1 fixtures 在 tests/fixtures/xdm/）
        "http://www.3soft.de/xml/tresos/datamodel/1.0",
    }
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class DispatcherError(ValueError):
    """dispatcher 解析 / 路由失败。"""


class UnknownFormatError(DispatcherError):
    """文件根 namespace 既不是 AUTOSAR 也不是 DataModel2。"""


class FormatMismatchError(DispatcherError):
    """调用方明确指定格式，但跟文件实际 namespace 冲突。"""


# ---------------------------------------------------------------------------
# Detect
# ---------------------------------------------------------------------------


def detect_format(path: str | Path) -> Format:
    """从文件根 ``xmlns`` 探测格式。

    :raises FileNotFoundError: 文件不存在
    :raises UnknownFormatError: 根 namespace 既不在 AUTOSAR 也不在 DataModel2 列表
    :raises DispatcherError: 文件无法解析为 XML
    """
    from lxml import etree

    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"detect_format: file not found: {p}")
    try:
        # 用 iterparse 而不是 etree.parse，省 RAM（大文件场景 8.E.5 验过）
        # 读到第一个 start event 拿到根 tag 就停
        context = etree.iterparse(str(p), events=("start",), recover=True, huge_tree=True)
        try:
            _, root = next(context)
        finally:
            # 显式关 context（lxml 内部会 free）
            for _ in context:
                pass
    except etree.XMLSyntaxError as e:  # pragma: no cover - 由 recover=True 吃掉
        raise DispatcherError(f"detect_format: cannot parse {p}: {e}") from e

    nsmap = dict(root.nsmap) if root.nsmap else {}
    # 找根元素的**默认 namespace**（无 prefix）；lxml 用 None 作 default ns
    default_uri = nsmap.get(None)
    return _classify_uri(default_uri, p)


def detect_format_from_tree(tree: Any) -> Format:
    """从已加载 lxml tree 探测格式（避免重复 IO；测试和 ecuc 共用）。

    接受 ``_ElementTree``（有 ``.getroot()``）或裸 ``_Element``（无 ``getroot()``，
    lxml :func:`fromstring` 返回值）。两种都支持。
    """
    if hasattr(tree, "getroot"):
        root = tree.getroot()
        if root is None:
            # :func:`fromstring` 返回的 _Element 被当 _ElementTree 用时
            # 退化成 root 本身的情况
            root = tree
    else:
        root = tree
    nsmap = dict(root.nsmap) if getattr(root, "nsmap", None) else {}
    default_uri = nsmap.get(None)
    return _classify_uri(default_uri, getattr(root, "source", "<tree>"))


def _classify_uri(uri: str | None, source: Any) -> Format:
    if uri is None:
        raise UnknownFormatError(
            f"file {source!s} has no default namespace; "
            f"neither AUTOSAR ({sorted(AUTOSAR_NAMESPACES)[0]}…) nor "
            f"DataModel2 ({sorted(DATAMODEL2_NAMESPACES)[0]})"
        )
    if uri in AUTOSAR_NAMESPACES:
        return "arxml"
    if uri in DATAMODEL2_NAMESPACES:
        return "xdm"
    raise UnknownFormatError(
        f"file {source!s} root namespace {uri!r} is neither AUTOSAR nor DataModel2; "
        f"known AUTOSAR: {sorted(AUTOSAR_NAMESPACES)}; "
        f"known DataModel2: {sorted(DATAMODEL2_NAMESPACES)}"
    )


# ---------------------------------------------------------------------------
# Dispatch: read / write
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LoadedDocument:
    """dispatcher 加载的文件（格式无关的轻壳）。"""

    path: Path
    format: Format
    tree: Any  # lxml _ElementTree / _Element（DataModel2 用 _ElementTree）

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"LoadedDocument(path={self.path!s}, format={self.format!r})"


def read(path: str | Path, *, expected_format: Format | None = None) -> LoadedDocument:
    """按文件根 namespace 选 arxml_io / datamodel2_io，返回 LoadedDocument。

    :param expected_format: 调用方明确指定（CLI 主路径 / 测试）。None = 自动探测。
    :raises FormatMismatchError: 期望格式 vs 实际格式冲突
    :raises UnknownFormatError: 自动探测失败
    """
    from claude_autosar.core.bsw.arxml_io import read as _arxml_read
    from claude_autosar.core.bsw.io.datamodel2_io import read as _xdm_read

    p = Path(path)
    actual = detect_format(p)
    if expected_format is not None and expected_format != actual:
        raise FormatMismatchError(
            f"file {p!s} is {actual!r} but expected_format={expected_format!r}"
        )
    if actual == "arxml":
        doc = _arxml_read(p)
        return LoadedDocument(path=p, format="arxml", tree=doc.tree)
    # xdm
    tree = _xdm_read(p)
    return LoadedDocument(path=p, format="xdm", tree=tree)


def write(doc: LoadedDocument, *, preserve_format: bool = True) -> None:
    """按 ``doc.format`` 路由到对应 writer。原子写 + 保留格式（默认）。"""
    from claude_autosar.core.bsw.arxml_io import ARXMLDocument
    from claude_autosar.core.bsw.arxml_io import write as _arxml_write
    from claude_autosar.core.bsw.io.datamodel2_io import write as _xdm_write

    if doc.format == "arxml":
        # arxml_io.write 接受 ARXMLDocument 或 _ElementTree（契约 3）
        if isinstance(doc.tree, ARXMLDocument):
            arxml_doc = doc.tree
        else:
            # 兜底：从 _ElementTree 包成最小 ARXMLDocument
            arxml_doc = ARXMLDocument(path=doc.path, tree=doc.tree)
        _arxml_write(arxml_doc, doc.path, preserve_format=preserve_format)
        return
    # xdm
    _xdm_write(doc.tree, doc.path, preserve_format=preserve_format)


# ---------------------------------------------------------------------------
# Convenience: detect-only（CLI / init 向导用）
# ---------------------------------------------------------------------------


def describe(path: str | Path) -> dict[str, Any]:
    """返回文件格式信息（给 init 向导 / 日志用，不抛异常）。"""
    try:
        fmt = detect_format(path)
        return {"success": True, "path": str(path), "format": fmt}
    except FileNotFoundError as e:
        return {"success": False, "path": str(path), "error": f"FileNotFoundError: {e}"}
    except UnknownFormatError as e:
        return {"success": False, "path": str(path), "error": str(e)}
    except DispatcherError as e:
        return {"success": False, "path": str(path), "error": str(e)}


__all__ = [
    "Format",
    "AUTOSAR_NAMESPACES",
    "DATAMODEL2_NAMESPACES",
    "DispatcherError",
    "UnknownFormatError",
    "FormatMismatchError",
    "LoadedDocument",
    "detect_format",
    "detect_format_from_tree",
    "read",
    "write",
    "describe",
]
