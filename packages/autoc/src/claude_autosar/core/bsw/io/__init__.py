"""BSW I/O 子包 — 模块专属 IO 适配器。

Sprint 9.0 引入。``arxml_io``（v1 资产，AUTOSAR ARXML 用）保留不动；
``datamodel2_io``（本子包，Sprint 9.0 新增）专攻 EB tresos DataModel2
.xdm 文件（``http://www.tresos.de/_projects/DataModel2/16/root.xsd``）。

命名空间表（DataModel2 1.0 alias + 2.0 16 root 头）：

  - d:  http://www.tresos.de/_projects/DataModel2/06/data.xsd  (2.0 短 alias)
  - 默认: http://www.tresos.de/_projects/DataModel2/16/root.xsd  (2.0 root)
  - a:  http://www.tresos.de/_projects/DataModel2/16/attribute.xsd
  - v:  http://www.tresos.de/_projects/DataModel2/06/schema.xsd
  - ad: http://www.tresos.de/_projects/DataModel2/08/admindata.xsd
  - cd: http://www.tresos.de/_projects/DataModel2/08/customdata.xsd
  - f:  http://www.tresos.de/_projects/DataModel2/14/formulaexpr.xsd
  - icc: http://www.tresos.de/_projects/DataModel2/08/implconfigclass.xsd
  - mt: http://www.tresos.de/_projects/DataModel2/11/multitest.xsd
  - variant: http://www.tresos.de/_projects/DataModel2/11/variant.xsd

EB 私有 ``<EAS-*>/<EAS-INFO>`` 节点（Infineon / NXP / Renesas 等 vendor
扩展）以 lxml recovery parser 容忍，遇到未知 prefix 的元素跳过 lxml
严格校验，由调用方按需解释。
"""
