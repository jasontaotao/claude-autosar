"""工具适配器协议定义。

通过 ``typing.Protocol``（结构化子类型）声明 EB tresos / DaVinci Configurator
适配器应满足的接口。**所有 adapter 共享 ``EcuConfigProjectContext`` / ``VerifyResult``
/ ``SaveResult`` 这三个 dataclass**——保证业务层（如 core.bsw.validator）可以
跨工具复用，不绑死任何具体工具。

注意：上下文名 ``EcuConfigProjectContext`` 是工具无关的（既可承载 EB tresos
的 ``TRESOS_HOME``，也可承载 DaVinci 的 ``DAVINCI_HOME``），字段 ``tool_home``
对应"工具安装根目录"。Sprint 3 重命名自 ``TresosProjectContext``。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

# =============================================================================
# 公共数据模型
# =============================================================================


@dataclass(frozen=True)
class EcuConfigProjectContext:
    """ECU 配置工程运行时上下文（MCU 差异化的关键 DTO，工具无关）。

    由 ``TresosAdapter.discover()`` 从 ``.project`` / ``.prefs/`` / ``<tool_home>/plugins/``
    三处动态读取构造，**不预知任何具体芯片字段**。S32K3 / TC3xx / RH850 走同一段代码。

    ``tool_home`` 既可指向 ``TRESOS_HOME``（EB tresos）也可指向
    ``DAVINCI_HOME``（Vector DaVinci Configurator），调用方按需填入。
    """

    project_path: Path
    tool_home: Path
    """工具安装根目录：EB tresos 模式下是 ``TRESOS_HOME``，DaVinci 模式下是
    ``DAVINCI_HOME``。"""
    target: str
    """EB Target，如 ``ARM``。"""
    derivate: str
    """EB Derivate（芯片衍生），如 ``S32K344`` / ``TC38XQ``。"""
    pn: str
    """Resource Subderivative。"""
    autosar_version: str
    """AUTOSAR 版本号，如 ``4.2.2`` / ``4.4.0``。"""
    enabled_modules: tuple[str, ...]
    """从 ``<project>/.prefs/*.xdm`` 解析出的已启用模块名（去重 + 排序）。
    DaVinci 工程不一定有 ``.prefs/``，可能为空 tuple。"""
    available_plugins: tuple[Path, ...]
    """``<tool_home>/plugins/`` 下所有 ``*_bswmd.arxml`` 的路径。"""

    def __post_init__(self) -> None:
        if not self.project_path.is_dir():
            raise ValueError(f"project_path is not a directory: {self.project_path}")
        if not self.tool_home.is_dir():
            raise ValueError(f"tool_home is not a directory: {self.tool_home}")
        if not self.target:
            raise ValueError("target must be non-empty")
        if not self.derivate:
            raise ValueError("derivate must be non-empty")
        if not self.autosar_version:
            raise ValueError("autosar_version must be non-empty")


@dataclass(frozen=True)
class VerifyResult:
    """工具 verify 调用结果。"""

    success: bool
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class SaveResult:
    """工具 save 调用结果。"""

    success: bool
    returncode: int
    stdout: str
    stderr: str
    written_files: tuple[Path, ...] = ()
    """实际写入磁盘的文件路径（如 EB 工程的 .xdm / DaVinci 的 .arxml）。"""


@dataclass(frozen=True)
class CalcResult:
    """AutoCalc 触发结果。"""

    success: bool
    returncode: int
    stdout: str
    stderr: str


# =============================================================================
# EB tresos 协议
# =============================================================================


@runtime_checkable
class TresosAdapter(Protocol):
    """EB tresos 适配器协议。

    所有方法必须接受 ``EcuConfigProjectContext``，**禁止**让调用方传零散路径——
    这样业务层就不必关心"工程根目录 vs tool_home vs 当前工作目录"
    之间的差异。
    """

    def discover(
        self,
        project_path: Path,
        tool_home: Path,
    ) -> EcuConfigProjectContext:
        """从 .project / .prefs/ / <tool_home>/plugins/ 动态发现工程上下文。"""
        ...

    def verify(
        self,
        ctx: EcuConfigProjectContext,
        module: str | None = None,
    ) -> VerifyResult:
        """调用 ``tresos_cmd --validate``。``module`` 为空时校验全部已启用模块。"""
        ...

    def save(
        self,
        ctx: EcuConfigProjectContext,
        module: str | None = None,
    ) -> SaveResult:
        """调用 ``tresos_cmd --save``。"""
        ...

    def autocalc(self, ctx: EcuConfigProjectContext) -> CalcResult:
        """调用 ``tresos_cmd --autocalc``。"""
        ...


# =============================================================================
# DaVinci Configurator 协议
# =============================================================================


@runtime_checkable
class DavinciAdapter(Protocol):
    """DaVinci Configurator 适配器协议。"""

    def verify(
        self,
        ctx: EcuConfigProjectContext,
        module: str | None = None,
    ) -> VerifyResult:
        """调用 ``DVCfgCmd.exe AutocVerify``。"""
        ...

    def save(
        self,
        ctx: EcuConfigProjectContext,
        module: str | None = None,
    ) -> SaveResult:
        """调用 ``DVCfgCmd.exe Save``。"""
        ...
