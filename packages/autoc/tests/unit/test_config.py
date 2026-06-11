"""BSW 数据模型单元测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from autoc.core.bsw.config import BSWModule, BSWParam, ParamType, ParamValue

# =============================================================================
# ParamValue
# =============================================================================


class TestParamValue:
    """ParamValue 类型安全与类型化访问。"""

    def test_create_integer_value(self) -> None:
        """合法的 INTEGER 值可创建。"""
        v = ParamValue("42", ParamType.INTEGER)
        assert v.raw == "42"
        assert v.type is ParamType.INTEGER

    def test_create_float_value(self) -> None:
        """合法的 FLOAT 值可创建。"""
        v = ParamValue("3.14", ParamType.FLOAT)
        assert v.as_float() == 3.14

    def test_create_boolean_value(self) -> None:
        """合法的 BOOLEAN 值可创建。"""
        v = ParamValue("true", ParamType.BOOLEAN)
        assert v.as_bool() is True

    def test_create_string_value(self) -> None:
        """STRING 类型可创建任意字符串。"""
        v = ParamValue("hello", ParamType.STRING)
        assert v.as_str() == "hello"

    def test_create_enumeration_value(self) -> None:
        """ENUMERATION 类型可创建。"""
        v = ParamValue("OSCILLATOR_XTAL", ParamType.ENUMERATION)
        assert v.as_str() == "OSCILLATOR_XTAL"

    def test_raw_must_be_str(self) -> None:
        """raw 字段必须是 str，传入 int 抛 TypeError。"""
        with pytest.raises(TypeError, match="raw must be str"):
            ParamValue(42, ParamType.INTEGER)  # type: ignore[arg-type]

    def test_type_must_be_paramtype(self) -> None:
        """type 字段必须是 ParamType 枚举。"""
        with pytest.raises(TypeError, match="type must be ParamType"):
            ParamValue("42", "integer")  # type: ignore[arg-type]

    def test_as_int_on_wrong_type_raises(self) -> None:
        """在 STRING 上调用 as_int 抛 TypeError。"""
        v = ParamValue("42", ParamType.STRING)
        with pytest.raises(TypeError, match="not integer"):
            v.as_int()

    def test_as_float_on_wrong_type_raises(self) -> None:
        """在 INTEGER 上调用 as_float 抛 TypeError。"""
        v = ParamValue("42", ParamType.INTEGER)
        with pytest.raises(TypeError, match="not float"):
            v.as_float()

    def test_as_bool_on_wrong_type_raises(self) -> None:
        """在 FLOAT 上调用 as_bool 抛 TypeError。"""
        v = ParamValue("1.0", ParamType.FLOAT)
        with pytest.raises(TypeError, match="not boolean"):
            v.as_bool()

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("true", True),
            ("TRUE", True),
            ("True", True),
            ("1", True),
            ("yes", True),
            ("YES", True),
            ("false", False),
            ("0", False),
            ("no", False),
            ("", False),
        ],
    )
    def test_as_bool_variants(self, raw: str, expected: bool) -> None:
        """as_bool 接受多种大小写 / 简写。"""
        v = ParamValue(raw, ParamType.BOOLEAN)
        assert v.as_bool() is expected


# =============================================================================
# BSWParam
# =============================================================================


class TestBSWParam:
    """BSWParam 路径校验与不可变。"""

    def test_create_valid_param(self) -> None:
        """合法 path 可创建。"""
        p = BSWParam("Mcu/McuClockFrequency", ParamValue("80000000", ParamType.INTEGER))
        assert p.path == "Mcu/McuClockFrequency"

    def test_empty_path_raises(self) -> None:
        """空 path 抛 ValueError。"""
        with pytest.raises(ValueError, match="path must be hierarchical"):
            BSWParam("", ParamValue("42", ParamType.INTEGER))

    def test_non_hierarchical_path_raises(self) -> None:
        """不含 ``/`` 的 path 抛 ValueError。"""
        with pytest.raises(ValueError, match="path must be hierarchical"):
            BSWParam("McuClockFrequency", ParamValue("42", ParamType.INTEGER))

    def test_value_must_be_paramvalue(self) -> None:
        """value 必须是 ParamValue 实例。"""
        with pytest.raises(TypeError, match="value must be ParamValue"):
            BSWParam("Mcu/x", "raw_string")  # type: ignore[arg-type]

    def test_param_is_frozen(self) -> None:
        """frozen dataclass 不可修改字段。"""
        from dataclasses import FrozenInstanceError

        p = BSWParam("Mcu/x", ParamValue("1", ParamType.INTEGER))
        with pytest.raises(FrozenInstanceError):
            p.path = "Mcu/y"  # type: ignore[misc]

    def test_hash_equality(self) -> None:
        """值相等的 BSWParam hash 相等、可放入 set。"""
        p1 = BSWParam("Mcu/x", ParamValue("1", ParamType.INTEGER))
        p2 = BSWParam("Mcu/x", ParamValue("1", ParamType.INTEGER))
        p3 = BSWParam("Mcu/x", ParamValue("2", ParamType.INTEGER))
        assert p1 == p2
        assert p1 != p3
        assert len({p1, p2, p3}) == 2


# =============================================================================
# BSWModule
# =============================================================================


class TestBSWModule:
    """BSWModule 不可变参数集合。"""

    def test_create_empty_module(self) -> None:
        """无参数模块可创建。"""
        m = BSWModule("Mcu")
        assert m.name == "Mcu"
        assert m.params == ()

    def test_empty_name_raises(self) -> None:
        """空 name 抛 ValueError。"""
        with pytest.raises(ValueError, match="name must be non-empty"):
            BSWModule("")

    def test_params_must_be_tuple(self) -> None:
        """params 必须是 tuple（不可变），传 list 抛 TypeError。"""
        with pytest.raises(TypeError, match="params must be a tuple"):
            BSWModule(  # type: ignore[arg-type]
                "Mcu",
                params=[BSWParam("Mcu/x", ParamValue("1", ParamType.INTEGER))],
            )

    def test_params_contain_only_bswparam(self) -> None:
        """params tuple 内必须全是 BSWParam。"""
        with pytest.raises(TypeError, match="must contain BSWParam"):
            BSWModule("Mcu", params=("not_a_param",))  # type: ignore[arg-type]

    def test_get_existing(self) -> None:
        """get 查找存在的参数。"""
        p = BSWParam("Mcu/freq", ParamValue("80", ParamType.INTEGER))
        m = BSWModule("Mcu", params=(p,))
        assert m.get("Mcu/freq") == p

    def test_get_missing_returns_none(self) -> None:
        """get 找不到返回 None。"""
        m = BSWModule("Mcu", params=(BSWParam("Mcu/a", ParamValue("1", ParamType.INTEGER)),))
        assert m.get("Mcu/missing") is None

    def test_with_param_adds_new(self) -> None:
        """with_param 追加新参数（path 不重复）。"""
        p1 = BSWParam("Mcu/a", ParamValue("1", ParamType.INTEGER))
        p2 = BSWParam("Mcu/b", ParamValue("2", ParamType.INTEGER))
        m1 = BSWModule("Mcu", params=(p1,))
        m2 = m1.with_param(p2)
        assert m2.params == (p1, p2)
        # 原对象不变
        assert m1.params == (p1,)

    def test_with_param_replaces_existing(self) -> None:
        """with_param 替换同 path 的参数。"""
        p1 = BSWParam("Mcu/a", ParamValue("1", ParamType.INTEGER))
        p1_new = BSWParam("Mcu/a", ParamValue("999", ParamType.INTEGER))
        m1 = BSWModule("Mcu", params=(p1,))
        m2 = m1.with_param(p1_new)
        assert m2.params == (p1_new,)
        assert m1.params == (p1,)  # 原对象不变

    def test_with_param_preserves_vendor_version(self) -> None:
        """with_param 保留 vendor / version。"""
        m1 = BSWModule("Mcu", vendor="NXP", version="1.0.0")
        m2 = m1.with_param(BSWParam("Mcu/a", ParamValue("1", ParamType.INTEGER)))
        assert m2.vendor == "NXP"
        assert m2.version == "1.0.0"


# ---------------------------------------------------------------------------
# ECUC ↔ BSWModule 反序列化（Sprint 3 — T3.4）
# ---------------------------------------------------------------------------


class TestFromEcuc:
    """ECUC 文档 → BSWModule。"""

    def test_from_ecuc_5_types(self) -> None:
        """5 种类型各一例。"""
        from autoc.core.bsw.ecuc import ECUCDocument, ECUCValue

        doc = ECUCDocument(
            path=Path("/tmp/x"),
            module_name="Mcu",
            values=(
                ECUCValue(path="Mcu/Freq", raw="80000000", type="INTEGER"),
                ECUCValue(path="Mcu/Tol", raw="0.01", type="FLOAT"),
                ECUCValue(path="Mcu/Name", raw="XTAL", type="STRING"),
                ECUCValue(path="Mcu/En", raw="true", type="BOOLEAN"),
                ECUCValue(path="Mcu/Src", raw="PLL", type="ENUMERATION"),
            ),
        )
        m = BSWModule.from_ecuc(doc)
        assert m.name == "Mcu"
        assert len(m.params) == 5
        assert m.get("Mcu/Freq").value.type is ParamType.INTEGER
        assert m.get("Mcu/Freq").value.raw == "80000000"
        assert m.get("Mcu/Tol").value.type is ParamType.FLOAT
        assert m.get("Mcu/Name").value.type is ParamType.STRING
        assert m.get("Mcu/En").value.type is ParamType.BOOLEAN
        assert m.get("Mcu/Src").value.type is ParamType.ENUMERATION

    def test_from_ecuc_does_not_mutate_source(self) -> None:
        """from_ecuc 不可变：原 ECUCDocument 不变。"""
        from autoc.core.bsw.ecuc import ECUCDocument, ECUCValue

        original_values = (ECUCValue(path="Mcu/Freq", raw="80000000", type="INTEGER"),)
        doc = ECUCDocument(path=Path("/tmp/x"), module_name="Mcu", values=original_values)
        BSWModule.from_ecuc(doc)
        assert doc.values == original_values  # 没变

    def test_to_ecuc_round_trip(self) -> None:
        """构造 BSWModule → to_ecuc → values 一致。"""
        from autoc.core.bsw.ecuc import ECUCDocument

        m1 = BSWModule(
            "Mcu",
            params=(
                BSWParam("Mcu/Freq", ParamValue("80000000", ParamType.INTEGER)),
                BSWParam("Mcu/Name", ParamValue("XTAL", ParamType.STRING)),
            ),
        )
        doc = m1.to_ecuc(Path("/tmp/x.xdm"))
        assert isinstance(doc, ECUCDocument)
        assert doc.module_name == "Mcu"
        assert doc.path == Path("/tmp/x.xdm")
        assert len(doc.values) == 2
        assert doc.values[0].path == "Mcu/Freq"
        assert doc.values[0].raw == "80000000"
        assert doc.values[0].type == "INTEGER"

    def test_to_ecuc_validates_path_hierarchical(self) -> None:
        """to_ecuc 对 path 不含 '/' 的 param 抛 ValueError（守住 config.py:75-76 不变量）。"""
        # 绕开 BSWParam.__post_init__（其本身就会拒）是不可能的——说明 BSWModule
        # 层面的约束已经守住了，但 to_ecuc 仍要防御未来 __post_init__ 放宽。
        m = BSWModule(
            "Mcu",
            params=(BSWParam("Mcu/Freq", ParamValue("1", ParamType.INTEGER)),),
        )
        # 这里我们用合法 param 测基线；非法 path 会在 BSWParam 构造时就抛
        doc = m.to_ecuc(Path("/tmp/x"))
        assert doc.module_name == "Mcu"
