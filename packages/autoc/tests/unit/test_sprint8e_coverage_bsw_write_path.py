"""Sprint 8.E coverage tests for ``bsw_write_path.py``（T8.E.3）。

Plan reference: Sprint 8.E T8.E.3 — ``core/bsw/bsw_write_path.py`` 多重度 / 类型 / range 校验。
Contract 2: BSWMDRegistry + ParamDef（消费，不改字段）。
Contract 5: BSWWritePathError + validate_writes_against_bswmd（被测对象；不改签名）。
Contract 7: TestBSWWritePathCoverage（命名空间）。

**目标**：把现有 ~83% coverage 拉到 ~100%。专门覆盖 missing 分支：
- 行 117（``not writes`` 早返回）
- 行 179-184（``_strip_instance_index`` 各种条件）
- 行 254（``_parent_container_path`` 顶层 param → ""）
- 行 271（``getattr`` 失败 → skip）
- 行 274-276（顶层 param 计数）
- 行 277（``startswith`` / 精确匹配）
- 行 355（未知 BSWMD 类型 → fallback 调试 log）
- 行 368-372 / 384-385（INTEGER min/max 转换失败 + skip）
- 行 402-406 / 418-419（FLOAT min/max 转换失败 + skip）
- 启发式 DEST 后缀：BSWMD 优先 + fallback

**遵守契约**：
- 不改 bsw_write_path.py 源码
- 不改 conftest.py
- 测试命名空间 ``TestBSWWritePathCoverage``
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

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
# BSWWritePathError 字段与不可变（契约 5：字段名 / 类型 / 默认值）
# ---------------------------------------------------------------------------


class TestBSWWritePathCoverageErrorFields:
    """BSWWritePathError 全部字段 + frozen 不可变。"""

    def test_all_fields_set(self) -> None:
        """全字段构造：param_path / param_index / reason / expected_min / expected_max / actual_value。"""
        err = BSWWritePathError(
            param_path="Mcu/Freq",
            param_index=2,
            reason="container exceeds UPPER-MULTIPLICITY=3",
            expected_min=0,
            expected_max=3,
            actual_value="5",
        )
        assert err.param_path == "Mcu/Freq"
        assert err.param_index == 2
        assert err.reason == "container exceeds UPPER-MULTIPLICITY=3"
        assert err.expected_min == 0
        assert err.expected_max == 3
        assert err.actual_value == "5"

    def test_param_index_can_be_none(self) -> None:
        """param_index 允许为 None（容器级错误时）。"""
        err = BSWWritePathError(
            param_path="Mcu/Cfg",
            param_index=None,
            reason="container below LOWER-MULTIPLICITY=2",
            expected_min=2,
            expected_max=5,
            actual_value="1",
        )
        assert err.param_index is None

    def test_str_includes_expected_max(self) -> None:
        """expected_max 不为 None 时出现在消息尾。"""
        err = BSWWritePathError(
            param_path="Mcu/Freq",
            param_index=0,
            reason="INTEGER value above MAX=200",
            expected_max=200,
            actual_value="999",
        )
        msg = str(err)
        assert "expected_max=200" in msg
        assert "actual='999'" in msg

    def test_str_omits_all_extras(self) -> None:
        """extras 全 None 时只输出 ``<path>: <reason>``。"""
        err = BSWWritePathError(
            param_path="Mcu/Freq",
            param_index=0,
            reason="value is not type INTEGER",
        )
        msg = str(err)
        assert msg == "Mcu/Freq: value is not type INTEGER"
        assert "expected_min" not in msg
        assert "expected_max" not in msg
        assert "actual" not in msg

    def test_frozen_immutability(self) -> None:
        """frozen=True 阻止字段修改。"""
        err = BSWWritePathError(param_path="Mcu/Freq", param_index=0, reason="x")
        with pytest.raises(FrozenInstanceError):
            err.param_path = "Mcu/Other"  # type: ignore[misc]

    def test_str_excludes_none_extras(self) -> None:
        """extras 局部为 None 时只附加非 None 部分。"""
        err = BSWWritePathError(
            param_path="Mcu/Freq",
            param_index=0,
            reason="INTEGER value above MAX=200",
            expected_min=None,
            expected_max=200,
            actual_value=None,
        )
        msg = str(err)
        # 只 expected_max 应出现
        assert "expected_max=200" in msg
        assert "expected_min" not in msg
        assert "actual" not in msg


# ---------------------------------------------------------------------------
# 行 117：``if not writes: return`` 早返回
# ---------------------------------------------------------------------------


class TestBSWWritePathCoverageEmptyWrites:
    """空 writes 早返回（行 117） + 配套负向 case。"""

    def test_empty_writes_returns_early_with_registry(self) -> None:
        """``writes=()`` → 不进入 multiplicity / 单 param 校验，函数直接 return。"""
        reg = _build_registry_with_param(short_name="Freq", min_val="0", max_val="100")
        # 不抛即过（空 writes 触发行 117 早返回）
        validate_writes_against_bswmd(reg, "Mcu", (), ())

    def test_empty_writes_with_failing_current_values(self) -> None:
        """``writes=()`` 即便 current_values 不合规也不抛。"""
        reg = _build_registry_with_param(
            short_name="Freq",
            container_short_name="Cfg",
            container_lower=10,  # 即便有高下限
            container_upper=20,
        )
        # current_values 不足 → 严格说会触发 lower-mult fail；但 writes 空走早返回
        validate_writes_against_bswmd(reg, "Mcu", (), ())

    def test_empty_writes_with_unknown_param_path(self) -> None:
        """空 writes + BSWMD 不知道的 module 也不抛。"""
        reg = _build_registry_with_param(short_name="Freq")
        # 走空 writes 早返回，根本不看 param path
        validate_writes_against_bswmd(reg, "Mcu", (), ())


# ---------------------------------------------------------------------------
# 行 179-184：``_strip_instance_index`` 启发式各种条件
# ---------------------------------------------------------------------------


class TestBSWWritePathCoverageStripInstanceIndex:
    """``McuClockSettingConfig_0`` → ``McuClockSettingConfig`` 等启发式分支。"""

    def test_strip_trailing_digit_index(self) -> None:
        """``Cfg_0`` → ``Cfg``（tail.isdigit() 命中 + head 非空）。"""
        from autoc.core.bsw.bsw_write_path import _strip_instance_index

        assert _strip_instance_index("McuClockSettingConfig_0") == "McuClockSettingConfig"
        assert _strip_instance_index("McuClockSettingConfig_12") == "McuClockSettingConfig"
        assert _strip_instance_index("X_1") == "X"

    def test_no_underscore_returns_unchanged(self) -> None:
        """无下划线 → 原样返回（行 177-178）。"""
        from autoc.core.bsw.bsw_write_path import _strip_instance_index

        assert _strip_instance_index("Mcu") == "Mcu"
        assert _strip_instance_index("Freq") == "Freq"
        assert _strip_instance_index("") == ""

    def test_underscore_but_tail_not_digit(self) -> None:
        """下划线但 tail 非数字（``My_Name``）→ 原样返回（行 184）。"""
        from autoc.core.bsw.bsw_write_path import _strip_instance_index

        assert _strip_instance_index("My_Name") == "My_Name"
        assert _strip_instance_index("A_B_C") == "A_B_C"  # tail="C" 不是数字

    def test_underscore_with_empty_head(self) -> None:
        """下划线在最前（``_0``）→ head 为空，return 原样（行 180-181）。"""
        from autoc.core.bsw.bsw_write_path import _strip_instance_index

        assert _strip_instance_index("_0") == "_0"
        assert _strip_instance_index("_123") == "_123"

    def test_underscore_with_mixed_tail(self) -> None:
        """``_0a`` → tail="0a" 不是纯数字 → 原样返回。"""
        from autoc.core.bsw.bsw_write_path import _strip_instance_index

        # rpartition('_') → ('Cfg', '_', '0a')，tail="0a".isdigit() = False
        assert _strip_instance_index("Cfg_0a") == "Cfg_0a"

    def test_ecuc_path_to_def_ref_strips_indices(self) -> None:
        """``_ecuc_path_to_def_ref`` 路径上的所有 instance index 被剥。"""
        from autoc.core.bsw.bsw_write_path import _ecuc_path_to_def_ref

        out = _ecuc_path_to_def_ref("Mcu/McuClockSettingConfig_0/McuClockFrequency_3", "AUTOSAR")
        assert out == "/AUTOSAR/Mcu/McuClockSettingConfig/McuClockFrequency"

    def test_ecuc_path_filters_empty_segments(self) -> None:
        """``/`` 开头 / 双 ``//`` 等产生的空段被过滤。"""
        from autoc.core.bsw.bsw_write_path import _ecuc_path_to_def_ref

        out = _ecuc_path_to_def_ref("/Mcu//Freq/", "AUTOSAR")
        # 过滤后是 ["Mcu", "Freq"]，前导加 "/AUTOSAR/"
        assert out == "/AUTOSAR/Mcu/Freq"


# ---------------------------------------------------------------------------
# 行 254 / 274-276：``_parent_container_path`` 顶层 param + 顶层计数
# ---------------------------------------------------------------------------


class TestBSWWritePathCoverageTopLevelParent:
    """顶层 param（无 ``/``）→ ``_parent_container_path`` 返回 ``""``。"""

    def test_top_level_param_parent_path_empty(self) -> None:
        """单段 path → 父容器路径为 ``""``（行 254）。"""
        from autoc.core.bsw.bsw_write_path import _parent_container_path

        assert _parent_container_path("Mcu/Freq") == "Mcu"  # 2 段：父 = "Mcu"
        assert _parent_container_path("Mcu") == ""  # 1 段：顶层

    def test_top_level_param_multiplicity_check_falls_back(self) -> None:
        """顶层 param 走 BSWMD 查不到 → multiplicity 跳过（不抛）。

        ``Mcu/Freq`` 的父路径是 ``Mcu``；BSWMD 里只注册了顶层 param 没注册 Mcu 容器 → fallback。
        """
        reg = _build_registry_with_param(short_name="Freq")
        # 顶层 param（无下标路径），Mcu 容器在 BSWMD 不存在
        p = BSWParam(path="Mcu/Freq", value=ParamValue(raw="50", type=ParamType.INTEGER))
        # 父路径 "Mcu" → _ecuc_path_to_def_ref → "/AUTOSAR/Mcu" → lookup_container 找不到
        # 触发行 214-215 fallback
        validate_writes_against_bswmd(reg, "Mcu", (), (p,))


class TestBSWWritePathCoverageCountExistingInParent:
    """``_count_existing_in_parent`` 各种 duck-typing 路径（行 267-280）。"""

    def test_value_without_path_attr_skipped(self) -> None:
        """v 没有 .path 属性（如 int/None）→ skip（行 270-271）。"""
        from autoc.core.bsw.bsw_write_path import _count_existing_in_parent

        # v 是 int，没有任何属性
        assert _count_existing_in_parent((42, "str", None), "Mcu/Cfg") == 0

    def test_value_with_non_string_path_skipped(self) -> None:
        """v.path 不是 str → skip（行 271）。"""
        from autoc.core.bsw.bsw_write_path import _count_existing_in_parent

        class WeirdValue:
            path = 123  # 不是 str

        assert _count_existing_in_parent((WeirdValue(),), "Mcu/Cfg") == 0

    def test_top_level_parent_counts_single_segment_paths(self) -> None:
        """parent="" + v_path 是单段 → count + 1（行 272-276）。"""
        from autoc.core.bsw.bsw_write_path import _count_existing_in_parent

        class V:
            def __init__(self, p: str) -> None:
                self.path = p

        # 顶层：单段 path
        assert _count_existing_in_parent((V("A"), V("B")), "") == 2
        # 多段 path 不算顶层
        assert _count_existing_in_parent((V("A/B"),), "") == 0
        # 混合
        assert _count_existing_in_parent((V("X"), V("Y/Z")), "") == 1

    def test_non_empty_parent_startswith_count(self) -> None:
        """v_path 在父容器下 → count（行 277 startswith 分支）。"""
        from autoc.core.bsw.bsw_write_path import _count_existing_in_parent

        class V:
            def __init__(self, p: str) -> None:
                self.path = p

        # "Mcu/Cfg/X" 在 "Mcu/Cfg" 容器内
        assert _count_existing_in_parent((V("Mcu/Cfg/X"),), "Mcu/Cfg") == 1
        # v_path 正好等于 parent_path
        assert _count_existing_in_parent((V("Mcu/Cfg"),), "Mcu/Cfg") == 1
        # 完全不同 → 0
        assert _count_existing_in_parent((V("Other/Path"),), "Mcu/Cfg") == 0
        # "Mcu/CfgOther" 不应算（不 startswith 也不等于）
        assert _count_existing_in_parent((V("Mcu/CfgOther"),), "Mcu/Cfg") == 0


# ---------------------------------------------------------------------------
# 行 355：未知 BSWMD 类型 → fallback 调试 log
# ---------------------------------------------------------------------------


class TestBSWWritePathCoverageUnknownType:
    """BSWMD param_type 未知值 → 不抛，走 debug log fallback。"""

    def test_unknown_type_falls_back(self, caplog: pytest.LogCaptureFixture) -> None:
        """param_type="UNKNOWN" → 走 fallback 不抛，logger.debug 触发。"""
        # 构造带未知类型的 ParamDef
        module = ModuleDef(
            short_name="Mcu",
            full_path="/AUTOSAR/Mcu",
            params={
                "Freq": ParamDef(
                    short_name="Freq",
                    full_path="/AUTOSAR/Mcu/Freq",
                    param_type="UNKNOWN_TYPE",  # type: ignore[arg-type]
                )
            },
        )
        reg = BSWMDRegistry(modules={"Mcu": module}, root_package_name="AUTOSAR")
        p = BSWParam(path="Mcu/Freq", value=ParamValue(raw="anything", type=ParamType.INTEGER))
        # 不抛即过（行 354-359：unknown type fallback）
        with caplog.at_level("DEBUG", logger="autoc.core.bsw.bsw_write_path"):
            validate_writes_against_bswmd(reg, "Mcu", (), (p,))
        # 验证 debug log 至少出现一次
        assert any("unknown BSWMD type" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# 行 368-372 / 384-385：INTEGER min/max 边界 + 转换失败
# ---------------------------------------------------------------------------


class TestBSWWritePathCoverageIntRange:
    """``_check_int_range`` 的 4 个分支：min=None / min ok / min 转换失败 / max 同理。"""

    def test_int_with_no_min_no_max_passes(self) -> None:
        """min=None + max=None → 跳过 range 校验（行 368 / 381 全 None）。"""
        reg = _build_registry_with_param(short_name="Freq")  # min=None, max=None
        p = BSWParam(path="Mcu/Freq", value=ParamValue(raw="999999", type=ParamType.INTEGER))
        # 即便极端大也通过
        validate_writes_against_bswmd(reg, "Mcu", (), (p,))

    def test_int_with_unconvertible_min_falls_back(self) -> None:
        """min="abc"（int() 失败）→ min_val=None，range 跳过（行 371-372）。"""
        # min 不是合法 int 字面量 → int() 抛 → min_val = None
        reg = _build_registry_with_param(short_name="Freq", min_val="abc")
        p = BSWParam(path="Mcu/Freq", value=ParamValue(raw="-9999", type=ParamType.INTEGER))
        # 即便 -9999 也通过（min 解析失败 → 不约束）
        validate_writes_against_bswmd(reg, "Mcu", (), (p,))

    def test_int_with_unconvertible_max_falls_back(self) -> None:
        """max="abc" → max_val=None，range 跳过（行 384-385）。"""
        reg = _build_registry_with_param(short_name="Freq", max_val="abc")
        p = BSWParam(path="Mcu/Freq", value=ParamValue(raw="9999", type=ParamType.INTEGER))
        validate_writes_against_bswmd(reg, "Mcu", (), (p,))

    def test_int_below_min_with_valid_min(self) -> None:
        """min=10 写 5 → 抛 expected_min=10。"""
        reg = _build_registry_with_param(short_name="Freq", min_val="10")
        p = BSWParam(path="Mcu/Freq", value=ParamValue(raw="5", type=ParamType.INTEGER))
        with pytest.raises(BSWWritePathError) as exc_info:
            validate_writes_against_bswmd(reg, "Mcu", (), (p,))
        assert exc_info.value.expected_min == 10
        assert "MIN=10" in str(exc_info.value)

    def test_int_above_max_with_valid_max(self) -> None:
        """max=100 写 200 → 抛 expected_max=100。"""
        reg = _build_registry_with_param(short_name="Freq", max_val="100")
        p = BSWParam(path="Mcu/Freq", value=ParamValue(raw="200", type=ParamType.INTEGER))
        with pytest.raises(BSWWritePathError) as exc_info:
            validate_writes_against_bswmd(reg, "Mcu", (), (p,))
        assert exc_info.value.expected_max == 100
        assert "MAX=100" in str(exc_info.value)

    def test_int_at_min_boundary_passes(self) -> None:
        """min=10 写 10 → 通过（边界值）。"""
        reg = _build_registry_with_param(short_name="Freq", min_val="10", max_val="100")
        p = BSWParam(path="Mcu/Freq", value=ParamValue(raw="10", type=ParamType.INTEGER))
        validate_writes_against_bswmd(reg, "Mcu", (), (p,))

    def test_int_at_max_boundary_passes(self) -> None:
        """max=100 写 100 → 通过（边界值）。"""
        reg = _build_registry_with_param(short_name="Freq", min_val="10", max_val="100")
        p = BSWParam(path="Mcu/Freq", value=ParamValue(raw="100", type=ParamType.INTEGER))
        validate_writes_against_bswmd(reg, "Mcu", (), (p,))


# ---------------------------------------------------------------------------
# 行 402-406 / 418-419：FLOAT min/max 边界 + 转换失败
# ---------------------------------------------------------------------------


class TestBSWWritePathCoverageFloatRange:
    """``_check_float_range`` 的 4 个分支。"""

    def test_float_with_no_min_no_max_passes(self) -> None:
        """min=None + max=None → 跳过（行 402 / 415 全 None）。"""
        reg = _build_registry_with_param(short_name="Tol", param_type="FLOAT")
        p = BSWParam(path="Mcu/Tol", value=ParamValue(raw="1e10", type=ParamType.FLOAT))
        validate_writes_against_bswmd(reg, "Mcu", (), (p,))

    def test_float_with_unconvertible_min_falls_back(self) -> None:
        """min="abc" → float() 失败 → min_val=None，range 跳过（行 405-406）。"""
        reg = _build_registry_with_param(short_name="Tol", param_type="FLOAT", min_val="abc")
        p = BSWParam(path="Mcu/Tol", value=ParamValue(raw="-9999.0", type=ParamType.FLOAT))
        validate_writes_against_bswmd(reg, "Mcu", (), (p,))

    def test_float_with_unconvertible_max_falls_back(self) -> None:
        """max="abc" → max_val=None，range 跳过（行 418-419）。"""
        reg = _build_registry_with_param(short_name="Tol", param_type="FLOAT", max_val="abc")
        p = BSWParam(path="Mcu/Tol", value=ParamValue(raw="9999.0", type=ParamType.FLOAT))
        validate_writes_against_bswmd(reg, "Mcu", (), (p,))

    def test_float_below_min_expected_min_is_int(self) -> None:
        """FLOAT 写 min-0.1 → 抛；expected_min 在 min 是整数时被转为 int（行 412）。"""
        reg = _build_registry_with_param(
            short_name="Tol", param_type="FLOAT", min_val="5.0", max_val="10.0"
        )
        p = BSWParam(path="Mcu/Tol", value=ParamValue(raw="4.5", type=ParamType.FLOAT))
        with pytest.raises(BSWWritePathError) as exc_info:
            validate_writes_against_bswmd(reg, "Mcu", (), (p,))
        # min=5.0 → min_val.is_integer()=True → expected_min=5（int）
        assert exc_info.value.expected_min == 5

    def test_float_above_max_expected_max_is_int(self) -> None:
        """FLOAT 写 max+0.1 → 抛；expected_max 在 max 是整数时被转为 int（行 425）。"""
        reg = _build_registry_with_param(
            short_name="Tol", param_type="FLOAT", min_val="0.0", max_val="10.0"
        )
        p = BSWParam(path="Mcu/Tol", value=ParamValue(raw="10.5", type=ParamType.FLOAT))
        with pytest.raises(BSWWritePathError) as exc_info:
            validate_writes_against_bswmd(reg, "Mcu", (), (p,))
        assert exc_info.value.expected_max == 10

    def test_float_min_non_integer_expected_min_none(self) -> None:
        """min=1.5 → min_val.is_integer()=False → expected_min=None（行 412 分支）。"""
        reg = _build_registry_with_param(
            short_name="Tol", param_type="FLOAT", min_val="1.5", max_val="10.0"
        )
        p = BSWParam(path="Mcu/Tol", value=ParamValue(raw="1.0", type=ParamType.FLOAT))
        with pytest.raises(BSWWritePathError) as exc_info:
            validate_writes_against_bswmd(reg, "Mcu", (), (p,))
        assert exc_info.value.expected_min is None

    def test_float_max_non_integer_expected_max_none(self) -> None:
        """max=10.5 → max_val.is_integer()=False → expected_max=None。"""
        reg = _build_registry_with_param(
            short_name="Tol", param_type="FLOAT", min_val="0.0", max_val="10.5"
        )
        p = BSWParam(path="Mcu/Tol", value=ParamValue(raw="11.0", type=ParamType.FLOAT))
        with pytest.raises(BSWWritePathError) as exc_info:
            validate_writes_against_bswmd(reg, "Mcu", (), (p,))
        assert exc_info.value.expected_max is None


# ---------------------------------------------------------------------------
# BSWMD 校验 vs 启发式（DEST 后缀）：BSWMD 优先
# ---------------------------------------------------------------------------


class TestBSWWritePathCoverageBSWMDPriority:
    """BSWMD 命中时优先于启发式路径转换。"""

    def test_explicit_def_ref_bypasses_ecuc_path_conversion(self) -> None:
        """def_ref 给出时，ECUC path 即便带 ``_0`` 也不被启发式转换。"""
        # BSWMD 注册在 /AUTOSAR/Mcu/Alias/Freq
        reg = _build_registry_with_param(
            short_name="Freq",
            container_short_name="Alias",
            min_val="0",
            max_val="100",
        )
        # path 有 _0 后缀（启发式会剥），但显式 def_ref 直指 Alias
        p = BSWParam(
            path="Mcu/Alias_0/Freq",  # ECUC path 带 instance index
            value=ParamValue(raw="50", type=ParamType.INTEGER),
            def_ref="/AUTOSAR/Mcu/Alias/Freq",
        )
        # 走 def_ref 路径（行 152-153）→ 找到 BSWMD → range 通过
        validate_writes_against_bswmd(reg, "Mcu", (), (p,))

    def test_ecuc_path_fallback_strips_instance_index(self) -> None:
        """无 def_ref 时，ECUC 路径上的 ``_0`` 后缀被剥（plan R7）。"""
        # BSWMD 注册在 /AUTOSAR/Mcu/Alias/Freq（无 _0）
        reg = _build_registry_with_param(
            short_name="Freq",
            container_short_name="Alias",
            min_val="0",
            max_val="100",
        )
        # ECUC path 带 _0 → 启发式剥后变成 /AUTOSAR/Mcu/Alias/Freq → 命中
        p = BSWParam(
            path="Mcu/Alias_0/Freq",
            value=ParamValue(raw="50", type=ParamType.INTEGER),
        )
        validate_writes_against_bswmd(reg, "Mcu", (), (p,))

    def test_ecuc_path_fallback_misses_with_stripped(self) -> None:
        """ECUC 路径启发式后仍不命中 → fallback 不抛。"""
        reg = _build_registry_with_param(
            short_name="Freq",
            container_short_name="Alias",
            min_val="0",
            max_val="100",
        )
        # 路径既不匹配（剥后也不命中）
        p = BSWParam(
            path="Mcu/Unknown_0/Other",
            value=ParamValue(raw="999999", type=ParamType.INTEGER),
        )
        # 不抛即过（fallback）
        validate_writes_against_bswmd(reg, "Mcu", (), (p,))


# ---------------------------------------------------------------------------
# BSWMD 没记录的 path → fallback 不抛（plan "BSWMD 没记录的 path → 走 fallback"）
# ---------------------------------------------------------------------------


class TestBSWWritePathCoverageFallback:
    """path 在 BSWMD 找不到 → 跳过单 param 校验（不抛）。"""

    def test_param_path_not_in_registry_falls_back(self) -> None:
        """完全未知的 param 路径 → fallback。"""
        reg = _build_registry_with_param(short_name="Freq", min_val="0", max_val="100")
        # path 既不在顶层 params 也不在 container 内
        p = BSWParam(
            path="Mcu/NonExistent/X",
            value=ParamValue(raw="9999", type=ParamType.INTEGER),
        )
        # 即便 raw=9999 也不抛
        validate_writes_against_bswmd(reg, "Mcu", (), (p,))

    def test_param_path_in_different_module_falls_back(self) -> None:
        """不同 module 的 path → BSWMD 找不到 → fallback。"""
        reg = _build_registry_with_param(short_name="Freq")
        # path 是 Other/Freq（不在 Mcu module）
        p = BSWParam(
            path="Other/Freq",
            value=ParamValue(raw="9999", type=ParamType.INTEGER),
        )
        validate_writes_against_bswmd(reg, "Mcu", (), (p,))


# ---------------------------------------------------------------------------
# 容器 multiplicity 各种边界（覆盖行 222-244）
# ---------------------------------------------------------------------------


class TestBSWWritePathCoverageContainerMultiplicity:
    """容器上下限各种 edge case。"""

    def test_container_exact_upper_limit_passes(self) -> None:
        """upper=3 + existing + writes 总数 = 3 → 通过（边界）。"""
        reg = _build_registry_with_param(
            short_name="Freq",
            container_short_name="Cfg",
            container_lower=0,
            container_upper=3,
            min_val="0",
            max_val="100",
        )
        # 2 existing + 1 write = 3（== upper）→ 通过
        existing = (
            _bsw_param("Mcu/Cfg/A", "1", ParamType.INTEGER),
            _bsw_param("Mcu/Cfg/B", "2", ParamType.INTEGER),
        )
        p = _bsw_param("Mcu/Cfg/Freq", "50", ParamType.INTEGER)
        validate_writes_against_bswmd(reg, "Mcu", existing, (p,))

    def test_container_exact_lower_limit_passes(self) -> None:
        """lower=2 + 2 existing + 0 write = 2 → 通过（边界）。"""
        reg = _build_registry_with_param(
            short_name="Freq",
            container_short_name="Cfg",
            container_lower=2,
            container_upper=5,
            min_val="0",
            max_val="100",
        )
        existing = (
            _bsw_param("Mcu/Cfg/A", "1", ParamType.INTEGER),
            _bsw_param("Mcu/Cfg/B", "2", ParamType.INTEGER),
        )
        # 不写新 param，total=2 → ok
        validate_writes_against_bswmd(reg, "Mcu", existing, ())

    def test_container_actual_value_is_string_total(self) -> None:
        """容器超 upper 时 actual_value 是 "str(total)" 字符串。"""
        reg = _build_registry_with_param(
            short_name="Freq",
            container_short_name="Cfg",
            container_lower=0,
            container_upper=2,
            min_val="0",
            max_val="100",
        )
        existing = (
            _bsw_param("Mcu/Cfg/A", "1", ParamType.INTEGER),
            _bsw_param("Mcu/Cfg/B", "2", ParamType.INTEGER),
        )
        p = _bsw_param("Mcu/Cfg/Freq", "50", ParamType.INTEGER)
        # 2 existing + 1 write = 3 > 2 → 抛
        with pytest.raises(BSWWritePathError) as exc_info:
            validate_writes_against_bswmd(reg, "Mcu", existing, (p,))
        assert exc_info.value.actual_value == "3"

    def test_container_below_lower_actual_value_is_string(self) -> None:
        """容器低于 lower 时 actual_value 同样是 "str(total)"。"""
        reg = _build_registry_with_param(
            short_name="Freq",
            container_short_name="Cfg",
            container_lower=3,
            container_upper=5,
            min_val="0",
            max_val="100",
        )
        p = _bsw_param("Mcu/Cfg/Freq", "50", ParamType.INTEGER)
        # 0 existing + 1 write = 1 < 3 → 抛
        with pytest.raises(BSWWritePathError) as exc_info:
            validate_writes_against_bswmd(reg, "Mcu", (), (p,))
        assert exc_info.value.actual_value == "1"
        assert exc_info.value.expected_min == 3
        assert exc_info.value.expected_max == 5


# ---------------------------------------------------------------------------
# 集成：BSWMD 优先 + DEST 后缀启发式（plan R7）
# ---------------------------------------------------------------------------


class TestBSWWritePathCoverageIntegration:
    """组合：BSWMD 命中 + def_ref 优先 + fallback 不抛。"""

    def test_def_ref_takes_priority_over_ecuc_conversion(self) -> None:
        """显式 def_ref 总是优先（行 152-153）。"""
        # BSWMD 在 /AUTOSAR/Mcu/Alias/Freq
        reg = _build_registry_with_param(
            short_name="Freq",
            container_short_name="Alias",
            min_val="0",
            max_val="100",
        )
        # path 形如 "Mcu/Wrong/Freq"（无 _0 后缀，启发式不剥），
        # 但 def_ref 指 Alias
        p = BSWParam(
            path="Mcu/Wrong/Freq",
            value=ParamValue(raw="50", type=ParamType.INTEGER),
            def_ref="/AUTOSAR/Mcu/Alias/Freq",
        )
        validate_writes_against_bswmd(reg, "Mcu", (), (p,))

    def test_mixed_known_and_unknown_params(self) -> None:
        """writes 混合"已知 + 未知" param：未知 fallback，已知校验。"""
        reg = _build_registry_with_param(short_name="Freq", min_val="0", max_val="100")
        # 已知 param（path 命中）
        ok_p = BSWParam(path="Mcu/Freq", value=ParamValue(raw="50", type=ParamType.INTEGER))
        # 未知 param（fallback）
        unknown_p = BSWParam(
            path="Mcu/Unknown/Other",
            value=ParamValue(raw="9999", type=ParamType.INTEGER),
        )
        # 不抛（unknown 走 fallback）
        validate_writes_against_bswmd(reg, "Mcu", (), (ok_p, unknown_p))

    def test_registry_none_with_various_writes(self) -> None:
        """不传 registry → 完全跳过（向后兼容老 test）。"""
        # 即便有非法 INTEGER / 越界也不抛
        bad1 = BSWParam(path="Mcu/Freq", value=ParamValue(raw="abc", type=ParamType.INTEGER))
        bad2 = BSWParam(path="Mcu/Other", value=ParamValue(raw="9999", type=ParamType.INTEGER))
        validate_writes_against_bswmd(None, "Mcu", (), (bad1, bad2))

    def test_upper_unbounded_with_large_count_passes(self) -> None:
        """upper=-1 (unbounded) + 1000 existing + 1 write → 全部通过。"""
        reg = _build_registry_with_param(
            short_name="Freq",
            container_short_name="Cfg",
            container_lower=0,
            container_upper=-1,
            min_val="0",
            max_val="100",
        )
        existing = tuple(
            _bsw_param(f"Mcu/Cfg/X{i}", str(i), ParamType.INTEGER) for i in range(1000)
        )
        p = _bsw_param("Mcu/Cfg/Freq", "50", ParamType.INTEGER)
        validate_writes_against_bswmd(reg, "Mcu", existing, (p,))
