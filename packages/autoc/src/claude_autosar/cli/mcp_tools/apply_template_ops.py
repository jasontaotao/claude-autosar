"""Apply-template tools + module name detection — moved from mcp_server.py.

Sprint 9.2 T9.2-gamma 双格式 apply-template tool.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast


def _detect_arxml_module_name(path: Path) -> str | None:
    """从 .arxml 文件取顶层 ECUC-MODULE-CONFIGURATION-VALUES 的 SHORT-NAME。

    任意失败一律返回 None；caller 决定 fallback。
    """
    try:
        from claude_autosar.core.bsw.arxml_io import detect_namespaces
        from claude_autosar.core.bsw.xml_safe import _safe_parse

        nsmap = detect_namespaces(path)
        ar_uri = nsmap.get("ar")
        if not ar_uri:
            return None
        tree = _safe_parse(path)
        root = tree.getroot()
        modules = root.xpath(
            "//ar:ECUC-MODULE-CONFIGURATION-VALUES",
            namespaces={"ar": ar_uri},
        )
    except Exception:  # noqa: BLE001
        return None
    if not modules:
        return None
    for m in modules:
        sn = m.find(f"{{{ar_uri}}}SHORT-NAME")
        if sn is not None and sn.text:
            return cast("str | None", sn.text)
    return None


def _detect_xdm_module_name(loaded_doc: Any) -> str | None:
    """从 dispatcher 加载的 XDM tree 找第一个 d:chc type=AR-ELEMENT name。"""
    try:
        tree = loaded_doc.tree
        root = tree.getroot() if hasattr(tree, "getroot") else tree
        ns = {"d": "http://www.tresos.de/_projects/DataModel2/06/data.xsd"}
        elems = root.xpath('.//d:chc[@type="AR-ELEMENT"]', namespaces=ns)
    except Exception:  # noqa: BLE001
        return None
    if not elems:
        return None
    name = elems[0].get("name")
    return name or None


def _apply_result_to_dict(result: Any) -> dict[str, Any]:
    """把 ApplyResult 缩成 dict（不假设字段顺序，避免 dataclass 耦合）。"""
    try:
        from dataclasses import asdict, is_dataclass

        if is_dataclass(result) and not isinstance(result, type):
            return asdict(cast(Any, result))
    except Exception:  # noqa: BLE001
        pass
    try:
        return dict(vars(result))
    except TypeError:
        return {}


def arxml_apply_template(
    path: str,
    template: str,
    *,
    apply: bool = False,
    output: str | None = None,
    project: str = ".",
) -> dict[str, Any]:
    """读 .arxml current + template -> diff -> dry-run / apply 写回。

    :param path: .arxml 当前文件路径（相对 project 根或绝对）
    :param template: .arxml 模板文件路径
    :param apply: True 真正写回；False 只算 diff（dry-run）
    :param output: 输出 HTML 报告路径（可选）
    :param project: 工程根目录（默认 cwd）
    """
    from claude_autosar.cli.mcp_server import _inspect_resolve_input
    from claude_autosar.core.bsw.arxml_io import ARXMLError
    from claude_autosar.core.bsw.dispatcher import (
        DispatcherError,
        FormatMismatchError,
        UnknownFormatError,
    )
    from claude_autosar.core.bsw.dispatcher import read as dispatcher_read
    from claude_autosar.core.bsw.ecuc import load_module as ecuc_load_module
    from claude_autosar.core.bsw.templates.apply import (
        ApplyMode,
        apply_template_diff,
    )
    from claude_autosar.core.bsw.templates.arxml_diff import diff_arxml_templates

    try:
        src = _inspect_resolve_input(path, project=project)
    except PermissionError as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}
    except FileNotFoundError as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    # M9: 校验 template 路径遍历
    if ".." in template:
        return {"success": False, "error": f"Path traversal not allowed: {template!r}"}

    tpl = Path(template).resolve()
    if not tpl.is_file():
        return {"success": False, "error": f"FileNotFoundError: {tpl}"}

    try:
        dispatcher_read(src, expected_format="arxml")
        dispatcher_read(tpl, expected_format="arxml")
    except (FileNotFoundError, OSError) as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}
    except (ARXMLError, DispatcherError, UnknownFormatError, FormatMismatchError) as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    module_name = _detect_arxml_module_name(src)
    if module_name is None:
        module_name = _detect_arxml_module_name(tpl)
    if module_name is None:
        return {
            "success": False,
            "error": ("ValueError: no ECUC-MODULE-CONFIGURATION-VALUES in current/template"),
        }

    try:
        current_doc = ecuc_load_module(src, module_name)
        template_doc = ecuc_load_module(tpl, module_name)
    except (ARXMLError, ValueError) as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    try:
        diff_result = diff_arxml_templates(current_doc, template_doc)
    except (ValueError, TypeError, AttributeError) as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    mode = ApplyMode.APPLY if apply else ApplyMode.DRY_RUN
    try:
        apply_result = apply_template_diff(src, diff_result, mode=mode)
    except (OSError, FileNotFoundError) as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}
    except (ValueError, TypeError, NotImplementedError) as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    return {
        "success": True,
        "format": "arxml",
        "mode": str(mode),
        "path": str(src),
        "template": str(tpl),
        "module_name": module_name,
        "diff_count": len(diff_result.diffs),
        "adds": len(diff_result.adds),
        "modifies": len(diff_result.modifies),
        "deletes": len(diff_result.deletes),
        "applied": bool(apply),
        "report_path": str(Path(output)) if output else None,
        "result": _apply_result_to_dict(apply_result),
    }


def xdm_apply_template(
    path: str,
    template: str,
    *,
    apply: bool = False,
    output: str | None = None,
    project: str = ".",
) -> dict[str, Any]:
    """读 .xdm current + template -> diff -> dry-run / apply 写回。

    :param path: .xdm 当前文件路径（相对 project 根或绝对）
    :param template: .xdm 模板文件路径
    :param apply: True 真正写回；False 只算 diff（dry-run）
    :param output: 输出 HTML 报告路径（可选）
    :param project: 工程根目录（默认 cwd）
    """
    from claude_autosar.cli.mcp_server import _inspect_resolve_input
    from claude_autosar.core.bsw.dispatcher import (
        DispatcherError,
        FormatMismatchError,
        UnknownFormatError,
    )
    from claude_autosar.core.bsw.dispatcher import read as dispatcher_read
    from claude_autosar.core.bsw.io.datamodel2_io import DataModel2Error
    from claude_autosar.core.bsw.templates.apply import (
        ApplyMode,
        apply_template_diff,
    )
    from claude_autosar.core.bsw.templates.xdm_diff import diff_xdm_templates
    from claude_autosar.core.bsw.templates.xdm_value import (
        XDMValueError,
        load_xdm_module,
    )

    try:
        src = _inspect_resolve_input(path, project=project)
    except PermissionError as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}
    except FileNotFoundError as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    # M9: 校验 template 路径遍历
    if ".." in template:
        return {"success": False, "error": f"Path traversal not allowed: {template!r}"}

    tpl = Path(template).resolve()
    if not tpl.is_file():
        return {"success": False, "error": f"FileNotFoundError: {tpl}"}

    try:
        current_doc = dispatcher_read(src, expected_format="xdm")
        template_doc = dispatcher_read(tpl, expected_format="xdm")
    except (FileNotFoundError, OSError) as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}
    except (DataModel2Error, DispatcherError, UnknownFormatError, FormatMismatchError) as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    module_name = _detect_xdm_module_name(current_doc)
    if module_name is None:
        module_name = _detect_xdm_module_name(template_doc)
    if module_name is None:
        return {
            "success": False,
            "error": ("XDMValueError: no <d:chc type=AR-ELEMENT> in current/template"),
        }

    try:
        current_mod = load_xdm_module(src, module_name)
        template_mod = load_xdm_module(tpl, module_name)
    except XDMValueError as e:
        return {"success": False, "error": f"XDMValueError: {e}"}

    try:
        diff_result = diff_xdm_templates(current_mod, template_mod)
    except (ValueError, TypeError, AttributeError) as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    mode = ApplyMode.APPLY if apply else ApplyMode.DRY_RUN
    try:
        apply_result = apply_template_diff(src, diff_result, mode=mode)
    except (OSError, FileNotFoundError) as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}
    except (ValueError, TypeError) as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    return {
        "success": True,
        "format": "xdm",
        "mode": str(mode),
        "path": str(src),
        "template": str(tpl),
        "module_name": module_name,
        "diff_count": len(diff_result.diffs),
        "adds": len(diff_result.adds),
        "modifies": len(diff_result.modifies),
        "deletes": len(diff_result.deletes),
        "applied": bool(apply),
        "report_path": str(Path(output)) if output else None,
        "result": _apply_result_to_dict(apply_result),
    }
