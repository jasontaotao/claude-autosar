"""``BSWWritePathError`` + ``validate_writes_against_bswmd`` —— 写参前的多重度/类型/range 校验。

Sprint 8.E — T8.E.3。契约 5 锁定：

* ``BSWWritePathError`` frozen dataclass + ``Exception`` 派生
* ``validate_writes_against_bswmd(registry, module, current_values, writes)`` 入口
  - ``registry`` 为 ``None`` → 跳过校验（向后兼容，9 个老 test 不破）
  - 失败抛 ``BSWWritePathError``；不抛通用 ``Exception``
* 校验维度（按 plan T8.E.3 RED 测试段）：
  1. **容器 multiplicity**（``LOWER-MULTIPLICITY`` / ``UPPER-MULTIPLICITY``），
     缺省 ``(0, 1)``；``unbounded`` → ``-1``。
  2. **参数类型**（``INTEGER`` / ``FLOAT`` / ``STRING`` / ``BOOLEAN`` / ``ENUMERATION`` /
     ``FUNCTION_NAME``）。
  3. **INTEGER / FLOAT range**（``<MIN>`` / ``<MAX>`` 字面量比较）。
  4. **ENUMERATION 合法值**（``symbol_strings`` 成员检查）。

设计选择：
* 本模块**不**消费 ``ECUCValue`` 类型（用 ``ParamValue`` 即可），保持依赖最小
  （仅消费 ``BSWParam`` + ``BSWMDRegistry`` + ``ParamDef``）。
* BSWMD 没记录的 path → 走 fallback（不抛），与 plan "BSWMD 没记录的 path → 走
  fallback（不抛）" 一致。
* ``param_index`` 在 BSWMD 命中时定位为"writes 里的索引"；fallback 路径时
  留 ``None``。
"""

from __future__ import annotations

from dataclasses import dataclass
import logging

from autoc.core.bsw.bswmd import BSWMDRegistry, ParamDef
from autoc.core.bsw.config import BSWParam

__all__ = [
    "BSWWritePathError",
    "validate_writes_against_bswmd",
]


_logger = logging.getLogger(__name__)


# =============================================================================
# 错误类型（契约 5 锁定签名）
# =============================================================================


@dataclass(frozen=True)
class BSWWritePathError(Exception):
    """BSW 写参校验失败的统一异常（契约 5 锁定）。

    Attributes:
        param_path: 失败的 param path（ECUC 路径形式 ``Module/.../ShortName``）。
        param_index: 在传入 ``writes`` tuple 里的索引（``None`` = 容器级 / fallback）。
        reason: 错误原因（短字符串，机器可读）。
        expected_min: multiplicity 下限（容器级错误时填）。
        expected_max: multiplicity 上限（容器级错误时填；``-1`` = unbounded）。
        actual_value: 实际值（type/range 错误时填）。
    """

    param_path: str
    param_index: int | None
    reason: str
    expected_min: int | None = None
    expected_max: int | None = None
    actual_value: str | None = None

    def __post_init__(self) -> None:
        # 契约 5 锁定：super().__init__(self._format_message()) 在 __post_init__
        # 调。Exception 是非 frozen，但 frozen=True 仍可调 super().__init__。
        Exception.__init__(self, self._format_message())

    def _format_message(self) -> str:
        """输出格式: ``<param_path>: <reason> [expected_min=X, expected_max=Y, actual=Z]``。"""
        # 当字段为 None 时省略；保持单行可被 grep。
        extras: list[str] = []
        if self.expected_min is not None:
            extras.append(f"expected_min={self.expected_min}")
        if self.expected_max is not None:
            extras.append(f"expected_max={self.expected_max}")
        if self.actual_value is not None:
            extras.append(f"actual={self.actual_value!r}")
        if extras:
            return f"{self.param_path}: {self.reason} [{', '.join(extras)}]"
        return f"{self.param_path}: {self.reason}"


# =============================================================================
# Public API
# =============================================================================


def validate_writes_against_bswmd(
    registry: BSWMDRegistry | None,
    module: str,
    current_values: tuple[object, ...],
    writes: tuple[BSWParam, ...],
) -> None:
    """按 BSWMD 校验 writes 集合；失败抛 ``BSWWritePathError``。

    Args:
        registry: BSWMD 模板表。``None`` → 跳过校验（向后兼容，9 个老 test 不破）。
        module: 模块名（仅用于 logging / 诊断）。
        current_values: 当前 ECUC 文档里的值（``ECUCValue`` 序列；本函数不直接读
                        字段，但为未来与 ``load_module`` 输出对齐保留签名）。
                        当前实现不消费；保留是为契约 5 锁定签名。
        writes: 待写入的 BSWParam 序列。

    Raises:
        BSWWritePathError: 任一校验维度（multiplicity / type / range / enum）失败。
    """
    if registry is None:
        # 契约 5：registry=None → 跳过校验（向后兼容）
        return

    if not writes:
        return

    # 当前 ``module`` 参数仅用于 logging / 诊断预留；保留以匹配契约 5 签名。
    _ = module  # noqa: F841

    # ------------------------------------------------------------------
    # 1) 容器 multiplicity 校验（按 ECUC 路径的"父容器"分组）
    # ------------------------------------------------------------------
    _check_container_multiplicity(registry, current_values, writes)

    # ------------------------------------------------------------------
    # 2) 单 param 校验：type + range + enumeration
    # ------------------------------------------------------------------
    for idx, param in enumerate(writes):
        param_def = _lookup_param_def(registry, param)
        if param_def is None:
            # BSWMD 没记录 → fallback（不抛）
            continue
        _check_param_value(param, param_def, idx)


# =============================================================================
# 内部：BSWMD 查表
# =============================================================================


def _lookup_param_def(registry: BSWMDRegistry, param: BSWParam) -> ParamDef | None:
    """按 ``BSWParam.def_ref`` 或 ECUC 路径反推 ``ParamDef``。

    优先级：
      1. ``param.def_ref`` 显式给出 → ``registry.lookup_param(def_ref)``。
      2. 否则按 plan R7 把 ECUC 路径 ``Mcu/McuClockSettingConfig_0/McuClockFrequency``
         转成 DEFINITION-REF 路径 ``/AUTOSAR/Mcu/McuClockSettingConfig/McuClockFrequency``
         查 registry。
    """
    if param.def_ref is not None:
        return registry.lookup_param(param.def_ref)
    # fallback：把 ECUC 路径转成 DEFINITION-REF
    def_ref = _ecuc_path_to_def_ref(param.path, registry.root_package_name)
    return registry.lookup_param(def_ref)


def _ecuc_path_to_def_ref(ecuc_path: str, root_pkg: str) -> str:
    """ECUC 路径 → DEFINITION-REF 路径。

    例: ``Mcu/McuClockSettingConfig_0/McuClockFrequency`` →
        ``/AUTOSAR/Mcu/McuClockSettingConfig/McuClockFrequency``。

    规则（plan R7）：去掉实例下标（``_0`` / ``_1`` ...），前导加 ``/`` + 根包名。
    """
    segments = [seg for seg in ecuc_path.split("/") if seg]
    cleaned = [_strip_instance_index(seg) for seg in segments]
    return "/" + root_pkg + "/" + "/".join(cleaned)


def _strip_instance_index(short_name: str) -> str:
    """去掉 EB tresos 自动加的实例下标（``McuClockSettingConfig_0`` → ``McuClockSettingConfig``）。

    启发式：最后一段以 ``_<digits>`` 结尾且前面非空 → 切掉。
    """
    if "_" not in short_name:
        return short_name
    head, _, tail = short_name.rpartition("_")
    if not head:
        return short_name
    if tail.isdigit():
        return head
    return short_name


# =============================================================================
# 内部：容器 multiplicity 校验
# =============================================================================


def _check_container_multiplicity(
    registry: BSWMDRegistry,
    current_values: tuple[object, ...],
    writes: tuple[BSWParam, ...],
) -> None:
    """按容器分组 + multiplicity 上下限校验 writes 数量。

    当前阶段（T8.E.3 + T8.E.0b 之后，lookup 仍是 stub）的覆盖范围：
      - param 路径的"父容器"= 去掉最后一段 short_name 的 ECUC 路径
      - 容器的 multiplicity 通过 ``lookup_container`` 取；未命中则走 fallback
        （不抛；与 "BSWMD 没记录的 path → fallback" 一致）
    """
    # 按父容器分组 writes（key = ECUC 父容器路径）
    by_container: dict[str, list[BSWParam]] = {}
    for param in writes:
        parent = _parent_container_path(param.path)
        by_container.setdefault(parent, []).append(param)

    for parent_path, child_writes in by_container.items():
        # parent 容器在 BSWMD 里查不到 → fallback
        def_ref = _ecuc_path_to_def_ref(parent_path, registry.root_package_name)
        container_def = registry.lookup_container(def_ref)
        if container_def is None:
            continue

        # 总实例数 = 已有（current_values）+ 本次 writes 落在此容器的
        existing_in_parent = _count_existing_in_parent(current_values, parent_path)
        total = existing_in_parent + len(child_writes)

        # upper=-1 = unbounded，永不超
        if container_def.upper_multiplicity != -1 and total > container_def.upper_multiplicity:
            raise BSWWritePathError(
                param_path=parent_path,
                param_index=None,
                reason=(
                    f"container exceeds UPPER-MULTIPLICITY=" f"{container_def.upper_multiplicity}"
                ),
                expected_min=container_def.lower_multiplicity,
                expected_max=container_def.upper_multiplicity,
                actual_value=str(total),
            )

        if total < container_def.lower_multiplicity:
            raise BSWWritePathError(
                param_path=parent_path,
                param_index=None,
                reason=(
                    f"container below LOWER-MULTIPLICITY=" f"{container_def.lower_multiplicity}"
                ),
                expected_min=container_def.lower_multiplicity,
                expected_max=container_def.upper_multiplicity,
                actual_value=str(total),
            )


def _parent_container_path(ecuc_path: str) -> str:
    """``Mcu/McuClockSettingConfig_0/McuClockFrequency`` → ``Mcu/McuClockSettingConfig_0``。

    顶层 param（只有一段）→ 返回 ``""``（表示 module 根）。
    """
    segments = [seg for seg in ecuc_path.split("/") if seg]
    if len(segments) <= 1:
        return ""
    return "/".join(segments[:-1])


def _count_existing_in_parent(
    current_values: tuple[object, ...],
    parent_path: str,
) -> int:
    """统计 current_values 里"父容器 == parent_path"的 leaf 数。

    ECUCValue 形态用 duck-typing：取 ``.path`` 属性。
    parent 为空时（顶层）→ 全部算。
    """
    count = 0
    for v in current_values:
        v_path = getattr(v, "path", None)
        if not isinstance(v_path, str):
            continue
        if parent_path == "":
            # 顶层 param：ECUC 路径只有一段
            segments = [seg for seg in v_path.split("/") if seg]
            if len(segments) == 1:
                count += 1
        elif v_path.startswith(parent_path + "/") or v_path == parent_path:
            # 在父容器内的 leaf
            count += 1
    return count


# =============================================================================
# 内部：单 param type / range / enum 校验
# =============================================================================


def _check_param_value(
    param: BSWParam,
    param_def: ParamDef,
    idx: int,
) -> None:
    """单 param 的类型 / range / enum 校验；失败抛 ``BSWWritePathError``。"""
    raw = param.value.raw
    bswmd_type = param_def.param_type

    # INTEGER
    if bswmd_type == "INTEGER":
        try:
            int_val = int(raw)
        except (TypeError, ValueError) as exc:
            raise BSWWritePathError(
                param_path=param.path,
                param_index=idx,
                reason="value is not type INTEGER",
                actual_value=raw,
            ) from exc
        _check_int_range(param, int_val, param_def, idx)
        return

    # FLOAT
    if bswmd_type == "FLOAT":
        try:
            float_val = float(raw)
        except (TypeError, ValueError) as exc:
            raise BSWWritePathError(
                param_path=param.path,
                param_index=idx,
                reason="value is not type FLOAT",
                actual_value=raw,
            ) from exc
        _check_float_range(param, float_val, param_def, idx)
        return

    # BOOLEAN
    if bswmd_type == "BOOLEAN":
        lowered = raw.strip().lower()
        if lowered not in ("true", "false", "0", "1", "yes", "no"):
            raise BSWWritePathError(
                param_path=param.path,
                param_index=idx,
                reason="value is not type BOOLEAN",
                actual_value=raw,
            )
        return

    # ENUMERATION
    if bswmd_type == "ENUMERATION":
        if param_def.symbol_strings and raw not in param_def.symbol_strings:
            raise BSWWritePathError(
                param_path=param.path,
                param_index=idx,
                reason=(
                    f"value not in ENUMERATION symbol_strings " f"{list(param_def.symbol_strings)}"
                ),
                actual_value=raw,
            )
        return

    # STRING / FUNCTION_NAME：BSWMD 不约束 range，原样通过
    if bswmd_type in ("STRING", "FUNCTION_NAME"):
        return

    # 未知类型 → 兼容 BSWMD 解析未到位时的 fallback：不抛
    _logger.debug(
        "validate_writes_against_bswmd: unknown BSWMD type %r for %s, skip",
        bswmd_type,
        param.path,
    )


def _check_int_range(
    param: BSWParam,
    int_val: int,
    param_def: ParamDef,
    idx: int,
) -> None:
    if param_def.min is not None:
        try:
            min_val = int(param_def.min)
        except (TypeError, ValueError):
            min_val = None
        if min_val is not None and int_val < min_val:
            raise BSWWritePathError(
                param_path=param.path,
                param_index=idx,
                reason=f"INTEGER value below MIN={min_val}",
                expected_min=min_val,
                actual_value=str(int_val),
            )
    if param_def.max is not None:
        try:
            max_val = int(param_def.max)
        except (TypeError, ValueError):
            max_val = None
        if max_val is not None and int_val > max_val:
            raise BSWWritePathError(
                param_path=param.path,
                param_index=idx,
                reason=f"INTEGER value above MAX={max_val}",
                expected_max=max_val,
                actual_value=str(int_val),
            )


def _check_float_range(
    param: BSWParam,
    float_val: float,
    param_def: ParamDef,
    idx: int,
) -> None:
    if param_def.min is not None:
        try:
            min_val = float(param_def.min)
        except (TypeError, ValueError):
            min_val = None
        if min_val is not None and float_val < min_val:
            raise BSWWritePathError(
                param_path=param.path,
                param_index=idx,
                reason=f"FLOAT value below MIN={min_val}",
                expected_min=int(min_val) if min_val.is_integer() else None,
                actual_value=str(float_val),
            )
    if param_def.max is not None:
        try:
            max_val = float(param_def.max)
        except (TypeError, ValueError):
            max_val = None
        if max_val is not None and float_val > max_val:
            raise BSWWritePathError(
                param_path=param.path,
                param_index=idx,
                reason=f"FLOAT value above MAX={max_val}",
                expected_max=int(max_val) if max_val.is_integer() else None,
                actual_value=str(float_val),
            )
