"""BSWMDRegistry.load / merge / lookup 相关测试。

从 test_sprint8e_coverage_bswmd.py 拆分而来。
覆盖：load_default 4 级优先级、罕见 schema、merge、path walk、
namespace alias、multi-package、repr。
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree
import pytest

from claude_autosar.core.bsw.bswmd import (
    BSWMDError,
    BSWMDRegistry,
    ModuleDef,
)


# -- helpers ------------------------------------------------------------------


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _bswmd_xml(root_pkg: str = "AUTOSAR", body: str = "") -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>{root_pkg}</SHORT-NAME>
      {body}
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
"""


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "autoc-bswmd-cov-ws"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


# -- load_default 4 级优先级 / 异常 / 解析失败 ---------------------------------


class TestBSWMDCoverageLoad:
    """``load`` / ``load_default`` 入口的 missing 分支。"""

    def test_load_default_picks_prefs_path_when_present(
        self, tmp_workspace: Path,
    ) -> None:
        """行 199->201：``.prefs`` 存在时追加到 candidate_roots。"""
        project = tmp_workspace / "proj"
        project.mkdir(parents=True, exist_ok=True)
        prefs = project / ".prefs"
        prefs.mkdir(parents=True, exist_ok=True)
        (prefs / "Custom.arxml").write_text(
            _bswmd_xml(
                body="<ELEMENTS><ECUC-MODULE-DEF><SHORT-NAME>PrefsMod</SHORT-NAME>"
                "</ECUC-MODULE-DEF></ELEMENTS>"
            ),
            encoding="utf-8",
        )
        from claude_autosar.core.config.project_config import ProjectConfig

        cfg = ProjectConfig(
            project_root=project,
            tresos_home=None,
            bswmd_root=project / ".autoc" / "bswmd" / "r22",
            extra_bswmd_paths=(),
        )
        reg = BSWMDRegistry.load_default(cfg)
        assert "PrefsMod" in reg.modules
        assert any(".prefs" in str(p) for p in reg.source_paths)

    def test_load_default_picks_extra_bswmd_paths(
        self, tmp_workspace: Path,
    ) -> None:
        """行 201：``extra_bswmd_paths`` 中的每个路径被追加。"""
        project = tmp_workspace / "proj"
        project.mkdir(parents=True, exist_ok=True)
        cdd1 = tmp_workspace / "cdd1"
        cdd1.mkdir()
        (cdd1 / "A.arxml").write_text(
            _bswmd_xml(
                body="<ELEMENTS><ECUC-MODULE-DEF><SHORT-NAME>ModA</SHORT-NAME>"
                "</ECUC-MODULE-DEF></ELEMENTS>"
            ),
            encoding="utf-8",
        )
        cdd2 = tmp_workspace / "cdd2"
        cdd2.mkdir()
        (cdd2 / "B.arxml").write_text(
            _bswmd_xml(
                body="<ELEMENTS><ECUC-MODULE-DEF><SHORT-NAME>ModB</SHORT-NAME>"
                "</ECUC-MODULE-DEF></ELEMENTS>"
            ),
            encoding="utf-8",
        )
        from claude_autosar.core.config.project_config import ProjectConfig

        cfg = ProjectConfig(
            project_root=project,
            tresos_home=None,
            bswmd_root=project / ".autoc" / "bswmd" / "r22",
            extra_bswmd_paths=(cdd1, cdd2),
        )
        reg = BSWMDRegistry.load_default(cfg)
        assert "ModA" in reg.modules
        assert "ModB" in reg.modules

    def test_load_default_uses_tresos_home_fallback(
        self, tmp_workspace: Path,
    ) -> None:
        """行 202-205：``tresos_home`` 设置时使用 ``BSWMD/AUTOSAR_R22/EcucDefs`` 兜底。"""
        project = tmp_workspace / "proj"
        project.mkdir(parents=True, exist_ok=True)
        tresos = tmp_workspace / "tresos_home"
        ecucdefs = tresos / "BSWMD" / "AUTOSAR_R22" / "EcucDefs"
        ecucdefs.mkdir(parents=True, exist_ok=True)
        (ecucdefs / "Fallback.arxml").write_text(
            _bswmd_xml(
                body="<ELEMENTS><ECUC-MODULE-DEF><SHORT-NAME>Fallback</SHORT-NAME>"
                "</ECUC-MODULE-DEF></ELEMENTS>"
            ),
            encoding="utf-8",
        )
        from claude_autosar.core.config.project_config import ProjectConfig

        cfg = ProjectConfig(
            project_root=project,
            tresos_home=tresos,
            bswmd_root=project / ".autoc" / "bswmd" / "r22",
            extra_bswmd_paths=(),
        )
        reg = BSWMDRegistry.load_default(cfg)
        assert "Fallback" in reg.modules
        assert any("BSWMD" in str(p) for p in reg.source_paths)

    def test_load_default_skips_tresos_home_fallback_when_dir_missing(
        self, tmp_workspace: Path,
    ) -> None:
        """行 204-205：``BSWMD/AUTOSAR_R22/EcucDefs/`` 不存在时跳过兜底。"""
        project = tmp_workspace / "proj"
        project.mkdir(parents=True, exist_ok=True)
        tresos = tmp_workspace / "empty_tresos"
        tresos.mkdir()
        from claude_autosar.core.config.project_config import ProjectConfig

        cfg = ProjectConfig(
            project_root=project,
            tresos_home=tresos,
            bswmd_root=project / ".autoc" / "bswmd" / "r22",
            extra_bswmd_paths=(),
        )
        reg = BSWMDRegistry.load_default(cfg)
        assert len(reg.modules) == 0

    def test_load_default_handles_corrupt_arxml_gracefully(
        self, tmp_workspace: Path,
    ) -> None:
        """行 221-223：单文件 XML 语法错误时警告 + 跳过（不抛）。"""
        project = tmp_workspace / "proj"
        project.mkdir(parents=True, exist_ok=True)
        corrupt_dir = project / ".autoc" / "bswmd" / "r22"
        corrupt_dir.mkdir(parents=True, exist_ok=True)
        (corrupt_dir / "Bad.arxml").write_text("not <valid> xml", encoding="utf-8")
        from claude_autosar.core.config.project_config import ProjectConfig

        cfg = ProjectConfig(
            project_root=project,
            tresos_home=None,
            bswmd_root=corrupt_dir,
            extra_bswmd_paths=(),
        )
        reg = BSWMDRegistry.load_default(cfg)
        assert isinstance(reg, BSWMDRegistry)
        assert len(reg.modules) == 0

    def test_load_raises_bswmd_error_on_invalid_xml(
        self, tmp_workspace: Path,
    ) -> None:
        """行 270-271 + 275：``load`` 遇到无效 XML → ``BSWMDError``。"""
        bad = tmp_workspace / "bad.arxml"
        bad.write_text("<not><closed>", encoding="utf-8")
        with pytest.raises(BSWMDError, match="failed to parse"):
            BSWMDRegistry.load((bad,))

    def test_load_raises_bswmd_error_on_empty_root(
        self, tmp_workspace: Path,
    ) -> None:
        """行 275：``<X/>`` 自闭根 → 解析成功但没有 module（不 raise）。"""
        empty = tmp_workspace / "empty.arxml"
        empty.write_text('<?xml version="1.0"?><X/>', encoding="utf-8")
        reg = BSWMDRegistry.load((empty,))
        assert reg.modules == {}
        assert reg.root_package_name == "AUTOSAR"


# -- 罕见 schema 变体 --------------------------------------------------------


class TestBSWMDCoverageSchemaVariants:
    """``ECUC-MODULE-DEF`` 直接在 AR-PACKAGE 下（无 ELEMENTS 包装）。"""

    def test_module_directly_under_ar_package(
        self, tmp_workspace: Path,
    ) -> None:
        """行 302->294 / 307-312。"""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>AUTOSAR</SHORT-NAME>
      <ECUC-MODULE-DEF>
        <SHORT-NAME>DirectMod</SHORT-NAME>
      </ECUC-MODULE-DEF>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
"""
        path = tmp_workspace / "direct.arxml"
        _write(path, xml)
        reg = BSWMDRegistry.load((path,))
        assert "DirectMod" in reg.modules


# -- merge 异常路径 -----------------------------------------------------------


class TestBSWMDCoverageMerge:
    """``merge`` 异常 / 边界。"""

    def test_merge_with_non_registry_returns_not_implemented(self) -> None:
        """行 335-336：``merge`` 非 ``BSWMDRegistry`` → ``NotImplemented``。"""
        reg = BSWMDRegistry()
        result = reg.merge("not a registry")  # type: ignore[arg-type]
        assert result is NotImplemented

    def test_merge_with_other_empty_registry(self) -> None:
        """``merge`` 对方是空 registry 时 root_package_name 保留 self。"""
        a = BSWMDRegistry(root_package_name="MyRoot")
        b = BSWMDRegistry()
        merged = a.merge(b)
        assert merged.root_package_name == "MyRoot"


# -- _walk_path 边界 ---------------------------------------------------------


class TestBSWMDCoveragePathWalk:
    """``_walk_path`` / ``__contains__`` / ``lookup_*`` 的 path walk 边界。"""

    @pytest.fixture
    def reg(self, tmp_workspace: Path) -> BSWMDRegistry:
        xml = _bswmd_xml(
            body="<ELEMENTS><ECUC-MODULE-DEF><SHORT-NAME>Mcu</SHORT-NAME>"
            "<CONTAINERS><ECUC-PARAM-CONF-CONTAINER-DEF>"
            "<SHORT-NAME>Clock</SHORT-NAME>"
            "<PARAMETERS><ECUC-INTEGER-PARAM-DEF>"
            "<SHORT-NAME>Freq</SHORT-NAME>"
            "</ECUC-INTEGER-PARAM-DEF></PARAMETERS>"
            "</ECUC-PARAM-CONF-CONTAINER-DEF></CONTAINERS>"
            "</ECUC-MODULE-DEF></ELEMENTS>",
        )
        path = tmp_workspace / "Mcu.arxml"
        _write(path, xml)
        return BSWMDRegistry.load((path,))

    def test_walk_returns_none_for_empty_string(
        self, reg: BSWMDRegistry,
    ) -> None:
        assert reg.lookup_param("") is None
        assert reg.lookup_container("") is None

    def test_walk_returns_none_for_only_slashes(
        self, reg: BSWMDRegistry,
    ) -> None:
        assert reg.lookup_param("///") is None

    def test_walk_returns_none_when_only_root_pkg(
        self, reg: BSWMDRegistry,
    ) -> None:
        """行 422-427：路径只有根包名（parts 消费后为空）→ None。"""
        assert reg.lookup_param("/AUTOSAR") is None
        assert "/AUTOSAR" not in reg

    def test_walk_returns_none_when_root_pkg_mismatch(
        self, reg: BSWMDRegistry,
    ) -> None:
        assert reg.lookup_param("/OTHER/Mcu") is None
        assert reg.lookup_container("/OTHER/Mcu") is None

    def test_walk_returns_module_for_path_with_only_module(self) -> None:
        """``/AUTOSAR/Mcu`` → 返回 ModuleDef。"""
        xml = _bswmd_xml(
            body="<ELEMENTS><ECUC-MODULE-DEF><SHORT-NAME>Mcu</SHORT-NAME>"
            "</ECUC-MODULE-DEF></ELEMENTS>",
        )
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "Mcu.arxml"
            _write(path, xml)
            reg = BSWMDRegistry.load((path,))
        assert reg.lookup_module("Mcu") is not None
        m = reg._walk_path("/AUTOSAR/Mcu")
        assert isinstance(m, ModuleDef)
        assert m.short_name == "Mcu"

    def test_walk_returns_module_for_just_module_name(self) -> None:
        xml = _bswmd_xml(
            body="<ELEMENTS><ECUC-MODULE-DEF><SHORT-NAME>Mcu</SHORT-NAME>"
            "</ECUC-MODULE-DEF></ELEMENTS>",
        )
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "Mcu.arxml"
            _write(path, xml)
            reg = BSWMDRegistry.load((path,))
        m = reg._walk_path("Mcu")
        assert isinstance(m, ModuleDef)

    def test_walk_returns_none_when_descend_fails(self) -> None:
        xml = _bswmd_xml(
            body="<ELEMENTS><ECUC-MODULE-DEF><SHORT-NAME>Mcu</SHORT-NAME>"
            "<CONTAINERS><ECUC-PARAM-CONF-CONTAINER-DEF>"
            "<SHORT-NAME>Clock</SHORT-NAME>"
            "</ECUC-PARAM-CONF-CONTAINER-DEF></CONTAINERS>"
            "</ECUC-MODULE-DEF></ELEMENTS>",
        )
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "Mcu.arxml"
            _write(path, xml)
            reg = BSWMDRegistry.load((path,))
        assert reg.lookup_param("/AUTOSAR/Mcu/Clock/Freq") is None
        assert reg.lookup_param("/AUTOSAR/Mcu/NoContainer/Freq") is None
        assert reg.lookup_container("/AUTOSAR/Mcu/NoContainer") is None


# -- namespace alias ----------------------------------------------------------


class TestBSWMDCoverageNamespaceAlias:
    """验证 ``arx:`` 等 alias 在 bswmd 解析下也工作。"""

    def test_arx_namespace_alias_loads_module(
        self, tmp_workspace: Path,
    ) -> None:
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<arx:AUTOSAR xmlns:arx="http://autosar.org/schema/r4.0">
  <arx:AR-PACKAGES>
    <arx:AR-PACKAGE>
      <arx:SHORT-NAME>AUTOSAR</arx:SHORT-NAME>
      <arx:ELEMENTS>
        <arx:ECUC-MODULE-DEF>
          <arx:SHORT-NAME>ArxMod</arx:SHORT-NAME>
        </arx:ECUC-MODULE-DEF>
      </arx:ELEMENTS>
    </arx:AR-PACKAGE>
  </arx:AR-PACKAGES>
</arx:AUTOSAR>
"""
        path = tmp_workspace / "arx.arxml"
        _write(path, xml)
        reg = BSWMDRegistry.load((path,))
        assert "ArxMod" in reg.modules


# -- multi-package ------------------------------------------------------------


class TestBSWMDCoverageMultiPackage:
    """多个 AR-PACKAGE 兄弟节点全部解析。"""

    def test_two_packages_with_same_module_name_later_wins(
        self, tmp_workspace: Path,
    ) -> None:
        """两个 AR-PACKAGE 同名 module → 后加载覆盖（D11）。"""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>AUTOSAR</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-DEF>
          <SHORT-NAME>Dup</SHORT-NAME>
          <CONTAINERS>
            <ECUC-PARAM-CONF-CONTAINER-DEF>
              <SHORT-NAME>FromStd</SHORT-NAME>
            </ECUC-PARAM-CONF-CONTAINER-DEF>
          </CONTAINERS>
        </ECUC-MODULE-DEF>
      </ELEMENTS>
    </AR-PACKAGE>
    <AR-PACKAGE>
      <SHORT-NAME>Vendor</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-DEF>
          <SHORT-NAME>Dup</SHORT-NAME>
          <CONTAINERS>
            <ECUC-PARAM-CONF-CONTAINER-DEF>
              <SHORT-NAME>FromVendor</SHORT-NAME>
            </ECUC-PARAM-CONF-CONTAINER-DEF>
          </CONTAINERS>
        </ECUC-MODULE-DEF>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
"""
        path = tmp_workspace / "dup.arxml"
        _write(path, xml)
        reg = BSWMDRegistry.load((path,))
        containers = reg.modules["Dup"].containers
        assert "FromVendor" in containers
        assert "FromStd" not in containers


# -- repr ---------------------------------------------------------------------


class TestBSWMDCoverageRepr:
    """``__repr__``（pragma 覆盖；这里强制覆盖以验证不抛）。"""

    def test_repr_does_not_raise(self) -> None:
        m = ModuleDef(short_name="Mcu", full_path="/A/Mcu")
        reg = BSWMDRegistry(modules={"Mcu": m}, source_paths=(Path("/x"),))
        result = repr(reg)
        assert "BSWMDRegistry" in result
        assert "Mcu" in result
        assert "1 files" in result
