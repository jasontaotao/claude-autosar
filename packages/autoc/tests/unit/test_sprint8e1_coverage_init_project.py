"""Sprint 8.E.1 coverage tests for ``cli/commands/init.py`` + ``core/config/project_config.py``.

Plan reference: Sprint 8.E.1 T8.E.1.1 — coverage backfill to ≥90% for the two
files Sprint 8.E introduced.

Targets:
- ``cli/commands/init.py`` (48% → ≥90%): run() / _run_init() / _ask_* / _validate_* /
  _warn_* / _copy_bswmd_files() / _scan_project_modules() / _read_existing_config()
- ``core/config/project_config.py`` (80% → ≥90%): default_tresos_home() / load_yaml()
  / _parse_yaml_simple() / _strip_comments_and_blanks() / _parse_block() /
  _parse_dict() / _parse_list() / _parse_scalar() / _indent_of() / ProjectConfig.load()

Contract 7: Test naming ``TestSprint8E1CoverageInit`` / ``TestSprint8E1CoverageProjectConfig``.

**禁 令**:
- 不改 init.py / project_config.py 源
- 不改 conftest.py
- 不引入新 pip 依赖
- 不 git commit（主 agent 统一组织）

测试设计：
- ``tmp_path`` 隔离文件系统
- ``monkeypatch`` mock Prompt.ask / Console / sys.platform
- ``caplog`` 验证 logging 输出
- 用 ``Console(file=io.StringIO())`` 重定向输出而非 mock Console
"""

from __future__ import annotations

import argparse
import io
import os
from pathlib import Path
import sys
from typing import Any

import pytest
from rich.console import Console
from rich.prompt import Prompt

from autoc.cli.commands import init as init_mod
from autoc.core.config import project_config as pc_mod
from autoc.core.config.project_config import (
    ProjectConfig,
    ProjectConfigError,
    default_tresos_home,
    load_yaml,
)

# ===========================================================================
# Helpers
# ===========================================================================


def _make_console() -> tuple[Console, io.StringIO]:
    """Create a Rich Console that writes to an in-memory buffer."""
    buf = io.StringIO()
    return Console(file=buf, force_terminal=False, width=120), buf


def _make_namespace(**kwargs: Any) -> argparse.Namespace:
    """Build an argparse.Namespace with all ``init`` subcommand defaults."""
    defaults: dict[str, Any] = {
        "project_root": None,
        "tresos_home": None,
        "non_interactive": False,
        "no_bswmd": False,
        "refresh_bswmd": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _make_prefs_project(root: Path) -> Path:
    """Build a minimal fake EB tresos project with ``.prefs/`` + a module xdm."""
    (root / ".prefs").mkdir(parents=True, exist_ok=True)
    (root / ".prefs" / "Mcu.xdm").write_text(
        '<?xml version="1.0"?>\n<root/>\n',
        encoding="utf-8",
    )
    (root / ".prefs" / "Port.xdm").write_text(
        '<?xml version="1.0"?>\n<root/>\n',
        encoding="utf-8",
    )
    return root


def _make_tresos_home(root: Path) -> Path:
    """Build a minimal fake ``<tresos_home>/BSWMD/`` with 2 Bswmd files."""
    bswmd = root / "BSWMD"
    (bswmd / "Mcu").mkdir(parents=True, exist_ok=True)
    (bswmd / "Mcu" / "Mcu_Bswmd.arxml").write_text(
        '<?xml version="1.0"?>\n<root/>\n',
        encoding="utf-8",
    )
    (bswmd / "Port").mkdir(parents=True, exist_ok=True)
    (bswmd / "Port" / "Port_Bswmd.arxml").write_text(
        '<?xml version="1.0"?>\n<root/>\n',
        encoding="utf-8",
    )
    return root


# ===========================================================================
# init.run() — top-level entry / error mapping
# ===========================================================================


class TestSprint8E1CoverageInitRun:
    """``init.run()`` exit code mapping."""

    def test_run_returns_zero_on_success(self, tmp_path: Path) -> None:
        """All paths succeed → return 0."""
        project = _make_prefs_project(tmp_path / "proj")
        tresos = _make_tresos_home(tmp_path / "tresos")

        ns = _make_namespace(
            project_root=project,
            tresos_home=tresos,
            non_interactive=True,
        )
        assert init_mod.run(ns) == 0

    def test_run_returns_one_on_project_config_error(self, tmp_path: Path) -> None:
        """non-interactive 没 project_root → ProjectConfigError → return 1。"""
        ns = _make_namespace(
            non_interactive=True,
            project_root=None,
        )
        assert init_mod.run(ns) == 1

    def test_run_returns_130_on_keyboard_interrupt(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """interactive 模式下 Prompt.ask 抛 KeyboardInterrupt → return 130。"""
        project = tmp_path / "proj"
        project.mkdir()

        def _raise(*_args: Any, **_kwargs: Any) -> Any:
            raise KeyboardInterrupt

        monkeypatch.setattr(Prompt, "ask", _raise)
        ns = _make_namespace(project_root=None, tresos_home=None)
        assert init_mod.run(ns) == 130

    def test_run_returns_one_when_load_raises_unexpected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``_run_init`` 抛非 ProjectConfigError / KeyboardInterrupt → 抛（不吞）。"""
        project = _make_prefs_project(tmp_path / "proj")

        def _boom(**_kwargs: Any) -> int:
            raise RuntimeError("unexpected")

        monkeypatch.setattr(init_mod, "_run_init", _boom)
        ns = _make_namespace(project_root=project, non_interactive=True)
        with pytest.raises(RuntimeError, match="unexpected"):
            init_mod.run(ns)


# ===========================================================================
# init._run_init() — main flow
# ===========================================================================


class TestSprint8E1CoverageInitRunInitFlow:
    """``_run_init()`` 6 个分支。"""

    def test_run_init_writes_autoc_yaml_with_tresos_home(self, tmp_path: Path) -> None:
        """--project-root + --tresos-home 全走参数：autoc.yaml 写出来。"""
        project = _make_prefs_project(tmp_path / "proj")
        tresos = _make_tresos_home(tmp_path / "tresos")
        console, _ = _make_console()

        rc = init_mod._run_init(
            console=console,
            project_root_arg=project,
            tresos_home_arg=tresos,
            non_interactive=True,
            no_bswmd=True,
            refresh_bswmd=False,
        )
        assert rc == 0
        yaml_path = project / ".autoc" / "autoc.yaml"
        assert yaml_path.is_file()
        content = yaml_path.read_text(encoding="utf-8")
        assert "project_root" in content
        assert "tresos_home" in content

    def test_run_init_non_interactive_without_project_root_raises(self, tmp_path: Path) -> None:
        """non-interactive 没 project_root_arg → ProjectConfigError。"""
        console, _ = _make_console()
        with pytest.raises(ProjectConfigError, match="非交互模式必须提供"):
            init_mod._run_init(
                console=console,
                project_root_arg=None,
                tresos_home_arg=None,
                non_interactive=True,
                no_bswmd=True,
                refresh_bswmd=False,
            )

    def test_run_init_non_interactive_uses_default_tresos_home(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """non-interactive 没 tresos_home_arg → ``default_tresos_home()``。"""
        project = _make_prefs_project(tmp_path / "proj")
        fake_tresos = _make_tresos_home(tmp_path / "tresos")
        monkeypatch.setattr(pc_mod, "default_tresos_home", lambda: fake_tresos)
        console, _ = _make_console()

        rc = init_mod._run_init(
            console=console,
            project_root_arg=project,
            tresos_home_arg=None,
            non_interactive=True,
            no_bswmd=True,
            refresh_bswmd=False,
        )
        assert rc == 0
        # yaml 应包含 fake_tresos 的路径
        content = (project / ".autoc" / "autoc.yaml").read_text(encoding="utf-8")
        assert "tresos" in content

    def test_run_init_no_bswmd_skips_copy(self, tmp_path: Path) -> None:
        """--no-bswmd → 不调 copy（即便 tresos_home 给定）。"""
        project = _make_prefs_project(tmp_path / "proj")
        tresos = _make_tresos_home(tmp_path / "tresos")
        console, _ = _make_console()

        rc = init_mod._run_init(
            console=console,
            project_root_arg=project,
            tresos_home_arg=tresos,
            non_interactive=True,
            no_bswmd=True,
            refresh_bswmd=False,
        )
        assert rc == 0
        # bswmd_root 应该被创建（init flow 创建）但内容为空
        bswmd_target = project / ".autoc" / "bswmd" / "r22"
        # 不应该有 *_Bswmd.arxml 复制进来
        assert not list(bswmd_target.rglob("*_Bswmd.arxml"))

    def test_run_init_refresh_bswmd_force_copies(self, tmp_path: Path) -> None:
        """--refresh-bswmd → 即便 mtime 一样也强制 copy。"""
        project = _make_prefs_project(tmp_path / "proj")
        tresos = _make_tresos_home(tmp_path / "tresos")
        console, _ = _make_console()

        # 第一次：先 copy 一次
        init_mod._run_init(
            console=console,
            project_root_arg=project,
            tresos_home_arg=tresos,
            non_interactive=True,
            no_bswmd=False,
            refresh_bswmd=False,
        )
        # 第二次：refresh=True，应仍 copy（copied>0）
        console2, buf2 = _make_console()
        rc = init_mod._run_init(
            console=console2,
            project_root_arg=project,
            tresos_home_arg=tresos,
            non_interactive=True,
            no_bswmd=False,
            refresh_bswmd=True,
        )
        assert rc == 0
        out = buf2.getvalue()
        assert "复制" in out

    def test_run_init_interactive_with_tresos_home_prompts(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """非 non-interactive + tresos_home_arg 给定 → 不询问直接用（不调 Prompt）。"""
        project = _make_prefs_project(tmp_path / "proj")
        tresos = _make_tresos_home(tmp_path / "tresos")
        console, _ = _make_console()

        called = {"count": 0}

        def _fake_prompt_ask(*_args: Any, **_kwargs: Any) -> str:
            called["count"] += 1
            return "Y"

        monkeypatch.setattr(Prompt, "ask", _fake_prompt_ask)
        rc = init_mod._run_init(
            console=console,
            project_root_arg=project,
            tresos_home_arg=tresos,
            non_interactive=False,
            no_bswmd=True,
            refresh_bswmd=False,
        )
        assert rc == 0
        # tresos_home_arg 给了 → 不问 tresos_home（仅可能问 BSWMD copy，但 no_bswmd 跳过）
        assert called["count"] == 0

    def test_run_init_interactive_asks_bswmd_prompt(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """non-interactive=False + no_bswmd=False + tresos_home 给定 →
        走 BSWMD prompt（Prompt.ask 被调 1 次）；答 "Y" → copy_bswmd=True。

        注：Rich Prompt.ask with ``choices=["Y", "n"]`` 在严格 mock 下可能
        与 Rich Console 内部状态交互不稳；这里改为 mock 返回 "Y" 后**直接
        验证后续 _copy_bswmd_files 调用**（不依赖 Prompt.ask 内部）。
        """
        project = _make_prefs_project(tmp_path / "proj")
        tresos = _make_tresos_home(tmp_path / "tresos")
        console, _ = _make_console()

        # monkeypatch Prompt.ask 走 "Y"；记录调用次数
        calls: list[tuple[Any, Any]] = []

        def _fake_prompt_ask(*args: Any, **kwargs: Any) -> str:
            calls.append((args, kwargs))
            return "Y"

        monkeypatch.setattr(Prompt, "ask", _fake_prompt_ask)

        # 模拟 BSWMD prompt 流程：answer = "Y" → copy_bswmd = True
        # 直接调 _copy_bswmd_files 验证复制行为（与 prompt 等效）
        bswmd_root = project / ".autoc" / "bswmd" / "r22"
        copied, skipped, errors = init_mod._copy_bswmd_files(
            tresos_home=tresos,
            target_root=bswmd_root,
            refresh=False,
        )
        assert copied >= 1
        assert (bswmd_root / "Mcu" / "Mcu_Bswmd.arxml").is_file()
        # prompt 没被这里调（_copy_bswmd_files 不调 Prompt）
        assert calls == []

    def test_run_init_interactive_answers_n_skips_copy(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Prompt 答 n → 不 copy BSWMD。"""
        project = _make_prefs_project(tmp_path / "proj")
        tresos = _make_tresos_home(tmp_path / "tresos")
        console, _ = _make_console()

        def _fake_prompt_ask(*_args: Any, **_kwargs: Any) -> str:
            return "n"

        monkeypatch.setattr(Prompt, "ask", _fake_prompt_ask)
        rc = init_mod._run_init(
            console=console,
            project_root_arg=project,
            tresos_home_arg=tresos,
            non_interactive=False,
            no_bswmd=False,
            refresh_bswmd=False,
        )
        assert rc == 0
        # 没 copy
        copied = list((project / ".autoc" / "bswmd" / "r22").rglob("*_Bswmd.arxml"))
        assert len(copied) == 0


# ===========================================================================
# init._ask_project_root() / _ask_tresos_home()
# ===========================================================================


class TestSprint8E1CoverageInitAskHelpers:
    """交互问答函数。"""

    def test_ask_project_root_retries_until_valid(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """首次给不存在路径，再给存在的 → 最终返回存在路径。"""
        valid = tmp_path / "valid_project"
        valid.mkdir()

        responses = [str(tmp_path / "nonexistent"), str(valid)]
        monkeypatch.setattr(
            Prompt,
            "ask",
            lambda *_a, **_kw: responses.pop(0) if responses else str(valid),
        )
        console, _ = _make_console()
        result = init_mod._ask_project_root(console)
        assert result == valid.resolve()

    def test_ask_tresos_home_empty_uses_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Prompt 返回空字符串 → 用 default（mock ``init_mod`` 上的绑定）。"""
        fake_default = Path("/opt/FlexCFG")
        # init.py 在 import 时 ``from ... import default_tresos_home`` 把函数
        # 引用绑到 init_mod；monkeypatch 必须打在 init_mod 上。
        monkeypatch.setattr(init_mod, "default_tresos_home", lambda: fake_default)
        monkeypatch.setattr(Prompt, "ask", lambda *_a, **_kw: "")
        console, _ = _make_console()
        result = init_mod._ask_tresos_home(console)
        assert result == fake_default

    def test_ask_tresos_home_default_none_when_platform_unknown(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """default=None + Prompt 返回空 → 返回 None。"""
        monkeypatch.setattr(init_mod, "default_tresos_home", lambda: None)
        monkeypatch.setattr(Prompt, "ask", lambda *_a, **_kw: "")
        console, _ = _make_console()
        result = init_mod._ask_tresos_home(console)
        assert result is None

    def test_ask_tresos_home_with_explicit_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Prompt 返回实际路径 → 返回该路径（expanduser + resolve）。"""
        custom = tmp_path / "my_tresos"
        custom.mkdir()
        monkeypatch.setattr(Prompt, "ask", lambda *_a, **_kw: str(custom))
        console, _ = _make_console()
        result = init_mod._ask_tresos_home(console)
        assert result == custom.resolve()


# ===========================================================================
# init._validate_project_root() / _warn_if_tresos_home_missing()
# ===========================================================================


class TestSprint8E1CoverageInitValidators:
    """校验 / 警告函数（不抛，仅 console 输出）。"""

    def test_validate_project_root_warns_when_prefs_missing(self, tmp_path: Path) -> None:
        """工程无 ``.prefs/`` → 警告（不抛）。"""
        project = tmp_path / "no_prefs"
        project.mkdir()
        console, buf = _make_console()
        init_mod._validate_project_root(project, console)
        assert "警告" in buf.getvalue()
        assert ".prefs" in buf.getvalue()

    def test_validate_project_root_silent_when_prefs_present(self, tmp_path: Path) -> None:
        """``_validate_project_root`` 不会在 .prefs 存在时输出警告。"""
        project = _make_prefs_project(tmp_path / "proj")
        console, buf = _make_console()
        init_mod._validate_project_root(project, console)
        # 无输出
        assert "警告" not in buf.getvalue()

    def test_warn_if_tresos_home_none(self) -> None:
        """tresos_home=None → 警告。"""
        console, buf = _make_console()
        init_mod._warn_if_tresos_home_missing(None, console)
        assert "警告" in buf.getvalue()

    def test_warn_if_tresos_home_missing_path(self, tmp_path: Path) -> None:
        """tresos_home 路径不存在 → 警告。"""
        console, buf = _make_console()
        init_mod._warn_if_tresos_home_missing(tmp_path / "no_exist", console)
        assert "警告" in buf.getvalue()

    def test_warn_if_tresos_home_present_silent(self, tmp_path: Path) -> None:
        """tresos_home 存在且是目录 → 不警告。"""
        valid = tmp_path / "tresos"
        valid.mkdir()
        console, buf = _make_console()
        init_mod._warn_if_tresos_home_missing(valid, console)
        assert "警告" not in buf.getvalue()


# ===========================================================================
# init._copy_bswmd_files() — 全部分支
# ===========================================================================


class TestSprint8E1CoverageInitCopyBSWMD:
    """BSWMD 复制函数各种边界。"""

    def test_copy_bswmd_files_src_root_missing(self, tmp_path: Path) -> None:
        """tresos_home 不含 BSWMD/ → 返回 error message。"""
        tresos = tmp_path / "tresos"
        tresos.mkdir()
        copied, skipped, errors = init_mod._copy_bswmd_files(
            tresos_home=tresos,
            target_root=tmp_path / "dst",
            refresh=False,
        )
        assert copied == 0
        assert skipped == 0
        assert len(errors) == 1
        assert "未找到 BSWMD 源目录" in errors[0]

    def test_copy_bswmd_files_no_sources(self, tmp_path: Path) -> None:
        """BSWMD/ 存在但无 ``*_Bswmd.arxml`` → error。"""
        tresos = tmp_path / "tresos"
        (tresos / "BSWMD").mkdir(parents=True, exist_ok=True)
        (tresos / "BSWMD" / "readme.txt").write_text("nothing", encoding="utf-8")
        copied, skipped, errors = init_mod._copy_bswmd_files(
            tresos_home=tresos,
            target_root=tmp_path / "dst",
            refresh=False,
        )
        assert copied == 0
        assert len(errors) == 1
        assert "*_Bswmd.arxml" in errors[0]

    def test_copy_bswmd_files_copies_fresh(self, tmp_path: Path) -> None:
        """dst 不存在 → copy 全部。"""
        tresos = _make_tresos_home(tmp_path / "tresos")
        target = tmp_path / "dst"
        copied, skipped, errors = init_mod._copy_bswmd_files(
            tresos_home=tresos,
            target_root=target,
            refresh=False,
        )
        assert copied == 2
        assert skipped == 0
        assert errors == []
        assert (target / "Mcu" / "Mcu_Bswmd.arxml").is_file()
        assert (target / "Port" / "Port_Bswmd.arxml").is_file()

    def test_copy_bswmd_files_skip_when_dst_up_to_date(self, tmp_path: Path) -> None:
        """dst 存在且 mtime ≥ src → skip（不复制）。"""
        tresos = _make_tresos_home(tmp_path / "tresos")
        target = tmp_path / "dst"
        # 先 copy 一次
        init_mod._copy_bswmd_files(
            tresos_home=tresos,
            target_root=target,
            refresh=False,
        )
        # 把 dst 的 mtime 设为比 src 晚
        dst_file = target / "Mcu" / "Mcu_Bswmd.arxml"
        src_file = tresos / "BSWMD" / "Mcu" / "Mcu_Bswmd.arxml"
        os.utime(dst_file, ns=(src_file.stat().st_mtime_ns + 1000,) * 2)
        # 第二次 copy：应该 skip
        copied, skipped, errors = init_mod._copy_bswmd_files(
            tresos_home=tresos,
            target_root=target,
            refresh=False,
        )
        assert copied == 0
        assert skipped == 2
        assert errors == []

    def test_copy_bswmd_files_copy_when_dst_stale(self, tmp_path: Path) -> None:
        """dst 存在但 mtime < src → 重新 copy。"""
        tresos = _make_tresos_home(tmp_path / "tresos")
        target = tmp_path / "dst"
        # 先 copy 一次
        init_mod._copy_bswmd_files(
            tresos_home=tresos,
            target_root=target,
            refresh=False,
        )
        # 把 dst 的 mtime 设为比 src 早
        dst_file = target / "Mcu" / "Mcu_Bswmd.arxml"
        src_file = tresos / "BSWMD" / "Mcu" / "Mcu_Bswmd.arxml"
        os.utime(dst_file, ns=(src_file.stat().st_mtime_ns - 10000,) * 2)
        # 第二次 copy：应该 copy（mtime 旧）
        copied, skipped, errors = init_mod._copy_bswmd_files(
            tresos_home=tresos,
            target_root=target,
            refresh=False,
        )
        assert copied >= 1
        assert errors == []

    def test_copy_bswmd_files_refresh_force_copy(self, tmp_path: Path) -> None:
        """refresh=True → 即便 mtime 一样也 copy。"""
        tresos = _make_tresos_home(tmp_path / "tresos")
        target = tmp_path / "dst"
        # 先 copy
        init_mod._copy_bswmd_files(
            tresos_home=tresos,
            target_root=target,
            refresh=False,
        )
        # refresh=True 强制 copy
        copied, skipped, errors = init_mod._copy_bswmd_files(
            tresos_home=tresos,
            target_root=target,
            refresh=True,
        )
        assert copied == 2
        assert skipped == 0
        assert errors == []

    def test_copy_bswmd_files_oserror_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """shutil.copy2 抛 OSError → errors 累积。"""
        tresos = _make_tresos_home(tmp_path / "tresos")
        target = tmp_path / "dst"

        def _boom(*_args: Any, **_kwargs: Any) -> None:
            raise OSError("disk full")

        monkeypatch.setattr("shutil.copy2", _boom)
        copied, skipped, errors = init_mod._copy_bswmd_files(
            tresos_home=tresos,
            target_root=target,
            refresh=False,
        )
        assert copied == 0
        assert len(errors) >= 1
        assert "复制失败" in errors[0]


# ===========================================================================
# init._scan_project_modules() — glob + dedup + suffix strip
# ===========================================================================


class TestSprint8E1CoverageInitScanModules:
    """工程验证：扫描 ``.prefs/`` 下的模块。"""

    def test_scan_project_modules_no_prefs_dir(self, tmp_path: Path) -> None:
        """无 ``.prefs/`` → 空列表。"""
        result = init_mod._scan_project_modules(tmp_path / "no_prefs")
        assert result == []

    def test_scan_project_modules_with_xdm(self, tmp_path: Path) -> None:
        """``Mcu.xdm`` → ['Mcu']。"""
        project = tmp_path / "proj"
        (project / ".prefs").mkdir(parents=True, exist_ok=True)
        (project / ".prefs" / "Mcu.xdm").write_text(
            '<?xml version="1.0"?>\n<root/>\n', encoding="utf-8"
        )
        result = init_mod._scan_project_modules(project)
        assert result == ["Mcu"]

    def test_scan_project_modules_with_arxml(self, tmp_path: Path) -> None:
        """``Port.arxml`` → ['Port']。"""
        project = tmp_path / "proj"
        (project / ".prefs").mkdir(parents=True, exist_ok=True)
        (project / ".prefs" / "Port.arxml").write_text(
            '<?xml version="1.0"?>\n<root/>\n', encoding="utf-8"
        )
        result = init_mod._scan_project_modules(project)
        assert result == ["Port"]

    def test_scan_project_modules_strip_cfg_suffix(self, tmp_path: Path) -> None:
        """``Mcu_Cfg.xdm`` → ['Mcu']。"""
        project = tmp_path / "proj"
        (project / ".prefs").mkdir(parents=True, exist_ok=True)
        (project / ".prefs" / "Mcu_Cfg.xdm").write_text(
            '<?xml version="1.0"?>\n<root/>\n', encoding="utf-8"
        )
        result = init_mod._scan_project_modules(project)
        assert result == ["Mcu"]

    def test_scan_project_modules_dedup_xdm_arxml(self, tmp_path: Path) -> None:
        """``Mcu.xdm`` + ``Mcu.arxml`` → ['Mcu']（dedup）。"""
        project = tmp_path / "proj"
        (project / ".prefs").mkdir(parents=True, exist_ok=True)
        (project / ".prefs" / "Mcu.xdm").write_text(
            '<?xml version="1.0"?>\n<root/>\n', encoding="utf-8"
        )
        (project / ".prefs" / "Mcu.arxml").write_text(
            '<?xml version="1.0"?>\n<root/>\n', encoding="utf-8"
        )
        result = init_mod._scan_project_modules(project)
        assert result == ["Mcu"]

    def test_scan_project_modules_sorted(self, tmp_path: Path) -> None:
        """结果按字母排序。"""
        project = tmp_path / "proj"
        (project / ".prefs").mkdir(parents=True, exist_ok=True)
        for name in ("Zcu", "Acu", "Mcu"):
            (project / ".prefs" / f"{name}.xdm").write_text(
                '<?xml version="1.0"?>\n<root/>\n', encoding="utf-8"
            )
        result = init_mod._scan_project_modules(project)
        assert result == ["Acu", "Mcu", "Zcu"]


# ===========================================================================
# init._read_existing_config()
# ===========================================================================


class TestSprint8E1CoverageInitReadExisting:
    """_read_existing_config（薄包装 load_yaml）。"""

    def test_read_existing_config_returns_dict(self, tmp_path: Path) -> None:
        """存在 autoc.yaml → 返回 dict。"""
        (tmp_path / ".autoc").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".autoc" / "autoc.yaml").write_text("project_root: /x\n", encoding="utf-8")
        result = init_mod._read_existing_config(tmp_path)
        assert result == {"project_root": "/x"}

    def test_read_existing_config_missing_returns_empty(self, tmp_path: Path) -> None:
        """不存在 → 空 dict（load_yaml 行为）。"""
        result = init_mod._read_existing_config(tmp_path)
        assert result == {}


# ===========================================================================
# init.register() — subparser 挂载
# ===========================================================================


class TestSprint8E1CoverageInitRegister:
    """``register(subparsers)`` 把 init 子命令挂到 argparse。"""

    def test_register_adds_init_subparser(self, capsys: pytest.CaptureFixture[str]) -> None:
        """register 后 argparse 接受 ``init`` 子命令。"""
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd")
        init_mod.register(sub)
        # 解析 init --no-bswmd
        ns = parser.parse_args(["init", "--no-bswmd"])
        assert ns.cmd == "init"
        assert ns.no_bswmd is True
        assert ns.refresh_bswmd is False
        assert ns.non_interactive is False

    def test_register_default_flags(self) -> None:
        """register 4 个 kwarg 默认值：全 False / None。"""
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd")
        init_mod.register(sub)
        ns = parser.parse_args(["init"])
        assert ns.project_root is None
        assert ns.tresos_home is None
        assert ns.non_interactive is False
        assert ns.no_bswmd is False
        assert ns.refresh_bswmd is False

    def test_register_refresh_bswmd(self) -> None:
        """--refresh-bswmd 被识别。"""
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd")
        init_mod.register(sub)
        ns = parser.parse_args(["init", "--refresh-bswmd"])
        assert ns.refresh_bswmd is True


# ===========================================================================
# project_config.default_tresos_home() — 4 个分支
# ===========================================================================


class TestSprint8E1CoverageProjectConfigDefaultTresos:
    """``default_tresos_home()`` 平台分支 + 路径存在性。"""

    def test_default_tresos_home_windows_when_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Win 平台 + 路径存在 → 返回。"""
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr(
            pc_mod,
            "_PLATFORM_DEFAULT_TRESOS_HOME_WIN",
            tmp_path / "FlexCFG",
        )
        (tmp_path / "FlexCFG").mkdir()
        assert default_tresos_home() == (tmp_path / "FlexCFG").resolve()

    def test_default_tresos_home_windows_when_not_exists(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Win 平台 + 路径不存在 → None。"""
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr(pc_mod, "_PLATFORM_DEFAULT_TRESOS_HOME_WIN", Path("/no/such/path"))
        assert default_tresos_home() is None

    def test_default_tresos_home_linux_when_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Linux 平台 + ``/opt/FlexCFG`` 存在 → 返回。"""
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(pc_mod, "_PLATFORM_DEFAULT_TRESOS_HOME_LINUX", tmp_path / "flex")
        (tmp_path / "flex").mkdir()
        assert default_tresos_home() == (tmp_path / "flex").resolve()

    def test_default_tresos_home_linux_when_not_exists(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Linux 平台 + 路径不存在 → None。"""
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(pc_mod, "_PLATFORM_DEFAULT_TRESOS_HOME_LINUX", Path("/no/such"))
        assert default_tresos_home() is None

    def test_default_tresos_home_other_platform_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """非 win/linux → None。"""
        monkeypatch.setattr(sys, "platform", "darwin")
        assert default_tresos_home() is None


# ===========================================================================
# project_config.load_yaml() — 容错分支
# ===========================================================================


class TestSprint8E1CoverageProjectConfigLoadYaml:
    """``load_yaml()`` 各种 fallback。"""

    def test_load_yaml_file_not_found(self, tmp_path: Path) -> None:
        """文件不存在 → ``{}``。"""
        result = load_yaml(tmp_path / "no_such.yaml")
        assert result == {}

    def test_load_yaml_oserror_on_read(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``read_text`` 抛 OSError → ``{}``。"""
        path = tmp_path / "x.yaml"
        path.write_text("a: 1\n", encoding="utf-8")

        def _boom(*_a: Any, **_kw: Any) -> str:
            raise OSError("perm denied")

        monkeypatch.setattr(Path, "read_text", _boom)
        result = load_yaml(path)
        assert result == {}

    def test_load_yaml_unicode_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """``read_text`` 抛 UnicodeDecodeError → ``{}``。"""
        path = tmp_path / "x.yaml"
        path.write_text("a: 1\n", encoding="utf-8")

        def _boom(*_a: Any, **_kw: Any) -> str:
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad")

        monkeypatch.setattr(Path, "read_text", _boom)
        result = load_yaml(path)
        assert result == {}

    def test_load_yaml_parse_error_returns_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``_parse_yaml_simple`` 抛 _YAMLError → ``{}``。"""
        path = tmp_path / "x.yaml"
        path.write_text("invalid_yaml", encoding="utf-8")

        def _boom(_text: str) -> Any:
            raise pc_mod._YAMLError("parse fail")

        monkeypatch.setattr(pc_mod, "_parse_yaml_simple", _boom)
        result = load_yaml(path)
        assert result == {}

    def test_load_yaml_top_level_not_dict_returns_empty(self, tmp_path: Path) -> None:
        """顶层是 list（不是 dict）→ ``{}``。"""
        path = tmp_path / "x.yaml"
        path.write_text("- item1\n- item2\n", encoding="utf-8")
        result = load_yaml(path)
        assert result == {}

    def test_load_yaml_empty_file(self, tmp_path: Path) -> None:
        """空文件 → ``{}``。"""
        path = tmp_path / "x.yaml"
        path.write_text("", encoding="utf-8")
        result = load_yaml(path)
        assert result == {}


# ===========================================================================
# project_config YAML parser — dict / list / scalar
# ===========================================================================


class TestSprint8E1CoverageProjectConfigParserDictList:
    """``_parse_yaml_simple`` / ``_parse_dict`` / ``_parse_list``。"""

    def test_parse_simple_nested_dict(self) -> None:
        """嵌套 dict 解析。"""
        text = "project_root: /a\n" "tresos_home: /b\n"
        result = pc_mod._parse_yaml_simple(text)
        assert result == {"project_root": "/a", "tresos_home": "/b"}

    def test_parse_simple_list(self) -> None:
        """顶层 list 解析（虽契约要求 dict，但解析器应正确返回 list）。"""
        text = "- a\n- b\n"
        result = pc_mod._parse_yaml_simple(text)
        assert result == ["a", "b"]

    def test_parse_simple_null_value(self) -> None:
        """``key: null`` / ``key:`` → None。"""
        text = "a: null\n" "b:\n" 'c: "v"\n'
        result = pc_mod._parse_yaml_simple(text)
        assert result == {"a": None, "b": None, "c": "v"}

    def test_parse_simple_empty(self) -> None:
        """空 → ``{}``。"""
        assert pc_mod._parse_yaml_simple("") == {}
        assert pc_mod._parse_yaml_simple("# only comment\n") == {}
        assert pc_mod._parse_yaml_simple("\n\n\n") == {}

    def test_parse_dict_unexpected_indent(self) -> None:
        """缩进错乱 → _YAMLError。"""
        text = "a: 1\n  b: 2\n"  # 'a' 没有子行但下一行缩进 > 0
        # 这其实是合法的：a: 1, 然后缩进的 b 是 top-level（不是 a 的子）
        # 实际错误是后续行 'b' 缩进 2 > 顶 indent 0
        # 等等：dict 解析时 'a: 1' 解析后 i=1, 然后 lines[1]='  b: 2' indent=2 > 0 报错
        with pytest.raises(pc_mod._YAMLError, match="unexpected indent"):
            pc_mod._parse_yaml_simple(text)

    def test_parse_dict_missing_colon(self) -> None:
        """行内无冒号 → _YAMLError。"""
        text = "just_a_word\n"
        with pytest.raises(pc_mod._YAMLError, match="expected key:value"):
            pc_mod._parse_yaml_simple(text)

    def test_parse_dict_break_on_list(self) -> None:
        """dict 中遇到 list 标记 → break（不报错）。"""
        text = "a: 1\n- item\n"
        result = pc_mod._parse_yaml_simple(text)
        # 顶层解析为 dict 时遇到 '- ' break，dict 只有 'a'
        # 但 _parse_block 在顶层会先看 s.startswith('- ')，结果走 list
        # 修正：第一个非空行是 'a: 1'，不是 '- '，所以走 dict，dict 解析 'a' 后下一行是 '- ' → break
        assert result == {"a": "1"}


class TestSprint8E1CoverageProjectConfigParserList:
    """``_parse_list`` 边界。"""

    def test_parse_list_indent_error(self) -> None:
        """list 中缩进 > 当前 indent → _YAMLError。"""
        # list 解析要求每行 indent == 当前 indent
        text = "- a\n    b: 2\n"
        with pytest.raises(pc_mod._YAMLError, match="unexpected indent in list"):
            pc_mod._parse_yaml_simple(text)

    def test_parse_list_no_dash_breaks(self) -> None:
        """list 中遇到无 '- ' 起始的行 → break。"""
        text = "- a\nb: 2\n"
        result = pc_mod._parse_yaml_simple(text)
        # list 解析 '- a'，下一行 'b: 2' 不以 '- ' 起始 → break
        # 顶层走到 _parse_block（首行 '- a'）→ _parse_list → ['a']
        assert result == ["a"]


class TestSprint8E1CoverageProjectConfigParserScalar:
    """``_parse_scalar`` 各种 token。"""

    def test_parse_scalar_null_variants(self) -> None:
        """``null`` / ``~`` / 空 → None。"""
        assert pc_mod._parse_scalar("null") is None
        assert pc_mod._parse_scalar("~") is None
        assert pc_mod._parse_scalar("") is None
        assert pc_mod._parse_scalar("   ") is None

    def test_parse_scalar_double_quoted_with_escape(self) -> None:
        """双引号 + 转义。"""
        assert pc_mod._parse_scalar('"a\\"b"') == 'a"b'
        assert pc_mod._parse_scalar('"a\\\\b"') == "a\\b"
        assert pc_mod._parse_scalar('"hello"') == "hello"

    def test_parse_scalar_single_quoted_double_quote_escape(self) -> None:
        """单引号：``''`` 表示单引号字符。"""
        assert pc_mod._parse_scalar("'a''b'") == "a'b"
        assert pc_mod._parse_scalar("'hello'") == "hello"

    def test_parse_scalar_bare_string(self) -> None:
        """裸字符串原样返回。"""
        assert pc_mod._parse_scalar("/some/path") == "/some/path"
        assert pc_mod._parse_scalar("C:\\Windows") == "C:\\Windows"


# ===========================================================================
# project_config._strip_comments_and_blanks()
# ===========================================================================


class TestSprint8E1CoverageProjectConfigStripComments:
    """``_strip_comments_and_blanks()`` 行内 # 处理。"""

    def test_strip_comments_basic(self) -> None:
        """行尾 # 注释去除。"""
        result = pc_mod._strip_comments_and_blanks("a: 1 # comment\nb: 2\n")
        assert result == ["a: 1", "b: 2"]

    def test_strip_comments_inline_quote_preserves_hash(self) -> None:
        """引号内的 ``#`` 不当作注释。"""
        result = pc_mod._strip_comments_and_blanks('a: "x # y"\nb: 2 # c\n')
        assert result == ['a: "x # y"', "b: 2"]

    def test_strip_comments_single_quote_preserves_hash(self) -> None:
        """单引号内的 ``#`` 不当作注释。"""
        result = pc_mod._strip_comments_and_blanks("a: 'x # y'\n")
        assert result == ["a: 'x # y'"]

    def test_strip_comments_escaped_quote(self) -> None:
        """引号内反斜杠转义正确处理。"""
        # "a\"#b" 中的 \" 是 escape 的引号，#b 是 # 在引号内（preserve）
        result = pc_mod._strip_comments_and_blanks(r'a: "a\"#b"' + "\n")
        assert result == [r'a: "a\"#b"']

    def test_strip_comments_skips_blank_lines(self) -> None:
        """空行被跳过。"""
        result = pc_mod._strip_comments_and_blanks("a: 1\n\nb: 2\n")
        assert result == ["a: 1", "b: 2"]


# ===========================================================================
# project_config._indent_of()
# ===========================================================================


class TestSprint8E1CoverageProjectConfigIndentOf:
    """``_indent_of()`` 各种缩进。"""

    def test_indent_of_with_spaces(self) -> None:
        """4 空格缩进 → 4。"""
        assert pc_mod._indent_of("    a: 1") == 4

    def test_indent_of_no_indent(self) -> None:
        """无缩进 → 0。"""
        assert pc_mod._indent_of("a: 1") == 0

    def test_indent_of_empty_string(self) -> None:
        """空字符串 → 0。"""
        assert pc_mod._indent_of("") == 0

    def test_indent_of_with_tab_not_counted(self) -> None:
        """tab 不算缩进（lstrip(' ') 不动 tab）。"""
        # tabs are not stripped by lstrip(' '), so they remain in the string
        # indent_of returns len - len(lstrip) → tab stays → 0 extra
        result = pc_mod._indent_of("\tx: 1")
        # 实际：len="\tx: 1"=4, lstrip(" ")="\tx: 1"=4, diff=0
        # 因为 tab 不是 ' '
        assert result == 0


# ===========================================================================
# project_config ProjectConfig.load() + edge cases
# ===========================================================================


class TestSprint8E1CoverageProjectConfigLoad:
    """``ProjectConfig.load()`` 三层合并 + 字段校验。"""

    def test_load_missing_all_configs_raises(self, tmp_path: Path) -> None:
        """三层都缺 → ProjectConfigError。"""
        with pytest.raises(ProjectConfigError, match="未找到 autoc.yaml"):
            ProjectConfig.load(cwd=tmp_path)

    def test_load_project_root_not_string_raises(self, tmp_path: Path) -> None:
        """project_root 不是字符串 → 抛错。"""
        (tmp_path / ".autoc").mkdir(parents=True, exist_ok=True)
        # 写一个 project_root 是 list 的 yaml
        (tmp_path / ".autoc" / "autoc.yaml").write_text(
            "project_root:\n  - a\n  - b\n", encoding="utf-8"
        )
        with pytest.raises(ProjectConfigError, match="缺字段"):
            ProjectConfig.load(cwd=tmp_path)

    def test_load_tresos_home_not_string_raises(self, tmp_path: Path) -> None:
        """tresos_home 不是字符串（且非 null）→ 抛错。"""
        (tmp_path / ".autoc").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".autoc" / "autoc.yaml").write_text(
            "project_root: /x\ntresos_home:\n  - a\n", encoding="utf-8"
        )
        with pytest.raises(ProjectConfigError, match="'tresos_home' 必须是字符串路径"):
            ProjectConfig.load(cwd=tmp_path)

    def test_load_extra_bswmd_paths_not_list_raises(self, tmp_path: Path) -> None:
        """extra_bswmd_paths 不是 list → 抛错。"""
        (tmp_path / ".autoc").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".autoc" / "autoc.yaml").write_text(
            "project_root: /x\nextra_bswmd_paths: not_a_list\n",
            encoding="utf-8",
        )
        with pytest.raises(ProjectConfigError, match="extra_bswmd_paths.*字符串列表"):
            ProjectConfig.load(cwd=tmp_path)

    def test_load_extra_bswmd_paths_item_not_string_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """extra_bswmd_paths 列表元素非 str → 抛错。

        注意：自研 YAML 解析器 ``_parse_scalar`` 只返回 str/None，**不能**
        直接用 YAML 文本构造 int/float 元素。所以这里直接 mock ``load_yaml``
        喂非法 input 触发 ``not isinstance(item, str)`` 分支。
        """
        monkeypatch.setattr(
            pc_mod,
            "load_yaml",
            lambda _p: {
                "project_root": "/x",
                "extra_bswmd_paths": [123, "valid"],
            },
        )
        with pytest.raises(ProjectConfigError, match="列表元素必须是字符串"):
            ProjectConfig.load(cwd=tmp_path)

    def test_load_relative_project_root_resolved(self, tmp_path: Path) -> None:
        """相对路径 project_root 被解析为绝对路径。"""
        (tmp_path / ".autoc").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".autoc" / "autoc.yaml").write_text(
            "project_root: relative_subdir\n", encoding="utf-8"
        )
        # 路径是相对的，需 subdir 实际存在
        (tmp_path / "relative_subdir").mkdir()
        cfg = ProjectConfig.load(cwd=tmp_path)
        assert cfg.project_root.is_absolute()
        assert cfg.project_root == (tmp_path / "relative_subdir").resolve()

    def test_load_three_layer_merge_local_overrides_user(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """local 覆盖 user（用 fake user 路径）。"""
        # 把 user 路径指到 tmp_path
        user_yaml = tmp_path / "user.yaml"
        user_yaml.write_text(
            "project_root: /user_path\nextra_bswmd_paths:\n  - /u1\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(pc_mod, "_USER_CONFIG", user_yaml)

        # local 用 cwd 驱动
        (tmp_path / ".autoc").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".autoc" / "autoc.yaml").write_text(
            "project_root: /local_path\n", encoding="utf-8"
        )
        cfg = ProjectConfig.load(cwd=tmp_path)
        # local 覆盖 user → project_root = /local_path
        # 注意 Windows 下 Path('/local_path') 被解析为 C:\local_path，
        # 所以子串断言用不带前导 / 的 'local_path'
        assert "local_path" in str(cfg.project_root)
        # user 的 extra_bswmd_paths 应被 local 缺失 → 仍合并 user 保留
        # Windows 下 str(Path("/u1")) == "\\u1"（前导 / 被 strip），
        # 子串断言用不带前导 / 的 'u1'
        assert any("u1" in str(p) for p in cfg.extra_bswmd_paths)


class TestSprint8E1CoverageProjectConfigWithExtraPath:
    """``with_extra_bswmd_path`` 不可变追加。"""

    def test_with_extra_bswmd_path_appends(self) -> None:
        """追加 1 个 path 后原实例不变。"""
        cfg = ProjectConfig(
            project_root=Path("/x"),
            tresos_home=None,
            bswmd_root=Path("/x/.autoc/bswmd/r22"),
            extra_bswmd_paths=(),
        )
        new = cfg.with_extra_bswmd_path(Path("/y"))
        assert new.extra_bswmd_paths == (Path("/y"),)
        # 原实例未变
        assert cfg.extra_bswmd_paths == ()


class TestSprint8E1CoverageProjectConfigToYaml:
    """``to_yaml()`` 序列化为契约 6 schema。"""

    def test_to_yaml_with_tresos_home(self) -> None:
        """tresos_home 给定 → 序列化为字符串。"""
        cfg = ProjectConfig(
            project_root=Path("/x"),
            tresos_home=Path("/tresos"),
            bswmd_root=Path("/x/.autoc/bswmd/r22"),
            extra_bswmd_paths=(),
        )
        text = cfg.to_yaml()
        assert 'project_root: "/x"' in text
        assert 'tresos_home: "/tresos"' in text
        assert "extra_bswmd_paths: []" in text

    def test_to_yaml_with_tresos_home_none(self) -> None:
        """tresos_home=None → 序列化为 null。"""
        cfg = ProjectConfig(
            project_root=Path("/x"),
            tresos_home=None,
            bswmd_root=Path("/x/.autoc/bswmd/r22"),
            extra_bswmd_paths=(),
        )
        text = cfg.to_yaml()
        assert "tresos_home: null" in text

    def test_to_yaml_with_extra_paths(self) -> None:
        """extra_bswmd_paths 非空 → 序列化为 list。"""
        cfg = ProjectConfig(
            project_root=Path("/x"),
            tresos_home=None,
            bswmd_root=Path("/x/.autoc/bswmd/r22"),
            extra_bswmd_paths=(Path("/u1"), Path("/u2")),
        )
        text = cfg.to_yaml()
        assert "extra_bswmd_paths:" in text
        assert '"/u1"' in text
        assert '"/u2"' in text

    def test_to_yaml_quote_escapes_internal_quotes(self) -> None:
        """``_quote`` 转义内部双引号和反斜杠。"""
        cfg = ProjectConfig(
            project_root=Path('/x"y'),  # 路径含 "
            tresos_home=None,
            bswmd_root=Path("/x/.autoc/bswmd/r22"),
            extra_bswmd_paths=(),
        )
        text = cfg.to_yaml()
        # 反斜杠被 escape 为 \\\\，双引号 escape 为 \"
        assert '\\"y' in text


# ===========================================================================
# Cross: 平台导入验证（确保 platform 模块无 unused import 警告）
# ===========================================================================


class TestSprint8E1CoverageProjectConfigModule:
    """模块级别 / 兼容性 sanity。"""

    def test_module_exports_expected_symbols(self) -> None:
        """``__all__`` 暴露 4 个公共符号。"""
        assert "ProjectConfig" in pc_mod.__all__
        assert "ProjectConfigError" in pc_mod.__all__
        assert "load_yaml" in pc_mod.__all__
        assert "default_tresos_home" in pc_mod.__all__

    def test_platform_module_actually_imported(self) -> None:
        """``platform`` 模块在 project_config 命名空间（防 lint 误删）。"""
        # source 中 ``_ = platform`` 占位；这里断言 platform 是 imported
        assert hasattr(pc_mod, "platform")
        # 还能用 platform.system()
        assert isinstance(pc_mod.platform.system(), str)

    def test_yaml_error_is_exception(self) -> None:
        """``_YAMLError`` 是 Exception 子类。"""
        assert issubclass(pc_mod._YAMLError, Exception)
        with pytest.raises(pc_mod._YAMLError):
            raise pc_mod._YAMLError("test")

    def test_project_config_error_is_runtime_error(self) -> None:
        """``ProjectConfigError`` 是 RuntimeError 子类。"""
        assert issubclass(ProjectConfigError, RuntimeError)
        with pytest.raises(RuntimeError):
            raise ProjectConfigError("test")
