"""Unit tests for ``BSWMDRegistry`` BSWMD 解析器（T8.E.2）。

Plan reference: Sprint 8.E T8.E.2 — `core/bsw/bswmd.py` 新建 BSWMD 解析器（全深度）。
Contract 2: BSWMDRegistry + ParamDef 数据模型（全字段）。
Contract 7: test naming + file layout（``TestBSWMDRegistry``）。

测试要点（plan T8.E.2 RED 测试段）：
- 5 种 ``param_type`` 各 1 case（INTEGER / FLOAT / STRING / BOOLEAN / ENUMERATION）
- ENUMERATION 的 ``symbol_strings`` 解析（≥ 2 个）
- ``LOWER-MULTIPLICITY`` / ``UPPER-MULTIPLICITY`` 解析，含 ``unbounded`` → -1
- ``MIN`` / ``MAX`` 字符串解析
- 嵌套 3 层 container
- ``lookup_param`` miss 返回 None（不抛）
- ``lookup_param`` BSWMD 优先覆盖 DEST 启发式
- ``lookup_param`` fallback 到 DEST 启发式（7 个老 test 不破）
- ``load(())`` → ``ValueError``
- 跳过 ``<AR-PACKAGE>`` 兄弟节点
- 处理 namespace alias（``xmlns:arx="..."`` + ``arx:ECUC-PARAM-CONF-CONTAINER-DEF``）
- ``BSWMDRegistry.__len__`` / ``__contains__``
- ``_parse_param_def`` ParamDef 全字段
- ``_parse_container_def`` 递归
- ``_parse_module_def`` 顶层 ModuleDef
"""

from __future__ import annotations

from pathlib import Path

import pytest

from autoc.core.bsw.bswmd import (
    BSWMDRegistry,
    ContainerDef,
    ModuleDef,
    ParamDef,
)

# ---------------------------------------------------------------------------
# Module-level fixture helpers（不碰 conftest.py；契约 7）
# ---------------------------------------------------------------------------


def _write_full_bswmd(path: Path) -> None:
    """写一个含 5 种 param_type + 嵌套 2 层 container 的 BSWMD。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>AUTOSAR</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-DEF>
          <SHORT-NAME>Mcu</SHORT-NAME>
          <LOWER-MULTIPLICITY>1</LOWER-MULTIPLICITY>
          <UPPER-MULTIPLICITY>1</UPPER-MULTIPLICITY>
          <CONTAINERS>
            <ECUC-PARAM-CONF-CONTAINER-DEF>
              <SHORT-NAME>McuClockSettingConfig</SHORT-NAME>
              <LOWER-MULTIPLICITY>0</LOWER-MULTIPLICITY>
              <UPPER-MULTIPLICITY>3</UPPER-MULTIPLICITY>
              <PARAMETERS>
                <ECUC-INTEGER-PARAM-DEF>
                  <SHORT-NAME>McuClockFrequency</SHORT-NAME>
                  <MIN>0</MIN>
                  <MAX>300000000</MAX>
                  <DEFAULT-VALUE>80000000</DEFAULT-VALUE>
                </ECUC-INTEGER-PARAM-DEF>
                <ECUC-FLOAT-PARAM-DEF>
                  <SHORT-NAME>McuClockTolerance</SHORT-NAME>
                  <MIN>0.0</MIN>
                  <MAX>1.0</MAX>
                </ECUC-FLOAT-PARAM-DEF>
                <ECUC-STRING-PARAM-DEF>
                  <SHORT-NAME>McuClockName</SHORT-NAME>
                </ECUC-STRING-PARAM-DEF>
                <ECUC-BOOLEAN-PARAM-DEF>
                  <SHORT-NAME>McuClockEnabled</SHORT-NAME>
                </ECUC-BOOLEAN-PARAM-DEF>
                <ECUC-ENUMERATION-PARAM-DEF>
                  <SHORT-NAME>McuClockSource</SHORT-NAME>
                  <LITERALS>
                    <ECUC-ENUMERATION-LITERAL-DEF>
                      <SHORT-NAME>PLL</SHORT-NAME>
                    </ECUC-ENUMERATION-LITERAL-DEF>
                    <ECUC-ENUMERATION-LITERAL-DEF>
                      <SHORT-NAME>XTAL</SHORT-NAME>
                    </ECUC-ENUMERATION-LITERAL-DEF>
                    <ECUC-ENUMERATION-LITERAL-DEF>
                      <SHORT-NAME>RC</SHORT-NAME>
                    </ECUC-ENUMERATION-LITERAL-DEF>
                  </LITERALS>
                </ECUC-ENUMERATION-PARAM-DEF>
              </PARAMETERS>
              <SUB-CONTAINERS>
                <ECUC-PARAM-CONF-CONTAINER-DEF>
                  <SHORT-NAME>McuClockReferencePoint</SHORT-NAME>
                  <LOWER-MULTIPLICITY>0</LOWER-MULTIPLICITY>
                  <UPPER-MULTIPLICITY>1</UPPER-MULTIPLICITY>
                  <PARAMETERS>
                    <ECUC-INTEGER-PARAM-DEF>
                      <SHORT-NAME>Frequency</SHORT-NAME>
                      <MIN>0</MIN>
                      <MAX>200000000</MAX>
                    </ECUC-INTEGER-PARAM-DEF>
                  </PARAMETERS>
                </ECUC-PARAM-CONF-CONTAINER-DEF>
              </SUB-CONTAINERS>
            </ECUC-PARAM-CONF-CONTAINER-DEF>
          </CONTAINERS>
        </ECUC-MODULE-DEF>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
""",
        encoding="utf-8",
    )


def _write_unbounded_container(path: Path) -> None:
    """写一个含 UPPER-MULTIPLICITY=unbounded 的 container。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>AUTOSAR</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-DEF>
          <SHORT-NAME>Can</SHORT-NAME>
          <CONTAINERS>
            <ECUC-PARAM-CONF-CONTAINER-DEF>
              <SHORT-NAME>CanControllerConfig</SHORT-NAME>
              <LOWER-MULTIPLICITY>0</LOWER-MULTIPLICITY>
              <UPPER-MULTIPLICITY>unbounded</UPPER-MULTIPLICITY>
              <PARAMETERS>
                <ECUC-INTEGER-PARAM-DEF>
                  <SHORT-NAME>CanControllerId</SHORT-NAME>
                  <MIN>0</MIN>
                  <MAX>255</MAX>
                </ECUC-INTEGER-PARAM-DEF>
              </PARAMETERS>
            </ECUC-PARAM-CONF-CONTAINER-DEF>
          </CONTAINERS>
        </ECUC-MODULE-DEF>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
""",
        encoding="utf-8",
    )


def _write_multi_package_bswmd(path: Path) -> None:
    """写一个含多个 AR-PACKAGE 兄弟节点的 BSWMD（验证只解析第一个作为根）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>AUTOSAR</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-DEF>
          <SHORT-NAME>Port</SHORT-NAME>
          <CONTAINERS>
            <ECUC-PARAM-CONF-CONTAINER-DEF>
              <SHORT-NAME>PortConfig</SHORT-NAME>
              <PARAMETERS>
                <ECUC-INTEGER-PARAM-DEF>
                  <SHORT-NAME>PortNumber</SHORT-NAME>
                </ECUC-INTEGER-PARAM-DEF>
              </PARAMETERS>
            </ECUC-PARAM-CONF-CONTAINER-DEF>
          </CONTAINERS>
        </ECUC-MODULE-DEF>
      </ELEMENTS>
    </AR-PACKAGE>
    <AR-PACKAGE>
      <SHORT-NAME>Vendor</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-DEF>
          <SHORT-NAME>NXP_Wdg</SHORT-NAME>
          <CONTAINERS>
            <ECUC-PARAM-CONF-CONTAINER-DEF>
              <SHORT-NAME>WdgConfig</SHORT-NAME>
              <PARAMETERS>
                <ECUC-INTEGER-PARAM-DEF>
                  <SHORT-NAME>WdgTimeout</SHORT-NAME>
                </ECUC-INTEGER-PARAM-DEF>
              </PARAMETERS>
            </ECUC-PARAM-CONF-CONTAINER-DEF>
          </CONTAINERS>
        </ECUC-MODULE-DEF>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
""",
        encoding="utf-8",
    )


def _write_namespace_alias_bswmd(path: Path) -> None:
    """写一个用非默认 namespace alias（如 ``arx:``）的 BSWMD。

    验证 BSWMD 解析对 namespace prefix 不敏感（用 localname 匹配）。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<arx:AUTOSAR xmlns:arx="http://autosar.org/schema/r4.0">
  <arx:AR-PACKAGES>
    <arx:AR-PACKAGE>
      <arx:SHORT-NAME>AUTOSAR</arx:SHORT-NAME>
      <arx:ELEMENTS>
        <arx:ECUC-MODULE-DEF>
          <arx:SHORT-NAME>Spi</arx:SHORT-NAME>
          <arx:CONTAINERS>
            <arx:ECUC-PARAM-CONF-CONTAINER-DEF>
              <arx:SHORT-NAME>SpiChannelConfig</arx:SHORT-NAME>
              <arx:PARAMETERS>
                <arx:ECUC-INTEGER-PARAM-DEF>
                  <arx:SHORT-NAME>SpiChannelId</arx:SHORT-NAME>
                </arx:ECUC-INTEGER-PARAM-DEF>
              </arx:PARAMETERS>
            </arx:ECUC-PARAM-CONF-CONTAINER-DEF>
          </arx:CONTAINERS>
        </arx:ECUC-MODULE-DEF>
      </arx:ELEMENTS>
    </arx:AR-PACKAGE>
  </arx:AR-PACKAGES>
</arx:AUTOSAR>
""",
        encoding="utf-8",
    )


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """隔离工作目录。"""
    ws = tmp_path / "autoc-bswmd-parser-ws"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


# ---------------------------------------------------------------------------
# TestBSWMDRegistry — load 入口
# ---------------------------------------------------------------------------


class TestBSWMDRegistryLoad:
    """``BSWMDRegistry.load`` / ``load_default`` 入口。"""

    def test_load_with_empty_paths_raises_value_error(self) -> None:
        """``load(())`` → ``ValueError``（契约 2 — 显式拒绝空输入）。"""
        with pytest.raises(ValueError, match="paths"):
            BSWMDRegistry.load(())

    def test_load_parses_module_short_name_and_full_path(
        self,
        tmp_workspace: Path,
    ) -> None:
        """``load`` 解析 ModuleDef 的 short_name + full_path。"""
        bswmd = tmp_workspace / "Mcu_Bswmd.arxml"
        _write_full_bswmd(bswmd)

        reg = BSWMDRegistry.load((bswmd,))

        assert "Mcu" in reg.modules
        mcu = reg.modules["Mcu"]
        assert isinstance(mcu, ModuleDef)
        assert mcu.short_name == "Mcu"
        assert mcu.full_path == "/AUTOSAR/Mcu"

    def test_load_returns_root_package_name(
        self,
        tmp_workspace: Path,
    ) -> None:
        """``root_package_name`` 探测到的是 ``AUTOSAR``（不是硬编码）。"""
        bswmd = tmp_workspace / "Mcu_Bswmd.arxml"
        _write_full_bswmd(bswmd)

        reg = BSWMDRegistry.load((bswmd,))

        assert reg.root_package_name == "AUTOSAR"

    def test_load_nonexistent_path_raises_value_error(
        self,
        tmp_workspace: Path,
    ) -> None:
        """``load`` 路径不存在 → ``ValueError``。"""
        nonexistent = tmp_workspace / "no_such_file.arxml"
        with pytest.raises((ValueError, OSError, FileNotFoundError)):
            BSWMDRegistry.load((nonexistent,))

    def test_load_handles_namespace_alias(
        self,
        tmp_workspace: Path,
    ) -> None:
        """非默认 namespace alias（``arx:``）也能正确解析。"""
        bswmd = tmp_workspace / "Spi_Bswmd.arxml"
        _write_namespace_alias_bswmd(bswmd)

        reg = BSWMDRegistry.load((bswmd,))

        assert "Spi" in reg.modules
        spi = reg.modules["Spi"]
        assert "SpiChannelConfig" in spi.containers
        assert "SpiChannelId" in spi.containers["SpiChannelConfig"].param_defs

    def test_load_multi_package_parses_all_modules(
        self,
        tmp_workspace: Path,
    ) -> None:
        """多个 AR-PACKAGE 兄弟节点都被解析（root + vendor）。"""
        bswmd = tmp_workspace / "Multi_Bswmd.arxml"
        _write_multi_package_bswmd(bswmd)

        reg = BSWMDRegistry.load((bswmd,))

        assert "Port" in reg.modules
        assert "NXP_Wdg" in reg.modules
        assert len(reg) == 2


# ---------------------------------------------------------------------------
# TestParamDef — ParamDef 全字段
# ---------------------------------------------------------------------------


class TestParamDef:
    """``_parse_param_def`` 解析的 ParamDef 全字段。"""

    def test_integer_param_def_parses_type_and_range(
        self,
        tmp_workspace: Path,
    ) -> None:
        """INTEGER 解析 param_type / min / max / default。"""
        bswmd = tmp_workspace / "Mcu_Bswmd.arxml"
        _write_full_bswmd(bswmd)
        reg = BSWMDRegistry.load((bswmd,))

        param = (
            reg.modules["Mcu"].containers["McuClockSettingConfig"].param_defs["McuClockFrequency"]
        )

        assert isinstance(param, ParamDef)
        assert param.short_name == "McuClockFrequency"
        assert param.full_path == ("/AUTOSAR/Mcu/McuClockSettingConfig/McuClockFrequency")
        assert param.param_type == "INTEGER"
        assert param.min == "0"
        assert param.max == "300000000"
        assert param.default == "80000000"

    def test_float_param_def_parses_type_and_range(
        self,
        tmp_workspace: Path,
    ) -> None:
        """FLOAT 解析 param_type / min / max。"""
        bswmd = tmp_workspace / "Mcu_Bswmd.arxml"
        _write_full_bswmd(bswmd)
        reg = BSWMDRegistry.load((bswmd,))

        param = (
            reg.modules["Mcu"].containers["McuClockSettingConfig"].param_defs["McuClockTolerance"]
        )

        assert param.param_type == "FLOAT"
        assert param.min == "0.0"
        assert param.max == "1.0"

    def test_string_param_def_parses_type(
        self,
        tmp_workspace: Path,
    ) -> None:
        """STRING 解析 param_type。"""
        bswmd = tmp_workspace / "Mcu_Bswmd.arxml"
        _write_full_bswmd(bswmd)
        reg = BSWMDRegistry.load((bswmd,))

        param = reg.modules["Mcu"].containers["McuClockSettingConfig"].param_defs["McuClockName"]

        assert param.param_type == "STRING"

    def test_boolean_param_def_parses_type(
        self,
        tmp_workspace: Path,
    ) -> None:
        """BOOLEAN 解析 param_type。"""
        bswmd = tmp_workspace / "Mcu_Bswmd.arxml"
        _write_full_bswmd(bswmd)
        reg = BSWMDRegistry.load((bswmd,))

        param = reg.modules["Mcu"].containers["McuClockSettingConfig"].param_defs["McuClockEnabled"]

        assert param.param_type == "BOOLEAN"

    def test_enumeration_param_def_parses_symbol_strings(
        self,
        tmp_workspace: Path,
    ) -> None:
        """ENUMERATION 解析 param_type + symbol_strings（≥ 2 个）。"""
        bswmd = tmp_workspace / "Mcu_Bswmd.arxml"
        _write_full_bswmd(bswmd)
        reg = BSWMDRegistry.load((bswmd,))

        param = reg.modules["Mcu"].containers["McuClockSettingConfig"].param_defs["McuClockSource"]

        assert param.param_type == "ENUMERATION"
        assert param.symbol_strings == ("PLL", "XTAL", "RC")
        assert len(param.symbol_strings) >= 2

    def test_param_def_defaults_when_fields_absent(
        self,
        tmp_workspace: Path,
    ) -> None:
        """ParamDef 缺字段时走 D5 决定：lower=0 upper=1。"""
        bswmd = tmp_workspace / "Mcu_Bswmd.arxml"
        _write_full_bswmd(bswmd)
        reg = BSWMDRegistry.load((bswmd,))

        param = reg.modules["Mcu"].containers["McuClockSettingConfig"].param_defs["McuClockName"]

        assert param.lower_multiplicity == 0
        assert param.upper_multiplicity == 1
        assert param.min is None
        assert param.max is None
        assert param.default is None
        assert param.symbol_strings == ()


# ---------------------------------------------------------------------------
# TestContainerDef — ContainerDef 递归
# ---------------------------------------------------------------------------


class TestContainerDef:
    """``_parse_container_def`` 解析的 ContainerDef + multiplicity。"""

    def test_container_parses_lower_and_upper_multiplicity(
        self,
        tmp_workspace: Path,
    ) -> None:
        """Container 解析 LOWER-MULTIPLICITY / UPPER-MULTIPLICITY。"""
        bswmd = tmp_workspace / "Mcu_Bswmd.arxml"
        _write_full_bswmd(bswmd)
        reg = BSWMDRegistry.load((bswmd,))

        container = reg.modules["Mcu"].containers["McuClockSettingConfig"]
        assert isinstance(container, ContainerDef)
        assert container.lower_multiplicity == 0
        assert container.upper_multiplicity == 3
        assert container.full_path == "/AUTOSAR/Mcu/McuClockSettingConfig"

    def test_container_unbounded_upper_parsed_as_negative_one(
        self,
        tmp_workspace: Path,
    ) -> None:
        """UPPER-MULTIPLICITY=unbounded → -1（D5 决定）。"""
        bswmd = tmp_workspace / "Can_Bswmd.arxml"
        _write_unbounded_container(bswmd)
        reg = BSWMDRegistry.load((bswmd,))

        container = reg.modules["Can"].containers["CanControllerConfig"]
        assert container.lower_multiplicity == 0
        assert container.upper_multiplicity == -1

    def test_container_nested_sub_containers(self) -> None:
        """3 层嵌套 container：Mcu → McuClockSettingConfig → McuClockReferencePoint。"""
        # 用 module-level fixture 路径生成
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            from pathlib import Path as _P

            bswmd = _P(td) / "Mcu_Bswmd.arxml"
            _write_full_bswmd(bswmd)
            reg = BSWMDRegistry.load((bswmd,))

            # Layer 1: Module → Mcu
            mcu = reg.modules["Mcu"]
            assert mcu.full_path == "/AUTOSAR/Mcu"

            # Layer 2: Module → McuClockSettingConfig
            assert "McuClockSettingConfig" in mcu.containers
            clock_cfg = mcu.containers["McuClockSettingConfig"]
            assert clock_cfg.full_path == ("/AUTOSAR/Mcu/McuClockSettingConfig")
            assert "McuClockFrequency" in clock_cfg.param_defs

            # Layer 3: McuClockSettingConfig → McuClockReferencePoint
            assert "McuClockReferencePoint" in clock_cfg.sub_container_defs
            ref_point = clock_cfg.sub_container_defs["McuClockReferencePoint"]
            assert ref_point.full_path == (
                "/AUTOSAR/Mcu/McuClockSettingConfig/McuClockReferencePoint"
            )
            assert "Frequency" in ref_point.param_defs
            assert (
                ref_point.param_defs["Frequency"].full_path
                == "/AUTOSAR/Mcu/McuClockSettingConfig/McuClockReferencePoint/Frequency"
            )


# ---------------------------------------------------------------------------
# TestLookup — lookup_param / lookup_container / lookup_module
# ---------------------------------------------------------------------------


class TestLookup:
    """``BSWMDRegistry`` lookup API。"""

    def test_lookup_param_returns_param_def(
        self,
        tmp_workspace: Path,
    ) -> None:
        """``lookup_param`` 用 DEFINITION-REF 路径命中 ParamDef。"""
        bswmd = tmp_workspace / "Mcu_Bswmd.arxml"
        _write_full_bswmd(bswmd)
        reg = BSWMDRegistry.load((bswmd,))

        param = reg.lookup_param(
            "/AUTOSAR/Mcu/McuClockSettingConfig/McuClockFrequency",
        )
        assert param is not None
        assert param.short_name == "McuClockFrequency"
        assert param.param_type == "INTEGER"

    def test_lookup_param_miss_returns_none(
        self,
        tmp_workspace: Path,
    ) -> None:
        """``lookup_param`` miss → ``None``（不抛 — 契约 2）。"""
        bswmd = tmp_workspace / "Mcu_Bswmd.arxml"
        _write_full_bswmd(bswmd)
        reg = BSWMDRegistry.load((bswmd,))

        result = reg.lookup_param("/AUTOSAR/Mcu/NonexistentParam")
        assert result is None

    def test_lookup_param_with_unknown_module_returns_none(
        self,
        tmp_workspace: Path,
    ) -> None:
        """``lookup_param`` 路径中模块未知 → ``None``（不抛）。"""
        bswmd = tmp_workspace / "Mcu_Bswmd.arxml"
        _write_full_bswmd(bswmd)
        reg = BSWMDRegistry.load((bswmd,))

        result = reg.lookup_param(
            "/AUTOSAR/UnknownModule/SomeContainer/SomeParam",
        )
        assert result is None

    def test_lookup_param_with_empty_path_returns_none(self) -> None:
        """``lookup_param`` 空路径 → ``None``。"""
        reg = BSWMDRegistry()
        assert reg.lookup_param("") is None
        assert reg.lookup_param("/") is None

    def test_lookup_container_returns_container_def(
        self,
        tmp_workspace: Path,
    ) -> None:
        """``lookup_container`` 用 DEFINITION-REF 路径命中 ContainerDef。"""
        bswmd = tmp_workspace / "Mcu_Bswmd.arxml"
        _write_full_bswmd(bswmd)
        reg = BSWMDRegistry.load((bswmd,))

        c = reg.lookup_container("/AUTOSAR/Mcu/McuClockSettingConfig")
        assert c is not None
        assert c.short_name == "McuClockSettingConfig"
        assert c.upper_multiplicity == 3

    def test_lookup_container_miss_returns_none(
        self,
        tmp_workspace: Path,
    ) -> None:
        """``lookup_container`` miss → ``None``（不抛）。"""
        bswmd = tmp_workspace / "Mcu_Bswmd.arxml"
        _write_full_bswmd(bswmd)
        reg = BSWMDRegistry.load((bswmd,))

        assert reg.lookup_container("/AUTOSAR/Mcu/Nonexistent") is None

    def test_lookup_module_returns_module_def(
        self,
        tmp_workspace: Path,
    ) -> None:
        """``lookup_module`` 按 short_name 命中 ModuleDef。"""
        bswmd = tmp_workspace / "Mcu_Bswmd.arxml"
        _write_full_bswmd(bswmd)
        reg = BSWMDRegistry.load((bswmd,))

        m = reg.lookup_module("Mcu")
        assert m is not None
        assert m.short_name == "Mcu"

    def test_lookup_module_miss_returns_none(self) -> None:
        """``lookup_module`` miss → ``None``。"""
        reg = BSWMDRegistry()
        assert reg.lookup_module("Unknown") is None


# ---------------------------------------------------------------------------
# TestBSWMDRegistryContainer — __len__ / __contains__
# ---------------------------------------------------------------------------


class TestBSWMDRegistryContainer:
    """``__len__`` / ``__contains__`` 容器协议。"""

    def test_len_returns_module_count(
        self,
        tmp_workspace: Path,
    ) -> None:
        """``len(reg)`` 返回模块数。"""
        bswmd = tmp_workspace / "Mcu_Bswmd.arxml"
        _write_full_bswmd(bswmd)
        reg = BSWMDRegistry.load((bswmd,))

        assert len(reg) == 1

    def test_contains_checks_module_name(
        self,
        tmp_workspace: Path,
    ) -> None:
        """``"Mcu" in reg`` 按 module name 判断。"""
        bswmd = tmp_workspace / "Mcu_Bswmd.arxml"
        _write_full_bswmd(bswmd)
        reg = BSWMDRegistry.load((bswmd,))

        assert "Mcu" in reg
        assert "Port" not in reg

    def test_contains_with_path_returns_true_when_param_exists(
        self,
        tmp_workspace: Path,
    ) -> None:
        """``"/AUTOSAR/Mcu/..." in reg`` 命中参数或容器时 True。"""
        bswmd = tmp_workspace / "Mcu_Bswmd.arxml"
        _write_full_bswmd(bswmd)
        reg = BSWMDRegistry.load((bswmd,))

        assert "/AUTOSAR/Mcu" in reg
        assert "/AUTOSAR/Mcu/McuClockSettingConfig" in reg
        assert "/AUTOSAR/Mcu/McuClockSettingConfig/McuClockFrequency" in reg

    def test_contains_with_path_returns_false_for_miss(
        self,
        tmp_workspace: Path,
    ) -> None:
        """``__contains__`` miss → False。"""
        bswmd = tmp_workspace / "Mcu_Bswmd.arxml"
        _write_full_bswmd(bswmd)
        reg = BSWMDRegistry.load((bswmd,))

        assert "/AUTOSAR/Mcu/Nonexistent" not in reg
        assert "/AUTOSAR/OtherModule" not in reg


# ---------------------------------------------------------------------------
# TestMerge — merge 行为（与 test_bswmd_load_default 互补）
# ---------------------------------------------------------------------------


class TestBSWMDRegistryMergeDeep:
    """``BSWMDRegistry.merge`` 深合并行为（按 module name 覆盖）。"""

    def test_merge_overrides_same_module_with_different_param_defs(
        self,
        tmp_workspace: Path,
    ) -> None:
        """同名 module 合并：other 的 containers / params 覆盖 self。"""
        m1 = ModuleDef(
            short_name="Mcu",
            full_path="/A/Mcu",
            containers={
                "Old": ContainerDef(
                    short_name="Old",
                    full_path="/A/Mcu/Old",
                    lower_multiplicity=0,
                    upper_multiplicity=1,
                ),
            },
        )
        m2 = ModuleDef(
            short_name="Mcu",
            full_path="/A/Mcu",
            containers={
                "New": ContainerDef(
                    short_name="New",
                    full_path="/A/Mcu/New",
                    lower_multiplicity=0,
                    upper_multiplicity=1,
                ),
            },
        )
        a = BSWMDRegistry(modules={"Mcu": m1}, root_package_name="A")
        b = BSWMDRegistry(modules={"Mcu": m2}, root_package_name="A")
        merged = a.merge(b)

        # 合并后 Mcu 应含 New（other 赢）
        assert "New" in merged.modules["Mcu"].containers
        assert "Old" not in merged.modules["Mcu"].containers


# ---------------------------------------------------------------------------
# TestFallback — DEST 启发式不破（与 ecuc._infer_type 集成）
# ---------------------------------------------------------------------------


class TestFallbackBehavior:
    """``lookup_param`` 返回 ``None`` 时不破；消费方应 fallback 到 DEST 启发式。"""

    def test_lookup_param_returns_none_for_unregistered_path(
        self,
        tmp_workspace: Path,
    ) -> None:
        """未在 BSWMD 注册的 path → ``None``（不抛 — 契约 2 向后兼容）。"""
        bswmd = tmp_workspace / "Mcu_Bswmd.arxml"
        _write_full_bswmd(bswmd)
        reg = BSWMDRegistry.load((bswmd,))

        # 一个不存在的 param（即使 module 存在）
        assert (
            reg.lookup_param(
                "/AUTOSAR/Mcu/McuClockSettingConfig/UnknownParam",
            )
            is None
        )
