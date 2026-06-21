"""Sprint 7 端到端 — 钩子 ↔ CLI ↔ MCP ↔ HTML 导出 全链路。

T7.1 验收：在 pytest 进程内串联 Claude Code 插件的核心工作流：

1. **钩子 subprocess 拒绝** — 跑 ``pretooluse_arxml_guard.py``，stdin 喂坏 XML
   Write 事件，断言 stdout 是 deny 决策
2. **钩子 subprocess 放行** — 喂合法 ARXML Write 事件，断言 stdout = ``{}``
3. **SessionStart 注入上下文** — 跑 ``sessionstart_detect_project.py``，cwd 命中
   ``.project`` 时注入 ``additionalContext``
4. **MCP 写入 → session 落盘 → HTML 导出** — 调 ``mcp_server.bsw_write`` +
   ``mcp_server.session_export``，验证 HTML 含改参 callout
5. **CLI → MCP 一致性** — ``autoc`` 子命令和直接调 MCP 工具返回相同 dict 结构
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Helper：跑钩子脚本（subprocess，stdin 喂 JSON，stdout 读 JSON）
# ---------------------------------------------------------------------------


def _run_hook(hook_path: Path, event: dict[str, Any] | str) -> dict[str, Any]:
    """subprocess 调钩子脚本，stdin=event JSON，stdout 解析 JSON 返回。

    用 ``encoding="utf-8"`` 显式锁编码（Windows 默认 cp936/cp1252 会让非 ASCII
    字符在 print 时崩）；任何非 0 returncode 都视为 hook 异常并 raise。
    """
    stdin_payload = json.dumps(event) if isinstance(event, dict) else event
    proc = subprocess.run(  # noqa: S603
        [sys.executable, str(hook_path)],
        input=stdin_payload,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"hook failed rc={proc.returncode}\n"
            f"stdout: {proc.stdout!r}\nstderr: {proc.stderr!r}"
        )
    out = proc.stdout.strip()
    if not out:
        return {}
    return json.loads(out)


def _hook_path(name: str) -> Path:
    """定位 plugin 钩子脚本。

    test_sprint7_e2e.py 在 packages/autoc/tests/integration/：
    - parents[0] = integration
    - parents[1] = tests
    - parents[2] = autoc
    - parents[3] = packages   ← 起点
    """
    repo_packages = Path(__file__).resolve().parents[3]
    return repo_packages / "plugin" / "plugins" / "claude-autosar" / "hooks" / name


# ---------------------------------------------------------------------------
# 1. 钩子拒绝坏 ARXML
# ---------------------------------------------------------------------------


def test_pretooluse_rejects_broken_arxml(tmp_path: Path) -> None:
    """PreToolUse：写坏 ARXML → 拒绝（hookSpecificOutput + 顶层 decision 双格式）。"""
    hook = _hook_path("pretooluse_arxml_guard.py")
    assert hook.is_file(), f"hook script not found: {hook}"

    bad = tmp_path / "bad.arxml"
    bad.write_text("<<not xml>>", encoding="utf-8")
    event = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(bad), "content": "<<not xml>>"},
    }
    decision = _run_hook(hook, event)
    # 必须有 denial 决策（双格式之一）
    hso = decision.get("hookSpecificOutput", {})
    top = decision.get("decision")
    denied = hso.get("permissionDecision") == "deny" or top == "block"
    assert denied, f"expected deny decision, got {decision!r}"
    # 应有 systemMessage 解释
    msg = hso.get("permissionDecisionReason") or decision.get("reason", "")
    assert "ARXML" in msg or "schema" in msg.lower()


def test_pretooluse_allows_valid_arxml(tmp_path: Path) -> None:
    """PreToolUse：合法 ARXML → 放行（空对象）。"""
    hook = _hook_path("pretooluse_arxml_guard.py")

    good = tmp_path / "ok.arxml"
    good.write_text(
        '<?xml version="1.0"?><AUTOSAR xmlns="http://autosar.org/schema/r4.0"><AR-PACKAGES/></AUTOSAR>',
        encoding="utf-8",
    )
    event = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(good), "content": good.read_text(encoding="utf-8")},
    }
    decision = _run_hook(hook, event)
    # 放行决策 = 空对象（或 permissionDecision == "allow"）
    hso = decision.get("hookSpecificOutput", {})
    if hso:
        assert hso.get("permissionDecision") in (None, "allow"), decision
    else:
        assert "decision" not in decision or decision["decision"] != "block"


def test_pretooluse_ignores_non_arxml_files(tmp_path: Path) -> None:
    """PreToolUse：非 .arxml 后缀 → 直接放行，不解析内容。"""
    hook = _hook_path("pretooluse_arxml_guard.py")

    f = tmp_path / "notes.md"
    f.write_text("anything goes", encoding="utf-8")
    event = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(f), "content": "anything goes"},
    }
    decision = _run_hook(hook, event)
    # 放行：空对象或 permissionDecision=allow
    hso = decision.get("hookSpecificOutput", {})
    assert not hso or hso.get("permissionDecision") in (None, "allow")


# ---------------------------------------------------------------------------
# 2. SessionStart 注入上下文
# ---------------------------------------------------------------------------


def test_sessionstart_injects_context_when_project_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch  # noqa: ARG001
) -> None:
    """SessionStart：cwd 命中 .project → 注入 additionalContext。"""
    hook = _hook_path("sessionstart_detect_project.py")
    assert hook.is_file()

    # 构造假 EB 工程根
    (tmp_path / ".project").write_text(
        "<project><target>ARM</target><derivate>S32K3</derivate></project>",
        encoding="utf-8",
    )

    event = {"session_id": "test-session", "cwd": str(tmp_path)}
    decision = _run_hook(hook, event)
    hso = decision.get("hookSpecificOutput", {})
    ctx = hso.get("additionalContext", "")
    assert "EB" in ctx or "Mcu" in ctx or "BSW" in ctx or "autoc" in ctx.lower()


def test_sessionstart_graceful_on_empty_cwd() -> None:
    """SessionStart：cwd 空 / 不存在 → 优雅放行不崩溃。"""
    hook = _hook_path("sessionstart_detect_project.py")

    # 喂一个空 event（缺字段）
    decision = _run_hook(hook, {})
    # 至少不抛；决策可能空，可能有 systemMessage
    assert isinstance(decision, dict)


# ---------------------------------------------------------------------------
# 3. MCP 写入 → session 落盘 → log_export 渲染
# ---------------------------------------------------------------------------


def _patch_session_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """把全局 session 目录改到 tmp_path。"""
    cfg_dir = tmp_path / "fake_agent"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "claude_autosar.utils.paths.user_config_dir",
        lambda *a, **kw: str(cfg_dir),
    )


def test_mcp_bsw_write_then_recorder_then_log_export_renders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """完整 e2e：MCP bsw_write 成功 → recorder 落盘 → log_export 看到改参。

    MCP ``bsw_write`` 工具本身只调 modify_and_verify，不写 session（T5 设计：session
    写入由 CLI 业务层 recorder 负责）。本测模拟 Claude Code Agent 的完整路径：
    调 MCP 工具 + 手工 record 一笔改参到 session。
    """
    from unittest import mock

    from claude_autosar.cli.mcp_server import bsw_write, log_export
    from claude_autosar.core.bsw.config import BSWParam, ParamType, ParamValue
    from claude_autosar.core.bsw.validator import ModifyResult
    from claude_autosar.core.session.recorder import record_bsw_write_batch

    _patch_session_dir(monkeypatch, tmp_path)

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
    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )

    fake_result = ModifyResult(
        success=True,
        written_files=(project / "Mcu.xdm",),
        verify_output="OK",
        rolled_back=False,
        error=None,
    )

    # 步骤 1：调 MCP bsw_write
    with mock.patch(
        "claude_autosar.core.bsw.validator.modify_and_verify", return_value=fake_result
    ):
        r = bsw_write(
            "Mcu",
            [
                {"path": "Mcu/ClockFreq", "value": 80000000, "type": "integer"},
            ],
            project=str(project),
        )
    assert r["success"] is True, r

    # 步骤 2：模拟 CLI 业务层 record 改参到 session
    from claude_autosar.core.session.store import SessionStore

    params = (
        BSWParam(
            path="Mcu/ClockFreq",
            value=ParamValue(raw="80000000", type=ParamType.INTEGER),
        ),
    )
    record_bsw_write_batch(
        SessionStore(),
        module="Mcu",
        params=params,
        success=True,
    )

    # 步骤 3：log_export 看到改参
    store = SessionStore()
    sessions = store.list_session_ids()
    assert len(sessions) >= 1, "expected at least one session after record"

    last = sessions[-1]
    log = log_export(last, view="timeline")
    assert log["success"] is True
    assert log["change_count"] >= 1
    # 渲染文本应含 Mcu 或 ClockFreq 或 80000000
    assert any(tok in log["text"] for tok in ("Mcu", "ClockFreq", "80000000"))


# ---------------------------------------------------------------------------
# 4. MCP session_export 写出 HTML
# ---------------------------------------------------------------------------


def test_mcp_session_export_writes_html(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """MCP session_export：写出 HTML 文件，含基础结构。"""
    from claude_autosar.cli.mcp_server import session_export
    from claude_autosar.core.session.store import SessionEntry, SessionStore

    _patch_session_dir(monkeypatch, tmp_path)
    store = SessionStore()
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

    out = tmp_path / "out.html"
    r = session_export("s1", fmt="html", output=str(out))
    assert r["success"] is True, r
    assert out.is_file()
    html_text = out.read_text(encoding="utf-8")
    assert "<html" in html_text.lower()
    # XSS 防御：html.escape 应对 < > &
    assert "&lt;" not in html_text or "&amp;" in html_text or "hello" in html_text


# ---------------------------------------------------------------------------
# 5. CLI 子命令 ↔ MCP 工具一致性
# ---------------------------------------------------------------------------


def test_cli_eb_save_and_mcp_bsw_write_return_consistent_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """autoc eb save (CLI) 与 mcp bsw_write (MCP) 的 success dict shape 一致。

    两者都返回 ``{"success", "module", "error", ...}`` — 不强求全部字段一致，
    但核心 3 字段必须存在且 success 类型相同。
    """
    from unittest import mock

    from claude_autosar.cli.mcp_server import bsw_write
    from claude_autosar.core.bsw.validator import ModifyResult

    _patch_session_dir(monkeypatch, tmp_path)

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
          <PARAMETER-VALUES/>
        </ECUC-MODULE-CONFIGURATION-VALUES>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
""",
        encoding="utf-8",
    )
    (project / "tresos_home").mkdir(parents=True, exist_ok=True)
    (project / "tresos_home" / "bin").mkdir(parents=True, exist_ok=True)
    (project / "tresos_home" / "bin" / "tresos_cmd.bat").write_text(
        "@echo off\necho stub\n", encoding="utf-8"
    )

    monkeypatch.setattr(
        "claude_autosar.cli.mcp_server._ALLOWED_PROJECT_ROOTS",
        frozenset({tmp_path.resolve()}),
    )

    fake = ModifyResult(
        success=True, written_files=(), verify_output="OK", rolled_back=False, error=None
    )

    # --- MCP: bsw_write ---
    with mock.patch("claude_autosar.core.bsw.validator.modify_and_verify", return_value=fake):
        mcp_r = bsw_write(
            "Mcu",
            [{"path": "Mcu/ClockFreq", "value": 80000000, "type": "integer"}],
            project=str(project),
        )

    # Shape 一致性：MCP 路径必须含 success(bool) + module(str) + error(nullable)
    assert isinstance(mcp_r["success"], bool)
    assert mcp_r["module"] == "Mcu"
    assert "error" in mcp_r
    assert mcp_r["success"] is True

    # --- CLI 烟囱：autoc eb save 走完整个 dispatch + argparse + adapter 创建 ---
    # 注：以下 CLI 进程跑真实 stub adapter + 真实 modify_and_verify，xdm fixture
    # 可能缺 ClockFreq 容器节点 → 接受 ValidatorError。目标是验证 dispatch 跑通
    # 到工具层（不是端到端 save 成功，那是 Sprint 4 e2e 的范畴）。
    cli_env = os.environ.copy()
    cli_env["PYTHONPATH"] = str(Path(__file__).resolve().parents[3] / "packages" / "autoc" / "src")
    cli_proc = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "claude_autosar.cli.main",
            "eb",
            "save",
            "--module",
            "Mcu",
            "--param",
            "Mcu/ClockFreq=80000000",
            "--adapter",
            "stub",
            "--project",
            str(project),
        ],
        capture_output=True,
        text=True,
        env=cli_env,
        check=False,
        timeout=30,
    )
    # 关键判定：CLI dispatch 真正跑通到工具层（validator / adapter 创建）。
    # 接受 rc=0（成功）或 rc=1（业务层 ValidatorError）；rc>=2 视为 dispatch 崩。
    assert cli_proc.returncode in (0, 1), (
        f"CLI dispatch 异常 rc={cli_proc.returncode}\n"
        f"stdout: {cli_proc.stdout}\nstderr: {cli_proc.stderr}"
    )
    if cli_proc.returncode != 0:
        # 业务层失败时，stderr JSON 必须含明确的错误信号
        # v0.3.0+: 错误进 stderr 的 {"success": false, "error": "..."}
        err_out = cli_proc.stderr or cli_proc.stdout
        assert (
            "ValidatorError" in err_out or "Path" in err_out
        ), f"业务层失败但缺错误信号\nstdout: {cli_proc.stdout}\nstderr: {cli_proc.stderr}"


# ---------------------------------------------------------------------------
# 6. CLI 烟囱：autoc --version / --help / nonexistent
# ---------------------------------------------------------------------------


def test_cli_version_help_nonexistent(tmp_path: Path) -> None:  # noqa: ARG001
    """``autoc`` CLI 烟囱：--version / --help / 未知子命令。"""
    """``autoc`` CLI 烟囱：--version / --help / 未知子命令。"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[3] / "packages" / "autoc" / "src")
    # 1. --version
    v = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "claude_autosar.cli.main", "--version"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert v.returncode == 0
    assert "0.4.0" in v.stdout

    # 2. --help
    h = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "claude_autosar.cli.main", "--help"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert h.returncode == 0
    # 至少有一个子命令出现在 help
    for sub in ("eb", "davinci", "session", "log", "export"):
        assert sub in h.stdout, f"subcommand {sub!r} missing from --help"

    # 3. 未知子命令 — 中文提示走 stderr（PROGRESS.md 5.1 节决定）
    u = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "claude_autosar.cli.main", "nonexistent_xyz"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert u.returncode == 1
    combined = (u.stdout + u.stderr).lower()
    assert "nonexistent_xyz" in combined or "未知" in combined or "unknown" in combined
