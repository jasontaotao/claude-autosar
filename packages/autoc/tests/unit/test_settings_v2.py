"""``core/settings/v2_paths.py`` + ``cli/commands/init.py`` v2 增强 单测。

Sprint 9.0 — T9.0.7（schema + 加载器）+ T9.0.6（init 向导 v2 部分）。

覆盖：
    - V2Paths dataclass 构造校验
    - 4 级优先级链：CLI > env > settings.json > 探测
    - 5 vendor 探测表（nxp / st / ti / renesas / infineon）
    - 3 路径任一缺失 → V2PathsError
    - to_json / write_settings_json
    - v1 ``autoc.yaml`` + v2 ``settings.json`` 共存
    - settings.json 缺字段 / 非法 JSON / 顶层非 dict 容错
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from claude_autosar.core.settings.v2_paths import (
    DEFAULT_TRESOS_HOME_LINUX,
    DEFAULT_TRESOS_HOME_WIN,
    MCAL_VENDORS,
    SETTINGS_JSON_NAME,
    TRESOS_CLI_LINUX,
    TRESOS_CLI_WIN,
    VENDOR_DEFAULT_HOMES,
    V2Paths,
    V2PathsError,
    load_v2_paths,
    probe_chip_derivative,
    probe_mcal_vendor_home,
    probe_tresos_home,
    write_settings_json,
)


# ===========================================================================
# Helpers
# ===========================================================================


def _build_vendor_home(root: Path, vendor: str) -> Path:
    """Build a fake ``<root>/<vendor_home>`` matching the vendor's default layout."""
    candidates = VENDOR_DEFAULT_HOMES[vendor]
    # use the first candidate's leaf name (e.g. "AUTOSAR", "SPC58")
    # for test we use the actual candidate but inside tmp_path
    home = root / "vendor_home"
    home.mkdir(parents=True, exist_ok=True)
    return home


def _build_tresos_home(root: Path) -> Path:
    """Build a fake tresos home with ``bin/tresos_cmd.bat`` (or sh for Linux)."""
    home = root / "tresos"
    bin_dir = home / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    cli = bin_dir / "tresos_cmd.bat"
    cli.write_text("@echo off\n", encoding="utf-8")
    return home


def _build_chip_dir(vendor_home: Path, chip_name: str) -> str:
    """Create ``<vendor_home>/autosar/<chip>.epd`` and return the chip name."""
    autosar = vendor_home / "autosar"
    autosar.mkdir(parents=True, exist_ok=True)
    epd = autosar / chip_name
    epd.write_text("<?xml version='1.0'?><root/>\n", encoding="utf-8")
    return chip_name


def _clean_env(
    monkeypatch: pytest.MonkeyPatch, *keys: str
) -> None:
    """Clear all V2 env vars so tests don't see host env."""
    for k in keys:
        monkeypatch.delenv(k, raising=False)


# ===========================================================================
# V2Paths dataclass — 构造校验
# ===========================================================================


class TestV2PathsDataclass:
    """``V2Paths`` 构造校验 + 序列化。"""

    def test_valid_construction(self) -> None:
        """4 字段都填 + vendor 在表里 → OK。"""
        v = V2Paths(
            tresos_home=Path("C:/EB/tresos"),
            mcal_vendor="nxp",
            mcal_vendor_home=Path("C:/NXP/AUTOSAR"),
            chip_derivative="Mcu_s32k148_lqfp176.epd",
        )
        assert v.tresos_home == Path("C:/EB/tresos")
        assert v.mcal_vendor == "nxp"
        assert v.chip_derivative.endswith(".epd")

    def test_invalid_vendor_raises(self) -> None:
        """vendor 不在 5 个里 → V2PathsError。"""
        with pytest.raises(V2PathsError, match="mcal_vendor 必须是"):
            V2Paths(
                tresos_home=Path("C:/EB/tresos"),
                mcal_vendor="bogus_vendor",  # type: ignore[arg-type]
                mcal_vendor_home=Path("C:/NXP/AUTOSAR"),
                chip_derivative="Mcu_s32k148_lqfp176.epd",
            )

    def test_empty_chip_derivative_raises(self) -> None:
        """chip_derivative 空 → V2PathsError。"""
        with pytest.raises(V2PathsError, match="chip_derivative 不能为空"):
            V2Paths(
                tresos_home=Path("C:/EB/tresos"),
                mcal_vendor="nxp",
                mcal_vendor_home=Path("C:/NXP/AUTOSAR"),
                chip_derivative="   ",
            )

    def test_non_epd_chip_raises(self) -> None:
        """chip_derivative 不以 .epd 结尾 → V2PathsError。"""
        with pytest.raises(V2PathsError, match="\\.epd"):
            V2Paths(
                tresos_home=Path("C:/EB/tresos"),
                mcal_vendor="nxp",
                mcal_vendor_home=Path("C:/NXP/AUTOSAR"),
                chip_derivative="mcu_s32k148.txt",
            )

    def test_to_json_format(self) -> None:
        """``to_json`` 输出符合 4 字段 schema（POSIX 路径）。"""
        v = V2Paths(
            tresos_home=Path("C:/EB/tresos"),
            mcal_vendor="nxp",
            mcal_vendor_home=Path("C:/NXP/AUTOSAR"),
            chip_derivative="Mcu_s32k148_lqfp176.epd",
        )
        text = v.to_json()
        data = json.loads(text)
        assert data["tresos_home"] == "C:/EB/tresos"
        assert data["mcal_vendor"] == "nxp"
        assert data["mcal_vendor_home"] == "C:/NXP/AUTOSAR"
        assert data["chip_derivative"] == "Mcu_s32k148_lqfp176.epd"

    def test_to_dict_uses_str_path(self) -> None:
        """``to_dict`` 把 Path 转 str（OS 风格，含盘符）。"""
        v = V2Paths(
            tresos_home=Path("C:/EB/tresos"),
            mcal_vendor="st",
            mcal_vendor_home=Path("C:/ST/SPC58"),
            chip_derivative="Mcu_spc58.epd",
        )
        d = v.to_dict()
        assert isinstance(d["tresos_home"], str)
        assert "EB" in d["tresos_home"]
        assert d["mcal_vendor"] == "st"

    def test_frozen_immutable(self) -> None:
        """frozen dataclass 不可改。"""
        v = V2Paths(
            tresos_home=Path("C:/EB/tresos"),
            mcal_vendor="nxp",
            mcal_vendor_home=Path("C:/NXP/AUTOSAR"),
            chip_derivative="Mcu_s32k148_lqfp176.epd",
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            v.mcal_vendor = "st"  # type: ignore[misc]


# ===========================================================================
# 探测函数 — 5 vendor
# ===========================================================================


class TestProbeTresosHome:
    """``probe_tresos_home()`` 平台分支。"""

    def test_windows_default_path_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Win + C:\\EB\\tresos 存在 → 返回 root。"""
        monkeypatch.setattr("sys.platform", "win32")
        tresos = _build_tresos_home(tmp_path)
        # 强制把 DEFAULT_TRESOS_HOME_WIN 指向我们造的
        monkeypatch.setattr(
            "claude_autosar.core.settings.v2_paths.TRESOS_CLI_WIN",
            tresos / "bin" / "tresos_cmd.bat",
        )
        monkeypatch.setattr(
            "claude_autosar.core.settings.v2_paths.DEFAULT_TRESOS_HOME_WIN",
            tresos,
        )
        result = probe_tresos_home()
        assert result == tresos.resolve()

    def test_linux_default_path_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Linux + /opt/tresos 存在 → 返回。"""
        monkeypatch.setattr("sys.platform", "linux")
        home = tmp_path / "tresos"
        (home / "bin").mkdir(parents=True)
        (home / "bin" / "tresos_cmd").write_text("#!/bin/sh\n", encoding="utf-8")
        monkeypatch.setattr(
            "claude_autosar.core.settings.v2_paths.TRESOS_CLI_LINUX",
            home / "bin" / "tresos_cmd",
        )
        monkeypatch.setattr(
            "claude_autosar.core.settings.v2_paths.DEFAULT_TRESOS_HOME_LINUX",
            home,
        )
        result = probe_tresos_home()
        assert result == home.resolve()

    def test_other_platform_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """darwin / 其他 → None。"""
        monkeypatch.setattr("sys.platform", "darwin")
        assert probe_tresos_home() is None

    def test_windows_default_missing_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Win + 默认路径都不存在 → None。"""
        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setattr(
            "claude_autosar.core.settings.v2_paths.TRESOS_CLI_WIN",
            Path("/no/such/tresos_cmd.bat"),
        )
        monkeypatch.setattr(
            "claude_autosar.core.settings.v2_paths.DEFAULT_TRESOS_HOME_WIN",
            Path("/no/such"),
        )
        assert probe_tresos_home() is None


class TestProbeMcalVendorHome:
    """``probe_mcal_vendor_home()`` 5 vendor。"""

    @pytest.mark.parametrize("vendor", list(MCAL_VENDORS))
    def test_vendor_default_exists(
        self, tmp_path: Path, vendor: str
    ) -> None:
        """5 vendor 任一：默认路径在 tmp 下存在 → 返回。"""
        # 直接 monkey-patch 探测表指向 tmp
        for cand in VENDOR_DEFAULT_HOMES[vendor]:
            (tmp_path / cand.name).mkdir(parents=True, exist_ok=True)
        # Build patched table
        patched = {
            v: tuple(
                tmp_path / c.name for c in VENDOR_DEFAULT_HOMES[v]
            )
            for v in MCAL_VENDORS
        }
        import claude_autosar.core.settings.v2_paths as mod
        orig = mod.VENDOR_DEFAULT_HOMES
        mod.VENDOR_DEFAULT_HOMES = patched
        try:
            result = probe_mcal_vendor_home(vendor)
        finally:
            mod.VENDOR_DEFAULT_HOMES = orig
        assert result is not None
        assert result.is_dir()

    def test_unknown_vendor_returns_none(self) -> None:
        """未知 vendor → None。"""
        assert probe_mcal_vendor_home("bogus") is None

    def test_vendor_default_missing_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """vendor 默认路径都不存在 → None。"""
        patched = {
            v: tuple(Path(f"/no/such/{v}_{i}") for i in range(2))
            for v in MCAL_VENDORS
        }
        import claude_autosar.core.settings.v2_paths as mod
        monkeypatch.setattr(mod, "VENDOR_DEFAULT_HOMES", patched)
        assert probe_mcal_vendor_home("nxp") is None


class TestProbeChipDerivative:
    """``probe_chip_derivative()`` 扫 autosar/*.epd。"""

    def test_chip_found(self, tmp_path: Path) -> None:
        """autosar/*.epd 存在 → 返回第一个 .epd 文件名。"""
        vendor_home = _build_vendor_home(tmp_path, "nxp")
        chip = _build_chip_dir(vendor_home, "Mcu_s32k148_lqfp176.epd")
        result = probe_chip_derivative(vendor_home)
        assert result == chip

    def test_chip_multiple_returns_first_sorted(
        self, tmp_path: Path
    ) -> None:
        """多个 .epd → 返回按字母排序后的第一个。"""
        vendor_home = _build_vendor_home(tmp_path, "nxp")
        autosar = vendor_home / "autosar"
        autosar.mkdir(parents=True, exist_ok=True)
        for name in ("Zcu_s32k3.epd", "Acu_s32k1.epd", "Mcu_s32k2.epd"):
            (autosar / name).write_text("<root/>\n", encoding="utf-8")
        result = probe_chip_derivative(vendor_home)
        assert result == "Acu_s32k1.epd"

    def test_chip_no_autosar_dir(self, tmp_path: Path) -> None:
        """无 autosar/ → None。"""
        vendor_home = tmp_path / "empty"
        vendor_home.mkdir()
        assert probe_chip_derivative(vendor_home) is None

    def test_chip_no_epd_files(self, tmp_path: Path) -> None:
        """autosar/ 存在但无 .epd → None。"""
        vendor_home = _build_vendor_home(tmp_path, "nxp")
        autosar = vendor_home / "autosar"
        autosar.mkdir(parents=True, exist_ok=True)
        (autosar / "readme.txt").write_text("nothing", encoding="utf-8")
        assert probe_chip_derivative(vendor_home) is None


# ===========================================================================
# load_v2_paths — 4 级优先级链
# ===========================================================================


class TestLoadV2PathsPriorityChain:
    """4 级优先级：CLI > env > settings.json > 探测。"""

    def test_cli_overrides_all(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """CLI 参数（最优先）— 忽略 env / json / 探测。"""
        _clean_env(
            monkeypatch,
            "TRESOS_HOME",
            "MCAL_VENDOR",
            "MCAL_VENDOR_HOME",
            "CLAUDE_AUTOSAR_CHIP",
        )
        # 写 settings.json（应被 CLI 覆盖）
        cfg_dir = tmp_path / "proj" / ".autoc"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        (cfg_dir / SETTINGS_JSON_NAME).write_text(
            json.dumps(
                {
                    "tresos_home": "/json/tresos",
                    "mcal_vendor": "st",
                    "mcal_vendor_home": "/json/vendor",
                    "chip_derivative": "Mcu_st.epd",
                }
            ),
            encoding="utf-8",
        )
        # 设 env（应被 CLI 覆盖）
        monkeypatch.setenv("TRESOS_HOME", "/env/tresos")
        monkeypatch.setenv("MCAL_VENDOR", "ti")

        v = load_v2_paths(
            project_root=tmp_path / "proj",
            cli_tresos_home="C:/cli/tresos",
            cli_mcal_vendor="renesas",
            cli_mcal_vendor_home="C:/cli/vendor",
            cli_chip_derivative="Mcu_rh850.epd",
        )
        # CLI 赢
        assert str(v.tresos_home).replace("\\", "/") == "C:/cli/tresos"
        assert v.mcal_vendor == "renesas"
        assert str(v.mcal_vendor_home).replace("\\", "/") == "C:/cli/vendor"
        assert v.chip_derivative == "Mcu_rh850.epd"

    def test_env_overrides_json(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """env 覆盖 settings.json。"""
        _clean_env(
            monkeypatch,
            "TRESOS_HOME",
            "MCAL_VENDOR",
            "MCAL_VENDOR_HOME",
            "CLAUDE_AUTOSAR_CHIP",
        )
        cfg_dir = tmp_path / "proj" / ".autoc"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        (cfg_dir / SETTINGS_JSON_NAME).write_text(
            json.dumps(
                {
                    "tresos_home": "/json/tresos",
                    "mcal_vendor": "st",
                    "mcal_vendor_home": "/json/vendor",
                    "chip_derivative": "Mcu_st.epd",
                }
            ),
            encoding="utf-8",
        )
        # 设 env
        tresos = _build_tresos_home(tmp_path / "env_tresos")
        monkeypatch.setenv("TRESOS_HOME", str(tresos))
        monkeypatch.setenv("MCAL_VENDOR", "infineon")
        # vendor_home + chip 也走 env
        vendor_home = tmp_path / "env_vendor"
        vendor_home.mkdir()
        _build_chip_dir(vendor_home, "Mcu_tc3xx.epd")
        monkeypatch.setenv("MCAL_VENDOR_HOME", str(vendor_home))
        monkeypatch.setenv("CLAUDE_AUTOSAR_CHIP", "Mcu_tc3xx.epd")

        v = load_v2_paths(project_root=tmp_path / "proj")
        # env 赢（不是 json 的 /json/tresos）
        assert "env_tresos" in str(v.tresos_home)
        assert v.mcal_vendor == "infineon"
        assert "env_vendor" in str(v.mcal_vendor_home)
        assert v.chip_derivative == "Mcu_tc3xx.epd"

    def test_json_overrides_probe(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """settings.json 覆盖平台默认探测。"""
        _clean_env(
            monkeypatch,
            "TRESOS_HOME",
            "MCAL_VENDOR",
            "MCAL_VENDOR_HOME",
            "CLAUDE_AUTOSAR_CHIP",
        )
        # 模拟探测能找到一个"对的"tresos
        tresos = _build_tresos_home(tmp_path / "probe_tresos")
        monkeypatch.setattr(
            "claude_autosar.core.settings.v2_paths.TRESOS_CLI_WIN",
            tresos / "bin" / "tresos_cmd.bat",
        )
        monkeypatch.setattr(
            "claude_autosar.core.settings.v2_paths.DEFAULT_TRESOS_HOME_WIN",
            tresos,
        )
        monkeypatch.setattr("sys.platform", "win32")
        # 但 settings.json 写另一个值
        cfg_dir = tmp_path / "proj" / ".autoc"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        vendor_home = tmp_path / "json_vendor"
        vendor_home.mkdir()
        _build_chip_dir(vendor_home, "Mcu_json.epd")
        (cfg_dir / SETTINGS_JSON_NAME).write_text(
            json.dumps(
                {
                    "tresos_home": str(tresos),
                    "mcal_vendor": "nxp",
                    "mcal_vendor_home": str(vendor_home),
                    "chip_derivative": "Mcu_json.epd",
                }
            ),
            encoding="utf-8",
        )

        v = load_v2_paths(project_root=tmp_path / "proj")
        # json 赢（不是 probe 的 probe_tresos）
        assert "probe_tresos" in str(v.tresos_home)  # probe 和 json 都是 probe_tresos
        assert v.mcal_vendor == "nxp"  # vendor 没 probe，只能从 json 来
        assert "json_vendor" in str(v.mcal_vendor_home)
        assert v.chip_derivative == "Mcu_json.epd"

    def test_probe_used_when_no_overrides(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """CLI / env / json 都没给 → 用探测。

        注：``mcal_vendor`` 没有"平台默认探测"（vendor 是用户态选择），
        所以这个 case 通过 env 给 vendor，让 tresos / vendor_home / chip
        走探测路径。
        """
        _clean_env(
            monkeypatch,
            "TRESOS_HOME",
            "MCAL_VENDOR",
            "MCAL_VENDOR_HOME",
            "CLAUDE_AUTOSAR_CHIP",
        )
        # 探测能成功（tresos）
        tresos = _build_tresos_home(tmp_path / "probe_tresos")
        monkeypatch.setattr(
            "claude_autosar.core.settings.v2_paths.TRESOS_CLI_WIN",
            tresos / "bin" / "tresos_cmd.bat",
        )
        monkeypatch.setattr(
            "claude_autosar.core.settings.v2_paths.DEFAULT_TRESOS_HOME_WIN",
            tresos,
        )
        monkeypatch.setattr("sys.platform", "win32")
        # vendor 通过 env 给（vendor 没 platform 探测）
        monkeypatch.setenv("MCAL_VENDOR", "nxp")
        # vendor_home 探测
        vendor_home = tmp_path / "probe_vendor"
        vendor_home.mkdir()
        _build_chip_dir(vendor_home, "Mcu_probe.epd")
        patched = {
            "nxp": (vendor_home,),
            "st": (Path("/no/such/st"),),
            "ti": (Path("/no/such/ti"),),
            "renesas": (Path("/no/such/renesas"),),
            "infineon": (Path("/no/such/infineon"),),
        }
        import claude_autosar.core.settings.v2_paths as mod
        monkeypatch.setattr(mod, "VENDOR_DEFAULT_HOMES", patched)

        v = load_v2_paths(project_root=tmp_path / "proj_no_cfg")
        assert "probe_tresos" in str(v.tresos_home)
        assert v.mcal_vendor == "nxp"
        assert "probe_vendor" in str(v.mcal_vendor_home)
        assert v.chip_derivative == "Mcu_probe.epd"


# ===========================================================================
# load_v2_paths — 3 路径任一缺失 → V2PathsError
# ===========================================================================


class TestLoadV2PathsMissing:
    """3 路径任一找不到 → 报错（不靠猜，不静默 default）。"""

    def test_missing_vendor_raises(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """vendor 没给 + env 也没 + json 也没 + probe 也没 → V2PathsError。"""
        _clean_env(
            monkeypatch,
            "TRESOS_HOME",
            "MCAL_VENDOR",
            "MCAL_VENDOR_HOME",
            "CLAUDE_AUTOSAR_CHIP",
        )
        # tresos 给（让流程走远一步到 vendor）
        tresos = _build_tresos_home(tmp_path / "t")
        monkeypatch.setattr(
            "claude_autosar.core.settings.v2_paths.TRESOS_CLI_WIN",
            tresos / "bin" / "tresos_cmd.bat",
        )
        monkeypatch.setattr(
            "claude_autosar.core.settings.v2_paths.DEFAULT_TRESOS_HOME_WIN",
            tresos,
        )
        monkeypatch.setattr("sys.platform", "win32")
        # 探测 vendor 表全空
        patched = {v: tuple() for v in MCAL_VENDORS}
        import claude_autosar.core.settings.v2_paths as mod
        monkeypatch.setattr(mod, "VENDOR_DEFAULT_HOMES", patched)

        with pytest.raises(V2PathsError, match="mcal_vendor"):
            load_v2_paths(project_root=tmp_path / "proj")

    def test_missing_vendor_home_raises(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """vendor 找到了但 vendor_home 没给 + env 也没 + json 也没 + probe 也没 → V2PathsError。"""
        _clean_env(
            monkeypatch,
            "TRESOS_HOME",
            "MCAL_VENDOR",
            "MCAL_VENDOR_HOME",
            "CLAUDE_AUTOSAR_CHIP",
        )
        tresos = _build_tresos_home(tmp_path / "t")
        monkeypatch.setattr(
            "claude_autosar.core.settings.v2_paths.TRESOS_CLI_WIN",
            tresos / "bin" / "tresos_cmd.bat",
        )
        monkeypatch.setattr(
            "claude_autosar.core.settings.v2_paths.DEFAULT_TRESOS_HOME_WIN",
            tresos,
        )
        monkeypatch.setattr("sys.platform", "win32")
        # vendor = "nxp"（env），但探测不到
        monkeypatch.setenv("MCAL_VENDOR", "nxp")
        patched = {v: (Path("/no/such"),) for v in MCAL_VENDORS}
        import claude_autosar.core.settings.v2_paths as mod
        monkeypatch.setattr(mod, "VENDOR_DEFAULT_HOMES", patched)

        with pytest.raises(V2PathsError, match="mcal_vendor_home"):
            load_v2_paths(project_root=tmp_path / "proj")

    def test_missing_chip_raises(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """chip 没给 + env 也没 + json 也没 + probe 也没 → V2PathsError。"""
        _clean_env(
            monkeypatch,
            "TRESOS_HOME",
            "MCAL_VENDOR",
            "MCAL_VENDOR_HOME",
            "CLAUDE_AUTOSAR_CHIP",
        )
        tresos = _build_tresos_home(tmp_path / "t")
        monkeypatch.setattr(
            "claude_autosar.core.settings.v2_paths.TRESOS_CLI_WIN",
            tresos / "bin" / "tresos_cmd.bat",
        )
        monkeypatch.setattr(
            "claude_autosar.core.settings.v2_paths.DEFAULT_TRESOS_HOME_WIN",
            tresos,
        )
        monkeypatch.setattr("sys.platform", "win32")
        # vendor + vendor_home 都给，但 chip 文件不在
        vendor_home = tmp_path / "v"
        vendor_home.mkdir()
        # 不创建 autosar/ 子目录 → probe 失败
        monkeypatch.setenv("MCAL_VENDOR", "nxp")
        monkeypatch.setenv("MCAL_VENDOR_HOME", str(vendor_home))

        with pytest.raises(V2PathsError, match="chip_derivative"):
            load_v2_paths(project_root=tmp_path / "proj")

    def test_missing_tresos_raises(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """tresos 4 级都没 → V2PathsError。"""
        _clean_env(
            monkeypatch,
            "TRESOS_HOME",
            "MCAL_VENDOR",
            "MCAL_VENDOR_HOME",
            "CLAUDE_AUTOSAR_CHIP",
        )
        monkeypatch.setattr(
            "claude_autosar.core.settings.v2_paths.TRESOS_CLI_WIN",
            Path("/no/such/tresos_cmd.bat"),
        )
        monkeypatch.setattr(
            "claude_autosar.core.settings.v2_paths.DEFAULT_TRESOS_HOME_WIN",
            Path("/no/such"),
        )
        monkeypatch.setattr("sys.platform", "win32")

        with pytest.raises(V2PathsError, match="tresos_home"):
            load_v2_paths(project_root=tmp_path / "proj")


# ===========================================================================
# settings.json 容错
# ===========================================================================


class TestSettingsJsonTolerance:
    """settings.json 缺字段 / 非法 / 顶层非 dict 容错。"""

    def test_missing_file_no_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``<proj>/.autoc/settings.json`` 不存在 → 当空处理（流程走 env / probe）。"""
        _clean_env(
            monkeypatch,
            "TRESOS_HOME",
            "MCAL_VENDOR",
            "MCAL_VENDOR_HOME",
            "CLAUDE_AUTOSAR_CHIP",
        )
        # 不创建 settings.json
        # 但 env 全给
        tresos = _build_tresos_home(tmp_path / "t")
        vendor_home = tmp_path / "v"
        vendor_home.mkdir()
        _build_chip_dir(vendor_home, "Mcu_x.epd")
        monkeypatch.setenv("TRESOS_HOME", str(tresos))
        monkeypatch.setenv("MCAL_VENDOR", "nxp")
        monkeypatch.setenv("MCAL_VENDOR_HOME", str(vendor_home))
        monkeypatch.setenv("CLAUDE_AUTOSAR_CHIP", "Mcu_x.epd")
        v = load_v2_paths(project_root=tmp_path / "proj")
        assert v.mcal_vendor == "nxp"

    def test_invalid_json_no_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """settings.json 非法 JSON → 当空（不抛）。"""
        _clean_env(
            monkeypatch,
            "TRESOS_HOME",
            "MCAL_VENDOR",
            "MCAL_VENDOR_HOME",
            "CLAUDE_AUTOSAR_CHIP",
        )
        cfg_dir = tmp_path / "proj" / ".autoc"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        (cfg_dir / SETTINGS_JSON_NAME).write_text(
            "{not valid json", encoding="utf-8"
        )
        # env 给全
        tresos = _build_tresos_home(tmp_path / "t")
        vendor_home = tmp_path / "v"
        vendor_home.mkdir()
        _build_chip_dir(vendor_home, "Mcu_x.epd")
        monkeypatch.setenv("TRESOS_HOME", str(tresos))
        monkeypatch.setenv("MCAL_VENDOR", "nxp")
        monkeypatch.setenv("MCAL_VENDOR_HOME", str(vendor_home))
        monkeypatch.setenv("CLAUDE_AUTOSAR_CHIP", "Mcu_x.epd")
        v = load_v2_paths(project_root=tmp_path / "proj")
        assert v.mcal_vendor == "nxp"

    def test_json_top_level_list_no_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """settings.json 顶层是 list → 当空。"""
        _clean_env(
            monkeypatch,
            "TRESOS_HOME",
            "MCAL_VENDOR",
            "MCAL_VENDOR_HOME",
            "CLAUDE_AUTOSAR_CHIP",
        )
        cfg_dir = tmp_path / "proj" / ".autoc"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        (cfg_dir / SETTINGS_JSON_NAME).write_text(
            json.dumps([1, 2, 3]), encoding="utf-8"
        )
        tresos = _build_tresos_home(tmp_path / "t")
        vendor_home = tmp_path / "v"
        vendor_home.mkdir()
        _build_chip_dir(vendor_home, "Mcu_x.epd")
        monkeypatch.setenv("TRESOS_HOME", str(tresos))
        monkeypatch.setenv("MCAL_VENDOR", "nxp")
        monkeypatch.setenv("MCAL_VENDOR_HOME", str(vendor_home))
        monkeypatch.setenv("CLAUDE_AUTOSAR_CHIP", "Mcu_x.epd")
        v = load_v2_paths(project_root=tmp_path / "proj")
        assert v.mcal_vendor == "nxp"

    def test_json_field_wrong_type_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """settings.json 字段类型错（如 int）→ V2PathsError（不静默）。"""
        _clean_env(
            monkeypatch,
            "TRESOS_HOME",
            "MCAL_VENDOR",
            "MCAL_VENDOR_HOME",
            "CLAUDE_AUTOSAR_CHIP",
        )
        cfg_dir = tmp_path / "proj" / ".autoc"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        (cfg_dir / SETTINGS_JSON_NAME).write_text(
            json.dumps({"mcal_vendor": 42}),
            encoding="utf-8",
        )
        with pytest.raises(V2PathsError, match="mcal_vendor.*字符串"):
            load_v2_paths(project_root=tmp_path / "proj")


# ===========================================================================
# write_settings_json + v1+v2 共存
# ===========================================================================


class TestWriteSettingsJson:
    """``write_settings_json`` 写文件 + v1 ``autoc.yaml`` 共存。"""

    def test_write_creates_file(
        self, tmp_path: Path
    ) -> None:
        """写 .autoc/settings.json 4 字段。"""
        v = V2Paths(
            tresos_home=Path("C:/EB/tresos"),
            mcal_vendor="nxp",
            mcal_vendor_home=Path("C:/NXP/AUTOSAR"),
            chip_derivative="Mcu_s32k148_lqfp176.epd",
        )
        path = write_settings_json(v, project_root=tmp_path)
        assert path.is_file()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["mcal_vendor"] == "nxp"
        assert data["chip_derivative"] == "Mcu_s32k148_lqfp176.epd"

    def test_write_creates_autoc_dir(
        self, tmp_path: Path
    ) -> None:
        """``.autoc/`` 不存在时自动创建。"""
        v = V2Paths(
            tresos_home=Path("C:/EB/tresos"),
            mcal_vendor="nxp",
            mcal_vendor_home=Path("C:/NXP/AUTOSAR"),
            chip_derivative="Mcu_s32k148_lqfp176.epd",
        )
        path = write_settings_json(v, project_root=tmp_path)
        assert (tmp_path / ".autoc").is_dir()
        assert path == tmp_path / ".autoc" / SETTINGS_JSON_NAME

    def test_v1_yaml_and_v2_json_coexist(
        self, tmp_path: Path
    ) -> None:
        """``.autoc/autoc.yaml`` + ``.autoc/settings.json`` 共存。"""
        from claude_autosar.core.config.project_config import ProjectConfig

        v1 = ProjectConfig(
            project_root=tmp_path,
            tresos_home=Path("C:/EB/tresos"),
            bswmd_root=tmp_path / ".autoc" / "bswmd" / "r22",
        )
        yaml_path = tmp_path / ".autoc" / "autoc.yaml"
        yaml_path.parent.mkdir(parents=True, exist_ok=True)
        yaml_path.write_text(v1.to_yaml(), encoding="utf-8")

        v2 = V2Paths(
            tresos_home=Path("C:/EB/tresos"),
            mcal_vendor="nxp",
            mcal_vendor_home=Path("C:/NXP/AUTOSAR"),
            chip_derivative="Mcu_s32k148_lqfp176.epd",
        )
        json_path = write_settings_json(v2, project_root=tmp_path)
        assert yaml_path.is_file()
        assert json_path.is_file()
        assert yaml_path.parent == json_path.parent
        # load_v2_paths 能读 json
        loaded = load_v2_paths(project_root=tmp_path)
        assert loaded.mcal_vendor == "nxp"
        # load_yaml 也能读 yaml
        from claude_autosar.core.config.project_config import load_yaml
        loaded_yaml = load_yaml(yaml_path)
        assert "project_root" in loaded_yaml


# ===========================================================================
# 探测表 — 5 vendor 内容正确
# ===========================================================================


class TestVendorTable:
    """5 vendor 探测表（PRD v2 §0.2.2）。"""

    def test_all_vendors_in_table(self) -> None:
        """5 vendor 都在 VENDOR_DEFAULT_HOMES。"""
        for v in MCAL_VENDORS:
            assert v in VENDOR_DEFAULT_HOMES
            assert len(VENDOR_DEFAULT_HOMES[v]) >= 1

    def test_mcal_vendors_tuple(self) -> None:
        """MCAL_VENDORS 恰好 5 个且顺序固定。"""
        assert MCAL_VENDORS == ("nxp", "st", "ti", "renesas", "infineon")

    def test_nxp_path(self) -> None:
        """NXP 默认路径是 ``C:\\NXP\\AUTOSAR``。"""
        paths = VENDOR_DEFAULT_HOMES["nxp"]
        assert any("NXP" in str(p).upper() for p in paths)

    def test_st_has_two_candidates(self) -> None:
        """ST 有 2 个候选（``SPC5`` / ``SPC58``）。"""
        paths = VENDOR_DEFAULT_HOMES["st"]
        assert len(paths) == 2
