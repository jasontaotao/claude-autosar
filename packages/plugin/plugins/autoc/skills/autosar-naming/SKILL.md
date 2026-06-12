---
name: autosar-naming
description: |
  AUTOSAR 命名规范速查。Module_Function / AUTOSAR_<Module>_<Abbreviation> 前缀 / 容器与参数命名。
  触发词：「命名规范」「MISRA」「MISRA-C」「C99」「Module_Function」「函数前缀」「类型后缀」。
---

# AUTOSAR 命名规范

## C 语言标识符（AUTOSAR 经典）

### 类型命名（强制 MISRA-C:2012）

| 类别 | 后缀 | 示例 |
|------|------|------|
| Struct 类型 | `_t` | `Mcu_ConfigType_t` |
| Enum 类型 | `_t` | `Mcu_ClockSource_t` |
| Typedef 函数指针 | `_fn` | `CanIf_TxConfirmation_fn` |
| 常量宏 | 全大写 + 下划线 | `MAX_CAN_PDU_LENGTH` |

### 函数命名（Module_Function 模式）

```c
/* 形如 <Module>_<Action>[_<Qualifier>] */
Std_ReturnType Can_Write(Can_HwHandleType Hth, const Can_PduType* PduInfo);
void CanIf_TxConfirmation(PduIdType CanTxPduId, Std_ReturnType result);
Adc_ValueGroupType Adc_ReadGroup(Adc_GroupType Group);
```

- **Module 前缀**：3 字母大写（Can, Mcu, Dio, Port, EcuC）
- **Action 动词**：Init, Read, Write, Get, Set, Main, Enable, Disable
- **Qualifier**：可选，表示子类型或后置条件（Start, Stop, Conf）

### 变量命名

| 类别 | 规则 | 示例 |
|------|------|------|
| 全局变量 | `g_` 前缀 + camelCase | `g_systemTickCount` |
| 静态变量 | `s_` 前缀 + camelCase | `s_canIfInitStatus` |
| 局部变量 | camelCase | `clockFreqHz` |
| 常量 | 全大写 + 下划线 | `MCU_DEFAULT_CLOCK_HZ` |
| 指针 | 描述所指对象 | `pduInfoPtr`, `configPtr` |
| 函数指针 | 描述行为 | `TxConfirmation_fn` |

### 单位后缀

```c
uint16_t battery_voltage_mv;    /* millivolts */
int16_t  battery_current_ma;    /* milliamperes */
uint8_t  temperature_celsius;  /* degC */
uint32_t timeout_ms;            /* milliseconds */
uint16_t speed_kmh;             /* km/h */
```

## ARXML 元素命名（XSD 约束）

- `<SHORT-NAME>`：CamelCase 或 PascalCase，首字母大写
- `<LONG-NAME>`：`<L-4 L="EN">Human readable name</L-4>`
- 引用路径：DEST 区分大消息类型（`DEST="ECUC-PARAM-CONF-CONTAINER-DEF"`）
- ShortName 唯一性：容器内所有子元素 ShortName 必须唯一

## EB tresos 模块特定

- **Module Name**：3 字母大写（`Mcu`, `Can`, `Port`）
- **Container Name**：PascalCase（`McuClockSettingConfig`, `CanHardwareObject`）
- **Parameter Name**：camelCase（`McuClockReferencePointFrequency`，但 `ClockFreq` 缩写版可）
- **Vendor Specific**：前缀 `_<Vendor>_<Module>_`（如 `_ST_Mcu_ClockSetting`）

## DaVinci 模块特定

- **DaVinci 项目名**：CamelCase，无下划线（`BswModule`, `CanIf`）
- **BSW 模块引用**：通过 `Base` 节点引用 EB / Vector / ETAS 模块

## 不要做的

- ❌ 不要混用命名风格（snake_case 与 camelCase 混用）
- ❌ 不要省略 Module 前缀（纯函数名 `Write` 在 100 模块工程里冲突）
- ❌ 不要在 Macro 里用 `l`（小写 L）作为变量名
- ❌ 不要用匈牙利命名（AUTOSAR 已废弃）
- ❌ 不要在 ShortName 中用空格或特殊字符（XSD 禁止）
