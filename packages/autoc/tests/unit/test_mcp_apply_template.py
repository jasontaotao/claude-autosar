"""Unit tests for Sprint 9.2 T9.2-γ — MCP ``arxml_apply_template`` /
``xdm_apply_template`` 工具。

覆盖：

- 2 个 tool 注册到 FastMCP（``_TOOL_NAMES`` / ``_TOOL_FUNCS`` /
  ``build_mcp_server``）
- 2 个 tool happy path：返回 ``{"success": True, "format": ..., "diff_count": ...}``
- H4 路径防御：cwd 外的 project → 返回 ``PermissionError``
- 不存在的文件 / 不存在的 template → 返回 ``FileNotFoundError`` error dict
- ``apply`` 参数透传到 ``ApplyMode.APPLY`` vs ``ApplyMode.DRY_RUN``

注：``apply_template_diff`` / ``ApplyMode`` / ``diff_arxml_templates`` 由
并发任务 T9.2.1 / T9.2.0b 实施。本文件用 :mod:`unittest.mock` patch 这些
符号（``sys.modules`` 注入 + 模块属性 patch）以保持切片独立性；当
T9.2.1 / T9.2.0b 落地后，本文件测试无须改动。
"""

from __future__ import annotations

from pathlib import Path
import sys
import types
from typing import Any

import pytest

from claude_autosar.cli.mcp_server import _TOOL_NAMES, build_mcp_server

pytestmark = pytest.mark.autosar


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
ARXML_FIXTURE = FIXTURES_DIR / "arxml" / "Com_Com.minimal.arxml"
XDM_FIXTURE = FIXTURES_DIR / "datamodel2" / "Can.xdm"


# ---------------------------------------------------------------------------
# ApplyMode stub + apply_template_diff stub（测试用）
# ---------------------------------------------------------------------------


class _ApplyModeStub:
    """替身：``ApplyMode.DRY_RUN`` / ``ApplyMode.APPLY`` 两个枚举值。"""

    DRY_RUN = "dry_run"
    APPLY = "apply"

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return (cls.DRY_RUN, cls.APPLY)


def _install_apply_template_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    """往 :mod:`claude_autosar.core.bsw.templates.apply` 注入 stub 模块。

    提供 ``ApplyMode``（DRY_RUN/APPLY）+ ``apply_template_diff(path, diff, *, mode)``，
    返回最简单的 ``ApplyResult`` shape（frozen-like simple object）。
    """
    stub = types.ModuleType("claude_autosar.core.bsw.templates.apply")

    class _ApplyResult:
        def __init__(self, mode: str, written: bool, byte_changes: int = 0) -> None:
            self.mode = mode
            self.written = written
            self.byte_changes = byte_changes

    def _apply_template_diff(
        path: Any,  # noqa: ARG001
        diff: Any,  # noqa: ARG001
        *,
        mode: Any = _ApplyModeStub.DRY_RUN,
    ) -> _ApplyResult:
        # 返回一个 sentinel object；测试只检查 shape
        m = str(mode)
        return _ApplyResult(
            mode=m,
            written=(m == _ApplyModeStub.APPLY),
            byte_changes=len(getattr(diff, "diffs", ())),
        )

    stub.ApplyMode = _ApplyModeStub
    stub.apply_template_diff = _apply_template_diff
    monkeypatch.setitem(sys.modules, "claude_autosar.core.bsw.templates.apply", stub)


def _install_arxml_diff_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    """往 :mod:`claude_autosar.core.bsw.templates.arxml_diff` 注入 stub 模块。"""
    stub = types.ModuleType("claude_autosar.core.bsw.templates.arxml_diff")

    class _TemplateDiffStub:
        def __init__(self, path: str, op: str) -> None:
            self.path = path
            self.op = op
            self.current = None
            self.template = None

    class _TemplateDiffResultStub:
        def __init__(self, diffs: tuple[_TemplateDiffStub, ...]) -> None:
            self.diffs = diffs

        @property
        def adds(self) -> tuple[_TemplateDiffStub, ...]:
            return tuple(d for d in self.diffs if d.op == "add")

        @property
        def modifies(self) -> tuple[_TemplateDiffStub, ...]:
            return tuple(d for d in self.diffs if d.op == "modify")

        @property
        def deletes(self) -> tuple[_TemplateDiffStub, ...]:
            return tuple(d for d in self.diffs if d.op == "delete")

    def _diff_arxml_templates(
        current: Any,  # noqa: ARG001
        template: Any,  # noqa: ARG001
    ) -> _TemplateDiffResultStub:
        return _TemplateDiffResultStub(diffs=(_TemplateDiffStub("Module/A", "modify"),))

    stub.diff_arxml_templates = _diff_arxml_templates
    monkeypatch.setitem(sys.modules, "claude_autosar.core.bsw.templates.arxml_diff", stub)


@pytest.fixture
def stub_template_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    """同时装 apply.py + arxml_diff.py stub。"""
    _install_apply_template_stub(monkeypatch)
    _install_arxml_diff_stub(monkeypatch)


# ---------------------------------------------------------------------------
# Tool 注册
# ---------------------------------------------------------------------------


class TestToolRegistration:
    """新增 2 个 apply-template tool 必须注册到 FastMCP server。"""

    def test_tool_names_includes_two_apply_template(self) -> None:
        """_TOOL_NAMES 元组新增 2 个 apply-template tool。"""
        assert "arxml_apply_template" in _TOOL_NAMES
        assert "xdm_apply_template" in _TOOL_NAMES
        # 原 13 + 新 2 = 15
        assert len(_TOOL_NAMES) == 15

    def test_tool_funcs_includes_two_apply_template(self) -> None:
        """_TOOL_FUNCS 字典映射正确（key 与函数名一致）。"""
        from claude_autosar.cli.mcp_server import _TOOL_FUNCS

        for name in ("arxml_apply_template", "xdm_apply_template"):
            assert name in _TOOL_FUNCS
            fn = _TOOL_FUNCS[name]
            assert fn.__name__ == name, (
                f"tool key {name!r} must match function name; " f"got {fn.__name__!r}"
            )

    def test_build_mcp_server_registers_apply_template_tools(self) -> None:
        """FastMCP server 上 2 个 apply-template tool 都已注册。"""
        server = build_mcp_server()
        tm = getattr(server, "_tool_manager", None)
        assert tm is not None
        tools_dict = getattr(tm, "_tools", None) or {}
        registered = set(tools_dict.keys())
        for name in ("arxml_apply_template", "xdm_apply_template"):
            assert name in registered, f"missing tool in FastMCP: {name}"


# ---------------------------------------------------------------------------
# arxml_apply_template tool 行为
# ---------------------------------------------------------------------------


class TestArxmlApplyTemplateTool:
    def test_arxml_apply_template_dry_run(
        self, tmp_path: Path, stub_template_modules: None
    ) -> None:
        """arxml_apply_template dry-run：返回 success=True + format=arxml。"""
        from claude_autosar.cli.mcp_server import arxml_apply_template

        src = tmp_path / "Com_Com.minimal.arxml"
        src.write_bytes(ARXML_FIXTURE.read_bytes())
        tpl = tmp_path / "Com_Com.template.arxml"
        tpl.write_bytes(ARXML_FIXTURE.read_bytes())

        result = arxml_apply_template(str(src), str(tpl))
        assert result["success"] is True
        assert result["format"] == "arxml"
        assert result["applied"] is False
        assert result["mode"] == _ApplyModeStub.DRY_RUN
        assert "diff_count" in result
        assert "adds" in result
        assert "modifies" in result
        assert "deletes" in result

    def test_arxml_apply_template_apply_flag(
        self, tmp_path: Path, stub_template_modules: None
    ) -> None:
        """arxml_apply_template apply=True → mode=APPLY + applied=True。"""
        from claude_autosar.cli.mcp_server import arxml_apply_template

        src = tmp_path / "Com_Com.minimal.arxml"
        src.write_bytes(ARXML_FIXTURE.read_bytes())
        tpl = tmp_path / "Com_Com.template.arxml"
        tpl.write_bytes(ARXML_FIXTURE.read_bytes())

        result = arxml_apply_template(str(src), str(tpl), apply=True)
        assert result["success"] is True
        assert result["applied"] is True
        assert result["mode"] == _ApplyModeStub.APPLY

    def test_arxml_apply_template_custom_output(
        self, tmp_path: Path, stub_template_modules: None
    ) -> None:
        """arxml_apply_template 带 output 参数：不强制写文件（apply stub 不写）。"""
        from claude_autosar.cli.mcp_server import arxml_apply_template

        src = tmp_path / "Com_Com.minimal.arxml"
        src.write_bytes(ARXML_FIXTURE.read_bytes())
        tpl = tmp_path / "Com_Com.template.arxml"
        tpl.write_bytes(ARXML_FIXTURE.read_bytes())
        out = tmp_path / "report.html"

        result = arxml_apply_template(str(src), str(tpl), output=str(out))
        assert result["success"] is True
        # output 参数透传，不一定写文件（apply stub 决定）
        assert result.get("report_path") == str(out.resolve())

    def test_arxml_apply_template_missing_current(
        self, tmp_path: Path, stub_template_modules: None
    ) -> None:
        """不存在的 current → 返回 error dict（不抛异常）。"""
        from claude_autosar.cli.mcp_server import arxml_apply_template

        tpl = tmp_path / "Com_Com.template.arxml"
        tpl.write_bytes(ARXML_FIXTURE.read_bytes())

        result = arxml_apply_template(str(tmp_path / "no_such.arxml"), str(tpl))
        assert result["success"] is False
        assert "error" in result

    def test_arxml_apply_template_missing_template(
        self, tmp_path: Path, stub_template_modules: None
    ) -> None:
        """不存在的 template → 返回 error dict。"""
        from claude_autosar.cli.mcp_server import arxml_apply_template

        src = tmp_path / "Com_Com.minimal.arxml"
        src.write_bytes(ARXML_FIXTURE.read_bytes())

        result = arxml_apply_template(str(src), str(tmp_path / "no_such.arxml"))
        assert result["success"] is False
        assert "error" in result

    def test_arxml_apply_template_path_outside_cwd(self, stub_template_modules: None) -> None:
        """R6 路径防御：cwd 外的 project → 返回 ``PermissionError``。"""
        from claude_autosar.cli.mcp_server import arxml_apply_template

        result = arxml_apply_template(
            "dummy.arxml",
            "template.arxml",
            project="/nonexistent_root_for_test_apply_template",
        )
        assert result["success"] is False
        assert "PermissionError" in result["error"]


# ---------------------------------------------------------------------------
# xdm_apply_template tool 行为
# ---------------------------------------------------------------------------


class TestXdmApplyTemplateTool:
    def test_xdm_apply_template_dry_run(self, tmp_path: Path, stub_template_modules: None) -> None:
        """xdm_apply_template dry-run：返回 success=True + format=xdm。"""
        from claude_autosar.cli.mcp_server import xdm_apply_template

        src = tmp_path / "Can.xdm"
        src.write_bytes(XDM_FIXTURE.read_bytes())
        tpl = tmp_path / "Can_template.xdm"
        tpl.write_bytes(XDM_FIXTURE.read_bytes())

        result = xdm_apply_template(str(src), str(tpl))
        assert result["success"] is True
        assert result["format"] == "xdm"
        assert result["applied"] is False
        assert result["mode"] == _ApplyModeStub.DRY_RUN
        assert "module_name" in result
        assert "diff_count" in result

    def test_xdm_apply_template_apply_flag(
        self, tmp_path: Path, stub_template_modules: None
    ) -> None:
        """xdm_apply_template apply=True → mode=APPLY + applied=True。"""
        from claude_autosar.cli.mcp_server import xdm_apply_template

        src = tmp_path / "Can.xdm"
        src.write_bytes(XDM_FIXTURE.read_bytes())
        tpl = tmp_path / "Can_template.xdm"
        tpl.write_bytes(XDM_FIXTURE.read_bytes())

        result = xdm_apply_template(str(src), str(tpl), apply=True)
        assert result["success"] is True
        assert result["applied"] is True
        assert result["mode"] == _ApplyModeStub.APPLY

    def test_xdm_apply_template_missing_current(
        self, tmp_path: Path, stub_template_modules: None
    ) -> None:
        from claude_autosar.cli.mcp_server import xdm_apply_template

        tpl = tmp_path / "Can_template.xdm"
        tpl.write_bytes(XDM_FIXTURE.read_bytes())

        result = xdm_apply_template(str(tmp_path / "no_such.xdm"), str(tpl))
        assert result["success"] is False
        assert "error" in result

    def test_xdm_apply_template_path_outside_cwd(self, stub_template_modules: None) -> None:
        """R6 路径防御：cwd 外的 project → 返回 ``PermissionError``。"""
        from claude_autosar.cli.mcp_server import xdm_apply_template

        result = xdm_apply_template(
            "dummy.xdm",
            "template.xdm",
            project="/nonexistent_root_for_test_xdm_apply_template",
        )
        assert result["success"] is False
        assert "PermissionError" in result["error"]


# ---------------------------------------------------------------------------
# 防御性：missing apply.py 模块（未合并 T9.2.1 时）
# ---------------------------------------------------------------------------
# 注：本文件测试用 sys.modules 注入 stub 替身 simulate T9.2.1 / T9.2.0b；
# 实际运行时 ``apply.py`` 由并发任务 T9.2.1 提供。Tool 的 lazy import 路径
# 假设 ``apply_template_diff`` / ``ApplyMode`` / ``diff_arxml_templates``
# 在调用时存在；缺这些模块时 Python 会抛 ``ImportError``（不可恢复）—
# 这是有意为之：并发任务交付后这个分支永远不会触发。
