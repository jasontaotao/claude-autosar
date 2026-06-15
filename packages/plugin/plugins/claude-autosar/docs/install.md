# AutoC Claude Code 插件 — 安装

## 1. 前置条件

| 依赖 | 最低版本 | 说明 |
|------|----------|------|
| Python | 3.11+ | `dict \| None`、tomllib 内置、match-case |
| Claude Code | 最新 | 插件支持 0.2.0+ |
| EB tresos | 24.x / 26.x | 仅在改 EB 工程时需要 |
| DaVinci | 5.x | 仅在改 DaVinci 工程时需要 |
| lxml | 4.9+ | ARXML guard hook 需要 |

## 2. 安装 claude-autosar Python 包

```bash
# 在 claude-autosar monorepo 根目录
cd D:\claude_proj2\claude-autosar

# editable install（含 dev deps）
pip install -e packages/autoc[dev]

# 验证
claude-autosar --version
claude-autosar --help
```

应该看到 6 个子命令：config / eb / davinci / session / log / export。

## 3. 加载插件到 Claude Code

### 方式 A：local plugin dir（推荐开发）

```bash
# 直接在仓库根跑
claude --plugin-dir ./packages/plugin/plugins/claude-autosar --debug
```

启动后 `/claude-autosar:bsw-config --module Mcu --param Mcu/Clock0/ClockFreq=80000000` 应能调用。

### 方式 B：marketplace + install

```bash
# 1. 把 marketplace 加到 Claude Code
# 在 Claude Code 对话中：
> /plugin marketplace add /path/to/claude-autosar/packages/plugin

# 2. 安装 claude-autosar 插件
> /plugin install claude-autosar

# 3. 验证
> /plugin validate claude-autosar
> /plugin list
```

应看到：

```
installed plugins:
  - claude-autosar (0.1.0)  ✓ valid
```

## 4. 验证 hooks 触发

### SessionStart

启动 Claude Code 时，看 stdout/log 应有类似：

```
[claude-autosar plugin] SessionStart hook detected project:
- EB tresos 工程（.project）
- 用 `/claude-autosar:eb-save` 改参
```

### PreToolUse（ARXML 写入拦截）

```bash
# 触发 ARXML guard：
> 帮我创建 /tmp/Mcu.arxml，内容是 <AR-PACKAGES><unclosed>
# 应被 block：
> ARXML guard: ARXML schema invalid: ...
```

### PostToolUse（XDM 写入后 verify）

```bash
# 在 EB tresos 工程下：
> 帮我改 .prefs/Mcu.xdm 的 ClockFreq 为 80000000
# 写完后注入：
> 已对 Mcu.xdm 跑 `claude-autosar eb verify`（stub adapter）：通过。
```

## 5. 验证 MCP 工具

在 Claude Code 对话中：

```
> 列出 claude-autosar 暴露的 MCP 工具
# 应看到 10 个：
# bsw_read / bsw_write / bsw_verify / bsw_autocalc
# arxml_validate / dbc_parse
# session_list / session_show / session_export / log_export
```

## 6. 排错

### `claude-autosar` CLI 不在 PATH

```
$ /claude-autosar:eb-save --module Mcu --param Mcu/Clock0/ClockFreq=80000000
未跑 verify：`claude-autosar` CLI 不在 PATH；安装：`pip install -e ../autoc[dev]`
```

**解决**：

```bash
# Windows
pip install -e D:\claude_proj2\claude-autosar\packages\autoc[dev]

# Linux / macOS
pip install -e /path/to/claude-autosar/packages/autoc[dev]

# 验证
which claude-autosar
```

### 加载插件失败

```
$ claude --plugin-dir ./packages/plugin/plugins/claude-autosar
[ERROR] Plugin claude-autosar failed to load: marketplace.json not found
```

**解决**：检查 `packages/plugin/.claude-plugin/marketplace.json` 存在。

### MCP server 启动失败

```
[ERROR] Failed to start MCP server `claude-autosar`.: No module named 'claude_autosar.cli.mcp_server'
```

**解决**：

1. `pip install -e packages/autoc[dev]`
2. 检查 `.mcp.json` 中 `env.PYTHONPATH` 指向 `packages/autoc/src`
3. `python -m claude_autosar.cli.mcp_server` 单独跑应能启动 stdio server

### ARXML guard 误拒合法文件

```
ARXML guard: ARXML schema invalid: ...
```

**可能原因**：

- ARXML 用了不常见 namespace prefix（guard 期望 `ar:`）
- 包含 `<?xml-stylesheet ?>` 处理指令
- lxml 解析严于浏览器

**解决**：临时绕过 — 改用 `Edit` 工具（matcher 包含但 path 解析不同）。
或升级 guard（`packages/plugin/plugins/claude-autosar/hooks/pretooluse_arxml_guard.py`）。

## 7. 卸载

```bash
# 移除 marketplace
> /plugin marketplace remove claude-autosar-marketplace

# 卸载 Python 包
pip uninstall claude-autosar
```
