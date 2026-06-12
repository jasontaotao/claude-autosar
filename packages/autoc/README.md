# autoc — AUTOSAR BSW AI 配置助手（Python 核心）

`autoc` 是 AutoC Claude Code 插件的 Python 核心包。对 EB tresos / DaVinci
Configurator 的 BSW 配置做读、改、验证、归档、导出，与 Claude Code 通过
MCP 协议对接。

## 特性

- **不可变数据模型**：`BSWModule` / `BSWParam` / `ParamValue`（`frozen=True`，
  `with_X()` 返回新实例）
- **MCU 差异化解耦**：`TresosAdapter.discover()` 数据驱动 — 同一段代码
  处理 S32K3 / TC3xx / RH850，**无 if/else 分支**
- **协议层抽象**：`typing.Protocol + @runtime_checkable`；测试用
  `StubTresosAdapter` / `StubDavinciAdapter`，CI 不依赖商业工具
- **ARXML 读写**：lxml 自写 `ARXMLDocument` / ECUC 解析（reference chain
  + type 启发式），无 `pyecarxml` 等不确定外部依赖
- **会话 / 改参日志 / 导出**：JSONL append-only 存储 + 不可变树 + fork
  + 自包含 HTML 导出（XSS 白名单 + 三色 callout）
- **MCP server**：FastMCP 10 工具（`bsw_read` / `bsw_write` / `bsw_verify` /
  `bsw_autocalc` / `arxml_validate` / `dbc_parse` / `session_list` /
  `session_show` / `session_export` / `log_export`）
- **路径防御**：MCP 工具的 `project` / `tresos_home` 入参在白名单
  `_ALLOWED_PROJECT_ROOTS`（cwd）之内（ISO 21434 信任边界）

## 安装

```bash
pip install autoc
```

开发模式（含 dev 依赖）：

```bash
pip install -e ".[dev]"
```

## 快速上手

CLI 入口 `autoc`（由 `pyproject.toml` `[project.scripts]` 提供）：

```bash
autoc --version
autoc --help

# 改 EB tresos 工程下 Mcu 模块的两个参数
autoc eb save \
  --project /path/to/tresos/project \
  --module Mcu \
  --param "Mcu/ClockConfiguration/McuClockSettingConfig_0/McuClockReferencePointFrequency=80000000" \
  --param "Mcu/SecConfig/SecurityAttributeConfig_0/McuSecRam=ENABLE"
```

MCP 集成：在 Claude Code 子 Agent 里直接调用 `bsw_write` / `arxml_validate` /
`session_export` 等工具，路径同 `autoc` 子命令。

## 项目状态

| 维度 | 值 |
|---|---|
| 测试 | **467 passed**（autoc 442 + plugin 25）|
| Coverage | **90.07%**（mcp_server 47%→91%，+44pp）|
| 静态检查 | ruff / isort / black / mypy strict 全清 |
| 安全 | bandit -ll 0 H/M（7 low 全是 subprocess 模式 + 1 path-traversal 防御）；pip-audit 0 H/M（autoc 运行时无漏洞，3 个 transitive CVE 已记录在 SECURITY.md）|
| Python | 3.11 / 3.12 / 3.13 |
| License | MIT |

完整 sprint-by-sprint 进度交接见 [PROGRESS.md](https://github.com/autoc-cc/autoc-cc/blob/main/PROGRESS.md)。

## 目录结构

```
src/autoc/
├── __init__.py / __main__.py
├── cli/
│   ├── main.py                # argparse 入口（dispatch 表 + 全局 flags）
│   ├── repl_skin.py           # Rich 主题 + ReplSkin 业务 API
│   ├── mcp_server.py          # FastMCP 10 工具
│   └── commands/              # eb / davinci / session / log / export
├── core/
│   ├── bsw/                   # BSW 数据模型 + ARXML/ECUC 解析 + 验证
│   ├── settings/              # 配置合并（<cwd>/.autoc/ + ~/.autoc/agent/）
│   ├── session/               # JSONL store + 不可变树 + recorder + exporter
│   └── log/                   # 改参 changelog
├── adapters/                  # EB tresos / DaVinci / stub
└── utils/                     # 跨平台路径
```

## 配套插件

`autoc` 是 Python 核心；要让 Claude Code 在 `~/.autoc/agent/` 工程里直接
调它，需要装
[autoc-cc 插件](https://github.com/autoc-cc/autoc-cc/tree/main/packages/plugin)：
7 个 `/autoc:*` 斜杠命令、7 个 skill、3 个 hook（ARXML guard / BSW
validate / SessionStart 项目检测）、1 个 agent（bsw-config）、`.mcp.json`
直接挂到本包。

## License

MIT — 详见 [LICENSE](https://github.com/autoc-cc/autoc-cc/blob/main/packages/autoc/LICENSE)
