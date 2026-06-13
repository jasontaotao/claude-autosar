"""配置合并单元测试。"""

from __future__ import annotations

import json
from pathlib import Path

from claude_autosar.core.settings.config import deep_merge, load_json, load_merged_settings

# =============================================================================
# deep_merge
# =============================================================================


class TestDeepMerge:
    """深度合并逻辑。"""

    def test_simple_override(self) -> None:
        """简单标量覆盖。"""
        base = {"a": 0, "b": 2}
        override = {"a": 1}
        result = deep_merge(base, override)
        assert result == {"a": 1, "b": 2}

    def test_nested_dict_recursive_merge(self) -> None:
        """嵌套 dict 递归合并，不覆盖未提到的键。"""
        base = {"x": {"a": 1, "b": 2}}
        override = {"x": {"b": 3, "c": 4}}
        result = deep_merge(base, override)
        assert result == {"x": {"a": 1, "b": 3, "c": 4}}

    def test_scalar_overrides_dict(self) -> None:
        """标量覆盖 dict：直接替换。"""
        base = {"x": {"a": 1}}
        override = {"x": "scalar"}
        result = deep_merge(base, override)
        assert result == {"x": "scalar"}

    def test_dict_overrides_scalar(self) -> None:
        """dict 覆盖标量：直接替换。"""
        base = {"x": "scalar"}
        override = {"x": {"a": 1}}
        result = deep_merge(base, override)
        assert result == {"x": {"a": 1}}

    def test_empty_override(self) -> None:
        """空 override 返回 base 的副本。"""
        base = {"a": 1, "b": {"c": 2}}
        result = deep_merge(base, {})
        assert result == base
        assert result is not base  # 不可变

    def test_empty_base(self) -> None:
        """空 base 返回 override 的副本。"""
        override = {"a": 1, "b": {"c": 2}}
        result = deep_merge({}, override)
        assert result == override
        assert result is not override  # 不可变

    def test_does_not_mutate_base(self) -> None:
        """deep_merge 不修改入参。"""
        base = {"x": {"a": 1}}
        base_snapshot = {"x": {"a": 1}}
        deep_merge(base, {"x": {"b": 2}})
        assert base == base_snapshot

    def test_does_not_mutate_override(self) -> None:
        """deep_merge 不修改 override。"""
        override = {"x": {"a": 1}}
        override_snapshot = {"x": {"a": 1}}
        deep_merge({"x": {"b": 0}}, override)
        assert override == override_snapshot

    def test_list_replaced_not_merged(self) -> None:
        """list 整体覆盖，不元素级合并。"""
        base = {"items": [1, 2, 3]}
        override = {"items": [4, 5]}
        result = deep_merge(base, override)
        assert result == {"items": [4, 5]}

    def test_deep_nesting(self) -> None:
        """3 层嵌套正确合并。"""
        base = {"a": {"b": {"c": 1, "d": 2}}}
        override = {"a": {"b": {"d": 20, "e": 30}}}
        result = deep_merge(base, override)
        assert result == {"a": {"b": {"c": 1, "d": 20, "e": 30}}}


# =============================================================================
# load_json
# =============================================================================


class TestLoadJson:
    """JSON 文件加载。"""

    def test_load_existing_valid_json(self, tmp_path: Path) -> None:
        """合法 JSON 可加载。"""
        p = tmp_path / "cfg.json"
        p.write_text(json.dumps({"a": 1}), encoding="utf-8")
        assert load_json(p) == {"a": 1}

    def test_load_nonexistent_returns_empty(self, tmp_path: Path) -> None:
        """文件不存在返回 {}。"""
        p = tmp_path / "missing.json"
        assert load_json(p) == {}

    def test_load_invalid_json_returns_empty(self, tmp_path: Path) -> None:
        """非法 JSON 返回 {}。"""
        p = tmp_path / "bad.json"
        p.write_text("{not valid json", encoding="utf-8")
        assert load_json(p) == {}

    def test_load_top_level_list_returns_empty(self, tmp_path: Path) -> None:
        """顶层不是 dict（如 list）返回 {}。"""
        p = tmp_path / "list.json"
        p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        assert load_json(p) == {}

    def test_load_top_level_scalar_returns_empty(self, tmp_path: Path) -> None:
        """顶层是标量返回 {}。"""
        p = tmp_path / "scalar.json"
        p.write_text("42", encoding="utf-8")
        assert load_json(p) == {}


# =============================================================================
# load_merged_settings
# =============================================================================


class TestLoadMergedSettings:
    """三级配置合并。"""

    def test_only_global(self, sample_settings_json: Path) -> None:
        """只有 global 时直接返回其内容。"""
        result = load_merged_settings(sample_settings_json)
        assert result["theme"] == "dark"
        assert result["compaction"]["enabled"] is True

    def test_global_and_project_override(
        self,
        sample_settings_json: Path,
        tmp_path: Path,
    ) -> None:
        """project 覆盖 global 相同字段。"""
        project = tmp_path / "project.json"
        project.write_text(
            json.dumps({"theme": "light", "extra": "value"}),
            encoding="utf-8",
        )
        result = load_merged_settings(sample_settings_json, project)
        # 覆盖生效
        assert result["theme"] == "light"
        # global 原值保留
        assert result["compaction"]["enabled"] is True
        # project 独有字段追加
        assert result["extra"] == "value"

    def test_only_project(self, tmp_path: Path) -> None:
        """global 不存在时只用 project。"""
        project = tmp_path / "project.json"
        project.write_text(json.dumps({"a": 1}), encoding="utf-8")
        nonexistent = tmp_path / "missing.json"
        result = load_merged_settings(nonexistent, project)
        assert result == {"a": 1}

    def test_both_missing(self, tmp_path: Path) -> None:
        """两者都缺失返回空 dict。"""
        result = load_merged_settings(
            tmp_path / "missing1.json",
            tmp_path / "missing2.json",
        )
        assert result == {}

    def test_nested_override_merges(
        self,
        sample_settings_json: Path,
        tmp_path: Path,
    ) -> None:
        """嵌套字段覆盖：project 中只改 reserveTokens，其它保留。"""
        project = tmp_path / "project.json"
        project.write_text(
            json.dumps({"compaction": {"reserveTokens": 8192}}),
            encoding="utf-8",
        )
        result = load_merged_settings(sample_settings_json, project)
        assert result["compaction"]["enabled"] is True  # 来自 global
        assert result["compaction"]["reserveTokens"] == 8192  # 来自 project
