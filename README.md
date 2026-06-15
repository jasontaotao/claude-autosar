# claude-autosar · Claude Code 插件

[![PyPI](https://img.shields.io/pypi/v/claude-autosar)](https://pypi.org/project/claude-autosar/)
[![Python](https://img.shields.io/pypi/pyversions/claude-autosar)](https://pypi.org/project/claude-autosar/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-1331%20passed-success)](https://github.com/jasontaotao/claude-autosar)
[![Coverage](https://img.shields.io/badge/coverage-85.86%25-yellowgreen)](https://github.com/jasontaotao/claude-autosar)

`autoc-tool.com` 的 Python 复刻 + Claude Code 插件外壳。在 Claude Code 对话中委派 **EB tresos / DaVinci Configurator / ARXML** 改参、verify、lint、模板 diff 与留痕任务给本地 Python CLI 子 Agent。

> **v0.3.0 已发布到 PyPI** （2026-06-14）— `pip install claude-autosar` 一行搞定。

---

## 五大特性（Sprint 9.2–9.5）

| 模块 | 简述 |
|---|---|
| **M1-T 双格式模板 diff + apply** | `.arxml`（AUTOSAR r4.x）+ `.xdm`（EB DataModel2）**各自独立 dataclass**；`arxml-apply-template` / `xdm-apply-template` CLI + MCP，ARXML byte-identity 100% |
| **M3 verify 增强** | EB `tresos_cmd verify` stdout/stderr 结构化解析（6 类正则 + severity） — `bsw_verify` 加 4 个 v2 path 参数 |
| **M4 lint 10 规则** | `LintRule` Protocol + Runner（异常隔离覆盖 `__next__()`）+ 10 规则（8 arxml + 2 xdm），自动按 namespace 过滤 |
| **双格式平级 IO** | dispatcher 按根 xmlns 自动路由（AUTOSAR r4.0–4.8 + DataModel2 2.0/1.0）；响应带 `format` 字段；**不互转**（plan v2 §2.1 锁定） |
| **15 个 MCP 工具** | bsw_* + arxml_* + xdm_* + session/log/apply-template — Claude Code 子 Agent 直调；ISO 21434 信任边界（project 必须在 cwd 内） |

---

## 三行装好

```bash
pip install claude-autosar                              # 装包（PyPI 0.3.0）
claude --plugin-dir ./packages/plugin/plugins/claude-autosar --debug   # 启动 CC 挂插件
> /claude-autosar:bsw-config --module Mcu --param Mcu/Clock0/ClockFreq=80000000   # 改参
```

更多安装方式（editable / 离线 wheel）+ 完整排错见 [`install.html`](./install.html) 和 [`docs/getting-started.html`](./docs/getting-started.html)。

---

## 仓库结构

```
claude-autosar/                                # monorepo 根（GitHub 仓库名 = claude-autosar）
├── pyproject.toml                          # workspace 元数据
├── README.md / CHANGELOG.md / PROGRESS.md  # 本文件 + 变更 + 进度
├── install.html                            # v0.3.0 详细安装 + 排错参考
├── docs/
│   └── getting-started.html                # v0.3.0 快速上手
├── packages/
│   ├── autoc/                              # Python CLI 核心（PyPI 包 claude-autosar）
│   │   ├── pyproject.toml                  #   name=claude-autosar, version=0.3.0
│   │   ├── src/claude_autosar/             #   13 CLI 子命令 + FastMCP server
│   │   │   ├── cli/{main,mcp_server}.py    #   argparse + FastMCP stdio
│   │   │   ├── cli/commands/               #   13 subcommands
│   │   │   ├── core/bsw/                   #   arxml_io / datamodel2_io / dispatcher
│   │   │   │                               #   inspector / lint / templates / verify
│   │   │   ├── core/{session,log,settings}/
│   │   │   └── adapters/                   #   tresos / davinci / stub (Protocol)
│   │   └── tests/                          #   1331 个 pytest
│   └── plugin/                             # Claude Code 插件外壳
│       └── plugins/claude-autosar/         #   7 slash + 1 agent + 7 skills + 3 hooks
└── tresos_home/                            # 离线 EB tresos 工程样本
```

---

## 13 个 CLI 子命令

| | 子命令 | 用途 |
|---|---|---|
| **改参** | `eb` | EB tresos `save / verify / autocalc`（`--adapter {real,stub}`） |
| | `davinci` | DaVinci Configurator `save / verify`（无 autocalc） |
| **模板** | `arxml-apply-template` | M1-T：ARXML 端 diff + apply |
| | `xdm-apply-template` | M1-T：XDM 端 diff + apply |
| **检查** | `arxml-inspect` / `xdm-inspect` / `bsw-inspect` | 提取 IPdu/Signal/ECUC 关键参数 → JSON + HTML 报告 |
| | `bsw-verify` | M3：EB tresos verify 结构化解析 |
| | `lint` | M4：10 条规则扫 + HTML 报告 |
| **会话语** | `session` | list / show / fork |
| | `log` | timeline / by-url 改参日志 |
| | `export` | 自包含 HTML 导出 |
| **其他** | `init` | 从 EB 工程生成 `.autoc/settings.json`（v2 路径：TRESOS_HOME / MCAL_VENDOR_HOME / CHIP_DERIVATIVE） |

```bash
$ claude-autosar --version
claude-autosar 0.3.0
$ claude-autosar --help
usage: claude-autosar [-h] [--version] [--project PROJECT] [--verbose] [--no-color]
         {eb,davinci,session,log,export,init,arxml-inspect,xdm-inspect,
          bsw-inspect,lint,bsw-verify,
          arxml-apply-template,xdm-apply-template} ...
```

---

## 15 个 MCP 工具

| 类别 | 工具 |
|---|---|
| **BSW 改参** | `bsw_read` / `bsw_write` / `bsw_verify` (M3) / `bsw_autocalc` |
| **ARXML** | `arxml_validate` / `arxml_inspect` / `arxml_apply_template` (M1-T) |
| **XDM** | `xdm_inspect` / `xdm_apply_template` (M1-T) |
| **联动** | `bsw_inspect`（同时 inspect arxml + xdm + verify section） |
| **DBC** | `dbc_parse`（cantools 解析 + CanIf 信号一致性） |
| **Session** | `session_list` / `session_show` / `session_export` |
| **Log** | `log_export`（`view ∈ {"timeline","by-url"}`） |

错误统一 `{"success": false, "error": "...", "field": "...", "param_index": N}`，LLM 友好定位。

---

## 7 个斜杠命令

```bash
/claude-autosar:bsw-config       # 子 Agent 入口（最常用，自动检测工程类型）
/claude-autosar:eb-save          # EB tresos 改参 + verify + 写 session
/claude-autosar:davinci-verify   # DaVinci 改参 + verify（无 autocalc）
/claude-autosar:arxml-validate   # ARXML / XDM schema 校验
/claude-autosar:session-tree     # 会话 fork 树 list / show / fork
/claude-autosar:export           # session → 自包含 HTML
/claude-autosar:log              # 改参日志 timeline / by-url
```

---

## 10 条 Lint 规则

| Namespace | 规则 ID | 检测 |
|---|---|---|
| arxml | `COM-AP-001` | ComSignal > 8 byte 经典 CAN 失败 |
| arxml | `COM-AP-002` | E2E Profile 缺失 |
| arxml | `CanIf-AP-007` | 软件全开 + 硬件全关 CPU 风暴 |
| arxml | `CanIf-AP-008` | CAN-FD length mismatch |
| arxml | `ECUM-AP-001` | RunRequest 死锁 |
| arxml | `ECUM-AP-003` | POSTBUILD variant 缺失 |
| arxml | `GEN-AP-002` | BswM 自循环 |
| arxml | `NM-AP-001` | CanNm 报文不在 ComM 引用 |
| xdm | `DEM-AP-001` | Flash 越界 |
| xdm | `DEM-AP-004` | Snapshot > 255 byte |

Runner 按文件 suffix 自动过滤（`applies_to: ClassVar[str]` tag），缺字段 skip 返 0 violation — **不误报**优先。

---

## 验证状态（5-stage verification 全过）

| 阶段 | 结果 |
|---|---|
| `ruff check` | ✓ 0 issue |
| `mypy --strict` | ✓ 0 issue |
| `pytest` | ✓ **1331 passed**（Sprint 8.E + 9.x 累计） |
| ARXML / XDM byte-identity | ✓ 100% / ≥99% |
| 端到端（用户工程 `D:/claude_proj2/src/S32K148_EAS_EB_3399A/`） | ✓ `xdm-inspect Can.xdm` / `arxml-inspect Com_Com.arxml` 67 IPdu / 双格式 apply-template dry-run |
| **Coverage** | **85.86%**（推到 Sprint 8.E.1 plan 补测目标 ≥90%） |

---

## 关键设计

- **MCU 差异化解耦** — `TresosAdapter.discover()` 数据驱动；同一段代码处理 S32K3 / TC3xx / RH850，**无 if/else 分支**
- **不可变数据** — 所有公开 dataclass `frozen=True`；`with_X()` / `set_value()` 返回新实例
- **JSONL append-only** — session 存储；`os.fsync` Windows 强持久
- **trust boundary** — MCP 工具的 `project` / `tresos_home` 入参白名单（ISO 21434）
- **lint 异常隔离** — `LintRunner` try 提到 `for v in yielded:` 包含 `__next__()`，单条 rule 抛错不影响其它 rule

---

## 文档导航

| 文档 | 内容 |
|---|---|
| [`docs/getting-started.html`](./docs/getting-started.html) | v0.3.0 快速上手（13 节：TL;DR / 系统要求 / 装包 / 插件 / 验证 / 第一次使用 / 命令 / CLI / MCP / Lint / 架构 / FAQ / 卸载） |
| [`install.html`](./install.html) | v0.3.0 详细安装 + 排错参考（4 装法 + 3 加载 + 14 节 FAQ） |
| [`CHANGELOG.md`](./CHANGELOG.md) | 完整变更日志（Keep a Changelog 格式） |
| [`PROGRESS.md`](./PROGRESS.md) | Sprint 0–9.5 进度交接文档 |
| [PyPI: claude-autosar](https://pypi.org/project/claude-autosar/) | 安装包（wheel + sdist + py.typed） |

---

## 与 autoc-tool.com 的关系

- [autoc-tool.com](https://www.autoc-tool.com/) — 原版（TypeScript + WhyEngineer 网关）
- 本仓库 — Python + Claude Code 插件复刻，**目标脱离 WhyEngineer 网关，自托管**；MCP stdio 直连，子 Agent 在用户本地跑

---

## License

MIT © 2026 AutoC Contributors
