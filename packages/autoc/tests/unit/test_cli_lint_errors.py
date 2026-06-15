"""Sprint 8.E.1 — coverage backfill for ``cli/commands/lint.py``.

Plan reference: Sprint 8.E.1 Task A — rank 10 CLI command error path coverage.

Targets (see ``plan/steady-covering-phoenix.md`` §1):
  - ``cli/commands/lint.py`` (26 missing → cover error paths):
    ``run`` 错误路径（detect_format / extract / LintRunner / HTML 写盘失败）,
    ``_filter_violations`` 边界, ``_violation_to_dict`` / ``_summary_to_dict``
    工具, ``_try_extract`` error 路径。

**禁 令**:
- 不改产品代码
- 不 git commit
- 不引入新 pip 依赖
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Any

import pytest

from claude_autosar.cli.commands import lint as lint_mod

pytestmark = pytest.mark.autosar


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
ARXML_FIXTURE = FIXTURES_DIR / "arxml" / "Com_Com.minimal.arxml"


# ---------------------------------------------------------------------------
# Fake lint framework (mirrors test_cli_lint.py)
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
        self,
        rules: tuple[Any, ...] = (),
        *,
        canned: list[_FakeViolation] | None = None,
        raise_on_run: BaseException | None = None,
    ) -> None:
        self.rules = rules
        self._canned = canned if canned is not None else []
        self._raise_on_run = raise_on_run

    def run(self, _extracted: Any) -> list[_FakeViolation]:
        if self._raise_on_run is not None:
            raise self._raise_on_run
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
    raise_on_run: BaseException | None = None,
    extract_returns: Any = "arxml-stub",
    extract_raises: BaseException | None = None,
    runner_factory: Any | None = None,
) -> None:
    """Inject fake ``claude_autosar.core.bsw.lint`` + 子模块到 sys.modules。"""
    fake_lint = ModuleType("claude_autosar.core.bsw.lint")
    fake_lint.LintViolation = _FakeViolation  # type: ignore[attr-defined]
    fake_lint.LintSummary = _FakeSummary  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "claude_autosar.core.bsw.lint", fake_lint)

    fake_rules = ModuleType("claude_autosar.core.bsw.lint.rules")
    fake_rules.ALL_RULES = (object(),)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "claude_autosar.core.bsw.lint.rules", fake_rules)

    fake_extract = ModuleType("claude_autosar.core.bsw.lint.extract")

    if extract_raises is not None:

        def _raise_extract(_p: Any) -> Any:
            raise extract_raises

        fake_extract.extract_arxml_for_lint = _raise_extract  # type: ignore[attr-defined]
        fake_extract.extract_xdm_for_lint = _raise_extract  # type: ignore[attr-defined]
    else:
        fake_extract.extract_arxml_for_lint = lambda _p: extract_returns  # type: ignore[attr-defined]
        fake_extract.extract_xdm_for_lint = lambda _p: extract_returns  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "claude_autosar.core.bsw.lint.extract", fake_extract)

    if runner_factory is not None:
        fake_lint.LintRunner = runner_factory  # type: ignore[attr-defined]
    else:

        def _factory(rules: tuple[Any, ...] = ()) -> _FakeRunner:
            return _FakeRunner(
                rules=rules,
                canned=canned if canned is not None else [],
                raise_on_run=raise_on_run,
            )

        fake_lint.LintRunner = _factory  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# _filter_violations helper
# ---------------------------------------------------------------------------


class TestFilterViolations:
    def test_no_filter_returns_all(self) -> None:
        vs = [
            _FakeViolation("R1", "error", "m1"),
            _FakeViolation("R2", "warning", "m2"),
            _FakeViolation("R3", "info", "m3"),
        ]
        out = lint_mod._filter_violations(vs, rules=[], severity=None)
        assert out == vs

    def test_rule_filter(self) -> None:
        vs = [
            _FakeViolation("R1", "error", "m1"),
            _FakeViolation("R2", "warning", "m2"),
        ]
        out = lint_mod._filter_violations(vs, rules=["R1"], severity=None)
        assert len(out) == 1
        assert out[0].rule_id == "R1"

    def test_severity_filter(self) -> None:
        vs = [
            _FakeViolation("R1", "error", "m1"),
            _FakeViolation("R2", "warning", "m2"),
        ]
        out = lint_mod._filter_violations(vs, rules=[], severity="ERROR")
        # 大小写不敏感
        assert len(out) == 1
        assert out[0].severity == "error"

    def test_combined_filter(self) -> None:
        vs = [
            _FakeViolation("R1", "error", "m1"),
            _FakeViolation("R1", "warning", "m2"),
            _FakeViolation("R2", "error", "m3"),
        ]
        out = lint_mod._filter_violations(vs, rules=["R1"], severity="error")
        assert len(out) == 1
        assert out[0].message == "m1"

    def test_empty_violations(self) -> None:
        out = lint_mod._filter_violations([], rules=["R1"], severity="error")
        assert out == []


# ---------------------------------------------------------------------------
# _violation_to_dict / _summary_to_dict
# ---------------------------------------------------------------------------


class TestViolationToDict:
    def test_serializes_all_fields(self) -> None:
        v = _FakeViolation("R-1", "error", "msg", path="X/Y", line=42)
        d = lint_mod._violation_to_dict(v)
        assert d["rule_id"] == "R-1"
        assert d["severity"] == "error"
        assert d["message"] == "msg"
        assert d["path"] == "X/Y"
        assert d["line"] == 42

    def test_handles_empty_path(self) -> None:
        v = _FakeViolation("R-1", "info", "msg", path="")
        d = lint_mod._violation_to_dict(v)
        assert d["path"] == ""


class TestSummaryToDict:
    def test_none_returns_empty(self) -> None:
        d = lint_mod._summary_to_dict(None)
        assert d == {"total": 0, "by_severity": {}}

    def test_serializes_summary(self) -> None:
        s = _FakeSummary(total=3, by_severity={"error": 1, "warning": 2})
        d = lint_mod._summary_to_dict(s)
        assert d["total"] == 3
        assert d["by_severity"] == {"error": 1, "warning": 2}


# ---------------------------------------------------------------------------
# _try_extract helper
# ---------------------------------------------------------------------------


class TestTryExtract:
    def test_returns_none_when_extract_raises_value_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """extract 抛 ValueError → 返 None。"""
        # build fake extract module that raises
        fake_extract = ModuleType("claude_autosar.core.bsw.lint.extract")

        def _raise(_p: Any) -> Any:
            raise ValueError("bad parse")

        fake_extract.extract_arxml_for_lint = _raise  # type: ignore[attr-defined]
        fake_extract.extract_xdm_for_lint = _raise  # type: ignore[attr-defined]
        monkeypatch.setitem(
            sys.modules, "claude_autosar.core.bsw.lint.extract", fake_extract
        )

        result = lint_mod._try_extract(Path("/tmp/x.arxml"), "arxml")
        assert result is None

    def test_returns_none_when_extract_raises_os_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """extract 抛 OSError → 返 None。"""
        fake_extract = ModuleType("claude_autosar.core.bsw.lint.extract")

        def _raise(_p: Any) -> Any:
            raise OSError("io error")

        fake_extract.extract_arxml_for_lint = _raise  # type: ignore[attr-defined]
        fake_extract.extract_xdm_for_lint = _raise  # type: ignore[attr-defined]
        monkeypatch.setitem(
            sys.modules, "claude_autosar.core.bsw.lint.extract", fake_extract
        )

        result = lint_mod._try_extract(Path("/tmp/x.arxml"), "arxml")
        assert result is None

    def test_returns_value_on_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """inject fake extract 模块返 stub → _try_extract 返 stub。"""
        fake_extract = ModuleType("claude_autosar.core.bsw.lint.extract")
        fake_extract.extract_arxml_for_lint = lambda _p: "arxml-stub"  # type: ignore[attr-defined]
        fake_extract.extract_xdm_for_lint = lambda _p: "xdm-stub"  # type: ignore[attr-defined]
        monkeypatch.setitem(
            sys.modules, "claude_autosar.core.bsw.lint.extract", fake_extract
        )
        result = lint_mod._try_extract(Path("/tmp/x.arxml"), "arxml")
        assert result == "arxml-stub"

    def test_dispatches_to_xdm_when_fmt_xdm(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_extract = ModuleType("claude_autosar.core.bsw.lint.extract")
        fake_extract.extract_arxml_for_lint = lambda _p: "arxml-stub"  # type: ignore[attr-defined]
        fake_extract.extract_xdm_for_lint = lambda _p: "xdm-stub"  # type: ignore[attr-defined]
        monkeypatch.setitem(
            sys.modules, "claude_autosar.core.bsw.lint.extract", fake_extract
        )
        result = lint_mod._try_extract(Path("/tmp/x.xdm"), "xdm")
        assert result == "xdm-stub"


# ---------------------------------------------------------------------------
# run() — error paths
# ---------------------------------------------------------------------------


class TestRunErrorPaths:
    def test_missing_file_returns_1(
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
        code = lint_mod.run(args)
        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.err.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "FileNotFoundError" in payload["error"]

    def test_dispatch_os_error_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """dispatcher.detect_format 抛 OSError → exit 1。"""
        from claude_autosar.core.bsw import dispatcher

        src = tmp_path / "x.arxml"
        src.write_bytes(ARXML_FIXTURE.read_bytes())

        def _raise(_p: Any) -> Any:
            raise OSError("disk error")

        monkeypatch.setattr(dispatcher, "detect_format", _raise)

        args = argparse.Namespace(
            path=src,
            output=None,
            rule=[],
            severity=None,
            project=".",
        )
        code = lint_mod.run(args)
        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.err.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "OSError" in payload["error"]

    def test_dispatch_value_error_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """dispatcher.detect_format 抛 ValueError → exit 1。"""
        from claude_autosar.core.bsw import dispatcher

        src = tmp_path / "x.arxml"
        src.write_bytes(ARXML_FIXTURE.read_bytes())

        def _raise(_p: Any) -> Any:
            raise ValueError("bad format")

        monkeypatch.setattr(dispatcher, "detect_format", _raise)

        args = argparse.Namespace(
            path=src,
            output=None,
            rule=[],
            severity=None,
            project=".",
        )
        code = lint_mod.run(args)
        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.err.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "ValueError" in payload["error"]

    def test_extract_returns_none_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """_try_extract 返 None → exit 1。"""
        src = tmp_path / "x.arxml"
        src.write_bytes(ARXML_FIXTURE.read_bytes())
        _install_fake_lint(monkeypatch, canned=[], extract_raises=ValueError("parse"))

        args = argparse.Namespace(
            path=src,
            output=None,
            rule=[],
            severity=None,
            project=".",
        )
        code = lint_mod.run(args)
        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.err.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "extract failed" in payload["error"]

    def test_runner_raises_value_error_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """LintRunner.run 抛 ValueError → exit 1。"""
        src = tmp_path / "x.arxml"
        src.write_bytes(ARXML_FIXTURE.read_bytes())
        _install_fake_lint(
            monkeypatch, canned=[], raise_on_run=ValueError("lint crashed")
        )

        args = argparse.Namespace(
            path=src,
            output=None,
            rule=[],
            severity=None,
            project=".",
        )
        code = lint_mod.run(args)
        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.err.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "ValueError" in payload["error"]

    def test_runner_raises_os_error_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """LintRunner.run 抛 OSError → exit 1。"""
        src = tmp_path / "x.arxml"
        src.write_bytes(ARXML_FIXTURE.read_bytes())
        _install_fake_lint(
            monkeypatch, canned=[], raise_on_run=OSError("disk fail")
        )

        args = argparse.Namespace(
            path=src,
            output=None,
            rule=[],
            severity=None,
            project=".",
        )
        code = lint_mod.run(args)
        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.err.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "OSError" in payload["error"]

    def test_html_output_os_error_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--output 写盘失败 → exit 1。"""
        src = tmp_path / "x.arxml"
        src.write_bytes(ARXML_FIXTURE.read_bytes())
        out_html = tmp_path / "report.html"

        canned = [
            _FakeViolation("R-1", "error", "m1", path="X", line=1),
        ]
        _install_fake_lint(monkeypatch, canned=canned)

        # patch Path.write_text to raise
        orig_write_text = Path.write_text

        def _raise_write(self: Path, *args: Any, **kwargs: Any) -> Any:  # noqa: ARG001
            if self.name == "report.html":
                raise OSError("permission denied")
            return orig_write_text(self, *args, **kwargs)

        monkeypatch.setattr(Path, "write_text", _raise_write)

        args = argparse.Namespace(
            path=src,
            output=out_html,
            rule=[],
            severity=None,
            project=".",
        )
        code = lint_mod.run(args)
        captured = capsys.readouterr()
        assert code == 1
        payload = json.loads(captured.err.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "HTML export failed" in payload["error"]

    def test_html_output_arxml_writes_report(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--output + arxml → 写 HTML 报告。"""
        src = tmp_path / "x.arxml"
        src.write_bytes(ARXML_FIXTURE.read_bytes())
        out_html = tmp_path / "report.html"

        canned = [
            _FakeViolation("R-1", "error", "m1", path="X", line=1),
        ]
        _install_fake_lint(monkeypatch, canned=canned)

        args = argparse.Namespace(
            path=src,
            output=out_html,
            rule=[],
            severity=None,
            project=".",
        )
        code = lint_mod.run(args)
        captured = capsys.readouterr()
        assert code == 0
        assert out_html.exists()
        payload = json.loads(captured.out.strip().splitlines()[-1])
        assert payload["success"] is True

    def test_html_output_xdm_writes_report(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--output + xdm 格式 → 走 xdm_report 分支。"""
        from claude_autosar.core.bsw import dispatcher

        src = tmp_path / "x.xdm"
        src.write_bytes(b"<?xml version='1.0'?><root/>")
        out_html = tmp_path / "report.html"

        canned = [
            _FakeViolation("R-1", "error", "m1", path="X", line=1),
        ]
        _install_fake_lint(monkeypatch, canned=canned, extract_returns="xdm-stub")

        # patch detect_format → xdm
        monkeypatch.setattr(dispatcher, "detect_format", lambda _p: "xdm")

        args = argparse.Namespace(
            path=src,
            output=out_html,
            rule=[],
            severity=None,
            project=".",
        )
        code = lint_mod.run(args)
        captured = capsys.readouterr()
        assert code == 0
        assert out_html.exists()
        payload = json.loads(captured.out.strip().splitlines()[-1])
        assert payload["format"] == "xdm"


# ---------------------------------------------------------------------------
# Lint 框架不可用分支（与 test_cli_lint.py 一致；再覆盖一次以确保统计）
# ---------------------------------------------------------------------------


class TestLintUnavailableBranch:
    def test_lint_unavailable_returns_flag(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        src = tmp_path / "x.arxml"
        src.write_bytes(ARXML_FIXTURE.read_bytes())

        # 强制 _try_import_lint 返 (None, None, None)
        monkeypatch.setattr(lint_mod, "_try_import_lint", lambda: (None, None, None))

        args = argparse.Namespace(
            path=src,
            output=None,
            rule=[],
            severity=None,
            project=".",
        )
        code = lint_mod.run(args)
        captured = capsys.readouterr()
        assert code == 0
        payload = json.loads(captured.out.strip().splitlines()[-1])
        assert payload["success"] is True
        assert payload["lint_unavailable"] is True


# ---------------------------------------------------------------------------
# rule_id 过滤
# ---------------------------------------------------------------------------


class TestRunRuleIdFilter:
    def test_run_lint_rule_id_filter(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        src = tmp_path / "x.arxml"
        src.write_bytes(ARXML_FIXTURE.read_bytes())

        canned = [
            _FakeViolation("R-A", "error", "a", path="", line=1),
            _FakeViolation("R-B", "warning", "b", path="", line=2),
            _FakeViolation("R-A", "error", "a2", path="", line=3),
        ]
        _install_fake_lint(monkeypatch, canned=canned)

        args = argparse.Namespace(
            path=src,
            output=None,
            rule=["R-A"],
            severity=None,
            project=".",
        )
        lint_mod.run(args)
        captured = capsys.readouterr()
        payload = json.loads(captured.out.strip().splitlines()[-1])
        assert payload["summary"]["total"] == 2
        assert all(v["rule_id"] == "R-A" for v in payload["violations"])


# ---------------------------------------------------------------------------
# 测试模块自身 — 模块表面（register / run / build_parser）
# ---------------------------------------------------------------------------


class TestModuleSurface:
    def test_module_has_register_and_run(self) -> None:
        assert callable(getattr(lint_mod, "register", None))
        assert callable(getattr(lint_mod, "run", None))

    def test_module_has_build_parser(self) -> None:
        assert callable(getattr(lint_mod, "build_parser", None))
