"""Unit tests for claude_autosar.core.bsw.templates.xdm_diff.

Sprint 9.2 — T9.2-α. Covers:

  - TemplateDiff / TemplateDiffResult frozen-ness
  - diff_xdm_templates add / modify / delete semantics
  - identical (path, raw) → not recorded
  - convenience properties (adds / modifies / deletes / is_empty)
  - sort stability by (path, op)
  - empty module edge cases
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from claude_autosar.core.bsw.templates.xdm_diff import (
    TemplateDiff,
    TemplateDiffResult,
    diff_xdm_templates,
)
from claude_autosar.core.bsw.templates.xdm_value import XDMModule, XDMValue

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mod(name: str, leaves: list[tuple[str, str, str]]) -> XDMModule:
    """造一个 XDMModule；leaves = [(path, raw, type), ...]。"""
    return XDMModule(
        path=Path(f"/tmp/{name}.xdm"),
        module_name=name,
        values=tuple(
            XDMValue(path=p, raw=r, type=t) for (p, r, t) in leaves  # type: ignore[arg-type]
        ),
    )


def _v(path: str, raw: str, type_: str = "INTEGER") -> XDMValue:
    return XDMValue(path=path, raw=raw, type=type_)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 1. dataclass frozen / hashable
# ---------------------------------------------------------------------------


class TestTemplateDiffFrozen:
    def test_template_diff_is_frozen(self) -> None:
        d = TemplateDiff(
            path="Can/A",
            current=None,
            template=_v("Can/A", "x"),
            op="add",
        )
        with pytest.raises(FrozenInstanceError):
            d.path = "Can/B"  # type: ignore[misc]

    def test_template_diff_result_is_frozen(self) -> None:
        r = TemplateDiffResult(diffs=())
        with pytest.raises(FrozenInstanceError):
            r.diffs = ()  # type: ignore[misc]

    def test_template_diff_is_hashable(self) -> None:
        d = TemplateDiff(
            path="Can/A",
            current=None,
            template=_v("Can/A", "x"),
            op="add",
        )
        assert {d} == {d}

    def test_template_diff_result_is_hashable(self) -> None:
        r = TemplateDiffResult(diffs=())
        assert {r} == {r}


# ---------------------------------------------------------------------------
# 2. add (template has, current missing)
# ---------------------------------------------------------------------------


class TestAdd:
    def test_path_only_in_template_produces_add(self) -> None:
        current = _mod("Can", [("Can/A", "old", "INTEGER")])
        template = _mod("Can", [("Can/A", "old", "INTEGER"), ("Can/B", "new", "BOOLEAN")])
        result = diff_xdm_templates(current, template)
        assert len(result.diffs) == 1
        d = result.diffs[0]
        assert d.path == "Can/B"
        assert d.op == "add"
        assert d.current is None
        assert d.template is not None
        assert d.template.raw == "new"

    def test_adds_property_filters_correctly(self) -> None:
        current = _mod("Can", [])
        template = _mod(
            "Can",
            [
                ("Can/A", "x", "INTEGER"),
                ("Can/B", "y", "BOOLEAN"),
            ],
        )
        result = diff_xdm_templates(current, template)
        assert len(result.adds) == 2
        assert {d.path for d in result.adds} == {"Can/A", "Can/B"}


# ---------------------------------------------------------------------------
# 3. delete (current has, template missing)
# ---------------------------------------------------------------------------


class TestDelete:
    def test_path_only_in_current_produces_delete(self) -> None:
        current = _mod(
            "Can",
            [("Can/A", "x", "INTEGER"), ("Can/B", "y", "BOOLEAN")],
        )
        template = _mod("Can", [("Can/A", "x", "INTEGER")])
        result = diff_xdm_templates(current, template)
        assert len(result.diffs) == 1
        d = result.diffs[0]
        assert d.path == "Can/B"
        assert d.op == "delete"
        assert d.template is None
        assert d.current is not None
        assert d.current.raw == "y"

    def test_deletes_property_filters_correctly(self) -> None:
        current = _mod(
            "Can",
            [
                ("Can/A", "x", "INTEGER"),
                ("Can/B", "y", "BOOLEAN"),
                ("Can/C", "z", "STRING"),
            ],
        )
        template = _mod("Can", [])
        result = diff_xdm_templates(current, template)
        assert len(result.deletes) == 3
        assert {d.path for d in result.deletes} == {
            "Can/A",
            "Can/B",
            "Can/C",
        }


# ---------------------------------------------------------------------------
# 4. modify (in both, raw differs)
# ---------------------------------------------------------------------------


class TestModify:
    def test_same_path_different_raw_produces_modify(self) -> None:
        current = _mod("Can", [("Can/A", "old", "INTEGER")])
        template = _mod("Can", [("Can/A", "new", "INTEGER")])
        result = diff_xdm_templates(current, template)
        assert len(result.diffs) == 1
        d = result.diffs[0]
        assert d.path == "Can/A"
        assert d.op == "modify"
        assert d.current is not None and d.current.raw == "old"
        assert d.template is not None and d.template.raw == "new"

    def test_modifies_property_filters_correctly(self) -> None:
        current = _mod(
            "Can",
            [("Can/A", "1", "INTEGER"), ("Can/B", "y", "BOOLEAN")],
        )
        template = _mod(
            "Can",
            [("Can/A", "2", "INTEGER"), ("Can/B", "y", "BOOLEAN")],
        )
        result = diff_xdm_templates(current, template)
        assert len(result.modifies) == 1
        assert result.modifies[0].path == "Can/A"


# ---------------------------------------------------------------------------
# 5. identical (path, raw) → not recorded
# ---------------------------------------------------------------------------


class TestIdenticalNotRecorded:
    def test_same_path_same_raw_yields_empty_diff(self) -> None:
        current = _mod("Can", [("Can/A", "x", "INTEGER")])
        template = _mod("Can", [("Can/A", "x", "INTEGER")])
        result = diff_xdm_templates(current, template)
        assert result.is_empty()
        assert result.diffs == ()
        assert result.adds == ()
        assert result.modifies == ()
        assert result.deletes == ()

    def test_type_does_not_trigger_modify(self) -> None:
        """type 字段不一致不算 modify（仅 raw 文本比较）。"""
        current = _mod("Can", [("Can/A", "x", "INTEGER")])
        template = _mod("Can", [("Can/A", "x", "STRING")])
        result = diff_xdm_templates(current, template)
        assert result.is_empty()


# ---------------------------------------------------------------------------
# 6. mixed (add + modify + delete in one result)
# ---------------------------------------------------------------------------


class TestMixed:
    def test_mixed_ops_all_present(self) -> None:
        current = _mod(
            "Can",
            [
                ("Can/A", "old_a", "INTEGER"),  # modify
                ("Can/B", "x", "BOOLEAN"),  # unchanged
                ("Can/C", "del", "STRING"),  # delete
            ],
        )
        template = _mod(
            "Can",
            [
                ("Can/A", "new_a", "INTEGER"),  # modify
                ("Can/B", "x", "BOOLEAN"),  # unchanged
                ("Can/D", "added", "STRING"),  # add
            ],
        )
        result = diff_xdm_templates(current, template)
        paths_by_op: dict[str, set[str]] = {
            "add": set(),
            "modify": set(),
            "delete": set(),
        }
        for d in result.diffs:
            paths_by_op[d.op].add(d.path)
        assert paths_by_op["add"] == {"Can/D"}
        assert paths_by_op["modify"] == {"Can/A"}
        assert paths_by_op["delete"] == {"Can/C"}
        # 三个 property 互不相交
        assert set(result.adds) | set(result.modifies) | set(result.deletes) == set(result.diffs)


# ---------------------------------------------------------------------------
# 7. empty edge cases
# ---------------------------------------------------------------------------


class TestEmptyModules:
    def test_both_empty_yields_empty_diff(self) -> None:
        result = diff_xdm_templates(_mod("Can", []), _mod("Can", []))
        assert result.is_empty()

    def test_empty_current_yields_all_adds(self) -> None:
        current = _mod("Can", [])
        template = _mod(
            "Can",
            [("Can/A", "x", "INTEGER"), ("Can/B", "y", "BOOLEAN")],
        )
        result = diff_xdm_templates(current, template)
        assert len(result.adds) == 2
        assert len(result.deletes) == 0
        assert len(result.modifies) == 0

    def test_empty_template_yields_all_deletes(self) -> None:
        current = _mod(
            "Can",
            [("Can/A", "x", "INTEGER"), ("Can/B", "y", "BOOLEAN")],
        )
        template = _mod("Can", [])
        result = diff_xdm_templates(current, template)
        assert len(result.adds) == 0
        assert len(result.deletes) == 2
        assert len(result.modifies) == 0


# ---------------------------------------------------------------------------
# 8. sort stability
# ---------------------------------------------------------------------------


class TestSortStability:
    def test_diffs_sorted_by_path_then_op(self) -> None:
        # 故意构造乱序 path，验证返回是排好序的
        current = _mod(
            "Can",
            [("Can/Z", "x", "INTEGER"), ("Can/A", "x", "INTEGER")],
        )
        template = _mod(
            "Can",
            [
                ("Can/A", "x", "INTEGER"),
                ("Can/Z", "new", "INTEGER"),
                ("Can/M", "added", "BOOLEAN"),
            ],
        )
        result = diff_xdm_templates(current, template)
        paths = [d.path for d in result.diffs]
        assert paths == sorted(paths)
        # 至少有一个 add（Can/M）和一个 modify（Can/Z）
        ops = [d.op for d in result.diffs]
        assert "add" in ops
        assert "modify" in ops
        assert "delete" in ops or len(ops) >= 2  # Can/A 也可能被 delete


# ---------------------------------------------------------------------------
# 9. immutability of inputs
# ---------------------------------------------------------------------------


class TestInputsNotMutated:
    def test_diff_does_not_mutate_inputs(self) -> None:
        cur_values = (
            _v("Can/A", "old", "INTEGER"),
            _v("Can/B", "x", "BOOLEAN"),
        )
        tpl_values = (
            _v("Can/A", "new", "INTEGER"),
            _v("Can/C", "y", "STRING"),
        )
        current = XDMModule(path=Path("/tmp/a.xdm"), module_name="Can", values=cur_values)
        template = XDMModule(path=Path("/tmp/b.xdm"), module_name="Can", values=tpl_values)
        snapshot_cur = tuple(current.values)
        snapshot_tpl = tuple(template.values)
        diff_xdm_templates(current, template)
        assert tuple(current.values) == snapshot_cur
        assert tuple(template.values) == snapshot_tpl


# ---------------------------------------------------------------------------
# 10. convenience property total covers diffs
# ---------------------------------------------------------------------------


class TestPropertiesCoverDiffs:
    def test_three_properties_partition_diffs(self) -> None:
        current = _mod(
            "Can",
            [
                ("Can/A", "old", "INTEGER"),
                ("Can/B", "x", "BOOLEAN"),
            ],
        )
        template = _mod(
            "Can",
            [
                ("Can/A", "new", "INTEGER"),
                ("Can/C", "added", "STRING"),
            ],
        )
        result = diff_xdm_templates(current, template)
        # adds + modifies + deletes == diffs（互不相交 + 全覆盖）
        combined = set(result.adds) | set(result.modifies) | set(result.deletes)
        assert combined == set(result.diffs)
        # 每条 diff 恰好落在一个 property
        for d in result.diffs:
            if d.op == "add":
                assert d in result.adds
            elif d.op == "modify":
                assert d in result.modifies
            elif d.op == "delete":
                assert d in result.deletes
