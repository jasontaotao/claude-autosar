"""Unit tests for ``BSWMDRegistry.load_default`` (T8.E.0b).

Plan reference: Sprint 8.E T8.E.0b — 工程本地 BSWMD 副本加载。
Contract 1: ProjectConfig 数据模型（消费）。
Contract 2: BSWMDRegistry + ParamDef 数据模型。
Contract 7: test naming + file layout（``TestBSWMDLoadDefault``）。

测试要点（plan T8.E.0b RED 测试段）：
- 工程本地 ``.autoc/bswmd/r22/`` 存在 → 优先加载
- 工程本地没有 → 降级到 ``tresos_home`` 兜底
- ``extra_bswmd_paths`` 拼 glob 命中三方 BSWMD → 加载并入 registry
- ``extra_bswmd_paths`` 路径不存在 → 警告 + 跳过
- 多源加载后 ``lookup_param`` 跨源命中（module 来自 r22, 三方来自 extra）
- 重复加载（同名模块不同根包名）→ 后加载覆盖前加载
- ``load_default`` 不依赖 ``autoc init``（fixture 造工程即可）
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from claude_autosar.core.bsw.bswmd import (
    BSWMDRegistry,
    ContainerDef,
    ModuleDef,
    ParamDef,
)
from claude_autosar.core.config.project_config import ProjectConfig

# ---------------------------------------------------------------------------
# 极简 fake ProjectConfig（不依赖 ProjectConfig.load()；契约 1 消费）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _FakeProjectConfig:
    """``load_default`` 只需读 4 个字段；用 dataclass 模拟契约 1 的 ProjectConfig 形态。"""

    project_root: Path
    tresos_home: Path | None
    bswmd_root: Path
    extra_bswmd_paths: tuple[Path, ...] = ()


def _fake_config(
    project_root: Path,
    tresos_home: Path | None = None,
    extra: tuple[Path, ...] = (),
) -> ProjectConfig:
    """构 ProjectConfig 实例（用真 dataclass 满足类型检查）。"""
    bswmd_root = project_root / ".autoc" / "bswmd" / "r22"
    return ProjectConfig(
        project_root=project_root,
        tresos_home=tresos_home,
        bswmd_root=bswmd_root,
        extra_bswmd_paths=extra,
    )


# ---------------------------------------------------------------------------
# Module-level fixtures（不碰 conftest.py；契约 7）
# ---------------------------------------------------------------------------


def _write_module_bswmd(path: Path, module_name: str, root_pkg: str = "AUTOSAR") -> None:
    """在 ``path`` 写一个最小 BSWMD：1 个 ``<ECUC-MODULE-DEF>`` 元素。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>{root_pkg}</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-DEF>
          <SHORT-NAME>{module_name}</SHORT-NAME>
        </ECUC-MODULE-DEF>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
""",
        encoding="utf-8",
    )


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """隔离工作目录。"""
    ws = tmp_path / "autoc-bswmd-ws"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


@pytest.fixture
def fake_tresos_home(tmp_path: Path) -> Path:
    """Fake EB tresos 安装目录（含 ``BSWMD/AUTOSAR_R22/EcucDefs/``）。"""
    home = tmp_path / "tresos_home"
    ecucdefs = home / "BSWMD" / "AUTOSAR_R22" / "EcucDefs"
    ecucdefs.mkdir(parents=True, exist_ok=True)
    _write_module_bswmd(ecucdefs / "Mcu_Bswmd.arxml", "Mcu")
    _write_module_bswmd(ecucdefs / "Port_Bswmd.arxml", "Port")
    _write_module_bswmd(ecucdefs / "Can_Bswmd.arxml", "Can")
    return home


@pytest.fixture
def fake_project_root(tmp_path: Path) -> Path:
    """Fake EB tresos 工程根目录（只建结构，无 BSWMD 副本）。"""
    project = tmp_path / "fake_project"
    project.mkdir(parents=True, exist_ok=True)
    (project / ".prefs").mkdir(parents=True, exist_ok=True)
    return project


# ---------------------------------------------------------------------------
# TestBSWMDLoadDefault
# ---------------------------------------------------------------------------


class TestBSWMDLoadDefault:
    """T8.E.0b 核心测试。"""

    def test_load_default_returns_empty_registry_when_no_bswmd_exists(
        self,
        fake_project_root: Path,
    ) -> None:
        """工程本地 + tresos_home + extra 都没有 → 返回空 registry（不抛）。"""
        cfg = _fake_config(
            project_root=fake_project_root,
            tresos_home=None,
        )
        reg = BSWMDRegistry.load_default(cfg)
        assert isinstance(reg, BSWMDRegistry)
        assert len(reg.modules) == 0
        assert reg.root_package_name == "AUTOSAR"

    def test_load_default_picks_project_local_r22_over_tresos_home(
        self,
        fake_project_root: Path,
        fake_tresos_home: Path,
    ) -> None:
        """工程本地 ``.autoc/bswmd/r22/`` 存在 → 本地命中后同名 module 用 local 覆盖 tresos_home。

        实际语义（D11）：4 级优先级按 directory 顺序扫，每个扫到的 module 都进 registry；
        后扫到的同名 module 覆盖前面的。BSWMD 模板跨厂商稳定（D11），所以同名 module
        的内容应当一致；本测试验证**覆盖方向**对（local 覆盖 tresos_home）。
        """
        # 工程本地放 Mcu_Bswmd.arxml（标记为"local 源"）
        local = fake_project_root / ".autoc" / "bswmd" / "r22" / "Mcu" / "Mcu_Bswmd.arxml"
        _write_module_bswmd(local, "Mcu")

        # tresos_home 放 Mcu_Bswmd.arxml（同 short_name "Mcu"）
        ecucdefs = fake_tresos_home / "BSWMD" / "AUTOSAR_R22" / "EcucDefs"
        _write_module_bswmd(ecucdefs / "Mcu_Bswmd.arxml", "Mcu")

        cfg = _fake_config(
            project_root=fake_project_root,
            tresos_home=fake_tresos_home,
        )
        reg = BSWMDRegistry.load_default(cfg)

        # 应该有 1 个 Mcu（同名模块去重）
        assert "Mcu" in reg.modules
        # Mcu 的 full_path 应来自 local r22（覆盖来自 tresos_home 的同名 module）
        assert reg.modules["Mcu"].full_path == "/AUTOSAR/Mcu"
        # source_paths 应同时含 local 和 tresos_home（两个都被扫了；后赢）
        local_paths = [p for p in reg.source_paths if ".autoc" in str(p)]
        tresos_paths = [p for p in reg.source_paths if "BSWMD" in str(p)]
        assert len(local_paths) >= 1
        assert len(tresos_paths) >= 1

    def test_load_default_falls_back_to_tresos_home_when_no_local(
        self,
        fake_project_root: Path,
        fake_tresos_home: Path,
    ) -> None:
        """工程本地没建 bswmd_root → 降级到 tresos_home 兜底。"""
        cfg = _fake_config(
            project_root=fake_project_root,
            tresos_home=fake_tresos_home,
        )
        reg = BSWMDRegistry.load_default(cfg)

        # tresos_home 下的 Mcu / Port / Can 应被加载
        assert "Mcu" in reg.modules
        assert "Port" in reg.modules
        assert "Can" in reg.modules
        assert len(reg) == 3
        # source_paths 来自 tresos_home
        assert any("BSWMD" in str(p) for p in reg.source_paths)

    def test_load_default_includes_extra_bswmd_paths(
        self,
        fake_project_root: Path,
        tmp_workspace: Path,
    ) -> None:
        """``extra_bswmd_paths`` 命中三方 BSWMD → 加载并入 registry。"""
        # 三方 BSWMD 路径（在 tmp_workspace 下）
        cdd_dir = tmp_workspace / "NXP_CDD_Plugins"
        cdd_dir.mkdir(parents=True, exist_ok=True)
        _write_module_bswmd(cdd_dir / "NXP_Wdg_Bswmd.arxml", "Wdg", root_pkg="NXP_Vendor")

        cfg = _fake_config(
            project_root=fake_project_root,
            tresos_home=None,
            extra=(cdd_dir,),
        )
        reg = BSWMDRegistry.load_default(cfg)

        assert "Wdg" in reg.modules
        assert reg.root_package_name == "NXP_Vendor"

    def test_load_default_skips_nonexistent_extra_path(
        self,
        fake_project_root: Path,
        tmp_workspace: Path,
    ) -> None:
        """``extra_bswmd_paths`` 路径不存在 → 警告（不抛），跳过该路径。"""
        nonexistent = tmp_workspace / "does_not_exist"

        cfg = _fake_config(
            project_root=fake_project_root,
            tresos_home=None,
            extra=(nonexistent,),
        )
        # 不应抛
        reg = BSWMDRegistry.load_default(cfg)
        assert isinstance(reg, BSWMDRegistry)
        assert len(reg.modules) == 0

    def test_load_default_merges_multi_source(
        self,
        fake_project_root: Path,
        fake_tresos_home: Path,
        tmp_workspace: Path,
    ) -> None:
        """多源加载：r22 加载 Mcu，extra 加载 Wdg → 合并入同一 registry。"""
        local = fake_project_root / ".autoc" / "bswmd" / "r22" / "Mcu" / "Mcu_Bswmd.arxml"
        _write_module_bswmd(local, "Mcu", root_pkg="AUTOSAR")

        cdd_dir = tmp_workspace / "vendor"
        cdd_dir.mkdir(parents=True, exist_ok=True)
        _write_module_bswmd(cdd_dir / "Vendor_Wdg.arxml", "Wdg", root_pkg="Vendor")

        cfg = _fake_config(
            project_root=fake_project_root,
            tresos_home=fake_tresos_home,
            extra=(cdd_dir,),
        )
        reg = BSWMDRegistry.load_default(cfg)

        # r22 标准 + tresos_home 兜底 + vendor 三方 都应被加载
        assert "Mcu" in reg.modules  # 来自 r22 本地
        assert "Port" in reg.modules  # 来自 tresos_home
        assert "Can" in reg.modules  # 来自 tresos_home
        assert "Wdg" in reg.modules  # 来自 extra
        assert len(reg) == 4

    def test_load_default_merges_extra_prefs_when_present(
        self,
        fake_project_root: Path,
        tmp_workspace: Path,
    ) -> None:
        """``.prefs/*.arxml`` 应被加载（D14 第 2 级）。"""
        # 工程本地 .prefs 已有 1 个 .arxml
        prefs = fake_project_root / ".prefs"
        _write_module_bswmd(prefs / "Mcu_Cfg.arxml", "Mcu", root_pkg="AUTOSAR")

        # tresos_home 提供 Port
        home = tmp_workspace / "tresos_home"
        ecucdefs = home / "BSWMD" / "AUTOSAR_R22" / "EcucDefs"
        ecucdefs.mkdir(parents=True, exist_ok=True)
        _write_module_bswmd(ecucdefs / "Port_Bswmd.arxml", "Port")

        cfg = _fake_config(
            project_root=fake_project_root,
            tresos_home=home,
        )
        reg = BSWMDRegistry.load_default(cfg)

        assert "Mcu" in reg.modules  # 来自 .prefs/
        assert "Port" in reg.modules  # 来自 tresos_home
        # source_paths 同时含 .prefs 和 BSWMD
        assert any(".prefs" in str(p) for p in reg.source_paths)
        assert any("BSWMD" in str(p) for p in reg.source_paths)


# ---------------------------------------------------------------------------
# Merge 行为（D11 决定：后加载覆盖前加载）
# ---------------------------------------------------------------------------


class TestBSWMDRegistryMerge:
    """``BSWMDRegistry.merge`` 不可变合并。"""

    def test_merge_overrides_same_module_later_wins(self) -> None:
        """同名模块：other.modules 覆盖 self.modules（后加载赢）。"""
        m1 = ModuleDef(short_name="Mcu", full_path="/A/Mcu")
        m2 = ModuleDef(short_name="Mcu", full_path="/B/Mcu")
        a = BSWMDRegistry(modules={"Mcu": m1}, root_package_name="A")
        b = BSWMDRegistry(modules={"Mcu": m2}, root_package_name="B")
        merged = a.merge(b)
        assert merged.modules["Mcu"] is m2
        assert merged.root_package_name == "B"

    def test_merge_preserves_distinct_modules(self) -> None:
        """不同名模块：两个都保留。"""
        m1 = ModuleDef(short_name="Mcu", full_path="/A/Mcu")
        m2 = ModuleDef(short_name="Port", full_path="/B/Port")
        a = BSWMDRegistry(modules={"Mcu": m1}, root_package_name="A")
        b = BSWMDRegistry(modules={"Port": m2}, root_package_name="B")
        merged = a.merge(b)
        assert "Mcu" in merged.modules
        assert "Port" in merged.modules
        assert len(merged) == 2

    def test_merge_concatenates_source_paths(self) -> None:
        """``source_paths`` 元组合并。"""
        a = BSWMDRegistry(modules={}, source_paths=(Path("/a/x.arxml"),))
        b = BSWMDRegistry(modules={}, source_paths=(Path("/b/y.arxml"),))
        merged = a.merge(b)
        assert Path("/a/x.arxml") in merged.source_paths
        assert Path("/b/y.arxml") in merged.source_paths

    def test_merge_returns_new_instance(self) -> None:
        """merge 是不可变操作，返回新实例。"""
        a = BSWMDRegistry(modules={}, source_paths=(Path("/a"),))
        b = BSWMDRegistry(modules={}, source_paths=(Path("/b"),))
        merged = a.merge(b)
        assert merged is not a
        assert merged is not b


# ---------------------------------------------------------------------------
# 容器协议
# ---------------------------------------------------------------------------


class TestBSWMDRegistryContainer:
    def test_len_returns_module_count(self) -> None:
        a = BSWMDRegistry(modules={"Mcu": ModuleDef("Mcu", "/A/Mcu")})
        b = BSWMDRegistry(
            modules={"Mcu": ModuleDef("Mcu", "/A/Mcu"), "Port": ModuleDef("Port", "/A/Port")}
        )
        assert len(a) == 1
        assert len(b) == 2

    def test_contains_checks_module_name(self) -> None:
        reg = BSWMDRegistry(modules={"Mcu": ModuleDef("Mcu", "/A/Mcu")})
        assert "Mcu" in reg
        assert "Port" not in reg

    def test_lookup_module_returns_module_def(self) -> None:
        m = ModuleDef("Mcu", "/A/Mcu")
        reg = BSWMDRegistry(modules={"Mcu": m})
        assert reg.lookup_module("Mcu") is m
        assert reg.lookup_module("Unknown") is None

    def test_lookup_param_returns_none_stub(self) -> None:
        """T8.E.2 占位：当前始终返回 ``None``（Agent F 实现）。"""
        reg = BSWMDRegistry()
        assert reg.lookup_param("/AUTOSAR/Mcu/Foo") is None

    def test_lookup_container_returns_none_stub(self) -> None:
        """T8.E.2 占位。"""
        reg = BSWMDRegistry()
        assert reg.lookup_container("/AUTOSAR/Mcu/Bar") is None


# ---------------------------------------------------------------------------
# ParamDef / ContainerDef / ModuleDef 数据类契约（frozen）
# ---------------------------------------------------------------------------


class TestDataModelFrozen:
    """契约 2 锁定：frozen dataclass，构造后不可变。"""

    def test_param_def_is_frozen(self) -> None:
        p = ParamDef(short_name="X", full_path="/A/X", param_type="INTEGER")
        with pytest.raises((AttributeError, Exception)):
            p.short_name = "Y"  # type: ignore[misc]

    def test_param_def_default_values(self) -> None:
        """D5 决定：lower=0, upper=1 缺省。"""
        p = ParamDef(short_name="X", full_path="/A/X", param_type="INTEGER")
        assert p.min is None
        assert p.max is None
        assert p.default is None
        assert p.lower_multiplicity == 0
        assert p.upper_multiplicity == 1
        assert p.symbol_strings == ()

    def test_param_def_enumeration_symbol_strings(self) -> None:
        p = ParamDef(
            short_name="Mode",
            full_path="/A/Mode",
            param_type="ENUMERATION",
            symbol_strings=("A", "B", "C"),
        )
        assert p.symbol_strings == ("A", "B", "C")

    def test_container_def_nested(self) -> None:
        sub = ContainerDef(
            short_name="Sub",
            full_path="/A/Sub",
            lower_multiplicity=0,
            upper_multiplicity=2,
        )
        c = ContainerDef(
            short_name="Main",
            full_path="/A/Main",
            lower_multiplicity=1,
            upper_multiplicity=1,
            sub_container_defs={"Sub": sub},
        )
        assert c.sub_container_defs["Sub"] is sub

    def test_module_def_default_empty(self) -> None:
        m = ModuleDef(short_name="Mcu", full_path="/A/Mcu")
        assert m.containers == {}
        assert m.params == {}

    def test_registry_default_root_package_name(self) -> None:
        """D11 决定：根包名探测到的是 ``AUTOSAR``（不要硬编码 ``/AUTOSAR/`` 前缀）。"""
        reg = BSWMDRegistry()
        assert reg.root_package_name == "AUTOSAR"
