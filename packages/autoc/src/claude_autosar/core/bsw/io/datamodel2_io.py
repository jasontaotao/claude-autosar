"""lxml-based low-level DataModel2 (.xdm) read/write utilities.

Sprint 9.0 — T9.0.1。EB tresos Studio 26.x 输出的 ``.xdm`` 配置文件
读写工具：命名空间感知、byte-identity 友好。

DataModel2 命名空间（按 prefix 索引）：

  - d:    http://www.tresos.de/_projects/DataModel2/06/data.xsd
  - 默认: http://www.tresos.de/_projects/DataModel2/16/root.xsd
  - a:    http://www.tresos.de/_projects/DataModel2/16/attribute.xsd
  - v:    http://www.tresos.de/_projects/DataModel2/06/schema.xsd
  - ad:   http://www.tresos.de/_projects/DataModel2/08/admindata.xsd
  - cd:   http://www.tresos.de/_projects/DataModel2/08/customdata.xsd
  - f:    http://www.tresos.de/_projects/DataModel2/14/formulaexpr.xsd
  - icc:  http://www.tresos.de/_projects/DataModel2/08/implconfigclass.xsd
  - mt:   http://www.tresos.de/_projects/DataModel2/11/multitest.xsd
  - variant: http://www.tresos.de/_projects/DataModel2/11/variant.xsd

另容许 DataModel2 1.0 alias：

  - d:    http://www.3soft.de/xml/tresos/datamodel/1.0  (旧版，v1 fixtures
                                                  在 tests/fixtures/xdm/)

EB vendor 扩展（Infineon / NXP / Renesas 等）以 ``<EAS-*>`` / ``<EAS-INFO>``
节点形式出现 — 用 lxml recovery parser 容忍（``recover=True``），不
抛 ``XMLSyntaxError``。

设计要点（对齐 ``arxml_io.py``）：

  - ``detect_namespaces(path)``：从根 xmlns 动态探测；返回 ``{prefix: uri}``
    映射（默认 ns 用 ``dm`` 作 key）。
  - ``read(path)``：返回 lxml ``_ElementTree``。
  - ``write(tree, path, *, atomic=True, preserve_format=True)``：主路径
    走 ``surgical patch``（保留原文件 99% 字节），退路走
    ``cleanup_namespaces`` + ``tostring``。
  - 私有 helper：``_parse_xdm`` / ``_serialize_xdm`` /
    ``_byte_identical_patch`` / ``_cleanup_namespaces_fallback``。

Sprint 8.E.5 验收：XDM byte-identity 写回 ≥ 99% 字节相同（PIs / DOCTYPE
/ 注释 / 属性顺序 / namespace prefix 全部保住）。本模块复刻同算法。
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
import re
from typing import Any, TypeAlias, cast

from lxml import etree

# ---------------------------------------------------------------------------
# Well-known DataModel2 namespace URIs
# ---------------------------------------------------------------------------

# DataModel2 1.0 alias（保留向后兼容）：d: 指向旧 3soft URI
# DataModel2 2.0 main 命名空间：默认 ns + a/d/v
DATAMODEL2_ROOT_2_0 = "http://www.tresos.de/_projects/DataModel2/16/root.xsd"
DATAMODEL2_DATA_2_0 = "http://www.tresos.de/_projects/DataModel2/06/data.xsd"
DATAMODEL2_ATTR_2_0 = "http://www.tresos.de/_projects/DataModel2/16/attribute.xsd"
DATAMODEL2_SCHEMA_2_0 = "http://www.tresos.de/_projects/DataModel2/06/schema.xsd"
DATAMODEL2_ADMIN_2_0 = "http://www.tresos.de/_projects/DataModel2/08/admindata.xsd"
DATAMODEL2_CUSTOM_2_0 = "http://www.tresos.de/_projects/DataModel2/08/customdata.xsd"
DATAMODEL2_FORMULA_2_0 = "http://www.tresos.de/_projects/DataModel2/14/formulaexpr.xsd"
DATAMODEL2_IMPLCFG_2_0 = "http://www.tresos.de/_projects/DataModel2/08/implconfigclass.xsd"
DATAMODEL2_MULTITEST_2_0 = "http://www.tresos.de/_projects/DataModel2/11/multitest.xsd"
DATAMODEL2_VARIANT_2_0 = "http://www.tresos.de/_projects/DataModel2/11/variant.xsd"

# v1 alias
DATAMODEL2_DM_1_0 = "http://www.3soft.de/xml/tresos/datamodel/1.0"

# xsi
_XSI_URI = "http://www.w3.org/2001/XMLSchema-instance"

# 默认 ns 的 prefix（arxml_io 用 'ar'，datamodel2 用 'dm' 以避免与 AUTOSAR ar 冲突）
_DEFAULT_NS_PREFIX = "dm"

WELL_KNOWN_NAMESPACE_URIS: dict[str, tuple[str, ...]] = {
    "dm": (DATAMODEL2_ROOT_2_0,),
    "d": (DATAMODEL2_DATA_2_0, DATAMODEL2_DM_1_0),
    "a": (DATAMODEL2_ATTR_2_0,),
    "v": (DATAMODEL2_SCHEMA_2_0,),
    "ad": (DATAMODEL2_ADMIN_2_0,),
    "cd": (DATAMODEL2_CUSTOM_2_0,),
    "f": (DATAMODEL2_FORMULA_2_0,),
    "icc": (DATAMODEL2_IMPLCFG_2_0,),
    "mt": (DATAMODEL2_MULTITEST_2_0,),
    "variant": (DATAMODEL2_VARIANT_2_0,),
    "xsi": (_XSI_URI,),
}

# 兼容 alias：老代码用 DEFAULT_NAMESPACES["dm"] 取默认 URI 不破。
DEFAULT_NAMESPACES: dict[str, tuple[str, ...]] = WELL_KNOWN_NAMESPACE_URIS


class DataModel2Error(Exception):
    """DataModel2 I/O 失败时抛出的统一异常（包装 lxml/OSError）。"""


class _SurgicalPatchUnavailable(Exception):
    """Surgical patch 路径不可用（无原文件 / 文件结构变化 / 改的不是 attr/value）。"""


# ---------------------------------------------------------------------------
# read / write
# ---------------------------------------------------------------------------


def _parse_xdm(path: str | Path) -> Any:
    """Parse a .xdm file with recovery parser to tolerate EB vendor extensions.

    EB 私有 ``<EAS-*>/<EAS-INFO>`` 节点（Infineon / NXP / Renesas vendor
    扩展）可能引入 lxml 严格 parser 不识别的属性 / 元素。``recover=True``
    让 lxml 容忍并继续解析，而不是抛 ``XMLSyntaxError``。
    """
    parser = etree.XMLParser(
        recover=True,
        remove_blank_text=False,  # 保留原缩进（surgical patch 需要）
        huge_tree=True,
    )
    return etree.parse(str(path), parser=parser)


def read(path: str | Path) -> Any:
    """读 .xdm 文件。文件不存在或 XML 畸形时抛 DataModel2Error。

    返回 lxml ``_ElementTree``（注意：arxml_io 包成 ``ARXMLDocument``
    dataclass；本模块返回裸 tree 以便直接 ``write(tree, path)``，
    与 arxml_io 的 ``_TreeLike`` 兼容模式保持一致）。
    """
    try:
        return _parse_xdm(path)
    except OSError as e:
        raise DataModel2Error(f"XDM file not readable: {path}: {e}") from e
    except etree.XMLSyntaxError as e:
        raise DataModel2Error(f"Malformed XDM in {path}: {e}") from e


# 接受 ARXMLDocument / DataModel2 文档 / 裸 lxml tree
_TreeLike: TypeAlias = "Any"


def write(
    target: _TreeLike,
    path: str | Path | None = None,
    *,
    atomic: bool = True,
    preserve_format: bool = True,
) -> None:
    """写 lxml 树到 path.

    签名（对齐 arxml_io）：``write(tree, path, *, atomic=True, preserve_format=True)``。

    - preserve_format=True (默认): 保留 PIs / DOCTYPE / 注释 / 属性顺序 /
      namespace prefix。主路径走"原字节 + surgical patch"（保留原文件字节，
      只替换 ``<a:a name="..." value="..."/>`` 段）。退路: lxml
      ``cleanup_namespaces`` + ``tostring`` + 重建 DOCTYPE。
    - preserve_format=False: 走 tostring 软保真（不保证 PI / DOCTYPE /
      属性顺序）。
    - atomic=True (默认): ``.tmp`` + ``os.replace``; 失败时原文件保持不变。
    """
    # 解析调用形态: 提取 tree + 路径
    if hasattr(target, "tree") and hasattr(target, "path"):
        # 类 ARXMLDocument 对象
        tree = target.tree
        if path is None:
            path = target.path
    else:
        tree = target
        if path is None:
            raise TypeError(
                "write(tree, ...) requires explicit path when target is not a document-like object"
            )

    out_path = Path(path)
    if not atomic:
        _write_to_path(out_path, tree, preserve_format=preserve_format)
        return

    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    try:
        _write_to_path(tmp, tree, preserve_format=preserve_format)
        os.replace(tmp, out_path)
    except (OSError, etree.SerialisationError) as e:
        # 清理可能残留的 .tmp
        with contextlib.suppress(OSError):
            if tmp.exists():
                tmp.unlink()
        raise DataModel2Error(f"Failed to write XDM atomically to {out_path}: {e}") from e


# ---------------------------------------------------------------------------
# Internal write pipeline
# ---------------------------------------------------------------------------


def _write_to_path(
    path: Path,
    tree: Any,
    *,
    preserve_format: bool = True,
) -> None:
    """实际写 XML 字节到 path.

    preserve_format=True:
      主路径 (surgical patch): 找原文件中所有 ``<a:a name="X" value="Y"/>``
        这种"已被 set_attr 改过"的段 → 替换原文件中对应段字节范围。
        99% 字节原样保留 → PIs / DOCTYPE / 注释 / 属性顺序 /
        namespace prefix 全部保住。
      退路 (tostring): cleanup_namespaces + tostring + 重建 DOCTYPE.

    preserve_format=False: 走纯 tostring 软保真.
    """
    if preserve_format:
        try:
            _byte_identical_patch(path, tree)
            return
        except _SurgicalPatchUnavailable:
            pass

    # 退路 / preserve_format=False
    _cleanup_namespaces_fallback(path, tree, preserve_format=preserve_format)


def _byte_identical_patch(path: Path, tree: Any) -> None:
    """Surgical patch 主路径.

    策略: 文件已存在 → 读原字节 → 直接从 in-memory tree 遍历所有
    ``<a:a name="X" value="Y"/>`` attr 元素，对比原文件中对应段，
    按位置倒序替换 → 99% 字节原样保留.

    触发条件: 改前 vs 改后只在 ``<a:a value="...">`` 段上不同
    （典型 set_attr_value 用例）。

    失败: 抛 ``_SurgicalPatchUnavailable`` 让调用方降级。
    """
    # atomic 写场景: path 是 <name>.xdm.tmp → 用 <name>.xdm 做 patch
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


def _parse_attrs(attr_str: str) -> dict[str, str]:
    """从 ``name="..." value="..."`` 解析出 {name: value}."""
    out: dict[str, str] = {}
    for m in re.finditer(r'(\w+(?::\w+)?)="([^"]*)"', attr_str):
        out[m.group(1)] = m.group(2)
    return out


def _walk_a_elems(elem: Any) -> list[Any]:
    """按 document order 收集所有 ``<a:a>`` 元素（self-closing + parent-form）。"""
    out: list[Any] = []
    if isinstance(elem.tag, str) and etree.QName(elem.tag).localname == "a":
        out.append(elem)
    for child in elem:
        if isinstance(child.tag, str):
            out.extend(_walk_a_elems(child))
    return out


def _apply_surgical_patch_to_bytes(original_bytes: bytes, tree: Any) -> bytes:
    """核心 surgical patch 逻辑. 输入原字节 + 树 → 输出 patched 字节.

    触发条件: 改前 vs 改后只在 ``<a:a name="..." value="..."/>`` 段上不同
    （self-closing 形态）或 ``<a:v>...</a:v>`` 段上不同（parent-form）。

    DataModel2 与 ARXML 的差别: ARXML surgical patch 改的是 ``<VALUE>``
    元素的文本；DataModel2 改的是 ``<a:a name="..." value="...">`` 的
    ``value`` 属性（self-closing）或 child text（parent-form）。

    EB tresos 实际输出两种形态：

      A) Self-closing: ``<a:a name="X" value="Y"/>`` — surgical patch 直接
         替换 value 属性。
      B) Parent-form: ``<a:a name="X"><a:v>Y</a:v></a:a>`` — value 是
         child text。surgical patch 替换第一个 ``<a:v>...</a:v>`` 段。

    本函数先尝试 (A)；若 tree 中包含 parent-form 元素（regex 找到的 self-closing
    段数 < 树中的 ``<a:a>`` 总数），自动降级到 (B) parent-form patch。
    """
    original_text = original_bytes.decode("utf-8", errors="replace")

    # 冷路径：c14n 比较（O(n)）— 当 <a:a> 段全无变化时，决定 fallback vs
    # 真无变化（保留字节）。
    # c14n 输出在 attribute order / namespace prefix 等做 canonical 化，
    # 仅语义层比较。
    try:
        new_canonical = etree.tostring(tree, method="c14n")
    except Exception:  # noqa: BLE001
        new_canonical = b""  # 走后续 patch 失败 → fallback
    try:
        orig_canonical = etree.tostring(etree.fromstring(original_bytes), method="c14n")
    except Exception:  # noqa: BLE001
        orig_canonical = b""
    if new_canonical and orig_canonical and new_canonical == orig_canonical:
        # 真无变化 — 保留原字节（byte-identity 100%）
        return original_bytes

    # 匹配 self-closing: <a:a name="..." value="..."/>
    self_closing_pattern = re.compile(
        r"<a:a\s+([^>]*?)/>",
        re.DOTALL,
    )
    # 匹配 parent-form opening: <a:a ...> （attrs 不以 `/` 结尾，即非
    # self-closing），捕获 attrs。`[^>]+?` 要求至少 1 个非 `>` 字符；
    # `[^/]` 排除 attrs 以 `/` 结尾的 self-closing 段。
    parent_open_pattern = re.compile(
        r"<a:a\s+([^>]+?[^/])>",
        re.DOTALL,
    )

    # 从 in-memory tree 收集所有 <a:a> 元素（按 document order）
    new_attr_elements = _walk_a_elems(tree.getroot())

    # 区分 self-closing 和 parent-form
    tree_self_closing = [e for e in new_attr_elements if len(e) == 0]
    tree_parent = [e for e in new_attr_elements if len(e) > 0]

    # 文本里 self-closing / parent-form 段数
    self_closing_matches = list(self_closing_pattern.finditer(original_text))
    parent_open_matches = list(parent_open_pattern.finditer(original_text))

    if len(tree_self_closing) == len(self_closing_matches) and len(tree_self_closing) > 0:
        patched = _patch_self_closing(
            original_text,
            tree_self_closing,
            self_closing_matches,
        )
        if patched is not None:
            return patched
        # self-closing attrs 无变化 — 试 parent-form（a:v 文本可能改了）
    if len(tree_parent) == len(parent_open_matches) and len(tree_parent) > 0:
        return _patch_parent_form(
            original_text,
            original_bytes,
            new_attr_elements,
        )
    # 混合或数量对不上 → 退路
    raise _SurgicalPatchUnavailable(
        f"cannot surgical-patch: tree_self_closing={len(tree_self_closing)} "
        f"tree_parent={len(tree_parent)} text_self_closing={len(self_closing_matches)} "
        f"text_parent_open={len(parent_open_matches)}"
    )


def _patch_self_closing(
    original_text: str,
    tree_self_closing: list[Any],
    original_matches: list[re.Match[str]],
) -> bytes | None:
    """Strategy A: 全 self-closing 形态 surgical patch。"""
    new_attr_pairs: list[tuple[str, str]] = [
        (e.get("name", ""), e.get("value", "")) for e in tree_self_closing
    ]

    if len(new_attr_pairs) != len(original_matches):
        raise _SurgicalPatchUnavailable(
            f"<a:a/> self-closing count differs: new={len(new_attr_pairs)} "
            f"orig={len(original_matches)}"
        )

    # 检查每个 attr 元素文本是否变化
    any_changed = False
    for om, (new_name, new_value) in zip(original_matches, new_attr_pairs, strict=False):
        orig_attrs = _parse_attrs(om.group(1))
        orig_value = orig_attrs.get("value", "")
        orig_name = orig_attrs.get("name", "")
        if orig_name != new_name or orig_value != new_value:
            any_changed = True
            break

    if not any_changed:
        # 没有 <a:a> attrs 变化 — caller 可能改了 parent-form <a:v> 文本
        # 或 <d:var> 等非 a:a 段。返回 None 让 caller 继续试 parent-form
        # 或 fallback。
        return None

    # 按位置倒序替换每个变化的段
    out = original_text
    changes: list[tuple[int, int, str]] = []
    for om, (new_name, new_value) in zip(original_matches, new_attr_pairs, strict=False):
        orig_attrs = _parse_attrs(om.group(1))
        orig_value = orig_attrs.get("value", "")
        orig_name = orig_attrs.get("name", "")
        if orig_name != new_name or orig_value != new_value:
            # 重建完整 <a:a name="..." value="..."/> 段
            # 保留原始属性顺序
            if "name" in om.group(1).split("value=")[0]:
                replacement = f'<a:a name="{new_name}" value="{new_value}"/>'
            else:
                replacement = f'<a:a value="{new_value}" name="{new_name}"/>'
            changes.append((om.start(), om.end(), replacement))
    changes.sort(key=lambda c: c[0], reverse=True)
    for start, end, replacement in changes:
        out = out[:start] + replacement + out[end:]
    return out.encode("utf-8")


def _patch_parent_form(
    original_text: str,
    original_bytes: bytes,
    new_attr_elements: list[Any],
) -> bytes:
    """Strategy B: 全 parent-form 形态 surgical patch.

    parent-form: ``<a:a name="X"><a:v>Y</a:v></a:a>``
    改的是 ``<a:v>...</a:v>`` 内容（value 存在子元素里）。
    """
    # 收集所有 <a:v>...</a:v> 段位置
    av_pattern = re.compile(r"<a:v>([^<]*)</a:v>", re.DOTALL)
    av_matches = list(av_pattern.finditer(original_text))

    # 从 tree 中按 document order 收集所有 <a:v> 元素
    new_av_texts: list[str] = []

    def _walk_av(elem: Any) -> None:
        if isinstance(elem.tag, str) and etree.QName(elem.tag).localname == "v":
            new_av_texts.append(elem.text or "")
        for child in elem:
            if isinstance(child.tag, str):
                _walk_av(child)

    # 用第一个 <a:a> 元素的 root 来 walk（拿到完整 tree 的 <a:v> 序列）
    root = new_attr_elements[0].getroottree()
    _walk_av(root.getroot())

    if len(new_av_texts) != len(av_matches):
        raise _SurgicalPatchUnavailable(
            f"<a:v> count differs: new={len(new_av_texts)} orig={len(av_matches)}"
        )

    # 检查变化
    any_changed = False
    for om, new_text in zip(av_matches, new_av_texts, strict=False):
        if om.group(1) != new_text:
            any_changed = True
            break

    if not any_changed:
        return original_bytes

    # 按位置倒序替换
    out = original_text
    changes: list[tuple[int, int, str]] = []
    for om, new_text in zip(av_matches, new_av_texts, strict=False):
        if om.group(1) != new_text:
            replacement = f"<a:v>{new_text}</a:v>"
            changes.append((om.start(), om.end(), replacement))
    changes.sort(key=lambda c: c[0], reverse=True)
    for start, end, replacement in changes:
        out = out[:start] + replacement + out[end:]
    return out.encode("utf-8")


def _cleanup_namespaces_fallback(
    path: Path,
    tree: Any,
    *,
    preserve_format: bool,
) -> None:
    """退路：cleanup_namespaces + tostring + 重建 DOCTYPE."""
    if preserve_format:
        with contextlib.suppress(ValueError, etree.Error):
            etree.cleanup_namespaces(tree)
        doctype = tree.docinfo.doctype if hasattr(tree, "docinfo") else None
        body = etree.tostring(
            tree,
            xml_declaration=True,
            encoding="UTF-8",
            standalone=True,
            doctype=doctype,
        )
        path.write_bytes(body)
    else:
        path.write_bytes(
            etree.tostring(
                tree,
                xml_declaration=True,
                encoding="UTF-8",
                standalone=True,
            )
        )


# ---------------------------------------------------------------------------
# Namespace detection (Sprint 9.0 — T9.0.1)
# ---------------------------------------------------------------------------


def build_default_nsmap(root: Any) -> dict[str, str]:
    """纯函数：输入 lxml Element，输出 ``{prefix: uri}``；xsi 必含。

    实现要点：
      - 根的 nsmap 里 key=None → 默认 ns，用 ``dm`` 作 key（避免与 ARXML
        的 ``ar`` 冲突）
      - 其他 named prefix 保留原 prefix
      - xsi 必含（即使原文件没声明）
    """
    nsmap: dict[str, str] = {}

    for prefix, uri in root.nsmap.items():
        if prefix is None:
            nsmap[_DEFAULT_NS_PREFIX] = cast(str, uri)
        else:
            nsmap[cast(str, prefix)] = cast(str, uri)

    # xsi 必含
    if "xsi" not in nsmap:
        nsmap["xsi"] = _XSI_URI

    return nsmap


def resolve_namespaces(root: Any) -> dict[str, str]:
    """``build_default_nsmap`` 包装。提供给调用方做 xpath / find_elements。"""
    return build_default_nsmap(root)


def detect_namespaces(path: str | Path) -> dict[str, str]:
    """从根 xmlns 动态探测；返回 ``{prefix: uri}``；xsi 必含。

    contract 9.0: datamodel2_io detect_namespaces API。调用方拿到 dict
    后拼到 xpath 的 ``namespaces=`` 参数。
    """
    p = Path(path)
    try:
        tree = _parse_xdm(p)
    except OSError as e:
        raise DataModel2Error(f"detect_namespaces: cannot read {p}: {e}") from e
    except etree.XMLSyntaxError as e:
        raise DataModel2Error(f"Malformed XDM in {p}: {e}") from e

    root = tree.getroot()
    return build_default_nsmap(root)


# ---------------------------------------------------------------------------
# Namespace-blind element / attribute helpers（对齐 arxml_io）
# ---------------------------------------------------------------------------


def find_elements(
    tree: Any,
    xpath: str,
    namespaces: dict[str, str] | None = None,
) -> list[Any]:
    """xpath 查找元素。返回列表（无匹配返回空）。

    如果 tree 有命名空间但调用者没传 namespaces 字典，结果会是空
    （lxml 默认行为）。
    """
    ns = namespaces if namespaces is not None else {}
    try:
        return cast(list[Any], tree.xpath(xpath, namespaces=ns))
    except etree.XPathEvalError as e:
        raise DataModel2Error(f"Invalid XPath {xpath!r}: {e}") from e


def get_attribute(elem: Any, name: str, *, default: str | None = None) -> str | None:
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

    namespaces=None（默认）：namespace-blind 匹配（用 lxml 的 ``{*}``
    wildcard，按 local name 匹配）。

    namespaces=非空：用第一个 prefix 拼接 tag 走 xpath 查找。
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
    """设置 elem 下 tag 子元素的文本。如果子元素存在则覆盖文本；否则创建新子元素。"""
    child = _find_child(elem, tag, namespaces)
    if child is None:
        if namespaces:
            ns_uri = next(iter(namespaces.values()))
            child = etree.SubElement(elem, f"{{{ns_uri}}}{tag}")
        else:
            child = etree.SubElement(elem, tag)
    child.text = value


def _find_child(
    elem: Any,
    tag: str,
    namespaces: dict[str, str] | None,
) -> Any | None:
    """内部：找 elem 的直接子元素匹配 tag。"""
    if namespaces:
        prefix = next(iter(namespaces))
        return elem.find(f"{prefix}:{tag}", namespaces=namespaces)
    return elem.find("{*}" + tag)
