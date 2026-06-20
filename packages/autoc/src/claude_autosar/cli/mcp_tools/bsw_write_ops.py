"""BSW write / verify / autocalc tools — moved from mcp_server.py."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def bsw_write(
    module: str,
    params: list[dict[str, Any]],
    *,
    project: str = ".",
    tresos_home: str | None = None,
) -> dict[str, Any]:
    """写一组 BSW 参数 + verify + 失败回滚（与 eb save 语义一致）。

    :param module: BSW 模块名
    :param params: list of {"path": "Mcu/Clock/ClockFreq", "value": 80000000, "type": "INTEGER"}
    :param project: 工程根目录
    :param tresos_home: EB tresos 安装目录（默认 project/tresos_home）
    """
    from claude_autosar.cli.mcp_server import (
        _build_ctx,
        _default_tresos_home,
        _resolve_safe_project,
    )
    from claude_autosar.cli.mcp_tools.validation import validate_module_name, validate_no_traversal
    from claude_autosar.adapters.tresos import TresosAdapter
    from claude_autosar.core.bsw.config import BSWParam, ParamType, ParamValue
    from claude_autosar.core.bsw.validator import ModifyRequest, modify_and_verify

    # M12: 校验 module 白名单
    try:
        validate_module_name(module)
    except ValueError as e:
        return {"success": False, "error": str(e), "field": "module", "param_index": -1}

    # H3: 入参 schema 校验前置
    if not isinstance(params, list) or not params:
        return {
            "success": False,
            "error": "params must be a non-empty list",
            "param_index": -1,
        }
    for i, p in enumerate(params):
        if not isinstance(p, dict):
            return {
                "success": False,
                "error": f"params[{i}] must be a dict, got {type(p).__name__}",
                "param_index": i,
                "field": "type",
            }
        for required in ("path", "value"):
            if required not in p:
                return {
                    "success": False,
                    "error": f"params[{i}] missing required field {required!r}",
                    "param_index": i,
                    "field": required,
                }
        # M9: 校验 params[i].path 路径遍历
        try:
            validate_no_traversal(p["path"])
        except ValueError:
            return {
                "success": False,
                "error": f"params[{i}].path contains path traversal",
                "param_index": i,
                "field": "path",
            }
        type_str = str(p.get("type", "integer")).upper()
        try:
            ParamType(type_str)
        except ValueError:
            return {
                "success": False,
                "error": (
                    f"params[{i}].type={type_str!r} is not a valid ParamType; "
                    f"valid: INTEGER, FLOAT, STRING, BOOLEAN, ENUMERATION"
                ),
                "param_index": i,
                "field": "type",
            }

    try:
        project_path = _resolve_safe_project(project)
    except PermissionError as e:
        return {
            "success": False,
            "error": f"{type(e).__name__}: {e}",
            "field": "project",
            "param_index": -1,
        }
    tresos_path = Path(tresos_home).resolve() if tresos_home else _default_tresos_home(project_path)
    try:
        tresos_path.relative_to(project_path)
    except ValueError as e:
        return {
            "success": False,
            "error": f"tresos_home must be inside project_path: {e}",
            "field": "tresos_home",
            "param_index": -1,
        }
    tresos_path.mkdir(parents=True, exist_ok=True)

    bsw_params = tuple(
        BSWParam(
            path=p["path"],
            value=ParamValue(
                raw=str(p["value"]),
                type=ParamType(str(p.get("type", "integer")).upper()),
            ),
        )
        for p in params
    )

    ctx = _build_ctx(project_path, tresos_path, module)
    adapter = TresosAdapter()
    try:
        result = modify_and_verify(
            ctx,
            adapter,
            ModifyRequest(module=module, params=bsw_params),
        )
    except (OSError, ValueError, TypeError, KeyError) as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    # 自动记录 session（Sprint 11 T11.3）
    if result.success:
        _try_record_session(module, params, success=True)
    else:
        _try_record_session(module, params, success=False)

    return {
        "success": result.success,
        "module": module,
        "written_files": [str(p) for p in result.written_files],
        "verify_output": result.verify_output,
        "rolled_back": result.rolled_back,
        "error": result.error,
    }


def bsw_verify(
    module: str,
    *,
    project: str = ".",
    tresos_home: str | None = None,
    chip_derivative: str | None = None,
    mcal_vendor: str | None = None,
    mcal_vendor_home: str | None = None,
    as_json: bool = False,
) -> dict[str, Any]:
    """调用 tresos_cmd verify（只 verify，不改值）。

    Sprint 9.3 — T9.3-beta 增强：v2 path 参数 + as_json + H4 路径防御。

    :param module: BSW 模块名（如 Mcu）
    :param project: 工程根目录路径字符串（默认 cwd）
    :param tresos_home: EB tresos CLI 根
    :param chip_derivative: 芯片派生
    :param mcal_vendor: MCAL 厂商
    :param mcal_vendor_home: 厂商 AUTOSAR 包根目录
    :param as_json: True 时返完整 TresosVerifyReport 序列化
    """
    from typing import cast

    from claude_autosar.cli.mcp_server import (
        _build_ctx,
        _default_tresos_home,
        _resolve_safe_project,
    )
    from claude_autosar.cli.mcp_tools.validation import validate_module_name
    from claude_autosar.adapters.tresos import TresosAdapter
    from claude_autosar.core.bsw.verify.tresos_parser import parse_tresos_verify_stdout

    # M12: 校验 module 白名单
    try:
        validate_module_name(module)
    except ValueError as e:
        return {"success": False, "error": str(e), "field": "module", "param_index": -1}

    try:
        project_path = _resolve_safe_project(project)
    except PermissionError as e:
        return {
            "success": False,
            "error": f"{type(e).__name__}: {e}",
            "field": "project",
            "param_index": -1,
        }
    tresos_path = Path(tresos_home).resolve() if tresos_home else _default_tresos_home(project_path)
    try:
        tresos_path.relative_to(project_path)
    except ValueError as e:
        return {
            "success": False,
            "error": f"tresos_home must be inside project_path: {e}",
            "field": "tresos_home",
            "param_index": -1,
        }
    tresos_path.mkdir(parents=True, exist_ok=True)

    _v2_paths_meta: dict[str, str] = {}
    try:
        from claude_autosar.core.settings.v2_paths import load_v2_paths

        v2 = load_v2_paths(
            project_path,
            cli_tresos_home=str(tresos_path),
            cli_mcal_vendor=mcal_vendor,
            cli_mcal_vendor_home=mcal_vendor_home,
            cli_chip_derivative=chip_derivative,
        )
        _v2_paths_meta = {
            "tresos_home": str(v2.tresos_home),
            "mcal_vendor": str(v2.mcal_vendor),
            "mcal_vendor_home": str(v2.mcal_vendor_home),
            "chip_derivative": str(v2.chip_derivative),
        }
    except Exception:
        pass

    ctx = _build_ctx(project_path, tresos_path, module)
    result = TresosAdapter().verify(ctx, module)
    report = parse_tresos_verify_stdout(
        result.stdout,
        result.stderr,
        returncode=result.returncode,
        module=module,
    )
    if as_json:
        from dataclasses import asdict

        report_dict = asdict(cast(Any, report))
        report_dict["has_errors"] = report.has_errors
        report_dict["has_warnings"] = report.has_warnings
        return {
            "success": result.returncode == 0,
            "module": module,
            "returncode": result.returncode,
            "report": report_dict,
            "v2_paths": _v2_paths_meta,
        }
    return {
        "success": result.returncode == 0,
        "module": module,
        "returncode": result.returncode,
        "report": {
            "issue_count": len(report.issues),
            "has_errors": report.has_errors,
            "has_warnings": report.has_warnings,
        },
        "v2_paths": _v2_paths_meta,
    }


def bsw_autocalc(
    modules: list[str], *, project: str = ".", tresos_home: str | None = None
) -> dict[str, Any]:
    """触发 AutoCalc（仅 EB tresos 支持；DaVinci 跳过）。

    注：当前协议只支持单 ctx 触发，modules[1:] 会被忽略。
    """
    from claude_autosar.cli.mcp_server import (
        _build_ctx,
        _default_tresos_home,
        _resolve_safe_project,
    )
    from claude_autosar.cli.mcp_tools.validation import validate_module_name
    from claude_autosar.adapters.tresos import TresosAdapter

    # M12: 校验 modules 白名单
    for idx, mod in enumerate(modules):
        try:
            validate_module_name(mod)
        except ValueError as e:
            return {"success": False, "error": str(e), "field": "module", "param_index": idx}

    try:
        project_path = _resolve_safe_project(project)
    except PermissionError as e:
        return {
            "success": False,
            "error": f"{type(e).__name__}: {e}",
            "field": "project",
            "param_index": -1,
        }
    tresos_path = Path(tresos_home).resolve() if tresos_home else _default_tresos_home(project_path)
    try:
        tresos_path.relative_to(project_path)
    except ValueError as e:
        return {
            "success": False,
            "error": f"tresos_home must be inside project_path: {e}",
            "field": "tresos_home",
            "param_index": -1,
        }
    tresos_path.mkdir(parents=True, exist_ok=True)
    primary = modules[0] if modules else None
    if primary is None:
        return {"success": False, "error": "modules list is empty"}
    ctx = _build_ctx(project_path, tresos_path, primary)
    result = TresosAdapter().autocalc(ctx)
    return {
        "success": result.success,
        "modules_requested": modules,
        "autocalc_triggered_module": primary,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _try_record_session(
    module: str,
    params: list[dict[str, Any]],
    *,
    success: bool,
) -> None:
    """尝试记录 session；失败静默忽略（不影响主流程）。"""
    try:
        from claude_autosar.core.session.recorder import record_bsw_write_batch
        from claude_autosar.core.session.store import SessionStore
        from claude_autosar.utils.paths import global_session_dir

        store = SessionStore(dir=global_session_dir())
        record_bsw_write_batch(
            store,
            module=module,
            params=tuple(
                {"path": p["path"], "value": str(p["value"])}
                for p in params
            ),
            success=success,
        )
    except Exception:
        # session 记录失败不影响主流程
        pass
