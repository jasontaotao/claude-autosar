"""AutoC MCP server（Sprint 5 — T5.3）。

把 autoc 的核心能力以 10 个 tool 形式暴露给 Claude Code 子 Agent。
所有 tool 接收基本类型参数，返回 JSON-friendly dict；错误路径走
``{"success": False, "error": "..."}`` 模式而不是抛异常，方便 MCP 客户端
拿到结构化错误。

启动：``python -m autoc.cli.mcp_server``（stdio 传输）
调试：``mcp-inspector python -m autoc.cli.mcp_server``
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

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

#: T3.1 节规定的 10 个 tool 名称（顺序无意义，集合用于注册自检）
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
)


def _default_session_dir() -> Path:
    """默认 session 目录：``~/.autoc/agent/sessions``。"""
    from autoc.utils.paths import global_session_dir

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
    from autoc.adapters.protocol import EcuConfigProjectContext

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

    :param module: BSW 模块名（如 ``Mcu``）
    :param path: ECUC 路径（如 ``Clock/ClockFreq``），会自动拼上 ``<module>/`` 前缀
    :param project: 工程根目录路径字符串，默认 cwd
    :return: ``{"success": True, "module", "path", "raw", "type", "value"}`` 或 error dict
    """
    from autoc.core.bsw.ecuc import get_value, load_module

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
    try:
        doc = load_module(f, module)
    except (ValueError, FileNotFoundError) as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}
    full_path = path if path.startswith(f"{module}/") else f"{module}/{path}"
    val = get_value(doc, full_path)
    if val is None:
        return {"success": False, "error": f"path {full_path!r} not in module {module!r}"}
    # M27: 派生 typed value（"80000000" → 80000000）
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
    }


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
    from autoc.adapters.tresos import TresosAdapter
    from autoc.core.bsw.config import BSWParam, ParamType, ParamValue
    from autoc.core.bsw.validator import ModifyRequest, modify_and_verify

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
    module: str, *, project: str = ".", tresos_home: str | None = None
) -> dict[str, Any]:
    """调用 ``tresos_cmd verify``（只 verify，不改值）。"""
    from autoc.adapters.tresos import TresosAdapter

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
    ctx = _build_ctx(project_path, tresos_path, module)
    result = TresosAdapter().verify(ctx, module)
    return {
        "success": result.success,
        "module": module,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def bsw_autocalc(
    modules: list[str], *, project: str = ".", tresos_home: str | None = None
) -> dict[str, Any]:
    """触发 AutoCalc（仅 EB tresos 支持；DaVinci 跳过）。

    注：当前协议只支持单 ctx 触发，所以 ``modules[1:]`` 会被忽略。响应里
    用 ``autocalc_triggered_module`` 字段明确告诉 LLM 实际跑了哪个。
    """
    from autoc.adapters.tresos import TresosAdapter

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
    from autoc.core.bsw.arxml_io import ARXMLError, read

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
    from autoc.core.session.store import SessionStore

    d = Path(session_dir) if session_dir else _default_session_dir()
    return SessionStore(dir=d).list_session_ids()


def session_show(session_id: str, *, session_dir: str | None = None) -> dict[str, Any]:
    """读单个 session 全部 entry。

    支持特殊值 ``"latest"``：解析为 session_dir 下 mtime 最大的 session。
    """
    from autoc.core.session.store import SessionStore, SessionStoreError

    d = Path(session_dir) if session_dir else _default_session_dir()
    if session_id == "latest":
        from autoc.core.session.store import resolve_latest_session_id

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
    from autoc.core.session.exporter import export_html
    from autoc.core.session.store import SessionStore, SessionStoreError
    from autoc.core.session.tree import SessionTree

    if fmt != "html":
        return {"success": False, "error": f"unsupported fmt: {fmt!r} (only 'html')"}
    d = Path(session_dir) if session_dir else _default_session_dir()
    if session_id == "latest":
        from autoc.core.session.store import resolve_latest_session_id

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
    from autoc.core.log.changelog import extract_changes, render_by_url, render_timeline
    from autoc.core.session.store import SessionStore, SessionStoreError
    from autoc.core.session.tree import SessionTree

    if view not in {"timeline", "by-url"}:
        return {"success": False, "error": f"unsupported view: {view!r}"}
    d = Path(session_dir) if session_dir else _default_session_dir()
    if session_id == "latest":
        from autoc.core.session.store import resolve_latest_session_id

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
