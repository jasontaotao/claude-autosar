"""`autoc eb` 子命令：EB tresos 工具集成。

Sprint 3 — T3.5。提供 `save` / `verify` / `autocalc` 三个子命令。
- save: 改 + verify + 失败回滚 + 成功 save（核心闭环）
- verify: 仅 verify（不改值）
- autocalc: 触发 AutoCalc（无 module 参数语义，命令级用 module 作为目标标识）
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Protocol

from autoc.adapters.protocol import (
    CalcResult,
    EcuConfigProjectContext,
    SaveResult,
    VerifyResult,
)
from autoc.adapters.stub import StubTresosAdapter
from autoc.adapters.tresos import TresosAdapter
from autoc.core.bsw.config import BSWParam, ParamType, ParamValue
from autoc.core.bsw.path_resolver import BSWPathResolver
from autoc.core.bsw.validator import ModifyRequest, modify_and_verify


class _HasVerifySaveAutocalc(Protocol):
    """eb 命令需要的最小 adapter surface。"""

    def discover(self, project_path: Path, tool_home: Path) -> EcuConfigProjectContext: ...
    def verify(self, ctx: EcuConfigProjectContext, module: str | None) -> VerifyResult: ...
    def save(self, ctx: EcuConfigProjectContext, module: str | None) -> SaveResult: ...
    def autocalc(self, ctx: EcuConfigProjectContext) -> CalcResult: ...


def register(subparsers: Any) -> None:
    """挂载到主 argparse subparsers。"""
    p = subparsers.add_parser("eb", help="EB tresos 工具子命令")
    sub = p.add_subparsers(dest="eb_command", required=True)

    for cmd in ("save", "verify", "autocalc"):
        sp = sub.add_parser(cmd)
        sp.add_argument("--project", type=Path, default=Path.cwd())
        sp.add_argument("--module", type=str, required=True)
        sp.add_argument("--tresos-home", type=Path, default=None)
        if cmd == "save":
            sp.add_argument(
                "--param",
                action="append",
                default=[],
                help="key=value，可重复，如 ClockFreq=80000000",
            )
        sp.add_argument("--adapter", choices=["real", "stub"], default="real")


def build_parser() -> argparse.ArgumentParser:
    """为单元测试提供独立 parser（含 eb 子命令）。"""
    parser = argparse.ArgumentParser(prog="autoc")
    sub = parser.add_subparsers(dest="command", required=False)
    register(sub)
    return parser


def _build_adapter(args: argparse.Namespace) -> _HasVerifySaveAutocalc:
    """根据 args.adapter 选 real 或 stub。"""
    if args.adapter == "stub":
        return StubTresosAdapter(discover_response=_fake_ctx_for_stub(args))
    return TresosAdapter()


def _fake_ctx_for_stub(args: argparse.Namespace) -> EcuConfigProjectContext:
    """StubTresosAdapter 必须有 discover_response；这里用最简 ctx 填充。"""
    tresos_home = args.tresos_home or (args.project / "fake-tresos")
    tresos_home.mkdir(exist_ok=True)
    return EcuConfigProjectContext(
        project_path=args.project,
        tool_home=tresos_home,
        target="UNKNOWN",
        derivate="UNKNOWN",
        pn="UNKNOWN",
        autosar_version="0.0.0",
        enabled_modules=(args.module,),
        available_plugins=(),
    )


def _parse_params(raw_list: list[str], module: str) -> list[BSWParam]:
    """把 --param path=value 列表转成 BSWParam list（type 默认 INTEGER）。

    path 接受以下两种格式：
      - 相对路径（不含 module 前缀）："Container/ParamName" → "Mcu/Container/ParamName"
      - 完整路径（以 module 名开头）："Mcu/Container/ParamName" → 原样
    """
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
    adapter_override: _HasVerifySaveAutocalc | None = None,
) -> int:
    """执行子命令。返回 exit code（0 成功 / 1 失败）。

    adapter_override：测试用，绕过真实 subprocess。
    """
    adapter = adapter_override if adapter_override is not None else _build_adapter(args)

    # 1. discover（用 args.tresos_home 或默认 project/tresos_home）
    tresos_home = args.tresos_home or (args.project / "tresos_home")
    tresos_home.mkdir(exist_ok=True)
    try:
        ctx = adapter.discover(args.project, tresos_home)
    except Exception as e:
        print(json.dumps({"success": False, "error": f"discover failed: {e}"}))
        return 1

    # 2. 分发
    if args.eb_command == "save":
        return _run_save(args, adapter, ctx)
    if args.eb_command == "verify":
        return _run_verify(adapter, ctx, args.module)
    if args.eb_command == "autocalc":
        return _run_autocalc(adapter, ctx, args.module)

    print(json.dumps({"success": False, "error": f"unknown subcommand {args.eb_command!r}"}))
    return 1


def _run_save(
    args: argparse.Namespace,
    adapter: _HasVerifySaveAutocalc,
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
    # Sprint 4 — 成功路径写入 session（best-effort，写失败不阻塞 save）。
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
    adapter: _HasVerifySaveAutocalc,
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


def _run_autocalc(
    adapter: _HasVerifySaveAutocalc,
    ctx: EcuConfigProjectContext,
    module: str,
) -> int:
    result = adapter.autocalc(ctx)
    print(
        json.dumps(
            {
                "success": result.success,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "module": module,
            }
        )
    )
    return 0 if result.success else 1


# ---------------------------------------------------------------------------
# T8.E.4 — typo 防御 helpers
# ---------------------------------------------------------------------------


def _maybe_typo_suggestion(
    exc: BaseException,
    ctx: EcuConfigProjectContext,
    module: str,
) -> tuple[str, ...]:
    """如果异常来自 `ecuc_set_value` 找不到 path，调 BSWPathResolver 给候选。

    链式判别：走 __cause__ / __context__ / 直接 exc 自身（covers
    `raise X from Y` 模式 + `raise X` in try/except + 直接 raise）。
    """
    from autoc.core.bsw.ecuc import load_module

    # 找目标 .xdm / .arxml（与 validator._locate_module_file 逻辑相同，
    # 这里再写一遍避免 import private）
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

    # 提取 err_path：exception str 里 "Path 'X'" 或 "path 'X'" 或 "X not in tree"
    err_path = _extract_err_path(str(exc))
    if err_path is None:
        return ()

    return BSWPathResolver.suggest_for_ecuc_set_value_error(err_path, doc)


def _extract_err_path(msg: str) -> str | None:
    """从 ValueError msg 提 path。

    ecuc_set_value / validator 可能的 msg 形态：
      - "Path 'X' not in ECUCDocument for module 'M'"
      - "Failed to set value for path 'X': ..."
      - "Path 'X' not found in tree ..."
    """
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
    """stderr 输出 "Did you mean: <s0>?"（契约 4 / plan T8.E.4 验收要求）。"""
    if not suggestions:
        return
    if len(suggestions) == 1:
        print(f"Did you mean: {suggestions[0]}?", file=sys.stderr)
    else:
        joined = ", ".join(suggestions)
        print(f"Did you mean: {joined}?", file=sys.stderr)
