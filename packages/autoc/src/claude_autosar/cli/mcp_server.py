"""AutoC MCP server（Sprint 5 — T5.3）。

把 autoc 的核心能力以 10 个 tool 形式暴露给 Claude Code 子 Agent。
所有 tool 接收基本类型参数，返回 JSON-friendly dict；错误路径走
``{"success": False, "error": "..."}`` 模式而不是抛异常，方便 MCP 客户端
拿到结构化错误。

启动：``python -m autoc.cli.mcp_server``（stdio 传输）
调试：``mcp-inspector python -m autoc.cli.mcp_server``
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Sprint 5 review fixes
# ---------------------------------------------------------------------------
# - H1: ``session_show("latest")`` 现在走 :func:`resolve_latest_session_id`（mtime
#   排序），与 CLI ``autoc session show latest`` 行为对齐
# - H2: ``bsw_write`` 异常收窄到 ``(OSError, ValueError, TypeError, KeyError)``；
#       ``from e`` 保留异常链
# - H3: ``bsw_write`` 入参 schema 校验前置，给 LLM 指出 ``param_index`` + ``field``
# - H4: ``bsw_*`` 工具的 ``project`` / ``tresos_home`` 路径防御：project 必须是
#       cwd 的子目录；tresos_home 必须是 project 的子目录（ISO 21434 信任边界）

# ---------------------------------------------------------------------------
# 模块级常量和工厂
# ---------------------------------------------------------------------------

#: T3.1 节规定的 10 个 tool 名称 + Sprint 9.1 T9.1.4 新增 3 个 inspect tool
#: （顺序无意义，集合用于注册自检）
_TOOL_NAMES: tuple[str, ...] = (
    "bsw_read",
    "bsw_write",
    "bsw_verify",
    "bsw_autocalc",
    "arxml_validate",
    "dbc_parse",
    "session_list",
    "session_show",
    "session_export",
    "log_export",
    # Sprint 9.1 T9.1.4
    "arxml_inspect",
    "xdm_inspect",
    "bsw_inspect",
    # Sprint 9.2 T9.2-γ
    "arxml_apply_template",
    "xdm_apply_template",
)


def _default_session_dir() -> Path:
    """默认 session 目录：``~/.autoc/agent/sessions``。"""
    from claude_autosar.utils.paths import global_session_dir

    return global_session_dir()


def _default_tresos_home(project: Path) -> Path:
    """默认 EB tresos 工具目录：``<project>/tresos_home``（多数 CI 假工程用此约定）。"""
    return project / "tresos_home"


#: H4 路径防御：允许的项目根（当前工作目录的解析结果；MCP 启动时快照一次）
_ALLOWED_PROJECT_ROOTS: frozenset[Path] = frozenset({Path.cwd().resolve()})


def _resolve_safe_project(project: str) -> Path:
    """H4 防御：解析 ``project`` 路径并校验其必须在 :data:`_ALLOWED_PROJECT_ROOTS` 内。

    抛出 :class:`PermissionError`（包含清晰错误信息）以阻止 path-traversal。
    """
    resolved = Path(project).resolve()
    for root in _ALLOWED_PROJECT_ROOTS:
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    raise PermissionError(
        f"project {resolved!s} is outside the allowed roots "
        f"{[str(r) for r in _ALLOWED_PROJECT_ROOTS]}"
    )


# ---------------------------------------------------------------------------
# 通用辅助：构造 EcuConfigProjectContext（bsw_* 工具用）
# ---------------------------------------------------------------------------


def _build_ctx(project: Path, tresos_home: Path, module: str) -> Any:
    """构造最小 ``EcuConfigProjectContext``（adapters 协议要求）。"""
    from claude_autosar.adapters.protocol import EcuConfigProjectContext

    return EcuConfigProjectContext(
        project_path=project,
        tool_home=tresos_home,
        target="UNKNOWN",
        derivate="UNKNOWN",
        pn="UNKNOWN",
        autosar_version="0.0.0",
        enabled_modules=(module,),
        available_plugins=(),
    )


# ---------------------------------------------------------------------------
# 10 个 tool 实现
# ---------------------------------------------------------------------------


def bsw_read(module: str, path: str, *, project: str = ".") -> dict[str, Any]:
    """读 XDM/ARXML 中 ``module`` 模块下 ``path`` 路径的参数值。

    Sprint 9.0 T9.0.3 改：用 :mod:`claude_autosar.core.bsw.dispatcher` 按文件
    根 namespace 自动选 arxml_io（AUTOSAR r4.x）或 datamodel2_io（EB tresos
    DataModel2）。XDM 路径用 ``<d:var>`` 扁平提取（DataModel2 树结构跟 ECUC
    不兼容，无法走 ECUC walker）。

    :param module: BSW 模块名（如 ``Mcu``）
    :param path: ECUC 路径（如 ``Clock/ClockFreq``），会自动拼上 ``<module>/`` 前缀
    :param project: 工程根目录路径字符串，默认 cwd
    :return: ``{"success": True, "module", "path", "raw", "type", "value", "format"}`` 或 error dict
    """
    from claude_autosar.core.bsw.dispatcher import (
        detect_format,
        UnknownFormatError,
        DispatcherError,
    )
    from claude_autosar.core.bsw.ecuc import get_value, load_module

    try:
        project_path = _resolve_safe_project(project)
    except PermissionError as e:
        return {
            "success": False,
            "error": f"{type(e).__name__}: {e}",
            "field": "project",
            "param_index": -1,
        }
    for ext in (".xdm", ".arxml"):
        f = project_path / f"{module}{ext}"
        if f.is_file():
            break
    else:
        return {
            "success": False,
            "error": f"module {module!r} not found in {project_path} (no .xdm or .arxml)",
        }
    # T9.0.3: dispatch by root namespace
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
            return {"success": False, "error": f"path {full_path!r} not in module {module!r}"}
        value_typed: int | float | bool | str = val.raw
        try:
            if isinstance(val.raw, str):
                if val.raw.lower() in ("true", "false"):
                    value_typed = val.raw.lower() == "true"
                elif val.raw.isdigit() or (val.raw.startswith("-") and val.raw[1:].isdigit()):
                    value_typed = int(val.raw)
                else:
                    value_typed = float(val.raw)
        except ValueError:
            pass  # 保留 str
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


# ---------------------------------------------------------------------------
# XDM (DataModel2) value extraction — Sprint 9.0 T9.0.3
# ---------------------------------------------------------------------------


def _bsw_read_xdm(path: Path, module: str, full_path: str) -> dict[str, Any]:
    """从 DataModel2 .xdm 读 ``<module>/<container>/.../<param>`` 路径下的值。

    DataModel2 树结构跟 ECUC 完全不一样（扁平 ``<d:var name=... type=... value=...>``）
    — 不能走 :func:`claude_autosar.core.bsw.ecuc.load_module`。本函数直接用
    lxml xpath 在 ``<d:chc name=<module>>`` 容器下定位。

    路径语义：每段对应一个 ``name`` 属性（container 或 var 同名空间）。例如
    ``Mcu/McuClockSettingConfig_0/McuClockFrequency`` 在 XDM 里就是
    ``<d:chc name=Mcu>`` → ``<d:ctr name=McuClockSettingConfig_0>`` →
    ``<d:var name=McuClockFrequency>``。
    """
    from claude_autosar.core.bsw.io.datamodel2_io import (
        DataModel2Error,
        read as _xdm_read,
    )

    try:
        tree = _xdm_read(path)
    except (DataModel2Error, OSError) as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    root = tree.getroot() if hasattr(tree, "getroot") else tree
    nsmap = dict(root.nsmap) if getattr(root, "nsmap", None) else {}
    default_ns = nsmap.get(None, "")

    def _q(local: str) -> str:
        return f"{{{default_ns}}}{local}" if default_ns else local

    # 找 <d:chc name=<module>>（AR-ELEMENT 节点）
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

    # 沿 path 段下钻。container 用 d:ctr 或 d:lst，leaf 用 d:var。
    # EB tresos DataModel2 树里中间层节点类型有 3 种：d:ctr (container)、
    # d:lst (list / map of children)、d:chc (choice)。所有中间层都有
    # ``name`` 属性。leaf 一定是 d:var 带 ``value`` 属性。
    segments = full_path.split("/")
    if segments[0] == module:
        segments = segments[1:]
    current = module_elem
    for i, seg in enumerate(segments):
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
    # current 应该是 d:var（leaf）；d:ctr 没有 value
    value_attr = current.get("value")
    type_attr = current.get("type")
    if value_attr is None:
        return {
            "success": False,
            "error": f"path {full_path!r} resolves to a container, not a leaf value",
        }
    # 类型派生
    value_typed: int | float | bool | str = value_attr
    inferred_type = type_attr or "STRING"
    if isinstance(value_attr, str):
        if value_attr.lower() in ("true", "false"):
            value_typed = value_attr.lower() == "true"
        elif value_attr.isdigit() or (value_attr.startswith("-") and value_attr[1:].isdigit()):
            with contextlib.suppress(ValueError):
                value_typed = int(value_attr)
        else:
            with contextlib.suppress(ValueError):
                value_typed = float(value_attr)
    return {
        "success": True,
        "module": module,
        "path": full_path,
        "raw": value_attr,
        "value": value_typed,
        "type": str(inferred_type).upper(),
    }


def _is_descendant_of(candidate: Any, ancestor: Any) -> bool:
    """判断 ``candidate`` 是否是 ``ancestor`` 的后代（lxml ``iterancestors`` 路径检查）。

    用于 XDM path walker 防 xpath 上跳（参见 :func:`_bsw_read_xdm`）。
    """
    try:
        # iterancestors() 返回所有 ancestor（从最近到 root）
        return any(anc is ancestor for anc in candidate.iterancestors())
    except (AttributeError, TypeError):
        # 防御：candidate 不是 lxml 元素
        return False


def bsw_write(
    module: str,
    params: list[dict[str, Any]],
    *,
    project: str = ".",
    tresos_home: str | None = None,
) -> dict[str, Any]:
    """写一组 BSW 参数 + verify + 失败回滚（与 ``eb save`` 语义一致）。

    :param module: BSW 模块名
    :param params: list of ``{"path": "Mcu/Clock/ClockFreq", "value": 80000000, "type": "INTEGER"}``
    :param project: 工程根目录
    :param tresos_home: EB tresos 安装目录（默认 ``<project>/tresos_home``）
    """
    from claude_autosar.adapters.tresos import TresosAdapter
    from claude_autosar.core.bsw.config import BSWParam, ParamType, ParamValue
    from claude_autosar.core.bsw.validator import ModifyRequest, modify_and_verify

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
        # ParamType 枚举值是小写（``integer`` / ``float`` / ...），与 EB tresos
        # ``BswMConfigType`` 字面值一致
        type_str = str(p.get("type", "integer")).lower()
        try:
            ParamType(type_str)
        except ValueError:
            return {
                "success": False,
                "error": (
                    f"params[{i}].type={type_str!r} is not a valid ParamType; "
                    f"valid: integer, float, string, boolean, enumeration"
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
    # H4: tresos_path 必须位于 project_path 之内
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
                type=ParamType(str(p.get("type", "integer")).lower()),
            ),
        )
        for p in params
    )

    ctx = _build_ctx(project_path, tresos_path, module)
    adapter = TresosAdapter()
    # H2: 异常收窄到 (OSError, ValueError, TypeError, KeyError) + 异常链
    try:
        result = modify_and_verify(
            ctx,
            adapter,
            ModifyRequest(module=module, params=bsw_params),
        )
    except (OSError, ValueError, TypeError, KeyError) as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

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
    """调用 ``tresos_cmd verify``（只 verify，不改值）。

    Sprint 9.3 — T9.3-β 增强：

    * 新增 4 个 v2 path 参数（``chip_derivative`` / ``mcal_vendor`` /
      ``mcal_vendor_home``）→ 走 :func:`load_v2_paths` 4 级优先级合并。
    * 新增 ``as_json`` 参数：默认返轻量 dict（success / module / returncode /
      report 摘要）；``as_json=True`` 时返完整
      :class:`TresosVerifyReport` 序列化。
    * 保留 H4 路径防御（``tresos_home.relative_to(project_path)`` 校验）。

    :param module: BSW 模块名（如 ``Mcu``）
    :param project: 工程根目录路径字符串（默认 cwd）
    :param tresos_home: EB tresos CLI 根（CLI 参数 / settings.json / 环境变量 /
        探测 4 级优先级合并）
    :param chip_derivative: 芯片派生（如 ``Mcu_s32k148_lqfp176.epd``）
    :param mcal_vendor: MCAL 厂商（nxp / st / ti / renesas / infineon）
    :param mcal_vendor_home: 厂商 AUTOSAR 包根目录
    :param as_json: ``True`` 时返完整 :class:`TresosVerifyReport` 序列化
    :return: ``{"success": ..., "module", "returncode", "report": {...}}`` 或
        ``as_json=True`` 时返 report dict 顶层展开。
    """
    from claude_autosar.adapters.tresos import TresosAdapter
    from claude_autosar.core.bsw.verify.tresos_parser import parse_tresos_verify_stdout

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

    # T9.3-β：把 4 个 v2 path 喂给 load_v2_paths（best-effort：失败不阻塞 verify，
    # 因为现有 verify 链路不依赖 vendor/chip 字段；保留扩展点）。
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
        # load_v2_paths 4 级都拿不到时抛 V2PathsError；这里不阻塞 verify 主链路。
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
        # 完整 TresosVerifyReport 序列化（含 issues tuple / has_errors property）
        from dataclasses import asdict

        report_dict = asdict(cast(Any, report))  # mypy: asdict 不接受 type[DataclassInstance]
        report_dict["has_errors"] = report.has_errors
        report_dict["has_warnings"] = report.has_warnings
        return {
            "success": result.returncode == 0,
            "module": module,
            "returncode": result.returncode,
            "report": report_dict,
            "v2_paths": _v2_paths_meta,
        }
    # 默认轻量 dict：仅暴露 summary（issue 数 + has_errors/has_warnings）
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

    注：当前协议只支持单 ctx 触发，所以 ``modules[1:]`` 会被忽略。响应里
    用 ``autocalc_triggered_module`` 字段明确告诉 LLM 实际跑了哪个。
    """
    from claude_autosar.adapters.tresos import TresosAdapter

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


def arxml_validate(path: str) -> dict[str, Any]:
    """ARXML 解析校验（parse-only：Sprint 5 范围内不接 XSD）。"""
    from claude_autosar.core.bsw.arxml_io import ARXMLError, read

    p = Path(path)
    if not p.is_file():
        return {"success": False, "error": f"file not found: {path}"}
    try:
        doc = read(p)
    except ARXMLError as e:
        return {"success": False, "error": f"ARXMLError: {e}"}
    except Exception as e:  # lxml / OSError 等
        return {"success": False, "error": f"{type(e).__name__}: {e}"}
    root = doc.tree.getroot()
    return {
        "success": True,
        "path": str(p),
        "root_tag": root.tag,
        "element_count": len(root.xpath("//*")),
    }


def dbc_parse(path: str) -> dict[str, Any]:
    """DBC 解析：返回 messages + signals 的 JSON 友好 dict。"""
    try:
        import cantools
    except ImportError:
        return {"success": False, "error": "cantools not installed"}
    p = Path(path)
    if not p.is_file():
        return {"success": False, "error": f"file not found: {path}"}
    try:
        # cantools 41 推荐 ``cantools.database.load_file``（旧的 ``cantools.db`` 已 deprecate）
        db = cantools.database.load_file(str(p))
    except Exception as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}
    # cantools 返回 Union[CanDatabase, DiagnosticsDatabase]；这里只取 .messages（CAN-only）
    if not hasattr(db, "messages"):
        return {"success": False, "error": "DBC parsed as non-CAN database (no messages)"}
    return {
        "success": True,
        "path": str(p),
        "version": getattr(db, "version", None),
        "messages": [
            {
                "name": m.name,
                "frame_id": m.frame_id,
                "is_extended": m.is_extended_frame,
                "length": m.length,
                "signals": [
                    {
                        "name": s.name,
                        "start_bit": s.start,  # cantools 41 把 start_bit 改名 start
                        "length": s.length,  # bit length
                        "byte_order": (
                            "little_endian" if s.byte_order == "little_endian" else "big_endian"
                        ),
                        "is_signed": s.is_signed,
                        "scale": s.scale,
                        "offset": s.offset,
                        "unit": s.unit or "",
                        "minimum": s.minimum,
                        "maximum": s.maximum,
                    }
                    for s in m.signals
                ],
            }
            for m in db.messages
        ],
    }


def session_list(*, session_dir: str | None = None) -> list[str]:
    """列出所有 session id。"""
    from claude_autosar.core.session.store import SessionStore

    d = Path(session_dir) if session_dir else _default_session_dir()
    return SessionStore(dir=d).list_session_ids()


def session_show(session_id: str, *, session_dir: str | None = None) -> dict[str, Any]:
    """读单个 session 全部 entry。

    支持特殊值 ``"latest"``：解析为 session_dir 下 mtime 最大的 session。
    """
    from claude_autosar.core.session.store import SessionStore, SessionStoreError

    d = Path(session_dir) if session_dir else _default_session_dir()
    if session_id == "latest":
        from claude_autosar.core.session.store import resolve_latest_session_id

        latest = resolve_latest_session_id(d)
        if latest is None:
            return {"success": False, "error": "no sessions found"}
        session_id = latest
    try:
        sess = SessionStore(dir=d).read(session_id)
    except SessionStoreError as e:
        return {"success": False, "error": str(e)}
    return {
        "success": True,
        "session_id": sess.id,
        "started_at": sess.started_at,
        "title": sess.title,
        "entries": [
            {
                "id": e.id,
                "parent_id": e.parent_id,
                "session_id": e.session_id,
                "timestamp": e.timestamp,
                "kind": e.kind,
                "content": e.content,
                "tool_name": e.tool_name,
                "tool_args": e.tool_args,
                "tool_result": e.tool_result,
            }
            for e in sess.entries
        ],
    }


def session_export(
    session_id: str,
    fmt: str = "html",
    *,
    output: str | None = None,
    session_dir: str | None = None,
) -> dict[str, Any]:
    """导出 session 为 ``fmt`` 格式（当前仅支持 ``html``）。"""
    from claude_autosar.core.session.exporter import export_html
    from claude_autosar.core.session.store import SessionStore, SessionStoreError
    from claude_autosar.core.session.tree import SessionTree

    if fmt != "html":
        return {"success": False, "error": f"unsupported fmt: {fmt!r} (only 'html')"}
    d = Path(session_dir) if session_dir else _default_session_dir()
    if session_id == "latest":
        from claude_autosar.core.session.store import resolve_latest_session_id

        latest = resolve_latest_session_id(d)
        if latest is None:
            return {"success": False, "error": "no sessions found"}
        session_id = latest
    out_path = Path(output) if output else d / f"{session_id}.html"
    try:
        tree = SessionTree.from_session_id(session_id, SessionStore(dir=d))
    except SessionStoreError as e:
        return {"success": False, "error": str(e)}
    try:
        written = export_html(tree, out_path)
    except OSError as e:
        return {"success": False, "error": f"OSError: {e}"}
    return {
        "success": True,
        "session_id": session_id,
        "format": fmt,
        "path": str(written),
    }


def log_export(
    session_id: str,
    view: str = "timeline",
    *,
    session_dir: str | None = None,
) -> dict[str, Any]:
    """从 session 提取 ``bsw_write`` entry，渲染成 timeline / by-url 文本。"""
    from claude_autosar.core.log.changelog import extract_changes, render_by_url, render_timeline
    from claude_autosar.core.session.store import SessionStore, SessionStoreError
    from claude_autosar.core.session.tree import SessionTree

    if view not in {"timeline", "by-url"}:
        return {"success": False, "error": f"unsupported view: {view!r}"}
    d = Path(session_dir) if session_dir else _default_session_dir()
    if session_id == "latest":
        from claude_autosar.core.session.store import resolve_latest_session_id

        latest = resolve_latest_session_id(d)
        if latest is None:
            return {"success": False, "error": "no sessions found"}
        session_id = latest
    try:
        tree = SessionTree.from_session_id(session_id, SessionStore(dir=d))
    except SessionStoreError as e:
        return {"success": False, "error": str(e)}
    changes = extract_changes(tree)
    text = render_timeline(changes) if view == "timeline" else render_by_url(changes)
    return {
        "success": True,
        "session_id": session_id,
        "view": view,
        "change_count": len(changes),
        "text": text,
    }


# ---------------------------------------------------------------------------
# Sprint 9.1 — T9.1.4 inspector tools（ARXML / XDM / dispatcher wrapper）
# ---------------------------------------------------------------------------
# 复用 :mod:`core.bsw.inspector.arxml_report` 和 ``xdm_report``；路径防御
# 走 :func:`_resolve_safe_project`（R6：project 路径必须是 cwd 子目录）。
# Sprint 9.4 M4 (T9.4-β) ``include_lint`` 激活：跑 LintRule 全集并把
# violations 写进返 dict。
#
# 注：``path`` 参数（待 inspect 的文件）**不**做 project 子目录校验 — 测试用
# tmp_path 时可能落在 cwd 之外（且 ``bsw_read`` 工具自身也只对 ``project``
# 做防御）。这是测试 + 简化实现的折中；后续若需要可加 ``allowed_inspect_roots``
# 防御层。


def _inspect_resolve_input(path: str, *, project: str = ".") -> Path:
    """解析 inspector 工具的 ``path`` 输入 + 校验 ``project`` 在允许根内。

    :raises PermissionError: project 不在 allowed roots
    :raises FileNotFoundError: 输入文件不存在
    """
    # 强制走 _resolve_safe_project：project 参数必须在 allowed roots 内
    _resolve_safe_project(project)
    src = Path(path).resolve()
    if not src.is_file():
        raise FileNotFoundError(f"file not found: {src}")
    return src


def _run_lint_for_inspect(
    src: Path, fmt: str
) -> dict[str, Any] | None:
    """走 LintRunner 跑 lint，返回 ``{violations, lint_summary}`` 或 ``None``。

    duck-typed：9.4-α 在并发写 ``core.bsw.lint``；框架未就位时返 ``None``
    （向调用方表示 "lint 不可用" 而不是抛异常）。任何 IO / 类型异常都收
    敛到 ``None``，避免污染 inspect 主流程。
    """
    try:
        from claude_autosar.core.bsw.lint import LintRunner
        from claude_autosar.core.bsw.lint.rules import rules_for_namespace
    except ImportError:
        return None

    try:
        if fmt == "arxml":
            from claude_autosar.core.bsw.lint.extract import (
                extract_arxml_for_lint,
            )

            extracted: Any = extract_arxml_for_lint(src)
            ns = "arxml"
        else:
            from claude_autosar.core.bsw.lint.extract import extract_xdm_for_lint

            extracted = extract_xdm_for_lint(src)
            ns = "xdm"
    except (ImportError, OSError, ValueError, TypeError):
        return None

    try:
        # 按 namespace 过滤规则（避免 arxml 规则被喂 XDM 数据抛 AttributeError）
        rules = list(rules_for_namespace(ns))
        runner = LintRunner(rules=rules)
        violations = list(runner.run(extracted))
        summary = runner.summarize(violations)
    except (OSError, ValueError, TypeError, AttributeError):
        return None

    return {
        "violations": [
            {
                "rule_id": str(getattr(v, "rule_id", "")),
                "severity": str(getattr(v, "severity", "")),
                "message": str(getattr(v, "message", "")),
                "path": str(getattr(v, "path", "") or ""),
                "line": getattr(v, "line", None),
            }
            for v in violations
        ],
        "lint_summary": (
            {
                "total": int(getattr(summary, "total", 0)),
                "by_severity": dict(
                    getattr(summary, "by_severity", {}) or {}
                ),
            }
            if summary is not None
            else {"total": len(violations), "by_severity": {}}
        ),
    }


def arxml_inspect(
    path: str,
    output: str | None = None,
    *,
    include_lint: bool = False,
    project: str = ".",
) -> dict[str, Any]:
    """读单个 ``.arxml`` → 渲染一页式 HTML 报告（IPdu / Signal / 关键参数）。

    :param path: ``.arxml`` 文件路径（相对 project 根或绝对）
    :param output: 输出 HTML 路径；``None`` = ``<input>.report.html``
    :param include_lint: ``True`` 时附加 LintRunner 全集（duck-typed；
        lint 框架未就位时返 ``lint_unavailable=True``，不抛异常）
    :param project: 工程根目录（默认 cwd）
    :return: ``{"success": True, "format": "arxml", "report_path": ..., "path": ...}``
        或 error dict
    """
    from claude_autosar.core.bsw.inspector.arxml_report import export_arxml_report

    try:
        src = _inspect_resolve_input(path, project=project)
    except PermissionError as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}
    except FileNotFoundError as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    out_path = Path(output) if output else None
    try:
        written = export_arxml_report(src, output=out_path)
    except (OSError, ValueError, TypeError) as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    result: dict[str, Any] = {
        "success": True,
        "format": "arxml",
        "path": str(src),
        "report_path": str(written),
    }

    if include_lint:
        lint_result = _run_lint_for_inspect(src, "arxml")
        if lint_result is None:
            result["lint_unavailable"] = True
        else:
            result["violations"] = lint_result["violations"]
            result["lint_summary"] = lint_result["lint_summary"]

    return result


def xdm_inspect(
    path: str,
    output: str | None = None,
    *,
    include_lint: bool = False,
    project: str = ".",
) -> dict[str, Any]:
    """读单个 ``.xdm`` (DataModel2) → 渲染一页式 HTML 报告。

    :param path: ``.xdm`` 文件路径（相对 project 根或绝对）
    :param output: 输出 HTML 路径；``None`` = ``<input>.report.html``
    :param include_lint: ``True`` 时附加 LintRunner 全集（duck-typed；
        lint 框架未就位时返 ``lint_unavailable=True``，不抛异常）
    :param project: 工程根目录（默认 cwd）
    :return: ``{"success": True, "format": "xdm", "report_path": ..., "path": ...}``
        或 error dict
    """
    from claude_autosar.core.bsw.inspector.xdm_report import export_xdm_report

    try:
        src = _inspect_resolve_input(path, project=project)
    except PermissionError as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}
    except FileNotFoundError as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    out_path = Path(output) if output else None
    try:
        written = export_xdm_report(src, output=out_path)
    except (OSError, ValueError, TypeError) as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    result: dict[str, Any] = {
        "success": True,
        "format": "xdm",
        "path": str(src),
        "report_path": str(written),
    }

    if include_lint:
        lint_result = _run_lint_for_inspect(src, "xdm")
        if lint_result is None:
            result["lint_unavailable"] = True
        else:
            result["violations"] = lint_result["violations"]
            result["lint_summary"] = lint_result["lint_summary"]

    return result


def bsw_inspect(
    path: str,
    output: str | None = None,
    *,
    include_lint: bool = False,
    project: str = ".",
) -> dict[str, Any]:
    """dispatcher：按文件根 namespace 自动选 arxml / xdm 渲染器。

    :param path: 输入文件路径（按根 xmlns 自动选，不依赖后缀）
    :param output: 输出 HTML 路径；``None`` = ``<input>.report.html``
    :param include_lint: ``True`` 时附加 LintRunner 全集（duck-typed）
    :param project: 工程根目录（默认 cwd）
    :return: ``{"success": True, "format": <arxml|xdm>, "report_path": ..., "path": ...}``
        或 error dict
    """
    from claude_autosar.core.bsw.dispatcher import (
        detect_format,
        DispatcherError,
        UnknownFormatError,
    )
    from claude_autosar.core.bsw.inspector.arxml_report import export_arxml_report
    from claude_autosar.core.bsw.inspector.xdm_report import export_xdm_report

    try:
        src = _inspect_resolve_input(path, project=project)
    except PermissionError as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}
    except FileNotFoundError as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    try:
        fmt = detect_format(src)
    except (UnknownFormatError, DispatcherError) as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}
    except FileNotFoundError as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    out_path = Path(output) if output else None
    try:
        if fmt == "arxml":
            written = export_arxml_report(src, output=out_path)
        else:  # fmt == "xdm"
            written = export_xdm_report(src, output=out_path)
    except (OSError, ValueError, TypeError) as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    result: dict[str, Any] = {
        "success": True,
        "format": fmt,
        "path": str(src),
        "report_path": str(written),
    }

    if include_lint:
        lint_result = _run_lint_for_inspect(src, fmt)
        if lint_result is None:
            result["lint_unavailable"] = True
        else:
            result["violations"] = lint_result["violations"]
            result["lint_summary"] = lint_result["lint_summary"]

    return result


# ---------------------------------------------------------------------------
# Sprint 9.2 — T9.2-γ 双格式 apply-template tool
# ---------------------------------------------------------------------------
# 注：``apply_template_diff`` / ``ApplyMode`` 由并发任务 T9.2.1（apply.py）
# 实现；``diff_arxml_templates`` 由 T9.2.0b（arxml_diff.py）；xdm_diff /
# xdm_value 由 T9.2-α 已完成。本 tool 用延迟 import 调用；这些模块加载失败
# 时返回 ``success=False`` error dict。路径防御复用 :func:`_inspect_resolve_input`。


def arxml_apply_template(
    path: str,
    template: str,
    *,
    apply: bool = False,
    output: str | None = None,
    project: str = ".",
) -> dict[str, Any]:
    """读 ``.arxml`` current + template → diff → dry-run / ``apply`` 写回。

    :param path: ``.arxml`` 当前文件路径（相对 project 根或绝对）
    :param template: ``.arxml`` 模板文件路径
    :param apply: ``True`` 真正写回；``False`` 只算 diff（dry-run）
    :param output: 输出 HTML 报告路径（可选）
    :param project: 工程根目录（默认 cwd）
    :return: ``{"success": True, "format": "arxml", "mode", "diff_count",
        "applied", ...}`` 或 error dict
    """
    from claude_autosar.core.bsw.arxml_io import ARXMLError
    from claude_autosar.core.bsw.dispatcher import (
        DispatcherError,
        FormatMismatchError,
        UnknownFormatError,
        read as dispatcher_read,
    )
    from claude_autosar.core.bsw.ecuc import load_module as ecuc_load_module
    # 延迟 import：依赖 T9.2.1（apply.py）+ T9.2.0b（arxml_diff.py）
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

    tpl = Path(template).resolve()
    if not tpl.is_file():
        return {"success": False, "error": f"FileNotFoundError: {tpl}"}

    try:
        dispatcher_read(src, expected_format="arxml")
        dispatcher_read(tpl, expected_format="arxml")
    except (FileNotFoundError, OSError) as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}
    except (ARXMLError, DispatcherError, UnknownFormatError,
            FormatMismatchError) as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    module_name = _detect_arxml_module_name(src)
    if module_name is None:
        module_name = _detect_arxml_module_name(tpl)
    if module_name is None:
        return {
            "success": False,
            "error": (
                "ValueError: no ECUC-MODULE-CONFIGURATION-VALUES "
                "in current/template"
            ),
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
        "report_path": str(Path(output).resolve()) if output else None,
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
    """读 ``.xdm`` current + template → diff → dry-run / ``apply`` 写回。

    :param path: ``.xdm`` 当前文件路径（相对 project 根或绝对）
    :param template: ``.xdm`` 模板文件路径
    :param apply: ``True`` 真正写回；``False`` 只算 diff（dry-run）
    :param output: 输出 HTML 报告路径（可选）
    :param project: 工程根目录（默认 cwd）
    :return: ``{"success": True, "format": "xdm", "module_name",
        "diff_count", ...}`` 或 error dict
    """
    from claude_autosar.core.bsw.dispatcher import (
        DispatcherError,
        FormatMismatchError,
        UnknownFormatError,
        read as dispatcher_read,
    )
    from claude_autosar.core.bsw.io.datamodel2_io import DataModel2Error
    # 延迟 import：依赖 T9.2.1（apply.py）
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

    tpl = Path(template).resolve()
    if not tpl.is_file():
        return {"success": False, "error": f"FileNotFoundError: {tpl}"}

    try:
        current_doc = dispatcher_read(src, expected_format="xdm")
        template_doc = dispatcher_read(tpl, expected_format="xdm")
    except (FileNotFoundError, OSError) as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}
    except (DataModel2Error, DispatcherError, UnknownFormatError,
            FormatMismatchError) as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    module_name = _detect_xdm_module_name(current_doc)
    if module_name is None:
        module_name = _detect_xdm_module_name(template_doc)
    if module_name is None:
        return {
            "success": False,
            "error": (
                "XDMValueError: no <d:chc type=AR-ELEMENT> in current/template"
            ),
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
        "report_path": str(Path(output).resolve()) if output else None,
        "result": _apply_result_to_dict(apply_result),
    }


def _detect_arxml_module_name(path: Path) -> str | None:
    """从 .arxml 文件取顶层 ECUC-MODULE-CONFIGURATION-VALUES 的 SHORT-NAME。

    任意失败（XML 畸形 / 无 module）一律返回 ``None``；caller 决定 fallback。
    """
    try:
        from lxml import etree

        from claude_autosar.core.bsw.arxml_io import detect_namespaces

        nsmap = detect_namespaces(path)
        ar_uri = nsmap.get("ar")
        if not ar_uri:
            return None
        tree = etree.parse(str(path))
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
    """从 dispatcher 加载的 XDM tree 找第一个 ``<d:chc type=AR-ELEMENT>`` name。"""
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
    """把 ``ApplyResult`` 缩成 dict（不假设字段顺序，避免 dataclass 耦合）。"""
    try:
        from dataclasses import asdict, is_dataclass

        if is_dataclass(result) and not isinstance(result, type):
            return asdict(cast(Any, result))  # mypy: asdict 不接受 type[DataclassInstance]
    except Exception:  # noqa: BLE001
        pass
    try:
        return dict(vars(result))
    except TypeError:
        return {}


# ---------------------------------------------------------------------------
# FastMCP server factory
# ---------------------------------------------------------------------------


#: tool 实现函数表（build_mcp_server 用它注册）
_TOOL_FUNCS: dict[str, Callable[..., Any]] = {
    "bsw_read": bsw_read,
    "bsw_write": bsw_write,
    "bsw_verify": bsw_verify,
    "bsw_autocalc": bsw_autocalc,
    "arxml_validate": arxml_validate,
    "dbc_parse": dbc_parse,
    "session_list": session_list,
    "session_show": session_show,
    "session_export": session_export,
    "log_export": log_export,
    # Sprint 9.1 T9.1.4
    "arxml_inspect": arxml_inspect,
    "xdm_inspect": xdm_inspect,
    "bsw_inspect": bsw_inspect,
    # Sprint 9.2 T9.2-γ
    "arxml_apply_template": arxml_apply_template,
    "xdm_apply_template": xdm_apply_template,
}


def build_mcp_server() -> FastMCP:
    """构造并返回配置好 10 个 tool 的 FastMCP 实例。"""
    server = FastMCP("autoc-mcp")
    for name, fn in _TOOL_FUNCS.items():
        # M2: 强制 dict key 与函数名一致（防止 _TOOL_FUNCS 漂移）
        assert name == fn.__name__, f"tool name {name!r} must match function name {fn.__name__!r}"
        server.add_tool(fn, name=name, description=fn.__doc__ or name)
    return server


def main() -> None:
    """console-script 入口：stdio 传输启动 MCP server。"""
    build_mcp_server().run()


if __name__ == "__main__":
    main()
