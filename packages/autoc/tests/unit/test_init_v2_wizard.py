"""``cli/commands/init.py`` v2 增强单测（Sprint 9.0 — T9.0.6）。

覆盖：
    - 探测成功（mock 路径存在）→ settings.json 写出来
    - 探测失败 / 路径缺失 → 错误信息清晰
    - 5 vendor 探测表正确
    - v1 ``autoc.yaml`` + v2 ``settings.json`` 共存
    - v2 CLI 参数（``--mcal-vendor`` / ``--mcal-vendor-home`` / ``--chip`` /
      ``--no-settings-json``）正确生效
"""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console

from claude_autosar.cli.commands import init as init_mod
from claude_autosar.core.config import project_config as pc_mod
from claude_autosar.core.settings.v2_paths import SETTINGS_JSON_NAME
from rich.prompt import Prompt


# ===========================================================================
# Helpers
# ===========================================================================


def _make_console() -> tuple[Console, io.StringIO]:
    """In-memory Rich Console."""
    buf = io.StringIO()
    return Console(file=buf, force_terminal=False, width=120), buf


def _make_namespace(**kwargs: Any) -> argparse.Namespace:
    """Build argparse.Namespace mirroring ``init register()`` defaults."""
    defaults: dict[str, Any] = {
        "project_root": None,
        "tresos_home": None,
        "non_interactive": False,
        "no_bswmd": False,
        "refresh_bswmd": False,
        "mcal_vendor": None,
        "mcal_vendor_home": None,
        "chip_derivative": None,
        "no_settings_json": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _make_prefs_project(root: Path) -> Path:
    """Fake EB tresos 工程（``.prefs/`` + 1 个 xdm）。"""
    (root / ".prefs").mkdir(parents=True, exist_ok=True)
    (root / ".prefs" / "Mcu.xdm").write_text(
        '<?xml version="1.0"?>\n<root/>\n', encoding="utf-8"
    )
    return root


def _build_tresos_home(root: Path) -> Path:
    """Fake tresos home + bin/tresos_cmd.bat。"""
    home = root / "tresos"
    bin_dir = home / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    (bin_dir / "tresos_cmd.bat").write_text(
        "@echo off\n", encoding="utf-8"
    )
    return home


def _build_vendor_home(root: Path) -> Path:
    """Fake vendor home + autosar/<chip>.epd。"""
    home = root / "vendor_home"
    (home / "autosar").mkdir(parents=True, exist_ok=True)
    (home / "autosar" / "Mcu_s32k148_lqfp176.epd").write_text(
        '<?xml version="1.0"?>\n<root/>\n', encoding="utf-8"
    )
    return home


def _clean_env(
    monkeypatch: pytest.MonkeyPatch, *keys: str
) -> None:
    """Clear all V2 env vars so tests don't see host env."""
    for k in keys:
        monkeypatch.delenv(k, raising=False)


# ===========================================================================
# 探测成功 → 写 settings.json
# ===========================================================================


class TestInitV2WizardProbeSuccess:
    """``claude-autosar init`` 探测成功 → 写 settings.json。"""

    def test_probe_success_writes_settings_json(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """探测全成功 → ``.autoc/settings.json`` 写出，4 字段对。"""
        _clean_env(
            monkeypatch,
            "TRESOS_HOME",
            "MCAL_VENDOR",
            "MCAL_VENDOR_HOME",
            "CLAUDE_AUTOSAR_CHIP",
        )
        project = _make_prefs_project(tmp_path / "proj")
        tresos = _build_tresos_home(tmp_path / "t")
        vendor_home = _build_vendor_home(tmp_path / "v")

        # patch 探测表 + 平台
        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setattr(
            "claude_autosar.core.settings.v2_paths.TRESOS_CLI_WIN",
            tresos / "bin" / "tresos_cmd.bat",
        )
        monkeypatch.setattr(
            "claude_autosar.core.settings.v2_paths.DEFAULT_TRESOS_HOME_WIN",
            tresos,
        )
        patched = {
            "nxp": (vendor_home,),
            "st": (Path("/no/such/st"),),
            "ti": (Path("/no/such/ti"),),
            "renesas": (Path("/no/such/renesas"),),
            "infineon": (Path("/no/such/infineon"),),
        }
        import claude_autosar.core.settings.v2_paths as v2p
        monkeypatch.setattr(v2p, "VENDOR_DEFAULT_HOMES", patched)
        # vendor 通过 env 给
        monkeypatch.setenv("MCAL_VENDOR", "nxp")

        # patch v1 default_tresos_home → 也走我们的
        monkeypatch.setattr(pc_mod, "default_tresos_home", lambda: tresos)

        ns = _make_namespace(
            project_root=project,
            non_interactive=True,
            no_bswmd=True,  # 跳过 BSWMD copy 跑得快
        )
        rc = init_mod.run(ns)
        assert rc == 0

        # 写出了 settings.json
        json_path = project / ".autoc" / SETTINGS_JSON_NAME
        assert json_path.is_file()
        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data["mcal_vendor"] == "nxp"
        assert data["chip_derivative"] == "Mcu_s32k148_lqfp176.epd"
        assert data["mcal_vendor_home"].endswith("vendor_home")

    def test_probe_success_writes_both_v1_yaml_and_v2_json(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """v1 ``autoc.yaml`` + v2 ``settings.json`` 都写出（共存）。"""
        _clean_env(
            monkeypatch,
            "TRESOS_HOME",
            "MCAL_VENDOR",
            "MCAL_VENDOR_HOME",
            "CLAUDE_AUTOSAR_CHIP",
        )
        project = _make_prefs_project(tmp_path / "proj")
        tresos = _build_tresos_home(tmp_path / "t")
        vendor_home = _build_vendor_home(tmp_path / "v")

        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setattr(
            "claude_autosar.core.settings.v2_paths.TRESOS_CLI_WIN",
            tresos / "bin" / "tresos_cmd.bat",
        )
        monkeypatch.setattr(
            "claude_autosar.core.settings.v2_paths.DEFAULT_TRESOS_HOME_WIN",
            tresos,
        )
        patched = {"nxp": (vendor_home,)}
        patched.update({v: (Path("/no"),) for v in ("st", "ti", "renesas", "infineon")})
        import claude_autosar.core.settings.v2_paths as v2p
        monkeypatch.setattr(v2p, "VENDOR_DEFAULT_HOMES", patched)
        monkeypatch.setenv("MCAL_VENDOR", "nxp")
        monkeypatch.setattr(pc_mod, "default_tresos_home", lambda: tresos)

        ns = _make_namespace(
            project_root=project,
            non_interactive=True,
            no_bswmd=True,
        )
        rc = init_mod.run(ns)
        assert rc == 0

        # v1 + v2 都存在
        assert (project / ".autoc" / "autoc.yaml").is_file()
        assert (project / ".autoc" / SETTINGS_JSON_NAME).is_file()


# ===========================================================================
# 探测失败 → 清晰报错
# ===========================================================================


class TestInitV2WizardProbeFailure:
    """探测失败 → 错误信息清晰（哪个路径 + 怎么配置）。"""

    def test_no_paths_raises_in_non_interactive(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """非交互 + 全 4 级缺 → V2PathsError → run 返 1。"""
        _clean_env(
            monkeypatch,
            "TRESOS_HOME",
            "MCAL_VENDOR",
            "MCAL_VENDOR_HOME",
            "CLAUDE_AUTOSAR_CHIP",
        )
        project = _make_prefs_project(tmp_path / "proj")
        # tresos 也探测不到
        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setattr(
            "claude_autosar.core.settings.v2_paths.TRESOS_CLI_WIN",
            Path("/no/such/tresos_cmd.bat"),
        )
        monkeypatch.setattr(
            "claude_autosar.core.settings.v2_paths.DEFAULT_TRESOS_HOME_WIN",
            Path("/no/such"),
        )
        monkeypatch.setattr(pc_mod, "default_tresos_home", lambda: None)

        ns = _make_namespace(
            project_root=project,
            non_interactive=True,
            no_bswmd=True,
        )
        rc = init_mod.run(ns)
        assert rc == 1

    def test_no_paths_warns_in_interactive(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """交互 + 全缺 → console 警告 + 跳过 settings.json（不阻 init）。"""
        from rich.prompt import Prompt

        _clean_env(
            monkeypatch,
            "TRESOS_HOME",
            "MCAL_VENDOR",
            "MCAL_VENDOR_HOME",
            "CLAUDE_AUTOSAR_CHIP",
        )
        project = _make_prefs_project(tmp_path / "proj")
        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setattr(
            "claude_autosar.core.settings.v2_paths.TRESOS_CLI_WIN",
            Path("/no/such/tresos_cmd.bat"),
        )
        monkeypatch.setattr(
            "claude_autosar.core.settings.v2_paths.DEFAULT_TRESOS_HOME_WIN",
            Path("/no/such"),
        )
        # 把 v1 tresos 探测也弄 None（避免 console 警告淹了 v2 警告）
        monkeypatch.setattr(pc_mod, "default_tresos_home", lambda: None)
        # mock 交互：Prompt.ask → 第一次给"无效路径"，之后给有效路径
        responses = [str(project), ""]  # project_root ok, tresos_home empty

        def _fake_prompt(*_a: Any, **_kw: Any) -> str:
            return responses.pop(0) if responses else ""

        monkeypatch.setattr(Prompt, "ask", _fake_prompt)

        ns = _make_namespace(
            project_root=None,  # 触发交互问
            non_interactive=False,
            no_bswmd=True,
        )
        rc = init_mod.run(ns)
        # v2 探测失败 → 走警告分支；v1 流程不受阻 → 返 0
        assert rc == 0
        # settings.json **没**写出（探测失败）
        assert not (project / ".autoc" / SETTINGS_JSON_NAME).exists()
        # autoc.yaml 还是写了（v1 兼容）
        assert (project / ".autoc" / "autoc.yaml").is_file()


# ===========================================================================
# 5 vendor 探测
# ===========================================================================


class TestInitV2WizardVendorTable:
    """5 vendor 任一可用 → init 探测成功。"""

    @pytest.mark.parametrize(
        "vendor",
        ["nxp", "st", "ti", "renesas", "infineon"],
    )
    def test_each_vendor_probe(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        vendor: str,
    ) -> None:
        """5 vendor 各自探测 → init 写出对应 settings.json。"""
        _clean_env(
            monkeypatch,
            "TRESOS_HOME",
            "MCAL_VENDOR",
            "MCAL_VENDOR_HOME",
            "CLAUDE_AUTOSAR_CHIP",
        )
        project = _make_prefs_project(tmp_path / "proj")
        tresos = _build_tresos_home(tmp_path / "t")
        vendor_home = _build_vendor_home(tmp_path / "v")

        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setattr(
            "claude_autosar.core.settings.v2_paths.TRESOS_CLI_WIN",
            tresos / "bin" / "tresos_cmd.bat",
        )
        monkeypatch.setattr(
            "claude_autosar.core.settings.v2_paths.DEFAULT_TRESOS_HOME_WIN",
            tresos,
        )
        # 5 vendor 各自指向我们的 vendor_home（其他指 /no）
        patched = {v: (Path("/no/such"),) for v in
                  ("nxp", "st", "ti", "renesas", "infineon")}
        patched[vendor] = (vendor_home,)
        import claude_autosar.core.settings.v2_paths as v2p
        monkeypatch.setattr(v2p, "VENDOR_DEFAULT_HOMES", patched)
        monkeypatch.setenv("MCAL_VENDOR", vendor)
        monkeypatch.setattr(pc_mod, "default_tresos_home", lambda: tresos)

        ns = _make_namespace(
            project_root=project,
            non_interactive=True,
            no_bswmd=True,
        )
        rc = init_mod.run(ns)
        assert rc == 0

        json_path = project / ".autoc" / SETTINGS_JSON_NAME
        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data["mcal_vendor"] == vendor
        assert data["mcal_vendor_home"].endswith("vendor_home")


# ===========================================================================
# v2 CLI 参数 + --no-settings-json
# ===========================================================================


class TestInitV2WizardCliArgs:
    """``--mcal-vendor`` / ``--mcal-vendor-home`` / ``--chip`` / ``--no-settings-json``。"""

    def test_no_settings_json_flag_skips_v2(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``--no-settings-json`` → 不写 settings.json。"""
        project = _make_prefs_project(tmp_path / "proj")
        ns = _make_namespace(
            project_root=project,
            non_interactive=True,
            no_bswmd=True,
            no_settings_json=True,
        )
        rc = init_mod.run(ns)
        assert rc == 0
        # v1 yaml 写
        assert (project / ".autoc" / "autoc.yaml").is_file()
        # v2 json 不写
        assert not (project / ".autoc" / SETTINGS_JSON_NAME).exists()

    def test_register_adds_v2_args(self) -> None:
        """register() 暴露 4 个 v2 CLI 参数。"""
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd")
        init_mod.register(sub)
        ns = parser.parse_args(
            [
                "init",
                "--mcal-vendor", "nxp",
                "--mcal-vendor-home", "C:/NXP/AUTOSAR",
                "--chip", "Mcu_s32k148.epd",
                "--no-settings-json",
            ]
        )
        assert ns.mcal_vendor == "nxp"
        assert str(ns.mcal_vendor_home).replace("\\", "/") == "C:/NXP/AUTOSAR"
        assert ns.chip_derivative == "Mcu_s32k148.epd"
        assert ns.no_settings_json is True

    def test_register_default_v2_args(self) -> None:
        """register() v2 参数默认 None / False。"""
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd")
        init_mod.register(sub)
        ns = parser.parse_args(["init"])
        assert ns.mcal_vendor is None
        assert ns.mcal_vendor_home is None
        assert ns.chip_derivative is None
        assert ns.no_settings_json is False

    def test_cli_overrides_take_priority_in_init(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``--mcal-vendor`` CLI 参数覆盖 env（init 流程透传）。"""
        _clean_env(
            monkeypatch,
            "TRESOS_HOME",
            "MCAL_VENDOR",
            "MCAL_VENDOR_HOME",
            "CLAUDE_AUTOSAR_CHIP",
        )
        project = _make_prefs_project(tmp_path / "proj")
        tresos = _build_tresos_home(tmp_path / "t")
        vendor_home = _build_vendor_home(tmp_path / "v")

        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setattr(
            "claude_autosar.core.settings.v2_paths.TRESOS_CLI_WIN",
            tresos / "bin" / "tresos_cmd.bat",
        )
        monkeypatch.setattr(
            "claude_autosar.core.settings.v2_paths.DEFAULT_TRESOS_HOME_WIN",
            tresos,
        )
        patched = {v: (Path("/no/such"),) for v in
                  ("nxp", "st", "ti", "renesas", "infineon")}
        patched["nxp"] = (vendor_home,)
        import claude_autosar.core.settings.v2_paths as v2p
        monkeypatch.setattr(v2p, "VENDOR_DEFAULT_HOMES", patched)
        monkeypatch.setattr(pc_mod, "default_tresos_home", lambda: tresos)

        # env 给 st（不同 vendor）
        monkeypatch.setenv("MCAL_VENDOR", "st")
        # CLI 给 nxp（应赢）
        ns = _make_namespace(
            project_root=project,
            non_interactive=True,
            no_bswmd=True,
            mcal_vendor="nxp",
        )
        rc = init_mod.run(ns)
        assert rc == 0

        json_path = project / ".autoc" / SETTINGS_JSON_NAME
        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data["mcal_vendor"] == "nxp"  # CLI 赢


# ===========================================================================
# _write_v2_settings 单元
# ===========================================================================


class TestWriteV2SettingsHelper:
    """``_write_v2_settings`` 单元。"""

    def test_write_v2_settings_writes_json(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """CLI 参数齐全 → 写 settings.json 4 字段。"""
        _clean_env(
            monkeypatch,
            "TRESOS_HOME",
            "MCAL_VENDOR",
            "MCAL_VENDOR_HOME",
            "CLAUDE_AUTOSAR_CHIP",
        )
        project = tmp_path / "proj"
        project.mkdir()
        tresos = _build_tresos_home(tmp_path / "t")
        vendor_home = _build_vendor_home(tmp_path / "v")

        console, _ = _make_console()
        init_mod._write_v2_settings(
            console=console,
            project_root=project,
            tresos_home=tresos,
            mcal_vendor_arg="nxp",
            mcal_vendor_home_arg=vendor_home,
            chip_derivative_arg="Mcu_s32k148_lqfp176.epd",
            non_interactive=True,
        )
        json_path = project / ".autoc" / SETTINGS_JSON_NAME
        assert json_path.is_file()
        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data["mcal_vendor"] == "nxp"
        assert data["chip_derivative"] == "Mcu_s32k148_lqfp176.epd"
