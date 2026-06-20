"""bsw_read / bsw_write / bsw_verify / bsw_autocalc 覆盖测试 + _run_lint_for_inspect helpers。

从 ``test_mcp_server_extra_coverage.py`` 拆分而来。
"""

from __future__ import annotations

from pathlib import Path
import sys
import types
from typing import Any
from unittest import mock

import pytest

pytestmark = pytest.mark.autosar

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
ARXML_FIXTURE = FIXTURES_DIR / "arxml" / "Com_Com.minimal.arxml"


@pytest.fixture(autouse=True)
def _snapshot_mcp_server_globals() -> Any:
    """每个 test 后还原 _ALLOWED_PROJECT_ROOTS / _default_session_dir。"""
    from claude_autosar.cli import mcp_server

    original_roots = mcp_server._ALLOWED_PROJECT_ROOTS
    original_default_dir = mcp_server._default_session_dir
    original_tresos_home = mcp_server._default_tresos_home
    yield
    mcp_server._ALLOWED_PROJECT_ROOTS = original_roots
    mcp_server._default_session_dir = original_default_dir
    mcp_server._default_tresos_home = original_tresos_home


@pytest.fixture
def fake_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """最小 EB 工程（XDM ECUC 结构 + tresos_home）+ 限定 _ALLOWED_PROJECT_ROOTS。"""
    project = tmp_path / "proj"
    project.mkdir(parents=True, exist_ok=True)
    (project / "Mcu.xdm").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>Ecuc</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-CONFIGURATION-VALUES>
          <SHORT-NAME>Mcu</SHORT-NAME>
          <DEFINITION-REF DEST="ECUC-MODULE-DEF">/AUTOSAR/EcucDefs/Mcu/Mcu</DEFINITION-REF>
          <PARAMETER-VALUES>
            <ECUC-NUMERICAL-PARAM-VALUE>
              <DEFINITION-REF DEST="ECUC-INTEGER-PARAM-DEF">/Mcu/ClockFreq</DEFINITION-REF>
              <VALUE>80000000</VALUE>
            </ECUC-NUMERICAL-PARAM-VALUE>
          </PARAMETER-VALUES>
        </ECUC-MODULE-CONFIGURATION-VALUES>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
""",
        encoding="utf-8",
    )
    (project / "tresos_home").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )
    return project


# ---------------------------------------------------------------------------
# bsw_read — error path（format 探测、load_module 失败）
# ---------------------------------------------------------------------------


def test_bsw_read_unknown_format_on_garbage_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """UnknownFormatError 路径：根 namespace 解析失败（line 160-165）。"""
    from claude_autosar.cli.mcp_server import bsw_read
    from claude_autosar.core.bsw.dispatcher import UnknownFormatError

    project = tmp_path / "proj"
    project.mkdir()
    # 写一个让 detect_format 无法识别 namespace 的文件
    (project / "Mcu.xdm").write_text("<?xml version='1.0'?><not-autosar/>", encoding="utf-8")
    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )

    def _raise_unknown(*_a: Any, **_kw: Any) -> None:
        raise UnknownFormatError("root namespace not recognized")

    monkeypatch.setattr(
        "claude_autosar.core.bsw.dispatcher.detect_format", _raise_unknown
    )
    r = bsw_read("Mcu", "X", project=str(project))
    assert r["success"] is False
    assert "root namespace" in r["error"]


def test_bsw_read_dispatcher_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """DispatcherError 路径（line 162-163）。"""
    from claude_autosar.cli.mcp_server import bsw_read
    from claude_autosar.core.bsw.dispatcher import DispatcherError

    project = tmp_path / "proj"
    project.mkdir()
    (project / "Mcu.xdm").write_text("<root/>", encoding="utf-8")
    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )

    def _raise_dispatch(*_a: Any, **_kw: Any) -> None:
        raise DispatcherError("dispatcher boom")

    monkeypatch.setattr(
        "claude_autosar.core.bsw.dispatcher.detect_format", _raise_dispatch
    )
    r = bsw_read("Mcu", "X", project=str(project))
    assert r["success"] is False
    assert "DispatcherError" in r["error"]
    assert "dispatcher boom" in r["error"]


def test_bsw_read_detect_format_os_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OSError/FileNotFoundError 路径（line 164-165）。"""
    from claude_autosar.cli.mcp_server import bsw_read

    project = tmp_path / "proj"
    project.mkdir()
    (project / "Mcu.xdm").write_text("<root/>", encoding="utf-8")
    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )

    def _raise_os(*_a: Any, **_kw: Any) -> None:
        raise OSError("disk gone")

    monkeypatch.setattr("claude_autosar.core.bsw.dispatcher.detect_format", _raise_os)
    r = bsw_read("Mcu", "X", project=str(project))
    assert r["success"] is False
    assert "OSError" in r["error"]
    assert "disk gone" in r["error"]


def test_bsw_read_load_module_value_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """load_module ValueError 路径（line 172-173）。"""
    from claude_autosar.cli.mcp_server import bsw_read

    project = tmp_path / "proj"
    project.mkdir()
    arxml = project / "Mcu.arxml"
    arxml.write_text(ARXML_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )

    def _raise_value(*_a: Any, **_kw: Any) -> None:
        raise ValueError("module not in document")

    monkeypatch.setattr("claude_autosar.core.bsw.ecuc.load_module", _raise_value)
    r = bsw_read("Mcu", "X", project=str(project))
    assert r["success"] is False
    assert "ValueError" in r["error"]
    assert "module not in document" in r["error"]


def test_bsw_read_load_module_file_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """load_module FileNotFoundError 路径。"""
    from claude_autosar.cli.mcp_server import bsw_read

    project = tmp_path / "proj"
    project.mkdir()
    (project / "Mcu.arxml").write_text(ARXML_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )

    def _raise_fnf(*_a: Any, **_kw: Any) -> None:
        raise FileNotFoundError("missing inner ref")

    monkeypatch.setattr("claude_autosar.core.bsw.ecuc.load_module", _raise_fnf)
    r = bsw_read("Mcu", "X", project=str(project))
    assert r["success"] is False
    assert "FileNotFoundError" in r["error"]


# ---------------------------------------------------------------------------
# bsw_write — ParamType ValueError / modify_and_verify exception
# ---------------------------------------------------------------------------


def test_bsw_write_rejects_invalid_param_type(
    fake_project: Path,
) -> None:
    """ParamType 枚举校验失败（line 369-381）→ param_index + field 标定。"""
    from claude_autosar.cli.mcp_server import bsw_write

    # 跳过 schema 前置校验 — 注：type="bogus" 实际会被拒绝
    r = bsw_write(
        "Mcu",
        [{"path": "Mcu/ClockFreq", "value": 1, "type": "bogus_type"}],
        project=str(fake_project),
    )
    assert r["success"] is False
    assert r["param_index"] == 0
    assert r["field"] == "type"
    assert "is not a valid ParamType" in r["error"]


def test_bsw_write_propagates_oserror_from_modify(
    fake_project: Path,
) -> None:
    """modify_and_verify 抛 OSError → (OSError, ValueError, TypeError, KeyError) 分支（line 425-426）。"""
    from claude_autosar.cli.mcp_server import bsw_write

    def _raise_os(*_a: Any, **_kw: Any) -> None:
        raise OSError("tresos disk full")

    with mock.patch(
        "claude_autosar.core.bsw.validator.modify_and_verify",
        side_effect=_raise_os,
    ):
        r = bsw_write(
            "Mcu",
            [{"path": "Mcu/ClockFreq", "value": 1, "type": "integer"}],
            project=str(fake_project),
        )
    assert r["success"] is False
    assert "OSError" in r["error"]
    assert "tresos disk full" in r["error"]


def test_bsw_write_propagates_keyerror_from_modify(
    fake_project: Path,
) -> None:
    """modify_and_verify 抛 KeyError → (..., KeyError) 分支。"""
    from claude_autosar.cli.mcp_server import bsw_write

    def _raise_ke(*_a: Any, **_kw: Any) -> None:
        raise KeyError("missing param")

    with mock.patch(
        "claude_autosar.core.bsw.validator.modify_and_verify",
        side_effect=_raise_ke,
    ):
        r = bsw_write(
            "Mcu",
            [{"path": "Mcu/ClockFreq", "value": 1, "type": "integer"}],
            project=str(fake_project),
        )
    assert r["success"] is False
    assert "KeyError" in r["error"]


# ---------------------------------------------------------------------------
# bsw_verify — path-defense / tresos_home 校验 / v2 path loader
# ---------------------------------------------------------------------------


def test_bsw_verify_rejects_tresos_home_outside_project(
    fake_project: Path,
) -> None:
    """tresos_home 防御（line 483-486）→ field='tresos_home'。"""
    from claude_autosar.cli.mcp_server import bsw_verify

    r = bsw_verify("Mcu", project=str(fake_project), tresos_home="/some/where/else")
    assert r["success"] is False
    assert r.get("field") == "tresos_home"
    assert r.get("param_index") == -1
    assert "tresos_home must be inside" in r["error"]


def test_bsw_verify_as_json_returns_full_report(
    fake_project: Path,
) -> None:
    """as_json=True → 完整 report dict（line 525-538）。"""
    from claude_autosar.cli.mcp_server import bsw_verify

    fake = mock.Mock(success=True, returncode=0, stdout="", stderr="")
    with mock.patch("claude_autosar.adapters.tresos.TresosAdapter.verify", return_value=fake):
        r = bsw_verify("Mcu", project=str(fake_project), as_json=True)
    assert r["success"] is True
    # 完整 report 含 issues / has_errors / has_warnings
    assert "report" in r
    assert "issues" in r["report"]
    assert "has_errors" in r["report"]
    assert "has_warnings" in r["report"]
    # v2_paths 即使 loader 失败也应是空 dict（line 513-515 except 路径）
    assert "v2_paths" in r


def test_bsw_verify_v2_paths_loader_raises_keeps_report(
    fake_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """load_v2_paths 抛异常时 verify 主流程不被打断（line 513-515）。"""
    from claude_autosar.cli.mcp_server import bsw_verify

    fake = mock.Mock(success=True, returncode=0, stdout="", stderr="")
    with mock.patch("claude_autosar.adapters.tresos.TresosAdapter.verify", return_value=fake):

        def _raise_v2(*_a: Any, **_kw: Any) -> None:
            raise RuntimeError("v2 paths broken")

        monkeypatch.setattr(
            "claude_autosar.core.settings.v2_paths.load_v2_paths", _raise_v2
        )
        r = bsw_verify("Mcu", project=str(fake_project))
    assert r["success"] is True
    # v2_paths 留空 dict（except 路径）
    assert r["v2_paths"] == {}


# ---------------------------------------------------------------------------
# bsw_autocalc — tresos_home 防御
# ---------------------------------------------------------------------------


def test_bsw_autocalc_rejects_tresos_home_outside_project(fake_project: Path) -> None:
    """tresos_home 防御（line 573-576）→ field='tresos_home'。"""
    from claude_autosar.cli.mcp_server import bsw_autocalc

    r = bsw_autocalc(["Mcu"], project=str(fake_project), tresos_home="/elsewhere")
    assert r["success"] is False
    assert r.get("field") == "tresos_home"


# ---------------------------------------------------------------------------
# _run_lint_for_inspect — 错误路径（ImportError / OSError / 各种异常）
# ---------------------------------------------------------------------------


def test_run_lint_for_inspect_import_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """LintRunner 不可用 → 返 None（line 832-833）。

    需同时 fake lint.extract，否则第二个 try 块里 extract_arxml_for_lint 会跑
    真实逻辑（即便 lint 本身被 fake 了；fake 只影响 ``from lint import
    LintRunner`` 的 look-up，extract 是单独 import）。
    """
    from claude_autosar.cli import mcp_server

    # fake lint + lint.rules（LintRunner 不可用 → ImportError 路径）
    fake_lint = types.ModuleType("claude_autosar.core.bsw.lint")
    fake_rules = types.ModuleType("claude_autosar.core.bsw.lint.rules")

    class _Boom:
        def __getattr__(self, name: str) -> None:
            raise ImportError(f"lint boom: {name}")

    fake_lint.LintRunner = _Boom()  # type: ignore[attr-defined]

    def _rules_boom(*_a: Any, **_kw: Any) -> Any:
        raise ImportError("rules broken")

    fake_rules.rules_for_namespace = _rules_boom  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "claude_autosar.core.bsw.lint", fake_lint)
    monkeypatch.setitem(sys.modules, "claude_autosar.core.bsw.lint.rules", fake_rules)

    # fake extract（让 extract_arxml_for_lint 抛 ImportError）— 必须，否则
    # 第二个 try 块先跑真实 extract，对坏 .arxml 抛 ARXMLError（不在 catch 列表）
    fake_extract = types.ModuleType("claude_autosar.core.bsw.lint.extract")

    def _extract_boom(*_a: Any, **_kw: Any) -> None:
        raise ImportError("extract boom")

    fake_extract.extract_arxml_for_lint = _extract_boom  # type: ignore[attr-defined]
    fake_extract.extract_xdm_for_lint = _extract_boom  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "claude_autosar.core.bsw.lint.extract", fake_extract)

    src = tmp_path / "x.arxml"
    src.write_text("<root/>", encoding="utf-8")
    result = mcp_server._run_lint_for_inspect(src, "arxml")
    assert result is None


def test_run_lint_for_inspect_extract_import_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """extract 模块 ImportError → 返 None（line 848）。"""
    from claude_autosar.cli import mcp_server

    fake_extract = types.ModuleType("claude_autosar.core.bsw.lint.extract")

    def _boom(*_a: Any, **_kw: Any) -> None:
        raise ImportError("extract module not ready")

    fake_extract.extract_arxml_for_lint = _boom  # type: ignore[attr-defined]
    fake_extract.extract_xdm_for_lint = _boom  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "claude_autosar.core.bsw.lint.extract", fake_extract)

    src = tmp_path / "x.arxml"
    src.write_text("<root/>", encoding="utf-8")
    result = mcp_server._run_lint_for_inspect(src, "arxml")
    assert result is None


def test_run_lint_for_inspect_runner_attribute_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """runner.run() 抛 AttributeError → 返 None（line 857-858）。"""
    from claude_autosar.cli import mcp_server

    class _BrokenRunner:
        def run(self, _extracted: Any) -> Any:
            raise AttributeError("missing attribute")

        def summarize(self, _vs: Any) -> Any:
            return None

    monkeypatch.setattr(
        "claude_autosar.core.bsw.lint.LintRunner", _BrokenRunner, raising=False
    )

    def _stub_extract(_path: Any) -> Any:
        return {"stub": "data"}

    monkeypatch.setattr(
        "claude_autosar.core.bsw.lint.extract.extract_arxml_for_lint",
        _stub_extract,
        raising=False,
    )

    src = tmp_path / "x.arxml"
    src.write_text("<root/>", encoding="utf-8")
    result = mcp_server._run_lint_for_inspect(src, "arxml")
    assert result is None
