"""arxml_inspect / xdm_inspect / bsw_inspect / arxml_validate / dbc_parse
+ apply_template / detect / _apply_result_to_dict / _inspect_resolve_input 覆盖测试。

从 ``test_mcp_server_extra_coverage.py`` 拆分而来。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any
from unittest import mock

import pytest

pytestmark = pytest.mark.autosar

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
ARXML_FIXTURE = FIXTURES_DIR / "arxml" / "Com_Com.minimal.arxml"
XDM_FIXTURE = FIXTURES_DIR / "datamodel2" / "Can.xdm"


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


def _copy_arxml_to_tmp(tmp_path: Path) -> Path:
    """把 ARXML fixture 复制到 tmp_path 并返回新路径。"""
    src = tmp_path / "Com_Com.minimal.arxml"
    src.write_bytes(ARXML_FIXTURE.read_bytes())
    return src


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

def test_dbc_parse_cantools_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """cantools ImportError 路径（line 623-625）。"""
    from claude_autosar.cli import mcp_server
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

def test_arxml_apply_template_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """project 不在 _ALLOWED_PROJECT_ROOTS → PermissionError（line 1092-1093）。"""
    from claude_autosar.cli.mcp_server import arxml_apply_template
    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )
    r = arxml_apply_template("/elsewhere/curr.arxml", "/elsewhere/tpl.arxml", project=".")
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
    tpl = tmp_path / "tpl.arxml"
    tpl.write_bytes(ARXML_FIXTURE.read_bytes())
    r = arxml_apply_template(str(tmp_path / "missing.arxml"), str(tpl), project=str(tmp_path))
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
    src = tmp_path / "src.arxml"
    src.write_bytes(ARXML_FIXTURE.read_bytes())
    r = arxml_apply_template(str(src), str(tmp_path / "missing_tpl.arxml"), project=str(tmp_path))
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
    xml = '<?xml version="1.0"?><AUTOSAR xmlns="http://autosar.org/schema/r4.0"><AR-PACKAGES/></AUTOSAR>'
    src = tmp_path / "curr.arxml"
    src.write_text(xml, encoding="utf-8")
    tpl = tmp_path / "tpl.arxml"
    tpl.write_text(xml, encoding="utf-8")
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
    r = xdm_apply_template(str(tmp_path / "missing.xdm"), str(tpl), project=str(tmp_path))
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
    r = xdm_apply_template(str(src), str(tmp_path / "missing_tpl.xdm"), project=str(tmp_path))
    assert r["success"] is False
    assert "FileNotFoundError" in r["error"]

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
        '<?xml version="1.0"?><AUTOSAR xmlns="http://autosar.org/schema/r4.0"><AR-PACKAGES/></AUTOSAR>',
        encoding="utf-8",
    )
    assert _detect_arxml_module_name(f) is None

def test_detect_arxml_module_name_no_shortname(tmp_path: Path) -> None:
    """module 存在但 SHORT-NAME 为空 → None（line 1282）。"""
    from claude_autosar.cli.mcp_server import _detect_arxml_module_name
    f = tmp_path / "no_shortname.arxml"
    f.write_text(
        '<?xml version="1.0"?><AUTOSAR xmlns="http://autosar.org/schema/r4.0">'
        '<AR-PACKAGES><AR-PACKAGE><SHORT-NAME>Ecuc</SHORT-NAME><ELEMENTS>'
        '<ECUC-MODULE-CONFIGURATION-VALUES></ECUC-MODULE-CONFIGURATION-VALUES>'
        '</ELEMENTS></AR-PACKAGE></AR-PACKAGES></AUTOSAR>',
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
