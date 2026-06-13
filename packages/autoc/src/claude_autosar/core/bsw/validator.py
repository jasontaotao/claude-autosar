"""BSW 改参闭环：modify + verify + rollback。

Sprint 3 — T3.3。位于 `ecuc.py` 之上、CLI 之下。
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from pathlib import Path
import shutil
import tempfile
from typing import Protocol

from lxml import etree

from claude_autosar.adapters.protocol import EcuConfigProjectContext, SaveResult, VerifyResult
from claude_autosar.core.bsw.arxml_io import read as arxml_read
from claude_autosar.core.bsw.arxml_io import write as arxml_write
from claude_autosar.core.bsw.bsw_write_path import (
    BSWWritePathError,
    validate_writes_against_bswmd,
)
from claude_autosar.core.bsw.bswmd import BSWMDRegistry
from claude_autosar.core.bsw.config import BSWParam
from claude_autosar.core.bsw.ecuc import _find_module_root, _local_tag, load_module
from claude_autosar.core.bsw.ecuc import set_value as ecuc_set_value


class ValidatorError(Exception):
    """validator 改参闭环失败时抛出的统一异常。"""


@dataclass(frozen=True)
class ModifyRequest:
    """单次改参请求：module 名 + 参数列表。"""

    module: str
    params: tuple[BSWParam, ...] = ()


@dataclass(frozen=True)
class ModifyResult:
    """改参结果。

    success: verify 通过且 save 完成
    written_files: adapter.save 返回的实际改动文件路径
    verify_output: adapter.verify 的 stdout+stderr 拼接
    rolled_back: verify 失败时是否回滚成功
    error: 错误信息（成功时为 None）
    """

    success: bool
    written_files: tuple[Path, ...] = ()
    verify_output: str = ""
    rolled_back: bool = False
    error: str | None = None


# Adapter 用 Protocol 描述（structural subtyping），避免 import cycle。
class _VerifySaveAdapter(Protocol):
    def verify(self, ctx: EcuConfigProjectContext, module: str | None) -> VerifyResult: ...
    def save(self, ctx: EcuConfigProjectContext, module: str | None) -> SaveResult: ...


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def modify_and_verify(
    ctx: EcuConfigProjectContext,
    adapter: _VerifySaveAdapter,
    req: ModifyRequest,
    *,
    bswmd_registry: BSWMDRegistry | None = None,
) -> ModifyResult:
    """改 + verify + 失败回滚 + 成功 save 的闭环。

    流程:
      1. 定位 <req.module> 的 .xdm / .arxml（启发式）
      2. 快照到系统临时目录
      3. 改值 + 写回
      4. verify → 失败：还原 + 返回 rolled_back
      5. verify → 成功：save → 把 written_files 填到结果
      6. 任何步骤抛异常：best-effort 还原 + 抛 ValidatorError

    T8.E.3：在 snapshot 之前先按 BSWMD 校验（multiplicity / type / range / enum）；
    校验失败时走 ``ModifyResult(error=...)`` 返回，不抛 ``ValidatorError``，不调 verify / save。
    9 个老 test 不破：``bswmd_registry=None`` 时跳过校验。
    """
    if not req.params:
        return ModifyResult(success=True, written_files=())

    # T8.E.3：BSWMD 校验在 snapshot 之前；不抛 ValidatorError
    if bswmd_registry is not None:
        try:
            # current_values 此时还未加载；走"以 BSWMD 已知的写集为准"路径
            # （容器 multiplicity 只看 writes 数；type/range 只看 writes 内容）
            validate_writes_against_bswmd(bswmd_registry, req.module, (), req.params)
        except BSWWritePathError as exc:
            return ModifyResult(
                success=False,
                rolled_back=False,
                error=f"BSWMD validation failed: {exc}",
            )

    target_file = _locate_module_file(ctx.project_path, req.module)
    if target_file is None:
        raise ValidatorError(
            f"Module {req.module!r} file (.xdm or .arxml) not found in {ctx.project_path}"
        )

    snapshot_dir = Path(tempfile.mkdtemp(prefix="autoc-snapshot-"))
    snapshot_file = snapshot_dir / target_file.name
    try:
        shutil.copy2(target_file, snapshot_file)

        # 解析 ECUC 文档以验证 path 存在 / ECUC 模块名匹配
        try:
            doc = load_module(target_file, req.module)
        except Exception as e:
            _restore_from_snapshot(snapshot_file, target_file)
            raise ValidatorError(f"Failed to load ECUC module {req.module!r}: {e}") from e

        # 改值（不可变）—— 提前校验所有 path 都存在
        for param in req.params:
            try:
                doc = ecuc_set_value(doc, param.path, param.value.raw)
            except ValueError as e:
                _restore_from_snapshot(snapshot_file, target_file)
                raise ValidatorError(f"Failed to set value for path {param.path!r}: {e}") from e

        # 把 ECUC doc 的改动反映回 lxml 树
        try:
            arxml_doc = arxml_read(target_file)
            for param in req.params:
                _update_tree_value(arxml_doc.tree, req.module, param)
            # T8.E.5: 走 preserve_format=True 保留 PIs / DOCTYPE / 注释 / 属性顺序 / namespace prefix
            arxml_write(arxml_doc.tree, target_file, atomic=True, preserve_format=True)
        except Exception as e:
            _restore_from_snapshot(snapshot_file, target_file)
            raise ValidatorError(f"Failed to write modified ARXML to {target_file}: {e}") from e

        # verify
        verify_result = adapter.verify(ctx, req.module)
        verify_output = (verify_result.stdout or "") + (verify_result.stderr or "")
        if not verify_result.success:
            _restore_from_snapshot(snapshot_file, target_file)
            return ModifyResult(
                success=False,
                rolled_back=True,
                verify_output=verify_output,
                error=f"verify failed (returncode={verify_result.returncode})",
            )

        # save
        save_result = adapter.save(ctx, req.module)
        return ModifyResult(
            success=save_result.success,
            written_files=save_result.written_files,
            verify_output=verify_output,
            error=(
                None
                if save_result.success
                else f"save failed (returncode={save_result.returncode})"
            ),
        )
    finally:
        # 清理 snapshot（失败 swallowed：snapshot 在系统 temp，最坏被 OS 回收）
        with contextlib.suppress(OSError):
            shutil.rmtree(snapshot_dir)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _locate_module_file(project_path: Path, module: str) -> Path | None:
    """启发式定位 module 的配置 .xdm / .arxml 文件。"""
    for ext in (".xdm", ".arxml"):
        candidate = project_path / f"{module}{ext}"
        if candidate.is_file():
            return candidate
    return None


def _restore_from_snapshot(snapshot_file: Path, target_file: Path) -> None:
    """Best-effort 还原。失败 swallowed。"""
    with contextlib.suppress(OSError):
        shutil.copy2(snapshot_file, target_file)


def _update_tree_value(
    tree: etree._ElementTree,
    module_name: str,
    param: BSWParam,
    *,
    nsmap: dict[str, str] | None = None,
) -> None:
    """在 lxml 树中按 path 找 ECUC 节点并改 VALUE 文本。

    path 格式: "ModuleName/[Container/]*ShortName"
    nsmap=None（默认）：自动从 root 重建（Sprint 8.E T8.E.1 contract 3）。
    nsmap=非空：调用方显式提供，避免重复 build_default_nsmap。
    """
    segments = param.path.split("/")
    assert segments[0] == module_name, f"path {param.path!r} 不属于模块 {module_name!r}"

    root = tree.getroot()
    # nsmap 重建（如果调用方没传）：用 root.nsmap 构造。
    # 当前 _find_module_root / _find_leaf_value_elem 都用 {*} wildcard，nsmap
    # 仅作将来 xpath 替换的扩展点；为契约 3 保持签名一致仍消费之。
    if nsmap is None:
        from claude_autosar.core.bsw.arxml_io import build_default_nsmap

        nsmap = build_default_nsmap(root)

    module_elem = _find_module_root(root, module_name)
    if module_elem is None:
        raise ValueError(f"Module root {module_name!r} not found in tree")

    # 从 module_elem 开始下钻
    leaf_value_elem = _find_leaf_value_elem(module_elem, segments[1:])
    if leaf_value_elem is None:
        raise ValueError(
            f"Path {param.path!r} not found in tree (load_module 接受了但 DOM 缺节点？)"
        )
    leaf_value_elem.text = param.value.raw


def _find_leaf_value_elem(
    container_elem: etree._Element,
    segments: list[str],
) -> etree._Element | None:
    """递归按 segments 找 ECUC-PARAMETER-VALUE 的 <VALUE> 元素。"""
    if len(segments) == 1:
        # 最后一段：找 ECUC-PARAMETER-VALUE
        target_short = segments[0]
        for child in container_elem:
            tag = _local_tag(child)
            if tag == "PARAMETER-VALUES":
                for pv in child:
                    ptag = _local_tag(pv)
                    if ptag in (
                        "ECUC-NUMERICAL-PARAM-VALUE",
                        "ECUC-TEXTUAL-PARAM-VALUE",
                        "ECUC-ADDITIONAL-PARAM-VALUE",
                    ):
                        def_ref = pv.find("{*}DEFINITION-REF")
                        if def_ref is None:
                            continue
                        ref_text = def_ref.text or ""
                        ref_short = ref_text.strip("/").split("/")[-1]
                        if ref_short == target_short:
                            return pv.find("{*}VALUE")
        return None

    # 递归：先找对应 SHORT-NAME 的 container
    target_short = segments[0]
    rest = segments[1:]
    for child in container_elem:
        tag = _local_tag(child)
        if tag in ("CONTAINERS", "SUB-CONTAINERS"):
            for sub in child:
                if _local_tag(sub) in (
                    "ECUC-PARAM-CONF-CONTAINER",
                    "ECUC-POST-BUILD-VARIANT-CONF-CONTAINER",
                ):
                    sn = sub.find("{*}SHORT-NAME")
                    if sn is not None and sn.text == target_short:
                        result = _find_leaf_value_elem(sub, rest)
                        if result is not None:
                            return result
        elif tag in (
            "ECUC-PARAM-CONF-CONTAINER",
            "ECUC-POST-BUILD-VARIANT-CONF-CONTAINER",
        ):
            sn = child.find("{*}SHORT-NAME")
            if sn is not None and sn.text == target_short:
                result = _find_leaf_value_elem(child, rest)
                if result is not None:
                    return result
    return None
