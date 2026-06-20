"""BSW read tool + XDM walker — moved from mcp_server.py."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _error(
    msg: str,
    *,
    error_code: str = "",
    field: str = "",
    param_index: int = -1,
    suggestion: str = "",
) -> dict[str, Any]:
    """构造结构化错误返回（Sprint 11 T11.2）。"""
    d: dict[str, Any] = {"success": False, "error": msg}
    if error_code:
        d["error_code"] = error_code
    if field:
        d["field"] = field
    if param_index >= 0:
        d["param_index"] = param_index
    if suggestion:
        d["suggestion"] = suggestion
    return d


def _infer_value(raw: str) -> int | float | bool | str:
    """Infer typed value from raw string. Attempts bool -> int -> float -> str."""
    lower = raw.lower()
    if lower in ("true", "false"):
        return lower == "true"
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def _is_descendant_of(candidate: Any, ancestor: Any) -> bool:
    """判断 candidate 是否是 ancestor 的后代（lxml iterancestors 路径检查）。"""
    try:
        return any(anc is ancestor for anc in candidate.iterancestors())
    except (AttributeError, TypeError):
        return False


def _bsw_read_xdm(path: Path, module: str, full_path: str) -> dict[str, Any]:
    """从 DataModel2 .xdm 读 module/container/.../param 路径下的值。

    DataModel2 树结构跟 ECUC 完全不一样（扁平 d:var）— 不能走 ecuc.load_module。
    本函数直接用 lxml xpath 在 d:chc name=module 容器下定位。

    .. note:: M12 修复：module 和 seg 在拼接 XPath 前均须通过白名单校验。
    """
    from claude_autosar.cli.mcp_tools.validation import validate_module_name
    from claude_autosar.core.bsw.io.datamodel2_io import DataModel2Error
    from claude_autosar.core.bsw.io.datamodel2_io import read as _xdm_read

    # M12: 校验 module 名白名单（阻断 XPath 注入）
    try:
        validate_module_name(module)
    except ValueError as e:
        return {"success": False, "error": str(e)}

    try:
        tree = _xdm_read(path)
    except (DataModel2Error, OSError) as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    root = tree.getroot() if hasattr(tree, "getroot") else tree
    nsmap = dict(root.nsmap) if getattr(root, "nsmap", None) else {}
    default_ns = nsmap.get(None, "")

    d_ns = "http://www.tresos.de/_projects/DataModel2/06/data.xsd"
    module_xpath = f'.//d:chc[@name="{module}"]'
    module_elems = root.xpath(
        module_xpath, namespaces={"d": d_ns, "dm": default_ns} if default_ns else {"d": d_ns}
    )
    if not module_elems:
        return {
            "success": False,
            "error": f"module {module!r} not found in {path} (no <d:chc name={module!r}>)",
        }
    module_elem = module_elems[0]

    segments = full_path.split("/")
    if segments[0] == module:
        segments = segments[1:]
    current = module_elem
    for i, seg in enumerate(segments):
        # M12: 校验每个 segment 白名单（阻断 XPath 注入）
        try:
            validate_module_name(seg)
        except ValueError:
            return {
                "success": False,
                "error": f"Invalid path segment {seg!r} in {full_path!r}",
            }
        next_el = current.xpath(
            f'.//d:ctr[@name="{seg}"] | .//d:lst[@name="{seg}"] '
            f'| .//d:chc[@name="{seg}"] | .//d:var[@name="{seg}"]',
            namespaces={"d": d_ns},
        )
        if not next_el:
            return {
                "success": False,
                "error": (
                    f"path {full_path!r} not in module {module!r} "
                    f"(segment {i + 1} {seg!r} not found)"
                ),
            }
        candidate = next_el[0]
        if not _is_descendant_of(candidate, current):
            return {
                "success": False,
                "error": (
                    f"path {full_path!r} not in module {module!r} "
                    f"(segment {i + 1} {seg!r} not in subtree)"
                ),
            }
        current = candidate

    value_attr = current.get("value")
    type_attr = current.get("type")
    if value_attr is None:
        return {
            "success": False,
            "error": f"path {full_path!r} resolves to a container, not a leaf value",
        }
    inferred_type = type_attr or "STRING"
    value_typed = _infer_value(value_attr) if isinstance(value_attr, str) else value_attr
    return {
        "success": True,
        "module": module,
        "path": full_path,
        "raw": value_attr,
        "value": value_typed,
        "type": str(inferred_type).upper(),
    }


def bsw_read(module: str, path: str, *, project: str = ".") -> dict[str, Any]:
    """读 XDM/ARXML 中 module 模块下 path 路径的参数值。

    Sprint 9.0 T9.0.3 改：用 dispatcher 按文件根 namespace 自动选 arxml_io 或
    datamodel2_io。XDM 路径用 d:var 扁平提取。

    :param module: BSW 模块名（如 Mcu）
    :param path: ECUC 路径（如 Clock/ClockFreq），会自动拼上 module/ 前缀
    :param project: 工程根目录路径字符串，默认 cwd
    :return: {"success": True, "module", "path", "raw", "type", "value", "format"} 或 error dict
    """
    from claude_autosar.cli.mcp_server import _resolve_safe_project
    from claude_autosar.cli.mcp_tools.validation import validate_module_name
    from claude_autosar.core.bsw.dispatcher import (
        DispatcherError,
        UnknownFormatError,
        detect_format,
    )
    from claude_autosar.core.bsw.ecuc import get_value, load_module

    # M12: 校验 module 白名单（阻断路径注入 / XPath 注入）
    try:
        validate_module_name(module)
    except ValueError as e:
        return _error(str(e), error_code="INVALID_MODULE_NAME", field="module")

    try:
        project_path = _resolve_safe_project(project)
    except PermissionError as e:
        return _error(
            f"{type(e).__name__}: {e}",
            error_code="PERMISSION_DENIED",
            field="project",
        )
    for ext in (".xdm", ".arxml"):
        f = project_path / f"{module}{ext}"
        if f.is_file():
            break
    else:
        return _error(
            f"module {module!r} not found in {project_path} (no .xdm or .arxml)",
            error_code="MODULE_NOT_FOUND",
            suggestion=f"check module name and ensure {module}.xdm or {module}.arxml exists",
        )
    try:
        fmt = detect_format(f)
    except UnknownFormatError as e:
        return {"success": False, "error": str(e)}
    except DispatcherError as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}
    except (OSError, FileNotFoundError) as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    full_path = path if path.startswith(f"{module}/") else f"{module}/{path}"

    if fmt == "arxml":
        try:
            doc = load_module(f, module)
        except (ValueError, FileNotFoundError) as e:
            return {"success": False, "error": f"{type(e).__name__}: {e}"}
        val = get_value(doc, full_path)
        if val is None:
            # 尝试 typo suggestion
            available = [v.path for v in doc.values if v.path.split("/")[-1].lower() == full_path.split("/")[-1].lower()]
            suggestion = ""
            if available:
                suggestion = f"did you mean {available[0]!r}?"
            return _error(
                f"path {full_path!r} not in module {module!r}",
                error_code="PATH_NOT_FOUND",
                suggestion=suggestion,
            )
        value_typed = _infer_value(val.raw) if isinstance(val.raw, str) else val.raw
        return {
            "success": True,
            "module": module,
            "path": val.path,
            "raw": val.raw,
            "value": value_typed,
            "type": str(val.type),
            "format": "arxml",
        }
    # fmt == "xdm"
    result = _bsw_read_xdm(f, module, full_path)
    if result.get("success"):
        result["format"] = "xdm"
    return result
