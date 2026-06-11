"""AUTOSAR ECUC ARXML 解析（lxml-only，**不**依赖 pyecarxml）。

Sprint 3 — T3.2。
高层的 ECUC 语义解析：reference chain / type inference / 不可变 set_value。
低层 XML 读写在 `arxml_io.py`。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from autoc.core.bsw.arxml_io import (
    read,
)

ECUCType = Literal["INTEGER", "FLOAT", "STRING", "BOOLEAN", "ENUMERATION"]

# AUTOSAR 经典平台默认命名空间
_NAMESPACES: dict[str, str] = {
    "ar": "http://autosar.org/schema/r4.0",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}

# ECUC 元素类型短名（在大写 tag 中）。Sprint 3 用启发式；
# 真实项目可能需要 BSWMD schema 配合才能严格推断。
_CONTAINER_TAGS: frozenset[str] = frozenset(
    {"ECUC-PARAM-CONF-CONTAINER", "ECUC-POST-BUILD-VARIANT-CONF-CONTAINER"}
)
_PARAMETER_VALUE_TAGS: frozenset[str] = frozenset(
    {
        "ECUC-NUMERICAL-PARAM-VALUE",
        "ECUC-TEXTUAL-PARAM-VALUE",
        "ECUC-ADDITIONAL-PARAM-VALUE",
    }
)


@dataclass(frozen=True)
class ECUCValue:
    """ECUC 树中的一个叶子值。

    path: 用 `/` 分段，从模块 SHORT-NAME 起到叶子。
          例: "Mcu/McuClockSettingConfig_0/McuClockFrequency"
    raw:  字面值（始终是字符串；类型语义在 type 字段）
    type: 5 种之一，按 DEFINITION-REF 路径启发式推断
    """

    path: str
    raw: str
    type: ECUCType


@dataclass(frozen=True)
class ECUCDocument:
    """不可变 ECUC 文档：path + module_name + values。"""

    path: Path
    module_name: str
    values: tuple[ECUCValue, ...]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_module(arxml_path: Path, module_name: str) -> ECUCDocument:
    """从 ARXML/XDM 文件加载指定 module 的 ECUC 配置。

    抛:
      - ARXMLError: 文件读不出 / 畸形
      - ValueError: 文件内找不到 SHORT-NAME == module_name 的
                     ECUC-MODULE-CONFIGURATION-VALUES
    """
    doc = read(arxml_path)
    root = doc.tree.getroot()
    module_elem = _find_module_root(root, module_name)
    if module_elem is None:
        raise ValueError(
            f"ECUC-MODULE-CONFIGURATION-VALUES with SHORT-NAME={module_name!r} "
            f"not found in {arxml_path}"
        )

    values: list[ECUCValue] = []
    _walk(module_elem, module_name, values)
    return ECUCDocument(
        path=arxml_path,
        module_name=module_name,
        values=tuple(values),
    )


def get_value(doc: ECUCDocument, path: str) -> ECUCValue | None:
    """按 path 查一个值；不存在返回 None。"""
    for v in doc.values:
        if v.path == path:
            return v
    return None


def set_value(doc: ECUCDocument, path: str, new_raw: str) -> ECUCDocument:
    """改一个值的 raw（不可变）。返回新 ECUCDocument；原 doc 不变。

    path 不在 doc.values 里时抛 ValueError。
    """
    new_values: list[ECUCValue] = []
    found = False
    for v in doc.values:
        if v.path == path:
            new_values.append(ECUCValue(path=v.path, raw=new_raw, type=v.type))
            found = True
        else:
            new_values.append(v)
    if not found:
        raise ValueError(f"Path {path!r} not in ECUCDocument for module {doc.module_name!r}")
    return ECUCDocument(
        path=doc.path,
        module_name=doc.module_name,
        values=tuple(new_values),
    )


def list_paths(doc: ECUCDocument) -> tuple[str, ...]:
    """返回所有值的 path 排序后元组。"""
    return tuple(sorted(v.path for v in doc.values))


# ---------------------------------------------------------------------------
# 内部：reference chain 解析
# ---------------------------------------------------------------------------


def _find_module_root(root: Any, module_name: str) -> Any | None:
    """在 ARXML root 下找 SHORT-NAME == module_name 的 ECUC-MODULE-CONFIGURATION-VALUES。"""

    # ECUC-MODULE-CONFIGURATION-VALUES 可能在任意命名空间下
    for elem in root.iter("{*}ECUC-MODULE-CONFIGURATION-VALUES"):
        sn = elem.find("{*}SHORT-NAME")
        if sn is not None and sn.text == module_name:
            return elem
    return None


def _walk(
    container_elem: Any,
    path: str,
    out: list[ECUCValue],
) -> None:
    """递归下钻 container，把所有 leaf value 收集到 out。

    container_elem 必须是 <ECUC-PARAM-CONF-CONTAINER> 或
    <ECUC-MODULE-CONFIGURATION-VALUES> 节点。
    path 是到达 container_elem 的完整 ECUC 路径。

    AUTOSAR 把同类元素包在 wrapper 元素下（<CONTAINERS>、<SUB-CONTAINERS>、
    <PARAMETER-VALUES>、<REFERENCE-VALUES>），本函数自动 unwrap。
    """
    # 直接子节点里可能直接出现 PARAMETER-VALUE 节点（已 unwrap 的旧 schema）
    # 也可能包在 <PARAMETER-VALUES> wrapper 下（标准 AUTOSAR）
    for child in container_elem:
        tag_local = _local_tag(child)
        if tag_local in _PARAMETER_VALUE_TAGS:
            _emit_parameter(child, path, out)
        elif tag_local == "ECUC-REFERENCE-VALUE":
            _emit_reference(child, path, out)
        elif tag_local == "PARAMETER-VALUES":
            # wrapper：下钻一层
            for pv in child:
                if _local_tag(pv) in _PARAMETER_VALUE_TAGS:
                    _emit_parameter(pv, path, out)
        elif tag_local == "REFERENCE-VALUES":
            for rv in child:
                if _local_tag(rv) == "ECUC-REFERENCE-VALUE":
                    _emit_reference(rv, path, out)
        elif tag_local in ("CONTAINERS", "SUB-CONTAINERS"):
            # wrapper：下钻一层找 ECUC-PARAM-CONF-CONTAINER
            for sub in child:
                if _local_tag(sub) in _CONTAINER_TAGS:
                    sn_elem = sub.find("{*}SHORT-NAME")
                    if sn_elem is None or sn_elem.text is None:
                        continue
                    child_path = f"{path}/{sn_elem.text}"
                    _walk(sub, child_path, out)
        elif tag_local in _CONTAINER_TAGS:
            # 直接出现 container（无 wrapper）
            sn_elem = child.find("{*}SHORT-NAME")
            if sn_elem is None or sn_elem.text is None:
                continue
            child_path = f"{path}/{sn_elem.text}"
            _walk(child, child_path, out)


def _emit_parameter(pv: Any, path: str, out: list[ECUCValue]) -> None:
    """从 <ECUC-NUMERICAL-PARAM-VALUE> / <ECUC-TEXTUAL-PARAM-VALUE> 提一个 ECUCValue。"""
    def_ref = pv.find("{*}DEFINITION-REF")
    if def_ref is None:
        return
    ecuc_type = _infer_type(def_ref)
    short_name = _definition_ref_short_name(def_ref)
    if short_name is None:
        return
    value_text = _get_value_text(pv)
    if value_text is None:
        return
    out.append(ECUCValue(path=f"{path}/{short_name}", raw=value_text, type=ecuc_type))


def _emit_reference(rv: Any, path: str, out: list[ECUCValue]) -> None:
    """从 <ECUC-REFERENCE-VALUE> 提一个 ECUCValue（type 固定 STRING）。

    raw 取 <VALUE-REF> 的文本（ECUC 路径）。DEST 是引用目标类型提示（如
    ECUC-PARAM-CONF-CONTAINER），不是路径一部分，忽略。
    """
    def_ref = rv.find("{*}DEFINITION-REF")
    if def_ref is None:
        return
    short_name = _definition_ref_short_name(def_ref)
    if short_name is None:
        return
    value_ref = rv.find("{*}VALUE-REF")
    target_path = value_ref.text if value_ref is not None else None
    out.append(ECUCValue(path=f"{path}/{short_name}", raw=target_path or "", type="STRING"))


def _get_value_text(pv: Any) -> str | None:
    """从 <ECUC-NUMERICAL-PARAM-VALUE>/<ECUC-TEXTUAL-PARAM-VALUE> 取 <VALUE> 文本。"""
    val_elem = pv.find("{*}VALUE")
    if val_elem is None:
        return None
    return cast(str | None, val_elem.text)


def _definition_ref_short_name(def_ref: Any) -> str | None:
    """从 <DEFINITION-REF>/Mcu/McuClockFrequency 提 'McuClockFrequency'。"""
    text = def_ref.text
    if not text:
        return None
    parts = text.strip("/").split("/")
    return cast(str, parts[-1]) if parts else None


def _infer_type(def_ref: Any) -> ECUCType:
    """按 DEFINITION-REF DEST 属性启发式推断类型。

    AUTOSAR 标准的 DEST 取值：
      - ECUC-INTEGER-PARAM-DEF      → INTEGER
      - ECUC-FLOAT-PARAM-DEF        → FLOAT
      - ECUC-STRING-PARAM-DEF       → STRING
      - ECUC-BOOLEAN-PARAM-DEF      → BOOLEAN
      - ECUC-ENUMERATION-PARAM-DEF  → ENUMERATION
      - 其他（vendor extension / 未匹配）→ STRING（最安全 fallback）

    参考：plan 中"启发式"是 Sprint 3 简化版，v2 接受 BSWMD schema 严格推断。
    """
    dest = (def_ref.get("DEST") or "").upper()
    for needle, mapped in (
        ("ECUC-INTEGER-PARAM-DEF", "INTEGER"),
        ("ECUC-FLOAT-PARAM-DEF", "FLOAT"),
        ("ECUC-STRING-PARAM-DEF", "STRING"),
        ("ECUC-BOOLEAN-PARAM-DEF", "BOOLEAN"),
        ("ECUC-ENUMERATION-PARAM-DEF", "ENUMERATION"),
    ):
        if needle in dest:
            return mapped  # type: ignore[return-value]
    return "STRING"


def _local_tag(elem: Any) -> str:
    """返回 elem 的 local tag（去命名空间）。"""
    from lxml import etree

    qname = etree.QName(elem.tag)
    return cast(str, qname.localname)
