"""ParamDef / ContainerDef / ModuleDef 数据类 + 集成测试。

从 test_sprint8e_coverage_bswmd.py 拆分而来。
覆盖：3 层嵌套、顶层 module param、完整端到端路径 walk。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_autosar.core.bsw.bswmd import (
    BSWMDRegistry,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """隔离工作目录。"""
    ws = tmp_path / "autoc-bswmd-cov-ws"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


# ---------------------------------------------------------------------------
# TestBSWMDCoverageThreeLevelNesting — 3 层 container
# ---------------------------------------------------------------------------


class TestBSWMDCoverageThreeLevelNesting:
    """3 层嵌套 container（plan RED 段要求）。"""

    def test_three_level_nested_container_path_walk(
        self,
        tmp_workspace: Path,
    ) -> None:
        """Mcu → Clock → RefPoint → Leaf 4 层路径 walk 命中 leaf param。"""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>AUTOSAR</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-DEF>
          <SHORT-NAME>Mcu</SHORT-NAME>
          <CONTAINERS>
            <ECUC-PARAM-CONF-CONTAINER-DEF>
              <SHORT-NAME>Clock</SHORT-NAME>
              <SUB-CONTAINERS>
                <ECUC-PARAM-CONF-CONTAINER-DEF>
                  <SHORT-NAME>RefPoint</SHORT-NAME>
                  <SUB-CONTAINERS>
                    <ECUC-PARAM-CONF-CONTAINER-DEF>
                      <SHORT-NAME>Leaf</SHORT-NAME>
                      <PARAMETERS>
                        <ECUC-INTEGER-PARAM-DEF>
                          <SHORT-NAME>Freq</SHORT-NAME>
                          <MIN>0</MIN>
                          <MAX>1000000</MAX>
                        </ECUC-INTEGER-PARAM-DEF>
                      </PARAMETERS>
                    </ECUC-PARAM-CONF-CONTAINER-DEF>
                  </SUB-CONTAINERS>
                </ECUC-PARAM-CONF-CONTAINER-DEF>
              </SUB-CONTAINERS>
            </ECUC-PARAM-CONF-CONTAINER-DEF>
          </CONTAINERS>
        </ECUC-MODULE-DEF>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
"""
        path = tmp_workspace / "deep.arxml"
        _write(path, xml)
        reg = BSWMDRegistry.load((path,))

        # 命中最深 param
        p = reg.lookup_param("/AUTOSAR/Mcu/Clock/RefPoint/Leaf/Freq")
        assert p is not None
        assert p.short_name == "Freq"
        assert p.param_type == "INTEGER"

        # 命中中间 container
        c = reg.lookup_container("/AUTOSAR/Mcu/Clock/RefPoint/Leaf")
        assert c is not None
        assert c.short_name == "Leaf"

        # 命中中间 RefPoint container
        c2 = reg.lookup_container("/AUTOSAR/Mcu/Clock/RefPoint")
        assert c2 is not None
        assert c2.short_name == "RefPoint"

        # 命中 Clock container
        c3 = reg.lookup_container("/AUTOSAR/Mcu/Clock")
        assert c3 is not None
        assert c3.short_name == "Clock"


# ---------------------------------------------------------------------------
# TestBSWMDCoverageTopLevelParam — module 顶层 param
# ---------------------------------------------------------------------------


class TestBSWMDCoverageTopLevelParam:
    """module 顶层有 PARAMETERS 块（plan 支持）。"""

    def test_module_top_level_param_lookup(self, tmp_workspace: Path) -> None:
        """module 顶层 PARAMETERS 中 param 可被 lookup 命中。"""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>AUTOSAR</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-DEF>
          <SHORT-NAME>Mcu</SHORT-NAME>
          <PARAMETERS>
            <ECUC-INTEGER-PARAM-DEF>
              <SHORT-NAME>Version</SHORT-NAME>
            </ECUC-INTEGER-PARAM-DEF>
          </PARAMETERS>
        </ECUC-MODULE-DEF>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
"""
        path = tmp_workspace / "topparam.arxml"
        _write(path, xml)
        reg = BSWMDRegistry.load((path,))
        p = reg.lookup_param("/AUTOSAR/Mcu/Version")
        assert p is not None
        assert p.param_type == "INTEGER"
        assert "Version" in reg.modules["Mcu"].params
