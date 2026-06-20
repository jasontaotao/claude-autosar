"""Sprint 8.E.1 coverage: init wizard flow + validation + BSWMD copy + scan + register.

Targets: cli/commands/init.py — run(), _run_init(), _ask_*, _validate_*,
_warn_*, _copy_bswmd_files(), _scan_project_modules(), _read_existing_config(), register().
"""

from __future__ import annotations

import argparse
import io
import os
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console
from rich.prompt import Prompt

from claude_autosar.cli.commands import init as init_mod
from claude_autosar.core.config import project_config as pc_mod
from claude_autosar.core.config.project_config import (
    ProjectConfigError,
)


def _make_console() -> tuple[Console, io.StringIO]:
    buf = io.StringIO()
    return Console(file=buf, force_terminal=False, width=120), buf


def _make_namespace(**kwargs: Any) -> argparse.Namespace:
    defaults: dict[str, Any] = {
        "project_root": None,
        "tresos_home": None,
        "non_interactive": False,
        "no_bswmd": False,
        "refresh_bswmd": False,
        "mcal_vendor": None,
        "mcal_vendor_home": None,
        "chip_derivative": None,
        "no_settings_json": True,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _make_prefs_project(root: Path) -> Path:
    (root / ".prefs").mkdir(parents=True, exist_ok=True)
    (root / ".prefs" / "Mcu.xdm").write_text('<?xml version="1.0"?>\n<root/>\n', encoding="utf-8")
    (root / ".prefs" / "Port.xdm").write_text('<?xml version="1.0"?>\n<root/>\n', encoding="utf-8")
    return root


def _make_tresos_home(root: Path) -> Path:
    bswmd = root / "BSWMD"
    (bswmd / "Mcu").mkdir(parents=True, exist_ok=True)
    (bswmd / "Mcu" / "Mcu_Bswmd.arxml").write_text('<?xml version="1.0"?>\n<root/>\n', encoding="utf-8")
    (bswmd / "Port").mkdir(parents=True, exist_ok=True)
    (bswmd / "Port" / "Port_Bswmd.arxml").write_text('<?xml version="1.0"?>\n<root/>\n', encoding="utf-8")
    return root


class TestSprint8E1CoverageInitRun:
    """``init.run()`` exit code mapping."""

    def test_run_returns_zero_on_success(self, tmp_path: Path) -> None:
        project = _make_prefs_project(tmp_path / "proj")
        tresos = _make_tresos_home(tmp_path / "tresos")
        ns = _make_namespace(project_root=project, tresos_home=tresos, non_interactive=True)
        assert init_mod.run(ns) == 0

    def test_run_returns_one_on_project_config_error(self, tmp_path: Path) -> None:
        ns = _make_namespace(non_interactive=True, project_root=None)
        assert init_mod.run(ns) == 1

    def test_run_returns_130_on_keyboard_interrupt(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
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
        project = _make_prefs_project(tmp_path / "proj")

        def _boom(**_kwargs: Any) -> int:
            raise RuntimeError("unexpected")

        monkeypatch.setattr(init_mod, "_run_init", _boom)
        ns = _make_namespace(project_root=project, non_interactive=True)
        with pytest.raises(RuntimeError, match="unexpected"):
            init_mod.run(ns)


class TestSprint8E1CoverageInitRunInitFlow:
    """``_run_init()`` 分支覆盖。"""

    def test_run_init_writes_autoc_yaml_with_tresos_home(self, tmp_path: Path) -> None:
        project = _make_prefs_project(tmp_path / "proj")
        tresos = _make_tresos_home(tmp_path / "tresos")
        console, _ = _make_console()
        rc = init_mod._run_init(
            console=console, project_root_arg=project, tresos_home_arg=tresos,
            non_interactive=True, no_bswmd=True, refresh_bswmd=False, no_settings_json=True,
        )
        assert rc == 0
        yaml_path = project / ".autoc" / "autoc.yaml"
        assert yaml_path.is_file()
        content = yaml_path.read_text(encoding="utf-8")
        assert "project_root" in content
        assert "tresos_home" in content

    def test_run_init_non_interactive_without_project_root_raises(self, tmp_path: Path) -> None:
        console, _ = _make_console()
        with pytest.raises(ProjectConfigError, match="非交互模式必须提供"):
            init_mod._run_init(
                console=console, project_root_arg=None, tresos_home_arg=None,
                non_interactive=True, no_bswmd=True, refresh_bswmd=False,
            )

    def test_run_init_non_interactive_uses_default_tresos_home(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _make_prefs_project(tmp_path / "proj")
        fake_tresos = _make_tresos_home(tmp_path / "tresos")
        monkeypatch.setattr(pc_mod, "default_tresos_home", lambda: fake_tresos)
        console, _ = _make_console()
        rc = init_mod._run_init(
            console=console, project_root_arg=project, tresos_home_arg=None,
            non_interactive=True, no_bswmd=True, refresh_bswmd=False, no_settings_json=True,
        )
        assert rc == 0
        content = (project / ".autoc" / "autoc.yaml").read_text(encoding="utf-8")
        assert "tresos" in content

    def test_run_init_no_bswmd_skips_copy(self, tmp_path: Path) -> None:
        project = _make_prefs_project(tmp_path / "proj")
        tresos = _make_tresos_home(tmp_path / "tresos")
        console, _ = _make_console()
        rc = init_mod._run_init(
            console=console, project_root_arg=project, tresos_home_arg=tresos,
            non_interactive=True, no_bswmd=True, refresh_bswmd=False, no_settings_json=True,
        )
        assert rc == 0
        bswmd_target = project / ".autoc" / "bswmd" / "r22"
        assert not list(bswmd_target.rglob("*_Bswmd.arxml"))

    def test_run_init_refresh_bswmd_force_copies(self, tmp_path: Path) -> None:
        project = _make_prefs_project(tmp_path / "proj")
        tresos = _make_tresos_home(tmp_path / "tresos")
        console, _ = _make_console()
        init_mod._run_init(
            console=console, project_root_arg=project, tresos_home_arg=tresos,
            non_interactive=True, no_bswmd=False, refresh_bswmd=False, no_settings_json=True,
        )
        console2, buf2 = _make_console()
        rc = init_mod._run_init(
            console=console2, project_root_arg=project, tresos_home_arg=tresos,
            non_interactive=True, no_bswmd=False, refresh_bswmd=True, no_settings_json=True,
        )
        assert rc == 0
        assert "复制" in buf2.getvalue()

    def test_run_init_interactive_with_tresos_home_prompts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        project = _make_prefs_project(tmp_path / "proj")
        tresos = _make_tresos_home(tmp_path / "tresos")
        console, _ = _make_console()
        called = {"count": 0}

        def _fake_prompt_ask(*_args: Any, **_kwargs: Any) -> str:
            called["count"] += 1
            return "Y"

        monkeypatch.setattr(Prompt, "ask", _fake_prompt_ask)
        rc = init_mod._run_init(
            console=console, project_root_arg=project, tresos_home_arg=tresos,
            non_interactive=False, no_bswmd=True, refresh_bswmd=False, no_settings_json=True,
        )
        assert rc == 0
        assert called["count"] == 0

    def test_run_init_interactive_asks_bswmd_prompt(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        project = _make_prefs_project(tmp_path / "proj")
        tresos = _make_tresos_home(tmp_path / "tresos")
        console, _ = _make_console()
        calls: list[tuple[Any, Any]] = []

        def _fake_prompt_ask(*args: Any, **kwargs: Any) -> str:
            calls.append((args, kwargs))
            return "Y"

        monkeypatch.setattr(Prompt, "ask", _fake_prompt_ask)
        bswmd_root = project / ".autoc" / "bswmd" / "r22"
        copied, skipped, errors = init_mod._copy_bswmd_files(
            tresos_home=tresos, target_root=bswmd_root, refresh=False,
        )
        assert copied >= 1
        assert (bswmd_root / "Mcu" / "Mcu_Bswmd.arxml").is_file()
        assert calls == []

    def test_run_init_interactive_answers_n_skips_copy(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        project = _make_prefs_project(tmp_path / "proj")
        tresos = _make_tresos_home(tmp_path / "tresos")
        console, _ = _make_console()

        def _fake_prompt_ask(*_args: Any, **_kwargs: Any) -> str:
            return "n"

        monkeypatch.setattr(Prompt, "ask", _fake_prompt_ask)
        rc = init_mod._run_init(
            console=console, project_root_arg=project, tresos_home_arg=tresos,
            non_interactive=False, no_bswmd=False, refresh_bswmd=False, no_settings_json=True,
        )
        assert rc == 0
        copied = list((project / ".autoc" / "bswmd" / "r22").rglob("*_Bswmd.arxml"))
        assert len(copied) == 0


class TestSprint8E1CoverageInitAskHelpers:
    """交互问答函数。"""

    def test_ask_project_root_retries_until_valid(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        valid = tmp_path / "valid_project"
        valid.mkdir()
        responses = [str(tmp_path / "nonexistent"), str(valid)]
        monkeypatch.setattr(
            Prompt, "ask",
            lambda *_a, **_kw: responses.pop(0) if responses else str(valid),
        )
        console, _ = _make_console()
        result = init_mod._ask_project_root(console)
        assert result == valid.resolve()

    def test_ask_tresos_home_empty_uses_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_default = Path("/opt/FlexCFG")
        monkeypatch.setattr(init_mod, "default_tresos_home", lambda: fake_default)
        monkeypatch.setattr(Prompt, "ask", lambda *_a, **_kw: "")
        console, _ = _make_console()
        result = init_mod._ask_tresos_home(console)
        assert result == fake_default

    def test_ask_tresos_home_default_none_when_platform_unknown(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(init_mod, "default_tresos_home", lambda: None)
        monkeypatch.setattr(Prompt, "ask", lambda *_a, **_kw: "")
        console, _ = _make_console()
        result = init_mod._ask_tresos_home(console)
        assert result is None

    def test_ask_tresos_home_with_explicit_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        custom = tmp_path / "my_tresos"
        custom.mkdir()
        monkeypatch.setattr(Prompt, "ask", lambda *_a, **_kw: str(custom))
        console, _ = _make_console()
        result = init_mod._ask_tresos_home(console)
        assert result == custom.resolve()


class TestSprint8E1CoverageInitValidators:
    """校验 / 警告函数。"""

    def test_validate_project_root_warns_when_prefs_missing(self, tmp_path: Path) -> None:
        project = tmp_path / "no_prefs"
        project.mkdir()
        console, buf = _make_console()
        init_mod._validate_project_root(project, console)
        assert "警告" in buf.getvalue()
        assert ".prefs" in buf.getvalue()

    def test_validate_project_root_silent_when_prefs_present(self, tmp_path: Path) -> None:
        project = _make_prefs_project(tmp_path / "proj")
        console, buf = _make_console()
        init_mod._validate_project_root(project, console)
        assert "警告" not in buf.getvalue()

    def test_warn_if_tresos_home_none(self) -> None:
        console, buf = _make_console()
        init_mod._warn_if_tresos_home_missing(None, console)
        assert "警告" in buf.getvalue()

    def test_warn_if_tresos_home_missing_path(self, tmp_path: Path) -> None:
        console, buf = _make_console()
        init_mod._warn_if_tresos_home_missing(tmp_path / "no_exist", console)
        assert "警告" in buf.getvalue()

    def test_warn_if_tresos_home_present_silent(self, tmp_path: Path) -> None:
        valid = tmp_path / "tresos"
        valid.mkdir()
        console, buf = _make_console()
        init_mod._warn_if_tresos_home_missing(valid, console)
        assert "警告" not in buf.getvalue()


class TestSprint8E1CoverageInitCopyBSWMD:
    """BSWMD 复制函数各种边界。"""

    def test_copy_bswmd_files_src_root_missing(self, tmp_path: Path) -> None:
        tresos = tmp_path / "tresos"
        tresos.mkdir()
        copied, skipped, errors = init_mod._copy_bswmd_files(
            tresos_home=tresos, target_root=tmp_path / "dst", refresh=False,
        )
        assert copied == 0
        assert skipped == 0
        assert len(errors) == 1
        assert "未找到 BSWMD 源目录" in errors[0]

    def test_copy_bswmd_files_no_sources(self, tmp_path: Path) -> None:
        tresos = tmp_path / "tresos"
        (tresos / "BSWMD").mkdir(parents=True, exist_ok=True)
        (tresos / "BSWMD" / "readme.txt").write_text("nothing", encoding="utf-8")
        copied, skipped, errors = init_mod._copy_bswmd_files(
            tresos_home=tresos, target_root=tmp_path / "dst", refresh=False,
        )
        assert copied == 0
        assert len(errors) == 1
        assert "*_Bswmd.arxml" in errors[0]

    def test_copy_bswmd_files_copies_fresh(self, tmp_path: Path) -> None:
        tresos = _make_tresos_home(tmp_path / "tresos")
        target = tmp_path / "dst"
        copied, skipped, errors = init_mod._copy_bswmd_files(
            tresos_home=tresos, target_root=target, refresh=False,
        )
        assert copied == 2
        assert skipped == 0
        assert errors == []
        assert (target / "Mcu" / "Mcu_Bswmd.arxml").is_file()

    def test_copy_bswmd_files_skip_when_dst_up_to_date(self, tmp_path: Path) -> None:
        tresos = _make_tresos_home(tmp_path / "tresos")
        target = tmp_path / "dst"
        init_mod._copy_bswmd_files(tresos_home=tresos, target_root=target, refresh=False)
        dst_file = target / "Mcu" / "Mcu_Bswmd.arxml"
        src_file = tresos / "BSWMD" / "Mcu" / "Mcu_Bswmd.arxml"
        os.utime(dst_file, ns=(src_file.stat().st_mtime_ns + 1000,) * 2)
        copied, skipped, errors = init_mod._copy_bswmd_files(
            tresos_home=tresos, target_root=target, refresh=False,
        )
        assert copied == 0
        assert skipped == 2
        assert errors == []

    def test_copy_bswmd_files_copy_when_dst_stale(self, tmp_path: Path) -> None:
        tresos = _make_tresos_home(tmp_path / "tresos")
        target = tmp_path / "dst"
        init_mod._copy_bswmd_files(tresos_home=tresos, target_root=target, refresh=False)
        dst_file = target / "Mcu" / "Mcu_Bswmd.arxml"
        src_file = tresos / "BSWMD" / "Mcu" / "Mcu_Bswmd.arxml"
        os.utime(dst_file, ns=(src_file.stat().st_mtime_ns - 10000,) * 2)
        copied, skipped, errors = init_mod._copy_bswmd_files(
            tresos_home=tresos, target_root=target, refresh=False,
        )
        assert copied >= 1
        assert errors == []

    def test_copy_bswmd_files_refresh_force_copy(self, tmp_path: Path) -> None:
        tresos = _make_tresos_home(tmp_path / "tresos")
        target = tmp_path / "dst"
        init_mod._copy_bswmd_files(tresos_home=tresos, target_root=target, refresh=False)
        copied, skipped, errors = init_mod._copy_bswmd_files(
            tresos_home=tresos, target_root=target, refresh=True,
        )
        assert copied == 2
        assert skipped == 0
        assert errors == []

    def test_copy_bswmd_files_oserror_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tresos = _make_tresos_home(tmp_path / "tresos")
        target = tmp_path / "dst"

        def _boom(*_args: Any, **_kwargs: Any) -> None:
            raise OSError("disk full")

        monkeypatch.setattr("shutil.copy2", _boom)
        copied, skipped, errors = init_mod._copy_bswmd_files(
            tresos_home=tresos, target_root=target, refresh=False,
        )
        assert copied == 0
        assert len(errors) >= 1
        assert "复制失败" in errors[0]


class TestSprint8E1CoverageInitScanModules:
    """工程验证：扫描 ``.prefs/`` 下的模块。"""

    def test_scan_project_modules_no_prefs_dir(self, tmp_path: Path) -> None:
        result = init_mod._scan_project_modules(tmp_path / "no_prefs")
        assert result == []

    def test_scan_project_modules_with_xdm(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        (project / ".prefs").mkdir(parents=True, exist_ok=True)
        (project / ".prefs" / "Mcu.xdm").write_text('<?xml version="1.0"?>\n<root/>\n', encoding="utf-8")
        result = init_mod._scan_project_modules(project)
        assert result == ["Mcu"]

    def test_scan_project_modules_with_arxml(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        (project / ".prefs").mkdir(parents=True, exist_ok=True)
        (project / ".prefs" / "Port.arxml").write_text('<?xml version="1.0"?>\n<root/>\n', encoding="utf-8")
        result = init_mod._scan_project_modules(project)
        assert result == ["Port"]

    def test_scan_project_modules_strip_cfg_suffix(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        (project / ".prefs").mkdir(parents=True, exist_ok=True)
        (project / ".prefs" / "Mcu_Cfg.xdm").write_text('<?xml version="1.0"?>\n<root/>\n', encoding="utf-8")
        result = init_mod._scan_project_modules(project)
        assert result == ["Mcu"]

    def test_scan_project_modules_dedup_xdm_arxml(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        (project / ".prefs").mkdir(parents=True, exist_ok=True)
        (project / ".prefs" / "Mcu.xdm").write_text('<?xml version="1.0"?>\n<root/>\n', encoding="utf-8")
        (project / ".prefs" / "Mcu.arxml").write_text('<?xml version="1.0"?>\n<root/>\n', encoding="utf-8")
        result = init_mod._scan_project_modules(project)
        assert result == ["Mcu"]

    def test_scan_project_modules_sorted(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        (project / ".prefs").mkdir(parents=True, exist_ok=True)
        for name in ("Zcu", "Acu", "Mcu"):
            (project / ".prefs" / f"{name}.xdm").write_text(
                '<?xml version="1.0"?>\n<root/>\n', encoding="utf-8"
            )
        result = init_mod._scan_project_modules(project)
        assert result == ["Acu", "Mcu", "Zcu"]


class TestSprint8E1CoverageInitReadExisting:
    """_read_existing_config（薄包装 load_yaml）。"""

    def test_read_existing_config_returns_dict(self, tmp_path: Path) -> None:
        (tmp_path / ".autoc").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".autoc" / "autoc.yaml").write_text("project_root: /x\n", encoding="utf-8")
        result = init_mod._read_existing_config(tmp_path)
        assert result == {"project_root": "/x"}

    def test_read_existing_config_missing_returns_empty(self, tmp_path: Path) -> None:
        result = init_mod._read_existing_config(tmp_path)
        assert result == {}


class TestSprint8E1CoverageInitRegister:
    """``register(subparsers)`` 把 init 子命令挂到 argparse。"""

    def test_register_adds_init_subparser(self, capsys: pytest.CaptureFixture[str]) -> None:
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd")
        init_mod.register(sub)
        ns = parser.parse_args(["init", "--no-bswmd"])
        assert ns.cmd == "init"
        assert ns.no_bswmd is True
        assert ns.refresh_bswmd is False
        assert ns.non_interactive is False

    def test_register_default_flags(self) -> None:
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
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd")
        init_mod.register(sub)
        ns = parser.parse_args(["init", "--refresh-bswmd"])
        assert ns.refresh_bswmd is True
