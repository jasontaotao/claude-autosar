"""Plugin hooks 单元测试。

通过 monkeypatching sys.stdin / subprocess.run 隔离 stdin 输入与外部依赖。
每个 hook 函数抽出来直接调用，避免 fork 子进程。
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
from unittest import mock

import pytest

# 把 plugin hooks 目录加到 sys.path
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = PLUGIN_ROOT / "plugins" / "claude-autosar" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import posttooluse_bsw_validate  # type: ignore[import-not-found]  # noqa: E402

# sys.path 调整必须在 import 之前
import pretooluse_arxml_guard  # type: ignore[import-not-found]  # noqa: E402
import sessionstart_detect_project  # type: ignore[import-not-found]  # noqa: E402

# --- 工具：模拟 Claude Code 事件并捕获 hook 输出 ---


def _run_hook_with_stdin(hook_main, event: dict[str, Any]) -> dict[str, Any]:
    """用给定的 event dict 喂入 hook stdin，捕获 stdout JSON 返回。"""
    stdin_payload = json.dumps(event)
    return _run_hook_with_stdin_raw(hook_main, stdin_payload)


def _run_hook_with_stdin_raw(hook_main, stdin_payload: str) -> dict[str, Any]:
    """直接喂原始 stdin 字符串（用于测 JSON 解析失败等异常路径）。"""
    captured: dict[str, Any] = {}

    def _fake_main() -> int:
        sys.stdin = io.StringIO(stdin_payload)  # type: ignore[assignment]
        old_stdout = sys.stdout
        buf = io.StringIO()
        sys.stdout = buf  # type: ignore[assignment]
        try:
            rc = hook_main()
        finally:
            sys.stdout = old_stdout  # type: ignore[assignment]
            sys.stdin = sys.__stdin__  # type: ignore[assignment]
        captured["_rc"] = rc
        captured["_stdout"] = buf.getvalue()
        return rc

    _fake_main()
    raw = captured["_stdout"].strip()
    if not raw:
        return {"_rc": captured["_rc"]}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_rc": captured["_rc"], "_raw": raw}


def _write_event(tool_name: str, file_path: str, content: str = "") -> dict[str, Any]:
    return {
        "tool_name": tool_name,
        "tool_input": {"file_path": file_path, "content": content},
    }


# --- pretooluse_arxml_guard 测试 ---


class TestArxmlGuard:
    """验证 ARXML 语法拦截。"""

    def test_non_arxml_write_allowed(self) -> None:
        event = _write_event("Write", "/tmp/foo.txt", "hello")
        out = _run_hook_with_stdin(pretooluse_arxml_guard.main, event)
        assert out == {}, f"非 ARXML 应放行，got {out}"

    def test_bash_tool_skipped(self) -> None:
        event = {"tool_name": "Bash", "tool_input": {"command": "ls"}}
        out = _run_hook_with_stdin(pretooluse_arxml_guard.main, event)
        assert out == {}

    def test_valid_arxml_allowed(self) -> None:
        valid = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<AR-PACKAGES xmlns="http://autosar.org/schema/r4.0">\n'
            "  <AR-PACKAGE><SHORT-NAME>Test</SHORT-NAME></AR-PACKAGE>\n"
            "</AR-PACKAGES>\n"
        )
        event = _write_event("Write", "/tmp/Mcu.arxml", valid)
        out = _run_hook_with_stdin(pretooluse_arxml_guard.main, event)
        assert out == {}, f"合法 ARXML 应放行，got {out}"

    def test_malformed_arxml_blocked(self) -> None:
        if not pretooluse_arxml_guard._HAS_LXML:
            pytest.skip("lxml 不可用，跳过")
        event = _write_event("Write", "/tmp/Mcu.arxml", "<AR-PACKAGES><unclosed>")
        out = _run_hook_with_stdin(pretooluse_arxml_guard.main, event)
        assert "hookSpecificOutput" in out
        spec = out["hookSpecificOutput"]
        assert spec["permissionDecision"] == "deny"
        assert "ARXML schema invalid" in spec["permissionDecisionReason"]

    def test_edit_event_uses_new_string(self) -> None:
        if not pretooluse_arxml_guard._HAS_LXML:
            pytest.skip("lxml 不可用，跳过")
        bad_event = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "/tmp/Mcu.arxml",
                "old_string": "<X/>",
                "new_string": "<Y>",  # 缺闭合
            },
        }
        out = _run_hook_with_stdin(pretooluse_arxml_guard.main, bad_event)
        assert "hookSpecificOutput" in out
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_empty_arxml_blocked(self) -> None:
        if not pretooluse_arxml_guard._HAS_LXML:
            pytest.skip("lxml 不可用，跳过")
        event = _write_event("Write", "/tmp/Mcu.arxml", "")
        out = _run_hook_with_stdin(pretooluse_arxml_guard.main, event)
        # 空内容也应被拒绝（不是合法 ARXML）
        assert "hookSpecificOutput" in out
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_malformed_event_does_not_crash(self) -> None:
        # 用真 JSON 解析失败场景（无效 JSON），不是合法 dict
        out = _run_hook_with_stdin_raw(pretooluse_arxml_guard.main, "{not valid json")
        # hook 解析失败不阻断：必须显式 systemMessage（禁止静默放行）
        assert "systemMessage" in out, f"malformed event 应有 systemMessage 显式记录，got {out}"
        assert "error" in out["systemMessage"].lower()

    def test_large_arxml_rejected_to_avoid_oom(self) -> None:
        """> 5MB 的 ARXML 让用户走 `autoc arxml validate`，hook 拒绝以防 OOM。"""
        if not pretooluse_arxml_guard._HAS_LXML:
            pytest.skip("lxml 不可用")
        huge = "<AR-PACKAGES>" + "x" * (6 * 1024 * 1024) + "</AR-PACKAGES>"
        event = _write_event("Write", "/tmp/Big.arxml", huge)
        out = _run_hook_with_stdin(pretooluse_arxml_guard.main, event)
        assert "hookSpecificOutput" in out
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "too large" in out["hookSpecificOutput"]["permissionDecisionReason"].lower()

    def test_deny_emits_both_decision_formats(self) -> None:
        """拒绝时同时输出新版 hookSpecificOutput 与旧版 decision（向后兼容）。"""
        if not pretooluse_arxml_guard._HAS_LXML:
            pytest.skip("lxml 不可用")
        event = _write_event("Write", "/tmp/Mcu.arxml", "<AR-PACKAGES><unclosed>")
        out = _run_hook_with_stdin(pretooluse_arxml_guard.main, event)
        assert out.get("decision") == "block", "旧版顶层 decision 字段缺失"
        assert "reason" in out, "旧版 reason 字段缺失"
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_multiedit_tool_not_intercepted(self) -> None:
        """MultiEdit 已被 matcher 排除（增量多 edit 无法预测最终内容）。"""
        event = {
            "tool_name": "MultiEdit",
            "tool_input": {
                "file_path": "/tmp/Mcu.arxml",
                "edits": [{"old_string": "x", "new_string": "y"}],
            },
        }
        out = _run_hook_with_stdin(pretooluse_arxml_guard.main, event)
        # MultiEdit 不命中 hook → 空对象（无决策）
        assert out == {}, f"MultiEdit 应被 matcher 排除，got {out}"


# --- posttooluse_bsw_validate 测试 ---


class TestBswValidate:
    """验证 .xdm 写完触发 verify。"""

    def test_non_xdm_write_skipped(self) -> None:
        event = _write_event("Write", "/tmp/foo.txt")
        out = _run_hook_with_stdin(posttooluse_bsw_validate.main, event)
        assert out == {}

    def test_bash_tool_skipped(self) -> None:
        event = {"tool_name": "Bash", "tool_input": {}}
        out = _run_hook_with_stdin(posttooluse_bsw_validate.main, event)
        assert out == {}

    def test_xdm_in_prefs_runs_verify(self) -> None:
        event = _write_event("Write", "/path/to/proj/.prefs/Mcu.xdm")
        fake_proc = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="verify: pass\n", stderr=""
        )
        with (
            mock.patch.object(
                posttooluse_bsw_validate.shutil, "which", return_value="/usr/bin/autoc"
            ),
            mock.patch.object(
                posttooluse_bsw_validate.subprocess, "run", return_value=fake_proc
            ) as run_mock,
        ):
            out = _run_hook_with_stdin(posttooluse_bsw_validate.main, event)
        assert run_mock.called
        assert "hookSpecificOutput" in out
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "Mcu.xdm" in ctx
        assert "通过" in ctx

    def test_xdm_outside_prefs_skipped(self) -> None:
        # /tmp/Mcu.xdm 不在 .prefs 目录下，应跳过
        event = _write_event("Write", "/tmp/Mcu.xdm")
        out = _run_hook_with_stdin(posttooluse_bsw_validate.main, event)
        assert out == {}

    def test_autoc_not_in_path_graceful(self) -> None:
        event = _write_event("Write", "/path/.prefs/Mcu.xdm")
        with mock.patch.object(posttooluse_bsw_validate.shutil, "which", return_value=None):
            out = _run_hook_with_stdin(posttooluse_bsw_validate.main, event)
        # 缺 CLI 不应崩溃；用 systemMessage 或 additionalContext 提示
        ctx = out.get("hookSpecificOutput", {}).get("additionalContext", "")
        assert ctx, f"expected additionalContext, got {out}"
        assert "autoc" in ctx.lower()

    def test_verify_failure_includes_stderr(self) -> None:
        event = _write_event("Write", "/path/.prefs/Port.xdm")
        fake_proc = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="validate error: bad path\n"
        )
        with (
            mock.patch.object(
                posttooluse_bsw_validate.shutil, "which", return_value="/usr/bin/autoc"
            ),
            mock.patch.object(posttooluse_bsw_validate.subprocess, "run", return_value=fake_proc),
        ):
            out = _run_hook_with_stdin(posttooluse_bsw_validate.main, event)
        ctx = out.get("hookSpecificOutput", {}).get("additionalContext", "")
        assert ctx, f"expected additionalContext, got {out}"
        assert "失败" in ctx
        assert "validate error" in ctx

    def test_windows_path_separator(self) -> None:
        # Windows 反斜杠路径也应被识别
        event = _write_event("Write", "C:\\proj\\.prefs\\Mcu.xdm")
        fake_proc = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok\n", stderr="")
        with (
            mock.patch.object(
                posttooluse_bsw_validate.shutil, "which", return_value="/usr/bin/autoc"
            ),
            mock.patch.object(
                posttooluse_bsw_validate.subprocess, "run", return_value=fake_proc
            ) as run_mock,
        ):
            out = _run_hook_with_stdin(posttooluse_bsw_validate.main, event)
        assert run_mock.called
        ctx = out.get("hookSpecificOutput", {}).get("additionalContext", "")
        assert ctx

    def test_malformed_event_does_not_crash(self) -> None:
        out = _run_hook_with_stdin(posttooluse_bsw_validate.main, {"oops": 1})
        assert out == {} or "systemMessage" in out


# --- sessionstart_detect_project 测试 ---


class TestSessionStartDetect:
    """验证工程类型检测与上下文注入。"""

    def test_eb_project_detected(self, tmp_path: Path) -> None:
        (tmp_path / ".project").write_text("<project/>", encoding="utf-8")
        event = {"cwd": str(tmp_path)}
        out = _run_hook_with_stdin(sessionstart_detect_project.main, event)
        assert "hookSpecificOutput" in out
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "EB tresos" in ctx
        assert "eb-save" in ctx

    def test_davinci_project_detected(self, tmp_path: Path) -> None:
        (tmp_path / "MyProj.dpa").write_text("dummy", encoding="utf-8")
        event = {"cwd": str(tmp_path)}
        out = _run_hook_with_stdin(sessionstart_detect_project.main, event)
        assert "hookSpecificOutput" in out
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "DaVinci" in ctx
        assert "davinci-verify" in ctx

    def test_arxml_files_listed(self, tmp_path: Path) -> None:
        for n in ("Mcu.arxml", "Port.arxml", "CanIf.arxml"):
            (tmp_path / n).write_text("<?xml?>", encoding="utf-8")
        event = {"cwd": str(tmp_path)}
        out = _run_hook_with_stdin(sessionstart_detect_project.main, event)
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "3 个 ARXML" in ctx
        for n in ("Mcu.arxml", "Port.arxml", "CanIf.arxml"):
            assert n in ctx

    def test_no_project_still_outputs_hint(self, tmp_path: Path) -> None:
        # 空目录
        event = {"cwd": str(tmp_path)}
        out = _run_hook_with_stdin(sessionstart_detect_project.main, event)
        assert "hookSpecificOutput" in out
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "未检测到" in ctx
        assert "arxml-validate" in ctx

    def test_uses_cwd_from_event(self, tmp_path: Path) -> None:
        (tmp_path / ".project").write_text("<p/>", encoding="utf-8")
        # event.cwd 是绝对路径，hook 应使用而非 os.getcwd()
        event = {"cwd": str(tmp_path)}
        with mock.patch("os.getcwd", return_value="/somewhere/else"):
            out = _run_hook_with_stdin(sessionstart_detect_project.main, event)
        assert "EB tresos" in out["hookSpecificOutput"]["additionalContext"]

    def test_invalid_cwd_falls_back_to_cwd_env(self, tmp_path: Path) -> None:
        # cwd 不存在时，hook 应静默返回空
        event = {"cwd": "/this/path/does/not/exist"}
        with mock.patch.dict(os.environ, {}, clear=True):
            out = _run_hook_with_stdin(sessionstart_detect_project.main, event)
        # 不崩溃，输出空对象或带 systemMessage
        assert out == {} or "systemMessage" in out or "additionalContext" in out

    def test_malformed_event_uses_real_cwd(self) -> None:
        # 无 cwd 字段时，hook 用 os.getcwd() 兜底
        out = _run_hook_with_stdin(sessionstart_detect_project.main, {"garbage": True})
        # 无论 cwd 实际状态如何，不应崩溃
        assert isinstance(out, dict)
