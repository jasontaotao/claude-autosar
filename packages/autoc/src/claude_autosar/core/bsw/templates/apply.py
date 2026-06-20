"""Unified template diff apply — Sprint 9.2 M1-T — T9.2-β.

按 :class:`TemplateDiffResult` 把 ``template`` 端的值写回 ``doc_path``。
支持双格式（.arxml / .xdm），通过 :mod:`claude_autosar.core.bsw.dispatcher`
自动探测格式 / 走对应 IO 库。

设计要点（plan v2 §2.2 / §2.3）:

  - **Unified API** — ``apply_template_diff`` 是双格式唯一对外入口；
    ``TemplateDiff``（来自 ``arxml_diff`` 或 ``xdm_diff``）直接喂入。
  - **Byte-identity 友好** — 走 ``dispatcher.read / write(preserve_format=True)``
    对单 VALUE / 单 a:a 段做 surgical patch（plan v2 §1.4 byte-identity 100%
    验收）。
  - **DRY_RUN vs APPLY** — ``ApplyMode`` enum 切换：dry-run 只返回
    ``ApplyResult`` 不写文件；apply 写文件 + 计算 ``bytes_changed``。
  - **Op 范围** — M1-T 范围只支持 ``modify``（设 VALUE / a:a value）。
    ``add`` / ``delete`` 显式抛 ``NotImplementedError``（告知 caller
    后续 sprint 加 container/leaf CRUD；不偷偷做 byte-identity 破坏）。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from claude_autosar.core.bsw.dispatcher import LoadedDocument
from claude_autosar.core.bsw.dispatcher import read as dispatcher_read
from claude_autosar.core.bsw.dispatcher import write as dispatcher_write

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class ApplyMode(str, Enum):  # noqa: UP042 - intentional str+Enum for serialization friendliness
    """apply 模式。

    DRY_RUN: 不写文件；返回 ApplyResult（含会写多少 diff / 多少字节）
    APPLY: 写文件；bytes_changed 反映实际 diff
    """

    DRY_RUN = "dry_run"
    APPLY = "apply"


@dataclass(frozen=True)
class ApplyResult:
    """apply 操作的不可变结果。

    mode: 执行的模式
    path: 操作的文档路径
    diffs_applied: 实际处理的 diff 条数（DRY_RUN 时 == len(diff.diffs)；
                   APPLY 时只包含已实现的 op；其他 op 会抛异常，故不会到达此处）
    bytes_changed: apply 模式：新文件 size - 原文件 size（绝对值）
                   dry_run 模式：原文件 size（用于"如果 apply 会改多少"
                   估算；具体改多少要等真跑过才知 — 这里用原 size 占位）
    diffs: 实际处理的 diff 列表
    """

    mode: ApplyMode
    path: Path
    diffs_applied: int
    bytes_changed: int
    diffs: tuple[object, ...]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def apply_template_diff(
    doc_path: Path,
    diff: object,
    *,
    mode: ApplyMode = ApplyMode.DRY_RUN,
) -> ApplyResult:
    """按 diff 写回 doc_path。

    :param doc_path: 当前文档（.arxml / .xdm 之一，由 dispatcher 自动探测）
    :param diff: :class:`TemplateDiffResult` 实例（来自
        :func:`arxml_diff.diff_arxml_templates` 或
        :func:`xdm_diff.diff_xdm_templates`）
    :param mode: DRY_RUN（默认；不写文件） / APPLY（写文件）
    :return: 不可变 :class:`ApplyResult`
    :raises NotImplementedError: diff 含 ``add`` 或 ``delete`` op（M1-T 范围外）
    :raises FileNotFoundError: doc_path 不存在
    :raises ValueError: diff 不是 TemplateDiffResult 类型
    """
    diffs_tuple = _extract_diffs(diff)
    if not diffs_tuple:
        # 没 diff → 啥也不做；返回空 result
        original_size = doc_path.stat().st_size if doc_path.exists() else 0
        return ApplyResult(
            mode=mode,
            path=doc_path,
            diffs_applied=0,
            bytes_changed=0,
            diffs=(),
        )

    # 读 doc → 走对应 IO 改 VALUE / a:a value → 写回
    loaded = dispatcher_read(doc_path)
    original_size = doc_path.stat().st_size

    # Sprint 12 T12.4：支持 modify / add / delete
    modify_diffs = tuple(d for d in diffs_tuple if getattr(d, "op", "modify") == "modify")
    add_diffs = tuple(d for d in diffs_tuple if getattr(d, "op", "add") == "add")
    delete_diffs = tuple(d for d in diffs_tuple if getattr(d, "op", "delete") == "delete")

    if modify_diffs:
        _apply_modify_to_tree(loaded, modify_diffs)
    if add_diffs:
        _apply_add_to_tree(loaded, add_diffs)
    if delete_diffs:
        _apply_delete_to_tree(loaded, delete_diffs)

    if mode == ApplyMode.APPLY:
        # Sprint 12 T12.4：add/delete 需要 preserve_format=False 以重建完整 XML
        # modify 保持 preserve_format=True 以保留字节一致性
        has_structural = bool(add_diffs or delete_diffs)
        dispatcher_write(loaded, preserve_format=not has_structural)
        new_size = doc_path.stat().st_size
        bytes_changed = abs(new_size - original_size)
    else:
        # DRY_RUN：不算真实 bytes_changed（没改文件），用 0 占位
        bytes_changed = 0

    return ApplyResult(
        mode=mode,
        path=doc_path,
        diffs_applied=len(diffs_tuple),
        bytes_changed=bytes_changed,
        diffs=diffs_tuple,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_diffs(diff_obj: object) -> tuple[object, ...]:
    """从 TemplateDiffResult 取 diffs tuple。duck-typed（不强制 import）。"""
    diffs = getattr(diff_obj, "diffs", None)
    if diffs is None or not isinstance(diffs, tuple):
        raise ValueError(
            f"apply_template_diff: expected TemplateDiffResult-like object "
            f"with .diffs tuple; got {type(diff_obj).__name__}"
        )
    return diffs


def _apply_modify_to_tree(
    loaded: LoadedDocument,
    diffs: tuple[object, ...],
) -> None:
    """对 in-memory tree 改每个 modify diff 的 target 元素文本。

    格式由 ``loaded.format`` 决定；走对应 io 模块的 set_child_text。
    """
    if loaded.format == "arxml":
        _apply_modify_arxml(loaded, diffs)
        return
    if loaded.format == "xdm":
        _apply_modify_xdm(loaded, diffs)
        return
    raise ValueError(f"apply_template_diff: unknown format {loaded.format!r}")


def _apply_add_to_tree(
    loaded: LoadedDocument,
    diffs: tuple[object, ...],
) -> None:
    """对 in-memory tree 添加每个 add diff 的新参数节点。"""
    if loaded.format == "arxml":
        _apply_add_arxml(loaded, diffs)
        return
    if loaded.format == "xdm":
        _apply_add_xdm(loaded, diffs)
        return
    raise ValueError(f"apply_template_diff: unknown format {loaded.format!r}")


def _apply_delete_to_tree(
    loaded: LoadedDocument,
    diffs: tuple[object, ...],
) -> None:
    """对 in-memory tree 删除每个 delete diff 的参数节点。"""
    if loaded.format == "arxml":
        _apply_delete_arxml(loaded, diffs)
        return
    if loaded.format == "xdm":
        _apply_delete_xdm(loaded, diffs)
        return
    raise ValueError(f"apply_template_diff: unknown format {loaded.format!r}")


# ---------------------------------------------------------------------------
# ARXML apply
# ---------------------------------------------------------------------------


def _apply_modify_arxml(
    loaded: LoadedDocument,
    diffs: tuple[object, ...],
) -> None:
    """ARXML 端 modify apply。

    路径 ``Can/CanConfigSet/CanTxIPdu_0/CanTxIPduHandleId`` 在树中表示为::

        <ECUC-MODULE-CONFIGURATION-VALUES>          (module_name)
          <SHORT-NAME>Can</SHORT-NAME>
          <CONTAINERS>
            <ECUC-CONTAINER-VALUE>                   (CanConfigSet)
              <SHORT-NAME>CanConfigSet</SHORT-NAME>
              <SUB-CONTAINERS>
                <ECUC-CONTAINER-VALUE>               (CanTxIPdu_0)
                  <SHORT-NAME>CanTxIPdu_0</SHORT-NAME>
                  <PARAMETER-VALUES>
                    <ECUC-NUMERICAL-PARAM-VALUE>
                      <DEFINITION-REF DEST=...>/.../CanTxIPduHandleId
                      <VALUE>100</VALUE>            ← 改这里

    走法：从 root 开始，按 path segments 逐层下钻，匹配 SHORT-NAME 节点；
    最后一段对应 parameter-value 的 ``DEFINITION-REF`` 短名；命中后
    改 ``<VALUE>...</VALUE>`` 文本。
    """
    from claude_autosar.core.bsw import arxml_io

    tree = loaded.tree
    root = tree.getroot() if hasattr(tree, "getroot") else tree

    for d in diffs:
        if getattr(d, "op", "modify") != "modify":
            continue
        template = getattr(d, "template", None)
        if template is None:
            continue
        path = getattr(template, "path", None) or getattr(d, "path", None)
        new_raw = getattr(template, "raw", None)
        if not path or new_raw is None:
            continue

        # 路径：module_name/container1/.../param_short_name
        segments = path.strip("/").split("/")
        if len(segments) < 2:
            continue  # 至少 module + 1 个 leaf

        target_param_short = segments[-1]
        container_segments = segments[:-1]
        module_name = container_segments[0]
        nested_containers = container_segments[1:]

        # 找 module root
        module_elem = _find_module_root_arxml(root, module_name)
        if module_elem is None:
            continue

        # 逐层下钻到含 target_param 的 container
        parent = module_elem
        for cname in nested_containers:
            found = _find_child_container_arxml(parent, cname)
            if found is None:
                parent = None
                break
            parent = found
        if parent is None:
            continue

        # 找含 DEFINITION-REF 短名为 target_param_short 的 param-value 节点
        param_value = _find_param_value_arxml(parent, target_param_short)
        if param_value is None:
            continue

        # 改 <VALUE> 文本
        arxml_io.set_child_text(param_value, "VALUE", new_raw)


def _apply_add_arxml(
    loaded: LoadedDocument,
    diffs: tuple[object, ...],
) -> None:
    """ARXML 端 add apply：在 parent container 下创建新的 param-value 节点。"""
    from claude_autosar.core.bsw import arxml_io

    tree = loaded.tree
    root = tree.getroot() if hasattr(tree, "getroot") else tree

    for d in diffs:
        if getattr(d, "op", "add") != "add":
            continue
        template = getattr(d, "template", None)
        if template is None:
            continue
        path = getattr(template, "path", None) or getattr(d, "path", None)
        new_raw = getattr(template, "raw", None)
        param_type = getattr(template, "type", "STRING")
        if not path or new_raw is None:
            continue

        segments = path.strip("/").split("/")
        if len(segments) < 2:
            continue

        target_param_short = segments[-1]
        container_segments = segments[:-1]
        module_name = container_segments[0]
        nested_containers = container_segments[1:]

        # 找 module root
        module_elem = _find_module_root_arxml(root, module_name)
        if module_elem is None:
            continue

        # 逐层下钻到 parent container
        parent = module_elem
        for cname in nested_containers:
            found = _find_child_container_arxml(parent, cname)
            if found is None:
                parent = None
                break
            parent = found
        if parent is None:
            continue

        # 确定 param-value tag（根据类型）
        # HIGH-8 修复：BOOLEAN 必须用 ECUC-NUMERICAL-PARAM-VALUE（数字 0/1）
        # + DEST="ECUC-NUMERICAL-PARAM-DEF"。AUTOSAR 没单独的 BOOLEAN-PARAM-DEF；
        # EB tresos / Vector 会拒绝 ``ECUC-TEXTUAL-PARAM-VALUE`` + ``ECUC-BOOLEAN-PARAM-DEF``。
        if param_type in ("INTEGER", "FLOAT", "BOOLEAN"):
            pv_tag = "ECUC-NUMERICAL-PARAM-VALUE"
        else:
            pv_tag = "ECUC-TEXTUAL-PARAM-VALUE"

        # 构造 DEFINITION-REF 路径
        def_ref_path = f"/{'/'.join(segments)}"

        # 找或创建 PARAMETER-VALUES wrapper
        pv_wrapper = parent.find("{*}PARAMETER-VALUES")
        if pv_wrapper is None:
            from lxml import etree

            nsmap = {"ar": "http://autosar.org/schema/r4.0"}
            pv_wrapper = etree.SubElement(parent, "{http://autosar.org/schema/r4.0}PARAMETER-VALUES")

        # 创建新的 param-value 节点
        from lxml import etree

        ns = "http://autosar.org/schema/r4.0"
        pv_elem = etree.SubElement(pv_wrapper, f"{{{ns}}}{pv_tag}")
        def_ref = etree.SubElement(pv_elem, f"{{{ns}}}DEFINITION-REF")
        # HIGH-8 修复：DEST 同上 — BOOLEAN 也用 NUMERICAL-DEF
        if param_type == "STRING":
            dest = "ECUC-STRING-PARAM-DEF"
        else:
            dest = f"ECUC-{param_type}-PARAM-DEF" if param_type != "BOOLEAN" else "ECUC-NUMERICAL-PARAM-DEF"
        def_ref.set("DEST", dest)
        def_ref.text = def_ref_path
        value = etree.SubElement(pv_elem, f"{{{ns}}}VALUE")
        value.text = new_raw


def _apply_delete_arxml(
    loaded: LoadedDocument,
    diffs: tuple[object, ...],
) -> None:
    """ARXML 端 delete apply：从 parent container 删除匹配的 param-value 节点。"""
    tree = loaded.tree
    root = tree.getroot() if hasattr(tree, "getroot") else tree

    for d in diffs:
        if getattr(d, "op", "delete") != "delete":
            continue
        current = getattr(d, "current", None)
        if current is None:
            continue
        path = getattr(current, "path", None) or getattr(d, "path", None)
        if not path:
            continue

        segments = path.strip("/").split("/")
        if len(segments) < 2:
            continue

        target_param_short = segments[-1]
        container_segments = segments[:-1]
        module_name = container_segments[0]
        nested_containers = container_segments[1:]

        # 找 module root
        module_elem = _find_module_root_arxml(root, module_name)
        if module_elem is None:
            continue

        # 逐层下钻到 parent container
        parent = module_elem
        for cname in nested_containers:
            found = _find_child_container_arxml(parent, cname)
            if found is None:
                parent = None
                break
            parent = found
        if parent is None:
            continue

        # 找匹配的 param-value 节点并删除
        param_value = _find_param_value_arxml(parent, target_param_short)
        if param_value is not None:
            param_value.getparent().remove(param_value)


def _find_module_root_arxml(root: Any, module_name: str) -> Any | None:
    """找 ``<ECUC-MODULE-CONFIGURATION-VALUES>`` SHORT-NAME == module_name."""
    for elem in root.iter("{*}ECUC-MODULE-CONFIGURATION-VALUES"):
        sn = elem.find("{*}SHORT-NAME")
        if sn is not None and sn.text == module_name:
            return elem
    return None


def _find_child_container_arxml(parent: Any, container_name: str) -> Any | None:
    """在 parent 下找 SHORT-NAME == container_name 的 container。

    兼容 ::

      <CONTAINERS><ECUC-CONTAINER-VALUE>...  (wrapper 形式)
      <CONTAINERS><ECUC-PARAM-CONF-CONTAINER>...  (AUTOSAR 标准)
      <SUB-CONTAINERS><ECUC-CONTAINER-VALUE>...
      <ECUC-CONTAINER-VALUE>...  (无 wrapper)
      <ECUC-PARAM-CONF-CONTAINER>...  (无 wrapper)
    """
    _CONTAINER_TAGS = ("ECUC-CONTAINER-VALUE", "ECUC-PARAM-CONF-CONTAINER")
    for child in parent:
        if not isinstance(child.tag, str):
            continue
        local = _local_tag_str(child.tag)
        if local in ("CONTAINERS", "SUB-CONTAINERS"):
            for sub in child:
                if _local_tag_str(sub.tag) in _CONTAINER_TAGS:
                    sn = sub.find("{*}SHORT-NAME")
                    if sn is not None and sn.text == container_name:
                        return sub
        elif local in _CONTAINER_TAGS:
            sn = child.find("{*}SHORT-NAME")
            if sn is not None and sn.text == container_name:
                return child
    return None


def _find_param_value_arxml(
    parent: Any,
    param_short_name: str,
) -> Any | None:
    """在 parent 下找 ``DEFINITION-REF`` 短名为 param_short_name 的 param-value 节点。"""
    _PARAM_VALUE_TAGS = (
        "ECUC-NUMERICAL-PARAM-VALUE",
        "ECUC-TEXTUAL-PARAM-VALUE",
        "ECUC-ADDITIONAL-PARAM-VALUE",
    )
    for child in parent:
        if not isinstance(child.tag, str):
            continue
        local = _local_tag_str(child.tag)
        if local == "PARAMETER-VALUES":
            for pv in child:
                if (
                    _local_tag_str(pv.tag) in _PARAM_VALUE_TAGS
                    and _def_ref_short(pv) == param_short_name
                ):
                    return pv
        elif local in _PARAM_VALUE_TAGS and _def_ref_short(child) == param_short_name:
            return child
    return None


def _def_ref_short(pv: Any) -> str | None:
    """取 ``<DEFINITION-REF>...</DEFINITION-REF>`` 文本的最后一段。"""
    def_ref = pv.find("{*}DEFINITION-REF")
    if def_ref is None:
        return None
    text = def_ref.text
    if not text:
        return None
    parts = text.strip("/").split("/")
    return parts[-1] if parts else None


def _local_tag_str(tag: str) -> str:
    """去命名空间取 local tag。"""
    from lxml import etree

    qname = etree.QName(tag)
    local: str = qname.localname
    return local


# ---------------------------------------------------------------------------
# XDM apply
# ---------------------------------------------------------------------------


def _apply_modify_xdm(
    loaded: LoadedDocument,
    diffs: tuple[object, ...],
) -> None:
    """XDM 端 modify apply。

    路径 ``Can/CanConfigSet/CanTxIPdu/CanTxIPdu_0/CanTxIPduHandleId`` 在树中
    表示为::

        <d:chc name="Can" type="AR-ELEMENT">     (module_name)
          <d:ctr type="MODULE-CONFIGURATION">
            <d:ctr name="CanConfigSet">          (CanConfigSet)
              <d:ctr name="CanTxIPdu_0">         (CanTxIPdu_0)
                <d:var name="CanTxIPduHandleId"  ← 改这个的 value 属性
                       value="100"/>

    走法：从 root 开始，按 path segments 在 d: namespace 下的 ``d:ctr`` /
    ``d:lst`` 节点下钻，匹配 ``name`` 属性；最后一段对应 ``<d:var>`` 节点
    改 ``value`` 属性。
    """
    from claude_autosar.core.bsw.io import datamodel2_io

    tree = loaded.tree
    root = tree.getroot() if hasattr(tree, "getroot") else tree

    for d in diffs:
        if getattr(d, "op", "modify") != "modify":
            continue
        template = getattr(d, "template", None)
        if template is None:
            continue
        path = getattr(template, "path", None) or getattr(d, "path", None)
        new_raw = getattr(template, "raw", None)
        if not path or new_raw is None:
            continue

        segments = path.strip("/").split("/")
        if len(segments) < 2:
            continue

        var_name = segments[-1]
        container_segments = segments[:-1]

        # 从 root 下钻到含 var 的 container
        parent = root
        for cname in container_segments:
            found = _find_child_container_xdm(parent, cname)
            if found is None:
                parent = None
                break
            parent = found
        if parent is None:
            continue

        # 找 <d:var name="var_name">
        var_elem = _find_var_xdm(parent, var_name)
        if var_elem is None:
            continue

        # 改 value 属性
        datamodel2_io.set_attribute(var_elem, "value", new_raw)


def _apply_add_xdm(
    loaded: LoadedDocument,
    diffs: tuple[object, ...],
) -> None:
    """XDM 端 add apply：在 parent container 下创建新的 d:var 节点。"""
    from lxml import etree

    tree = loaded.tree
    root = tree.getroot() if hasattr(tree, "getroot") else tree
    d_ns = "http://www.tresos.de/_projects/DataModel2/06/data.xsd"

    for d in diffs:
        if getattr(d, "op", "add") != "add":
            continue
        template = getattr(d, "template", None)
        if template is None:
            continue
        path = getattr(template, "path", None) or getattr(d, "path", None)
        new_raw = getattr(template, "raw", None)
        if not path or new_raw is None:
            continue

        segments = path.strip("/").split("/")
        if len(segments) < 2:
            continue

        var_name = segments[-1]
        container_segments = segments[:-1]

        # 从 root 下钻到 parent container
        parent = root
        for cname in container_segments:
            found = _find_child_container_xdm(parent, cname)
            if found is None:
                parent = None
                break
            parent = found
        if parent is None:
            continue

        # 创建新的 d:var 节点
        var_elem = etree.SubElement(parent, f"{{{d_ns}}}var")
        var_elem.set("name", var_name)
        var_elem.set("value", new_raw)
        var_elem.set("type", "STRING")  # 默认类型


def _apply_delete_xdm(
    loaded: LoadedDocument,
    diffs: tuple[object, ...],
) -> None:
    """XDM 端 delete apply：从 parent container 删除匹配的 d:var 节点。"""
    tree = loaded.tree
    root = tree.getroot() if hasattr(tree, "getroot") else tree

    for d in diffs:
        if getattr(d, "op", "delete") != "delete":
            continue
        current = getattr(d, "current", None)
        if current is None:
            continue
        path = getattr(current, "path", None) or getattr(d, "path", None)
        if not path:
            continue

        segments = path.strip("/").split("/")
        if len(segments) < 2:
            continue

        var_name = segments[-1]
        container_segments = segments[:-1]

        # 从 root 下钻到 parent container
        parent = root
        for cname in container_segments:
            found = _find_child_container_xdm(parent, cname)
            if found is None:
                parent = None
                break
            parent = found
        if parent is None:
            continue

        # 找匹配的 d:var 节点并删除
        var_elem = _find_var_xdm(parent, var_name)
        if var_elem is not None:
            var_elem.getparent().remove(var_elem)


def _find_child_container_xdm(parent: Any, container_name: str) -> Any | None:
    """在 parent 下找 ``name == container_name`` 的 d:ctr / d:lst / d:chc 节点。

    策略: 跳过一个无名 wrapper 层（``d:lst type="ELEMENTS"`` 等），
    递归下钻直到找到 name 匹配的节点或穷尽。

    EB tresos 生成的 XDM 树里，``<d:ctr name="A">`` 下常挂一个无名
    ``<d:lst type="ELEMENTS">`` 或 ``<d:ctr type="MODULE-CONFIGURATION">``，
    再下面才是 name 匹配的子节点。
    """
    d_ns = "http://www.tresos.de/_projects/DataModel2/06/data.xsd"
    for child in parent:
        if not isinstance(child.tag, str):
            continue
        if not child.tag.startswith(f"{{{d_ns}}}"):
            continue
        local = child.tag.split("}", 1)[1]  # "ctr" / "lst" / "chc" / "var" / "ref"
        if local in ("ctr", "lst", "chc") and child.get("name") == container_name:
            return child
        # 无名 wrapper → 递归下钻
        if local in ("ctr", "lst", "chc") and not child.get("name"):
            found = _find_child_container_xdm(child, container_name)
            if found is not None:
                return found
    return None


def _find_var_xdm(parent: Any, var_name: str) -> Any | None:
    """在 parent 下找 ``<d:var name=var_name>``。"""
    d_ns = "http://www.tresos.de/_projects/DataModel2/06/data.xsd"
    for child in parent:
        if not isinstance(child.tag, str):
            continue
        if not child.tag.startswith(f"{{{d_ns}}}"):
            continue
        local = child.tag.split("}", 1)[1]
        if local == "var" and child.get("name") == var_name:
            return child
    return None


__all__ = [
    "ApplyMode",
    "ApplyResult",
    "apply_template_diff",
]
