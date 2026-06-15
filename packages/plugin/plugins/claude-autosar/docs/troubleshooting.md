# 排错

## 常见问题

### 1. 启动后看不到 `/claude-autosar:*` 命令

**症状**：`/claude-autosar:eb-save` 显示 "Unknown command"。

**原因**：插件没正确加载。

**排查**：

```bash
# 1. 验证 marketplace
> /plugin marketplace list
# 应有 autoc-marketplace

# 2. 验证插件
> /plugin validate claude-autosar
# 应显示 0 错误

# 3. 验证 commands
ls packages/plugin/plugins/claude-autosar/commands/
# 应有 7 个 .md 文件

# 4. 重启 Claude Code
```

### 2. 改参后 verify 失败

**症状**：

```
| Module | Path            | Old      | New      | Status |
|--------|-----------------|----------|----------|--------|
| Mcu    | Clock0/ClockFreq| 60000000 | 80000000 | failed |

verify: failed (1/2)
  - Mcu.Clock0.ClockSrc: value out of range
```

**原因**：依赖参数未联动。

**解决**：

```bash
# 1. 看完整错误
claude-autosar eb save --module Mcu --param Mcu/Clock0/ClockFreq=80000000 --verify --verbose

# 2. 读 schema 找约束
cat $TRESOS_HOME/plugins/Mcu_TS_T40D34M30I0R0/resources/Mcu_BSWMD.arxml | grep ClockSrc

# 3. 一次性改多个联动参数
/claude-autosar:eb-save --module Mcu --param Mcu/Clock0/ClockFreq=80000000 --param Mcu/Clock0/ClockSrc=2
```

### 3. ARXML guard 拒绝合法文件

**症状**：

```
ARXML guard: ARXML schema invalid: Opening and ending tag mismatch
```

**排查**：

```bash
# 1. 用 xmllint 独立验证
xmllint --noout /path/to/file.arxml

# 2. Python lxml 独立验证
python -c "from lxml import etree; etree.parse('/path/to/file.arxml')"

# 3. 如果 xmllint 通过但 guard 拒绝，可能是 hook 的 XML 编码问题
# 看 hook 源码：packages/plugin/plugins/claude-autosar/hooks/pretooluse_arxml_guard.py
```

**临时绕过**：

```bash
# 把目标文件临时改名（不是 .arxml 后缀），改完再改回
mv /tmp/Mcu.arxml /tmp/Mcu.arxml.bak
# 改 .arxml.bak 文件（hook 不拦截）
# 改完恢复
mv /tmp/Mcu.arxml.bak /tmp/Mcu.arxml
```

> ⚠️ hook matcher 是 `Write|Edit`，**不**拦截 `MultiEdit`（增量多 edit 无法预测最终内容）。
> 改 ARXML 用 `MultiEdit` 是真的绕过，但改完后建议手动跑 `claude-autosar arxml validate` 校验。

### 4. MCP 工具 `bsw_write` 报路径错误

**症状**：

```json
{"success": false, "error": "Module not found: Mcu", "param_index": 0, "field": "module"}
```

**原因**：当前 cwd 不是 EB tresos / DaVinci 工程。

**排查**：

```bash
# 1. 检查 cwd
pwd
ls .project   # EB
ls *.dpa      # DaVinci

# 2. 显式指定 project
bsw_write(module="Mcu", path="Clock0/ClockFreq", value=80000000, project="/path/to/proj")
```

### 5. Session 写入失败

**症状**：

```
session_record_error: [Errno 13] Permission denied
```

**原因**：`~/.claude-autosar/agent/sessions/` 不可写。

**解决**：

```bash
# 修复权限
chmod -R u+w ~/.claude-autosar/agent/sessions/

# 或显式指定 session_dir（env var）
export AUTOC_SESSION_DIR=/tmp/autoc-sessions
```

### 6. `lxml` ImportError

**症状**：

```
ImportError: No module named lxml
```

**解决**：

```bash
pip install lxml
# 或重新装 autoc
pip install -e packages/autoc[dev]
```

ARXML guard hook 缺 lxml 会自动放行（不阻断）但跳过校验；改参仍能工作。

## 调试技巧

### 跑单个 hook 手动测

```bash
# 模拟 PreToolUse 事件
echo '{"tool_name": "Write", "tool_input": {"file_path": "/tmp/Mcu.arxml", "content": "<AR-PACKAGES/>"}}' | \
    python packages/plugin/plugins/claude-autosar/hooks/pretooluse_arxml_guard.py

# 模拟 SessionStart
echo '{"cwd": "/path/to/proj"}' | \
    python packages/plugin/plugins/claude-autosar/hooks/sessionstart_detect_project.py
```

### 跑单元测试

```bash
cd D:\claude_proj2\claude-autosar
python -m pytest packages/plugin/tests/ -v
```

### 看 Claude Code hook 错误日志

```bash
# 启动时加 --debug
claude --plugin-dir ./packages/plugin/plugins/claude-autosar --debug

# 错误信息含 hook 输出
```

## GitHub Issues

未在上面覆盖的问题：在 claude-autosar 仓库开 issue，附：

- 操作系统 + Python 版本
- `claude-autosar --version`
- `pip list | grep autoc`
- 复现命令（脱敏工程路径）
- hook 输出 / Claude Code debug 日志
