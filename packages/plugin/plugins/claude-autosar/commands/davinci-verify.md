---
name: davinci-verify
description: |
  DaVinci Configurator 工程校验。底层调用 `claude-autosar davinci verify` 或 `claude-autosar davinci save`。
  用法：`/claude-autosar:davinci-verify --module <Module> [--save]`
allowed-tools: Bash
---

# /claude-autosar:davinci-verify

直接委派到 `claude-autosar davinci` 子命令。

## 用法

```
/claude-autosar:davinci-verify --module <Module>            # 仅 verify
/claude-autosar:davinci-verify --module <Module> --save     # verify + save
/claude-autosar:davinci-verify --module <Module> --param <path>=<value>  # 改参 + verify
```

## 行为

1. 解析 `<Project>.dpa` → 发现 BSW 模块位置
2. 读 ARXML 配置（baseline）
3. 如有 `--param` → 写新值
4. `DVCfgCmd.exe /Verify` 校验
5. 如有 `--save` → `DVCfgCmd.exe /Save` 保存
6. **失败回滚**：快照在系统 temp，verify 失败立即还原

## 示例

```
/claude-autosar:davinci-verify --module Com
/claude-autosar:davinci-verify --module Com --save
/claude-autosar:davinci-verify --module Com --param Com/ComConfig/ComTimeBase=0.01 --save
```

## 常见错误

- `DVCfgCmd.exe` 不在 PATH → 检查 `DAVINCI_HOME` 环境变量
- `.dpa` 被 DaVinci GUI 占用 → 关闭 DaVinci Configurator GUI
- Bswmd 未导入 → 模块灰显，无法改参
- ARXML 命名空间不匹配（用 R20-11 配置但工程是 R21-11）

## 前置条件

- 当前目录含 `<Project>.dpa`（DaVinci 工程）
- `DAVINCI_HOME` 环境变量指向 Vector DaVinci 工具根目录
