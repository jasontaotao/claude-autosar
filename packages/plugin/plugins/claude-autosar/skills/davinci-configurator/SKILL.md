---
name: davinci-configurator
description: |
  Vector DaVinci Configurator 工具链知识。`.dpa` 工程、`DVCfgCmd.exe` 命令行、ARXML 导入/导出、BSW 模块配置。
  触发词：「DaVinci」「Vector」「DVCfgCmd」「.dpa」「AUTOSAR Builder」「DaVinci Developer」。
---

# Vector DaVinci Configurator

## 工程结构

```
<project>/
├── <Project>.dpa              # DaVinci Project Archive（必须）
├── <Project>.dvp              # 旧版工程（dpa = 压缩包，dvp = 目录）
├── Bsw/                       # BSW 模块配置
│   ├── Com/
│   ├── PduR/
│   ├── CanIf/
│   └── ...
├── EcuC/                      # ECU 配置
│   └── EcucPduCollection
├── arxml/                     # 导入/导出的 AUTOSAR XML
│   ├── Bswmd_*.arxml
│   ├── EcuExtract.arxml
│   └── ...
└── system_design/             # 通信矩阵 / 信号定义
```

## 关键文件识别

- **`<Project>.dpa`**：ZIP 包，含完整工程（git 友好，diff 清晰）
- **`<Project>.dvp`**：目录形式（旧版 DaVinci）
- **`system_design/`**：COM/PDU/Signal 通信设计
- **`EcuC/`**：ECU 提取配置

## DVCfgCmd 调用

### Windows

```bash
# 通过 cmd.exe 包装
cmd.exe /c "<DAVINCI_HOME>/DVCfgCmd.exe" /Verify /Project:"<project_path>/<Project>.dpa" /Exit
cmd.exe /c "<DAVINCI_HOME>/DVCfgCmd.exe" /Save /Project:"<project_path>/<Project>.dpa" /Exit
cmd.exe /c "<DAVINCI_HOME>/DVCfgCmd.exe" /AutoCalc /Project:"<project_path>/<Project>.dpa" /Exit
```

### DaVinci vs EB tresos 差异

| 操作 | DaVinci | EB tresos |
|------|---------|-----------|
| Verify | `DVCfgCmd /Verify` | `tresos_cmd --validate` |
| Save | `DVCfgCmd /Save` | `tresos_cmd --generate` |
| AutoCalc | `DVCfgCmd /AutoCalc` | `tresos_cmd --autocalc` |
| 配置格式 | ARXML | XDM + ARXML |
| 配置文件 | `.dpa` / `.dvp` | `.project` + `.prefs/*.xdm` |
| 输出 | 生成到 arxml/ | 生成到 output/ |

## 改参闭环

`claude-autosar davinci save --module <Module> --param <path>=<value>` 内部流程：

1. **discover**：解析 `<Project>.dpa` → 找到 BSW 模块位置
2. **read**：`autoc/core/bsw/config.py` 解析 ARXML → `BSWModule` dataclass
3. **modify**：`BSWModule.with_param(path, value)` 返回新实例
4. **serialize**：`to_ecuc(arxml_path)` 写回
5. **verify**：`DVCfgCmd /Verify`（子进程调用）
6. **save**：`DVCfgCmd /Save`（成功才保存）
7. **失败回滚**：快照在系统 temp，verify 失败立即还原

## DaVinci 特有概念

- **AUTOSAR Version**：R20-11 / R21-11 / R24-11（导出 ARXML 命名空间）
- **EcuExtract**：完整 ECU 配置导出的 ARXML（导入到别的工具）
- **System Extract**：系统级（多 ECU）配置 ARXML
- **Bswmd**：BSW Module Description ARXML（导入 BSWMD 才能配置模块）
- **Composition**：组合 SWC（DaVinci Developer 概念，Configurator 不涉及）

## Wrote: 模式

`DVCfgCmd /Save` 输出含 `Wrote: <path>` 行，autoc 用正则解析填 `written_files`：

```
Verifying project...OK
Saving...Wrote: Bsw\Com\Com_PduGroupRouting.arxml
Saving...Wrote: EcuC\EcucPduCollection.arxml
Save completed
```

⚠️ 正则模式 `\bWrote:\s*(.+?)$` 严格匹配 `Wrote: ` 前缀，避免误匹配自然语言中的 "wrote/saved"。

## 常见错误

- **DAVINCI_HOME 未设**：在 `~/.bashrc` 或 Windows env 加 `DAVINCI_HOME=C:\Vector\DaVinci_5_20_27`
- **.dpa 锁定**：DaVinci GUI 开着时 DVCfgCmd /Save 失败 — 关闭 GUI
- **版本不匹配**：DaVinci Developer 生成的 system extract 与 Configurator 版本不兼容
- **Bswmd 缺失**：模块是「只读」状态，配置灰色 — 导入对应 vendor 的 Bswmd ARXML
- **路径含空格**：`/Project:"C:\My Project\foo.dpa"` 一定加引号

## 工具版本

- DaVinci Configurator 5.x（当前主流）
- 旧版 4.x / 3.x 不支持 ARXML 4.4+
- DaVinci Developer（图形 SWC 设计，Configurator 仅 BSW）

## DaVinci → claude-autosar CLI 映射

| DVCfgCmd | claude-autosar CLI | 说明 |
|----------|-----------|------|
| `/Verify` | `claude-autosar davinci verify` | 仅校验 |
| `/Save` | `claude-autosar davinci save` | 校验 + 保存 |
| `/AutoCalc` | ❌ 无（`DVCfgCmd /Save` 自带） | Save 时自动 |
| `/Project:` | 自动从 `.dpa` 路径读 | discover() 提取 |
| `/Exit` | 必加 | 调用后立即退出，不阻塞 |
