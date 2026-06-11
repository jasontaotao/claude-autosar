# AutoC Claude Code 插件

让 Claude Code 在对话中自动委派 AUTOSAR BSW 配置任务给本地 Python CLI。

参考原版项目 [autoc-tool.com](https://www.autoc-tool.com/) 的设计，本仓库是 Python 实现 + Claude Code 插件外壳的复刻。

## 项目结构

```
autoc-cc/
├── pyproject.toml                  # workspace 根元数据
├── .pre-commit-config.yaml         # black / ruff / isort / mypy / bandit
├── .github/
│   ├── workflows/ci.yml            # 5 jobs CI
│   └── PULL_REQUEST_TEMPLATE.md
└── packages/
    ├── autoc/                      # Python CLI 核心（Sprint 0-5）
    │   ├── pyproject.toml
    │   ├── src/autoc/
    │   │   ├── cli/main.py         # argparse 入口
    │   │   ├── core/               # BSW / settings / log 领域
    │   │   ├── adapters/           # EB tresos / DaVinci 适配器
    │   │   └── utils/              # 路径、日志、工具
    │   └── tests/                  # pytest
    └── plugin/                     # Claude Code 插件外壳（Sprint 6-7）
        ├── .claude-plugin/plugin.json
        ├── agents/                # 子 Agent 定义
        ├── commands/              # 斜杠命令
        ├── skills/                # 技能
        └── hooks/                 # 钩子脚本
```

## 快速开始

```bash
git clone <repo-url>
cd autoc-cc
pip install -e packages/autoc[dev]
pre-commit install
autoc --version
```

## 开发

| 操作 | 命令 |
|---|---|
| 单测 | `pytest packages/autoc/tests` |
| Coverage | `pytest --cov=packages/autoc/src/autoc --cov-fail-under=80` |
| Lint | `ruff check packages/autoc/src packages/autoc/tests` |
| Format | `black packages/autoc/src packages/autoc/tests` |
| Import sort | `isort packages/autoc/src packages/autoc/tests` |
| Type check | `mypy --strict packages/autoc/src/autoc` |
| Security | `bandit -r packages/autoc/src/autoc -ll` |

## 进度

- [x] Sprint 0: 仓库骨架
- [ ] Sprint 1: 基础数据模型
- [ ] Sprint 2: 工具适配器（含 MCU 差异化 discover 机制）
- [ ] Sprint 3: ARXML 读写
- [ ] Sprint 4: 会话与日志
- [ ] Sprint 5: CLI + MCP server
- [ ] Sprint 6: 插件外壳
- [ ] Sprint 7: E2E + 文档

详细规划见 `~/.claude/plans/declarative-wiggling-cook.md`。

## License

MIT

## 关联项目

- [autoc-tool.com](https://www.autoc-tool.com/) — 原版（TypeScript + WhyEngineer 网关）
- 本仓库 — Python + Claude Code 插件复刻，目标脱离 WhyEngineer 网关，自托管
