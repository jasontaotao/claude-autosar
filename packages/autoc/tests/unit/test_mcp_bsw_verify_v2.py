"""Unit tests for the enhanced `bsw_verify` MCP tool (Sprint 9.3 — T9.3-β).

测试范围（8 个 case）：
* 签名：4 个新 v2 path 参数 + as_json 参数的默认值 + 必填位置参数
* happy path：mock TresosAdapter.verify → 默认返轻量 dict（issue_count +
  has_errors/has_warnings + v2_paths）
* as_json=True：返 TresosVerifyReport 完整序列化（issues tuple + has_*
  property + raw_stdout/raw_stderr）
* parse_tresos_verify_stdout 集成：stdout 含 ERROR 行 → has_errors=True
* H4 路径防御：project 路径穿越 → PermissionError dict
* tresos_home 不在 project 之下 → error dict
* v2_paths meta：CLI 参数正确喂给 load_v2_paths（mocked）
* backwards-compat：保留旧的 stdout/stderr 字段语义（MCP 客户端可能依赖）

实现策略：因 mcp_server.py 在 Sprint 9.2-γ 中有未完成的
``arxml_apply_template`` / ``xdm_apply_template`` tool 函数未定义（模块级
``_TOOL_FUNCS`` 引用未实现），整个模块无法直接 ``import``。本测试用 AST
提取 ``bsw_verify`` 函数源码 + 在 sandbox 里 exec，让它和必要依赖一起加载。
这是临时绕过；待 9.2-γ 完整实现后切回标准 import。
"""

from __future__ import annotations

import ast
from pathlib import Path
import textwrap
from unittest import mock

import pytest

pytestmark = pytest.mark.autosar


# ---------------------------------------------------------------------------
# Fixture：加载 bsw_verify 函数（绕过 9.2-γ 阻塞 import）
# ---------------------------------------------------------------------------


_MCP_SERVER_PATH = Path(__file__).resolve().parents[2] / ("src/claude_autosar/cli/mcp_server.py")


_SANDBOX_GLOBALS: dict[str, object] = {}


def _load_bsw_verify_from_source() -> object:
    """从 mcp_server.py 源码 AST 提取 bsw_verify 函数，注入 sandbox exec。

    使用 module 级 _SANDBOX_GLOBALS dict 复用 sandbox（这样 fixture 改写
    ``_ALLOWED_PROJECT_ROOTS`` 时，函数仍然引用同一个 globals dict）。
    """
    if "bsw_verify" in _SANDBOX_GLOBALS:
        return _SANDBOX_GLOBALS["bsw_verify"]
    source = _MCP_SERVER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    func_node = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "bsw_verify"
    )
    # 提取函数依赖的辅助函数（_resolve_safe_project / _default_tresos_home /
    # _build_ctx）。
    helper_names = {
        "_resolve_safe_project",
        "_default_tresos_home",
        "_build_ctx",
    }
    helper_nodes: list[ast.stmt] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in helper_names:
            helper_nodes.append(node)

    # 构造 sandbox：先 import Path，再定义 _ALLOWED_PROJECT_ROOTS，再定义
    # helpers，最后 bsw_verify。
    prefix_src = textwrap.dedent("""
        from __future__ import annotations
        from pathlib import Path
        from typing import Any, cast
        import os

        # 兼容 mcp_server 模块级 _ALLOWED_PROJECT_ROOTS（H4 路径防御）。
        # 占位值；fixture 会改写 _SANDBOX_GLOBALS["_ALLOWED_PROJECT_ROOTS"]。
        _ALLOWED_PROJECT_ROOTS: frozenset[Path] = frozenset({Path(os.getcwd()).resolve()})
        """).strip()
    sandbox_src = prefix_src + "\n"
    for node in helper_nodes:
        sandbox_src += ast.unparse(node) + "\n\n"
    sandbox_src += ast.unparse(func_node) + "\n"
    code = compile(sandbox_src, str(_MCP_SERVER_PATH), "exec")
    _SANDBOX_GLOBALS.clear()
    _SANDBOX_GLOBALS["__name__"] = "_sandbox_bsw_verify"
    exec(code, _SANDBOX_GLOBALS)
    return _SANDBOX_GLOBALS["bsw_verify"]


@pytest.fixture(scope="module")
def bsw_verify_fn() -> object:
    """加载 bsw_verify 函数（module-scope，只解 AST 一次）。"""
    return _load_bsw_verify_from_source()


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
    """把 _ALLOWED_PROJECT_ROOTS（sandbox + 真实 module）限定到 fake_project。"""
    _SANDBOX_GLOBALS["_ALLOWED_PROJECT_ROOTS"] = frozenset({fake_project.resolve()})
    # 同步真实 module（即便现在不能 import；保留接口统一）
    try:
        from claude_autosar.cli import mcp_server as real_mod

        monkeypatch.setattr(real_mod, "_ALLOWED_PROJECT_ROOTS", frozenset({fake_project.resolve()}))
    except Exception:
        # mcp_server 模块因 9.2-γ 不完整而无法 import；跳过真实 module 同步。
        pass


# ---------------------------------------------------------------------------
# 1. 签名
# ---------------------------------------------------------------------------


def test_signature_has_new_v2_path_params(bsw_verify_fn: object) -> None:
    """bsw_verify 新签名：4 个 v2 path kwonly + as_json kwonly。"""
    import inspect

    sig = inspect.signature(bsw_verify_fn)  # type: ignore[arg-type]
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
# 2. happy path（默认 as_json=False → 轻量 dict）
# ---------------------------------------------------------------------------


def test_happy_returns_lightweight_dict(
    bsw_verify_fn: object, fake_project: Path, _allowed_roots: None
) -> None:
    """as_json=False（默认）：返 issue_count + has_errors/has_warnings 摘要。"""
    # stdout 用空字符串 — 解析器返回空 issues 列表
    fake_verify = mock.Mock(success=True, returncode=0, stdout="", stderr="")
    with mock.patch(
        "claude_autosar.adapters.tresos.TresosAdapter.verify", return_value=fake_verify
    ):
        r = bsw_verify_fn("Mcu", project=str(fake_project))  # type: ignore[operator]
    assert r["success"] is True
    assert r["module"] == "Mcu"
    assert r["returncode"] == 0
    # 轻量 dict：只有 summary
    assert "report" in r
    assert r["report"]["issue_count"] == 0
    assert r["report"]["has_errors"] is False
    assert r["report"]["has_warnings"] is False
    # 没有完整 issues 列表（轻量化）
    assert "issues" not in r["report"]
    assert "raw_stdout" not in r["report"]


# ---------------------------------------------------------------------------
# 3. as_json=True → 完整 TresosVerifyReport 序列化
# ---------------------------------------------------------------------------


def test_as_json_returns_full_report(
    bsw_verify_fn: object, fake_project: Path, _allowed_roots: None
) -> None:
    """as_json=True：issues tuple + has_errors/has_warnings + raw_* 全展开。"""
    fake_verify = mock.Mock(
        success=False, returncode=1, stdout="ERROR: bad\nWARNING: typo\n", stderr=""
    )
    with mock.patch(
        "claude_autosar.adapters.tresos.TresosAdapter.verify", return_value=fake_verify
    ):
        r = bsw_verify_fn("Mcu", project=str(fake_project), as_json=True)  # type: ignore[operator]
    assert r["success"] is False
    assert r["returncode"] == 1
    report = r["report"]
    # 完整序列化字段
    assert "issues" in report
    assert "returncode" in report
    assert "raw_stdout" in report
    assert "raw_stderr" in report
    assert "has_errors" in report
    assert "has_warnings" in report
    # 内容
    assert len(report["issues"]) == 2
    assert report["has_errors"] is True
    assert report["has_warnings"] is True
    # 第一条 issue 是 ERROR
    assert report["issues"][0]["severity"] == "ERROR"
    assert report["issues"][1]["severity"] == "WARNING"


# ---------------------------------------------------------------------------
# 4. parse_tresos_verify_stdout 集成：stderr 在 returncode!=0 时附加一条 ERROR
# ---------------------------------------------------------------------------


def test_stderr_appended_as_error_when_returncode_nonzero(
    bsw_verify_fn: object, fake_project: Path, _allowed_roots: None
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
        r = bsw_verify_fn("Mcu", project=str(fake_project), as_json=True)  # type: ignore[operator]
    report = r["report"]
    issues = report["issues"]
    # 至少有 1 条 ERROR（来自 stderr）+ 至少 1 条来自 stdout
    assert report["has_errors"] is True
    # stderr 整段应该作为一条 ERROR issue 出现
    stderr_issues = [i for i in issues if "tresos_cmd exit 2" in i["message"]]
    assert len(stderr_issues) == 1
    assert stderr_issues[0]["severity"] == "ERROR"


# ---------------------------------------------------------------------------
# 5. H4 路径防御：project 路径穿越
# ---------------------------------------------------------------------------


def test_rejects_path_traversal(
    bsw_verify_fn: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """project 路径穿越 → PermissionError dict（field=project）。"""
    # 限定 allowed roots 到 tmp_path，但用 /etc 触发越界
    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )
    r = bsw_verify_fn("Mcu", project="/etc")  # type: ignore[operator]
    assert r["success"] is False
    assert "PermissionError" in r["error"] or "outside" in r["error"]
    assert r["field"] == "project"


# ---------------------------------------------------------------------------
# 6. tresos_home 不在 project 之下 → error dict
# ---------------------------------------------------------------------------


def test_tresos_home_outside_project_returns_error(
    bsw_verify_fn: object, fake_project: Path, _allowed_roots: None
) -> None:
    """tresos_home 必须在 project_path 子树下，否则 error。"""
    # /tmp 完全在 fake_project 之外
    r = bsw_verify_fn(  # type: ignore[operator]
        "Mcu", project=str(fake_project), tresos_home="/tmp/somewhere_else"
    )
    assert r["success"] is False
    assert "tresos_home" in r["error"]
    assert r["field"] == "tresos_home"


# ---------------------------------------------------------------------------
# 7. v2_paths meta：CLI 参数喂给 load_v2_paths
# ---------------------------------------------------------------------------


def test_v2_paths_meta_included_in_response(
    bsw_verify_fn: object, fake_project: Path, _allowed_roots: None
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
    ):
        r = bsw_verify_fn(  # type: ignore[operator]
            "Mcu",
            project=str(fake_project),
            tresos_home=str(fake_project / "tresos_home"),
            mcal_vendor="nxp",
            mcal_vendor_home="/tmp/nxp",
            chip_derivative="Mcu.epd",
        )
    # load_v2_paths 被调用，参数正确
    m_lv2.assert_called_once()
    kwargs = m_lv2.call_args.kwargs
    assert kwargs["cli_mcal_vendor"] == "nxp"
    assert kwargs["cli_chip_derivative"] == "Mcu.epd"
    assert kwargs["cli_mcal_vendor_home"] == "/tmp/nxp"
    # 响应包含 v2_paths meta
    assert r["v2_paths"]["mcal_vendor"] == "nxp"
    assert r["v2_paths"]["chip_derivative"] == "Mcu.epd"


# ---------------------------------------------------------------------------
# 8. backwards-compat：v2_paths 加载失败时返回空 dict，不阻塞 verify
# ---------------------------------------------------------------------------


def test_v2_paths_failure_does_not_block_verify(
    bsw_verify_fn: object, fake_project: Path, _allowed_roots: None
) -> None:
    """load_v2_paths 抛 V2PathsError（4 级都拿不到）时 → v2_paths={}，verify 继续。"""
    from claude_autosar.core.settings.v2_paths import V2PathsError

    fake_verify = mock.Mock(success=True, returncode=0, stdout="ok", stderr="")
    with (
        mock.patch("claude_autosar.adapters.tresos.TresosAdapter.verify", return_value=fake_verify),
        mock.patch(
            "claude_autosar.core.settings.v2_paths.load_v2_paths",
            side_effect=V2PathsError("no v2 paths"),
        ),
    ):
        r = bsw_verify_fn("Mcu", project=str(fake_project))  # type: ignore[operator]
    # verify 主链路不受影响
    assert r["success"] is True
    assert r["module"] == "Mcu"
    # v2_paths 退化为空 dict
    assert r["v2_paths"] == {}
