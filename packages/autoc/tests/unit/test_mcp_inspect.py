"""Unit tests for Sprint 9.1 T9.1.4 — MCP ``arxml_inspect`` /
``xdm_inspect`` / ``bsw_inspect`` 工具。

覆盖：

- 3 个 tool 注册到 FastMCP（``_TOOL_NAMES`` / ``_TOOL_FUNCS`` / ``build_mcp_server``）
- 3 个 tool happy path：返回 ``{"success": True, "format": ..., "report_path": ...}``
- ``bsw_inspect`` 在 arxml fixture 上自动选 ``arxml``
- R6 路径防御：cwd 外的 path → 返回 ``PermissionError``
- 不存在的文件 → 返回 ``FileNotFoundError`` error dict
- 响应必须含 ``format`` 字段
"""

from __future__ import annotations

from pathlib import Path

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
# Tool 注册
# ---------------------------------------------------------------------------


class TestToolRegistration:
    """新增 3 个 inspect tool 必须注册到 FastMCP server。"""

    def test_tool_names_includes_three_inspect(self) -> None:
        """_TOOL_NAMES 元组新增 3 个 inspect tool + 2 个 apply_template tool。"""
        assert "arxml_inspect" in _TOOL_NAMES
        assert "xdm_inspect" in _TOOL_NAMES
        assert "bsw_inspect" in _TOOL_NAMES
        # 总数：原 10 + 3 inspect (Sprint 9.1) + 2 apply_template (Sprint 9.2-γ) = 15
        assert len(_TOOL_NAMES) == 15

    def test_tool_funcs_includes_three_inspect(self) -> None:
        """_TOOL_FUNCS 字典映射正确（key 与函数名一致）。"""
        from claude_autosar.cli.mcp_server import _TOOL_FUNCS

        for name in ("arxml_inspect", "xdm_inspect", "bsw_inspect"):
            assert name in _TOOL_FUNCS
            fn = _TOOL_FUNCS[name]
            assert fn.__name__ == name, (
                f"tool key {name!r} must match function name; "
                f"got {fn.__name__!r}"
            )

    def test_build_mcp_server_registers_inspect_tools(self) -> None:
        """FastMCP server 上 3 个 inspect tool 都已注册。"""
        server = build_mcp_server()
        tm = getattr(server, "_tool_manager", None)
        assert tm is not None
        tools_dict = getattr(tm, "_tools", None) or {}
        registered = set(tools_dict.keys())
        for name in ("arxml_inspect", "xdm_inspect", "bsw_inspect"):
            assert name in registered, f"missing tool in FastMCP: {name}"


# ---------------------------------------------------------------------------
# arxml_inspect tool 行为
# ---------------------------------------------------------------------------


class TestArxmlInspectTool:
    def test_arxml_inspect_tool_success(self, tmp_path: Path) -> None:
        """arxml_inspect happy：返回 success=True + format=arxml + report_path。"""
        from claude_autosar.cli.mcp_server import arxml_inspect

        src = tmp_path / "Com_Com.minimal.arxml"
        src.write_bytes(ARXML_FIXTURE.read_bytes())

        result = arxml_inspect(str(src))
        assert result["success"] is True
        assert result["format"] == "arxml"
        assert result["path"] == str(src)
        assert "report_path" in result
        assert Path(result["report_path"]).exists()
        # 报告 HTML 合法
        content = Path(result["report_path"]).read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content

    def test_arxml_inspect_tool_custom_output(self, tmp_path: Path) -> None:
        """arxml_inspect 带 output 参数写到指定路径。"""
        from claude_autosar.cli.mcp_server import arxml_inspect

        src = tmp_path / "Com_Com.minimal.arxml"
        src.write_bytes(ARXML_FIXTURE.read_bytes())
        out = tmp_path / "custom.html"

        result = arxml_inspect(str(src), output=str(out))
        assert result["success"] is True
        assert Path(result["report_path"]).resolve() == out.resolve()
        assert out.exists()


# ---------------------------------------------------------------------------
# xdm_inspect tool 行为
# ---------------------------------------------------------------------------


class TestXdmInspectTool:
    def test_xdm_inspect_tool_success(self, tmp_path: Path) -> None:
        """xdm_inspect happy：返回 success=True + format=xdm。"""
        from claude_autosar.cli.mcp_server import xdm_inspect

        src = tmp_path / "Can.xdm"
        src.write_bytes(XDM_FIXTURE.read_bytes())

        result = xdm_inspect(str(src))
        assert result["success"] is True
        assert result["format"] == "xdm"
        assert result["path"] == str(src)
        assert "report_path" in result
        assert Path(result["report_path"]).exists()
        content = Path(result["report_path"]).read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content


# ---------------------------------------------------------------------------
# bsw_inspect tool 行为（dispatcher 自动选）
# ---------------------------------------------------------------------------


class TestBswInspectTool:
    def test_bsw_inspect_tool_auto_dispatch(self, tmp_path: Path) -> None:
        """bsw_inspect 在 arxml fixture 上自动选 arxml（不依赖后缀）。"""
        from claude_autosar.cli.mcp_server import bsw_inspect

        src = tmp_path / "renamed_no_extension"
        # 把 arxml 内容写到无后缀文件（dispatcher 按根 xmlns 探测）
        src.write_bytes(ARXML_FIXTURE.read_bytes())

        result = bsw_inspect(str(src))
        assert result["success"] is True
        assert result["format"] == "arxml"
        assert "report_path" in result

    def test_inspect_tool_includes_format_field(self, tmp_path: Path) -> None:
        """所有 inspect tool 响应必含 ``format`` 字段（"arxml" 或 "xdm"）。"""
        from claude_autosar.cli.mcp_server import arxml_inspect, bsw_inspect, xdm_inspect

        arxml_src = tmp_path / "a.arxml"
        arxml_src.write_bytes(ARXML_FIXTURE.read_bytes())
        xdm_src = tmp_path / "a.xdm"
        xdm_src.write_bytes(XDM_FIXTURE.read_bytes())

        for fn, path, expected_fmt in (
            (arxml_inspect, arxml_src, "arxml"),
            (xdm_inspect, xdm_src, "xdm"),
            (bsw_inspect, arxml_src, "arxml"),
        ):
            result = fn(str(path))
            assert result["success"] is True
            assert result.get("format") == expected_fmt, (
                f"{fn.__name__}: expected format={expected_fmt!r}, "
                f"got {result.get('format')!r}"
            )


# ---------------------------------------------------------------------------
# 错误路径 + R6 路径防御
# ---------------------------------------------------------------------------


class TestErrors:
    def test_arxml_inspect_tool_missing_file(self, tmp_path: Path) -> None:
        """不存在的文件 → 返回 error dict（不抛异常）。"""
        from claude_autosar.cli.mcp_server import arxml_inspect

        result = arxml_inspect(str(tmp_path / "no_such.arxml"))
        assert result["success"] is False
        assert "error" in result

    def test_xdm_inspect_tool_missing_file(self, tmp_path: Path) -> None:
        from claude_autosar.cli.mcp_server import xdm_inspect

        result = xdm_inspect(str(tmp_path / "no_such.xdm"))
        assert result["success"] is False
        assert "error" in result

    def test_arxml_inspect_tool_path_outside_cwd(self) -> None:
        """R6 路径防御：cwd 外的 project → 返回 ``PermissionError``。

        ``_ALLOWED_PROJECT_ROOTS`` 是 cwd（per ``_resolve_safe_project``）；
        ``/nonexistent_root_for_test`` 不可能是 cwd 子目录 → ``PermissionError``。
        """
        from claude_autosar.cli.mcp_server import arxml_inspect

        result = arxml_inspect(
            "dummy.arxml",
            project="/nonexistent_root_for_test_inspect",
        )
        assert result["success"] is False
        assert "PermissionError" in result["error"]

    def test_bsw_inspect_tool_unknown_format(self, tmp_path: Path) -> None:
        """未知 namespace → ``UnknownFormatError``。"""
        from claude_autosar.cli.mcp_server import bsw_inspect

        # 写一个 root 没 namespace 的 XML（既不是 AUTOSAR 也不是 DataModel2）
        weird = tmp_path / "weird.xml"
        weird.write_text(
            '<?xml version="1.0"?><root xmlns="http://example.com/unknown"><x/></root>',
            encoding="utf-8",
        )
        result = bsw_inspect(str(weird))
        assert result["success"] is False
        assert "error" in result
