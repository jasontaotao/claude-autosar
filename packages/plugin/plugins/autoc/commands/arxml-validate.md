---
name: arxml-validate
description: |
  ARXML 文件校验（lxml + XSD schema）。底层调用 `autoc arxml validate`。
  用法：`/autoc:arxml-validate <path-to-arxml> [--xsd <path-to-xsd>]`
allowed-tools: Bash
---

# /autoc:arxml-validate

校验 ARXML 文件的语法 + 命名空间 + schema。

## 用法

```
/autoc:arxml-validate <path-to-arxml>
/autoc:arxml-validate <path-to-arxml> --xsd <path-to-xsd>
/autoc:arxml-validate <path-to-arxml> --strict
```

## 必选参数

- `<path-to-arxml>`：要校验的 ARXML 文件（相对或绝对路径）

## 可选参数

- `--xsd <path>`：用指定 XSD schema 校验（不指定则按 `<ar:AR-PACKAGES>` 命名空间自动选 R20-11 / R21-11 / R24-11）
- `--strict`：任何 warning 都失败（默认只报 error）
- `--show-line`：在错误信息中显示行号

## 示例

```
/autoc:arxml-validate Mcu.arxml
/autoc:arxml-validate EcuExtract.arxml --xsd AUTOSAR_00046.xsd
/autoc:arxml-validate Bswmd_Can.arxml --strict --show-line
```

## 输出

```
[OK]  Mcu.arxml  (12453 lines, 3.2 MB)
  0 errors, 0 warnings
  schema: R20-11
```

或失败时：

```
[FAIL]  Mcu.arxml  (12453 lines, 3.2 MB)
  3 errors, 1 warning
  schema: R20-11

  Line 142: cvc-complex-type.4: Attribute 'VALUE' must appear on element 'ECUC-NUMERICAL-PARAM-VALUE'
  Line 203: cvc-datatype-valid.1: 'abc' is not a valid value for 'integer'
  Line 308: UndeclaredPrefix: Cannot find prefix 'xyz'
  Line 401 (warning): undefined ECUC-PARAM-CONF-CONTAINER-DEF reference
```

## 前置条件

- ARXML 文件可读
- XSD schema 可访问（默认通过命名空间推断；离线时需显式 `--xsd`）
