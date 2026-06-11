"""`autoc davinci` 子命令：DaVinci Configurator 工具集成。

Sprint 3 — T3.6。提供 `save` / `verify` 子命令（无 autocalc — DaVinciAdapter Protocol 不含）。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Protocol

from autoc.adapters.davinci import DavinciAdapter
from autoc.adapters.protocol import (
    EcuConfigProjectContext,
    SaveResult,
    VerifyResult,
)
from autoc.adapters.stub import StubDavinciAdapter
from autoc.core.bsw.config import BSWParam, ParamType, ParamValue
from autoc.core.bsw.validator import ModifyRequest, modify_and_verify


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
    result = modify_and_verify(ctx, adapter, req)
    payload = {
        "success": result.success,
        "written_files": [str(p) for p in result.written_files],
        "verify_output": result.verify_output,
        "rolled_back": result.rolled_back,
        "error": result.error,
    }
    # Sprint 4 — 成功路径写入 session（best-effort）。
    if result.success and params:
        from autoc.core.session.recorder import record_bsw_write_batch
        from autoc.core.session.store import SessionStore

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
