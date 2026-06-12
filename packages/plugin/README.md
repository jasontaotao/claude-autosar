# AutoC Claude Code 插件

把 `autoc-tool.com` 描述的 `autoc-plugin-cc`（Claude Code 中委托 BSW 配置任务的子 Agent）用 Claude Code 原生插件格式（Markdown + JSON）打包。

## 安装

```bash
# 1. 安装 autoc Python 包（含 CLI + MCP server）
pip install -e ../autoc[dev]

# 2. 把 marketplace 加到 Claude Code
# 在 Claude Code 对话中：
> /plugin marketplace add /path/to/autoc-cc/packages/plugin

# 3. 安装 autoc 插件
> /plugin install autoc

# 4. 验证
> /autoc:bsw-config --module Mcu --param ClockFreq=80000000
```

## 结构

```
packages/plugin/
├── .claude-plugin/
│   └── marketplace.json          # plugin marketplace 索引
└── plugins/autoc/
    ├── .claude-plugin/
    │   └── plugin.json            # plugin manifest
    ├── .mcp.json                  # 声明 autoc MCP server
    ├── agents/
    │   └── bsw-config.md          # autoc:bsw-config 子 Agent
    ├── commands/                  # /autoc:* 7 个命令
    │   ├── bsw-config.md
    │   ├── eb-save.md
    │   ├── davinci-verify.md
    │   ├── arxml-validate.md
    │   ├── session-tree.md
    │   ├── export.md
    │   └── log.md
    ├── skills/                    # 7 个自动加载的知识
    │   ├── bsw-knowledge/
    │   ├── autosar-naming/
    │   ├── eb-tresos/
    │   ├── davinci-configurator/
    │   ├── arxml-format/
    │   ├── dbc-can/
    │   └── change-traceability/
    ├── hooks/                     # PreToolUse / PostToolUse / SessionStart
    │   ├── hooks.json
    │   ├── pretooluse_arxml_guard.py
    │   ├── posttooluse_bsw_validate.py
    │   └── sessionstart_detect_project.py
    └── docs/
        ├── install.md
        ├── troubleshooting.md
        └── dev-guide.md
```

## /autoc:* 命令 ↔ MCP 工具 映射

| 斜杠命令 | 触发方式 | 委派到的 MCP 工具 |
|----------|----------|-------------------|
| `/autoc:bsw-config` | 子 Agent 入口 | `bsw_read` / `bsw_write` / `bsw_verify` / `bsw_autocalc` |
| `/autoc:eb-save` | 直接 | `bsw_read` / `bsw_write`（EB adapter） |
| `/autoc:davinci-verify` | 直接 | `bsw_read` / `bsw_write`（DaVinci adapter） |
| `/autoc:arxml-validate` | 直接 | `arxml_validate` |
| `/autoc:session-tree` | 直接 | `session_list` / `session_show` |
| `/autoc:export` | 直接 | `session_export` |
| `/autoc:log` | 直接 | `log_export` |

**额外 MCP 工具**（无对应斜杠命令，Agent 直接调用）：
`dbc_parse`（DBC 解析 + CanIf 一致性检查）。

子 Agent `autoc:bsw-config` 可直接调 10 个 MCP 工具中任一。

## 验证

```bash
# 启动 Claude Code 并加载插件
cd autoc-cc
claude --plugin-dir ./packages/plugin/plugins/autoc --debug

# 在对话中：
> /plugin validate autoc
> /autoc:bsw-config --module Mcu --param ClockFreq=80000000
```

## 文档

- `docs/install.md` — 安装
- `docs/troubleshooting.md` — 排错
- `docs/dev-guide.md` — 如何加新 skill / command / hook

## 许可

Apache-2.0
