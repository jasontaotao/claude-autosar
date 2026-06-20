"""Sprint 8.E.1 coverage: ProjectConfig + YAML parser + platform defaults.

Targets: core/config/project_config.py — default_tresos_home(), load_yaml(),
_parse_yaml_simple(), _strip_comments_and_blanks(), _indent_of(), ProjectConfig.load().
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

import pytest

from claude_autosar.core.config import project_config as pc_mod
from claude_autosar.core.config.project_config import (
    ProjectConfig,
    ProjectConfigError,
    default_tresos_home,
    load_yaml,
)


class TestSprint8E1CoverageProjectConfigDefaultTresos:
    """``default_tresos_home()`` 平台分支 + 路径存在性。"""

    def test_default_tresos_home_windows_when_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr(pc_mod, "_PLATFORM_DEFAULT_TRESOS_HOME_WIN", tmp_path / "FlexCFG")
        (tmp_path / "FlexCFG").mkdir()
        assert default_tresos_home() == (tmp_path / "FlexCFG").resolve()

    def test_default_tresos_home_windows_when_not_exists(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr(pc_mod, "_PLATFORM_DEFAULT_TRESOS_HOME_WIN", Path("/no/such/path"))
        assert default_tresos_home() is None

    def test_default_tresos_home_linux_when_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(pc_mod, "_PLATFORM_DEFAULT_TRESOS_HOME_LINUX", tmp_path / "flex")
        (tmp_path / "flex").mkdir()
        assert default_tresos_home() == (tmp_path / "flex").resolve()

    def test_default_tresos_home_linux_when_not_exists(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(pc_mod, "_PLATFORM_DEFAULT_TRESOS_HOME_LINUX", Path("/no/such"))
        assert default_tresos_home() is None

    def test_default_tresos_home_other_platform_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "platform", "darwin")
        assert default_tresos_home() is None


class TestSprint8E1CoverageProjectConfigLoadYaml:
    """``load_yaml()`` 各种 fallback。"""

    def test_load_yaml_file_not_found(self, tmp_path: Path) -> None:
        result = load_yaml(tmp_path / "no_such.yaml")
        assert result == {}

    def test_load_yaml_oserror_on_read(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "x.yaml"
        path.write_text("a: 1\n", encoding="utf-8")

        def _boom(*_a: Any, **_kw: Any) -> str:
            raise OSError("perm denied")

        monkeypatch.setattr(Path, "read_text", _boom)
        result = load_yaml(path)
        assert result == {}

    def test_load_yaml_unicode_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        path = tmp_path / "x.yaml"
        path.write_text("a: 1\n", encoding="utf-8")

        def _boom(*_a: Any, **_kw: Any) -> str:
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad")

        monkeypatch.setattr(Path, "read_text", _boom)
        result = load_yaml(path)
        assert result == {}

    def test_load_yaml_parse_error_returns_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "x.yaml"
        path.write_text("invalid_yaml", encoding="utf-8")

        def _boom(_text: str) -> Any:
            raise pc_mod._YAMLError("parse fail")

        monkeypatch.setattr(pc_mod, "_parse_yaml_simple", _boom)
        result = load_yaml(path)
        assert result == {}

    def test_load_yaml_top_level_not_dict_returns_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "x.yaml"
        path.write_text("- item1\n- item2\n", encoding="utf-8")
        result = load_yaml(path)
        assert result == {}

    def test_load_yaml_empty_file(self, tmp_path: Path) -> None:
        path = tmp_path / "x.yaml"
        path.write_text("", encoding="utf-8")
        result = load_yaml(path)
        assert result == {}


class TestSprint8E1CoverageProjectConfigParserDictList:
    """``_parse_yaml_simple`` / ``_parse_dict`` / ``_parse_list``。"""

    def test_parse_simple_nested_dict(self) -> None:
        text = "project_root: /a\ntresos_home: /b\n"
        result = pc_mod._parse_yaml_simple(text)
        assert result == {"project_root": "/a", "tresos_home": "/b"}

    def test_parse_simple_list(self) -> None:
        text = "- a\n- b\n"
        result = pc_mod._parse_yaml_simple(text)
        assert result == ["a", "b"]

    def test_parse_simple_null_value(self) -> None:
        text = "a: null\nb:\nc: \"v\"\n"
        result = pc_mod._parse_yaml_simple(text)
        assert result == {"a": None, "b": None, "c": "v"}

    def test_parse_simple_empty(self) -> None:
        assert pc_mod._parse_yaml_simple("") == {}
        assert pc_mod._parse_yaml_simple("# only comment\n") == {}
        assert pc_mod._parse_yaml_simple("\n\n\n") == {}

    def test_parse_dict_unexpected_indent(self) -> None:
        text = "a: 1\n  b: 2\n"
        with pytest.raises(pc_mod._YAMLError, match="unexpected indent"):
            pc_mod._parse_yaml_simple(text)

    def test_parse_dict_missing_colon(self) -> None:
        text = "just_a_word\n"
        with pytest.raises(pc_mod._YAMLError, match="expected key:value"):
            pc_mod._parse_yaml_simple(text)

    def test_parse_dict_break_on_list(self) -> None:
        text = "a: 1\n- item\n"
        result = pc_mod._parse_yaml_simple(text)
        assert result == {"a": "1"}


class TestSprint8E1CoverageProjectConfigParserList:
    """``_parse_list`` 边界。"""

    def test_parse_list_indent_error(self) -> None:
        text = "- a\n    b: 2\n"
        with pytest.raises(pc_mod._YAMLError, match="unexpected indent in list"):
            pc_mod._parse_yaml_simple(text)

    def test_parse_list_no_dash_breaks(self) -> None:
        text = "- a\nb: 2\n"
        result = pc_mod._parse_yaml_simple(text)
        assert result == ["a"]


class TestSprint8E1CoverageProjectConfigParserScalar:
    """``_parse_scalar`` 各种 token。"""

    def test_parse_scalar_null_variants(self) -> None:
        assert pc_mod._parse_scalar("null") is None
        assert pc_mod._parse_scalar("~") is None
        assert pc_mod._parse_scalar("") is None
        assert pc_mod._parse_scalar("   ") is None

    def test_parse_scalar_double_quoted_with_escape(self) -> None:
        assert pc_mod._parse_scalar('"a\\"b"') == 'a"b'
        assert pc_mod._parse_scalar('"a\\\\b"') == "a\\b"
        assert pc_mod._parse_scalar('"hello"') == "hello"

    def test_parse_scalar_single_quoted_double_quote_escape(self) -> None:
        assert pc_mod._parse_scalar("'a''b'") == "a'b"
        assert pc_mod._parse_scalar("'hello'") == "hello"

    def test_parse_scalar_bare_string(self) -> None:
        assert pc_mod._parse_scalar("/some/path") == "/some/path"
        assert pc_mod._parse_scalar("C:\\Windows") == "C:\\Windows"


class TestSprint8E1CoverageProjectConfigStripComments:
    """``_strip_comments_and_blanks()`` 行内 # 处理。"""

    def test_strip_comments_basic(self) -> None:
        result = pc_mod._strip_comments_and_blanks("a: 1 # comment\nb: 2\n")
        assert result == ["a: 1", "b: 2"]

    def test_strip_comments_inline_quote_preserves_hash(self) -> None:
        result = pc_mod._strip_comments_and_blanks('a: "x # y"\nb: 2 # c\n')
        assert result == ['a: "x # y"', "b: 2"]

    def test_strip_comments_single_quote_preserves_hash(self) -> None:
        result = pc_mod._strip_comments_and_blanks("a: 'x # y'\n")
        assert result == ["a: 'x # y'"]

    def test_strip_comments_escaped_quote(self) -> None:
        result = pc_mod._strip_comments_and_blanks(r'a: "a\"#b"' + "\n")
        assert result == [r'a: "a\"#b"']

    def test_strip_comments_skips_blank_lines(self) -> None:
        result = pc_mod._strip_comments_and_blanks("a: 1\n\nb: 2\n")
        assert result == ["a: 1", "b: 2"]


class TestSprint8E1CoverageProjectConfigIndentOf:
    """``_indent_of()`` 各种缩进。"""

    def test_indent_of_with_spaces(self) -> None:
        assert pc_mod._indent_of("    a: 1") == 4

    def test_indent_of_no_indent(self) -> None:
        assert pc_mod._indent_of("a: 1") == 0

    def test_indent_of_empty_string(self) -> None:
        assert pc_mod._indent_of("") == 0

    def test_indent_of_with_tab_not_counted(self) -> None:
        assert pc_mod._indent_of("\tx: 1") == 0


class TestSprint8E1CoverageProjectConfigLoad:
    """``ProjectConfig.load()`` 三层合并 + 字段校验。"""

    def test_load_missing_all_configs_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ProjectConfigError, match="未找到 autoc.yaml"):
            ProjectConfig.load(cwd=tmp_path)

    def test_load_project_root_not_string_raises(self, tmp_path: Path) -> None:
        (tmp_path / ".autoc").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".autoc" / "autoc.yaml").write_text(
            "project_root:\n  - a\n  - b\n", encoding="utf-8"
        )
        with pytest.raises(ProjectConfigError, match="缺字段"):
            ProjectConfig.load(cwd=tmp_path)

    def test_load_tresos_home_not_string_raises(self, tmp_path: Path) -> None:
        (tmp_path / ".autoc").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".autoc" / "autoc.yaml").write_text(
            "project_root: /x\ntresos_home:\n  - a\n", encoding="utf-8"
        )
        with pytest.raises(ProjectConfigError, match="'tresos_home' 必须是字符串路径"):
            ProjectConfig.load(cwd=tmp_path)

    def test_load_extra_bswmd_paths_not_list_raises(self, tmp_path: Path) -> None:
        (tmp_path / ".autoc").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".autoc" / "autoc.yaml").write_text(
            "project_root: /x\nextra_bswmd_paths: not_a_list\n", encoding="utf-8",
        )
        with pytest.raises(ProjectConfigError, match="extra_bswmd_paths.*字符串列表"):
            ProjectConfig.load(cwd=tmp_path)

    def test_load_extra_bswmd_paths_item_not_string_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            pc_mod, "load_yaml",
            lambda _p: {"project_root": "/x", "extra_bswmd_paths": [123, "valid"]},
        )
        with pytest.raises(ProjectConfigError, match="列表元素必须是字符串"):
            ProjectConfig.load(cwd=tmp_path)

    def test_load_relative_project_root_resolved(self, tmp_path: Path) -> None:
        (tmp_path / ".autoc").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".autoc" / "autoc.yaml").write_text(
            "project_root: relative_subdir\n", encoding="utf-8"
        )
        (tmp_path / "relative_subdir").mkdir()
        cfg = ProjectConfig.load(cwd=tmp_path)
        assert cfg.project_root.is_absolute()
        assert cfg.project_root == (tmp_path / "relative_subdir").resolve()

    def test_load_three_layer_merge_local_overrides_user(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        user_yaml = tmp_path / "user.yaml"
        user_yaml.write_text(
            "project_root: /user_path\nextra_bswmd_paths:\n  - /u1\n", encoding="utf-8",
        )
        monkeypatch.setattr(pc_mod, "_USER_CONFIG", user_yaml)
        (tmp_path / ".autoc").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".autoc" / "autoc.yaml").write_text(
            "project_root: /local_path\n", encoding="utf-8"
        )
        cfg = ProjectConfig.load(cwd=tmp_path)
        assert "local_path" in str(cfg.project_root)
        assert any("u1" in str(p) for p in cfg.extra_bswmd_paths)


class TestSprint8E1CoverageProjectConfigWithExtraPath:
    """``with_extra_bswmd_path`` 不可变追加。"""

    def test_with_extra_bswmd_path_appends(self) -> None:
        cfg = ProjectConfig(
            project_root=Path("/x"), tresos_home=None,
            bswmd_root=Path("/x/.autoc/bswmd/r22"), extra_bswmd_paths=(),
        )
        new = cfg.with_extra_bswmd_path(Path("/y"))
        assert new.extra_bswmd_paths == (Path("/y"),)
        assert cfg.extra_bswmd_paths == ()


class TestSprint8E1CoverageProjectConfigToYaml:
    """``to_yaml()`` 序列化。"""

    def test_to_yaml_with_tresos_home(self) -> None:
        cfg = ProjectConfig(
            project_root=Path("/x"), tresos_home=Path("/tresos"),
            bswmd_root=Path("/x/.autoc/bswmd/r22"), extra_bswmd_paths=(),
        )
        text = cfg.to_yaml()
        assert 'project_root: "/x"' in text
        assert 'tresos_home: "/tresos"' in text
        assert "extra_bswmd_paths: []" in text

    def test_to_yaml_with_tresos_home_none(self) -> None:
        cfg = ProjectConfig(
            project_root=Path("/x"), tresos_home=None,
            bswmd_root=Path("/x/.autoc/bswmd/r22"), extra_bswmd_paths=(),
        )
        text = cfg.to_yaml()
        assert "tresos_home: null" in text

    def test_to_yaml_with_extra_paths(self) -> None:
        cfg = ProjectConfig(
            project_root=Path("/x"), tresos_home=None,
            bswmd_root=Path("/x/.autoc/bswmd/r22"),
            extra_bswmd_paths=(Path("/u1"), Path("/u2")),
        )
        text = cfg.to_yaml()
        assert "extra_bswmd_paths:" in text
        assert '"/u1"' in text
        assert '"/u2"' in text

    def test_to_yaml_quote_escapes_internal_quotes(self) -> None:
        cfg = ProjectConfig(
            project_root=Path('/x"y'), tresos_home=None,
            bswmd_root=Path("/x/.autoc/bswmd/r22"), extra_bswmd_paths=(),
        )
        text = cfg.to_yaml()
        assert '\\"y' in text


class TestSprint8E1CoverageProjectConfigModule:
    """模块级别 / 兼容性 sanity。"""

    def test_module_exports_expected_symbols(self) -> None:
        assert "ProjectConfig" in pc_mod.__all__
        assert "ProjectConfigError" in pc_mod.__all__
        assert "load_yaml" in pc_mod.__all__
        assert "default_tresos_home" in pc_mod.__all__

    def test_platform_module_actually_imported(self) -> None:
        assert hasattr(pc_mod, "platform")
        assert isinstance(pc_mod.platform.system(), str)

    def test_yaml_error_is_exception(self) -> None:
        assert issubclass(pc_mod._YAMLError, Exception)
        with pytest.raises(pc_mod._YAMLError):
            raise pc_mod._YAMLError("test")

    def test_project_config_error_is_runtime_error(self) -> None:
        assert issubclass(ProjectConfigError, RuntimeError)
        with pytest.raises(RuntimeError):
            raise ProjectConfigError("test")
