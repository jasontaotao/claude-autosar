"""AUTOSAR schemas 摘要测试。"""

from __future__ import annotations

import pytest

from claude_autosar.core.bsw.schemas import (
    ECU_ABSTRACTION_MODULES,
    MCAL_MODULES,
    ModuleSchema,
    get_module_schema,
    is_known_module,
    list_modules_by_category,
)


class TestModuleSchema:
    """ModuleSchema 数据校验。"""

    def test_create_valid_schema(self) -> None:
        """合法字段可创建。"""
        s = ModuleSchema(
            name="X",
            category="MCAL",
            typical_vendor="test",
            description="test",
        )
        assert s.name == "X"
        assert s.category == "MCAL"
        assert s.common_config_groups == ()

    def test_empty_name_raises(self) -> None:
        """空 name 抛 ValueError。"""
        with pytest.raises(ValueError, match="name must be non-empty"):
            ModuleSchema(name="", category="MCAL", typical_vendor="x", description="y")

    def test_invalid_category_raises(self) -> None:
        """非法 category 抛 ValueError。"""
        with pytest.raises(ValueError, match="category must be one of"):
            ModuleSchema(
                name="X",
                category="INVALID",  # type: ignore[arg-type]
                typical_vendor="x",
                description="y",
            )

    def test_schema_is_frozen(self) -> None:
        """frozen dataclass 不可修改。"""
        from dataclasses import FrozenInstanceError

        s = ModuleSchema(name="X", category="MCAL", typical_vendor="x", description="y")
        with pytest.raises(FrozenInstanceError):
            s.name = "Y"  # type: ignore[misc]


class TestMcalModules:
    """MCAL 模块字典完整性。"""

    @pytest.mark.parametrize("name", ["Mcu", "Port", "Dio", "Can", "Spi"])
    def test_core_mcal_modules_exist(self, name: str) -> None:
        """核心 MCAL 模块必须存在。"""
        assert name in MCAL_MODULES
        assert MCAL_MODULES[name].category == "MCAL"

    def test_all_mcal_have_non_empty_config_groups(self) -> None:
        """MCAL 模块应当至少有一组常见配置组。"""
        for name, schema in MCAL_MODULES.items():
            assert schema.common_config_groups, f"{name} has empty config groups"


class TestEcuAbstractionModules:
    """ECU 抽象层模块字典完整性。"""

    @pytest.mark.parametrize("name", ["CanIf", "PduR", "EcuC", "Com"])
    def test_core_ecu_abstraction_modules_exist(self, name: str) -> None:
        """核心 ECU 抽象层模块必须存在。"""
        assert name in ECU_ABSTRACTION_MODULES


class TestLookupHelpers:
    """模块查找辅助函数。"""

    def test_get_module_schema_mcal(self) -> None:
        """get_module_schema 找到 MCAL 模块。"""
        s = get_module_schema("Mcu")
        assert s is not None
        assert s.category == "MCAL"

    def test_get_module_schema_ecu_abstraction(self) -> None:
        """get_module_schema 找到 ECU 抽象层模块。"""
        s = get_module_schema("PduR")
        assert s is not None
        assert s.category == "ECU_ABSTRACTION"

    def test_get_module_schema_missing(self) -> None:
        """get_module_schema 找不到返回 None。"""
        assert get_module_schema("NonExistent") is None

    def test_is_known_module_true(self) -> None:
        """is_known_module 对已知模块返回 True。"""
        assert is_known_module("Mcu") is True
        assert is_known_module("PduR") is True

    def test_is_known_module_false(self) -> None:
        """is_known_module 对未知模块返回 False。"""
        assert is_known_module("MyCustomModule") is False

    def test_list_modules_by_category_mcal(self) -> None:
        """list_modules_by_category 列出全部 MCAL 模块。"""
        mcal = list_modules_by_category("MCAL")
        assert "Mcu" in mcal
        assert "Port" in mcal
        assert "Dio" in mcal
        assert "Can" in mcal
        assert "Spi" in mcal
        assert "PduR" not in mcal  # ECU 抽象层，不应出现

    def test_list_modules_by_category_empty(self) -> None:
        """list_modules_by_category 对未知类别返回空 tuple。"""
        assert list_modules_by_category("UNKNOWN") == ()
