#!/usr/bin/env python3
"""PreToolUse hook: block Writes/Edits of syntactically invalid ARXML.

协议:
  stdin  ← Claude Code 事件 JSON
  stdout → 决策 JSON（空对象表示允许；deny 时同时输出新版
          `hookSpecificOutput.permissionDecision` 与旧版顶层 `decision` 双格式向后兼容）

触发条件:
  tool_name in {Write, Edit} AND file_path 后缀为 .arxml
  (MultiEdit 不在本 hook 范围：增量多 edit 无法预测最终内容，单独走 claude-autosar arxml validate)

行为:
  1. 解析 stdin 事件
  2. 提取 tool_name 与 file_path
  3. 如匹配 ARXML：解析新内容（Write 用 content；Edit 用 new_string）
  4. 内容 > 5MB 直接拒绝（防 OOM，让用户走 claude-autosar arxml validate）
  5. lxml 解析失败 → 输出 deny 决策
  6. 解析成功 → 输出 {} 允许
"""

from __future__ import annotations

import json
import sys
from typing import Any

# 仅依赖标准库 + lxml（lxml 是 claude-autosar 项目级依赖）
try:
    from lxml import etree

    _HAS_LXML = True
except ImportError:  # pragma: no cover - 缺依赖时让 hook 优雅退化
    _HAS_LXML = False

# 5MB 硬上限：超过此大小 hook 拒绝（防 OOM），让用户走 `claude-autosar arxml validate`
_MAX_INLINE_BYTES = 5 * 1024 * 1024


def _read_event() -> dict[str, Any]:
    """从 stdin 读取 Claude Code 事件。"""
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    result: dict[str, Any] = json.loads(raw)
    return result


def _is_arxml_target(tool_name: str, file_path: str) -> bool:
    """检查 Write/Edit 是否针对 .arxml 文件。"""
    if tool_name not in {"Write", "Edit"}:
        return False
    if not file_path:
        return False
    return file_path.lower().endswith(".arxml")


def _extract_payload(event: dict[str, Any]) -> tuple[str, str]:
    """从事件中提取 (file_path, new_content)。

    - Write: tool_input.file_path + tool_input.content
    - Edit: tool_input.file_path + tool_input.new_string
    """
    tool_input = event.get("tool_input") or {}
    file_path = tool_input.get("file_path", "")

    if "content" in tool_input:  # Write
        return file_path, str(tool_input.get("content", ""))
    if "new_string" in tool_input:  # Edit
        return file_path, str(tool_input.get("new_string", ""))
    return file_path, ""


def _validate_arxml(content: str) -> str | None:
    """解析 ARXML 字符串；成功返回 None，失败返回错误描述。"""
    if not _HAS_LXML:
        return "lxml not installed — skip ARXML validation"
    if not content.strip():
        return "empty content — not a valid ARXML document"
    if len(content.encode("utf-8")) > _MAX_INLINE_BYTES:
        return (
            f"ARXML too large for inline guard (>{_MAX_INLINE_BYTES // (1024 * 1024)}MB); "
            f"请用 `claude-autosar arxml validate <path>` 验证"
        )
    try:
        etree.fromstring(content.encode("utf-8") if isinstance(content, str) else content)
    except etree.XMLSyntaxError as exc:
        return f"ARXML schema invalid: {exc}"
    return None


def _decision(allow: bool, reason: str = "") -> dict[str, Any]:
    """构造 hook 决策。

    输出两套字段向后兼容：
    - 新版：hookSpecificOutput.permissionDecision = "deny"
    - 旧版：顶层 decision = "block"（部分 Claude Code 版本仍识别）
    """
    if allow:
        return {}
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        },
        "decision": "block",
        "reason": reason,
    }


def main() -> int:
    try:
        event = _read_event()
        tool_name = event.get("tool_name", "")
        file_path, new_content = _extract_payload(event)

        if not _is_arxml_target(tool_name, file_path):
            print(json.dumps(_decision(True)))
            return 0

        err = _validate_arxml(new_content)
        if err and err.startswith("lxml not installed"):
            # 缺依赖：放行 + 警告，不阻断用户
            print(json.dumps({"systemMessage": f"ARXML guard: {err}"}))
            return 0

        if err:
            print(json.dumps(_decision(False, err)))
            return 0

        print(json.dumps(_decision(True)))
        return 0
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        # 解析事件失败：放行 + 警告（不要因 hook 异常阻断 Claude Code）
        print(json.dumps({"systemMessage": f"ARXML guard parse error: {exc}"}))
        return 0
    except Exception as exc:  # noqa: BLE001 - 最后兜底
        print(json.dumps({"systemMessage": f"ARXML guard unexpected error: {exc}"}))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
