---
name: eb-tresos
description: |
  EB tresos Studio / AutoCore 工具链知识。`.project` 解析、`tresos_cmd.bat` 调用、BSWMD 发现、`.prefs/*.xdm` 读写、Generate 流程。
  触发词：「tresos」「EB」「AutoCore」「BSWMD」「.project」「.xdm」「tresos_cmd」「Generate」「verify」「autocalc」。
---

# EB tresos 工具链

## 工程结构

```
<project>/
├── .project                    # Eclipse-style project metadata
├── .prefs/                     # 偏好设置（编辑器、Maven 风格）
│   ├── Mcu.xdm                 # 模块配置
│   ├── Port.xdm
│   ├── Can.xdm
│   └── ...
├── <Module>_BSWMD/             # BSW Module Description（每个模块一个目录）
├── <Module>_Im/                # Implementation（生成的代码）
├── <Module>_Sg/                # Static configuration
├── output/                     # 生成产物（.c / .h）
├── Tresos24/                   # 工具自带的本地配置
└── plugins/                    # 工程级 BSWMD 扩展
```

## 关键文件识别

- **`.project`**：必须有，否则不是 EB 工程
- **`.prefs/*.xdm`**：模块配置数据（XML 格式）
- **`<Module>_BSWMD/`**：模块定义（参数 schema、容器层级）
- **`<tool_home>/plugins/`**：工具自带 BSWMD，定义通用模块 + 芯片专属派生模块

## tresos_cmd 调用

### Windows

```bash
# 通过 cmd.exe 包装（不用 shell=True）
cmd.exe /c "<TRESOS_HOME>/bin/tresos_cmd.bat" --generate --project "<project_path>"
cmd.exe /c "<TRESOS_HOME>/bin/tresos_cmd.bat" --validate --project "<project_path>"
cmd.exe /c "<TRESOS_HOME>/bin/tresos_cmd.bat" --autocalc --project "<project_path>"
```

### Linux

```bash
<TRESOS_HOME>/bin/tresos_cmd.sh --generate --project "$project_path"
```

## 改参闭环

`autoc eb save --module <Module> --param <path>=<value>` 内部流程：

1. **discover**：解析 `.project` → Target/Derivate/AutosarVersion + 扫 `<TRESOS_HOME>/plugins/` 列 BSWMD
2. **read**：`autoc/core/bsw/config.py` 解析 `.prefs/<Module>.xdm` → `BSWModule` dataclass
3. **modify**：`BSWModule.with_param(path, value)` 返回新实例
4. **serialize**：`to_ecuc(arxml_path)` 写回 `.prefs/<Module>.xdm`
5. **verify**：`tresos_cmd --validate`（子进程调用）
6. **autocalc**：`tresos_cmd --autocalc`（如未禁用）
7. **generate**：`tresos_cmd --generate`（可选）
8. **失败回滚**：快照存到系统 temp，verify 失败立即还原

## MCU 差异化（关键）

`TresosProjectContext.discover()` 从 `.project` 和 BSWMD 动态发现：

- **S32K3 (NXP)**：NXP 提供 `Mcu` / `Port` / `Dio` 的 BSWMD 派生（`<tool_home>/plugins/Mcu_TS_T40D34M30I0R0/`）
- **TC3xx (Infineon)**：Infineon 提供 `Mcu_TC3xx` / `Port_TC3xx`（`<tool_home>/plugins/Mcu_TS_T16D27M10I0R0/`）
- **RH850 (Renesas)**：Renesas 提供 `Mcu_RH850` / `Port_RH850`（`<tool_home>/plugins/Mcu_RH850_RZN_*/`）

**adapater 代码不预知任何具体芯片字段**，所有字段从 BSWMD 动态加载。

## 常见错误

- **工具路径错**：`TRESOS_HOME` 环境变量未设或设错 — 检查 `bin/tresos_cmd.bat` 存在
- **plugin 缺失**：工程引用的 BSWMD 不在 `<tool_home>/plugins/` — 单独安装 NXP / Infineon / Renesas plugin pack
- **variant 不匹配**：工程用 S32K3 的 `.prefs` 但 `target` 是 TC3xx — 改 `.project` 的 `<entry>` 值
- **编码错乱**：Windows .bat 默认 cp1252，配置里有中文会乱码 — subprocess 显式 `cp1252` 解码
- **生成超时**：大型工程（100+ 模块）generate 超 60s — 加 `--timeout-s 300`

## 工具版本兼容

- EB tresos Studio 24.x / 26.x：API 稳定
- AutoCore 8.x：模块路径增加 `/_Ac8/` 段
- 旧版（17.x 之前）：BSWMD 在 `<tool_home>/eclipse/plugins/com.<vendor>.<module>_<version>/`

## EB tresos → autoc CLI 映射

| tresos_cmd | autoc CLI | 说明 |
|------------|-----------|------|
| `--validate` | `autoc eb verify` | 仅校验，不改文件 |
| `--autocalc` | `autoc eb autocalc` | 触发衍生参数重算 |
| `--generate` | `autoc eb save --generate` | 改 + 生成 |
| `--target=...` | 自动从 `.project` 读 | discover() 提取 |
| `--plugin-path=...` | `TRESOS_HOME` 环境变量 | 工具根目录 |
