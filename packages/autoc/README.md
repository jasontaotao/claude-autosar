# autoc - Python CLI 核心

AutoC Python 实现的核心包。提供：

- **CLI 入口**：`autoc` 命令（argparse）
- **BSW 领域模型**：`BSWModule` / `BSWParam` / `ParamValue`（frozen dataclass）
- **AUTOSAR schemas 摘要**：通用 MCAL 模块名映射（不含芯片特定字段）
- **配置合并**：全局/项目三级 JSON deep_merge
- **路径工具**：跨平台 `~/.autoc/` 与 `<cwd>/.autoc/` 解析
- **工具适配器**：EB tresos / DaVinci Configurator（subprocess 包装）
- **MCP server**：暴露给 Claude Code 子 Agent 调用的工具

## 安装

```bash
pip install -e .[dev]
```

## 快速测试

```bash
pytest tests/
```

## 目录结构

```
src/autoc/
├── __init__.py
├── __main__.py                # python -m autoc
├── cli/
│   ├── main.py                # argparse 入口
│   └── commands/              # 子命令实现（Sprint 5）
├── core/
│   ├── bsw/                   # BSW 配置数据模型
│   │   ├── config.py          # BSWModule / BSWParam / ParamValue
│   │   ├── schemas.py         # AUTOSAR MCAL 模块摘要
│   │   └── ...                # Sprint 2+ 扩展
│   ├── settings/              # 配置合并
│   ├── session/               # 会话（Sprint 4）
│   └── log/                   # 改参日志（Sprint 4）
├── adapters/                  # 工具适配器（Sprint 2+）
│   ├── protocol.py            # EBAdapter / DavinciAdapter Protocol
│   ├── tresos.py              # EB tresos subprocess 包装
│   ├── davinci.py             # DaVinci Configurator
│   └── stub.py                # 测试用 stub
└── utils/                     # 工具
    ├── paths.py               # 跨平台路径
    └── ...
```

## 状态

**Sprint 0 + 1** 已完成（仓库骨架 + 基础数据模型）。Sprint 2+ 进行中。

## License

MIT
