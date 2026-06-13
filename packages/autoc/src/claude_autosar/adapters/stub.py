"""测试用 Stub 适配器。

把对真实工具的调用替换为可断言的记录器，单元测试可以：
    - 验证业务层传入了正确的 module 名
    - 注入预设的 returncode / stdout / stderr
    - 验证调用次数（避免重复触发昂贵的 subprocess）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from claude_autosar.adapters.protocol import (
    CalcResult,
    EcuConfigProjectContext,
    SaveResult,
    VerifyResult,
)


@dataclass
class StubTresosAdapter:
    """EB tresos Stub 实现。

    字段：
        - ``verify_responses`` / ``save_responses`` / ``autocalc_response``：预设返回
        - ``verify_calls`` / ``save_calls`` / ``autocalc_calls``：调用记录
        - ``discover_response``：预设 discover 返回（避免测试需要真实 .project）
    """

    discover_response: EcuConfigProjectContext
    verify_responses: list[VerifyResult] = field(default_factory=list)
    save_responses: list[SaveResult] = field(default_factory=list)
    autocalc_response: CalcResult | None = None

    verify_calls: list[tuple[EcuConfigProjectContext, str | None]] = field(default_factory=list)
    save_calls: list[tuple[EcuConfigProjectContext, str | None]] = field(default_factory=list)
    autocalc_calls: list[EcuConfigProjectContext] = field(default_factory=list)

    def discover(
        self,
        project_path: Path,
        tool_home: Path,
    ) -> EcuConfigProjectContext:
        """返回预设 context（不读盘）。"""
        return self.discover_response

    def verify(
        self,
        ctx: EcuConfigProjectContext,
        module: str | None = None,
    ) -> VerifyResult:
        """记录并返回下一个预设结果。"""
        self.verify_calls.append((ctx, module))
        if not self.verify_responses:
            return VerifyResult(success=True, returncode=0, stdout="", stderr="")
        return self.verify_responses.pop(0)

    def save(
        self,
        ctx: EcuConfigProjectContext,
        module: str | None = None,
    ) -> SaveResult:
        """记录并返回下一个预设结果。"""
        self.save_calls.append((ctx, module))
        if not self.save_responses:
            return SaveResult(
                success=True,
                returncode=0,
                stdout="",
                stderr="",
                written_files=(),
            )
        return self.save_responses.pop(0)

    def autocalc(self, ctx: EcuConfigProjectContext) -> CalcResult:
        """记录并返回预设结果。"""
        self.autocalc_calls.append(ctx)
        if self.autocalc_response is None:
            return CalcResult(success=True, returncode=0, stdout="", stderr="")
        return self.autocalc_response


@dataclass
class StubDavinciAdapter:
    """DaVinci Configurator Stub 实现。"""

    verify_responses: list[VerifyResult] = field(default_factory=list)
    save_responses: list[SaveResult] = field(default_factory=list)

    verify_calls: list[tuple[EcuConfigProjectContext, str | None]] = field(default_factory=list)
    save_calls: list[tuple[EcuConfigProjectContext, str | None]] = field(default_factory=list)

    def verify(
        self,
        ctx: EcuConfigProjectContext,
        module: str | None = None,
    ) -> VerifyResult:
        self.verify_calls.append((ctx, module))
        if not self.verify_responses:
            return VerifyResult(success=True, returncode=0, stdout="", stderr="")
        return self.verify_responses.pop(0)

    def save(
        self,
        ctx: EcuConfigProjectContext,
        module: str | None = None,
    ) -> SaveResult:
        self.save_calls.append((ctx, module))
        if not self.save_responses:
            return SaveResult(
                success=True,
                returncode=0,
                stdout="",
                stderr="",
                written_files=(),
            )
        return self.save_responses.pop(0)


# 结构化子类型断言：运行时也校验（满足 Protocol）
# 由 test_protocol.py::TestProtocols 验证
