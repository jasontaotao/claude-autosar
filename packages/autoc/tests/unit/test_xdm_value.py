"""Unit tests for claude_autosar.core.bsw.templates.xdm_value.

Sprint 9.2 — T9.2-α. Covers:

  - dataclass frozen-ness / hashability
  - load_xdm_module happy path (DataModel2 2.0 fixture)
  - type inference heuristic (INTEGER / FLOAT / BOOLEAN / ENUMERATION / STRING)
  - path building (module / ctr / var)
  - missing module → XDMValueError
  - missing file → XDMValueError
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from claude_autosar.core.bsw.templates.xdm_value import (
    XDMModule,
    XDMValue,
    XDMValueError,
    XDMValueType,
    _infer_xdm_type,
    load_xdm_module,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DATAMODEL2_DIR = Path(__file__).parent.parent / "fixtures" / "datamodel2"

# 一个最小 DataModel2 2.0 fixture（tmp_path 里写，避免依赖现有 fixture
# 内容变化）。模块名 Can，包含若干 <d:var> 覆盖所有 5 种 type。
_MINIMAL_XDM = """<?xml version='1.0' encoding='UTF-8'?>
<datamodel version="7.0"
           xmlns="http://www.tresos.de/_projects/DataModel2/16/root.xsd"
           xmlns:a="http://www.tresos.de/_projects/DataModel2/16/attribute.xsd"
           xmlns:d="http://www.tresos.de/_projects/DataModel2/06/data.xsd">
  <d:ctr type="AUTOSAR" factory="autosar">
    <d:lst type="TOP-LEVEL-PACKAGES">
      <d:ctr name="Can" type="AR-PACKAGE">
        <d:lst type="ELEMENTS">
          <d:chc name="Can" type="AR-ELEMENT" value="MODULE-CONFIGURATION">
            <d:ctr type="MODULE-CONFIGURATION">
              <d:ctr name="CanConfigSet" type="IDENTIFIABLE">
                <d:var name="CanHwChannel" type="ENUMERATION" value="FlexCAN_A"/>
                <d:var name="CanControllerActivation" type="BOOLEAN" value="true"/>
                <d:var name="CanControllerBaudRate" type="INTEGER" value="500000"/>
                <d:var name="CanPropDelayTranceiver" type="FLOAT" value="5.0"/>
                <d:var name="CanRxFifoWarningNotification" type="FUNCTION-NAME"
                       value="NULL_PTR"/>
              </d:ctr>
              <d:ctr name="CanGeneral" type="IDENTIFIABLE">
                <d:var name="CanDevErrorDetect" type="BOOLEAN" value="false"/>
                <d:var name="CanMainFunctionPeriod" type="FLOAT" value="0.01"/>
              </d:ctr>
            </d:ctr>
          </d:chc>
        </d:lst>
      </d:ctr>
    </d:lst>
  </d:ctr>
</datamodel>
"""


@pytest.fixture
def can_xdm(tmp_path: Path) -> Path:
    """写一个最小 Can.xdm 到 tmp_path 并返回路径。"""
    p = tmp_path / "Can.xdm"
    p.write_text(_MINIMAL_XDM, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# 1. dataclass frozen / hashable
# ---------------------------------------------------------------------------


class TestXDMValueFrozen:
    def test_xdm_value_is_frozen(self) -> None:
        v = XDMValue(path="Can/A", raw="x", type="STRING")
        with pytest.raises(FrozenInstanceError):
            v.path = "Can/B"  # type: ignore[misc]

    def test_xdm_module_is_frozen(self) -> None:
        m = XDMModule(path=Path("/tmp/x.xdm"), module_name="Can", values=())
        with pytest.raises(FrozenInstanceError):
            m.module_name = "Mcu"  # type: ignore[misc]

    def test_xdm_value_is_hashable(self) -> None:
        # frozen dataclass 默认 __hash__；要求能放进 set
        v = XDMValue(path="Can/A", raw="x", type="STRING")
        assert {v} == {v}

    def test_xdm_module_is_hashable(self) -> None:
        m = XDMModule(path=Path("/tmp/x.xdm"), module_name="Can", values=())
        assert {m} == {m}


# ---------------------------------------------------------------------------
# 2. load_xdm_module happy path
# ---------------------------------------------------------------------------


class TestLoadXdmModuleHappyPath:
    def test_load_returns_xdm_module_with_correct_metadata(
        self, can_xdm: Path
    ) -> None:
        mod = load_xdm_module(can_xdm, "Can")
        assert isinstance(mod, XDMModule)
        assert mod.path == can_xdm
        assert mod.module_name == "Can"
        assert isinstance(mod.values, tuple)

    def test_load_extracts_all_d_var_leaves(self, can_xdm: Path) -> None:
        mod = load_xdm_module(can_xdm, "Can")
        names = {v.path.split("/")[-1] for v in mod.values}
        # fixture 里 7 个 <d:var>：CanHwChannel / CanControllerActivation /
        # CanControllerBaudRate / CanPropDelayTranceiver /
        # CanRxFifoWarningNotification / CanDevErrorDetect /
        # CanMainFunctionPeriod
        assert names == {
            "CanHwChannel",
            "CanControllerActivation",
            "CanControllerBaudRate",
            "CanPropDelayTranceiver",
            "CanRxFifoWarningNotification",
            "CanDevErrorDetect",
            "CanMainFunctionPeriod",
        }

    def test_paths_start_with_module_name(self, can_xdm: Path) -> None:
        mod = load_xdm_module(can_xdm, "Can")
        assert all(v.path.startswith("Can/") for v in mod.values)

    def test_uses_real_datamodel2_fixture_when_present(self) -> None:
        """如果仓库里有 fixtures/datamodel2/Can.xdm，加载它不报错（烟测）。"""
        if not DATAMODEL2_DIR.is_dir():
            pytest.skip("datamodel2 fixtures not present")
        can = DATAMODEL2_DIR / "Can.xdm"
        if not can.is_file():
            pytest.skip("Can.xdm fixture missing")
        mod = load_xdm_module(can, "Can")
        assert mod.module_name == "Can"
        # 真实 fixture 一定有至少几十个 <d:var>
        assert len(mod.values) > 10


# ---------------------------------------------------------------------------
# 3. type inference heuristic
# ---------------------------------------------------------------------------


class TestInferXdmType:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("INT", "INTEGER"),
            ("INTEGER", "INTEGER"),
            ("int", "INTEGER"),
            ("FLOAT", "FLOAT"),
            ("DOUBLE", "FLOAT"),
            ("float", "FLOAT"),
            ("BOOL", "BOOLEAN"),
            ("BOOLEAN", "BOOLEAN"),
            ("bool", "BOOLEAN"),
            ("ENUM", "ENUMERATION"),
            ("ENUMERATION", "ENUMERATION"),
            ("FUNCTION-NAME", "STRING"),
            ("REFERENCE", "STRING"),
            ("", "STRING"),
            ("UNKNOWN-TYPE", "STRING"),
        ],
    )
    def test_infer_returns_literal_value(
        self, raw: str, expected: XDMValueType
    ) -> None:
        assert _infer_xdm_type(raw) == expected


# ---------------------------------------------------------------------------
# 4. type inference integration (load → leaf type)
# ---------------------------------------------------------------------------


class TestLoadLeavesHaveCorrectTypes:
    def test_integer_leaf_has_integer_type(self, can_xdm: Path) -> None:
        mod = load_xdm_module(can_xdm, "Can")
        baud = _find(mod, "CanControllerBaudRate")
        assert baud.type == "INTEGER"
        assert baud.raw == "500000"

    def test_float_leaf_has_float_type(self, can_xdm: Path) -> None:
        mod = load_xdm_module(can_xdm, "Can")
        delay = _find(mod, "CanPropDelayTranceiver")
        assert delay.type == "FLOAT"
        assert delay.raw == "5.0"

    def test_boolean_leaf_has_boolean_type(self, can_xdm: Path) -> None:
        mod = load_xdm_module(can_xdm, "Can")
        dev = _find(mod, "CanDevErrorDetect")
        assert dev.type == "BOOLEAN"
        assert dev.raw == "false"

    def test_enumeration_leaf_has_enumeration_type(
        self, can_xdm: Path
    ) -> None:
        mod = load_xdm_module(can_xdm, "Can")
        hwch = _find(mod, "CanHwChannel")
        assert hwch.type == "ENUMERATION"
        assert hwch.raw == "FlexCAN_A"

    def test_function_name_leaf_falls_back_to_string(
        self, can_xdm: Path
    ) -> None:
        mod = load_xdm_module(can_xdm, "Can")
        notif = _find(mod, "CanRxFifoWarningNotification")
        # FUNCTION-NAME 不是 ECUC/XDMValueType 5 种之一 → STRING
        assert notif.type == "STRING"
        assert notif.raw == "NULL_PTR"


# ---------------------------------------------------------------------------
# 5. error paths
# ---------------------------------------------------------------------------


class TestLoadErrors:
    def test_missing_module_raises_xdm_value_error(
        self, can_xdm: Path
    ) -> None:
        with pytest.raises(XDMValueError) as exc_info:
            load_xdm_module(can_xdm, "NonExistent")
        assert "NonExistent" in str(exc_info.value)
        assert "not found" in str(exc_info.value)

    def test_missing_file_raises_xdm_value_error(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(XDMValueError) as exc_info:
            load_xdm_module(tmp_path / "does_not_exist.xdm", "Can")
        assert "not readable" in str(exc_info.value)

    def test_wrong_format_raises_xdm_value_error(
        self, tmp_path: Path
    ) -> None:
        # 写一个 arxml 风格的 .xdm 命名（让 dispatcher 探测失败）
        bad = tmp_path / "wrong.xdm"
        bad.write_text(
            '<?xml version="1.0"?><AR-PACKAGES xmlns="http://autosar.org/schema/r4.0"/>',
            encoding="utf-8",
        )
        with pytest.raises(XDMValueError):
            load_xdm_module(bad, "Can")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find(mod: XDMModule, name: str) -> XDMValue:
    """在 mod.values 里找 path 以 /name 结尾的 leaf。"""
    matches = [v for v in mod.values if v.path.endswith(f"/{name}")]
    assert len(matches) == 1, f"expected 1 leaf named {name}, got {len(matches)}"
    return matches[0]
