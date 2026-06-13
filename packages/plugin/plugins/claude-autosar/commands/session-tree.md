---
name: session-tree
description: |
  会话树管理。list / show / fork 当前 `.current` 标记的会话。
  用法：`/claude-autosar:session-tree <list|show|fork> [session-id]`
allowed-tools: Bash
---

# /claude-autosar:session-tree

查看 / 切换 / fork AutoC 会话。

## 用法

```
/claude-autosar:session-tree list                              # 列所有 session
/claude-autosar:session-tree show                               # 显当前 session 详情
/claude-autosar:session-tree show <session-id>                  # 显指定 session
/claude-autosar:session-tree show latest                        # 显最近 mtime 的 session
/claude-autosar:session-tree fork <session-id>                  # 复制某 session 作为新起点
```

## 行为

### list

```
20260611-143000-abc123  12 entries  14:30:00
20260611-150000-def456   5 entries  15:00:23
20260611-160000-ghi789   8 entries  16:45:01
```

按 mtime 倒序（最近的在最上），用 `claude_autosar/core/session/store.py:resolve_latest_session_id()` 解析。

### show

读取 `.jsonl` 中所有 entry，输出时间线摘要：

```
session: 20260611-143000-abc123
created: 2026-06-11 14:30:00 UTC
entries: 12 (8 tool + 4 user)
modifications: 5 (Mcu=3, Port=2)
verify: 5/5 pass
```

### fork

复制 `<session-id>.jsonl` 到新 ID，原始不变，新 ID 自动设为 `.current`。

## 高级：与 Claude 对话联动

每次 `bsw_write` MCP 调用都自动记入 `.current`。切换 Claude Code 工作区时：

```
/claude-autosar:session-tree show latest     # 看上次改参了啥
/claude-autosar:session-tree fork latest     # 开新分支继续改
```

## 前置条件

- 至少运行过一次 `claude-autosar eb save` 或 `claude-autosar davinci save`（才有 session）
- `~/.claude-autosar/agent/sessions/` 目录存在且可写
