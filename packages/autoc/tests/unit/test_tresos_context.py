"""EcuConfigProjectContext.discover() 测试 — MCU 差异化核心。

这个测试同时跑 S32K3 / TC3xx / RH850 三种不同芯片的工程 fixture，
目的是证明 ``discover()`` 对所有芯片走同一段代码，**没有任何
``if derivate == "S32K3"`` 之类的分支**。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_autosar.adapters.tresos import TresosAdapter, TresosAdapterError

# =============================================================================
# 工厂 fixture 验证
# =============================================================================


class TestFakeProjectFactories:
    """验证 conftest 的 fake 工程工厂确实生成了正确的结构。"""

    def test_s32k3_has_tresos_style_project(self, fake_s32k3_project: tuple[Path, Path]) -> None:
        """S32K3 .project 是 EB tresos 风格。"""
        project, _ = fake_s32k3_project
        project_xml = (project / ".project").read_text(encoding="utf-8")
        assert "tresos:property" in project_xml
        assert "S32K344" in project_xml
        assert "AutosarVersion" in project_xml

    def test_tc3xx_has_tresos_style_project(self, fake_tc3xx_project: tuple[Path, Path]) -> None:
        """TC3xx .project 是 EB tresos 风格。"""
        project, _ = fake_tc3xx_project
        project_xml = (project / ".project").read_text(encoding="utf-8")
        assert "tresos:property" in project_xml
        assert "TC38XQ" in project_xml

    def test_rh850_has_simple_style_project(self, fake_rh850_project: tuple[Path, Path]) -> None:
        """RH850 .project 是简化风格。"""
        project, _ = fake_rh850_project
        project_xml = (project / ".project").read_text(encoding="utf-8")
        assert "tresos:property" not in project_xml  # 简化风格不带 namespace
        assert "<target>RH850</target>" in project_xml
        assert "<derivate>R7F701Z3</derivate>" in project_xml

    def test_prefs_populated(self, fake_s32k3_project: tuple[Path, Path]) -> None:
        """.prefs/ 下应有模块 .xdm 文件。"""
        project, _ = fake_s32k3_project
        prefs = project / ".prefs"
        assert prefs.is_dir()
        xdm_files = list(prefs.glob("*.xdm"))
        names = {f.stem.replace("_Cfg", "") for f in xdm_files}
        assert "Mcu" in names
        assert "Port" in names
        assert "Can" in names


# =============================================================================
# discover() 行为 — 跨芯片统一代码路径
# =============================================================================


@pytest.mark.parametrize(
    ("project_fixture", "expected_target", "expected_derivate", "expected_version"),
    [
        ("fake_s32k3_project", "ARM", "S32K344", "4.4.0"),
        ("fake_tc3xx_project", "TC38XQ", "TC38XQ", "4.2.2"),
        ("fake_rh850_project", "RH850", "R7F701Z3", "4.0.3"),
    ],
)
class TestDiscoverAcrossChips:
    """同一段代码处理 S32K3 / TC3xx / RH850。"""

    def test_discover_extracts_target(
        self,
        project_fixture: str,
        expected_target: str,
        expected_derivate: str,
        expected_version: str,
        request: pytest.FixtureRequest,
    ) -> None:
        """discover() 正确提取 target。"""
        project_path, tool_home = request.getfixturevalue(project_fixture)
        ctx = TresosAdapter().discover(project_path, tool_home)
        assert ctx.target == expected_target

    def test_discover_extracts_derivate(
        self,
        project_fixture: str,
        expected_target: str,
        expected_derivate: str,
        expected_version: str,
        request: pytest.FixtureRequest,
    ) -> None:
        """discover() 正确提取 derivate。"""
        project_path, tool_home = request.getfixturevalue(project_fixture)
        ctx = TresosAdapter().discover(project_path, tool_home)
        assert ctx.derivate == expected_derivate

    def test_discover_extracts_autosar_version(
        self,
        project_fixture: str,
        expected_target: str,
        expected_derivate: str,
        expected_version: str,
        request: pytest.FixtureRequest,
    ) -> None:
        """discover() 正确提取 autosar_version。"""
        project_path, tool_home = request.getfixturevalue(project_fixture)
        ctx = TresosAdapter().discover(project_path, tool_home)
        assert ctx.autosar_version == expected_version

    def test_discover_lists_enabled_modules(
        self,
        project_fixture: str,
        expected_target: str,
        expected_derivate: str,
        expected_version: str,
        request: pytest.FixtureRequest,
    ) -> None:
        """discover() 正确列出 .prefs/ 里的模块（按字母序、tuple 不可变）。"""
        project_path, tool_home = request.getfixturevalue(project_fixture)
        ctx = TresosAdapter().discover(project_path, tool_home)
        # 至少含 Mcu（所有芯片都有）
        assert "Mcu" in ctx.enabled_modules
        # 是 tuple
        assert isinstance(ctx.enabled_modules, tuple)
        # 已排序
        assert list(ctx.enabled_modules) == sorted(ctx.enabled_modules)

    def test_discover_lists_bswmd_plugins(
        self,
        project_fixture: str,
        expected_target: str,
        expected_derivate: str,
        expected_version: str,
        request: pytest.FixtureRequest,
    ) -> None:
        """discover() 扫出 plugins/ 下所有 _bswmd.arxml。"""
        project_path, tool_home = request.getfixturevalue(project_fixture)
        ctx = TresosAdapter().discover(project_path, tool_home)
        assert len(ctx.available_plugins) > 0
        for p in ctx.available_plugins:
            assert p.name.endswith("_bswmd.arxml")


# =============================================================================
# 错误路径
# =============================================================================


class TestDiscoverErrors:
    """discover() 错误处理。"""

    def test_missing_project_file(self, tmp_path: Path) -> None:
        """没有 .project 时抛 TresosAdapterError。"""
        project = tmp_path / "empty"
        project.mkdir()
        home = tmp_path / "h"
        home.mkdir()
        with pytest.raises(TresosAdapterError, match="no .project"):
            TresosAdapter().discover(project, home)

    @pytest.mark.parametrize("alt_name", ["project.xml", ".project.xml"])
    def test_alternate_project_file_names(self, tmp_path: Path, alt_name: str) -> None:
        """``project.xml`` 和 ``.project.xml`` 也被识别。"""
        project = tmp_path / "alt"
        project.mkdir()
        (project / alt_name).write_text(
            """<?xml version="1.0"?>
<project>
  <target>ARM</target>
  <derivate>X</derivate>
  <autosarVersion>4.4.0</autosarVersion>
</project>
""",
            encoding="utf-8",
        )
        home = tmp_path / "h"
        home.mkdir()
        ctx = TresosAdapter().discover(project, home)
        assert ctx.derivate == "X"

    def test_dot_project_wins_over_alternates(self, tmp_path: Path) -> None:
        """``<project>/.project`` 优先于 ``project.xml``/``.project.xml``。"""
        project = tmp_path / "both"
        project.mkdir()
        (project / ".project").write_text(
            """<?xml version="1.0"?>
<project>
  <target>ARM</target>
  <derivate>PRIMARY</derivate>
  <autosarVersion>4.4.0</autosarVersion>
</project>
""",
            encoding="utf-8",
        )
        (project / "project.xml").write_text(
            """<?xml version="1.0"?>
<project>
  <target>ARM</target>
  <derivate>SECONDARY</derivate>
  <autosarVersion>4.4.0</autosarVersion>
</project>
""",
            encoding="utf-8",
        )
        home = tmp_path / "h"
        home.mkdir()
        ctx = TresosAdapter().discover(project, home)
        assert ctx.derivate == "PRIMARY"

    def test_missing_tool_home(self, tmp_path: Path) -> None:
        """tool_home 不是目录时抛 TresosAdapterError。"""
        bogus_home = tmp_path / "bogus"
        bogus_project = tmp_path / "p"
        bogus_project.mkdir()
        with pytest.raises(TresosAdapterError, match="tool_home is not a directory"):
            TresosAdapter().discover(bogus_project, bogus_home)

    def test_missing_project_dir(self, tmp_path: Path) -> None:
        """project_path 不是目录时抛 TresosAdapterError。"""
        bogus = tmp_path / "nope"
        home = tmp_path / "h"
        home.mkdir()
        with pytest.raises(TresosAdapterError, match="project_path is not a directory"):
            TresosAdapter().discover(bogus, home)

    def test_malformed_project_xml(self, tmp_path: Path) -> None:
        """.project 是非法 XML 时抛 TresosAdapterError。"""
        project = tmp_path / "bad"
        project.mkdir()
        (project / ".project").write_text("not valid xml<", encoding="utf-8")
        home = tmp_path / "h"
        home.mkdir()
        with pytest.raises(TresosAdapterError, match="malformed"):
            TresosAdapter().discover(project, home)


# =============================================================================
# .prefs 解析细节
# =============================================================================


class TestListEnabledModules:
    """_list_enabled_modules_from_prefs 单元行为。"""

    def test_empty_prefs_dir(self, tmp_path: Path) -> None:
        """.prefs/ 不存在时返回空 tuple。"""
        result = TresosAdapter._list_enabled_modules_from_prefs(tmp_path)
        assert result == ()

    def test_strips_cfg_suffix(self, tmp_path: Path) -> None:
        """``Mcu_Cfg.xdm`` → 模块名 ``Mcu``。"""
        prefs = tmp_path / ".prefs"
        prefs.mkdir()
        (prefs / "Mcu_Cfg.xdm").write_text("x", encoding="utf-8")
        (prefs / "Port_Cfg.xdm").write_text("x", encoding="utf-8")
        result = TresosAdapter._list_enabled_modules_from_prefs(tmp_path)
        assert result == ("Mcu", "Port")

    def test_keeps_module_without_cfg_suffix(self, tmp_path: Path) -> None:
        """``Mcu.xdm``（无 _Cfg）→ 模块名 ``Mcu``。"""
        prefs = tmp_path / ".prefs"
        prefs.mkdir()
        (prefs / "Mcu.xdm").write_text("x", encoding="utf-8")
        result = TresosAdapter._list_enabled_modules_from_prefs(tmp_path)
        assert result == ("Mcu",)

    def test_dedupes(self, tmp_path: Path) -> None:
        """同名模块（不同后缀）去重。"""
        prefs = tmp_path / ".prefs"
        prefs.mkdir()
        (prefs / "Mcu_Cfg.xdm").write_text("x", encoding="utf-8")
        (prefs / "Mcu.xdm").write_text("x", encoding="utf-8")
        result = TresosAdapter._list_enabled_modules_from_prefs(tmp_path)
        assert result == ("Mcu",)


# =============================================================================
# 插件扫描
# =============================================================================


class TestListBswmdPlugins:
    """_list_bswmd_plugins 单元行为。"""

    def test_no_plugins_dir(self, tmp_path: Path) -> None:
        """plugins/ 不存在时返回空。"""
        result = TresosAdapter._list_bswmd_plugins(tmp_path)
        assert result == ()

    def test_finds_bswmd_files(self, tmp_path: Path) -> None:
        """扫出所有 _bswmd.arxml。"""
        plugins = tmp_path / "plugins"
        plugins.mkdir()
        (plugins / "Mcu_S32K3_bswmd.arxml").write_text("x", encoding="utf-8")
        (plugins / "Port_bswmd.arxml").write_text("x", encoding="utf-8")
        (plugins / "README.md").write_text("x", encoding="utf-8")  # 噪声
        result = TresosAdapter._list_bswmd_plugins(tmp_path)
        assert len(result) == 2
        assert all(p.name.endswith("_bswmd.arxml") for p in result)

    def test_finds_in_subdirs(self, tmp_path: Path) -> None:
        """递归扫子目录。"""
        plugins = tmp_path / "plugins"
        sub = plugins / "Mcu_S32K3"
        sub.mkdir(parents=True)
        (sub / "Mcu_S32K3_bswmd.arxml").write_text("x", encoding="utf-8")
        result = TresosAdapter._list_bswmd_plugins(tmp_path)
        assert len(result) == 1
