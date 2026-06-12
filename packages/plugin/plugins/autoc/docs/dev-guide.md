# 开发指南

如何扩展 AutoC Claude Code 插件：加新 skill、command、hook、agent。

## 目录布局

```
packages/plugin/plugins/autoc/
├── .claude-plugin/
│   └── plugin.json          # manifest
├── .mcp.json                # MCP server 配置
├── agents/                  # 子 Agent（sub-agent dispatch）
├── commands/                # /autoc:xxx 斜杠命令
├── skills/                  # 自动加载的领域知识
├── hooks/                   # 事件触发脚本
│   ├── hooks.json
│   └── *.py
└── docs/                    # 文档
```

## 加新 skill

skill 是按描述（description）自动加载的领域知识。`SKILL.md` 单文件即可。

```bash
mkdir -p packages/plugin/plugins/autoc/skills/my-new-skill
```

创建 `SKILL.md`：

```markdown
---
name: my-new-skill
description: |
  描述：何时触发？包含触发关键词。
  触发词：「foo」「bar」「baz」
---

# My New Skill

## 核心概念
...

## 用法
...
```

**约束**：

- `name`：kebab-case
- `description`：≥ 50 字，含具体触发词
- frontmatter 完整（YAML）
- 内容中文（业务）+ 英文（API / 协议字段）

## 加新 command

command 是用户可调用的 `/autoc:xxx` 斜杠命令。

```bash
# 创建文件
touch packages/plugin/plugins/autoc/commands/my-new.md
```

```markdown
---
description: |
  一句话功能描述 + 触发场景。
allowed-tools: Bash, Read
---

# /autoc:my-new

详细说明。

## 用法
\`\`\`
/autoc:my-new --arg1 <value>
\`\`\`

## 行为
1. ...

## 示例
\`\`\`
/autoc:my-new --arg1 foo
\`\`\`
```

**约束**：

- `description` ≥ 20 字
- `allowed-tools` 列出该命令用得到的工具
- 命令名格式 `kebab-case.md`（不带 autoc: 前缀）
- 内部命令靠 Bash 委派到 `autoc` Python CLI

## 加新 hook

hook 是事件触发的 Python 脚本。三种事件：

- `PreToolUse`：工具执行前（可 block / 注入上下文）
- `PostToolUse`：工具执行后（仅注入上下文）
- `SessionStart`：会话开始时（注入项目上下文）

### 步骤 1：写脚本

```python
#!/usr/bin/env python3
"""My new hook: 简述功能。

协议：
  stdin  ← 事件 JSON
  stdout → 决策 JSON
"""
from __future__ import annotations

import json
import sys
from typing import Any


def _read_event() -> dict[str, Any]:
    raw = sys.stdin.read()
    return json.loads(raw) if raw.strip() else {}


def main() -> int:
    try:
        event = _read_event()
        # ... 你的逻辑 ...
        # 允许：输出 {} 或空
        # 拒绝：输出 {"hookSpecificOutput": {"permissionDecision": "deny", "permissionDecisionReason": "..."}}
        # 注入：输出 {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "..."}}
        print(json.dumps({}))
        return 0
    except Exception as exc:  # noqa: BLE001
        # hook 异常必须放行（不要阻断 Claude Code）
        print(json.dumps({"systemMessage": f"my-hook error: {exc}"}))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

### 步骤 2：注册到 hooks.json

```json
{
  "PreToolUse": [
    {
      "matcher": "Write|Edit",
      "hooks": [
        {
          "type": "command",
          "command": "python \"${CLAUDE_PLUGIN_ROOT}/hooks/my_new_hook.py\"",
          "timeout": 10
        }
      ]
    }
  ]
}
```

### 步骤 3：写单元测试

```python
# packages/plugin/tests/test_my_new_hook.py
from __future__ import annotations
import io
import json
import sys
from pathlib import Path
from typing import Any
from unittest import mock

# 加 hooks 目录到 sys.path
HOOKS_DIR = Path(__file__).resolve().parent.parent / "plugins" / "autoc" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import my_new_hook  # type: ignore[import-not-found]  # noqa: E402


def _run_hook_with_stdin(hook_main, event: dict[str, Any]) -> dict[str, Any]:
    stdin_payload = json.dumps(event)
    captured: dict[str, Any] = {}

    def _fake_main() -> int:
        sys.stdin = io.StringIO(stdin_payload)  # type: ignore[assignment]
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf  # type: ignore[assignment]
        try:
            rc = hook_main()
        finally:
            sys.stdout = old  # type: ignore[assignment]
            sys.stdin = sys.__stdin__  # type: ignore[assignment]
        captured["_rc"] = rc
        captured["_stdout"] = buf.getvalue()
        return rc

    _fake_main()
    raw = captured["_stdout"].strip()
    return json.loads(raw) if raw else {}


def test_happy_path() -> None:
    event = {"tool_name": "Write", "tool_input": {"file_path": "/tmp/foo"}}
    out = _run_hook_with_stdin(my_new_hook.main, event)
    assert out == {}


def test_malformed_event_does_not_crash() -> None:
    out = _run_hook_with_stdin(my_new_hook.main, {"garbage": True})
    assert out == {} or "systemMessage" in out
```

### 步骤 4：跑检查

```bash
# ruff
ruff check packages/plugin/plugins/autoc/hooks/my_new_hook.py packages/plugin/tests/test_my_new_hook.py

# mypy strict
mypy --strict packages/plugin/plugins/autoc/hooks/my_new_hook.py

# black + isort
black packages/plugin/plugins/autoc/hooks/my_new_hook.py packages/plugin/tests/test_my_new_hook.py
isort packages/plugin/plugins/autoc/hooks/my_new_hook.py packages/plugin/tests/test_my_new_hook.py

# pytest
python -m pytest packages/plugin/tests/test_my_new_hook.py -v
```

## 加新 agent

agent 是 Claude Code 可委派的子 Agent。

```bash
touch packages/plugin/plugins/autoc/agents/my-new.md
```

```markdown
---
name: my-new
description: |
  描述：什么场景用？触发关键词。
  触发词：「do X」「handle Y」
tools: Read, Grep, Glob, Bash
model: sonnet
---

# my-new Agent

## 工作流程
1. ...

## 触发示例
用户说 → 你的动作
...
```

**约束**：

- `name`：kebab-case
- `tools`：只列用得到的
- `model`：haiku / sonnet / opus

## 加新 MCP 工具

MCP 工具是给 Claude Code 子 Agent 调用的 Python 函数。在 `packages/autoc/src/autoc/cli/mcp_server.py` 加：

```python
@mcp.tool(description="新工具简述")
def my_new_tool(arg1: str, arg2: int = 0) -> dict[str, Any]:
    """详细 docstring。
    
    Args:
        arg1: 描述
        arg2: 描述（默认 0）
    
    Returns:
        {"success": True, "data": ...} 成功
        {"success": False, "error": "..."} 失败
    """
    try:
        # ... 业务逻辑 ...
        return {"success": True, "data": result}
    except (OSError, ValueError) as exc:
        return {"success": False, "error": str(exc)}
```

写单元测试 `packages/autoc/tests/unit/test_mcp_server.py`：

```python
def test_my_new_tool_happy_path() -> None:
    result = mcp_server.my_new_tool("foo", 42)
    assert result["success"] is True
    assert "data" in result


def test_my_new_tool_handles_error() -> None:
    result = mcp_server.my_new_tool("bad", -1)
    assert result["success"] is False
    assert "error" in result
```

## 端到端测试

```bash
# 1. 装 autoc 包
pip install -e packages/autoc[dev]

# 2. 启动 Claude Code
claude --plugin-dir ./packages/plugin/plugins/autoc --debug

# 3. 在 Claude Code 对话中
> /plugin validate autoc
> /autoc:my-new --arg1 foo
> 帮我改 Mcu 时钟到 80MHz
```

## 提交规范

```
<type>(<scope>): <description>

<optional body>
```

类型：feat / fix / refactor / docs / test / chore

示例：

```
feat(plugin): add arxml-validate command

- 新增 commands/arxml-validate.md
- 复用 mcp__autoc__arxml_validate 工具
- 前置 ARXML guard hook 自动校验
```

```
fix(hooks): fix .xdm path detection on Windows

- 之前用 tuple 比较 Path.parts 导致 always-true
- 改成单字符串 .prefs in parts
- 加 test_windows_path_separator
```

## 调试技巧

```bash
# 跑单个 hook 手动测
echo '{"tool_name": "Write", "tool_input": {"file_path": "/tmp/Mcu.arxml", "content": "<x>"}}' | \
    python packages/plugin/plugins/autoc/hooks/pretooluse_arxml_guard.py

# 看 Claude Code hook 错误
claude --plugin-dir ./packages/plugin/plugins/autoc --debug 2>&1 | grep -i hook
```

## 贡献前 checklist

- [ ] `ruff check` 通过
- [ ] `mypy --strict` 通过
- [ ] `black --check` 通过
- [ ] `isort --check` 通过
- [ ] `pytest packages/plugin/tests/` 全过
- [ ] 现有 autoc 测试没破：`pytest packages/autoc/tests/`
- [ ] 新文件加进 `packages/plugin/README.md` 结构图
