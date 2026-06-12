---
name: bsw-config
description: |
  通用 BSW 改参入口。自动检测 EB tresos / DaVinci 工程，按用户自然语言解析后调用 autoc CLI。
  用法：`/autoc:bsw-config --module <Module> --param <path>=<value> [--param ...]`
allowed-tools: Bash, Read
---

# /autoc:bsw-config

通用 BSW 改参入口。先检测工程类型（EB tresos / DaVinci），再委派到对应子命令。

## 用法

```
/autoc:bsw-config --module <Module> --param <Module>/<Container>/<Param>=<value> [--param ...] [--verify] [--autocalc]
```

## 行为

1. 检测 `<cwd>/.project`（EB tresos）→ 用 `autoc eb save`
2. 检测 `<cwd>/<Project>.dpa`（DaVinci）→ 用 `autoc davinci save`
3. 检测 `<cwd>/*.arxml`（纯 ARXML 工程）→ 用 `autoc arxml validate` + 手动编辑

## 示例

```
/autoc:bsw-config --module Mcu --param Mcu/Clock0/ClockFreq=80000000 --param Mcu/Clock0/ClockSrc=1
/autoc:bsw-config --module Port --param Port/PortPin/Pin0/Dir=OUT --verify
/autoc:bsw-config --module CanIf --param CanIf/CanIfTxPduCfg_EngineData/CanIfTxPduCanId=0x100 --autocalc
```

## 输出

调用 `autoc {tool} save --module <Module> --param ...` 的标准输出：

```
| Module     | Path                       | Old      | New      | Status |
|------------|----------------------------|----------|----------|--------|
| Mcu        | Clock0/ClockFreq           | 60000000 | 80000000 | ok     |
| Mcu        | Clock0/ClockSrc            | 1        | 1        | skip   |

verify: pass  (2/2)
autocalc: changed 1 derived parameter
```

## 前置条件

- `pip install -e ../autoc[dev]` 已装
- 当前目录在 EB / DaVinci / ARXML 工程根目录
