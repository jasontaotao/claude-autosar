"""XDM leaf values + module loading — Sprint 9.2 M1-T — T9.2-α.

Immutable dataclasses for one ``<d:var>`` leaf and one XDM module document,
plus ``load_xdm_module`` that reads an .xdm file via the BSW dispatcher
and walks ``<d:chc>/<d:ctr>/<d:lst>/<d:var>`` to emit the leaf set.

Design notes (aligned with plan §2.1 / §2.2):

  - **No shared InstanceTree abstraction** — every format owns its own
    dataclasses. We intentionally do not reuse
    :class:`claude_autosar.core.bsw.ecuc.ECUCValue` because XDM leaves
    (``<d:var>``) have a different shape than ECUC values
    (``<ECUC-NUMERICAL-PARAM-VALUE>``).
  - **Type inference heuristic** — :func:`_infer_xdm_type` reads the
    ``type`` attribute on ``<d:var>``:

      - ``INT`` / ``INTEGER`` → ``INTEGER``
      - ``FLOAT`` / ``DOUBLE`` → ``FLOAT``
      - ``BOOL`` / ``BOOLEAN`` → ``BOOLEAN``
      - ``ENUM`` / ``ENUMERATION`` → ``ENUMERATION``
      - other (FUNCTION-NAME, REFERENCE, etc.) → ``STRING``

    The heuristic mirrors what ``core/bsw/ecuc.py`` does for ECUC
    parameter types — same Literal, same fallback to STRING.
  - **Dispatcher routing** — :func:`load_xdm_module` calls
    :func:`claude_autosar.core.bsw.dispatcher.read` so the format
    detection / namespace probing is shared with the rest of the
    BSW pipeline. The loader is otherwise self-contained: it walks
    the tree with lxml xpath.
  - **Immutability** — every dataclass is ``frozen=True``. ``load``
    returns a brand-new ``XDMModule``; the underlying lxml tree is
    never mutated.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

#: XDM leaf value type — mirrors :data:`claude_autosar.core.bsw.ecuc.ECUCType`
#: but is independent (kept as a separate Literal so xdm_value is
#: self-contained — no cross-import with ECUC).
XDMValueType = Literal["INTEGER", "FLOAT", "STRING", "BOOLEAN", "ENUMERATION"]


class XDMValueError(ValueError):
    """XDM 模块加载 / 解析失败。"""


@dataclass(frozen=True)
class XDMValue:
    """XDM 树中的一个叶子值（``<d:var>``）。

    path: 用 ``/`` 分段，从 module SHORT-NAME 到叶子。
          例: ``Can/CanConfigSet/CanController/CanHwChannel``
    raw:  字面值（始终是字符串；类型语义在 ``type`` 字段）
    type: 5 种之一，按 ``<d:var>`` 的 ``type`` 属性启发式推断
    """

    path: str
    raw: str
    type: XDMValueType


@dataclass(frozen=True)
class XDMModule:
    """不可变 XDM 模块：path + module_name + values。"""

    path: Path
    module_name: str
    values: tuple[XDMValue, ...]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

#: DataModel2 data namespace (固定 d 前缀；与 inspector/xdm_report 共享)
D_NS = "http://www.tresos.de/_projects/DataModel2/06/data.xsd"


def load_xdm_module(
    path: Path,
    module_name: str,
) -> XDMModule:
    """从 ``.xdm`` 文件加载指定 module 的 XDM leaf 集合。

    用 :func:`claude_autosar.core.bsw.dispatcher.read` 拿到 lxml tree，
    然后用 ``<d:chc name=X type="AR-ELEMENT">`` xpath 定位 module root，
    再走 ``<d:ctr>`` / ``<d:lst>`` 收 ``<d:var>`` 叶子。

    :param path: ``.xdm`` 文件路径（dispatcher 会探测格式）
    :param module_name: module SHORT-NAME（``<d:chc name=X>`` 的 X）
    :raises XDMValueError: 文件读不出 / XML 畸形 / 找不到 module
    :return: 不可变 XDMModule（叶子按 xpath 出现顺序）
    """
    from claude_autosar.core.bsw.dispatcher import read as _dispatcher_read

    p = Path(path)
    try:
        doc = _dispatcher_read(p)
    except (FileNotFoundError, OSError) as e:
        raise XDMValueError(f"XDM file not readable: {p}: {e}") from e
    except Exception as e:
        # dispatcher 抛 ValueError（FormatMismatch / UnknownFormat / DispatcherError）
        raise XDMValueError(f"XDM file not readable: {p}: {e}") from e

    tree = doc.tree
    root = tree.getroot() if hasattr(tree, "getroot") else tree

    module_elem = _find_module_root(root, module_name)
    if module_elem is None:
        raise XDMValueError(f"<d:chc name={module_name!r} type=AR-ELEMENT> not found in {p}")

    values: list[XDMValue] = []
    _walk_module(module_elem, module_name, values)
    return XDMModule(
        path=p,
        module_name=module_name,
        values=tuple(values),
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _find_module_root(root: Any, module_name: str) -> Any | None:
    """找 ``<d:chc name=X type="AR-ELEMENT">`` 返回该 elem。"""
    namespaces: dict[str, str] = {"d": D_NS}
    elems = root.xpath(
        f'.//d:chc[@name="{module_name}" and @type="AR-ELEMENT"]',
        namespaces=namespaces,
    )
    return elems[0] if elems else None


def _walk_module(
    module_elem: Any,
    base_path: str,
    out: list[XDMValue],
) -> None:
    """递归下钻 module_elem，把所有 ``<d:var>`` 收集到 out。

    base_path 是到达 module_elem 的路径（一般就是 module_name）。
    """
    var_elems = module_elem.xpath(".//d:var[@name]", namespaces={"d": D_NS})
    for var in var_elems:
        # 防上跳：必须是 module_elem 的后代
        if not _is_descendant_of(var, module_elem):
            continue
        name = var.get("name")
        if not name:
            continue
        vtype_attr = var.get("type", "")
        raw_value = var.get("value", "")
        # 路径：从 module root → 所有有 name 的 ``d:`` namespace 祖先 → var name
        path = _build_var_path(var, base_path)
        out.append(
            XDMValue(
                path=path,
                raw=raw_value,
                type=_infer_xdm_type(vtype_attr),
            )
        )


def _build_var_path(var: Any, module_name: str) -> str:
    """从 ``<d:var>`` 向上 walk ancestors，收集 ``name`` 属性，拼成路径。

    与 inspector/xdm_report._build_path 同风格；这里 self-contained 不
    直接复用 inspector 模块（避免 cross-package coupling）。
    """
    parts: list[str] = [module_name]
    ancestors = list(var.iterancestors())
    ancestors.reverse()  # 远到近
    for anc in ancestors:
        if not isinstance(anc.tag, str):
            continue
        if not anc.tag.startswith(f"{{{D_NS}}}"):
            continue
        anc_name = anc.get("name")
        if anc_name and anc_name != module_name:
            parts.append(anc_name)
    parts.append(var.get("name", ""))
    return "/".join(p for p in parts if p)


def _is_descendant_of(candidate: Any, ancestor: Any) -> bool:
    """判断 ``candidate`` 是否是 ``ancestor`` 的后代（lxml iterancestors）。"""
    try:
        return any(a is ancestor for a in candidate.iterancestors())
    except (AttributeError, TypeError):
        return False


def _infer_xdm_type(type_attr: str) -> XDMValueType:
    """按 ``<d:var>`` 的 ``type`` 属性启发式推断 :data:`XDMValueType`。

    规则（plan §2.2 锁定）：

      - ``INT`` / ``INTEGER`` → INTEGER
      - ``FLOAT`` / ``DOUBLE`` → FLOAT
      - ``BOOL`` / ``BOOLEAN`` → BOOLEAN
      - ``ENUM`` → ENUMERATION
      - 其他（含 ``FUNCTION-NAME`` / ``REFERENCE`` / 空）→ STRING
    """
    t = (type_attr or "").strip().upper()
    if t in ("INT", "INTEGER"):
        return "INTEGER"
    if t in ("FLOAT", "DOUBLE"):
        return "FLOAT"
    if t in ("BOOL", "BOOLEAN"):
        return "BOOLEAN"
    if t in ("ENUM", "ENUMERATION"):
        return "ENUMERATION"
    return "STRING"


def _local_tag(elem: Any) -> str:
    """返回 elem 的 local tag（去命名空间）；保留便于未来调试。"""
    from lxml import etree

    qname = etree.QName(elem.tag)
    return cast(str, qname.localname)


__all__ = [
    "XDMValue",
    "XDMValueType",
    "XDMValueError",
    "XDMModule",
    "D_NS",
    "load_xdm_module",
]
