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
    build_default_nsmap,
    detect_namespaces,
    read,
)
from autoc.core.bsw.bswmd import BSWMDRegistry

ECUCType = Literal["INTEGER", "FLOAT", "STRING", "BOOLEAN", "ENUMERATION"]

# 知名 URI 字典（contract 3 兼容 alias）。Sprint 3 用 r4.0 硬编码，Sprint 8.E
# 改为多版本：默认 ns 通过 detect_namespaces(path) 动态探测，本表只作 fallback
# (D1 决定)。
_WELL_KNOWN: dict[str, tuple[str, ...]] = {
    "ar": (
        "http://autosar.org/schema/r4.0",
        "http://autosar.org/schema/r4.2",
        "http://autosar.org/schema/r4.4",
        "http://autosar.org/schema/r4.6",
        "http://autosar.org/schema/r4.7",
        "http://autosar.org/schema/r4.8",
    ),
    "xsi": ("http://www.w3.org/2001/XMLSchema-instance",),
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


def load_module(
    arxml_path: Path,
    module_name: str,
    *,
    nsmap: dict[str, str] | None = None,
    bswmd_registry: BSWMDRegistry | None = None,
) -> ECUCDocument:
    """从 ARXML/XDM 文件加载指定 module 的 ECUC 配置。

    nsmap=None（默认）：自动调 detect_namespaces(arxml_path) 探测根 xmlns，
    支持任意 r4.x URI（r4.0/4.2/4.4/4.6/4.7/4.8）。
    nsmap=非空：调用方显式提供；用于 CLI 阶段、测试 stage 控制、避免重复探测。

    bswmd_registry=None（默认）：按 DEFINITION-REF DEST 后缀启发式推断类型（Sprint 3 行为）。
    bswmd_registry=非空：先查 BSWMD ``lookup_param(def_ref.text)`` 严格推断；miss 时
    fallback 到 DEST 启发式（T8.E.2 新行为；plan R4.a 锁定）。

    抛:
      - ARXMLError: 文件读不出 / 畸形
      - ValueError: 文件内找不到 SHORT-NAME == module_name 的
                     ECUC-MODULE-CONFIGURATION-VALUES
    """
    if nsmap is None:
        nsmap = detect_namespaces(arxml_path)

    doc = read(arxml_path)
    root = doc.tree.getroot()
    # 即便调用方传了 nsmap，我们仍要校验 root.nsmap 与传入一致；不一致时
    # 用 root.nsmap 重建（避免误把别处 nsmap 强加到当前 doc）。
    actual_nsmap = build_default_nsmap(root)
    if actual_nsmap != nsmap:
        # 调用方显式传错 → 用实际 root nsmap 兜底（更安全）
        nsmap = actual_nsmap

    module_elem = _find_module_root(root, module_name)
    if module_elem is None:
        raise ValueError(
            f"ECUC-MODULE-CONFIGURATION-VALUES with SHORT-NAME={module_name!r} "
            f"not found in {arxml_path}"
        )

    values: list[ECUCValue] = []
    _walk(module_elem, module_name, values, bswmd_registry=bswmd_registry)
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


def set_value(
    doc: ECUCDocument,
    path: str,
    new_raw: str,
    *,
    nsmap: dict[str, str] | None = None,  # noqa: ARG001 — 保留为后续 BSWMD 校验扩展点
) -> ECUCDocument:
    """改一个值的 raw（不可变）。返回新 ECUCDocument；原 doc 不变。

    path 不在 doc.values 里时抛 ValueError。
    nsmap=None（默认）：与 doc 探测时一致；本函数不重探测（set_value 是纯
    immutable 映射操作，不需 nsmap；保留 kw 为后续 Sprint 9.x BSWMD 校验扩展用）。
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
    *,
    bswmd_registry: BSWMDRegistry | None = None,
) -> None:
    """递归下钻 container，把所有 leaf value 收集到 out。

    container_elem 必须是 <ECUC-PARAM-CONF-CONTAINER> 或
    <ECUC-MODULE-CONFIGURATION-VALUES> 节点。
    path 是到达 container_elem 的完整 ECUC 路径。

    bswmd_registry：透传给 _emit_parameter / _emit_reference 推断类型；
        None 时走 DEST 启发式（Sprint 3 行为）。

    AUTOSAR 把同类元素包在 wrapper 元素下（<CONTAINERS>、<SUB-CONTAINERS>、
    <PARAMETER-VALUES>、<REFERENCE-VALUES>），本函数自动 unwrap。
    """
    # 直接子节点里可能直接出现 PARAMETER-VALUE 节点（已 unwrap 的旧 schema）
    # 也可能包在 <PARAMETER-VALUES> wrapper 下（标准 AUTOSAR）
    for child in container_elem:
        tag_local = _local_tag(child)
        if tag_local in _PARAMETER_VALUE_TAGS:
            _emit_parameter(child, path, out, bswmd_registry=bswmd_registry)
        elif tag_local == "ECUC-REFERENCE-VALUE":
            _emit_reference(child, path, out)
        elif tag_local == "PARAMETER-VALUES":
            # wrapper：下钻一层
            for pv in child:
                if _local_tag(pv) in _PARAMETER_VALUE_TAGS:
                    _emit_parameter(pv, path, out, bswmd_registry=bswmd_registry)
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
                    _walk(sub, child_path, out, bswmd_registry=bswmd_registry)
        elif tag_local in _CONTAINER_TAGS:
            # 直接出现 container（无 wrapper）
            sn_elem = child.find("{*}SHORT-NAME")
            if sn_elem is None or sn_elem.text is None:
                continue
            child_path = f"{path}/{sn_elem.text}"
            _walk(child, child_path, out, bswmd_registry=bswmd_registry)


def _emit_parameter(
    pv: Any,
    path: str,
    out: list[ECUCValue],
    *,
    bswmd_registry: BSWMDRegistry | None = None,
) -> None:
    """从 <ECUC-NUMERICAL-PARAM-VALUE> / <ECUC-TEXTUAL-PARAM-VALUE> 提一个 ECUCValue。"""
    def_ref = pv.find("{*}DEFINITION-REF")
    if def_ref is None:
        return
    ecuc_type = _infer_type(def_ref, bswmd_registry=bswmd_registry)
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


def _infer_type(
    def_ref: Any,
    *,
    bswmd_registry: BSWMDRegistry | None = None,
) -> ECUCType:
    """按 DEFINITION-REF DEST 属性（或 BSWMD）推断类型。

    优先查 BSWMD（T8.E.2 新行为）：
        - 若 ``bswmd_registry`` 非 None 且 ``lookup_param(def_ref.text)`` 命中
          → 用 ``ParamDef.param_type`` 严格推断
        - 命中失败 → fallback 到 DEST 启发式（向后兼容）

    DEST 启发式（plan R4.b 锁定）：
      - ECUC-INTEGER-PARAM-DEF      → INTEGER
      - ECUC-FLOAT-PARAM-DEF        → FLOAT
      - ECUC-STRING-PARAM-DEF       → STRING
      - ECUC-BOOLEAN-PARAM-DEF      → BOOLEAN
      - ECUC-ENUMERATION-PARAM-DEF  → ENUMERATION
      - 其他（vendor extension / 未匹配）→ STRING（最安全 fallback）

    参考：plan 中"启发式"是 Sprint 3 简化版，T8.E.2 接受 BSWMD schema 严格推断。
    """
    # BSWMD 优先（契约 2 — Plan T8.E.2）
    if bswmd_registry is not None:
        def_text = (def_ref.text or "").strip()
        if def_text:
            param_def = bswmd_registry.lookup_param(def_text)
            if param_def is not None:
                # 严格类型映射
                mapped = _map_param_type_to_ecuc(param_def.param_type)
                if mapped is not None:
                    return mapped
                # 未识别的 param_type（FUNCTION_NAME 等）→ fallback DEST

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


def _map_param_type_to_ecuc(
    param_type: str,
) -> ECUCType | None:
    """BSWMD ``ParamDef.param_type`` → ECUC 类型。FUNCTION_NAME 等不在 ECUCType 范围时返回 None。"""
    if param_type in ("INTEGER", "FLOAT", "STRING", "BOOLEAN", "ENUMERATION"):
        return cast(ECUCType, param_type)
    return None


def _local_tag(elem: Any) -> str:
    """返回 elem 的 local tag（去命名空间）。"""
    from lxml import etree

    qname = etree.QName(elem.tag)
    return cast(str, qname.localname)
