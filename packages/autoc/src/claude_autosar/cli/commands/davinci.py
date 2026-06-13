"""`autoc davinci` 子命令：DaVinci Configurator 工具集成。

Sprint 3 — T3.6。提供 `save` / `verify` 子命令（无 autocalc — DaVinciAdapter Protocol 不含）。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Protocol

from claude_autosar.adapters.davinci import DavinciAdapter
from claude_autosar.adapters.protocol import (
    EcuConfigProjectContext,
    SaveResult,
    VerifyResult,
)
from claude_autosar.adapters.stub import StubDavinciAdapter
from claude_autosar.core.bsw.config import BSWParam, ParamType, ParamValue
from claude_autosar.core.bsw.path_resolver import BSWPathResolver
from claude_autosar.core.bsw.validator import ModifyRequest, modify_and_verify


class _HasVerifySave(Protocol):
    """davinci 命令需要的最小 adapter surface（无 autocalc）。"""

    def verify(self, ctx: EcuConfigProjectContext, module: str | None) -> VerifyResult: ...
    def save(self, ctx: EcuConfigProjectContext, module: str | None) -> SaveResult: ...


def register(subparsers: Any) -> None:
    """挂载到主 argparse subparsers。"""
    p = subparsers.add_parser("davinci", help="DaVinci Configurator 工具子命令")
    sub = p.add_subparsers(dest="davinci_command", required=True)

    for cmd in ("save", "verify"):
        sp = sub.add_parser(cmd)
        sp.add_argument("--project", type=Path, default=Path.cwd())
        sp.add_argument("--module", type=str, required=True)
        sp.add_argument("--davinci-home", type=Path, default=None)
        if cmd == "save":
            sp.add_argument(
                "--param",
                action="append",
                default=[],
                help="path=value，可重复，如 Mcu/Clock/ClockFreq=80000000",
            )
        sp.add_argument("--adapter", choices=["real", "stub"], default="real")


def build_parser() -> argparse.ArgumentParser:
    """为单元测试提供独立 parser。"""
    parser = argparse.ArgumentParser(prog="autoc")
    sub = parser.add_subparsers(dest="command", required=False)
    register(sub)
    return parser


def _build_adapter(args: argparse.Namespace) -> _HasVerifySave:
    """根据 args.adapter 选 real 或 stub。"""
    if args.adapter == "stub":
        return StubDavinciAdapter()
    return DavinciAdapter()


def _parse_params(raw_list: list[str], module: str) -> list[BSWParam]:
    """同 eb._parse_params 逻辑。"""
    out: list[BSWParam] = []
    for kv in raw_list:
        if "=" not in kv:
            print(f"警告: --param {kv!r} 不含 '=', 跳过", file=sys.stderr)
            continue
        k, v = kv.split("=", 1)
        raw_path = k.strip()
        path = raw_path if raw_path.startswith(f"{module}/") else f"{module}/{raw_path}"
        out.append(BSWParam(path, ParamValue(v.strip(), ParamType.INTEGER)))
    return out


def run(
    args: argparse.Namespace,
    *,
    adapter_override: _HasVerifySave | None = None,
) -> int:
    """执行 davinci 子命令。返回 exit code。"""
    davinci_home = args.davinci_home or (args.project / "davinci_home")
    davinci_home.mkdir(exist_ok=True)

    # 构造 ctx（davinci adapter 没有 discover()，我们用 args 自己构造）
    ctx = EcuConfigProjectContext(
        project_path=args.project,
        tool_home=davinci_home,
        target="UNKNOWN",
        derivate="UNKNOWN",
        pn="UNKNOWN",
        autosar_version="0.0.0",
        enabled_modules=(args.module,),
        available_plugins=(),
    )

    adapter = adapter_override if adapter_override is not None else _build_adapter(args)

    if args.davinci_command == "save":
        return _run_save(args, adapter, ctx)
    if args.davinci_command == "verify":
        return _run_verify(adapter, ctx, args.module)

    print(json.dumps({"success": False, "error": f"unknown subcommand {args.davinci_command!r}"}))
    return 1


def _run_save(
    args: argparse.Namespace,
    adapter: _HasVerifySave,
    ctx: EcuConfigProjectContext,
) -> int:
    params = _parse_params(args.param, args.module)
    req = ModifyRequest(module=args.module, params=tuple(params))
    try:
        result = modify_and_verify(ctx, adapter, req)
    except Exception as e:
        # T8.E.4: typo 防御 — 尝试给"path not found"类错误加"Did you mean: ..."
        suggestions = _maybe_typo_suggestion(e, ctx, args.module)
        payload: dict[str, Any] = {
            "success": False,
            "error": str(e),
        }
        if suggestions:
            payload["suggestions"] = list(suggestions)
            _emit_did_you_mean(suggestions)
        print(json.dumps(payload))
        return 1
    payload = {
        "success": result.success,
        "written_files": [str(p) for p in result.written_files],
        "verify_output": result.verify_output,
        "rolled_back": result.rolled_back,
        "error": result.error,
    }
    # Sprint 4 — 成功路径写入 session（best-effort）。
    if result.success and params:
        from claude_autosar.core.session.recorder import record_bsw_write_batch
        from claude_autosar.core.session.store import SessionStore

        try:
            rec = record_bsw_write_batch(
                SessionStore(),
                module=args.module,
                params=params,
                success=True,
            )
            if rec is not None:
                payload["session_id"] = rec.session_id
        except (OSError, ValueError, TypeError) as e:
            payload["session_record_error"] = str(e)
    print(json.dumps(payload))
    return 0 if result.success else 1


def _run_verify(
    adapter: _HasVerifySave,
    ctx: EcuConfigProjectContext,
    module: str,
) -> int:
    result = adapter.verify(ctx, module)
    print(
        json.dumps(
            {
                "success": result.success,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
    )
    return 0 if result.success else 1


# ---------------------------------------------------------------------------
# T8.E.4 — typo 防御 helpers（与 eb.py 同样的逻辑）
# ---------------------------------------------------------------------------


def _maybe_typo_suggestion(
    exc: BaseException,
    ctx: EcuConfigProjectContext,
    module: str,
) -> tuple[str, ...]:
    """如果异常来自 `ecuc_set_value` 找不到 path，调 BSWPathResolver 给候选。"""
    from claude_autosar.core.bsw.ecuc import load_module

    # 找目标 .xdm / .arxml
    target_file: Path | None = None
    for ext in (".xdm", ".arxml"):
        candidate = ctx.project_path / f"{module}{ext}"
        if candidate.is_file():
            target_file = candidate
            break
    if target_file is None:
        return ()

    try:
        doc = load_module(target_file, module)
    except Exception:
        return ()

    err_path = _extract_err_path(str(exc))
    if err_path is None:
        return ()

    return BSWPathResolver.suggest_for_ecuc_set_value_error(err_path, doc)


def _extract_err_path(msg: str) -> str | None:
    """从 ValueError msg 提 path。"""
    import re

    patterns = (
        r"path\s+'([^']+)'",
        r"Path\s+'([^']+)'",
        r"\"([^\"]+)\"\s+not\s+in",
    )
    for pat in patterns:
        m = re.search(pat, msg)
        if m:
            return m.group(1)
    return None


def _emit_did_you_mean(suggestions: tuple[str, ...]) -> None:
    """stderr 输出 'Did you mean: ...'。"""
    if not suggestions:
        return
    if len(suggestions) == 1:
        print(f"Did you mean: {suggestions[0]}?", file=sys.stderr)
    else:
        joined = ", ".join(suggestions)
        print(f"Did you mean: {joined}?", file=sys.stderr)
