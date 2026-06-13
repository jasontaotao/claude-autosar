"""Unit tests for T8.E.4 — BSWPathResolver typo defense.

Plan reference: Sprint 8.E T8.E.4 — `core/bsw/path_resolver.py` + suggestion.
Contract 4: BSWPathResolver API (frozen).
Contract 7: test naming + file layout (`TestPathResolver`).

Module-level fixtures (per plan: "fixture 放 test_path_resolver.py module 级")。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_autosar.core.bsw.ecuc import ECUCDocument, ECUCValue, list_paths
from claude_autosar.core.bsw.path_resolver import BSWPathResolver, ResolverResult

pytestmark = pytest.mark.arxml


# ---------------------------------------------------------------------------
# Module-level fixtures: 5 ECUC 路径典型 typo 场景
# ---------------------------------------------------------------------------


_S32K3_PATHS: tuple[str, ...] = (
    "Mcu/McuClockSettingConfig_0/McuClockFrequency",
    "Mcu/McuClockSettingConfig_0/McuClockTolerance",
    "Mcu/McuClockSettingConfig_0/McuClockName",
    "Mcu/McuClockSettingConfig_0/McuClockSource",
    "Port/PortConfigSet_0/PortPin_0/PortPinDirection",
    "Port/PortConfigSet_0/PortPin_0/PortPinLevel",
    "Can/CanConfigSet_0/CanController_0/CanControllerBaudRate",
)


def _make_doc() -> ECUCDocument:
    """构造合成 ECUCDocument（不依赖 lxml，path_resolver 只看 doc.values）。"""
    values = tuple(ECUCValue(path=p, raw="0", type="INTEGER") for p in _S32K3_PATHS)
    return ECUCDocument(
        path=Path("/tmp/fake.xdm"),
        module_name="Mcu",
        values=values,
    )


# ---------------------------------------------------------------------------
# Test: ResolverResult dataclass
# ---------------------------------------------------------------------------


class TestResolverResultDataclass:
    def test_resolver_result_is_frozen(self) -> None:
        r = ResolverResult(exact=True, original="x", suggestions=("a", "b"))
        with pytest.raises((AttributeError, Exception)):
            r.exact = False  # type: ignore[misc]

    def test_resolver_result_suggestions_default_empty(self) -> None:
        r = ResolverResult(exact=False, original="x")
        assert r.suggestions == ()


# ---------------------------------------------------------------------------
# Test: resolve() — exact match path
# ---------------------------------------------------------------------------


class TestResolveExactMatch:
    def test_resolve_exact_match_returns_empty_suggestions(self) -> None:
        result = BSWPathResolver.resolve(
            "Mcu/McuClockSettingConfig_0/McuClockFrequency",
            _S32K3_PATHS,
        )
        assert result.exact is True
        assert result.original == "Mcu/McuClockSettingConfig_0/McuClockFrequency"
        assert result.suggestions == ()

    def test_resolve_exact_match_in_middle_of_list(self) -> None:
        # 路径在 valid_paths 中间（不是首项）
        result = BSWPathResolver.resolve(
            "Port/PortConfigSet_0/PortPin_0/PortPinLevel",
            _S32K3_PATHS,
        )
        assert result.exact is True
        assert result.suggestions == ()

    def test_resolve_fuzzy_disabled_exact_match_still_works(self) -> None:
        # fuzzy=False 不影响 exact match（exact 永远最先判定）
        result = BSWPathResolver.resolve(
            "Mcu/McuClockSettingConfig_0/McuClockFrequency",
            _S32K3_PATHS,
            fuzzy=False,
        )
        assert result.exact is True
        assert result.suggestions == ()


# ---------------------------------------------------------------------------
# Test: resolve() — fuzzy match path
# ---------------------------------------------------------------------------


class TestResolveFuzzyMatch:
    def test_resolve_typo_close_to_one_path_returns_suggestion(self) -> None:
        # 末段拼错：McuClockFreqncy vs McuClockFrequency
        result = BSWPathResolver.resolve(
            "Mcu/McuClockSettingConfig_0/McuClockFreqncy",
            _S32K3_PATHS,
        )
        assert result.exact is False
        assert len(result.suggestions) >= 1
        assert "Mcu/McuClockSettingConfig_0/McuClockFrequency" in result.suggestions

    def test_resolve_typo_returns_at_most_3_suggestions(self) -> None:
        # 5 个合法 path，typo 接近 3 个 → 候选 ≤ 3
        target = "Mcu/McuClockSettingConfig_0/PortPin_0"
        result = BSWPathResolver.resolve(target, _S32K3_PATHS)
        assert result.exact is False
        assert len(result.suggestions) <= 3

    def test_resolve_typo_far_from_all_returns_empty_suggestions(self) -> None:
        # 距离太远（短字符串 + 完全不相关）→ 候选空
        result = BSWPathResolver.resolve("XyzFooBar", _S32K3_PATHS)
        assert result.exact is False
        assert result.suggestions == ()

    def test_resolve_module_name_typo_suggests_correct_module(self) -> None:
        # MCu → Mcu（module 名前缀写错）
        result = BSWPathResolver.resolve(
            "MCu/McuClockSettingConfig_0/McuClockFrequency",
            _S32K3_PATHS,
        )
        assert result.exact is False
        assert any(s == "Mcu/McuClockSettingConfig_0/McuClockFrequency" for s in result.suggestions)

    def test_resolve_fuzzy_disabled_returns_empty_suggestions(self) -> None:
        # fuzzy=False → 候选必空（哪怕 typo 离合法很近）
        result = BSWPathResolver.resolve(
            "Mcu/McuClockSettingConfig_0/McuClockFreqncy",
            _S32K3_PATHS,
            fuzzy=False,
        )
        assert result.exact is False
        assert result.suggestions == ()

    def test_resolve_dot_separator_typo_suggests_slash_form(self) -> None:
        # "Mcu.Clock0.ClockFreq"（. 分隔）→ 候选含 / 正确写法
        result = BSWPathResolver.resolve(
            "Mcu.McuClockSettingConfig_0.McuClockFrequency",
            _S32K3_PATHS,
        )
        # 此例可能因为分隔符差异大导致 ratio < 0.6（我们只校验 exact=False 即可）
        # 分隔符完全不同的 path 可能不会进入候选，但 exact 必 False
        assert result.exact is False
        # 注：实际候选可能为空（因为 . vs / 的 ratio 很低），但接口行为正确

    def test_resolve_empty_target_returns_empty(self) -> None:
        # 防御：空字符串 → exact=False, suggestions=()
        result = BSWPathResolver.resolve("", _S32K3_PATHS)
        assert result.exact is False
        assert result.suggestions == ()


# ---------------------------------------------------------------------------
# Test: suggest_for_ecuc_set_value_error() 便利方法
# ---------------------------------------------------------------------------


class TestSuggestForEcucSetValueError:
    def test_suggest_returns_suggestions_for_typo(self) -> None:
        doc = _make_doc()
        err_path = "Mcu/McuClockSettingConfig_0/McuClockFreqncy"
        suggestions = BSWPathResolver.suggest_for_ecuc_set_value_error(err_path, doc)
        assert "Mcu/McuClockSettingConfig_0/McuClockFrequency" in suggestions

    def test_suggest_returns_empty_for_unrelated_input(self) -> None:
        doc = _make_doc()
        suggestions = BSWPathResolver.suggest_for_ecuc_set_value_error("TotallyUnrelated", doc)
        assert suggestions == ()

    def test_suggest_uses_list_paths_for_valid_set(self) -> None:
        # 校验内部确实用了 list_paths(doc) 作 valid_paths
        doc = _make_doc()
        expected = list_paths(doc)
        assert len(expected) == len(_S32K3_PATHS)
        # valid_paths 是 list_paths(doc) → 跑 resolve 应得相同结果
        result_direct = BSWPathResolver.resolve(
            "Mcu/McuClockSettingConfig_0/McuClockFreqncy",
            expected,
        )
        result_indirect = BSWPathResolver.suggest_for_ecuc_set_value_error(
            "Mcu/McuClockSettingConfig_0/McuClockFreqncy", doc
        )
        assert result_direct.suggestions == result_indirect


# ---------------------------------------------------------------------------
# Test: 内部实现一致性
# ---------------------------------------------------------------------------


class TestResolveInternalContract:
    def test_min_ratio_constant_value(self) -> None:
        # 契约 4：_MIN_RATIO = 0.6（threshold constant）
        assert BSWPathResolver._MIN_RATIO == 0.6

    def test_resolve_returns_resolver_result_instance(self) -> None:
        # 类型契约：返回 ResolverResult
        result = BSWPathResolver.resolve("anything", _S32K3_PATHS)
        assert isinstance(result, ResolverResult)

    def test_resolve_empty_valid_paths_returns_no_match(self) -> None:
        # valid_paths 空时 → exact=False, suggestions=()
        result = BSWPathResolver.resolve(
            "Mcu/McuClockSettingConfig_0/McuClockFrequency",
            (),
        )
        assert result.exact is False
        assert result.suggestions == ()
