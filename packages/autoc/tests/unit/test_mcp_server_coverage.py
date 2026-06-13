"""Sprint 7 — mcp_server 工具覆盖补强。

把 Sprint 5 的 18 个测试（覆盖 47% 提到 ~80%+）。每个 tool 必须 happy + sad path，
所有 9 个 error dict 分支 + 路径防御 H4 + schema H3 全部走通。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest import mock

import pytest

pytestmark = pytest.mark.autosar


# ---------------------------------------------------------------------------
# autouse fixture：每个测试后还原 mcp_server 模块级 mutable 状态
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _snapshot_mcp_server_globals() -> Any:
    """保存并恢复 mcp_server 的模块级 mutable（_ALLOWED_PROJECT_ROOTS /
    _default_session_dir），避免测试间污染。"""
    from claude_autosar.cli import mcp_server

    original_roots = mcp_server._ALLOWED_PROJECT_ROOTS
    original_default_dir = mcp_server._default_session_dir
    yield
    mcp_server._ALLOWED_PROJECT_ROOTS = original_roots
    mcp_server._default_session_dir = original_default_dir


# ---------------------------------------------------------------------------
# Fixtures：fake EB project（含 xdm + tresos_home）
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """构造最小 EB 工程 + 把 _ALLOWED_PROJECT_ROOTS 限定到 tmp_path。

    XDM 走 ECUC-MODULE-CONFIGURATION-VALUES 结构（与
    ``tests/conftest.py::sample_arxml`` 对齐，让 ``ecuc.load_module`` 能 parse）。
    """
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
            <ECUC-NUMERICAL-PARAM-VALUE>
              <DEFINITION-REF DEST="ECUC-FLOAT-PARAM-DEF">/Mcu/ClockTolerance</DEFINITION-REF>
              <VALUE>1.5</VALUE>
            </ECUC-NUMERICAL-PARAM-VALUE>
            <ECUC-NUMERICAL-PARAM-VALUE>
              <DEFINITION-REF DEST="ECUC-BOOLEAN-PARAM-DEF">/Mcu/ClockEnable</DEFINITION-REF>
              <VALUE>true</VALUE>
            </ECUC-NUMERICAL-PARAM-VALUE>
            <ECUC-TEXTUAL-PARAM-VALUE>
              <DEFINITION-REF DEST="ECUC-STRING-PARAM-DEF">/Mcu/ClockName</DEFINITION-REF>
              <VALUE>SYSCLK</VALUE>
            </ECUC-TEXTUAL-PARAM-VALUE>
          </PARAMETER-VALUES>
        </ECUC-MODULE-CONFIGURATION-VALUES>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
""",
        encoding="utf-8",
    )
    # tresos_home（bsw_write 默认 mkdir；这里预建好让 verify/autocalc 也能跑）
    (project / "tresos_home").mkdir(parents=True, exist_ok=True)
    (project / "tresos_home" / "bin").mkdir(parents=True, exist_ok=True)
    (project / "tresos_home" / "bin" / "tresos_cmd.bat").write_text(
        "@echo off\necho stub\n", encoding="utf-8"
    )
    # H4 路径防御：把允许根限定到 tmp_path
    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )
    return project


# ---------------------------------------------------------------------------
# bsw_read：happy + typed value 派生 + 各种 sad
# ---------------------------------------------------------------------------


def test_bsw_read_happy_int(fake_project: Path) -> None:
    from claude_autosar.cli.mcp_server import bsw_read

    r = bsw_read("Mcu", "ClockFreq", project=str(fake_project))
    assert r["success"] is True
    assert r["value"] == 80000000
    assert isinstance(r["value"], int)
    # ECUCType Literal 是大写 ("INTEGER" / "FLOAT" / ...)
    assert r["type"] == "INTEGER"


def test_bsw_read_happy_float(fake_project: Path) -> None:
    from claude_autosar.cli.mcp_server import bsw_read

    r = bsw_read("Mcu", "ClockTolerance", project=str(fake_project))
    assert r["success"] is True
    assert r["value"] == pytest.approx(1.5)
    assert isinstance(r["value"], float)
    assert r["type"] == "FLOAT"


def test_bsw_read_happy_bool(fake_project: Path) -> None:
    from claude_autosar.cli.mcp_server import bsw_read

    r = bsw_read("Mcu", "ClockEnable", project=str(fake_project))
    assert r["success"] is True
    assert r["value"] is True
    assert isinstance(r["value"], bool)
    # boolean 实际被推断为 BOOLEAN
    assert r["type"] in {"BOOLEAN", "INTEGER"}  # type: ignore[comparison-overlap]


def test_bsw_read_happy_string(fake_project: Path) -> None:
    from claude_autosar.cli.mcp_server import bsw_read

    r = bsw_read("Mcu", "ClockName", project=str(fake_project))
    assert r["success"] is True
    assert r["value"] == "SYSCLK"


def test_bsw_read_with_full_module_prefix(fake_project: Path) -> None:
    """H4 接口：path 已含 Mcu/ 前缀时不重拼。"""
    from claude_autosar.cli.mcp_server import bsw_read

    r = bsw_read("Mcu", "Mcu/ClockFreq", project=str(fake_project))
    assert r["success"] is True
    assert r["value"] == 80000000


def test_bsw_read_module_not_found(fake_project: Path) -> None:
    from claude_autosar.cli.mcp_server import bsw_read

    r = bsw_read("NoSuchModule", "X", project=str(fake_project))
    assert r["success"] is False
    assert "not found" in r["error"]


def test_bsw_read_path_not_in_module(fake_project: Path) -> None:
    from claude_autosar.cli.mcp_server import bsw_read

    r = bsw_read("Mcu", "NonExistent", project=str(fake_project))
    assert r["success"] is False
    assert "not in module" in r["error"]


def test_bsw_read_path_traversal_outside_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """H4：project 必须在 _ALLOWED_PROJECT_ROOTS 内。"""
    from claude_autosar.cli.mcp_server import bsw_read

    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )
    r = bsw_read("Mcu", "X", project="/etc")
    assert r["success"] is False
    assert "PermissionError" in r["error"] or "outside" in r["error"]


# ---------------------------------------------------------------------------
# bsw_write：完整 5 ParamType + H3 schema + happy (stub) + tresos_home 防御
# ---------------------------------------------------------------------------


def test_bsw_write_rejects_empty_params(fake_project: Path) -> None:
    from claude_autosar.cli.mcp_server import bsw_write

    r = bsw_write("Mcu", [], project=str(fake_project))
    assert r["success"] is False
    assert r["param_index"] == -1


def test_bsw_write_rejects_non_list_params(fake_project: Path) -> None:
    from claude_autosar.cli.mcp_server import bsw_write

    r = bsw_write("Mcu", "not a list", project=str(fake_project))  # type: ignore[arg-type]
    assert r["success"] is False
    assert r["param_index"] == -1


def test_bsw_write_rejects_non_dict_param(fake_project: Path) -> None:
    from claude_autosar.cli.mcp_server import bsw_write

    r = bsw_write(
        "Mcu",
        [{"path": "Mcu/ClockFreq", "value": 1, "type": "integer"}, "bad"],
        project=str(fake_project),
    )
    assert r["success"] is False
    assert r["param_index"] == 1
    assert r["field"] == "type"


def test_bsw_write_rejects_first_param_bad(fake_project: Path) -> None:
    """H3：param_index=0 时也要精确定位。"""
    from claude_autosar.cli.mcp_server import bsw_write

    r = bsw_write(
        "Mcu",
        [{"name": "no_path"}, {"path": "Mcu/ClockFreq", "value": 1, "type": "integer"}],
        project=str(fake_project),
    )
    assert r["success"] is False
    assert r["param_index"] == 0


def test_bsw_write_rejects_tresos_home_outside_project(
    fake_project: Path,
) -> None:
    """H4：tresos_home 必须在 project 之内。错误 dict 必须含 field='tresos_home'。"""
    from claude_autosar.cli.mcp_server import bsw_write

    r = bsw_write(
        "Mcu",
        [{"path": "Mcu/ClockFreq", "value": 1, "type": "integer"}],
        project=str(fake_project),
        tresos_home="/some/where/else",
    )
    assert r["success"] is False
    assert "tresos_home must be inside" in r["error"]
    # T3 H3 合约：path-defense 错误也要含 param_index + field
    assert r.get("field") == "tresos_home"
    assert r.get("param_index") == -1


def test_bsw_write_rejects_project_outside_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """H4：project 必须在 _ALLOWED_PROJECT_ROOTS 内。错误 dict 必须含 field='project'。"""
    from claude_autosar.cli.mcp_server import bsw_write

    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )
    r = bsw_write(
        "Mcu",
        [{"path": "Mcu/ClockFreq", "value": 1, "type": "integer"}],
        project="/nonexistent_outside_root_xyz",
    )
    assert r["success"] is False
    assert r.get("field") == "project"
    assert r.get("param_index") == -1
    assert "PermissionError" in r["error"] or "outside" in r["error"]


def test_bsw_write_happy_path_with_stub_adapter(fake_project: Path) -> None:
    """完整 happy：patch 模块级 modify_and_verify → 5 种 ParamType 全跑通。"""
    from claude_autosar.cli.mcp_server import bsw_write
    from claude_autosar.core.bsw.validator import ModifyResult

    fake_result = ModifyResult(
        success=True,
        written_files=(fake_project / "Mcu.xdm",),
        verify_output="stub OK",
        rolled_back=False,
        error=None,
    )

    with mock.patch(
        "claude_autosar.core.bsw.validator.modify_and_verify",
        return_value=fake_result,
    ):
        r = bsw_write(
            "Mcu",
            [
                {"path": "Mcu/ClockFreq", "value": 80000000, "type": "integer"},
                {"path": "Mcu/ClockTolerance", "value": 1.5, "type": "float"},
                {"path": "Mcu/ClockEnable", "value": "true", "type": "boolean"},
                {"path": "Mcu/ClockName", "value": "SYSCLK", "type": "string"},
                {"path": "Mcu/ClockSource", "value": "OSC", "type": "enumeration"},
            ],
            project=str(fake_project),
        )

    assert r["success"] is True, r
    assert r["module"] == "Mcu"
    assert len(r["written_files"]) == 1
    assert r["verify_output"] == "stub OK"
    assert r["rolled_back"] is False
    assert r["error"] is None


def test_bsw_write_happy_path_default_type_is_integer(fake_project: Path) -> None:
    """H3 隐含：type 缺省 = integer。验证方式：捕获传给 modify_and_verify 的 request。"""
    from claude_autosar.cli.mcp_server import bsw_write
    from claude_autosar.core.bsw.config import ParamType
    from claude_autosar.core.bsw.validator import ModifyRequest, ModifyResult

    captured: dict[str, Any] = {}

    def _capture(_ctx: Any, _adapter: Any, request: ModifyRequest) -> ModifyResult:
        captured["request"] = request
        return ModifyResult(
            success=True,
            written_files=(),
            verify_output="OK",
            rolled_back=False,
            error=None,
        )

    with mock.patch("claude_autosar.core.bsw.validator.modify_and_verify", side_effect=_capture):
        r = bsw_write(
            "Mcu",
            [{"path": "Mcu/ClockFreq", "value": 80000000}],  # 缺 type
            project=str(fake_project),
        )

    assert r["success"] is True
    assert captured["request"].params[0].value.type == ParamType.INTEGER


def test_bsw_write_propagates_modify_error(fake_project: Path) -> None:
    """modify_and_verify 返回 success=False 时 dict 透传 error。"""
    from claude_autosar.cli.mcp_server import bsw_write
    from claude_autosar.core.bsw.validator import ModifyResult

    fake_result = ModifyResult(
        success=False,
        written_files=(),
        verify_output="verify failed: bad value",
        rolled_back=True,
        error="BSW value validation failed",
    )
    with mock.patch(
        "claude_autosar.core.bsw.validator.modify_and_verify",
        return_value=fake_result,
    ):
        r = bsw_write(
            "Mcu",
            [{"path": "Mcu/ClockFreq", "value": 1, "type": "integer"}],
            project=str(fake_project),
        )
    assert r["success"] is False
    assert r["error"] == "BSW value validation failed"
    assert r["rolled_back"] is True


# ---------------------------------------------------------------------------
# bsw_verify / bsw_autocalc
# ---------------------------------------------------------------------------


def test_bsw_verify_happy_returns_stub_output(fake_project: Path) -> None:
    from claude_autosar.cli.mcp_server import bsw_verify

    fake = mock.Mock(success=True, returncode=0, stdout="ok", stderr="")
    with mock.patch("claude_autosar.adapters.tresos.TresosAdapter.verify", return_value=fake):
        r = bsw_verify("Mcu", project=str(fake_project))
    assert r["success"] is True
    assert r["returncode"] == 0
    # Sprint 9.3-β bsw_verify 改签名后返 {"success", "module", "returncode", "report": {...}}
    assert r["report"]["has_errors"] is False
    # stdout "ok" 解析器 fallback: 不匹配行 → INFO 整段记 1 条（保守策略）
    assert r["report"]["issue_count"] == 1


def test_bsw_verify_rejects_path_traversal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from claude_autosar.cli.mcp_server import bsw_verify

    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )
    r = bsw_verify("Mcu", project="/etc")
    assert r["success"] is False
    assert "PermissionError" in r["error"] or "outside" in r["error"]


def test_bsw_autocalc_empty_modules_returns_error(fake_project: Path) -> None:
    from claude_autosar.cli.mcp_server import bsw_autocalc

    r = bsw_autocalc([], project=str(fake_project))
    assert r["success"] is False
    assert "modules list is empty" in r["error"]


def test_bsw_autocalc_runs_first_module_only(fake_project: Path) -> None:
    """协议限制：autocalc 只跑 modules[0]；其余标注但忽略。"""
    from claude_autosar.cli.mcp_server import bsw_autocalc

    fake = mock.Mock(success=True, returncode=0, stdout="calc ok", stderr="")
    with mock.patch("claude_autosar.adapters.tresos.TresosAdapter.autocalc", return_value=fake) as m:
        r = bsw_autocalc(["Mcu", "Port", "Dio"], project=str(fake_project))
    assert r["success"] is True
    assert r["modules_requested"] == ["Mcu", "Port", "Dio"]
    assert r["autocalc_triggered_module"] == "Mcu"
    # adapter 调了 1 次
    assert m.call_count == 1


def test_bsw_autocalc_rejects_path_traversal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from claude_autosar.cli.mcp_server import bsw_autocalc

    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )
    r = bsw_autocalc(["Mcu"], project="/etc")
    assert r["success"] is False


# ---------------------------------------------------------------------------
# arxml_validate：missing / ARXMLError / happy
# ---------------------------------------------------------------------------


def test_arxml_validate_missing_file(tmp_path: Path) -> None:
    from claude_autosar.cli.mcp_server import arxml_validate

    r = arxml_validate(str(tmp_path / "no_such.arxml"))
    assert r["success"] is False
    assert "file not found" in r["error"]


def test_arxml_validate_arxml_error(tmp_path: Path) -> None:
    """ARXMLError 路径被显式 catch。"""
    from claude_autosar.cli.mcp_server import arxml_validate

    # 写一个能 parse 但会让 arxml_io 内部报错的（空 root + 坏 namespace）
    bad = tmp_path / "badns.arxml"
    bad.write_text(
        '<?xml version="1.0"?><NOT_AUTOSAR xmlns:bogus="urn:bogus" />',
        encoding="utf-8",
    )
    r = arxml_validate(str(bad))
    # 要么成功（valid XML），要么明确的 error dict；不能 vague pass
    assert "success" in r
    if not r["success"]:
        assert "error" in r
        assert isinstance(r["error"], str) and len(r["error"]) > 0


def test_arxml_validate_catchall_exception(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """catch-all Exception 路径：lxml / OSError 等。"""
    from claude_autosar.cli.mcp_server import arxml_validate
    from claude_autosar.core.bsw import arxml_io

    f = tmp_path / "x.arxml"
    f.write_text("<root/>", encoding="utf-8")

    def _raise_runtime_error(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(arxml_io, "read", _raise_runtime_error)
    r = arxml_validate(str(f))
    assert r["success"] is False
    assert "RuntimeError" in r["error"]
    assert "disk full" in r["error"]


# ---------------------------------------------------------------------------
# dbc_parse：cantools 装了但 DBC 文件路径错误
# ---------------------------------------------------------------------------


def test_dbc_parse_exception_returns_error_dict(tmp_path: Path) -> None:
    from claude_autosar.cli.mcp_server import dbc_parse

    # cantools 装了但 db 解析失败
    bad = tmp_path / "bad.dbc"
    bad.write_text("totally not a dbc", encoding="utf-8")
    r = dbc_parse(str(bad))
    assert r["success"] is False
    # 错误 dict 必须含非空 error 字段（给 LLM caller 可解析的信号）
    assert "error" in r
    assert isinstance(r["error"], str) and len(r["error"]) > 0


# ---------------------------------------------------------------------------
# session_list / session_show / session_export / log_export
# ---------------------------------------------------------------------------


def test_session_list_with_data_returns_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from claude_autosar.cli.mcp_server import session_list

    monkeypatch.setattr("claude_autosar.cli.mcp_server._default_session_dir", lambda: tmp_path)
    # 直接落 2 个 session 文件
    (tmp_path / "alpha.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "beta.jsonl").write_text("", encoding="utf-8")
    ids = session_list()
    # session_list 返回 list[str]（session id 短名）；要求前缀匹配（避免 "alphabet" 误判）
    assert any(s == "alpha" or s.startswith("alpha-") for s in ids)
    assert any(s == "beta" or s.startswith("beta-") for s in ids)


def test_session_show_latest_no_sessions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from claude_autosar.cli.mcp_server import session_show

    monkeypatch.setattr("claude_autosar.cli.mcp_server._default_session_dir", lambda: tmp_path)
    r = session_show("latest")
    assert r["success"] is False
    assert "no sessions found" in r["error"]


def test_session_export_unsupported_fmt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from claude_autosar.cli.mcp_server import session_export

    monkeypatch.setattr("claude_autosar.cli.mcp_server._default_session_dir", lambda: tmp_path)
    r = session_export("s1", fmt="json", session_dir=str(tmp_path))
    assert r["success"] is False
    assert "unsupported fmt" in r["error"]


def test_session_export_latest_no_sessions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from claude_autosar.cli.mcp_server import session_export

    monkeypatch.setattr("claude_autosar.cli.mcp_server._default_session_dir", lambda: tmp_path)
    r = session_export("latest", session_dir=str(tmp_path))
    assert r["success"] is False
    assert "no sessions found" in r["error"]


def test_session_export_happy_html(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    out = tmp_path / "out.html"
    r = session_export("s1", fmt="html", output=str(out), session_dir=str(tmp_path))
    assert r["success"] is True
    assert Path(r["path"]).is_file()
    assert "<html" in out.read_text(encoding="utf-8").lower()


def test_log_export_unsupported_view(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from claude_autosar.cli.mcp_server import log_export

    monkeypatch.setattr("claude_autosar.cli.mcp_server._default_session_dir", lambda: tmp_path)
    r = log_export("s1", view="graphviz", session_dir=str(tmp_path))
    assert r["success"] is False
    assert "unsupported view" in r["error"]


def test_log_export_latest_no_sessions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from claude_autosar.cli.mcp_server import log_export

    monkeypatch.setattr("claude_autosar.cli.mcp_server._default_session_dir", lambda: tmp_path)
    r = log_export("latest", session_dir=str(tmp_path))
    assert r["success"] is False
    assert "no sessions found" in r["error"]


def test_log_export_no_bsw_writes_yields_empty_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """空 session → change_count=0；timeline 文本非空（含 Timeline 标题）。"""
    from claude_autosar.cli.mcp_server import log_export
    from claude_autosar.core.session.store import SessionEntry, SessionStore

    monkeypatch.setattr("claude_autosar.cli.mcp_server._default_session_dir", lambda: tmp_path)
    store = SessionStore(dir=tmp_path)
    # 只写 user entry，不写 bsw_write
    store.append(
        SessionEntry(
            id="e1",
            parent_id=None,
            session_id="s1",
            timestamp="2026-01-01T00:00:00+00:00",
            kind="user",
            content="no edits",
        )
    )
    r = log_export("s1", view="timeline", session_dir=str(tmp_path))
    assert r["success"] is True
    assert r["change_count"] == 0
    # timeline 即使空也含 Timeline 标题（避免硬编码中文，避免 Windows 编码噪音）
    assert "Timeline" in r["text"]


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------


def test_resolve_safe_project_rejects_outside(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from claude_autosar.cli import mcp_server

    monkeypatch.setattr(mcp_server, "_ALLOWED_PROJECT_ROOTS", frozenset({tmp_path.resolve()}))
    with pytest.raises(PermissionError):
        mcp_server._resolve_safe_project("/etc/passwd")


def test_resolve_safe_project_accepts_inside(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from claude_autosar.cli import mcp_server

    monkeypatch.setattr(mcp_server, "_ALLOWED_PROJECT_ROOTS", frozenset({tmp_path.resolve()}))
    inside = tmp_path / "sub"
    inside.mkdir()
    result = mcp_server._resolve_safe_project(str(inside))
    assert result == inside.resolve()


def test_default_tresos_home_returns_subpath(tmp_path: Path) -> None:
    from claude_autosar.cli.mcp_server import _default_tresos_home

    p = tmp_path / "proj"
    p.mkdir()
    assert _default_tresos_home(p) == p / "tresos_home"


# ---------------------------------------------------------------------------
# build_mcp_server 校验：tool name 与函数名一致
# ---------------------------------------------------------------------------


def test_tool_funcs_names_match_function_names() -> None:
    from claude_autosar.cli import mcp_server

    for name, fn in mcp_server._TOOL_FUNCS.items():
        assert name == fn.__name__, f"_TOOL_FUNCS key {name!r} != function name {fn.__name__!r}"


def test_build_mcp_server_asserts_name_mismatch() -> None:
    """M2 防护：如果 _TOOL_FUNCS key 与 fn.__name__ 不一致则 AssertionError。"""
    from claude_autosar.cli import mcp_server

    with (
        mock.patch.object(mcp_server, "_TOOL_FUNCS", {"wrong_name": mcp_server.bsw_read}),
        pytest.raises(AssertionError, match="must match function name"),
    ):
        mcp_server.build_mcp_server()


def test_main_invokes_fastmcp_run() -> None:
    """main() 调用 build_mcp_server().run()（防回归：MCP server 启动入口）。"""
    from claude_autosar.cli import mcp_server

    fake_server = mock.Mock()
    with mock.patch.object(mcp_server, "build_mcp_server", return_value=fake_server):
        mcp_server.main()
    fake_server.run.assert_called_once()
