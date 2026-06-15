"""Sprint 8.E.1 Task B — ``cli/mcp_server.py`` error-path 补测。

目标（per ``plans/steady-covering-phoenix.md`` §1 / §2）：

* 补 ``mcp_server.py`` 118 missing → 目标 ≤ 60 missing（-50+）
* 目标 ≥ 50 new covered lines
* 不重复 ``test_mcp_server_coverage.py`` 已有的 happy + 早期 sad case
* 专注各 tool 的 error path + 入口 wrapper 分支

注：handler 函数都是模块顶层 ``def``（无闭包、无 ``async``），**直接 import
调**——比 monkeypatch ``@mcp.tool()`` 装饰器更稳定。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
import types
from typing import Any
from unittest import mock

import pytest

pytestmark = pytest.mark.autosar


# ---------------------------------------------------------------------------
# 模块级 autouse fixture：保存/恢复 mcp_server 全部 mutable 状态
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# 共享 fixtures
# ---------------------------------------------------------------------------


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
ARXML_FIXTURE = FIXTURES_DIR / "arxml" / "Com_Com.minimal.arxml"
XDM_FIXTURE = FIXTURES_DIR / "datamodel2" / "Can.xdm"


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
# arxml_validate — catch-all path
# ---------------------------------------------------------------------------


def test_arxml_validate_value_error_returns_error_dict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """lxml ValueError 走 catch-all Exception（line 609-610）。"""
    from claude_autosar.cli.mcp_server import arxml_validate
    from claude_autosar.core.bsw import arxml_io

    f = tmp_path / "x.arxml"
    f.write_text("<root/>", encoding="utf-8")

    def _raise_value(*_a: Any, **_kw: Any) -> None:
        raise ValueError("malformed structure")

    monkeypatch.setattr(arxml_io, "read", _raise_value)
    r = arxml_validate(str(f))
    assert r["success"] is False
    assert "ValueError" in r["error"]
    assert "malformed structure" in r["error"]


# ---------------------------------------------------------------------------
# dbc_parse — cantools 未装 / non-CAN database
# ---------------------------------------------------------------------------


def test_dbc_parse_cantools_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """cantools ImportError 路径（line 623-625）。"""
    from claude_autosar.cli import mcp_server

    # 让 ``import cantools`` 失败
    monkeypatch.setitem(sys.modules, "cantools", None)  # type: ignore[arg-type]
    r = mcp_server.dbc_parse("dummy.dbc")
    assert r["success"] is False
    assert "cantools not installed" in r["error"]


def test_dbc_parse_non_can_database(tmp_path: Path) -> None:
    """解析成功但 messages 属性不存在（line 635-636）。"""
    from claude_autosar.cli.mcp_server import dbc_parse

    class _FakeDiagDb:
        pass

    fake = _FakeDiagDb()
    fake_path = tmp_path / "any.dbc"
    fake_path.write_text("stub", encoding="utf-8")
    with mock.patch("cantools.database.load_file", return_value=fake):
        r = dbc_parse(str(fake_path))
    assert r["success"] is False
    assert "non-CAN database" in r["error"]


def test_dbc_parse_file_missing_returns_error(tmp_path: Path) -> None:
    """文件不存在（line 627-628）。"""
    from claude_autosar.cli.mcp_server import dbc_parse

    r = dbc_parse(str(tmp_path / "no_such.dbc"))
    assert r["success"] is False
    assert "file not found" in r["error"]


# ---------------------------------------------------------------------------
# session_show — SessionStoreError / happy
# ---------------------------------------------------------------------------


def test_session_show_session_store_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SessionStoreError 路径（line 695-696）。"""
    from claude_autosar.cli.mcp_server import session_show
    from claude_autosar.core.session.store import SessionStoreError

    monkeypatch.setattr("claude_autosar.cli.mcp_server._default_session_dir", lambda: tmp_path)

    def _raise_store(*_a: Any, **_kw: Any) -> None:
        raise SessionStoreError("corrupt jsonl")

    monkeypatch.setattr(
        "claude_autosar.core.session.store.SessionStore.read", _raise_store
    )
    r = session_show("s1", session_dir=str(tmp_path))
    assert r["success"] is False
    assert "corrupt jsonl" in r["error"]


def test_session_show_happy_with_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """happy path: 1 个 user entry → entries 序列化正确。"""
    from claude_autosar.cli.mcp_server import session_show
    from claude_autosar.core.session.store import SessionEntry, SessionStore

    monkeypatch.setattr("claude_autosar.cli.mcp_server._default_session_dir", lambda: tmp_path)
    store = SessionStore(dir=tmp_path)
    store.append(
        SessionEntry(
            id="e1",
            parent_id=None,
            session_id="s1",
            timestamp="2026-01-01T00:00:00+00:00",
            kind="user",
            content="hello",
        )
    )
    r = session_show("s1", session_dir=str(tmp_path))
    assert r["success"] is True
    assert r["session_id"] == "s1"
    assert len(r["entries"]) == 1
    assert r["entries"][0]["content"] == "hello"


# ---------------------------------------------------------------------------
# session_export — OSError / happy
# ---------------------------------------------------------------------------


def test_session_export_oserror_writing_html(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """export_html 抛 OSError（line 748-749）。"""
    from claude_autosar.cli.mcp_server import session_export
    from claude_autosar.core.session.store import SessionEntry, SessionStore

    monkeypatch.setattr("claude_autosar.cli.mcp_server._default_session_dir", lambda: tmp_path)
    store = SessionStore(dir=tmp_path)
    store.append(
        SessionEntry(
            id="e1",
            parent_id=None,
            session_id="s1",
            timestamp="2026-01-01T00:00:00+00:00",
            kind="user",
            content="hi",
        )
    )

    def _raise_os(*_a: Any, **_kw: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("claude_autosar.core.session.exporter.export_html", _raise_os)
    r = session_export("s1", fmt="html", session_dir=str(tmp_path))
    assert r["success"] is False
    assert "OSError" in r["error"]
    assert "disk full" in r["error"]


def test_session_export_session_store_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SessionStoreError from SessionTree.from_session_id（line 744-745）。"""
    from claude_autosar.cli.mcp_server import session_export
    from claude_autosar.core.session.store import SessionStoreError

    monkeypatch.setattr("claude_autosar.cli.mcp_server._default_session_dir", lambda: tmp_path)

    def _raise_store(*_a: Any, **_kw: Any) -> None:
        raise SessionStoreError("no such session")

    monkeypatch.setattr(
        "claude_autosar.core.session.tree.SessionTree.from_session_id", _raise_store
    )
    r = session_export("s1", fmt="html", session_dir=str(tmp_path))
    assert r["success"] is False
    assert "no such session" in r["error"]


# ---------------------------------------------------------------------------
# log_export — SessionStoreError / happy
# ---------------------------------------------------------------------------


def test_log_export_session_store_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """log_export SessionStoreError 路径（line 781-782）。"""
    from claude_autosar.cli.mcp_server import log_export
    from claude_autosar.core.session.store import SessionStoreError

    monkeypatch.setattr("claude_autosar.cli.mcp_server._default_session_dir", lambda: tmp_path)

    def _raise_store(*_a: Any, **_kw: Any) -> None:
        raise SessionStoreError("missing session")

    monkeypatch.setattr(
        "claude_autosar.core.session.tree.SessionTree.from_session_id", _raise_store
    )
    r = log_export("s1", session_dir=str(tmp_path))
    assert r["success"] is False
    assert "missing session" in r["error"]


def test_log_export_by_url_view(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """view='by-url' 走 render_by_url（line 784）。"""
    from claude_autosar.cli.mcp_server import log_export
    from claude_autosar.core.session.store import SessionEntry, SessionStore

    monkeypatch.setattr("claude_autosar.cli.mcp_server._default_session_dir", lambda: tmp_path)
    store = SessionStore(dir=tmp_path)
    store.append(
        SessionEntry(
            id="e1",
            parent_id=None,
            session_id="s1",
            timestamp="2026-01-01T00:00:00+00:00",
            kind="user",
            content="x",
        )
    )
    r = log_export("s1", view="by-url", session_dir=str(tmp_path))
    assert r["success"] is True
    assert r["view"] == "by-url"
    # by-url 渲染输出含 'URL' 字样（保守检查；避免硬编码中文）
    assert "URL" in r["text"] or "url" in r["text"].lower() or r["change_count"] == 0


# ---------------------------------------------------------------------------
# arxml_inspect / xdm_inspect / bsw_inspect — error path
# ---------------------------------------------------------------------------


def _copy_arxml_to_tmp(tmp_path: Path) -> Path:
    """把 ARXML fixture 复制到 tmp_path 并返回新路径（避免污染 fixture）。"""
    src = tmp_path / "Com_Com.minimal.arxml"
    src.write_bytes(ARXML_FIXTURE.read_bytes())
    return src


def test_arxml_inspect_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """project 不在 _ALLOWED_PROJECT_ROOTS → PermissionError（line 903-904）。"""
    from claude_autosar.cli.mcp_server import arxml_inspect

    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )
    r = arxml_inspect("/somewhere/else/Com_Com.minimal.arxml", project=".")
    assert r["success"] is False
    assert "PermissionError" in r["error"]


def test_arxml_inspect_file_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """path 文件不存在（line 905-906）。"""
    from claude_autosar.cli.mcp_server import arxml_inspect

    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )
    r = arxml_inspect(str(tmp_path / "missing.arxml"), project=str(tmp_path))
    assert r["success"] is False
    assert "FileNotFoundError" in r["error"]


def test_arxml_inspect_export_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """export_arxml_report 抛 OSError（line 911-912）。"""
    from claude_autosar.cli.mcp_server import arxml_inspect

    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )
    src = _copy_arxml_to_tmp(tmp_path)

    def _raise_os(*_a: Any, **_kw: Any) -> None:
        raise OSError("report write fail")

    monkeypatch.setattr(
        "claude_autosar.core.bsw.inspector.arxml_report.export_arxml_report", _raise_os
    )
    r = arxml_inspect(str(src), project=str(tmp_path))
    assert r["success"] is False
    assert "OSError" in r["error"]
    assert "report write fail" in r["error"]


def test_xdm_inspect_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """xdm_inspect path 防御（line 953-954）。"""
    from claude_autosar.cli.mcp_server import xdm_inspect

    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )
    r = xdm_inspect("/elsewhere/Can.xdm", project=".")
    assert r["success"] is False
    assert "PermissionError" in r["error"]


def test_xdm_inspect_file_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """xdm_inspect file not found（line 955-956）。"""
    from claude_autosar.cli.mcp_server import xdm_inspect

    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )
    r = xdm_inspect(str(tmp_path / "missing.xdm"), project=str(tmp_path))
    assert r["success"] is False
    assert "FileNotFoundError" in r["error"]


def test_xdm_inspect_export_value_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """xdm_inspect export 抛 ValueError（line 961-962）。"""
    from claude_autosar.cli.mcp_server import xdm_inspect

    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )
    src = tmp_path / "Can.xdm"
    src.write_bytes(XDM_FIXTURE.read_bytes())

    def _raise_value(*_a: Any, **_kw: Any) -> None:
        raise ValueError("bad xdm structure")

    monkeypatch.setattr(
        "claude_autosar.core.bsw.inspector.xdm_report.export_xdm_report", _raise_value
    )
    r = xdm_inspect(str(src), project=str(tmp_path))
    assert r["success"] is False
    assert "ValueError" in r["error"]
    assert "bad xdm structure" in r["error"]


def test_bsw_inspect_unknown_format(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """bsw_inspect detect_format UnknownFormatError（line 1015-1016）。"""
    from claude_autosar.cli.mcp_server import bsw_inspect
    from claude_autosar.core.bsw.dispatcher import UnknownFormatError

    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )
    src = tmp_path / "garbage.xdm"
    src.write_text("not real xml", encoding="utf-8")

    def _raise_unknown(*_a: Any, **_kw: Any) -> None:
        raise UnknownFormatError("cannot detect")

    monkeypatch.setattr(
        "claude_autosar.core.bsw.dispatcher.detect_format", _raise_unknown
    )
    r = bsw_inspect(str(src), project=str(tmp_path))
    assert r["success"] is False
    assert "UnknownFormatError" in r["error"]
    assert "cannot detect" in r["error"]


def test_bsw_inspect_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """bsw_inspect project 防御（line 1008-1009）。"""
    from claude_autosar.cli.mcp_server import bsw_inspect

    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )
    r = bsw_inspect("/elsewhere/Com_Com.minimal.arxml", project=".")
    assert r["success"] is False
    assert "PermissionError" in r["error"]


def test_bsw_inspect_file_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """bsw_inspect file not found（line 1010-1011）。"""
    from claude_autosar.cli.mcp_server import bsw_inspect

    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )
    r = bsw_inspect(str(tmp_path / "missing.arxml"), project=str(tmp_path))
    assert r["success"] is False
    assert "FileNotFoundError" in r["error"]


def test_bsw_inspect_dispatcher_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """bsw_inspect detect_format DispatcherError（line 1015-1016）。"""
    from claude_autosar.cli.mcp_server import bsw_inspect
    from claude_autosar.core.bsw.dispatcher import DispatcherError

    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )
    src = tmp_path / "garbage.xdm"
    src.write_text("<root/>", encoding="utf-8")

    def _raise_dispatch(*_a: Any, **_kw: Any) -> None:
        raise DispatcherError("dispatch broken")

    monkeypatch.setattr(
        "claude_autosar.core.bsw.dispatcher.detect_format", _raise_dispatch
    )
    r = bsw_inspect(str(src), project=str(tmp_path))
    assert r["success"] is False
    assert "DispatcherError" in r["error"]


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


# ---------------------------------------------------------------------------
# arxml_apply_template / xdm_apply_template — error path
# ---------------------------------------------------------------------------


def test_arxml_apply_template_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """project 不在 _ALLOWED_PROJECT_ROOTS → PermissionError（line 1092-1093）。"""
    from claude_autosar.cli.mcp_server import arxml_apply_template

    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )
    r = arxml_apply_template(
        "/elsewhere/curr.arxml", "/elsewhere/tpl.arxml", project="."
    )
    assert r["success"] is False
    assert "PermissionError" in r["error"]


def test_arxml_apply_template_src_file_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """src 文件不存在（line 1094-1095）。"""
    from claude_autosar.cli.mcp_server import arxml_apply_template

    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )
    tpl = _copy_arxml_to_tmp(tmp_path)
    r = arxml_apply_template(
        str(tmp_path / "missing.arxml"), str(tpl), project=str(tmp_path)
    )
    assert r["success"] is False
    assert "FileNotFoundError" in r["error"]


def test_arxml_apply_template_tpl_file_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """template 文件不存在（line 1098-1099）。"""
    from claude_autosar.cli.mcp_server import arxml_apply_template

    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )
    src = _copy_arxml_to_tmp(tmp_path)
    r = arxml_apply_template(
        str(src), str(tmp_path / "missing_tpl.arxml"), project=str(tmp_path)
    )
    assert r["success"] is False
    assert "FileNotFoundError" in r["error"]


def test_arxml_apply_template_no_module_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """current/template 都无 ECUC-MODULE-CONFIGURATION-VALUES → ValueError（line 1112-1115）。"""
    from claude_autosar.cli import mcp_server

    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )
    # 有 AUTOSAR namespace 但无 ECUC-MODULE-CONFIGURATION-VALUES
    src = tmp_path / "curr.arxml"
    src.write_text(
        '<?xml version="1.0"?><AUTOSAR xmlns="http://autosar.org/schema/r4.0">'
        "<AR-PACKAGES/></AUTOSAR>",
        encoding="utf-8",
    )
    tpl = tmp_path / "tpl.arxml"
    tpl.write_text(
        '<?xml version="1.0"?><AUTOSAR xmlns="http://autosar.org/schema/r4.0">'
        "<AR-PACKAGES/></AUTOSAR>",
        encoding="utf-8",
    )

    monkeypatch.setattr(mcp_server, "_detect_arxml_module_name", lambda _p: None)
    r = mcp_server.arxml_apply_template(str(src), str(tpl), project=str(tmp_path))
    assert r["success"] is False
    assert "no ECUC-MODULE-CONFIGURATION-VALUES" in r["error"]


def test_xdm_apply_template_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """xdm_apply_template project 防御（line 1193-1194）。"""
    from claude_autosar.cli.mcp_server import xdm_apply_template

    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )
    r = xdm_apply_template("/elsewhere/Can.xdm", "/elsewhere/tpl.xdm", project=".")
    assert r["success"] is False
    assert "PermissionError" in r["error"]


def test_xdm_apply_template_file_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """xdm_apply_template src 不存在（line 1195-1196）。"""
    from claude_autosar.cli.mcp_server import xdm_apply_template

    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )
    tpl = tmp_path / "tpl.xdm"
    tpl.write_bytes(XDM_FIXTURE.read_bytes())
    r = xdm_apply_template(
        str(tmp_path / "missing.xdm"), str(tpl), project=str(tmp_path)
    )
    assert r["success"] is False
    assert "FileNotFoundError" in r["error"]


def test_xdm_apply_template_tpl_file_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """xdm_apply_template tpl 不存在（line 1199-1200）。"""
    from claude_autosar.cli.mcp_server import xdm_apply_template

    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )
    src = tmp_path / "Can.xdm"
    src.write_bytes(XDM_FIXTURE.read_bytes())
    r = xdm_apply_template(
        str(src), str(tmp_path / "missing_tpl.xdm"), project=str(tmp_path)
    )
    assert r["success"] is False
    assert "FileNotFoundError" in r["error"]


# ---------------------------------------------------------------------------
# _detect_arxml_module_name / _detect_xdm_module_name — error path
# ---------------------------------------------------------------------------


def test_detect_arxml_module_name_missing_ar_namespace(tmp_path: Path) -> None:
    """没有 ar namespace → None（line 1267-1268）。"""
    from claude_autosar.cli.mcp_server import _detect_arxml_module_name

    f = tmp_path / "no_ns.arxml"
    f.write_text(
        '<?xml version="1.0"?><root xmlns:other="urn:x"><other:x/></root>',
        encoding="utf-8",
    )
    assert _detect_arxml_module_name(f) is None


def test_detect_arxml_module_name_no_modules(tmp_path: Path) -> None:
    """有 ar ns 但无 ECUC-MODULE-CONFIGURATION-VALUES → None（line 1277-1278）。"""
    from claude_autosar.cli.mcp_server import _detect_arxml_module_name

    f = tmp_path / "empty.arxml"
    f.write_text(
        """<?xml version="1.0"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES/>
</AUTOSAR>""",
        encoding="utf-8",
    )
    assert _detect_arxml_module_name(f) is None


def test_detect_arxml_module_name_no_shortname(tmp_path: Path) -> None:
    """module 存在但 SHORT-NAME 为空 → None（line 1282）。"""
    from claude_autosar.cli.mcp_server import _detect_arxml_module_name

    f = tmp_path / "no_shortname.arxml"
    f.write_text(
        """<?xml version="1.0"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>Ecuc</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-CONFIGURATION-VALUES>
        </ECUC-MODULE-CONFIGURATION-VALUES>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>""",
        encoding="utf-8",
    )
    assert _detect_arxml_module_name(f) is None


def test_detect_xdm_module_name_no_chc() -> None:
    """无 ``<d:chc type=AR-ELEMENT>`` → None（line 1295-1296）。"""
    from claude_autosar.cli.mcp_server import _detect_xdm_module_name

    class _FakeRoot:
        nsmap: dict[str, str] = {}

        def xpath(self, *_a: Any, **_kw: Any) -> list[Any]:
            return []

    class _FakeTree:
        def __init__(self) -> None:
            self.tree = _FakeRoot()

    assert _detect_xdm_module_name(_FakeTree()) is None


def test_detect_xdm_module_name_attribute_error() -> None:
    """loaded_doc 无 .tree 属性 → None（line 1288-1294 except 路径）。"""
    from claude_autosar.cli.mcp_server import _detect_xdm_module_name

    class _BadDoc:
        pass

    assert _detect_xdm_module_name(_BadDoc()) is None


# ---------------------------------------------------------------------------
# _apply_result_to_dict — dataclass / 非 dataclass / TypeError
# ---------------------------------------------------------------------------


def test_apply_result_to_dict_dataclass() -> None:
    """dataclass → asdict 路径（line 1306-1307）。"""
    from claude_autosar.cli.mcp_server import _apply_result_to_dict

    @dataclass
    class _R:
        a: int = 1
        b: str = "x"

    out = _apply_result_to_dict(_R())
    assert out == {"a": 1, "b": "x"}


def test_apply_result_to_dict_plain_object() -> None:
    """非 dataclass 普通对象 → vars() 路径（line 1310-1311）。"""
    from claude_autosar.cli.mcp_server import _apply_result_to_dict

    class _Plain:
        def __init__(self) -> None:
            self.alpha = 1
            self.beta = "y"

    out = _apply_result_to_dict(_Plain())
    assert out == {"alpha": 1, "beta": "y"}


def test_apply_result_to_dict_no_vars() -> None:
    """无 __dict__ → 返 {}（line 1312-1313）。"""
    from claude_autosar.cli.mcp_server import _apply_result_to_dict

    class _NoVars:
        __slots__ = ("a",)

        def __init__(self) -> None:
            self.a = 1

    out = _apply_result_to_dict(_NoVars())
    # slots 对象 vars() 抛 TypeError → fallback 返 {}
    assert out == {}


# ---------------------------------------------------------------------------
# _inspect_resolve_input — error path
# ---------------------------------------------------------------------------


def test_inspect_resolve_input_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """project 不在 _ALLOWED_PROJECT_ROOTS → PermissionError（line 815）。"""
    from claude_autosar.cli.mcp_server import _inspect_resolve_input

    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )
    with pytest.raises(PermissionError):
        _inspect_resolve_input("/anywhere/x.arxml", project=".")


def test_inspect_resolve_input_file_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """path 不存在 → FileNotFoundError（line 818）。"""
    from claude_autosar.cli.mcp_server import _inspect_resolve_input

    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )
    with pytest.raises(FileNotFoundError):
        _inspect_resolve_input(str(tmp_path / "missing.arxml"), project=str(tmp_path))


def test_inspect_resolve_input_happy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """happy path 返 resolved Path（line 819）。"""
    from claude_autosar.cli.mcp_server import _inspect_resolve_input

    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )
    f = tmp_path / "x.arxml"
    f.write_text("<root/>", encoding="utf-8")
    result = _inspect_resolve_input(str(f), project=str(tmp_path))
    assert result == f.resolve()
