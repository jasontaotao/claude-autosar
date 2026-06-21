"""Unit tests for the enhanced `bsw_verify` MCP tool (Sprint 9.3 — T9.3-beta).

测试范围（8 个 case）：
* 签名：4 个新 v2 path 参数 + as_json 参数的默认值 + 必填位置参数
* happy path：mock TresosAdapter.verify -> 默认返轻量 dict（issue_count +
  has_errors/has_warnings + v2_paths）
* as_json=True：返 TresosVerifyReport 完整序列化（issues tuple + has_*
  property + raw_stdout/raw_stderr）
* parse_tresos_verify_stdout 集成：stdout 含 ERROR 行 -> has_errors=True
* H4 路径防御：project 路径穿越 -> PermissionError dict
* tresos_home 不在 project 之下 -> error dict
* v2_paths meta：CLI 参数正确喂给 load_v2_paths（mocked）
* backwards-compat：保留旧的 stdout/stderr 字段语义（MCP 客户端可能依赖）

Sprint 9.5 重构后：已从 AST sandbox exec 切回标准 import（bsw_verify
在 mcp_tools/bsw_write_ops.py，通过 mcp_server re-export）。
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from claude_autosar.cli.mcp_server import bsw_verify as bsw_verify_fn

pytestmark = pytest.mark.autosar


@pytest.fixture
def fake_project(tmp_path: Path) -> Path:
    """构造最小 fake 工程（含 tresos_home + bat stub）。"""
    project = tmp_path / "proj"
    project.mkdir(parents=True, exist_ok=True)
    (project / "tresos_home").mkdir(parents=True, exist_ok=True)
    (project / "tresos_home" / "bin").mkdir(parents=True, exist_ok=True)
    (project / "tresos_home" / "bin" / "tresos_cmd.bat").write_text(
        "@echo off\necho stub\n", encoding="utf-8"
    )
    return project


@pytest.fixture
def _allowed_roots(fake_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """把 _ALLOWED_PROJECT_ROOTS 限定到 fake_project。"""
    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({fake_project.resolve()}),
    )


# ---------------------------------------------------------------------------
# 1. 签名
# ---------------------------------------------------------------------------


def test_signature_has_new_v2_path_params() -> None:
    """bsw_verify 新签名：4 个 v2 path kwonly + as_json kwonly。"""
    import inspect

    sig = inspect.signature(bsw_verify_fn)
    kw = sig.parameters
    # 必填位置：module
    assert "module" in sig.parameters
    assert sig.parameters["module"].default is inspect.Parameter.empty
    # 新增 kwonly 参数
    assert "chip_derivative" in kw
    assert "mcal_vendor" in kw
    assert "mcal_vendor_home" in kw
    assert "as_json" in kw
    # 既有 kwonly 参数
    assert "project" in kw
    assert "tresos_home" in kw
    # 默认值
    assert kw["project"].default == "."
    assert kw["as_json"].default is False
    # 类型注解
    assert kw["chip_derivative"].annotation == "str | None"
    assert kw["as_json"].annotation == "bool"


# ---------------------------------------------------------------------------
# 2. happy path（默认 as_json=False -> 轻量 dict）
# ---------------------------------------------------------------------------


def test_happy_returns_lightweight_dict(
    fake_project: Path, _allowed_roots: None
) -> None:
    """as_json=False（默认）：返 issue_count + has_errors/has_warnings 摘要。"""
    fake_verify = mock.Mock(success=True, returncode=0, stdout="", stderr="")
    with mock.patch(
        "claude_autosar.adapters.tresos.TresosAdapter.verify", return_value=fake_verify
    ):
        r = bsw_verify_fn("Mcu", project=str(fake_project))
    assert r["success"] is True
    assert r["module"] == "Mcu"
    assert r["returncode"] == 0
    assert "report" in r
    assert r["report"]["issue_count"] == 0
    assert r["report"]["has_errors"] is False
    assert r["report"]["has_warnings"] is False
    assert "issues" not in r["report"]
    assert "raw_stdout" not in r["report"]


# ---------------------------------------------------------------------------
# 3. as_json=True -> 完整 TresosVerifyReport 序列化
# ---------------------------------------------------------------------------


def test_as_json_returns_full_report(
    fake_project: Path, _allowed_roots: None
) -> None:
    """as_json=True：issues tuple + has_errors/has_warnings + raw_* 全展开。"""
    fake_verify = mock.Mock(
        success=False, returncode=1, stdout="ERROR: bad\nWARNING: typo\n", stderr=""
    )
    with mock.patch(
        "claude_autosar.adapters.tresos.TresosAdapter.verify", return_value=fake_verify
    ):
        r = bsw_verify_fn("Mcu", project=str(fake_project), as_json=True)
    assert r["success"] is False
    assert r["returncode"] == 1
    report = r["report"]
    assert "issues" in report
    assert "returncode" in report
    assert "raw_stdout" in report
    assert "raw_stderr" in report
    assert "has_errors" in report
    assert "has_warnings" in report
    assert len(report["issues"]) == 2
    assert report["has_errors"] is True
    assert report["has_warnings"] is True
    assert report["issues"][0]["severity"] == "ERROR"
    assert report["issues"][1]["severity"] == "WARNING"


# ---------------------------------------------------------------------------
# 4. parse_tresos_verify_stdout 集成：stderr 在 returncode!=0 时附加一条 ERROR
# ---------------------------------------------------------------------------


def test_stderr_appended_as_error_when_returncode_nonzero(
    fake_project: Path, _allowed_roots: None
) -> None:
    """returncode != 0 时 stderr 整段附加一条 ERROR issue。"""
    fake_verify = mock.Mock(
        success=False,
        returncode=2,
        stdout="ERROR: config invalid code: E001",
        stderr="tresos_cmd exit 2: validation failed",
    )
    with mock.patch(
        "claude_autosar.adapters.tresos.TresosAdapter.verify", return_value=fake_verify
    ):
        r = bsw_verify_fn("Mcu", project=str(fake_project), as_json=True)
    report = r["report"]
    issues = report["issues"]
    assert report["has_errors"] is True
    stderr_issues = [i for i in issues if "tresos_cmd exit 2" in i["message"]]
    assert len(stderr_issues) == 1
    assert stderr_issues[0]["severity"] == "ERROR"


# ---------------------------------------------------------------------------
# 5. H4 路径防御：project 路径穿越
# ---------------------------------------------------------------------------


def test_rejects_path_traversal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """project 路径穿越 -> PermissionError dict（field=project）。"""
    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )
    r = bsw_verify_fn("Mcu", project="/etc")
    assert r["success"] is False
    assert "PermissionError" in r["error"] or "outside" in r["error"]
    assert r["field"] == "project"


# ---------------------------------------------------------------------------
# 6. tresos_home 不在 project 之下 -> error dict
# ---------------------------------------------------------------------------


def test_tresos_home_outside_project_returns_error(
    fake_project: Path, _allowed_roots: None
) -> None:
    """tresos_home 必须在 project_path 子树下，否则 error。"""
    r = bsw_verify_fn(
        "Mcu", project=str(fake_project), tresos_home="/tmp/somewhere_else"
    )
    assert r["success"] is False
    assert "tresos_home" in r["error"] or "Path traversal" in r["error"]
    assert r["field"] == "tresos_home"


# ---------------------------------------------------------------------------
# 7. v2_paths meta：CLI 参数喂给 load_v2_paths
# ---------------------------------------------------------------------------


def test_v2_paths_meta_included_in_response(
    fake_project: Path, _allowed_roots: None
) -> None:
    """响应含 v2_paths 字段；mock load_v2_paths 验证调用。"""
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class _FakeV2:
        tresos_home: Path
        mcal_vendor: str
        mcal_vendor_home: Path
        chip_derivative: str

    fake_v2 = _FakeV2(
        tresos_home=fake_project / "tresos_home",
        mcal_vendor="nxp",
        mcal_vendor_home=Path("/tmp/nxp"),
        chip_derivative="Mcu.epd",
    )
    fake_verify = mock.Mock(success=True, returncode=0, stdout="", stderr="")
    with (
        mock.patch("claude_autosar.adapters.tresos.TresosAdapter.verify", return_value=fake_verify),
        mock.patch(
            "claude_autosar.core.settings.v2_paths.load_v2_paths", return_value=fake_v2
        ) as m_lv2,
        # validate_no_traversal 拒绝绝对路径；此处 bypass 以测试 load_v2_paths 透传
        mock.patch(
            "claude_autosar.cli.mcp_tools.validation.validate_no_traversal",
            side_effect=lambda p: p,
        ),
    ):
        r = bsw_verify_fn(
            "Mcu",
            project=str(fake_project),
            tresos_home=str(fake_project / "tresos_home"),
            mcal_vendor="nxp",
            mcal_vendor_home="/tmp/nxp",
            chip_derivative="Mcu.epd",
        )
    m_lv2.assert_called_once()
    kwargs = m_lv2.call_args.kwargs
    assert kwargs["cli_mcal_vendor"] == "nxp"
    assert kwargs["cli_chip_derivative"] == "Mcu.epd"
    assert kwargs["cli_mcal_vendor_home"] == "/tmp/nxp"
    assert r["v2_paths"]["mcal_vendor"] == "nxp"
    assert r["v2_paths"]["chip_derivative"] == "Mcu.epd"


# ---------------------------------------------------------------------------
# 8. backwards-compat：v2_paths 加载失败时返回空 dict，不阻塞 verify
# ---------------------------------------------------------------------------


def test_v2_paths_failure_does_not_block_verify(
    fake_project: Path, _allowed_roots: None
) -> None:
    """load_v2_paths 抛 V2PathsError（4 级都拿不到）时 -> v2_paths={}，verify 继续。"""
    from claude_autosar.core.settings.v2_paths import V2PathsError

    fake_verify = mock.Mock(success=True, returncode=0, stdout="ok", stderr="")
    with (
        mock.patch("claude_autosar.adapters.tresos.TresosAdapter.verify", return_value=fake_verify),
        mock.patch(
            "claude_autosar.core.settings.v2_paths.load_v2_paths",
            side_effect=V2PathsError("no v2 paths"),
        ),
    ):
        r = bsw_verify_fn("Mcu", project=str(fake_project))
    assert r["success"] is True
    assert r["module"] == "Mcu"
    assert r["v2_paths"] == {}
