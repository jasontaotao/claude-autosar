"""Unit tests for Sprint 9.4 M4 (T9.4-β) — ``autoc lint`` 子命令。

覆盖：

- argparse ``--help`` 不崩（含 ``--output`` / ``--rule`` / ``--severity`` / ``--project``）
- ``_DISPATCH`` 表新增 ``lint`` 子命令（避免 import main.py — 那个模块
  会 import 9.2-γ 的 ``bsw_verify``，跟本切片无关）
- run() 在 lint 框架不可用（9.4-α 未并入）时返 ``lint_unavailable=True``
- run() 在 lint 框架可用时走 LintRunner 全集 → JSON stdout + 可选 HTML
- ``--severity`` 过滤生效
- XSS：恶意 violation message 含 ``<script>`` 必须 escape（HTML 报告）
- 不存在的文件 → exit 1 + stderr JSON error
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Any

import pytest

from claude_autosar.cli.commands.lint import build_parser, run

pytestmark = pytest.mark.autosar


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
ARXML_FIXTURE = FIXTURES_DIR / "arxml" / "Com_Com.minimal.arxml"


# ---------------------------------------------------------------------------
# Helpers — fake lint framework (no dependency on 9.4-α)
# ---------------------------------------------------------------------------


class _FakeViolation:
    """Mock LintViolation duck-typed shape."""

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
    canned: list[_FakeViolation],
) -> None:
    """把 fake ``claude_autosar.core.bsw.lint`` + 子模块塞进 sys.modules。"""
    fake_lint = ModuleType("claude_autosar.core.bsw.lint")
    fake_lint.LintViolation = _FakeViolation  # type: ignore[attr-defined]
    fake_lint.LintRunner = _FakeRunner  # type: ignore[attr-defined]
    fake_lint.LintSummary = _FakeSummary  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "claude_autosar.core.bsw.lint", fake_lint)

    fake_rules = ModuleType("claude_autosar.core.bsw.lint.rules")
    fake_rules.ALL_RULES = (object(),)  # type: ignore[attr-defined]
    monkeypatch.setitem(
        sys.modules, "claude_autosar.core.bsw.lint.rules", fake_rules
    )

    fake_extract = ModuleType("claude_autosar.core.bsw.lint.extract")
    fake_extract.extract_arxml_for_lint = lambda _p: "arxml-stub"  # type: ignore[attr-defined]
    fake_extract.extract_xdm_for_lint = lambda _p: "xdm-stub"  # type: ignore[attr-defined]
    monkeypatch.setitem(
        sys.modules, "claude_autosar.core.bsw.lint.extract", fake_extract
    )

    # Force fresh Runner factory with our canned list
    def _runner_factory(rules: tuple[Any, ...] = ()) -> _FakeRunner:
        return _FakeRunner(rules=rules, canned=canned)

    fake_lint.LintRunner = _runner_factory  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# argparse help
# ---------------------------------------------------------------------------


class TestArgparseHelp:
    def test_lint_help_exits_zero(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--help"])
        assert exc_info.value.code == 0

    def test_lint_help_lists_all_args(self, capsys: pytest.CaptureFixture[str]) -> None:
        """``lint --help`` 必须含全部参数（用子命令自身 parser，不走 main.py）。"""
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["lint", "--help"])
        captured = capsys.readouterr()
        for arg in ("--output", "--rule", "--severity", "--project"):
            assert arg in captured.out, f"missing arg {arg!r} in help text"

    def test_lint_module_exposes_register_and_run(self) -> None:
        """``commands.lint`` 模块必须暴露 ``register`` 和 ``run``。"""
        import claude_autosar.cli.commands.lint as lint_mod

        assert callable(getattr(lint_mod, "register", None))
        assert callable(getattr(lint_mod, "run", None))


# ---------------------------------------------------------------------------
# lint 框架不可用 (default state: 9.4-α 还没并入)
# ---------------------------------------------------------------------------


class TestLintUnavailable:
    def test_run_lint_unavailable_returns_flag(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        src = tmp_path / "Com_Com.minimal.arxml"
        src.write_bytes(ARXML_FIXTURE.read_bytes())

        # 把 _try_import_lint 替换成返 (None, None, None)，模拟 lint 框架不可用
        import claude_autosar.cli.commands.lint as lint_mod

        monkeypatch.setattr(
            lint_mod, "_try_import_lint", lambda: (None, None, None)
        )

        args = argparse.Namespace(
            path=src,
            output=None,
            rule=[],
            severity=None,
            project=".",
        )
        code = run(args)
        captured = capsys.readouterr()

        assert code == 0
        payload = json.loads(captured.out.strip().splitlines()[-1])
        assert payload["success"] is True
        assert payload["lint_unavailable"] is True
        assert payload["format"] == "arxml"


# ---------------------------------------------------------------------------
# lint 框架可用 (fake-installed)
# ---------------------------------------------------------------------------


class TestLintAvailable:
    def test_run_lint_outputs_json(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        src = tmp_path / "Com_Com.minimal.arxml"
        src.write_bytes(ARXML_FIXTURE.read_bytes())

        canned = [
            _FakeViolation(
                rule_id="R-001",
                severity="error",
                message="bad IPdu length",
                path="Com/ComIPdu[0]",
                line=42,
            ),
            _FakeViolation(
                rule_id="R-002",
                severity="warning",
                message="missing comment",
                path="Com/ComSignal[0]",
                line=10,
            ),
        ]
        _install_fake_lint(monkeypatch, canned)

        args = argparse.Namespace(
            path=src,
            output=None,
            rule=[],
            severity=None,
            project=".",
        )
        code = run(args)
        captured = capsys.readouterr()
        assert code == 0
        payload = json.loads(captured.out.strip().splitlines()[-1])
        assert payload["success"] is True
        assert payload["lint_unavailable"] is False
        assert payload["format"] == "arxml"
        assert payload["summary"]["total"] == 2
        assert payload["summary"]["by_severity"]["error"] == 1
        assert payload["summary"]["by_severity"]["warning"] == 1
        assert len(payload["violations"]) == 2
        v0 = payload["violations"][0]
        assert v0["rule_id"] == "R-001"
        assert v0["severity"] == "error"
        assert v0["line"] == 42

    def test_run_lint_severity_filter(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        src = tmp_path / "Com_Com.minimal.arxml"
        src.write_bytes(ARXML_FIXTURE.read_bytes())

        canned = [
            _FakeViolation(
                rule_id="R-E", severity="error", message="e", path="", line=1
            ),
            _FakeViolation(
                rule_id="R-W", severity="warning", message="w", path="", line=2
            ),
        ]
        _install_fake_lint(monkeypatch, canned)

        args = argparse.Namespace(
            path=src,
            output=None,
            rule=[],
            severity="error",
            project=".",
        )
        run(args)
        captured = capsys.readouterr()
        payload = json.loads(captured.out.strip().splitlines()[-1])
        assert payload["summary"]["total"] == 1
        assert payload["violations"][0]["severity"] == "error"

    def test_run_lint_html_report_escapes_xss(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """恶意 violation message 含 ``<script>`` → HTML 必须 escape。"""
        src = tmp_path / "Com_Com.minimal.arxml"
        src.write_bytes(ARXML_FIXTURE.read_bytes())
        out_html = tmp_path / "report.html"

        canned = [
            _FakeViolation(
                rule_id="R-X",
                severity="error",
                message="<script>alert('xss')</script>",
                path="<bad>",
                line=99,
            )
        ]
        _install_fake_lint(monkeypatch, canned)

        args = argparse.Namespace(
            path=src,
            output=out_html,
            rule=[],
            severity=None,
            project=".",
        )
        code = run(args)
        assert code == 0
        assert out_html.exists()
        html_text = out_html.read_text(encoding="utf-8")
        # 关键断言：raw <script> 不应作为可执行 tag 出现
        assert "<script>alert" not in html_text
        # 应当看到 escaped 版本
        assert "&lt;script&gt;alert" in html_text

    def test_run_lint_missing_file(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        args = argparse.Namespace(
            path=tmp_path / "nonexistent.arxml",
            output=None,
            rule=[],
            severity=None,
            project=".",
        )
        code = run(args)
        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.err.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "FileNotFoundError" in payload["error"]
