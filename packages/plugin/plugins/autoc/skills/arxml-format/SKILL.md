---
name: arxml-format
description: |
  AUTOSAR ARXML 文件读写知识。命名空间、DEFINITION-REF、ECUC 路径、REFERENCE-VALUE、PARAMETER-VALUES。
  触发词：「ARXML」「AR-PACKAGES」「ECUC」「DEFINITION-REF」「REFERENCE-VALUE」「lxml」「schema 校验」。
---

# AUTOSAR ARXML 格式

## 命名空间

| 规范版本 | 命名空间 | schema 位置 |
|----------|---------|-------------|
| R20-11 | `http://autosar.org/schema/r4.0 AUTOSAR_00046.xsd` | AUTOSAR_00046.xsd |
| R21-11 | `http://autosar.org/schema/r4.0 AUTOSAR_00047.xsd` | AUTOSAR_00047.xsd |
| R24-11 | `http://autosar.org/schema/r4.0 AUTOSAR_00048.xsd` | AUTOSAR_00048.xsd |

```xml
<AR-PACKAGES xmlns="http://autosar.org/schema/r4.0"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="http://autosar.org/schema/r4.0 AUTOSAR_00046.xsd">
  ...
</AR-PACKAGES>
```

## 顶层结构

```xml
<AUTOSAR xmlns="..." xsi:schemaLocation="...">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>Ecuc</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-CONFIGURATION-VALUES>
          <SHORT-NAME>Mcu</SHORT-NAME>
          <DEFINITION-REF DEST="ECUC-MODULE-DEF">/AUTOSAR/EcucDefs/Mcu</DEFINITION-REF>
          <CONTAINERS>...</CONTAINERS>
        </ECUC-MODULE-CONFIGURATION-VALUES>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
```

## ECUC 容器与参数

### 容器（Container）

```xml
<CONTAINERS>
  <ECUC-CONTAINER-VALUE>
    <SHORT-NAME>Clock0</SHORT-NAME>
    <DEFINITION-REF DEST="ECUC-PARAM-CONF-CONTAINER-DEF">/AUTOSAR/EcucDefs/Mcu/McuClockSettingConfig</DEFINITION-REF>
    <PARAMETER-VALUES>
      <ECUC-NUMERICAL-PARAM-VALUE>
        <SHORT-NAME>ClockFreq</SHORT-NAME>
        <DEFINITION-REF DEST="ECUC-INTEGER-PARAM-DEF">/AUTOSAR/EcucDefs/Mcu/McuClockSettingConfig/McuClockReferencePointFrequency</DEFINITION-REF>
        <VALUE>80000000</VALUE>
      </ECUC-NUMERICAL-PARAM-VALUE>
    </PARAMETER-VALUES>
  </ECUC-CONTAINER-VALUE>
</CONTAINERS>
```

### 参数类型 DEST 启发式

| DEST 属性 | 类型 | Value 形式 |
|-----------|------|-----------|
| `ECUC-INTEGER-PARAM-DEF` | Integer | `<VALUE>42</VALUE>` |
| `ECUC-FLOAT-PARAM-DEF` | Float | `<VALUE>3.14</VALUE>` |
| `ECUC-BOOLEAN-PARAM-DEF` | Boolean | `<VALUE>true</VALUE>` |
| `ECUC-STRING-PARAM-DEF` | String | `<VALUE>hello</VALUE>` |
| `ECUC-ENUMERATION-PARAM-DEF` | Enum | `<VALUE>ENUM_VALUE</VALUE>` |
| `ECUC-REFERENCE-VALUE` | Reference | `<DEFINITION-REF DEST="...">/path/to/target</DEFINITION-REF>` |

## ECUC 路径

`autoc` 用斜杠分隔路径：`Module/Container/Param` 或 `Module/Container/SubContainer/Param`

- **完整路径**：`Mcu/Clock0/ClockFreq`
- **DEFINITION-REF**：DEST 标识参数类型，autoc 用启发式自动推断
- **容器名 ≠ 参数名**（避免 `Mcu/ClockFreq/ClockFreq` 重复）

## 自动 unwrap wrappers

`<CONTAINERS>` / `<SUB-CONTAINERS>` / `<PARAMETER-VALUES>` / `<REFERENCE-VALUES>` 是元素分组
wrapper，autoc 自动 unwrap 后再处理内部元素，调用方无需感知。

## lxml 读写

### 读

```python
from lxml import etree
tree = etree.parse("Mcu.arxml")
ns = {"ar": "http://autosar.org/schema/r4.0"}
elements = tree.findall(".//ar:ECUC-CONTAINER-VALUE", ns)
```

### 写

```python
# 原子写：先写临时文件 + fsync，再 rename
with tempfile.NamedTemporaryFile("wb", delete=False, dir=path.parent) as tmp:
    tree.write(tmp, xml_declaration=True, encoding="UTF-8", pretty_print=True)
    tmp.flush()
    os.fsync(tmp.fileno())
os.replace(tmp.name, path)  # atomic on POSIX, best-effort on Windows
```

## Schema 校验

```python
# lxml 加载 XSD
schema_doc = etree.parse("AUTOSAR_00046.xsd")
schema = etree.XMLSchema(schema_doc)
if not schema.validate(tree):
    errors = schema.error_log
    for err in errors:
        print(f"Line {err.line}: {err.message}")
```

⚠️ AUTOSAR xsd 体积大（10MB+），lxml 解析慢 — 校验放到 lint 阶段，不在 bsw_read 每次跑。

## 常见陷阱

- **命名空间前缀**：XPath 不带 `ar:` 前缀找不到元素 — 始终声明 `ns = {"ar": "..."}`
- **大小写敏感**：`<VALUE>` 与 `<value>` 不同，AUTOSAR 用大写
- **DEFINITION-REF 路径**：以 `/AUTOSAR/` 开头（不是 `/Vendor/Specific/`）
- **DEST 属性缺失**：DEFINITION-REF 没 `DEST` 时 lxml 不报错，但 autoc 启发式失败
- **编码**：ARXML 必须 UTF-8 声明 `<?xml version="1.0" encoding="UTF-8"?>`
- **CDATA**：含 `<` 或 `&` 的字符串必须 CDATA 包裹

## 跨工具 ARXML 兼容性

- **EB tresos → DaVinci**：从 EB 导出的 EcuExtract.arxml 可被 DaVinci 导入（验证 ARXML 版本）
- **Vector 工具链**：vStudio / CANoe / CANalyzer 都消费 EcuExtract.arxml
- **ARXML Diff**：用 `diff -u` 看结构变化；用 Vector 工具的 vTestStudio 看具体字段
