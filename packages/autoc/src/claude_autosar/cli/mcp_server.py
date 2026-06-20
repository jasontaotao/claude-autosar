"""AutoC MCP server（Sprint 5 — T5.3）。

把 autoc 的核心能力以 10 个 tool 形式暴露给 Claude Code 子 Agent。
所有 tool 接收基本类型参数，返回 JSON-friendly dict；错误路径走
``{"success": False, "error": "..."}`` 模式而不是抛异常，方便 MCP 客户端
拿到结构化错误。

启动：``python -m autoc.cli.mcp_server``（stdio 传输）
调试：``mcp-inspector python -m autoc.cli.mcp_server``

Sprint 9.5 重构：tool 实现拆分到 ``mcp_tools/`` 子包（bsw_ops / session_ops /
inspect_ops），本文件保留 server factory、dispatch table、路径防御、
context builder。所有 tool 函数通过 re-export 保持
``from claude_autosar.cli.mcp_server import bsw_read`` 等既有 import 路径不变。
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
    # Sprint 10 T10.6
    "bsw_validate",
    # Sprint 11 T11.1
    "bsw_diff",
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
# Re-export tool 实现函数（从 mcp_tools 子包导入，保持向后兼容）
# ---------------------------------------------------------------------------
# 既有的 import 路径 ``from claude_autosar.cli.mcp_server import bsw_read`` 等
# 继续工作；monkeypatch ``mcp_server._run_lint_for_inspect`` 也继续工作
# （inspect tool 函数内部通过 ``import claude_autosar.cli.mcp_server`` 模块
# 引用调用 _run_lint_for_inspect，确保 monkeypatch 生效）。

from claude_autosar.cli.mcp_tools.bsw_read_ops import (  # noqa: E402
    _infer_value,
    bsw_read,
)
from claude_autosar.cli.mcp_tools.bsw_write_ops import (  # noqa: E402
    bsw_autocalc,
    bsw_verify,
    bsw_write,
)
from claude_autosar.cli.mcp_tools.inspect_ops import (  # noqa: E402
    _inspect_resolve_input,
    _run_lint_for_inspect,
    arxml_inspect,
    arxml_validate,
    bsw_inspect,
    dbc_parse,
    xdm_inspect,
)
from claude_autosar.cli.mcp_tools.apply_template_ops import (  # noqa: E402
    _apply_result_to_dict,
    _detect_arxml_module_name,
    _detect_xdm_module_name,
    arxml_apply_template,
    xdm_apply_template,
)
from claude_autosar.cli.mcp_tools.session_ops import (  # noqa: E402
    log_export,
    session_export,
    session_list,
    session_show,
)
from claude_autosar.cli.mcp_tools.validate_ops import (  # noqa: E402
    bsw_validate,
)
from claude_autosar.cli.mcp_tools.diff_ops import (  # noqa: E402
    bsw_diff,
)


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
    # Sprint 10 T10.6
    "bsw_validate": bsw_validate,
    # Sprint 11 T11.1
    "bsw_diff": bsw_diff,
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
