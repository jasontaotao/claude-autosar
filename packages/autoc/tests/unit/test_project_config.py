"""``ProjectConfig`` 单元测试。

契约 7：``TestProjectConfig`` 命名空间；测试函数 ``test_<method_or_behavior>_<expected_outcome>``。
fixture 放本文件 module 级（@pytest.fixture），不污染 conftest.py。
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

from claude_autosar.cli.commands.init import (
    _copy_bswmd_files,
    _scan_project_modules,
)
from claude_autosar.core.config.project_config import (
    ProjectConfig,
    ProjectConfigError,
    default_tresos_home,
    load_yaml,
)

# =============================================================================
# fixtures (module-local；不污染 conftest.py)
# =============================================================================


@pytest.fixture
def fake_project_root(tmp_path: Path) -> Path:
    """最小 EB tresos 工程目录（含 ``.prefs/`` + 1 个 xdm）。"""
    root = tmp_path / "MyECU"
    (root / ".prefs").mkdir(parents=True)
    (root / ".prefs" / "Mcu.xdm").write_text(
        '<?xml version="1.0"?><d:datamodel xmlns:d="http://www.3soft.de/xml/tresos/datamodel/1.0"/>',
        encoding="utf-8",
    )
    return root


@pytest.fixture
def fake_tresos_home(tmp_path: Path) -> Path:
    """最小 EB tresos 安装目录（含 ``BSWMD/`` + 2 个 ``*_Bswmd.arxml``）。"""
    home = tmp_path / "FlexCFG"
    bswmd_dir = home / "BSWMD"
    bswmd_dir.mkdir(parents=True)
    (bswmd_dir / "Mcu_Bswmd.arxml").write_text("<a/>", encoding="utf-8")
    (bswmd_dir / "Port_Bswmd.arxml").write_text("<a/>", encoding="utf-8")
    return home


@pytest.fixture
def local_yaml_path(fake_project_root: Path) -> Path:
    """``<fake_project_root>/.autoc/autoc.yaml``（不存在；测试自己写）。"""
    return fake_project_root / ".autoc" / "autoc.yaml"


@pytest.fixture
def user_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """隔离 ``~/.autoc/agent/`` 到 tmp_path。"""
    user_dir = tmp_path / "user-autoc" / "agent"
    user_dir.mkdir(parents=True)
    monkeypatch.setattr(
        "claude_autosar.core.config.project_config._USER_CONFIG",
        user_dir / "autoc.yaml",
    )
    return user_dir


# =============================================================================
# load_yaml / default_tresos_home
# =============================================================================


class TestLoadYaml:
    """极简 YAML 解析器（无 PyYAML 依赖）。"""

    def test_load_yaml_returns_dict_for_valid_simple_key_value(self, tmp_path: Path) -> None:
        """简单 key:value 解析正确。"""
        f = tmp_path / "x.yaml"
        f.write_text("project_root: 'C:/foo'\n", encoding="utf-8")
        assert load_yaml(f) == {"project_root": "C:/foo"}

    def test_load_yaml_returns_dict_for_quoted_strings(self, tmp_path: Path) -> None:
        """双引号字符串解引号。"""
        f = tmp_path / "x.yaml"
        f.write_text('project_root: "C:/foo bar"\n', encoding="utf-8")
        assert load_yaml(f) == {"project_root": "C:/foo bar"}

    def test_load_yaml_returns_dict_for_null_value(self, tmp_path: Path) -> None:
        """null 字段解析为 None。"""
        f = tmp_path / "x.yaml"
        f.write_text("tresos_home: null\n", encoding="utf-8")
        assert load_yaml(f) == {"tresos_home": None}

    def test_load_yaml_returns_dict_for_list_field(self, tmp_path: Path) -> None:
        """list[str] 字段解析。"""
        f = tmp_path / "x.yaml"
        f.write_text(
            "extra_bswmd_paths:\n" '  - "A:/p1"\n' '  - "B:/p2"\n',
            encoding="utf-8",
        )
        assert load_yaml(f) == {"extra_bswmd_paths": ["A:/p1", "B:/p2"]}

    def test_load_yaml_returns_empty_dict_when_file_missing(self, tmp_path: Path) -> None:
        """文件不存在 → 空 dict。"""
        assert load_yaml(tmp_path / "missing.yaml") == {}

    def test_load_yaml_ignores_comments(self, tmp_path: Path) -> None:
        """``#`` 注释行被忽略。"""
        f = tmp_path / "x.yaml"
        f.write_text(
            "# header comment\n" "project_root: 'C:/foo'  # trailing comment\n",
            encoding="utf-8",
        )
        assert load_yaml(f) == {"project_root": "C:/foo"}


class TestDefaultTresosHome:
    """平台默认 EB tresos 安装目录探测。"""

    def test_default_tresos_home_returns_none_when_platform_dir_missing(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """探测路径不存在时返回 None。"""
        # 强制 win32 分支并指向 tmp_path（不存在）
        monkeypatch.setattr(sys, "platform", "win32", raising=False)
        # 替换默认路径常量
        import claude_autosar.core.config.project_config as mod

        monkeypatch.setattr(
            mod,
            "_PLATFORM_DEFAULT_TRESOS_HOME_WIN",
            Path("/nonexistent_xyz_path"),
        )
        assert default_tresos_home() is None

    def test_default_tresos_home_returns_path_when_dir_exists(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """探测路径存在时返回该路径。"""
        import claude_autosar.core.config.project_config as mod

        monkeypatch.setattr(sys, "platform", "win32", raising=False)
        monkeypatch.setattr(
            mod,
            "_PLATFORM_DEFAULT_TRESOS_HOME_WIN",
            tmp_path,
        )
        assert default_tresos_home() == tmp_path.resolve()


# =============================================================================
# ProjectConfig.load() — 三层合并
# =============================================================================


class TestProjectConfigLoad:
    """``ProjectConfig.load()`` 三层合并（cwd 覆盖 user 覆盖 default）。"""

    def test_load_returns_empty_raises_when_no_config_anywhere(
        self,
        user_config_dir: Path,
        tmp_path: Path,
    ) -> None:
        """cwd 无 .autoc/autoc.yaml + user 无 → 抛 ProjectConfigError（D12 强制）。"""
        with pytest.raises(ProjectConfigError, match="autoc init"):
            ProjectConfig.load(cwd=tmp_path)

    def test_load_uses_cwd_local_config_when_present(
        self,
        local_yaml_path: Path,
        user_config_dir: Path,
        fake_project_root: Path,
    ) -> None:
        """工程本地 autoc.yaml 优先；user 即使有也被覆盖。"""
        # user-level 设一个值
        (user_config_dir / "autoc.yaml").write_text(
            'project_root: "C:/should/be/ignored"\n',
            encoding="utf-8",
        )
        # local 设另一个值
        local_yaml_path.parent.mkdir(parents=True, exist_ok=True)
        local_yaml_path.write_text(
            f'project_root: "{fake_project_root.as_posix()}"\n',
            encoding="utf-8",
        )
        cfg = ProjectConfig.load(cwd=fake_project_root)
        assert cfg.project_root == fake_project_root.resolve()

    def test_load_falls_back_to_user_level_when_cwd_missing(
        self,
        user_config_dir: Path,
        fake_project_root: Path,
        tmp_path: Path,
    ) -> None:
        """cwd 无配置时降级到 user-level。"""
        (user_config_dir / "autoc.yaml").write_text(
            f'project_root: "{fake_project_root.as_posix()}"\n',
            encoding="utf-8",
        )
        cfg = ProjectConfig.load(cwd=tmp_path)
        assert cfg.project_root == fake_project_root.resolve()

    def test_load_resolves_relative_project_root_against_cwd(
        self,
        fake_project_root: Path,
    ) -> None:
        """project_root 相对路径按 cwd 解析。"""
        # 把 .autoc/autoc.yaml 放在 cwd（fake_project_root.parent）下；
        # project_root 字段写成相对 'MyECU'，load 应解析为 <cwd>/MyECU
        cwd_dir = fake_project_root.parent
        local = cwd_dir / ".autoc" / "autoc.yaml"
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text(
            "project_root: 'MyECU'\n",
            encoding="utf-8",
        )
        cfg = ProjectConfig.load(cwd=cwd_dir)
        assert cfg.project_root == fake_project_root.resolve()

    def test_load_raises_when_project_root_field_missing(
        self,
        user_config_dir: Path,
        tmp_path: Path,
    ) -> None:
        """YAML 缺 project_root 字段 → 报错并指出字段。"""
        (user_config_dir / "autoc.yaml").write_text(
            "tresos_home: 'C:/FlexCFG'\n",
            encoding="utf-8",
        )
        with pytest.raises(ProjectConfigError, match="project_root"):
            ProjectConfig.load(cwd=tmp_path)

    def test_load_uses_platform_default_tresos_home_when_field_missing(
        self,
        user_config_dir: Path,
        fake_project_root: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """缺 tresos_home 字段 → 走 default_tresos_home()。"""
        import claude_autosar.core.config.project_config as mod

        monkeypatch.setattr(sys, "platform", "win32", raising=False)
        monkeypatch.setattr(
            mod,
            "_PLATFORM_DEFAULT_TRESOS_HOME_WIN",
            Path("/nonexistent_xyz"),
        )
        (user_config_dir / "autoc.yaml").write_text(
            f'project_root: "{fake_project_root.as_posix()}"\n',
            encoding="utf-8",
        )
        cfg = ProjectConfig.load(cwd=tmp_path)
        assert cfg.tresos_home is None  # 平台默认路径不存在 → None

    def test_load_reads_optional_tresos_home_explicitly(
        self,
        local_yaml_path: Path,
        fake_project_root: Path,
        fake_tresos_home: Path,
    ) -> None:
        """显式 tresos_home 字段被读取。"""
        local_yaml_path.parent.mkdir(parents=True, exist_ok=True)
        local_yaml_path.write_text(
            f'project_root: "{fake_project_root.as_posix()}"\n'
            f'tresos_home: "{fake_tresos_home.as_posix()}"\n',
            encoding="utf-8",
        )
        cfg = ProjectConfig.load(cwd=fake_project_root)
        assert cfg.tresos_home == fake_tresos_home.resolve()

    def test_load_reads_extra_bswmd_paths_list(
        self,
        local_yaml_path: Path,
        fake_project_root: Path,
        tmp_path: Path,
    ) -> None:
        """``extra_bswmd_paths`` 列表解析正确。"""
        p1 = tmp_path / "sdk1"
        p2 = tmp_path / "sdk2"
        local_yaml_path.parent.mkdir(parents=True, exist_ok=True)
        local_yaml_path.write_text(
            f'project_root: "{fake_project_root.as_posix()}"\n'
            "extra_bswmd_paths:\n"
            f'  - "{p1.as_posix()}"\n'
            f'  - "{p2.as_posix()}"\n',
            encoding="utf-8",
        )
        cfg = ProjectConfig.load(cwd=fake_project_root)
        assert cfg.extra_bswmd_paths == (p1.resolve(), p2.resolve())

    def test_load_sets_bswmd_root_to_project_dot_autoc_bswmd_r22(
        self,
        local_yaml_path: Path,
        fake_project_root: Path,
    ) -> None:
        """``bswmd_root`` 默认 ``<project_root>/.autoc/bswmd/r22/``。"""
        local_yaml_path.parent.mkdir(parents=True, exist_ok=True)
        local_yaml_path.write_text(
            f'project_root: "{fake_project_root.as_posix()}"\n',
            encoding="utf-8",
        )
        cfg = ProjectConfig.load(cwd=fake_project_root)
        assert cfg.bswmd_root == (fake_project_root / ".autoc" / "bswmd" / "r22").resolve()


# =============================================================================
# with_extra_bswmd_path（不可变）
# =============================================================================


class TestProjectConfigWithExtra:
    """``with_extra_bswmd_path`` 不可变追加。"""

    def test_with_extra_bswmd_path_returns_new_instance(
        self,
        fake_project_root: Path,
    ) -> None:
        cfg = ProjectConfig(
            project_root=fake_project_root,
            tresos_home=None,
            bswmd_root=fake_project_root / ".autoc" / "bswmd" / "r22",
        )
        new_cfg = cfg.with_extra_bswmd_path(Path("D:/sdk"))
        assert new_cfg is not cfg
        assert new_cfg.extra_bswmd_paths == (Path("D:/sdk").expanduser(),)

    def test_with_extra_bswmd_path_appends_to_existing(
        self,
        fake_project_root: Path,
    ) -> None:
        cfg = ProjectConfig(
            project_root=fake_project_root,
            tresos_home=None,
            bswmd_root=fake_project_root / ".autoc" / "bswmd" / "r22",
            extra_bswmd_paths=(Path("D:/a"),),
        )
        new_cfg = cfg.with_extra_bswmd_path(Path("D:/b"))
        assert new_cfg.extra_bswmd_paths == (
            Path("D:/a").expanduser(),
            Path("D:/b").expanduser(),
        )


# =============================================================================
# to_yaml（契约 6 schema）
# =============================================================================


class TestProjectConfigToYaml:
    """``to_yaml()`` 序列化为契约 6 描述的 autoc.yaml schema。"""

    def test_to_yaml_includes_required_project_root(
        self,
        fake_project_root: Path,
    ) -> None:
        cfg = ProjectConfig(
            project_root=fake_project_root,
            tresos_home=None,
            bswmd_root=fake_project_root / ".autoc" / "bswmd" / "r22",
        )
        text = cfg.to_yaml()
        assert 'project_root: "' in text
        assert fake_project_root.as_posix() in text

    def test_to_yaml_includes_tresos_home_when_set(
        self,
        fake_project_root: Path,
        fake_tresos_home: Path,
    ) -> None:
        cfg = ProjectConfig(
            project_root=fake_project_root,
            tresos_home=fake_tresos_home,
            bswmd_root=fake_project_root / ".autoc" / "bswmd" / "r22",
        )
        text = cfg.to_yaml()
        assert 'tresos_home: "' in text
        assert fake_tresos_home.as_posix() in text

    def test_to_yaml_renders_tresos_home_as_null_when_none(
        self,
        fake_project_root: Path,
    ) -> None:
        cfg = ProjectConfig(
            project_root=fake_project_root,
            tresos_home=None,
            bswmd_root=fake_project_root / ".autoc" / "bswmd" / "r22",
        )
        text = cfg.to_yaml()
        assert "tresos_home: null" in text

    def test_to_yaml_renders_extra_bswmd_paths_as_yaml_list(
        self,
        fake_project_root: Path,
    ) -> None:
        cfg = ProjectConfig(
            project_root=fake_project_root,
            tresos_home=None,
            bswmd_root=fake_project_root / ".autoc" / "bswmd" / "r22",
            extra_bswmd_paths=(Path("D:/sdk1"), Path("D:/sdk2")),
        )
        text = cfg.to_yaml()
        assert "extra_bswmd_paths:" in text
        assert '  - "D:/sdk1"' in text
        assert '  - "D:/sdk2"' in text

    def test_to_yaml_round_trips_via_load(
        self,
        fake_project_root: Path,
        fake_tresos_home: Path,
        user_config_dir: Path,
    ) -> None:
        """to_yaml → 写到临时文件 → load(cwd) → 字段一致。"""
        cfg = ProjectConfig(
            project_root=fake_project_root,
            tresos_home=fake_tresos_home,
            bswmd_root=fake_project_root / ".autoc" / "bswmd" / "r22",
            extra_bswmd_paths=(Path("D:/sdk1"),),
        )
        # 写到一个独立目录，load 用该目录当 cwd
        target = fake_project_root / ".autoc"
        target.mkdir(parents=True, exist_ok=True)
        (target / "autoc.yaml").write_text(cfg.to_yaml(), encoding="utf-8")
        cfg2 = ProjectConfig.load(cwd=fake_project_root)
        assert cfg2.project_root == fake_project_root.resolve()
        assert cfg2.tresos_home == fake_tresos_home.resolve()
        assert cfg2.extra_bswmd_paths == (Path("D:/sdk1").expanduser(),)


# =============================================================================
# BSWMD copy 辅助
# =============================================================================


class TestBswmdCopy:
    """``_copy_bswmd_files`` 行为。"""

    def test_copy_bswmd_files_copies_all_bswmd_sources(
        self,
        fake_tresos_home: Path,
        tmp_path: Path,
    ) -> None:
        """把 ``*_Bswmd.arxml`` 全部复制到 ``<target>/<module>/``。"""
        target = tmp_path / "bswmd"
        copied, skipped, errors = _copy_bswmd_files(
            tresos_home=fake_tresos_home,
            target_root=target,
            refresh=False,
        )
        assert errors == []
        assert copied == 2
        assert skipped == 0
        assert (target / "Mcu" / "Mcu_Bswmd.arxml").is_file()
        assert (target / "Port" / "Port_Bswmd.arxml").is_file()

    def test_copy_bswmd_files_skips_existing_when_mtime_unchanged(
        self,
        fake_tresos_home: Path,
        tmp_path: Path,
    ) -> None:
        """mtime 未变 → 跳过。"""
        target = tmp_path / "bswmd"
        copied, skipped, errors = _copy_bswmd_files(
            tresos_home=fake_tresos_home,
            target_root=target,
            refresh=False,
        )
        # 第二次
        copied2, skipped2, _ = _copy_bswmd_files(
            tresos_home=fake_tresos_home,
            target_root=target,
            refresh=False,
        )
        assert copied == 2
        assert skipped == 0
        assert copied2 == 0
        assert skipped2 == 2

    def test_copy_bswmd_files_refresh_flag_forces_re_copy(
        self,
        fake_tresos_home: Path,
        tmp_path: Path,
    ) -> None:
        """``--refresh-bswmd`` 强制重 copy。"""
        target = tmp_path / "bswmd"
        _copy_bswmd_files(
            tresos_home=fake_tresos_home,
            target_root=target,
            refresh=False,
        )
        copied, skipped, _ = _copy_bswmd_files(
            tresos_home=fake_tresos_home,
            target_root=target,
            refresh=True,
        )
        assert copied == 2
        assert skipped == 0

    def test_copy_bswmd_files_handles_missing_bswmd_dir(
        self,
        tmp_path: Path,
    ) -> None:
        """``<tresos_home>/BSWMD`` 不存在 → 0 复制 + 1 error。"""
        home = tmp_path / "EmptyHome"
        home.mkdir()
        copied, skipped, errors = _copy_bswmd_files(
            tresos_home=home,
            target_root=tmp_path / "bswmd",
            refresh=False,
        )
        assert copied == 0
        assert skipped == 0
        assert len(errors) == 1


# =============================================================================
# _scan_project_modules（init 验证步骤）
# =============================================================================


class TestScanProjectModules:
    """工程验证：扫 ``.prefs/`` 下的 xdm / arxml 找模块。"""

    def test_scan_returns_unique_module_names(self, tmp_path: Path) -> None:
        """``Mcu.xdm``、``Port.xdm``、``Mcu_Cfg.xdm`` → ``['Mcu', 'Port']``。"""
        prefs = tmp_path / ".prefs"
        prefs.mkdir()
        (prefs / "Mcu.xdm").write_text("<a/>", encoding="utf-8")
        (prefs / "Mcu_Cfg.xdm").write_text("<a/>", encoding="utf-8")
        (prefs / "Port.xdm").write_text("<a/>", encoding="utf-8")
        assert _scan_project_modules(tmp_path) == ["Mcu", "Port"]

    def test_scan_returns_empty_when_no_prefs_dir(self, tmp_path: Path) -> None:
        """无 ``.prefs/`` → 空 list。"""
        assert _scan_project_modules(tmp_path) == []

    def test_scan_includes_arxml_files(self, tmp_path: Path) -> None:
        """``.arxml`` 文件也被识别为模块。"""
        prefs = tmp_path / ".prefs"
        prefs.mkdir()
        (prefs / "Can.arxml").write_text("<a/>", encoding="utf-8")
        assert _scan_project_modules(tmp_path) == ["Can"]
