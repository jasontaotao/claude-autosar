"""`autoc bsw-verify` 子命令：MCP `bsw_verify` tool 的 CLI 入口。

Sprint 9.3 — T9.3-β。设计要点：

* CLI 通过 import 调 MCP tool 函数本身（不重复实现业务逻辑），跟
  现有 `eb` / `davinci` 一致。
* 新增 4 个 v2 path 参数：``--chip-derivative`` / ``--mcal-vendor`` /
  ``--mcal-vendor-home``（与 ``load_v2_paths`` 4 级优先级对齐）。
* ``--as-json`` 走完整 TresosVerifyReport 序列化（默认走轻量 dict，
  含 success / module / returncode / report 摘要）。
* 异常 → stderr JSON + return 1。

参考：
* `packages/autoc/src/claude_autosar/cli/mcp_server.py:435-490` — 现有
  `bsw_verify` 函数（被本命令 import）。
* `packages/autoc/src/claude_autosar/cli/commands/eb.py` — CLI 4 段样板
  （register / run / argparse / JSON output）。
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

def register(subparsers: Any) -> None:
    """挂载到主 argparse subparsers。"""
    p = subparsers.add_parser(
        "bsw-verify",
        help="BSW 模块 verify（只校验不改值；MCP bsw_verify tool 的 CLI 入口）",
    )
    p.add_argument(
        "--project",
        type=str,
        default=".",
        help="工程根目录路径字符串（默认：当前工作目录）",
    )
    p.add_argument(
        "--module",
        type=str,
        required=True,
        help="BSW 模块名（如 Mcu）",
    )
    p.add_argument(
        "--tresos-home",
        type=str,
        default=None,
        help="EB tresos 安装根目录（覆盖 settings.json / 环境变量 / 探测）",
    )
    p.add_argument(
        "--chip-derivative",
        type=str,
        default=None,
        dest="chip_derivative",
        help="芯片派生（如 Mcu_s32k148_lqfp176.epd）",
    )
    p.add_argument(
        "--mcal-vendor",
        type=str,
        default=None,
        help="MCAL 厂商（nxp / st / ti / renesas / infineon）",
    )
    p.add_argument(
        "--mcal-vendor-home",
        type=str,
        default=None,
        help="MCAL 厂商 AUTOSAR 包根目录",
    )
    p.add_argument(
        "--as-json",
        action="store_true",
        default=False,
        help="输出 TresosVerifyReport 完整 JSON（默认轻量 dict）",
    )


def build_parser() -> argparse.ArgumentParser:
    """为单元测试提供独立 parser（含 bsw-verify 子命令）。"""
    parser = argparse.ArgumentParser(prog="autoc")
    sub = parser.add_subparsers(dest="command", required=False)
    register(sub)
    return parser


def run(args: argparse.Namespace) -> int:
    """执行 bsw-verify 子命令。返回 exit code（0 成功 / 1 失败）。"""
    from claude_autosar.cli.mcp_server import bsw_verify as _mcp_bsw_verify

    try:
        result = _mcp_bsw_verify(
            args.module,
            project=args.project,
            tresos_home=args.tresos_home,
            chip_derivative=args.chip_derivative,
            mcal_vendor=args.mcal_vendor,
            mcal_vendor_home=args.mcal_vendor_home,
            as_json=args.as_json,
        )
    except Exception as e:
        # 异常 → stderr JSON + return 1（与 eb / davinci CLI 一致）
        print(
            json.dumps({"success": False, "error": f"{type(e).__name__}: {e}"}),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result))
    return 0 if result.get("success") else 1
