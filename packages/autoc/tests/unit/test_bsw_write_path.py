"""Unit tests for ``bsw_write_path.py`` (T8.E.3).

Plan reference: Sprint 8.E T8.E.3 — ``core/bsw/bsw_write_path.py`` 多重度 / 类型 / range 校验。
Contract 2: BSWMDRegistry + ParamDef（消费）。
Contract 5: BSWWritePathError + validate_writes_against_bswmd（被测对象）。
Contract 7: TestBSWWritePath（test 命名空间）。

测试要点（plan T8.E.3 RED 测试段）：
- ``upper=3`` 写 2 个 → ok
- ``upper=3`` 写 4 个 → 抛，msg 含 "UPPER-MULTIPLICITY=3"
- ``lower=2`` 写 1 个 → 抛，msg 含 "LOWER-MULTIPLICITY=2"
- 写 INTEGER 的 raw = ``"abc"`` → 抛 + 显式 "type INTEGER"
- ENUM 写不在 ``symbol_strings`` 的值 → 抛 + 列出合法值
- INTEGER 写 ``min - 1`` → 抛
- BSWMD 没记录的 path → 走 fallback（不抛）
- 不传 registry → 跳过校验（向后兼容）
- ``upper=-1`` → 任意 N 都过
- 集成：``modify_and_verify`` 在 BSWMD 不通过时不调 verify（直接 fail）
"""

from __future__ import annotations

from pathlib import Path

import pytest

from autoc.adapters.protocol import (
    EcuConfigProjectContext,
    SaveResult,
    VerifyResult,
)
from autoc.adapters.stub import StubTresosAdapter
from autoc.core.bsw.bsw_write_path import (
    BSWWritePathError,
    validate_writes_against_bswmd,
)
from autoc.core.bsw.bswmd import (
    BSWMDRegistry,
    ContainerDef,
    ModuleDef,
    ParamDef,
)
from autoc.core.bsw.config import BSWParam, ParamType, ParamValue
from autoc.core.bsw.ecuc import ECUCValue
from autoc.core.bsw.validator import (
    ModifyRequest,
    modify_and_verify,
)

pytestmark = pytest.mark.autosar


# ---------------------------------------------------------------------------
# Module-level fixture helpers（不碰 conftest.py；契约 7）
# ---------------------------------------------------------------------------


def _build_registry_with_param(
    *,
    short_name: str,
    param_type: str = "INTEGER",
    min_val: str | None = None,
    max_val: str | None = None,
    symbol_strings: tuple[str, ...] = (),
    container_short_name: str | None = None,
    container_lower: int = 0,
    container_upper: int = 1,
) -> BSWMDRegistry:
    """构造一个含 1 个 module + 1 个 container + 1 个 param 的最小 registry。

    模块名 = ``Mcu``；根包名 = ``AUTOSAR``。
    ParamDef.full_path = ``/AUTOSAR/Mcu[/Container]/<short_name>``。
    """
    if container_short_name is not None:
        param_full = f"/AUTOSAR/Mcu/{container_short_name}/{short_name}"
        container_full = f"/AUTOSAR/Mcu/{container_short_name}"
        container = ContainerDef(
            short_name=container_short_name,
            full_path=container_full,
            lower_multiplicity=container_lower,
            upper_multiplicity=container_upper,
            param_defs={
                short_name: ParamDef(
                    short_name=short_name,
                    full_path=param_full,
                    param_type=param_type,  # type: ignore[arg-type]
                    min=min_val,
                    max=max_val,
                    symbol_strings=symbol_strings,
                )
            },
        )
        module = ModuleDef(
            short_name="Mcu",
            full_path="/AUTOSAR/Mcu",
            containers={container_short_name: container},
        )
    else:
        param_full = f"/AUTOSAR/Mcu/{short_name}"
        module = ModuleDef(
            short_name="Mcu",
            full_path="/AUTOSAR/Mcu",
            params={
                short_name: ParamDef(
                    short_name=short_name,
                    full_path=param_full,
                    param_type=param_type,  # type: ignore[arg-type]
                    min=min_val,
                    max=max_val,
                    symbol_strings=symbol_strings,
                )
            },
        )
    return BSWMDRegistry(modules={"Mcu": module}, root_package_name="AUTOSAR")


def _bsw_param(
    path: str,
    raw: str,
    ptype: ParamType = ParamType.INTEGER,
    def_ref: str | None = None,
) -> BSWParam:
    return BSWParam(path=path, value=ParamValue(raw=raw, type=ptype), def_ref=def_ref)


# ---------------------------------------------------------------------------
# BSWWritePathError 自身（契约 5 锁定字段 + 字符串格式）
# ---------------------------------------------------------------------------


class TestBSWWritePathError:
    """BSWWritePathError 字段与消息格式。"""

    def test_basic_construction(self) -> None:
        """最小 3 字段构造。"""
        err = BSWWritePathError(
            param_path="Mcu/Freq",
            param_index=0,
            reason="value is not type INTEGER",
        )
        assert err.param_path == "Mcu/Freq"
        assert err.param_index == 0
        assert err.reason == "value is not type INTEGER"
        assert err.expected_min is None
        assert err.expected_max is None
        assert err.actual_value is None

    def test_str_includes_path_and_reason(self) -> None:
        """``str(err)`` 含 path + reason。"""
        err = BSWWritePathError(
            param_path="Mcu/Freq",
            param_index=0,
            reason="value is not type INTEGER",
        )
        msg = str(err)
        assert "Mcu/Freq" in msg
        assert "value is not type INTEGER" in msg

    def test_str_includes_extras_when_set(self) -> None:
        """expected_min/max/actual 非 None 时附在消息尾。"""
        err = BSWWritePathError(
            param_path="Mcu/Freq",
            param_index=0,
            reason="INTEGER value below MIN=0",
            expected_min=0,
            actual_value="-1",
        )
        msg = str(err)
        assert "Mcu/Freq" in msg
        assert "expected_min=0" in msg
        assert "actual='-1'" in msg

    def test_is_exception(self) -> None:
        """BSWWritePathError 是 Exception 派生（契约 5 锁定）。"""
        err = BSWWritePathError(param_path="Mcu/Freq", param_index=0, reason="x")
        assert isinstance(err, Exception)
        with pytest.raises(BSWWritePathError):
            raise err

    def test_is_frozen(self) -> None:
        """frozen dataclass 不可改字段。"""
        from dataclasses import FrozenInstanceError

        err = BSWWritePathError(param_path="Mcu/Freq", param_index=0, reason="x")
        with pytest.raises(FrozenInstanceError):
            err.param_path = "Mcu/X"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# validate_writes_against_bswmd
# ---------------------------------------------------------------------------


class TestValidateWrites:
    """主函数正向 / 反向用例（契约 5 + plan RED 段）。"""

    # ---- registry=None → 跳过校验（向后兼容） ----

    def test_registry_none_skips(self) -> None:
        """不传 registry → 跳过校验，不抛。"""
        # 写一个 BSWMD 必拒的非法 INTEGER
        bad = _bsw_param("Mcu/Freq", "abc", ParamType.INTEGER)
        # 不抛即过
        validate_writes_against_bswmd(None, "Mcu", (), (bad,))

    def test_registry_none_with_empty_writes(self) -> None:
        """registry=None + 空 writes → 不抛。"""
        validate_writes_against_bswmd(None, "Mcu", (), ())

    # ---- BSWMD 没记录的 path → fallback 不抛 ----

    def test_unknown_param_path_falls_back(self) -> None:
        """BSWMD 找不到的 param path → 跳过校验（不抛）。"""
        reg = _build_registry_with_param(short_name="Freq")
        # path 在 BSWMD 里有（Freq），但走"非 Freq 路径"
        unknown = _bsw_param("Mcu/UnknownParam", "999", ParamType.INTEGER)
        # 不抛即过
        validate_writes_against_bswmd(reg, "Mcu", (), (unknown,))

    # ---- INTEGER 类型 + range ----

    def test_integer_within_range_passes(self) -> None:
        """INTEGER 写范围内值 → ok。"""
        reg = _build_registry_with_param(short_name="Freq", min_val="0", max_val="300000000")
        p = _bsw_param("Mcu/Freq", "80000000", ParamType.INTEGER)
        validate_writes_against_bswmd(reg, "Mcu", (), (p,))

    def test_integer_below_min_raises(self) -> None:
        """INTEGER 写 min-1 → 抛 BSWWritePathError，msg 含 MIN。"""
        reg = _build_registry_with_param(short_name="Freq", min_val="0", max_val="300000000")
        p = _bsw_param("Mcu/Freq", "-1", ParamType.INTEGER)
        with pytest.raises(BSWWritePathError) as exc_info:
            validate_writes_against_bswmd(reg, "Mcu", (), (p,))
        assert "MIN=0" in str(exc_info.value)
        assert exc_info.value.expected_min == 0

    def test_integer_above_max_raises(self) -> None:
        """INTEGER 写 max+1 → 抛 BSWWritePathError，msg 含 MAX。"""
        reg = _build_registry_with_param(short_name="Freq", min_val="0", max_val="300000000")
        p = _bsw_param("Mcu/Freq", "300000001", ParamType.INTEGER)
        with pytest.raises(BSWWritePathError) as exc_info:
            validate_writes_against_bswmd(reg, "Mcu", (), (p,))
        assert "MAX=300000000" in str(exc_info.value)
        assert exc_info.value.expected_max == 300000000

    def test_integer_non_numeric_raises(self) -> None:
        """INTEGER 写 raw = "abc" → 抛 + 显式 "type INTEGER"。"""
        reg = _build_registry_with_param(
            short_name="Freq", param_type="INTEGER", min_val="0", max_val="100"
        )
        # 强制 BSWParam 构造（默认是 INTEGER ParamType）
        p = BSWParam(path="Mcu/Freq", value=ParamValue(raw="abc", type=ParamType.INTEGER))
        with pytest.raises(BSWWritePathError) as exc_info:
            validate_writes_against_bswmd(reg, "Mcu", (), (p,))
        assert "INTEGER" in str(exc_info.value)
        assert exc_info.value.actual_value == "abc"

    # ---- ENUMERATION 合法值 ----

    def test_enum_valid_value_passes(self) -> None:
        """ENUMERATION 写在 symbol_strings 内 → ok。"""
        reg = _build_registry_with_param(
            short_name="Source",
            param_type="ENUMERATION",
            symbol_strings=("PLL", "XTAL", "RC"),
        )
        p = BSWParam(path="Mcu/Source", value=ParamValue(raw="PLL", type=ParamType.ENUMERATION))
        validate_writes_against_bswmd(reg, "Mcu", (), (p,))

    def test_enum_invalid_value_raises(self) -> None:
        """ENUMERATION 写不在 symbol_strings 的值 → 抛 + 列出合法值。"""
        reg = _build_registry_with_param(
            short_name="Source",
            param_type="ENUMERATION",
            symbol_strings=("PLL", "XTAL", "RC"),
        )
        p = BSWParam(
            path="Mcu/Source",
            value=ParamValue(raw="INVALID", type=ParamType.ENUMERATION),
        )
        with pytest.raises(BSWWritePathError) as exc_info:
            validate_writes_against_bswmd(reg, "Mcu", (), (p,))
        msg = str(exc_info.value)
        assert "ENUMERATION" in msg
        assert "PLL" in msg  # 列出了合法值

    def test_enum_empty_symbols_passes_any(self) -> None:
        """ENUMERATION 但 symbol_strings 空 → 不约束（向后兼容）。"""
        reg = _build_registry_with_param(
            short_name="Source",
            param_type="ENUMERATION",
            symbol_strings=(),
        )
        p = BSWParam(
            path="Mcu/Source",
            value=ParamValue(raw="AnythingGoes", type=ParamType.ENUMERATION),
        )
        validate_writes_against_bswmd(reg, "Mcu", (), (p,))

    # ---- BOOLEAN ----

    def test_boolean_true_passes(self) -> None:
        """BOOLEAN 写 'true' → ok。"""
        reg = _build_registry_with_param(short_name="En", param_type="BOOLEAN")
        p = BSWParam(path="Mcu/En", value=ParamValue(raw="true", type=ParamType.BOOLEAN))
        validate_writes_against_bswmd(reg, "Mcu", (), (p,))

    def test_boolean_invalid_raises(self) -> None:
        """BOOLEAN 写 'maybe' → 抛。"""
        reg = _build_registry_with_param(short_name="En", param_type="BOOLEAN")
        p = BSWParam(path="Mcu/En", value=ParamValue(raw="maybe", type=ParamType.BOOLEAN))
        with pytest.raises(BSWWritePathError) as exc_info:
            validate_writes_against_bswmd(reg, "Mcu", (), (p,))
        assert "BOOLEAN" in str(exc_info.value)

    # ---- FLOAT range ----

    def test_float_within_range_passes(self) -> None:
        """FLOAT 写范围内值 → ok。"""
        reg = _build_registry_with_param(
            short_name="Tol", param_type="FLOAT", min_val="0.0", max_val="1.0"
        )
        p = BSWParam(path="Mcu/Tol", value=ParamValue(raw="0.5", type=ParamType.FLOAT))
        validate_writes_against_bswmd(reg, "Mcu", (), (p,))

    def test_float_below_min_raises(self) -> None:
        """FLOAT 写 min-0.5 → 抛。"""
        reg = _build_registry_with_param(
            short_name="Tol", param_type="FLOAT", min_val="0.0", max_val="1.0"
        )
        p = BSWParam(path="Mcu/Tol", value=ParamValue(raw="-0.5", type=ParamType.FLOAT))
        with pytest.raises(BSWWritePathError) as exc_info:
            validate_writes_against_bswmd(reg, "Mcu", (), (p,))
        assert "MIN=0" in str(exc_info.value)

    def test_float_above_max_raises(self) -> None:
        """FLOAT 写 max+0.5 → 抛。"""
        reg = _build_registry_with_param(
            short_name="Tol", param_type="FLOAT", min_val="0.0", max_val="1.0"
        )
        p = BSWParam(path="Mcu/Tol", value=ParamValue(raw="1.5", type=ParamType.FLOAT))
        with pytest.raises(BSWWritePathError) as exc_info:
            validate_writes_against_bswmd(reg, "Mcu", (), (p,))
        assert "MAX=1" in str(exc_info.value)

    def test_float_non_numeric_raises(self) -> None:
        """FLOAT 写 'abc' → 抛 + 显式 FLOAT。"""
        reg = _build_registry_with_param(
            short_name="Tol", param_type="FLOAT", min_val="0.0", max_val="1.0"
        )
        p = BSWParam(path="Mcu/Tol", value=ParamValue(raw="abc", type=ParamType.FLOAT))
        with pytest.raises(BSWWritePathError) as exc_info:
            validate_writes_against_bswmd(reg, "Mcu", (), (p,))
        assert "FLOAT" in str(exc_info.value)

    # ---- STRING / FUNCTION_NAME：BSWMD 不约束 ----

    def test_string_always_passes(self) -> None:
        """STRING 写任意字符串 → ok（BSWMD 不约束）。"""
        reg = _build_registry_with_param(short_name="Name", param_type="STRING")
        p = BSWParam(path="Mcu/Name", value=ParamValue(raw="anything", type=ParamType.STRING))
        validate_writes_against_bswmd(reg, "Mcu", (), (p,))

    # ---- 容器 multiplicity（upper=3 / upper=4 fail / lower=2 fail / upper=-1 ok） ----

    def test_container_upper_3_write_2_passes(self) -> None:
        """upper=3 写 2 个 → ok。"""
        reg = _build_registry_with_param(
            short_name="Freq",
            container_short_name="Cfg",
            container_lower=0,
            container_upper=3,
            min_val="0",
            max_val="100",
        )
        # writes 全在 Cfg 容器内（同一容器名）
        p1 = BSWParam(path="Mcu/Cfg/Freq", value=ParamValue(raw="50", type=ParamType.INTEGER))
        # 第二个 param 也用 BSWMD 已知的 path（Freq 在 Cfg 容器下），
        # 但 multiplicity 检查"父容器内 writes 数"——这里用相同 path 来计数。
        # 为避免重复 type 检查导致 INTEGER 范围重复，先把它们都设为合法值：
        p2 = BSWParam(path="Mcu/Cfg/Freq", value=ParamValue(raw="60", type=ParamType.INTEGER))
        validate_writes_against_bswmd(reg, "Mcu", (), (p1, p2))

    def test_container_upper_3_write_4_raises(self) -> None:
        """upper=3 写 4 个 → 抛，msg 含 "UPPER-MULTIPLICITY=3"。

        current_values 给 3 个（在容器内），writes 给 2 个 → 总 5 > 3。
        """
        reg = _build_registry_with_param(
            short_name="Freq",
            container_short_name="Cfg",
            container_lower=0,
            container_upper=3,
            min_val="0",
            max_val="100",
        )
        existing = (
            ECUCValue(path="Mcu/Cfg/OtherA", raw="1", type="INTEGER"),
            ECUCValue(path="Mcu/Cfg/OtherB", raw="2", type="INTEGER"),
            ECUCValue(path="Mcu/Cfg/OtherC", raw="3", type="INTEGER"),
        )
        p1 = BSWParam(path="Mcu/Cfg/Freq", value=ParamValue(raw="50", type=ParamType.INTEGER))
        p2 = BSWParam(path="Mcu/Cfg/Freq", value=ParamValue(raw="60", type=ParamType.INTEGER))
        with pytest.raises(BSWWritePathError) as exc_info:
            validate_writes_against_bswmd(reg, "Mcu", existing, (p1, p2))
        assert "UPPER-MULTIPLICITY=3" in str(exc_info.value)
        assert exc_info.value.expected_max == 3

    def test_container_lower_2_write_1_raises(self) -> None:
        """lower=2 写 1 个 → 抛，msg 含 "LOWER-MULTIPLICITY=2"。

        current_values 空 + writes 1 个 → 总 1 < 2。
        """
        reg = _build_registry_with_param(
            short_name="Freq",
            container_short_name="Cfg",
            container_lower=2,
            container_upper=5,
            min_val="0",
            max_val="100",
        )
        p = BSWParam(path="Mcu/Cfg/Freq", value=ParamValue(raw="50", type=ParamType.INTEGER))
        with pytest.raises(BSWWritePathError) as exc_info:
            validate_writes_against_bswmd(reg, "Mcu", (), (p,))
        assert "LOWER-MULTIPLICITY=2" in str(exc_info.value)
        assert exc_info.value.expected_min == 2

    def test_container_unbounded_upper_always_passes(self) -> None:
        """upper=-1 (unbounded) → 任意 N 都过。"""
        reg = _build_registry_with_param(
            short_name="Freq",
            container_short_name="Cfg",
            container_lower=0,
            container_upper=-1,
            min_val="0",
            max_val="100",
        )
        # 造 100 个 existing + 1 write → unbounded
        existing = tuple(
            ECUCValue(path=f"Mcu/Cfg/X{i}", raw="1", type="INTEGER") for i in range(100)
        )
        p = BSWParam(path="Mcu/Cfg/Freq", value=ParamValue(raw="50", type=ParamType.INTEGER))
        validate_writes_against_bswmd(reg, "Mcu", existing, (p,))

    def test_container_unknown_in_registry_falls_back(self) -> None:
        """容器在 BSWMD 查不到 → multiplicity 跳过（fallback 不抛）。"""
        reg = _build_registry_with_param(
            short_name="Freq",
            container_short_name="Cfg",
            container_lower=0,
            container_upper=2,
            min_val="0",
            max_val="100",
        )
        # 写到一个 BSWMD 不知道的容器
        p = BSWParam(
            path="Mcu/UnknownContainer/Freq",
            value=ParamValue(raw="50", type=ParamType.INTEGER),
        )
        # 不抛即过（容器 unknown + param 路径也不在 registry）
        validate_writes_against_bswmd(reg, "Mcu", (), (p,))

    # ---- param_index 字段 ----

    def test_param_index_set_to_writes_index(self) -> None:
        """失败 param 在 writes 里的索引。"""
        reg = _build_registry_with_param(short_name="Freq", min_val="0", max_val="100")
        p1 = BSWParam(path="Mcu/Freq", value=ParamValue(raw="50", type=ParamType.INTEGER))
        p2 = BSWParam(path="Mcu/Freq", value=ParamValue(raw="999", type=ParamType.INTEGER))
        with pytest.raises(BSWWritePathError) as exc_info:
            validate_writes_against_bswmd(reg, "Mcu", (), (p1, p2))
        assert exc_info.value.param_index == 1

    # ---- def_ref 显式优先 ----

    def test_explicit_def_ref_used(self) -> None:
        """BSWParam.def_ref 显式给出 → 优先用 def_ref 查 BSWMD。"""
        # BSWMD 里 param 在 /AUTOSAR/Mcu/Alias/Freq（不在 Mcu/Freq）
        reg = _build_registry_with_param(
            short_name="Freq",
            container_short_name="Alias",
            min_val="0",
            max_val="100",
        )
        # ECUC path 走 Mcu/Freq（查不到），但显式 def_ref 指 Alias 容器
        p = BSWParam(
            path="Mcu/Freq",
            value=ParamValue(raw="50", type=ParamType.INTEGER),
            def_ref="/AUTOSAR/Mcu/Alias/Freq",
        )
        validate_writes_against_bswmd(reg, "Mcu", (), (p,))


# ---------------------------------------------------------------------------
# 集成：modify_and_verify + bswmd_registry kwarg
# ---------------------------------------------------------------------------


_MCU_XML = """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES><AR-PACKAGE><SHORT-NAME>B</SHORT-NAME><ELEMENTS>
    <ECUC-MODULE-CONFIGURATION-VALUES>
      <SHORT-NAME>Mcu</SHORT-NAME>
      <CONTAINERS>
        <ECUC-PARAM-CONF-CONTAINER>
          <SHORT-NAME>Root</SHORT-NAME>
          <PARAMETER-VALUES>
            <ECUC-NUMERICAL-PARAM-VALUE>
              <DEFINITION-REF DEST="ECUC-INTEGER-PARAM-DEF">/Mcu/Root/ClockFreq</DEFINITION-REF>
              <VALUE>80000000</VALUE>
            </ECUC-NUMERICAL-PARAM-VALUE>
          </PARAMETER-VALUES>
        </ECUC-PARAM-CONF-CONTAINER>
      </CONTAINERS>
    </ECUC-MODULE-CONFIGURATION-VALUES>
  </ELEMENTS></AR-PACKAGE></AR-PACKAGES>
</AUTOSAR>
"""


def _make_project(tmp_path: Path) -> Path:
    project = tmp_path / "bsw-project"
    project.mkdir()
    (project / "Mcu.xdm").write_text(_MCU_XML, encoding="utf-8")
    return project


def _make_ctx(project: Path) -> EcuConfigProjectContext:
    tool_home = project.parent / "fake-tresos"
    tool_home.mkdir(exist_ok=True)
    return EcuConfigProjectContext(
        project_path=project,
        tool_home=tool_home,
        target="S32K3",
        derivate="S32K344",
        pn="ARM",
        autosar_version="4.4.0",
        enabled_modules=("Mcu",),
        available_plugins=(),
    )


class TestModifyAndVerifyIntegration:
    """``modify_and_verify`` 集成 BSWMD 校验（plan RED 段最后一条）。"""

    def test_bswmd_validation_fail_skips_verify_and_save(self, tmp_path: Path) -> None:
        """BSWMD 校验失败 → 不调 verify / save，直接返回 ``ModifyResult(error=...)``。"""
        project = _make_project(tmp_path)
        ctx = _make_ctx(project)
        original_xml = (project / "Mcu.xdm").read_text(encoding="utf-8")

        # BSWMD 限制 ClockFreq 0..100，但传 999；ECUC path 是 Mcu/Root/ClockFreq
        reg = _build_registry_with_param(
            short_name="ClockFreq",
            container_short_name="Root",
            min_val="0",
            max_val="100",
        )
        adapter = StubTresosAdapter(
            discover_response=ctx,
            verify_responses=[VerifyResult(success=True, returncode=0, stdout="", stderr="")],
            save_responses=[SaveResult(success=True, returncode=0, stdout="", stderr="")],
        )
        result = modify_and_verify(
            ctx,
            adapter,
            ModifyRequest(
                module="Mcu",
                params=(
                    BSWParam(
                        "Mcu/Root/ClockFreq",
                        ParamValue("999", ParamType.INTEGER),
                    ),
                ),
            ),
            bswmd_registry=reg,
        )
        assert result.success is False
        assert result.error is not None
        assert "BSWMD validation failed" in result.error
        # verify / save 都没被调
        assert len(adapter.verify_calls) == 0
        assert len(adapter.save_calls) == 0
        # 文件未被改
        assert (project / "Mcu.xdm").read_text(encoding="utf-8") == original_xml

    def test_bswmd_validation_pass_proceeds_normally(self, tmp_path: Path) -> None:
        """BSWMD 校验通过 → 继续走原 verify / save 流程。"""
        project = _make_project(tmp_path)
        ctx = _make_ctx(project)

        # BSWMD 允许 0..300000000；ECUC path 是 Mcu/Root/ClockFreq
        reg = _build_registry_with_param(
            short_name="ClockFreq",
            container_short_name="Root",
            min_val="0",
            max_val="300000000",
        )
        adapter = StubTresosAdapter(
            discover_response=ctx,
            verify_responses=[VerifyResult(success=True, returncode=0, stdout="OK", stderr="")],
            save_responses=[
                SaveResult(
                    success=True,
                    returncode=0,
                    stdout="wrote",
                    stderr="",
                    written_files=(project / "Mcu.xdm",),
                )
            ],
        )
        result = modify_and_verify(
            ctx,
            adapter,
            ModifyRequest(
                module="Mcu",
                params=(
                    BSWParam(
                        "Mcu/Root/ClockFreq",
                        ParamValue("120000000", ParamType.INTEGER),
                    ),
                ),
            ),
            bswmd_registry=reg,
        )
        assert result.success is True
        assert result.error is None
        assert len(adapter.verify_calls) == 1
        assert len(adapter.save_calls) == 1

    def test_bswmd_registry_none_preserves_legacy_behavior(self, tmp_path: Path) -> None:
        """不传 bswmd_registry → 与 sprint 3 老行为一致（不校验 BSWMD）。"""
        project = _make_project(tmp_path)
        ctx = _make_ctx(project)
        adapter = StubTresosAdapter(
            discover_response=ctx,
            verify_responses=[VerifyResult(success=True, returncode=0, stdout="", stderr="")],
            save_responses=[
                SaveResult(
                    success=True,
                    returncode=0,
                    stdout="",
                    stderr="",
                    written_files=(project / "Mcu.xdm",),
                )
            ],
        )
        # 写 999 也不报错（不传 registry）
        result = modify_and_verify(
            ctx,
            adapter,
            ModifyRequest(
                module="Mcu",
                params=(
                    BSWParam(
                        "Mcu/Root/ClockFreq",
                        ParamValue("999", ParamType.INTEGER),
                    ),
                ),
            ),
        )
        assert result.success is True
