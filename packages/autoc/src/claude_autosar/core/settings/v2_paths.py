"""``.autoc/settings.json`` schema + 加载器（Sprint 9.0 — T9.0.7）。

PRD v2 §0.2.2 锁定的 3 个用户配置路径：

    TRESOS_HOME          EB tresos CLI 根
    MCAL_VENDOR          MCAL 厂商（nxp / st / ti / renesas / infineon）
    MCAL_VENDOR_HOME     厂商 AUTOSAR 包根
    CHIP_DERIVATIVE      芯片派生（如 ``Mcu_s32k148_lqfp176.epd``）

**加载优先级链**（v2 新加 vs v1 ``autoc.yaml``）：

    1. 环境变量：``TRESOS_HOME`` / ``MCAL_VENDOR`` / ``MCAL_VENDOR_HOME`` /
       ``CLAUDE_AUTOSAR_CHIP``
    2. CLI 参数：``--tresos-home`` / ``--mcal-vendor`` / ``--mcal-vendor-home`` /
       ``--chip``
    3. 配置文件：``<project>/.autoc/settings.json``（**v2 新增**，与 v1
       ``autoc.yaml`` 共存；v1 不读这个文件，v2 不读 ``autoc.yaml``）
    4. 缺省：``_probe_*`` 函数平台默认探测 + 找不到报错

**契约**（PRD v2 §0.2.2 + Sprint 9.0 T9.0.7）：

- :class:`V2Paths` 是不可变 dataclass（frozen）
- 4 字段全 ``str`` / ``Path``，无 None（找不到直接抛 :class:`V2PathsError`）
- :func:`load_v2_paths` 严格按上面 4 级优先级合并
- :func:`V2Paths.to_json` 序列化回 ``settings.json``（v1 ``autoc.yaml``
  由 :mod:`claude_autosar.core.config.project_config` 单独写）
- 探测表覆盖 5 vendor，每个 vendor 给 1-2 个默认路径
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
import platform
import sys
from typing import Any, Final, Literal

__all__ = [
    "V2Paths",
    "V2PathsError",
    "MCAL_VENDORS",
    "load_v2_paths",
    "probe_tresos_home",
    "probe_mcal_vendor_home",
    "probe_chip_derivative",
    "DEFAULT_TRESOS_HOME_WIN",
    "DEFAULT_TRESOS_HOME_LINUX",
    "VENDOR_DEFAULT_HOMES",
]


# =============================================================================
# 类型 / 常量
# =============================================================================


#: v2 支持的 5 个 MCAL vendor（PRD v2 §0.2.2 — 用户 2026-06-12 当面拍板"通用一点"）。
MCAL_VENDORS: Final[tuple[str, ...]] = ("nxp", "st", "ti", "renesas", "infineon")

#: 同上但作 ``Literal`` 用（strict type check）。
McalVendor = Literal["nxp", "st", "ti", "renesas", "infineon"]

#: 平台默认 TRESOS_HOME（Win / Linux）。
DEFAULT_TRESOS_HOME_WIN: Final[Path] = Path(r"C:\EB\tresos")
DEFAULT_TRESOS_HOME_LINUX: Final[Path] = Path("/opt/tresos")

#: 平台默认 TRESOS_HOME 验证文件（存在即认为 EB tresos 装好）。
TRESOS_CLI_WIN: Final[Path] = Path(r"C:\EB\tresos\bin\tresos_cmd.bat")
TRESOS_CLI_LINUX: Final[Path] = Path("/opt/tresos/bin/tresos_cmd")

#: 5 vendor 的默认 MCAL_VENDOR_HOME 探测表（PRD v2 §0.2.2）。
#: 每个 vendor 给 1-2 个候选路径，按列表顺序探，第一个存在的胜出。
VENDOR_DEFAULT_HOMES: Final[dict[str, tuple[Path, ...]]] = {
    "nxp": (Path(r"C:\NXP\AUTOSAR"),),
    "st": (
        Path(r"C:\ST\AUTOSAR\SPC5"),
        Path(r"C:\ST\SPC58"),
    ),
    "ti": (Path(r"C:\ti\AUTOSAR"),),
    "renesas": (Path(r"C:\Renesas\AUTOSAR"),),
    "infineon": (Path(r"C:\Infineon\AURIX"),),
}

#: settings.json 内 4 字段的 JSON key 名（snake_case，跟 v1 ``autoc.yaml`` 对齐）。
_FIELD_TRESOS_HOME: Final[str] = "tresos_home"
_FIELD_MCAL_VENDOR: Final[str] = "mcal_vendor"
_FIELD_MCAL_VENDOR_HOME: Final[str] = "mcal_vendor_home"
_FIELD_CHIP_DERIVATIVE: Final[str] = "chip_derivative"

#: settings.json 文件名（v2 新加；与 v1 ``autoc.yaml`` 共存于 ``<project>/.autoc/``）。
SETTINGS_JSON_NAME: Final[str] = "settings.json"

#: 环境变量名（PRD v2 §0.2.2 优先级链 1）。
ENV_TRESOS_HOME: Final[str] = "TRESOS_HOME"
ENV_MCAL_VENDOR: Final[str] = "MCAL_VENDOR"
ENV_MCAL_VENDOR_HOME: Final[str] = "MCAL_VENDOR_HOME"
ENV_CHIP_DERIVATIVE: Final[str] = "CLAUDE_AUTOSAR_CHIP"

#: <vendor>/autosar/*.epd glob 模式；扫到第一个 ``.epd`` 即返回。
_CHIP_GLOB: Final[str] = "*.epd"


# =============================================================================
# 错误类型
# =============================================================================


class V2PathsError(RuntimeError):
    """``V2Paths`` 加载 / 探测 / 校验失败。"""


# =============================================================================
# 数据模型
# =============================================================================


@dataclass(frozen=True)
class V2Paths:
    """v2 路径配置（4 字段全填满；找不到 → 构造时抛 :class:`V2PathsError`）。

    Attributes:
        tresos_home: EB tresos CLI 根（Win: ``C:\\EB\\tresos``，Linux:
            ``/opt/tresos``）
        mcal_vendor: MCAL 厂商标识（``nxp`` / ``st`` / ``ti`` /
            ``renesas`` / ``infineon``）
        mcal_vendor_home: 厂商 AUTOSAR 包根（按 vendor 表探测）
        chip_derivative: 芯片派生文件名（``<module>_<chip>_<pkg>.epd``）
    """

    tresos_home: Path
    mcal_vendor: str
    mcal_vendor_home: Path
    chip_derivative: str

    def __post_init__(self) -> None:
        """构造后立即校验 — 4 字段全必填，vendor 必须 in MCAL_VENDORS。"""
        if self.mcal_vendor not in MCAL_VENDORS:
            raise V2PathsError(
                f"mcal_vendor 必须是 {MCAL_VENDORS!r} 之一，得到 "
                f"{self.mcal_vendor!r}",
            )
        if not self.tresos_home or str(self.tresos_home) == "":
            raise V2PathsError("tresos_home 不能为空")
        if not self.mcal_vendor_home or str(self.mcal_vendor_home) == "":
            raise V2PathsError("mcal_vendor_home 不能为空")
        if not self.chip_derivative or self.chip_derivative.strip() == "":
            raise V2PathsError("chip_derivative 不能为空")
        if not self.chip_derivative.endswith(".epd"):
            raise V2PathsError(
                f"chip_derivative 应以 '.epd' 结尾，得到 {self.chip_derivative!r}",
            )

    # ------------------------------------------------------------------
    # 序列化
    # ------------------------------------------------------------------

    def to_json(self) -> str:
        """序列化为 ``settings.json`` 格式字符串。

        路径用 POSIX 风格（``/`` 替代 ``\\``）—— 跨平台可读；json 模块
        接受 ``\\`` 但 ``/`` 在 settings.json 里更干净。
        """
        payload: dict[str, str] = {
            _FIELD_TRESOS_HOME: self.tresos_home.as_posix(),
            _FIELD_MCAL_VENDOR: self.mcal_vendor,
            _FIELD_MCAL_VENDOR_HOME: self.mcal_vendor_home.as_posix(),
            _FIELD_CHIP_DERIVATIVE: self.chip_derivative,
        }
        return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

    def to_dict(self) -> dict[str, str]:
        """返回 dataclass 字段的 dict 表达（路径用 ``str(Path)``，含 OS 风格）。"""
        out = asdict(self)
        # asdict 对 Path 保留为 Path，转 str 给下游用
        out[_FIELD_TRESOS_HOME] = str(self.tresos_home)
        out[_FIELD_MCAL_VENDOR_HOME] = str(self.mcal_vendor_home)
        return out


# =============================================================================
# 探测函数（priority chain 第 4 级 — 平台默认）
# =============================================================================


def probe_tresos_home() -> Path | None:
    """按平台返回默认 EB tresos 安装目录；不存在 → ``None``。

    Win:  ``C:\\EB\\tresos``（验 ``bin\\tresos_cmd.bat``）
    Linux: ``/opt/tresos``（验 ``bin/tresos_cmd``）
    其他平台 → ``None``。
    """
    if sys.platform == "win32":
        candidates = (TRESOS_CLI_WIN, DEFAULT_TRESOS_HOME_WIN)
    elif sys.platform.startswith("linux"):
        candidates = (TRESOS_CLI_LINUX, DEFAULT_TRESOS_HOME_LINUX)
    else:
        return None
    for c in candidates:
        if c.is_file() or c.is_dir():
            # 优先返回 ``bin/`` 的父目录（即 tresos 根）
            if c.name in ("tresos_cmd.bat", "tresos_cmd"):
                root = c.parent.parent
                if root.is_dir():
                    return root.resolve()
            elif c.is_dir():
                return c.resolve()
    return None


def probe_mcal_vendor_home(vendor: str) -> Path | None:
    """按 vendor 查表返回默认 MCAL_VENDOR_HOME；不在表 / 不存在 → ``None``。

    Args:
        vendor: ``nxp`` / ``st`` / ``ti`` / ``renesas`` / ``infineon``
    """
    if vendor not in MCAL_VENDORS:
        return None
    for candidate in VENDOR_DEFAULT_HOMES[vendor]:
        if candidate.is_dir():
            return candidate.resolve()
    return None


def probe_chip_derivative(vendor_home: Path) -> str | None:
    """扫 ``<vendor_home>/autosar/*.epd`` 返回第一个 ``.epd`` 文件名；找不到 → ``None``。

    排序后取第一个（稳定）；不递归（``autosar/`` 是单层）。
    """
    autosar_dir = vendor_home / "autosar"
    if not autosar_dir.is_dir():
        return None
    candidates = sorted(autosar_dir.glob(_CHIP_GLOB))
    if not candidates:
        return None
    return candidates[0].name


# =============================================================================
# 加载器（priority chain）
# =============================================================================


@dataclass(frozen=True)
class _Overrides:
    """CLI 参数 / 显式 override（priority chain 第 2 级）。"""

    tresos_home: Path | None = None
    mcal_vendor: str | None = None
    mcal_vendor_home: Path | None = None
    chip_derivative: str | None = None


def _read_settings_json(project_root: Path) -> dict[str, Any]:
    """读 ``<project_root>/.autoc/settings.json``；缺失/非法 → ``{}``。"""
    path = project_root / ".autoc" / SETTINGS_JSON_NAME
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _coalesce(
    *,
    field_name: str,
    cli_value: str | Path | None,
    env_var: str,
    json_value: Any,
    probed_value: str | Path | None,
) -> str:
    """4 级优先级合并（CLI > env > settings.json > probe）。

    Returns:
        非空字符串值（任何一级非空 / 非 None 即返回）。

    Raises:
        V2PathsError: 4 级都没找到 + 探测返回 None。
    """
    # 1. CLI 参数
    if cli_value is not None and str(cli_value) != "":
        return str(cli_value)
    # 2. 环境变量
    env_raw = os.environ.get(env_var, "").strip()
    if env_raw:
        return env_raw
    # 3. settings.json
    if json_value is not None and json_value != "":
        if not isinstance(json_value, str):
            raise V2PathsError(
                f"settings.json 字段 {field_name!r} 必须是字符串，"
                f"得到 {type(json_value).__name__}",
            )
        return json_value
    # 4. 探测
    if probed_value is not None and str(probed_value) != "":
        return str(probed_value)
    # 全空 → 报错（不靠猜）
    raise V2PathsError(
        f"无法解析 {field_name!r}：CLI 参数 / 环境变量 {env_var} / "
        f"settings.json 字段 / 平台默认探测全部为空。"
        f"请通过 --{field_name.replace('_', '-')} 提供，或"
        f"设置环境变量 {env_var}，或编辑 .autoc/settings.json",
    )


def load_v2_paths(
    project_root: Path | None = None,
    *,
    cli_tresos_home: str | Path | None = None,
    cli_mcal_vendor: str | None = None,
    cli_mcal_vendor_home: str | Path | None = None,
    cli_chip_derivative: str | None = None,
) -> V2Paths:
    """加载 v2 4 路径配置（4 级优先级 + 探测）。

    Priority chain（高 → 低）：
        1. ``cli_*`` 参数（调用方传入）
        2. 环境变量 ``TRESOS_HOME`` / ``MCAL_VENDOR`` /
           ``MCAL_VENDOR_HOME`` / ``CLAUDE_AUTOSAR_CHIP``
        3. ``<project_root>/.autoc/settings.json``
        4. 平台默认探测（``probe_*``）

    Args:
        project_root: 工程根；``None`` 时用 :func:`os.getcwd`。
        cli_*: 4 个 CLI 参数 / 显式 override（priority 1）。

    Returns:
        4 字段全填满的 :class:`V2Paths`。

    Raises:
        V2PathsError: 任何字段 4 级都拿不到（不靠猜，不静默 default）。
    """
    base_dir = (
        Path(project_root) if project_root is not None else Path(os.getcwd())
    )
    json_data = _read_settings_json(base_dir)

    # --- 3 路径独立合并（互不依赖；vendor 缺时 vendor_home 探测先看
    # 是否有 vendor 名，否则跳过 vendor_home 探测直接报错）
    tresos_home_str = _coalesce(
        field_name=_FIELD_TRESOS_HOME,
        cli_value=cli_tresos_home,
        env_var=ENV_TRESOS_HOME,
        json_value=json_data.get(_FIELD_TRESOS_HOME),
        probed_value=probe_tresos_home(),
    )

    mcal_vendor_str = _coalesce(
        field_name=_FIELD_MCAL_VENDOR,
        cli_value=cli_mcal_vendor,
        env_var=ENV_MCAL_VENDOR,
        json_value=json_data.get(_FIELD_MCAL_VENDOR),
        probed_value=None,  # vendor 没有"平台默认" — 强制用户显式指定
    )

    # vendor_home 探测依赖 vendor：先确定 vendor 再扫
    mcal_vendor_home_str = _coalesce(
        field_name=_FIELD_MCAL_VENDOR_HOME,
        cli_value=cli_mcal_vendor_home,
        env_var=ENV_MCAL_VENDOR_HOME,
        json_value=json_data.get(_FIELD_MCAL_VENDOR_HOME),
        probed_value=probe_mcal_vendor_home(mcal_vendor_str),
    )

    # chip_derivative 探测依赖 vendor_home：先确定 vendor_home 再扫
    chip_derivative_str = _coalesce(
        field_name=_FIELD_CHIP_DERIVATIVE,
        cli_value=cli_chip_derivative,
        env_var=ENV_CHIP_DERIVATIVE,
        json_value=json_data.get(_FIELD_CHIP_DERIVATIVE),
        probed_value=probe_chip_derivative(Path(mcal_vendor_home_str)),
    )

    return V2Paths(
        tresos_home=Path(tresos_home_str),
        mcal_vendor=mcal_vendor_str,
        mcal_vendor_home=Path(mcal_vendor_home_str),
        chip_derivative=chip_derivative_str,
    )


# =============================================================================
# 写 settings.json（init 向导用）
# =============================================================================


def write_settings_json(paths: V2Paths, project_root: Path) -> Path:
    """写 ``<project_root>/.autoc/settings.json``；返回写入的路径。

    自动 ``mkdir -p`` ``.autoc/`` 目录。

    Raises:
        OSError: 写失败。
    """
    target = project_root / ".autoc" / SETTINGS_JSON_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(paths.to_json(), encoding="utf-8")
    return target


# 显式占位：防 lint 误删 platform import
_platform_marker = platform
# McalVendor = Literal[...] 仅为类型注解，运行时不需要
_literal_marker = "Literal"
