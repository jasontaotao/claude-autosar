"""AutoC - AUTOSAR BSW 配置 AI 助手 Python 核心。

AutoC 是一个面向 AUTOSAR BSW 工程师的终端 AI 助手：用自然语言描述
时钟、引脚、模块等配置目标，AI 在工程里完成改参、依赖计算与校验，
并根据结果继续调整，直到配置通过。

本包提供：
    - 命令行入口（cli.main）
    - BSW 领域数据模型（core.bsw）
    - 工具适配器（adapters）
    - 工具与配置（utils, core.settings）
"""

__version__ = "0.4.0"
__all__ = ["__version__"]
