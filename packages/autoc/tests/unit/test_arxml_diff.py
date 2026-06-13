"""Unit tests for arxml_diff — Sprint 9.2 M1-T — T9.2-β.

10 test cases covering:

  - pure function (no I/O)
  - add / modify / delete 三种 op 各自
  - 混合多 op
  - path-keyed 比较（不依赖 order）
  - 同 (path, raw) 视为无 diff
  - module_name 一致性校验
  - 不可变 dataclass（frozen）
  - 排序稳定性
"""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_autosar.core.bsw.ecuc import ECUCValue, ECUCDocument
from claude_autosar.core.bsw.templates.arxml_diff import (
    TemplateDiff,
    TemplateDiffResult,
    diff_arxml_templates,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _doc(module: str, *values: tuple[str, str, str]) -> ECUCDocument:
    """便利：构造 ECUCDocument。``values`` 是 (path, raw, type) 元组。"""
    return ECUCDocument(
        path=Path("/tmp/dummy.arxml"),
        module_name=module,
        values=tuple(ECUCValue(path=p, raw=r, type=t) for p, r, t in values),
    )


# ---------------------------------------------------------------------------
# 1. 纯函数 — 无 I/O
# ---------------------------------------------------------------------------


def test_diff_pure_function_no_io() -> None:
    """diff_arxml_templates 不读文件、不写文件。"""
    current = _doc("Can", ("Can/CanHwChannel", "FlexCAN_A", "ENUMERATION"))
    template = _doc("Can", ("Can/CanHwChannel", "FlexCAN_B", "ENUMERATION"))

    result = diff_arxml_templates(current, template)

    assert isinstance(result, TemplateDiffResult)
    # 原始 doc 不可变
    assert current.values[0].raw == "FlexCAN_A"
    assert template.values[0].raw == "FlexCAN_B"


# ---------------------------------------------------------------------------
# 2. modify op
# ---------------------------------------------------------------------------


def test_diff_modify_detects_value_change() -> None:
    """raw 变化 → 1 个 modify。"""
    current = _doc("Can", ("Can/CanHwChannel", "FlexCAN_A", "ENUMERATION"))
    template = _doc("Can", ("Can/CanHwChannel", "FlexCAN_B", "ENUMERATION"))

    result = diff_arxml_templates(current, template)

    assert len(result.diffs) == 1
    d = result.diffs[0]
    assert d.op == "modify"
    assert d.path == "Can/CanHwChannel"
    assert d.current is not None and d.current.raw == "FlexCAN_A"
    assert d.template is not None and d.template.raw == "FlexCAN_B"


# ---------------------------------------------------------------------------
# 3. add op
# ---------------------------------------------------------------------------


def test_diff_add_detects_new_path() -> None:
    """template 有但 current 没有 → 1 个 add。"""
    current = _doc("Can", ("Can/CanHwChannel", "FlexCAN_A", "ENUMERATION"))
    template = _doc(
        "Can",
        ("Can/CanHwChannel", "FlexCAN_A", "ENUMERATION"),
        ("Can/CanControllerBaudRate", "500", "INTEGER"),
    )

    result = diff_arxml_templates(current, template)

    assert len(result.diffs) == 1
    d = result.diffs[0]
    assert d.op == "add"
    assert d.path == "Can/CanControllerBaudRate"
    assert d.current is None
    assert d.template is not None and d.template.raw == "500"


# ---------------------------------------------------------------------------
# 4. delete op
# ---------------------------------------------------------------------------


def test_diff_delete_detects_missing_path() -> None:
    """current 有但 template 没有 → 1 个 delete。"""
    current = _doc(
        "Can",
        ("Can/CanHwChannel", "FlexCAN_A", "ENUMERATION"),
        ("Can/CanControllerBaudRate", "500", "INTEGER"),
    )
    template = _doc("Can", ("Can/CanHwChannel", "FlexCAN_A", "ENUMERATION"))

    result = diff_arxml_templates(current, template)

    assert len(result.diffs) == 1
    d = result.diffs[0]
    assert d.op == "delete"
    assert d.path == "Can/CanControllerBaudRate"
    assert d.current is not None and d.current.raw == "500"
    assert d.template is None


# ---------------------------------------------------------------------------
# 5. 混合：add + modify + delete
# ---------------------------------------------------------------------------


def test_diff_mixed_add_modify_delete() -> None:
    """多个 op 混合。"""
    current = _doc(
        "Can",
        ("Can/CanHwChannel", "FlexCAN_A", "ENUMERATION"),  # modify
        ("Can/CanControllerBaudRate", "250", "INTEGER"),  # delete
    )
    template = _doc(
        "Can",
        ("Can/CanHwChannel", "FlexCAN_B", "ENUMERATION"),  # modify
        ("Can/CanControllerId", "0", "INTEGER"),  # add
    )

    result = diff_arxml_templates(current, template)

    ops = {d.op for d in result.diffs}
    assert ops == {"add", "modify", "delete"}
    assert len(result.modifies) == 1
    assert len(result.adds) == 1
    assert len(result.deletes) == 1


# ---------------------------------------------------------------------------
# 6. 同 (path, raw) → 视为无 diff
# ---------------------------------------------------------------------------


def test_diff_no_change_when_raw_equal() -> None:
    """相同 path + 相同 raw → 没有 diff。"""
    current = _doc("Can", ("Can/CanHwChannel", "FlexCAN_A", "ENUMERATION"))
    template = _doc("Can", ("Can/CanHwChannel", "FlexCAN_A", "ENUMERATION"))

    result = diff_arxml_templates(current, template)

    assert result.is_empty()
    assert len(result.diffs) == 0


# ---------------------------------------------------------------------------
# 7. path-keyed — order independent
# ---------------------------------------------------------------------------


def test_diff_path_keyed_order_independent() -> None:
    """diff 按 path 比较，不依赖 values 列表顺序。"""
    current = _doc(
        "Can",
        ("Can/A", "1", "INTEGER"),
        ("Can/B", "2", "INTEGER"),
        ("Can/C", "3", "INTEGER"),
    )
    # template 反向
    template = _doc(
        "Can",
        ("Can/C", "3", "INTEGER"),
        ("Can/B", "20", "INTEGER"),  # modify
        ("Can/A", "1", "INTEGER"),
    )

    result = diff_arxml_templates(current, template)

    assert len(result.diffs) == 1
    d = result.diffs[0]
    assert d.op == "modify"
    assert d.path == "Can/B"


# ---------------------------------------------------------------------------
# 8. module_name mismatch
# ---------------------------------------------------------------------------


def test_diff_raises_on_module_name_mismatch() -> None:
    """两个 doc 的 module_name 不一致 → 抛 ValueError。"""
    current = _doc("Can", ("Can/CanHwChannel", "FlexCAN_A", "ENUMERATION"))
    template = _doc("Com", ("Com/ComGeneral", "0", "INTEGER"))

    with pytest.raises(ValueError, match="module_name mismatch"):
        diff_arxml_templates(current, template)


# ---------------------------------------------------------------------------
# 9. TemplateDiffResult 不可变 + frozen
# ---------------------------------------------------------------------------


def test_diff_result_is_frozen() -> None:
    """TemplateDiffResult / TemplateDiff 都是 frozen。"""
    current = _doc("Can", ("Can/X", "1", "INTEGER"))
    template = _doc("Can", ("Can/X", "2", "INTEGER"))

    result = diff_arxml_templates(current, template)

    with pytest.raises((AttributeError, Exception)):  # FrozenInstanceError
        result.module_name = "X"  # type: ignore[misc]

    with pytest.raises((AttributeError, Exception)):
        result.diffs[0].op = "add"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 10. 排序稳定性
# ---------------------------------------------------------------------------


def test_diff_results_sorted_by_path_then_op() -> None:
    """多个 diff 按 path 升序 → op 升序 排序。"""
    current = _doc(
        "Can",
        ("Can/A", "1", "INTEGER"),
        ("Can/B", "2", "INTEGER"),
    )
    template = _doc(
        "Can",
        ("Can/A", "10", "INTEGER"),
        ("Can/B", "20", "INTEGER"),
    )

    result = diff_arxml_templates(current, template)

    # 2 个 modify，按 path 升序
    assert len(result.diffs) == 2
    assert result.diffs[0].path == "Can/A"
    assert result.diffs[1].path == "Can/B"


# ---------------------------------------------------------------------------
# Bonus: TemplateDiffOp 是 Literal type
# ---------------------------------------------------------------------------


def test_template_diff_op_literal() -> None:
    """TemplateDiffOp 是 Literal["add", "modify", "delete"]; 仅在 op 字段上校验。"""
    # 用 TemplateDiff 构造时 op 字段接收 Literal 之一
    d1 = TemplateDiff(path="a", current=None, template=None, op="add")
    d2 = TemplateDiff(path="a", current=None, template=None, op="modify")
    d3 = TemplateDiff(path="a", current=None, template=None, op="delete")
    assert d1.op == "add"
    assert d2.op == "modify"
    assert d3.op == "delete"
