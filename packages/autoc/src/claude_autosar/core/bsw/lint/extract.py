"""ARXML / XDM → lint-friendly data —— Sprint 9.4 T9.4-α。

设计要点（plan smooth-spinning-dolphin §4.3）：

* 不重写解析逻辑 — **复用** :mod:`claude_autosar.core.bsw.inspector.arxml_report`
  / :mod:`.xdm_report` 里的 ``_extract_*`` 私有函数。复用路线：
    1. 调用 ``render_arxml_report`` / ``render_xdm_report`` 的同样入口
       (``read`` + xpath)；为避免改 inspector 公开 API，加**轻量包装**：
       ``extract_arxml_for_lint`` 直接调 inspector 模块级私有函数
       （``_extract_ipdus`` / ``_extract_signals_by_ipdu`` / ``_extract_key_params``
       / ``_extract_module_names`` 等），由 lint 顶层包 import 解耦。
* 输出 **frozen dataclass** + tuple 容器（rule 直接 ``for ipdu in
  extracted.ipdus: ...``，不可变）
* key_params 的 key 用 ``"<module>/<container>/<param>"`` 形式（拼接后让
  rule 可以做 prefix 判断）
* XDM leaves 的 ``raw`` 保留原值字符串（rule 自己 parse），让 DEM-AP-001
  能直接看 hex 字面量

注：inspector ``_extract_*`` 是**模块级私有**函数（前置下划线），从 lint
直接调用是**有意为之**（plan §11 关键文件路径速查明示），v2 可考虑提取成
公开 API。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from claude_autosar.core.bsw.arxml_io import ARXMLError, build_default_nsmap
from claude_autosar.core.bsw.arxml_io import read as _arxml_read

__all__ = [
    "ArxmlLintData",
    "XdmLintData",
    "extract_arxml_for_lint",
    "extract_xdm_for_lint",
]


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArxmlLintData:
    """ARXML lint 输入（frozen + tuple 容器）。

    :param module_name: 顶层 ECUC-MODULE-CONFIGURATION-VALUES 的 SHORT-NAME
        （多模块 ARXML 取第一个；当前 inspector 也是这个简化策略）
    :param ipdus: IPdu 容器列表（每个 dict 含 ``name`` / ``type`` + 关键
        PARAM-VALUES 字段如 ``ComIPduHandleId`` / ``ComIPduLength`` /
        ``ComIPduDirection``）
    :param signals_by_ipdu: ``{ipdu_name: (signal_record, ...)}``
    :param key_params: 顶层容器（ComGeneral / EcuMConfiguration 等）下的关键参数
        列表；每个 ``dict`` 含 ``container`` / ``name`` / ``value`` 字段。
    :param os_tasks: OsTask 容器列表（每个 dict 含 ``name`` / ``priority`` /
        ``stack_size`` 等字段）。Sprint 12 T12.2 新增。
    :param nvm_blocks: NvMBlockDescriptor 容器列表（每个 dict 含 ``name`` /
        ``block_size`` / ``crc_type`` 等字段）。Sprint 12 T12.2 新增。
    :param fee_blocks: FeeBlockConfiguration 容器列表（每个 dict 含 ``name`` /
        ``block_size`` 等字段）。Sprint 12 T12.2 新增。
    """

    module_name: str
    ipdus: tuple[dict[str, Any], ...]
    signals_by_ipdu: dict[str, tuple[dict[str, Any], ...]]
    key_params: tuple[dict[str, str], ...]
    # Sprint 12 T12.2 新增（向后兼容：默认空元组）
    os_tasks: tuple[dict[str, Any], ...] = ()
    nvm_blocks: tuple[dict[str, Any], ...] = ()
    fee_blocks: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class XdmLintData:
    """XDM lint 输入（frozen + tuple 容器）。

    :param module_name: 顶层 ``<d:chc name=X type=AR-ELEMENT>`` 的 X
    :param containers: 第一层 ``<d:ctr>`` / ``<d:lst>`` 列表
    :param leaves: 所有 ``<d:var>`` 扁平列表（含 path / raw / type）
    """

    module_name: str
    containers: tuple[dict[str, Any], ...]
    leaves: tuple[dict[str, Any], ...]


# ---------------------------------------------------------------------------
# ARXML → ArxmlLintData
# ---------------------------------------------------------------------------


def extract_arxml_for_lint(path: Path) -> ArxmlLintData:
    """读 ``.arxml`` → 抽 IPdu / Signal / key_params → 装入 ArxmlLintData。

    :param path: ARXML 文件路径
    :raises ARXMLError: 文件不存在 / XML 畸形 / 根 namespace 缺失
    :return: frozen ArxmlLintData
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

    # 直接复用已解析的 doc tree 提取 nsmap，避免 detect_namespaces 再次完整解析文件
    root = doc.tree.getroot()
    nsmap = build_default_nsmap(root)
    default_ns = nsmap.get("ar", "")
    if not default_ns:
        raise ARXMLError(
            f"ARXML file {p} has no default namespace; " f"nsmap keys: {sorted(nsmap)}"
        )

    # 延迟 import 避免 lint → inspector → arxml_io 的循环（虽然实际
    # 不会循环，但 inspector 自身用 lxml 较重，按需加载更友好）
    # Sprint 11 T11.4：改用公共 API
    from claude_autosar.core.bsw.inspector.arxml_report import (
        extract_fee_blocks,
        extract_ipdus,
        extract_key_params,
        extract_module_names,
        extract_nvm_blocks,
        extract_os_tasks,
        extract_signals_by_ipdu,
    )
    module_names = extract_module_names(root, default_ns)
    module_name = module_names[0] if module_names else "<unknown-module>"
    ipdus = extract_ipdus(root, default_ns)
    sigs_by_ipdu_raw = extract_signals_by_ipdu(root, default_ns)
    key_params = extract_key_params(root, default_ns)

    # Sprint 12 T12.2：提取 Os/NvM/Fee 数据
    os_tasks = extract_os_tasks(root, default_ns)
    nvm_blocks = extract_nvm_blocks(root, default_ns)
    fee_blocks = extract_fee_blocks(root, default_ns)

    # list → tuple（frozen + hashable）
    sigs_by_ipdu: dict[str, tuple[dict[str, Any], ...]] = {
        k: tuple(v) for k, v in sigs_by_ipdu_raw.items()
    }

    return ArxmlLintData(
        module_name=module_name,
        ipdus=tuple(ipdus),
        signals_by_ipdu=sigs_by_ipdu,
        key_params=tuple(key_params),
        os_tasks=tuple(os_tasks),
        nvm_blocks=tuple(nvm_blocks),
        fee_blocks=tuple(fee_blocks),
    )


# ---------------------------------------------------------------------------
# XDM → XdmLintData
# ---------------------------------------------------------------------------


def extract_xdm_for_lint(path: Path) -> XdmLintData:
    """读 ``.xdm`` → 扁平化 DataModel2 树 → 装入 XdmLintData。

    :param path: XDM 文件路径
    :raises DataModel2Error: 文件不存在 / XML 畸形
    :return: frozen XdmLintData
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
    nsmap = dict(root.nsmap) if getattr(root, "nsmap", None) else {}
    default_ns = nsmap.get(None, "")

    # Sprint 11 T11.4：改用公共 API
    from claude_autosar.core.bsw.inspector.xdm_report import (
        extract_module_name,
        flatten_module_tree,
    )

    module_name = extract_module_name(root, default_ns) or "<unknown-module>"
    containers_raw, leaves_raw = flatten_module_tree(root, module_name, default_ns)

    return XdmLintData(
        module_name=module_name,
        containers=tuple(containers_raw),
        leaves=tuple(leaves_raw),
    )
