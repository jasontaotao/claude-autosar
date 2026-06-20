"""Sprint 9.5 — MCP 输入校验安全测试（M9–M12）。

验证 mcp_tools/validation.py 中的共享校验函数：
- validate_module_name：白名单过滤 XPath / 路径注入
- validate_no_traversal：路径遍历 .. 阻断
- validate_safe_path：组合校验（traversal + 非法字符）
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.autosar


# ---------------------------------------------------------------------------
# validate_module_name — XPath 注入（M12）
# ---------------------------------------------------------------------------


class TestValidateModuleName:
    """白名单：^[A-Za-z][A-Za-z0-9_]*$"""

    def test_valid_simple(self) -> None:
        from claude_autosar.cli.mcp_tools.validation import validate_module_name

        assert validate_module_name("Mcu") == "Mcu"

    def test_valid_underscore(self) -> None:
        from claude_autosar.cli.mcp_tools.validation import validate_module_name

        assert validate_module_name("Port_Pin") == "Port_Pin"

    def test_valid_mixed_case(self) -> None:
        from claude_autosar.cli.mcp_tools.validation import validate_module_name

        assert validate_module_name("AdcGroup1") == "AdcGroup1"

    def test_rejects_path_traversal(self) -> None:
        from claude_autosar.cli.mcp_tools.validation import validate_module_name

        with pytest.raises(ValueError, match="Invalid module name"):
            validate_module_name("../../../etc/passwd")

    def test_rejects_sql_injection(self) -> None:
        from claude_autosar.cli.mcp_tools.validation import validate_module_name

        with pytest.raises(ValueError, match="Invalid module name"):
            validate_module_name("Mcu'; drop table")

    def test_rejects_xpath_quote_injection(self) -> None:
        from claude_autosar.cli.mcp_tools.validation import validate_module_name

        with pytest.raises(ValueError, match="Invalid module name"):
            validate_module_name('" or "1"="1')

    def test_rejects_empty_string(self) -> None:
        from claude_autosar.cli.mcp_tools.validation import validate_module_name

        with pytest.raises(ValueError, match="Invalid module name"):
            validate_module_name("")

    def test_rejects_leading_digit(self) -> None:
        from claude_autosar.cli.mcp_tools.validation import validate_module_name

        with pytest.raises(ValueError, match="Invalid module name"):
            validate_module_name("1Mcu")

    def test_rejects_slash(self) -> None:
        from claude_autosar.cli.mcp_tools.validation import validate_module_name

        with pytest.raises(ValueError, match="Invalid module name"):
            validate_module_name("Mcu/Clock")

    def test_rejects_dot(self) -> None:
        from claude_autosar.cli.mcp_tools.validation import validate_module_name

        with pytest.raises(ValueError, match="Invalid module name"):
            validate_module_name("Mcu.xdm")

    def test_rejects_space(self) -> None:
        from claude_autosar.cli.mcp_tools.validation import validate_module_name

        with pytest.raises(ValueError, match="Invalid module name"):
            validate_module_name("Mcu Clock")

    def test_rejects_bracket(self) -> None:
        from claude_autosar.cli.mcp_tools.validation import validate_module_name

        with pytest.raises(ValueError, match="Invalid module name"):
            validate_module_name("Mcu[@name='x']")


# ---------------------------------------------------------------------------
# validate_no_traversal — 路径遍历（M9 / M10 / M11）
# ---------------------------------------------------------------------------


class TestValidateNoTraversal:
    def test_valid_path(self) -> None:
        from claude_autosar.cli.mcp_tools.validation import validate_no_traversal

        assert validate_no_traversal("/valid/path") == "/valid/path"

    def test_valid_relative(self) -> None:
        from claude_autosar.cli.mcp_tools.validation import validate_no_traversal

        assert validate_no_traversal("some/relative/path") == "some/relative/path"

    def test_rejects_double_dot_prefix(self) -> None:
        from claude_autosar.cli.mcp_tools.validation import validate_no_traversal

        with pytest.raises(ValueError, match="Path traversal"):
            validate_no_traversal("../../secret")

    def test_rejects_double_dot_middle(self) -> None:
        from claude_autosar.cli.mcp_tools.validation import validate_no_traversal

        with pytest.raises(ValueError, match="Path traversal"):
            validate_no_traversal("/some/../../etc/passwd")

    def test_rejects_double_dot_suffix(self) -> None:
        from claude_autosar.cli.mcp_tools.validation import validate_no_traversal

        with pytest.raises(ValueError, match="Path traversal"):
            validate_no_traversal("path/..")

    def test_rejects_dot_dot_only(self) -> None:
        from claude_autosar.cli.mcp_tools.validation import validate_no_traversal

        with pytest.raises(ValueError, match="Path traversal"):
            validate_no_traversal("..")

    def test_accepts_dot_in_filename(self) -> None:
        """单个 . 是合法的（文件名含点号）。"""
        from claude_autosar.cli.mcp_tools.validation import validate_no_traversal

        assert validate_no_traversal("Mcu.xdm") == "Mcu.xdm"

    def test_accepts_dot_dot_in_filename_without_separator(self) -> None:
        """合法文件名中出现 '..' 但两侧无路径分隔符的情况（极端 case）。

        当前策略：只要含 '..' 就拒绝，不区分上下文。宁可误杀。
        """
        from claude_autosar.cli.mcp_tools.validation import validate_no_traversal

        with pytest.raises(ValueError, match="Path traversal"):
            validate_no_traversal("file..name")

    def test_empty_path_passes(self) -> None:
        """空字符串不含 '..'，应当通过 traversal 检查。"""
        from claude_autosar.cli.mcp_tools.validation import validate_no_traversal

        assert validate_no_traversal("") == ""


# ---------------------------------------------------------------------------
# 集成校验：inspect_ops / bsw_read_ops / session_ops 中的注入场景
# ---------------------------------------------------------------------------


class TestModuleNameIntegration:
    """验证 bsw_read 中 module 参数的注入阻断。"""

    def test_bsw_read_rejects_module_traversal_as_module_name(
        self,
    ) -> None:
        """module 参数含 ../ → validate_module_name 拒绝，不会走到文件查找。"""
        from claude_autosar.cli.mcp_tools.bsw_read_ops import bsw_read

        r = bsw_read("../../../etc/passwd", "Clock")
        assert r["success"] is False
        assert "Invalid module name" in r["error"]

    def test_bsw_read_rejects_module_with_semicolon(self) -> None:
        from claude_autosar.cli.mcp_tools.bsw_read_ops import bsw_read

        r = bsw_read("Mcu'; DROP TABLE", "Clock")
        assert r["success"] is False
        assert "Invalid module name" in r["error"]

    def test_bsw_read_rejects_seg_injection_via_path(self) -> None:
        """path 含非法 segment 时被 bsw_read 内的 seg 校验拦截。"""
        from claude_autosar.cli.mcp_tools.bsw_read_ops import bsw_read

        r = bsw_read('Mcu", "or"="1', "Clock")
        assert r["success"] is False
        assert "Invalid module name" in r["error"]


class TestSessionDirTraversalIntegration:
    """验证 session_ops 中 session_dir 参数的路径遍历阻断。"""

    def test_session_list_rejects_traversal_session_dir(self) -> None:
        from claude_autosar.cli.mcp_tools.session_ops import session_list

        r = session_list(session_dir="../../../../etc")
        assert r == [] or (isinstance(r, dict) and r.get("success") is False)

    def test_session_show_rejects_traversal_session_dir(self) -> None:
        from claude_autosar.cli.mcp_tools.session_ops import session_show

        r = session_show("s1", session_dir="../../../../etc")
        # 应返回 error dict 而非抛异常
        assert isinstance(r, dict)
        assert r.get("success") is False

    def test_session_export_rejects_traversal_session_dir(self) -> None:
        from claude_autosar.cli.mcp_tools.session_ops import session_export

        r = session_export("s1", session_dir="../../../../tmp/stolen")
        assert isinstance(r, dict)
        assert r.get("success") is False

    def test_log_export_rejects_traversal_session_dir(self) -> None:
        from claude_autosar.cli.mcp_tools.session_ops import log_export

        r = log_export("s1", session_dir="../../../../tmp/stolen")
        assert isinstance(r, dict)
        assert r.get("success") is False


class TestInspectPathTraversalIntegration:
    """验证 inspect_ops 中 path 参数的路径遍历阻断。"""

    def test_arxml_validate_rejects_traversal_path(self) -> None:
        from claude_autosar.cli.mcp_tools.inspect_ops import arxml_validate

        r = arxml_validate("../../../../etc/passwd")
        assert r["success"] is False

    def test_dbc_parse_rejects_traversal_path(self) -> None:
        from claude_autosar.cli.mcp_tools.inspect_ops import dbc_parse

        r = dbc_parse("../../../../etc/passwd")
        assert r["success"] is False


class TestSessionIdTraversalIntegration:
    """验证 session_ops 中 session_id 参数的路径遍历阻断（review MEDIUM）。"""

    def test_session_show_rejects_traversal_session_id(self) -> None:
        from claude_autosar.cli.mcp_tools.session_ops import session_show

        r = session_show("../../tmp/evil")
        assert isinstance(r, dict)
        assert r["success"] is False
        assert "Path traversal" in r["error"]

    def test_session_export_rejects_traversal_session_id(self, tmp_path: Path) -> None:
        from claude_autosar.cli.mcp_tools.session_ops import session_export

        r = session_export("../../tmp/evil", session_dir=str(tmp_path))
        assert isinstance(r, dict)
        assert r["success"] is False
        assert "Path traversal" in r["error"]

    def test_log_export_rejects_traversal_session_id(self, tmp_path: Path) -> None:
        from claude_autosar.cli.mcp_tools.session_ops import log_export

        r = log_export("../../tmp/evil", session_dir=str(tmp_path))
        assert isinstance(r, dict)
        assert r["success"] is False
        assert "Path traversal" in r["error"]

    def test_session_show_accepts_latest_keyword(self, tmp_path: Path) -> None:
        """'latest' 是特殊关键字，不触发 traversal 校验。"""
        from claude_autosar.cli.mcp_tools.session_ops import session_show

        r = session_show("latest", session_dir=str(tmp_path))
        # 空 store → "no sessions found"，但不是 traversal 错误
        assert r["success"] is False
        assert "no sessions found" in r["error"]


class TestTemplatePathTraversalIntegration:
    """验证 apply_template_ops 中 template 参数的路径遍历阻断（review MEDIUM）。"""

    def test_arxml_apply_template_rejects_traversal_template(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from claude_autosar.cli import mcp_server
        from claude_autosar.cli.mcp_tools.apply_template_ops import arxml_apply_template

        monkeypatch.setattr(
            mcp_server, "_ALLOWED_PROJECT_ROOTS", frozenset({tmp_path.resolve()})
        )
        # path 参数必须是真实文件（否则 _inspect_resolve_input 抛 FileNotFoundError）
        ok_file = tmp_path / "ok.arxml"
        ok_file.write_text("<root/>", encoding="utf-8")
        r = arxml_apply_template(str(ok_file), "../../../../etc/passwd", project=str(tmp_path))
        assert r["success"] is False
        assert "Path traversal" in r["error"]

    def test_xdm_apply_template_rejects_traversal_template(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from claude_autosar.cli import mcp_server
        from claude_autosar.cli.mcp_tools.apply_template_ops import xdm_apply_template

        monkeypatch.setattr(
            mcp_server, "_ALLOWED_PROJECT_ROOTS", frozenset({tmp_path.resolve()})
        )
        ok_file = tmp_path / "ok.xdm"
        ok_file.write_text("<root/>", encoding="utf-8")
        r = xdm_apply_template(str(ok_file), "../../../../etc/passwd", project=str(tmp_path))
        assert r["success"] is False
        assert "Path traversal" in r["error"]


class TestBswWritePathTraversalIntegration:
    """验证 bsw_write 中 params[].path 的路径遍历阻断（review LOW）。"""

    def test_bsw_write_rejects_traversal_in_param_path(self) -> None:
        from claude_autosar.cli.mcp_tools.bsw_write_ops import bsw_write

        r = bsw_write(
            "Mcu",
            [{"path": "../../etc/passwd", "value": 1, "type": "integer"}],
            project=".",
        )
        assert r["success"] is False
        assert r["field"] == "path"
        assert "traversal" in r["error"]
