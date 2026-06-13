#!/usr/bin/env python3
"""PostToolUse hook: 写完 .prefs/*.xdm 后自动调 `claude-autosar eb verify` 触发 verify。

协议:
  stdin  ← Claude Code 事件 JSON
  stdout → {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "..."}}
            （additionalContext 会被注入 Claude 对话上下文）

触发条件:
  tool_name in {Write, Edit, MultiEdit} AND file_path 匹配 .prefs/<Module>.xdm

行为:
  1. 解析事件，提取 file_path
  2. 用 Path 解析得 module 名（不带扩展）
  3. subprocess.run `claude-autosar eb verify --module <module>`，timeout 25s
  4. 成功：注入"verify 通过"上下文
  5. 失败：注入 verify 错误详情（不阻断，但让 Claude 看到）
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

# .prefs 下的 xdm 是 EB tresos 模块配置文件名格式
# 单字符串（不是 tuple）：Path.parts 是字符串列表，in 查的是 str
_XDM_PARENT_DIR = ".prefs"


def _read_event() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    result: dict[str, Any] = json.loads(raw)
    return result


def _extract_file_path(event: dict[str, Any]) -> str:
    tool_input = event.get("tool_input") or {}
    return str(tool_input.get("file_path", ""))


def _is_xdm_target(file_path: str) -> bool:
    """检查是否 EB tresos .prefs/<Module>.xdm 文件。"""
    if not file_path:
        return False
    p = Path(file_path.replace("\\", "/"))
    parts = p.parts
    # 必须包含 .prefs 段且以 .xdm 结尾
    if _XDM_PARENT_DIR not in parts or not p.name.lower().endswith(".xdm"):
        return False
    # 排除非模块 xdm（用户偏好文件等）
    stem = p.stem  # e.g. "Mcu"
    return not (not stem or stem.startswith("."))


def _module_name_from_xdm(file_path: str) -> str:
    return Path(file_path).stem


def _run_verify(module: str) -> tuple[int, str, str]:
    """执行 `claude-autosar eb verify --module <module>`；返回 (rc, stdout, stderr)。"""
    claude_autosar = shutil.which("claude-autosar")
    if claude_autosar is None:
        return (
            127,
            "",
            "`claude-autosar` CLI 不在 PATH；安装：`pip install -e ../autoc[dev]`",
        )
    try:
        proc = subprocess.run(
            [claude_autosar, "eb", "verify", "--module", module, "--adapter", "stub"],
            capture_output=True,
            text=True,
            timeout=25,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return (124, "", "claude-autosar eb verify 超时（>25s）")
    except OSError as exc:
        return (126, "", f"subprocess 启动失败: {exc}")
    return (proc.returncode, proc.stdout, proc.stderr)


def _output(ctx: str) -> dict[str, Any]:
    if not ctx:
        return {}
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": ctx,
        }
    }


def main() -> int:
    try:
        event = _read_event()
        tool_name = event.get("tool_name", "")
        if tool_name not in {"Write", "Edit"}:
            print(json.dumps({}))
            return 0

        file_path = _extract_file_path(event)
        if not _is_xdm_target(file_path):
            print(json.dumps({}))
            return 0

        module = _module_name_from_xdm(file_path)
        rc, stdout, stderr = _run_verify(module)

        if rc == 0:
            ctx = (
                f"已对 {module}.xdm 跑 `claude-autosar eb verify`（stub adapter）：通过。\n"
                f"如需完整 verify（真 EB tresos），可能耗时 5-10s，属正常。\n{stdout.strip()}"
            )
        elif rc == 127:
            ctx = f"未跑 verify：{stderr}"
        else:
            tail = (stderr or stdout).strip()[-800:]
            ctx = f"`claude-autosar eb verify --module {module}` 失败（rc={rc}）：\n{tail}"

        print(json.dumps(_output(ctx)))
        return 0
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        print(json.dumps({"systemMessage": f"BSW validate hook parse error: {exc}"}))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"systemMessage": f"BSW validate hook unexpected error: {exc}"}))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
