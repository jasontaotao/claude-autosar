"""lxml-based low-level ARXML read/write utilities.

Sprint 3 — T3.1。提供命名空间感知的元素查找、属性/子文本读写、原子写文件。
仅作低层工具；高层 ECUC 语义解析在 `ecuc.py`。

Sprint 8.E — T8.E.1：dynamic namespace detection（r4.0/4.2/4.4/4.6/4.7/4.8）
通过 `detect_namespaces(path)` 探测根 xmlns，调用方按需拼到 xpath 里。

Sprint 8.E — T8.E.5：XDM byte-identity round-trip。
`write(tree, path, *, atomic=True, preserve_format=True)` 保留 PIs / DOCTYPE / 注释 /
属性顺序 / namespace prefix。主路径走"原字节 + surgical patch"，退路走
`cleanup_namespaces` + `tostring`。旧 API `write(doc: ARXMLDocument, *, atomic=True)`
继续兼容（doc 自身带 path）。
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, TypeAlias, cast

from lxml import etree

from claude_autosar.core.bsw.io.xml_io_base import (
    _SurgicalPatchUnavailable,
    atomic_write,
    cleanup_namespaces_fallback,
)
from claude_autosar.core.bsw.xml_safe import _safe_parse
from claude_autosar.utils.xml_escape import escape_xml_text

# 知名命名空间 URI（按 prefix 索引）。本表只用作 prefix fallback
# （如 `xsi:noNamespaceSchemaLocation`），ARXML 默认 ns 通过 detect_namespaces
# 从根 xmlns 动态探测。
WELL_KNOWN_NAMESPACE_URIS: dict[str, tuple[str, ...]] = {
    "ar": (
        "http://autosar.org/schema/r4.0",
        "http://autosar.org/schema/r4.2",
        "http://autosar.org/schema/r4.4",
        "http://autosar.org/schema/r4.6",
        "http://autosar.org/schema/r4.7",
        "http://autosar.org/schema/r4.8",
    ),
    "d": ("http://www.3soft.de/xml/tresos/datamodel/1.0",),
    "xsi": ("http://www.w3.org/2001/XMLSchema-instance",),
}

# 兼容 alias：老代码用 DEFAULT_NAMESPACES["ar"] 取默认 URI 不破。
DEFAULT_NAMESPACES: dict[str, tuple[str, ...]] = WELL_KNOWN_NAMESPACE_URIS

# detect_namespaces 中默认 ns 的 prefix
_DEFAULT_NS_PREFIX = "ar"
# xsi 必含（contract 3 硬约束）
_XSI_URI = "http://www.w3.org/2001/XMLSchema-instance"


class ARXMLError(Exception):
    """ARXML I/O 失败时抛出的统一异常（包装 lxml/OSError）。"""


@dataclass(frozen=True)
class ARXMLDocument:
    """不可变 ARXML 文档：path + 解析后的 lxml 树。"""

    path: Path
    tree: Any  # lxml.etree._ElementTree（不指定 generic 避免 mypy 噪音）


@lru_cache(maxsize=64)
def _cached_parse(path_str: str, mtime_ns: int) -> etree._ElementTree:
    """Cached XML parse keyed by (resolved path, mtime_ns).

    ``mtime_ns`` is intentionally present as a cache key — it ensures the
    cache automatically invalidates when the file is modified on disk.
    """
    return _safe_parse(path_str, recover=False)


def _invalidate_cache(path: str | Path) -> None:
    """Invalidate cached parse result for *path* (call after write).

    ``lru_cache`` does not support selective invalidation, so the entire
    cache is cleared.  This is acceptable because the cache is small
    (maxsize=64) and writes are infrequent relative to reads.
    """
    _cached_parse.cache_clear()


def read(path: Path) -> ARXMLDocument:
    """读 ARXML 文件。文件不存在或 XML 畸形时抛 ARXMLError。"""
    p = Path(path)
    try:
        mtime_ns = p.stat().st_mtime_ns
    except OSError as e:
        raise ARXMLError(f"ARXML file not readable: {p}: {e}") from e
    path_str = str(p.resolve())
    try:
        tree = _cached_parse(path_str, mtime_ns)
    except etree.XMLSyntaxError as e:
        raise ARXMLError(f"Malformed ARXML in {p}: {e}") from e
    return ARXMLDocument(path=p, tree=tree)


# 接受 ARXMLDocument 或裸 lxml tree（契约 3 签名）
_TreeLike: TypeAlias = "ARXMLDocument | etree._ElementTree"


def write(
    target: _TreeLike,
    path: str | Path | None = None,
    *,
    atomic: bool = True,
    preserve_format: bool = True,
) -> None:
    """写 lxml 树（或 ARXMLDocument）到 path.

    契约 3 (frozen) 签名: write(tree, path, *, atomic=True, preserve_format=True)
    也支持旧调用: write(arxml_doc, atomic=True, preserve_format=True)
    → 此时 path 取自 arxml_doc.path.

    - preserve_format=True (默认): 保留 PIs / DOCTYPE / 注释 / 属性顺序 / namespace prefix.
      主路径走"原字节 + surgical patch"（保留原文件字节，只替换 <VALUE>xxx</VALUE> 段）.
      退路: lxml.etree.cleanup_namespaces + tostring + 重建 DOCTYPE.
    - preserve_format=False: 走 tostring 软保真（不保证 PI / DOCTYPE / 属性顺序）.
    - atomic=True (默认): .tmp + os.replace; 失败时原文件保持不变.
    """
    # 解析调用形态: (doc, path=None) vs (tree, path=...)
    if isinstance(target, ARXMLDocument):
        if path is None:
            path = target.path
        tree = target.tree
    else:
        tree = target
        if path is None:
            raise TypeError(
                "write(tree, ...) requires explicit path when target is not an ARXMLDocument"
            )

    out_path = Path(path)
    if not atomic:
        _write_to_path(out_path, tree, preserve_format=preserve_format)
        _invalidate_cache(out_path)
        return

    def _write_fn(p: Path, t: Any) -> None:
        _write_to_path(p, t, preserve_format=preserve_format)

    atomic_write(out_path, tree, _write_fn, ARXMLError)
    _invalidate_cache(out_path)


def _write_to_path(
    path: Path,
    tree: Any,
    *,
    preserve_format: bool = True,
) -> None:
    """实际写 XML 字节到 path.

    preserve_format=True:
      主路径 (surgical patch): 找原文件中 <VALUE>xxx</VALUE> 这种"已被 set_value 改过"的段
        → 替换原文件中对应 <VALUE>...</VALUE> 字节范围. 99% 字节原样保留 →
        PIs / DOCTYPE / 注释 / 属性顺序 / namespace prefix 全部保住.
      退路 (tostring): cleanup_namespaces + tostring + 重建 DOCTYPE.

    preserve_format=False: 走纯 tostring 软保真.
    """
    if preserve_format:
        # 主路径: surgical patch
        try:
            _write_surgical_patch(path, tree)
            return
        except _SurgicalPatchUnavailable:
            # 退路: tostring + cleanup_namespaces + 重建 DOCTYPE
            pass

    # 退路 / preserve_format=False
    cleanup_namespaces_fallback(path, tree, preserve_format=preserve_format)


def _write_surgical_patch(path: Path, tree: Any) -> None:
    """Surgical patch 主路径.

    策略: 文件已存在（必须存在以做 patch）→ 读原文件字节 → 直接从 in-memory tree
    遍历所有 <VALUE> 元素，对比原文件中 <VALUE>old</VALUE> 段文本，按位置倒序替换
    → 99% 字节原样保留（PIs / DOCTYPE / 注释 / 属性顺序 / namespace prefix 全部保住）.

    触发条件: 改前 vs 改后只在 <VALUE> 元素文本上不同（典型 set_value 用例）.
    失败: 抛 _SurgicalPatchUnavailable 让调用方降级.

    重要: atomic 写路径先写 .tmp 再 os.replace → .tmp 不存在 → patch 不可用.
    因此 write() 调用方在 atomic 模式下应传入 ORIGINAL 路径,本函数检测到 .tmp 后缀时
    自动切到 ORIGINAL 路径做 patch,然后把结果写到 .tmp.
    """
    # atomic 写场景: path 是 <name>.xdm.tmp → 用 <name>.xdm 做 patch,
    # 再把 patched bytes 写到 tmp
    if path.suffix == ".tmp":
        original_path = path.with_suffix("")  # strip .tmp
        if not original_path.exists():
            raise _SurgicalPatchUnavailable(
                f"original path {original_path} does not exist for atomic surgical patch"
            )
        original_bytes = original_path.read_bytes()
        patched = _apply_surgical_patch_to_bytes(original_bytes, tree)
        path.write_bytes(patched)
        return

    if not path.exists():
        raise _SurgicalPatchUnavailable("file does not exist for surgical patch")
    original_bytes = path.read_bytes()
    patched = _apply_surgical_patch_to_bytes(original_bytes, tree)
    path.write_bytes(patched)


def _apply_surgical_patch_to_bytes(original_bytes: bytes, tree: Any) -> bytes:
    """核心 surgical patch 逻辑. 输入原字节 + 树 → 输出 patched 字节.

    触发条件: 改前 vs 改后只在 <VALUE> 元素文本上不同.
    """
    original_text = original_bytes.decode("utf-8", errors="strict")

    import re

    # 在原始文件字节（字符串视图）里找所有 <VALUE>...</VALUE> 段的位置
    # 注意: 这是按原文件找，不依赖 cleanup_namespaces 后的字节（后者会改空白/缩进）
    value_pattern = re.compile(
        r"<VALUE[^>]*>([^<]*)</VALUE>",
        re.DOTALL,
    )
    original_matches = list(value_pattern.finditer(original_text))

    # 从 in-memory tree 收集所有 <VALUE> 元素当前文本
    # 注意: lxml 5+ 中 tree.getroot().iter("{*}VALUE") 在有 comments / PIs 时返回 0
    # (因为 wildcard match 对 non-str .tag 元素静默跳过) → 用手写 walk + local-name 匹配
    new_value_texts: list[str] = []

    def _walk_value_texts(elem: Any) -> None:
        if isinstance(elem.tag, str) and etree.QName(elem.tag).localname == "VALUE":
            new_value_texts.append(elem.text or "")
        for child in elem:
            if isinstance(child.tag, str):
                _walk_value_texts(child)

    _walk_value_texts(tree.getroot())

    if len(new_value_texts) != len(original_matches):
        # 数量不同 → 不是单纯 VALUE 文本变化 → 退路
        raise _SurgicalPatchUnavailable(
            f"VALUE element count differs: new={len(new_value_texts)} "
            f"orig={len(original_matches)}"
        )

    # 检查每个 VALUE 元素文本是否变化
    any_changed = False
    for old_text, new_text in zip(
        (m.group(1) for m in original_matches), new_value_texts, strict=False
    ):
        if old_text != new_text:
            any_changed = True
            break

    if not any_changed:
        # VALUE 文本都没变 → 写原字节（避免 mtime 变化 + 字节完全一致）
        # 但 mtime 不变又会触发"无操作"判断，所以这里强制重写以保持语义
        return original_bytes

    # Surgical patch: 在 original_text 中按位置倒序替换每个变化的 <VALUE>...</VALUE>
    # 倒序避免前面替换影响后面位置
    out = original_text
    changes: list[tuple[int, int, str]] = []
    for om, new_text in zip(original_matches, new_value_texts, strict=False):
        old_text = om.group(1)
        if old_text != new_text:
            # 重建完整 <VALUE>new</VALUE> 段
            # 保留原属性部分（om.group(0) 的 <VALUE...> 与 </VALUE>）
            opening_tag = om.group(0).split(">", 1)[0] + ">"
            # HIGH-1 修复：``new_text`` 来自 lxml 解码文本（``&`` 而非 ``&amp;``），
            # 写入前必须重新转义为 XML 文本。否则 ``Tom & Jerry`` 写回后会变
            # 裸 ``&``，产生畸形 XML。
            replacement = f"{opening_tag}{escape_xml_text(new_text)}</VALUE>"
            changes.append((om.start(), om.end(), replacement))
    # 倒序（start 大的先替换）
    changes.sort(key=lambda c: c[0], reverse=True)
    for start, end, replacement in changes:
        out = out[:start] + replacement + out[end:]

    return out.encode("utf-8")


# ---------------------------------------------------------------------------
# Namespace detection (Sprint 8.E — T8.E.1; contract 3)
# ---------------------------------------------------------------------------


def build_default_nsmap(root: etree._Element) -> dict[str, str]:
    """纯函数：输入 lxml Element，输出 {prefix: uri}；xsi 必含。

    实现要点：
      - 根的 nsmap 里 key=None → 默认 ns，用 'ar' 作为 key（contract）
      - 其他 named prefix 保留原 prefix
      - xsi 必含（即使原文件没声明）
    """
    nsmap: dict[str, str] = {}

    # lxml 1.x 中 root.nsmap 返回 OrderedDict[str, str]；key 可能为 None
    for prefix, uri in root.nsmap.items():
        if prefix is None:
            # 默认 ns → 用 "ar" prefix（D1 / contract 3 决定）
            nsmap[_DEFAULT_NS_PREFIX] = uri
        else:
            nsmap[prefix] = uri

    # xsi 必含（contract 3 硬约束）
    if "xsi" not in nsmap:
        nsmap["xsi"] = _XSI_URI

    return nsmap


def resolve_namespaces(root: etree._Element) -> dict[str, str]:
    """build_default_nsmap 包装。提供给 ecuc.py / xpath 调用方。"""
    return build_default_nsmap(root)


# resolve_namespaces 的 frozenset cache：相同 root 共享。
# 实际工程里 read(path) 后 root 会被多次 walk；缓存 build_default_nsmap 结果
# 避免每次重算。frozenset(items) 作 cache key 跨调用可哈希。
@lru_cache(maxsize=256)
def _resolve_namespaces_from_key(
    cache_key: frozenset[tuple[str | None, str]],
) -> dict[str, str]:
    """Cached namespace resolution keyed by nsmap items frozenset.

    ``lru_cache`` 替代原先无界 ``_resolve_nsmap_cache`` dict，
    限制最多 256 条目以控制内存。
    """
    nsmap: dict[str, str] = {}
    for prefix, uri in cache_key:
        if prefix is None:
            nsmap[_DEFAULT_NS_PREFIX] = uri
        else:
            nsmap[prefix] = uri
    # xsi 必含（contract 3 硬约束）
    if "xsi" not in nsmap:
        nsmap["xsi"] = _XSI_URI
    return nsmap


def _resolve_namespaces_cached(root: etree._Element) -> dict[str, str]:
    """从 root.nsmap 提取 cache key 后委托 ``_resolve_namespaces_from_key``。"""
    cache_key = frozenset(root.nsmap.items())
    return _resolve_namespaces_from_key(cache_key)


def detect_namespaces(path: str | Path) -> dict[str, str]:
    """从根 xmlns 动态探测；返回 {prefix: uri}；xsi 必含。

    - LRU cache by (str(path), mtime_ns) — 文件改写后自动失效
    - 默认 namespace 的 key 为 'ar'
    - xsi 必含

    contract 3: arxml_io detect_namespaces API。调用方拿到 dict 后拼到 xpath 的
    `namespaces=` 参数。
    """
    p = Path(path)
    try:
        mtime_ns = p.stat().st_mtime_ns
    except OSError as e:
        raise ARXMLError(f"detect_namespaces: cannot stat {p}: {e}") from e

    return _detect_namespaces_cached(str(p), mtime_ns)


@lru_cache(maxsize=128)
def _detect_namespaces_cached(path_str: str, mtime_ns: int) -> dict[str, str]:  # noqa: ARG001
    """内部实现：lru_cache key 含 mtime_ns → 文件改写后自动 invalidate。

    mtime_ns 看似 unused，实际是 lru_cache 的 key（让 cache 随文件 mtime 自动
    invalidate）。不重命名 _mtime_ns 以保持 lru_cache 跨调用稳定。
    """
    try:
        tree = _safe_parse(path_str, recover=False)
    except OSError as e:
        raise ARXMLError(f"detect_namespaces: cannot read {path_str}: {e}") from e
    except etree.XMLSyntaxError as e:
        raise ARXMLError(f"Malformed ARXML in {path_str}: {e}") from e

    root = tree.getroot()
    nsmap = build_default_nsmap(root)
    return nsmap


# ---------------------------------------------------------------------------
# XPath / find / attribute / child-text helpers
# ---------------------------------------------------------------------------


def find_elements(
    doc: ARXMLDocument,
    xpath: str,
    namespaces: dict[str, str] | None = None,
) -> list[Any]:
    """xpath 查找元素。返回列表（无匹配返回空）。

    如果 doc 有命名空间但调用者没传 namespaces 字典，结果会是空（lxml 默认行为）。
    """
    ns = namespaces if namespaces is not None else {}
    try:
        return cast(list[Any], doc.tree.xpath(xpath, namespaces=ns))
    except etree.XPathEvalError as e:
        raise ARXMLError(f"Invalid XPath {xpath!r}: {e}") from e


def get_attribute(
    elem: Any,
    name: str,
    *,
    default: str | None = None,
) -> str | None:
    """取元素属性值；不存在时返回 default（默认 None）。"""
    return cast(str | None, elem.get(name, default))


def set_attribute(elem: Any, name: str, value: str) -> None:
    """设置元素属性（覆盖已有值）。"""
    elem.set(name, value)


def get_child_text(
    elem: Any,
    tag: str,
    *,
    namespaces: dict[str, str] | None = None,
) -> str | None:
    """取 elem 下第一个 tag 子元素的文本。子元素不存在时返回 None。

    namespaces=None（默认）：namespace-blind 匹配（用 lxml 的 `{*}` wildcard，
    按 local name 匹配）。绝大多数 ARXML 子树都在 AUTOSAR 默认命名空间下，
    这种匹配是最常用的。

    namespaces=非空：用第一个 prefix 拼接 tag 走 xpath 查找
    （如 namespaces={"ar": "..."}，"VALUE" → "ar:VALUE"）。
    """
    child = _find_child(elem, tag, namespaces)
    if child is None:
        return None
    return cast(str | None, child.text)


def set_child_text(
    elem: Any,
    tag: str,
    value: str,
    *,
    namespaces: dict[str, str] | None = None,
) -> None:
    """设置 elem 下 tag 子元素的文本。如果子元素存在则覆盖文本；否则创建新子元素。

    命名空间规则同 get_child_text。
    """
    child = _find_child(elem, tag, namespaces)
    if child is None:
        if namespaces:
            ns_uri = next(iter(namespaces.values()))
            child = etree.SubElement(elem, f"{{{ns_uri}}}{tag}")
        else:
            # 不指定 ns → 新元素无命名空间；调用方如有强需求可显式传 namespaces
            child = etree.SubElement(elem, tag)
    child.text = value


def _find_child(elem: Any, tag: str, namespaces: dict[str, str] | None) -> Any | None:
    """内部：找 elem 的直接子元素匹配 tag。"""
    if namespaces:
        prefix = next(iter(namespaces))
        return elem.find(f"{prefix}:{tag}", namespaces=namespaces)
    return elem.find("{*}" + tag)
