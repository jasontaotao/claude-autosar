#!/usr/bin/env python3
"""SessionStart hook: 检测 cwd 下 EB / DaVinci / ARXML 工程，注入上下文。

协议:
  stdin  ← SessionStart 事件（含 cwd）
  stdout → {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "..."}}

行为:
  1. 解析 cwd（默认 os.getcwd()）
  2. 检测 .project（EB tresos）/ *.dpa（DaVinci）/ *.arxml（纯 ARXML）
  3. 拼一段项目摘要 + autoc 用法提示，注入 Claude 上下文
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any

_PROJECT_FILES = (".project", "project.xml", ".project.xml")
_DAVINCI_EXT = ".dpa"
_ARXML_EXT = ".arxml"


def _read_event() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        result: dict[str, Any] = json.loads(raw)
        return result
    except json.JSONDecodeError:
        return {}


def _resolve_cwd(event: dict[str, Any]) -> Path:
    """优先用 event.cwd，否则用环境变量 PWD，最后用 os.getcwd()。"""
    cwd = event.get("cwd") or os.environ.get("PWD") or os.getcwd()
    return Path(cwd).resolve()


def _detect_eb(cwd: Path) -> str | None:
    for name in _PROJECT_FILES:
        if (cwd / name).is_file():
            return name
    return None


def _detect_davinci(cwd: Path) -> str | None:
    for entry in cwd.iterdir():
        if entry.is_file() and entry.suffix.lower() == _DAVINCI_EXT:
            return entry.name
    return None


def _detect_arxml(cwd: Path) -> list[str]:
    return sorted(
        entry.name
        for entry in cwd.iterdir()
        if entry.is_file() and entry.suffix.lower() == _ARXML_EXT
    )


def _build_context(cwd: Path) -> str:
    parts: list[str] = [f"AutoC 插件已加载（cwd = {cwd}）。"]
    eb = _detect_eb(cwd)
    davinci = _detect_davinci(cwd)
    arxmls = _detect_arxml(cwd)

    if eb:
        parts.append(
            f"- 检测到 EB tresos 工程（{eb}）。用 `/autoc:eb-save` 或 "
            f"`autoc eb save --module <Module> --param <path>=<value>` 改参。"
        )
    if davinci:
        parts.append(
            f"- 检测到 DaVinci 工程（{davinci}）。用 `/autoc:davinci-verify` 或 "
            f"`autoc davinci save --module <Module> --param <path>=<value>` 改参。"
        )
    if arxmls:
        top = ", ".join(arxmls[:5])
        more = "" if len(arxmls) <= 5 else f"（外加 {len(arxmls) - 5} 个）"
        parts.append(
            f"- 检测到 {len(arxmls)} 个 ARXML：{top} {more}。"
            f"用 `/autoc:arxml-validate <path>` 校验。"
        )
    if not (eb or davinci or arxmls):
        parts.append(
            "- 未检测到 EB / DaVinci / ARXML 工程。如需手动指定 ARXML："
            "`/autoc:arxml-validate <path>`。"
        )

    parts.append(
        "\n- 子 Agent `autoc:bsw-config` 可处理自然语言改参请求。"
        "\n- 所有改参自动写入 `~/.autoc/agent/sessions/.current`；"
        "用 `/autoc:session-tree show latest` 查看历史。"
        "\n- 当前 session 导出 HTML：`/autoc:export --output report.html`。"
    )
    return "\n".join(parts)


def main() -> int:
    try:
        event = _read_event()
        cwd = _resolve_cwd(event)
        if not cwd.is_dir():
            print(json.dumps({}))
            return 0
        ctx = _build_context(cwd)
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": ctx,
                    }
                }
            )
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"systemMessage": f"SessionStart hook unexpected error: {exc}"}))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
