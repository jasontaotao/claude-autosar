"""AUTOSAR 经典平台 BSW 模块 schema 摘要。

重要设计：本文件**只提供通用 AUTOSAR 模块名**的元数据（类别、典型 vendor、
常见配置组），不预知任何具体芯片 / 工程特有的参数定义。

具体芯片（S32K3 / TC3xx / RH850 等）的字段、取值范围、约束，由 EB tresos
或 DaVinci Configurator 工程自带的 BSWMD 决定，autoc 通过
``adapters.tresos.TresosAdapter.discover()`` 在运行时动态发现。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModuleSchema:
    """模块 schema 摘要（不含具体参数定义）。"""

    name: str
    category: str  # "MCAL" | "ECU_ABSTRACTION" | "SERVICE" | "CDD"
    typical_vendor: str
    description: str
    common_config_groups: tuple[str, ...] = ()
    """常见配置组名（不绑定具体字段名）。"""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("name must be non-empty")
        valid_categories = ("MCAL", "ECU_ABSTRACTION", "SERVICE", "CDD")
        if self.category not in valid_categories:
            raise ValueError(f"category must be one of {valid_categories}, got {self.category!r}")


# AUTOSAR 经典平台常见 MCAL 模块
MCAL_MODULES: dict[str, ModuleSchema] = {
    "Mcu": ModuleSchema(
        name="Mcu",
        category="MCAL",
        typical_vendor="EB tresos / Vector / Renesas",
        description="微控制器单元驱动：时钟、复位、PLL、模式切换",
        common_config_groups=("McuClockSetting", "McuResetConfig", "McuModeSetting"),
    ),
    "Port": ModuleSchema(
        name="Port",
        category="MCAL",
        typical_vendor="EB tresos / Vector / Renesas",
        description="端口引脚配置：方向、模式、驱动强度、上下拉",
        common_config_groups=("PortConfigSet", "PortPin"),
    ),
    "Dio": ModuleSchema(
        name="Dio",
        category="MCAL",
        typical_vendor="EB tresos / Vector / Renesas",
        description="数字 IO 通道读写",
        common_config_groups=("DioConfig", "DioChannel"),
    ),
    "Can": ModuleSchema(
        name="Can",
        category="MCAL",
        typical_vendor="EB tresos / Vector / Bosch",
        description="CAN 控制器驱动：波特率、滤波器、硬件对象",
        common_config_groups=("CanConfigSet", "CanController", "CanHardwareObject"),
    ),
    "Spi": ModuleSchema(
        name="Spi",
        category="MCAL",
        typical_vendor="EB tresos / Vector / Renesas",
        description="SPI 主/从驱动：通道、Job、Sequence",
        common_config_groups=("SpiConfigSet", "SpiChannel", "SpiJob", "SpiSequence"),
    ),
}


# AUTOSAR 经典平台 ECU 抽象层与服务层
ECU_ABSTRACTION_MODULES: dict[str, ModuleSchema] = {
    "CanIf": ModuleSchema(
        name="CanIf",
        category="ECU_ABSTRACTION",
        typical_vendor="EB tresos / Vector",
        description="CAN 接口层：上层与 CAN 驱动解耦",
        common_config_groups=("CanIfConfigSet", "CanIfHrh", "CanIfHth"),
    ),
    "PduR": ModuleSchema(
        name="PduR",
        category="ECU_ABSTRACTION",
        typical_vendor="Vector",
        description="PDU 路由器：模块间 PDU 转发",
        common_config_groups=("PduRRoutingTables", "PduRRoutingPath"),
    ),
    "EcuC": ModuleSchema(
        name="EcuC",
        category="ECU_ABSTRACTION",
        typical_vendor="Vector",
        description="ECU 配置：PDU 容器、句柄",
        common_config_groups=("EcuCConfiguration", "EcuCPdu"),
    ),
    "Com": ModuleSchema(
        name="Com",
        category="SERVICE",
        typical_vendor="Vector",
        description="通信服务：信号打包、传输确认",
        common_config_groups=("ComConfig", "ComSignal", "ComIPdu"),
    ),
}


def get_module_schema(name: str) -> ModuleSchema | None:
    """按模块名查找 schema；未找到返回 None。"""
    return MCAL_MODULES.get(name) or ECU_ABSTRACTION_MODULES.get(name)


def list_modules_by_category(category: str) -> tuple[str, ...]:
    """按类别列出模块名（按字典序）。"""
    modules = list(MCAL_MODULES.items()) + list(ECU_ABSTRACTION_MODULES.items())
    return tuple(sorted(n for n, s in modules if s.category == category))


def is_known_module(name: str) -> bool:
    """判断模块名是否在 autoc 已知列表中。"""
    return name in MCAL_MODULES or name in ECU_ABSTRACTION_MODULES
