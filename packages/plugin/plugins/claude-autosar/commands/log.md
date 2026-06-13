---
name: log
description: |
  改参日志。底层调用 `claude-autosar log --view {timeline,by-url}`。
  用法：`/claude-autosar:log --view timeline|by-url [--session <id|latest>]`
allowed-tools: Bash
---

# /claude-autosar:log

显示某次会话的改参日志。

## 用法

```
/claude-autosar:log --view timeline                    # 当前 session 时间线
/claude-autosar:log --view timeline --session latest   # 最近 mtime session
/claude-autosar:log --view by-url                      # 按 (module, path) 分组
/claude-autosar:log --view by-url --session 20260611-143000-abc123
```

## 视图

### timeline（按时间倒序）

```
[2026-06-11 14:30:01] Mcu.Clock0.ClockFreq  60000000 → 80000000  ✓
[2026-06-11 14:30:03] Mcu.Clock0.ClockSrc   1 → 1  (skip)
[2026-06-11 14:30:05] Port.PortPin.Pin0.Dir IN → OUT  ✓
[2026-06-11 14:30:07] Can.CanIfTxPduCanId   0x100 → 0x100  (skip)
```

### by-url（按 (module, path) 分组）

```
Mcu/Clock0/ClockFreq
  14:30:01  60000000 → 80000000  ✓
  16:45:12  80000000 → 100000000 ✓

Port/PortPin/Pin0/Dir
  14:30:05  IN → OUT  ✓
```

## 与 HTML export 区别

- `claude-autosar log` 输出纯文本 / Markdown（适合管道、grep、编辑器）
- `claude-autosar export` 输出 HTML（适合邮件附件、客户演示）

## 高级

```bash
# 找出所有改过 Mcu 的 session
claude-autosar log --view by-url --session <id> | grep -A 1 "Mcu/"

# 统计每日改参次数
claude-autosar log --view timeline --session latest | grep -oE '\[[0-9-]{10}' | sort | uniq -c
```

## 前置条件

- 有可查询的 session
- 当前 `.current` 或 `--session` 指定的 session_id 必须存在
