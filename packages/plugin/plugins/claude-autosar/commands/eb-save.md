---
name: eb-save
description: |
  EB tresos 工程改参 + verify + save。底层调用 `claude-autosar eb save`。
  用法：`/claude-autosar:eb-save --module <Module> --param <path>=<value> [--verify] [--generate]`
allowed-tools: Bash
---

# /claude-autosar:eb-save

直接委派到 `claude-autosar eb save` 子命令。

## 用法

```
/claude-autosar:eb-save --module <Module> --param <path>=<value> [--param ...] [--adapter {real,stub}] [--timeout-s <N>] [--verify] [--autocalc]
```

## 必选参数

- `--module`：Mcu / Port / Dio / Can / CanIf / Spi / PduR / EcuC / Com / ...
- `--param`：完整 ECUC 路径 `Mcu/Clock0/ClockFreq=80000000`（可重复）

## 可选参数

- `--adapter real|stub`：用真 EB tresos 还是测试 stub（默认 real）
- `--timeout-s <N>`：tresos_cmd 超时（默认 60s）
- `--verify`：仅校验不保存
- `--autocalc`：保存前触发衍生参数重算
- `--generate`：保存后立即生成代码

## 示例

```
/claude-autosar:eb-save --module Mcu --param Mcu/Clock0/ClockFreq=80000000 --verify
/claude-autosar:eb-save --module Port --param Port/PortPin/Pin0/Dir=OUT --autocalc
/claude-autosar:eb-save --module CanIf --param CanIf/CanIfTxPduCfg_EngineData/CanIfTxPduCanId=0x100 --generate
```

## 行为

1. 解析 `.project` → `TresosProjectContext`（discover BSWMD + 已启用模块）
2. 读 `.prefs/<Module>.xdm` 拿当前值（baseline）
3. 写新值到 `.prefs/<Module>.xdm`
4. `tresos_cmd --validate` 校验（如 `--verify`）
5. `tresos_cmd --autocalc` 触发衍生（如 `--autocalc`）
6. `tresos_cmd --generate` 生成代码（如 `--generate`）
7. **失败回滚**：快照到系统 temp，校验失败立即还原
8. 写 session 到 `~/.claude-autosar/agent/sessions/.current`

## 前置条件

- 当前目录含 `.project`（EB 工程）
- `TRESOS_HOME` 环境变量指向 EB tresos 工具根目录
