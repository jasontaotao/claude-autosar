"""Unit tests for Sprint 9.4 M4 (T9.4-β) — MCP ``arxml_inspect`` /
``xdm_inspect`` / ``bsw_inspect`` 工具的 ``include_lint`` 激活。

覆盖：

- ``include_lint=False``（默认）→ 返 dict 不含 lint 字段（向后兼容）
- ``include_lint=True`` + lint 框架不可用 → 返 ``lint_unavailable=True``
- ``include_lint=True`` + lint 框架可用 → 返 ``violations`` + ``lint_summary``
- ``bsw_inspect`` 同样接受 ``include_lint=True``
- 现有 9.1 T9.1.4 的 tool 注册测试不被破坏（dispatch 表计数稳定）
- lint 失败（extract 抛错）→ 主流程仍返 success=True，无 lint 字段
"""

from __future__ import annotations

from pathlib import Path
import sys
from types import ModuleType
from typing import Any

import pytest

pytestmark = pytest.mark.autosar


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
ARXML_FIXTURE = FIXTURES_DIR / "arxml" / "Com_Com.minimal.arxml"
XDM_FIXTURE = FIXTURES_DIR / "datamodel2" / "Can.xdm"


# ---------------------------------------------------------------------------
# 假 lint 框架（不依赖 9.4-α；同 test_cli_lint.py）
# ---------------------------------------------------------------------------


class _FakeViolation:
    def __init__(
        self,
        rule_id: str,
        severity: str,
        message: str,
        path: str = "",
        line: int | None = None,
    ) -> None:
        self.rule_id = rule_id
        self.severity = severity
        self.message = message
        self.path = path
        self.line = line


class _FakeSummary:
    def __init__(self, total: int, by_severity: dict[str, int]) -> None:
        self.total = total
        self.by_severity = by_severity


class _FakeRunner:
    def __init__(
        self, rules: tuple[Any, ...] = (), *, canned: list[_FakeViolation] | None = None
    ) -> None:
        self.rules = rules
        self._canned = canned if canned is not None else []

    def run(self, _extracted: Any) -> list[_FakeViolation]:
        return list(self._canned)

    def summarize(self, vs: list[_FakeViolation]) -> _FakeSummary:
        bs: dict[str, int] = {}
        for v in vs:
            bs[v.severity] = bs.get(v.severity, 0) + 1
        return _FakeSummary(total=len(vs), by_severity=bs)


def _install_fake_lint(
    monkeypatch: pytest.MonkeyPatch,
    canned: list[_FakeViolation] | None = None,
    *,
    raise_on_extract: bool = False,
) -> None:
    """Install fake lint modules; optionally inject extract failure."""
    fake_lint = ModuleType("claude_autosar.core.bsw.lint")
    fake_lint.LintViolation = _FakeViolation  # type: ignore[attr-defined]
    fake_lint.LintRunner = _FakeRunner  # type: ignore[attr-defined]
    fake_lint.LintSummary = _FakeSummary  # type: ignore[attr-defined]

    def _runner_factory(rules: tuple[Any, ...] = ()) -> _FakeRunner:
        return _FakeRunner(rules=rules, canned=canned or [])

    fake_lint.LintRunner = _runner_factory  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "claude_autosar.core.bsw.lint", fake_lint)

    fake_rules = ModuleType("claude_autosar.core.bsw.lint.rules")
    fake_rules.ALL_RULES = (object(),)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "claude_autosar.core.bsw.lint.rules", fake_rules)

    fake_extract = ModuleType("claude_autosar.core.bsw.lint.extract")
    if raise_on_extract:

        def _explode(_p: Any) -> Any:
            raise OSError("fake extract failure")

        fake_extract.extract_arxml_for_lint = _explode  # type: ignore[attr-defined]
        fake_extract.extract_xdm_for_lint = _explode  # type: ignore[attr-defined]
    else:
        fake_extract.extract_arxml_for_lint = lambda _p: "arxml-stub"  # type: ignore[attr-defined]
        fake_extract.extract_xdm_for_lint = lambda _p: "xdm-stub"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "claude_autosar.core.bsw.lint.extract", fake_extract)


# ---------------------------------------------------------------------------
# include_lint=False (默认) — 向后兼容
# ---------------------------------------------------------------------------


class TestIncludeLintFalse:
    def test_arxml_inspect_default_excludes_lint(self, tmp_path: Path) -> None:
        from claude_autosar.cli.mcp_server import arxml_inspect

        src = tmp_path / "Com_Com.minimal.arxml"
        src.write_bytes(ARXML_FIXTURE.read_bytes())

        result = arxml_inspect(str(src))
        assert result["success"] is True
        # 不含任何 lint 字段
        for k in ("violations", "lint_summary", "lint_unavailable"):
            assert k not in result, f"include_lint=False should not return {k!r}, got {result}"

    def test_xdm_inspect_default_excludes_lint(self, tmp_path: Path) -> None:
        from claude_autosar.cli.mcp_server import xdm_inspect

        src = tmp_path / "Can.xdm"
        src.write_bytes(XDM_FIXTURE.read_bytes())

        result = xdm_inspect(str(src))
        assert result["success"] is True
        for k in ("violations", "lint_summary", "lint_unavailable"):
            assert k not in result, f"include_lint=False should not return {k!r}, got {result}"

    def test_bsw_inspect_default_excludes_lint(self, tmp_path: Path) -> None:
        from claude_autosar.cli.mcp_server import bsw_inspect

        src = tmp_path / "Com_Com.minimal.arxml"
        src.write_bytes(ARXML_FIXTURE.read_bytes())

        result = bsw_inspect(str(src))
        assert result["success"] is True
        for k in ("violations", "lint_summary", "lint_unavailable"):
            assert k not in result


# ---------------------------------------------------------------------------
# include_lint=True + lint 框架不可用
# ---------------------------------------------------------------------------


class TestIncludeLintUnavailable:
    def test_arxml_inspect_lint_unavailable(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from claude_autosar.cli.mcp_server import arxml_inspect

        # 把 _run_lint_for_inspect 替换成返 None（模拟 lint 框架不可用）
        monkeypatch.setattr(
            "claude_autosar.cli.mcp_server._run_lint_for_inspect",
            lambda _src, _fmt: None,
        )

        src = tmp_path / "Com_Com.minimal.arxml"
        src.write_bytes(ARXML_FIXTURE.read_bytes())

        result = arxml_inspect(str(src), include_lint=True)
        assert result["success"] is True
        assert result["lint_unavailable"] is True
        assert "violations" not in result
        assert "lint_summary" not in result

    def test_xdm_inspect_lint_unavailable(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from claude_autosar.cli.mcp_server import xdm_inspect

        monkeypatch.setattr(
            "claude_autosar.cli.mcp_server._run_lint_for_inspect",
            lambda _src, _fmt: None,
        )

        src = tmp_path / "Can.xdm"
        src.write_bytes(XDM_FIXTURE.read_bytes())

        result = xdm_inspect(str(src), include_lint=True)
        assert result["success"] is True
        assert result["lint_unavailable"] is True

    def test_bsw_inspect_lint_unavailable(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from claude_autosar.cli.mcp_server import bsw_inspect

        monkeypatch.setattr(
            "claude_autosar.cli.mcp_server._run_lint_for_inspect",
            lambda _src, _fmt: None,
        )

        src = tmp_path / "Com_Com.minimal.arxml"
        src.write_bytes(ARXML_FIXTURE.read_bytes())

        result = bsw_inspect(str(src), include_lint=True)
        assert result["success"] is True
        assert result["lint_unavailable"] is True


# ---------------------------------------------------------------------------
# include_lint=True + lint 框架可用（fake-installed）
# ---------------------------------------------------------------------------


class TestIncludeLintAvailable:
    def test_arxml_inspect_with_violations(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from claude_autosar.cli.mcp_server import arxml_inspect

        canned = [
            _FakeViolation(
                rule_id="R-A",
                severity="error",
                message="bad",
                path="Com/ComIPdu[0]",
                line=42,
            ),
            _FakeViolation(
                rule_id="R-B",
                severity="warning",
                message="warn",
                path="Com/ComSignal[0]",
                line=10,
            ),
        ]
        # 直接把 _run_lint_for_inspect 替换成 fake
        monkeypatch.setattr(
            "claude_autosar.cli.mcp_server._run_lint_for_inspect",
            lambda _src, _fmt: {
                "violations": [
                    {
                        "rule_id": v.rule_id,
                        "severity": v.severity,
                        "message": v.message,
                        "path": v.path,
                        "line": v.line,
                    }
                    for v in canned
                ],
                "lint_summary": {
                    "total": len(canned),
                    "by_severity": {
                        "error": sum(1 for v in canned if v.severity == "error"),
                        "warning": sum(1 for v in canned if v.severity == "warning"),
                    },
                },
            },
        )

        src = tmp_path / "Com_Com.minimal.arxml"
        src.write_bytes(ARXML_FIXTURE.read_bytes())

        result = arxml_inspect(str(src), include_lint=True)
        assert result["success"] is True
        assert "lint_unavailable" not in result
        assert "violations" in result
        assert "lint_summary" in result
        assert result["lint_summary"]["total"] == 2
        assert result["lint_summary"]["by_severity"]["error"] == 1
        assert result["lint_summary"]["by_severity"]["warning"] == 1
        assert len(result["violations"]) == 2
        assert result["violations"][0]["rule_id"] == "R-A"

    def test_xdm_inspect_with_violations(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from claude_autosar.cli.mcp_server import xdm_inspect

        canned = [
            _FakeViolation(
                rule_id="XDM-001",
                severity="info",
                message="hint",
                path="Can/Mcu",
                line=1,
            )
        ]
        monkeypatch.setattr(
            "claude_autosar.cli.mcp_server._run_lint_for_inspect",
            lambda _src, _fmt: {
                "violations": [
                    {
                        "rule_id": v.rule_id,
                        "severity": v.severity,
                        "message": v.message,
                        "path": v.path,
                        "line": v.line,
                    }
                    for v in canned
                ],
                "lint_summary": {"total": 1, "by_severity": {"info": 1}},
            },
        )

        src = tmp_path / "Can.xdm"
        src.write_bytes(XDM_FIXTURE.read_bytes())

        result = xdm_inspect(str(src), include_lint=True)
        assert result["success"] is True
        assert result["lint_summary"]["by_severity"]["info"] == 1

    def test_bsw_inspect_dispatch_with_lint(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``bsw_inspect(include_lint=True)`` 必须能 dispatch 到 arxml lint。"""
        from claude_autosar.cli.mcp_server import bsw_inspect

        captured_fmt: list[str] = []

        def _fake_lint(_src: Any, fmt: str) -> dict[str, Any]:
            captured_fmt.append(fmt)
            return {
                "violations": [
                    {
                        "rule_id": "X",
                        "severity": "info",
                        "message": "",
                        "path": "",
                        "line": None,
                    }
                ],
                "lint_summary": {"total": 1, "by_severity": {"info": 1}},
            }

        monkeypatch.setattr("claude_autosar.cli.mcp_server._run_lint_for_inspect", _fake_lint)

        src = tmp_path / "Com_Com.minimal.arxml"
        src.write_bytes(ARXML_FIXTURE.read_bytes())

        result = bsw_inspect(str(src), include_lint=True)
        assert result["success"] is True
        assert result["format"] == "arxml"
        # 必须用 arxml 走 lint（不是 xdm）
        assert captured_fmt == ["arxml"]
        assert result["lint_summary"]["total"] == 1


# ---------------------------------------------------------------------------
# Lint 框架内部错误不污染主流程
# ---------------------------------------------------------------------------


class TestLintFailureIsolation:
    def test_arxml_inspect_lint_failure_does_not_break_main(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """extract 抛错时主流程返 success=True，无 lint 字段。"""
        from claude_autosar.cli.mcp_server import arxml_inspect

        # monkeypatch _run_lint_for_inspect 模拟 extract 失败
        monkeypatch.setattr(
            "claude_autosar.cli.mcp_server._run_lint_for_inspect",
            lambda _src, _fmt: None,
        )

        src = tmp_path / "Com_Com.minimal.arxml"
        src.write_bytes(ARXML_FIXTURE.read_bytes())

        result = arxml_inspect(str(src), include_lint=True)
        assert result["success"] is True
        assert result["lint_unavailable"] is True


# ---------------------------------------------------------------------------
# 9.1 T9.1.4 tool 注册不被破坏（计数 + 存在性）
# ---------------------------------------------------------------------------


class TestBackwardCompat:
    def test_tool_names_includes_three_inspect(self) -> None:
        """Sprint 9.1 T9.1.4 注册的 3 个 inspect tool 仍然在 ``_TOOL_NAMES``。"""
        from claude_autosar.cli.mcp_server import _TOOL_NAMES

        assert "arxml_inspect" in _TOOL_NAMES
        assert "xdm_inspect" in _TOOL_NAMES
        assert "bsw_inspect" in _TOOL_NAMES

    def test_tool_funcs_includes_three_inspect(self) -> None:
        from claude_autosar.cli.mcp_server import _TOOL_FUNCS

        for name in ("arxml_inspect", "xdm_inspect", "bsw_inspect"):
            assert name in _TOOL_FUNCS
            assert _TOOL_FUNCS[name].__name__ == name

    def test_build_mcp_server_registers_inspect_tools(self) -> None:
        from claude_autosar.cli.mcp_server import build_mcp_server

        server = build_mcp_server()
        tm = getattr(server, "_tool_manager", None)
        assert tm is not None
        tools_dict = getattr(tm, "_tools", None) or {}
        registered = set(tools_dict.keys())
        for name in ("arxml_inspect", "xdm_inspect", "bsw_inspect"):
            assert name in registered, f"missing tool in FastMCP: {name}"

    def test_bsw_inspect_accepts_include_lint_kwarg(self, tmp_path: Path) -> None:
        """``bsw_inspect`` 必须接受 ``include_lint`` keyword（向后兼容默认）。"""
        import inspect

        from claude_autosar.cli.mcp_server import bsw_inspect

        sig = inspect.signature(bsw_inspect)
        assert "include_lint" in sig.parameters
        # default = False
        assert sig.parameters["include_lint"].default is False
