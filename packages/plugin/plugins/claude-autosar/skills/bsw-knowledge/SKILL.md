---
name: bsw-knowledge
description: |
  AUTOSAR 经典平台 BSW（Basic Software）模块知识。当用户讨论 Mcu/Port/Dio/Can/CanIf/Spi/PduR/EcuC/Com 任一模块时自动加载。
  触发词：「BSW 模块」「Mcu 时钟」「Port 引脚」「Can 报文」「Spi 通道」「PduR 路由」「EcuC 休眠」「Com 信号」。
---

# BSW 模块知识

## AUTOSAR 分层

```
应用软件层 (ASW)
  ↓ RTE
BSW 服务层 (Services Layer)   — Os, Com, PduR, EcuM
  ↓
BSW ECU 抽象层 (ECU Abstraction) — Mcu, Port, Dio, Adc, Pwm, Icu
  ↓
BSW 驱动层 (MCAL / Drivers)    — 直接操作硬件寄存器
  ↓
微控制器硬件
```

## 核心模块速查

| 模块 | 职责 | 典型参数 |
|------|------|----------|
| **Mcu** | 时钟、PLL、复位、低功耗模式 | `ClockFreq`, `ClockSrc`, `RunMode` |
| **Port** | 引脚复用、方向、上下拉、驱动强度 | `Pin0/Dir`, `Pin0/Idr`, `Pin0/Pcr` |
| **Dio** | 数字 IO 读写（Port 之上的位级） | `Channel`, `Level` |
| **Can** | CAN 控制器：波特率、Mailbox | `Baudrate`, `CanHwChannel` |
| **CanIf** | Can ↔ 上层（CanTp/CanNm/PduR）路由 | `CanIfTxPduId`, `CanIfRxPduId` |
| **CanTp** | CAN 传输层（多帧、分段、重传） | `CanTpTxId`, `CanTpRxId`, `AddressingFormat` |
| **Spi** | SPI 主/从设备、波特率、CS | `SpiChannelId`, `SpiBaudrate` |
| **PduR** | PDU 路由（If ↔ Tp ↔ Com） | `PduRSrcPduId`, `PduRDestPduId` |
| **Com** | 信号打包 / 拆包、发送属性 | `ComSignalId`, `ComSignalLength` |
| **EcuC** | Ecu 配置总集（休眠、唤醒、PDU 容器） | `EcuC/EcucPduCollection` |
| **Nm** | 网络管理（协同休眠） | `NmChannelId`, `NmBusType` |
| **Wdg** | 看门狗（驱动 + 接口） | `WdgMode`, `WdgTimeout` |

## 改参流程（行业标准）

1. **读** — `bsw_read(module, path)` 取得当前值
2. **改** — `bsw_write(module, path, value)`（自动 verify + 失败回滚）
3. **触发衍生** — `bsw_autocalc([module])` 重新计算衍生参数
4. **生成代码** — 在 EB tresos / DaVinci 中 "Generate" / "Save"
5. **回归** — 编译 + 单测 + 集成测试

## 常见错误模式

- **路径重复**：`Mcu/ClockFreq/ClockFreq`（容器名 == 参数名）— 实际应为 `Mcu/Clock0/ClockFreq`
- **范围越界**：ClockFreq 给 999999999 触发「物理约束违反」
- **依赖未更新**：改了 CanIf RxPduId 没改 CanTp Routing
- **单位混淆**：ClockFreq 单位是 Hz，配置工具常显示 MHz — 转换 6 个零
- **Variant 错配**：编译时选的 MCU 变体与配置不匹配 → Save 时 EB tresos 报错

## 参考

- AUTOSAR 经典平台规范 4.4 / R21-11
- ISO 26262-6 软件层要求
- EB tresos / Vector DaVinci 工具用户手册
