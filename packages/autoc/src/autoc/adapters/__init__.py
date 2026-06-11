"""autoc 工具适配器层。

封装对 EB tresos / DaVinci Configurator 等 AUTOSAR 商业工具的 subprocess 调用，
对外暴露 ``Protocol`` 接口（``adapters.protocol``），便于：
    - 单元测试时用 ``StubAdapter`` 替换
    - 未来接入其它工具时只换实现，不动业务层
"""
