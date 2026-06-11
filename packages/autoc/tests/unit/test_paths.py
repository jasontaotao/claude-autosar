"""路径工具单元测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from autoc.utils.paths import (
    APP_AUTHOR,
    APP_NAME,
    find_ancestor_file,
    global_config_dir,
    global_data_dir,
    global_log_dir,
    global_session_dir,
    normalize_path,
    project_config_dir,
)

# =============================================================================
# 全局目录
# =============================================================================


class TestGlobalDirs:
    """全局目录（由 platformdirs 决定）。"""

    def test_global_config_dir_exists(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """global_config_dir 返回的目录应当存在。"""
        monkeypatch.setattr(
            "autoc.utils.paths.user_config_dir",
            lambda *a, **kw: str(tmp_path / "cfg"),
        )
        result = global_config_dir()
        assert result.is_dir()
        assert result.parent == tmp_path

    def test_global_session_dir_is_under_config(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """global_session_dir 在 config_dir/sessions 下。"""
        monkeypatch.setattr(
            "autoc.utils.paths.user_config_dir",
            lambda *a, **kw: str(tmp_path / "cfg"),
        )
        result = global_session_dir()
        assert result.name == "sessions"
        assert result.parent == global_config_dir()

    def test_global_data_dir_exists(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """global_data_dir 返回的目录应当存在。"""
        monkeypatch.setattr(
            "autoc.utils.paths.user_data_dir",
            lambda *a, **kw: str(tmp_path / "data"),
        )
        result = global_data_dir()
        assert result.is_dir()

    def test_global_log_dir_exists(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """global_log_dir 返回的目录应当存在。"""
        monkeypatch.setattr(
            "autoc.utils.paths.user_log_dir",
            lambda *a, **kw: str(tmp_path / "logs"),
        )
        result = global_log_dir()
        assert result.is_dir()

    def test_app_constants(self) -> None:
        """APP_NAME / APP_AUTHOR 符合预期。"""
        assert APP_NAME == "autoc"
        assert APP_AUTHOR == "autoc-tool"


# =============================================================================
# project_config_dir
# =============================================================================


class TestProjectConfigDir:
    """项目级配置目录。"""

    def test_creates_dir_under_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """不传 cwd 时用 Path.cwd()，创建 .autoc 目录。"""
        monkeypatch.chdir(tmp_path)
        result = project_config_dir()
        assert result == tmp_path / ".autoc"
        assert result.is_dir()

    def test_creates_dir_under_explicit_cwd(self, tmp_path: Path) -> None:
        """传 cwd 时在该目录下创建 .autoc。"""
        result = project_config_dir(tmp_path)
        assert result == tmp_path / ".autoc"
        assert result.is_dir()

    def test_accepts_string_path(self, tmp_path: Path) -> None:
        """cwd 接受 str 路径。"""
        result = project_config_dir(str(tmp_path))
        assert result == tmp_path / ".autoc"

    def test_idempotent(self, tmp_path: Path) -> None:
        """重复调用不报错。"""
        project_config_dir(tmp_path)
        project_config_dir(tmp_path)
        assert (tmp_path / ".autoc").is_dir()


# =============================================================================
# find_ancestor_file
# =============================================================================


class TestFindAncestorFile:
    """向上查找文件。"""

    def test_finds_file_in_current_dir(self, tmp_path: Path) -> None:
        """当前目录存在目标文件。"""
        (tmp_path / "AGENTS.md").write_text("x", encoding="utf-8")
        result = find_ancestor_file("AGENTS.md", tmp_path)
        assert result == tmp_path / "AGENTS.md"

    def test_finds_file_in_parent(self, tmp_path: Path) -> None:
        """父目录存在目标文件。"""
        (tmp_path / "AGENTS.md").write_text("x", encoding="utf-8")
        sub = tmp_path / "sub" / "deeper"
        sub.mkdir(parents=True)
        result = find_ancestor_file("AGENTS.md", sub)
        assert result == tmp_path / "AGENTS.md"

    def test_returns_none_when_not_found(self, tmp_path: Path) -> None:
        """找不到返回 None（不抛）。"""
        sub = tmp_path / "sub"
        sub.mkdir()
        result = find_ancestor_file("AGENTS.md", sub)
        assert result is None

    def test_accepts_string_path(self, tmp_path: Path) -> None:
        """start 接受 str。"""
        (tmp_path / "x").write_text("y", encoding="utf-8")
        result = find_ancestor_file("x", str(tmp_path))
        assert result == tmp_path / "x"

    def test_searches_to_filesystem_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """从根目录查找，目标不在应返回 None，不报错。"""
        monkeypatch.chdir(tmp_path)
        result = find_ancestor_file("definitely_not_exists_xyz_123.md")
        assert result is None


# =============================================================================
# normalize_path
# =============================================================================


class TestNormalizePath:
    """路径规范化。"""

    def test_expand_user(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """~ 展开为 home。"""
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))  # Windows
        result = normalize_path("~/file.txt")
        assert result == (tmp_path / "file.txt").resolve()

    def test_expand_env_var(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """环境变量展开。"""
        monkeypatch.setenv("MY_TEST_DIR", str(tmp_path))
        result = normalize_path("$MY_TEST_DIR/sub.txt")
        assert result == (tmp_path / "sub.txt").resolve()

    def test_resolve_relative(self, tmp_path: Path) -> None:
        """相对路径解析为绝对。"""
        result = normalize_path(tmp_path / "relative.txt")
        assert result.is_absolute()
        assert result == (tmp_path / "relative.txt").resolve()

    def test_accepts_path_object(self, tmp_path: Path) -> None:
        """接受 Path 对象。"""
        result = normalize_path(tmp_path)
        assert result.is_absolute()
        assert result == tmp_path.resolve()
