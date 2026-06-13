---
name: dbc-can
description: |
  CAN DBC 文件与 AUTOSAR CanIf / CanTp 配置的对照。DBC 解析（cantools）、CanIf TxPduId 映射、CanTp 寻址格式、signal 一致性检查。
  触发词：「DBC」「cantools」「CanIf」「CanTp」「信号」「报文」「Pdu」「message ID」「multiplexor」。
---

# DBC 与 AUTOSAR Can 对照

## DBC 文件结构

```
VERSION "1.0"

NS_ :
    NS_DESC_
    CM_
    BA_DEF_
    BA_
    VAL_
    CAT_DEF_
    CAT_
    FILTER
    BA_DEF_DEF_
    EV_DATA_
    ENVVAR_DATA_
    SGTYPE_
    SGTYPE_VAL_
    BA_DEF_SGTYPE_
    BA_SGTYPE_
    SIG_TYPE_REF_
    VAL_TABLE_
    SIG_GROUP_
    SIG_VALTYPE_
    SIGTYPE_VALTYPE_

BS_:

BU_: ECU1 ECU2

BO_ <CAN_ID> <MessageName>: <DLC> <Transmitter>
 SG_ <SignalName> : <StartBit>|<Length>@<ByteOrder><ValueType> (<Factor>,<Offset>) [<Min>|<Max>] "<Unit>" <Receivers>
```

## DBC 解析（cantools）

```python
import cantools
db = cantools.load_file("network.dbc")
for msg in db.messages:
    print(f"  0x{msg.frame_id:X}  {msg.name}  DLC={msg.length}  signals={len(msg.signals)}")
    for sig in msg.signals:
        print(f"    {sig.name}  start={sig.start}  length={sig.length}  factor={sig.scale}  offset={sig.offset}")
```

⚠️ **cantools 41.x 重命名**：`start_bit` → `start`，`signal_size` → `length`

## CanIf Tx/Rx PDU 配置（AUTOSAR）

### TxPduId 映射

```xml
<ECUC-CONTAINER-VALUE>
  <SHORT-NAME>CanIfTxPduCfg_EngineData</SHORT-NAME>
  <DEFINITION-REF DEST="ECUC-PARAM-CONF-CONTAINER-DEF">/AUTOSAR/EcucDefs/CanIf/CanIfTxPduConfig</DEFINITION-REF>
  <PARAMETER-VALUES>
    <ECUC-NUMERICAL-PARAM-VALUE>
      <SHORT-NAME>CanIfTxPduId</SHORT-NAME>
      <VALUE>0</VALUE>  <!-- PDU handle，autoc 内部用 -->
    </ECUC-NUMERICAL-PARAM-VALUE>
    <ECUC-NUMERICAL-PARAM-VALUE>
      <SHORT-NAME>CanIfTxPduCanId</SHORT-NAME>
      <VALUE>256</VALUE>  <!-- 0x100，与 DBC 中 BO_ 256 EngineData 一致 -->
    </ECUC-NUMERICAL-PARAM-VALUE>
    <ECUC-NUMERICAL-PARAM-VALUE>
      <SHORT-NAME>CanIfTxPduDlc</SHORT-NAME>
      <VALUE>8</VALUE>
    </ECUC-NUMERICAL-PARAM-VALUE>
  </PARAMETER-VALUES>
</ECUC-CONTAINER-VALUE>
```

### 信号 → 字节布局

DBC 描述信号的 bit 位置、长度、缩放；AUTOSAR CanIf 描述 PDU（8 字节块）；
Com 模块负责把 signal 打包到 PDU 字节里。

`autoc dbc_parse` 输出：

```python
{
  "messages": [
    {
      "id": 0x100,
      "name": "EngineData",
      "length": 8,
      "signals": [
        {"name": "EngineSpeed", "start": 0, "length": 16, "scale": 0.25, "offset": 0, "unit": "rpm"},
        ...
      ]
    }
  ]
}
```

## CanTp 寻址格式

| 格式 | 适用 | N_TA 地址 |
|------|------|-----------|
| Standard | 普通 CAN | 11-bit CAN ID |
| Extended | 29-bit CAN ID | 29-bit CAN ID |
| NormalFixed | ISO 15765-2 标准 | 第 1 字节 |
| Mixed | ISO 15765-2 混合 | 11-bit + 8-bit |
| Enhanced | 行业扩展 | 29-bit + 8/16/32-bit |

`autoc dbc_parse` 返回 `addressing_format` 字段。

## 一致性检查

`autoc dbc_parse + bsw_read(CanIf, "")` 对照：

| 检查项 | 失败处理 |
|--------|----------|
| DBC 中所有 message ID 都在 CanIf.CanIfTxPduCanId | 报告缺失 |
| CanIf 中所有 TxPdu 在 DBC 中存在 | 报告冗余 |
| signal length × count 超过 DLC | 报告溢出 |
| multiplexor 信号未声明 | 报告缺 multiplexer |
| signal factor / offset 不一致 | 报告数值漂移 |

## 工程实践

- **DBC 是真相源**：先维护 DBC，再生成 CanIf 配置
- **EcuExtract**：从 ECU 配置导出 DBC 片段（Vector 工具支持）
- **CANdelaStudio / PREEvision**：DBC 上游工具，定义完整网络后再分配到 ECU
- **dbc_sync**：CI 钩子定期跑 `autoc dbc_parse` + `bsw_read(CanIf, "")` 确认一致性

## 参考

- ISO 11898-1 (CAN 2.0A/B)
- ISO 15765-2 (CAN TP / Diagnostics)
- Vector CANdb++ 文档
- cantools Python 包（41.x）
