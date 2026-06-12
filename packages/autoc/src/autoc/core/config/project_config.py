"""``ProjectConfig`` 数据模型 — EB tresos 工程配置（三层合并：cwd > user-level > default）。

Sprint 8.E — T8.E.0a。契约 1 锁定：frozen dataclass + ``load()`` 三层合并 + ``to_yaml()``。

合并规则（D13 决定 cwd 驱动）：
    1. ``<cwd>/.autoc/autoc.yaml``              # 工程本地（最高优先）
    2. ``~/.autoc/agent/autoc.yaml``             # 用户级
    3. 平台默认 tresos_home 探测                 # 兜底（Win: C:\\Program Files (x86)\\FlexCFG）

缺省行为（D12 决定强制）：未找到任何配置 → 抛 ``ProjectConfigError``，提示运行 ``autoc init``。
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import platform
import sys
from typing import Any

__all__ = [
    "ProjectConfig",
    "ProjectConfigError",
    "load_yaml",
    "default_tresos_home",
]

# YAML 字段名（契约 6 — snake_case）
_FIELD_PROJECT_ROOT = "project_root"
_FIELD_TRESOS_HOME = "tresos_home"
_FIELD_EXTRA_BSWMD_PATHS = "extra_bswmd_paths"

# 工程本地配置路径
_LOCAL_CONFIG = Path(".autoc") / "autoc.yaml"

# 用户级配置路径
_USER_CONFIG = Path.home() / ".autoc" / "agent" / "autoc.yaml"

# 平台默认 EB tresos 安装目录
_PLATFORM_DEFAULT_TRESOS_HOME_WIN = Path(r"C:\Program Files (x86)\FlexCFG")
_PLATFORM_DEFAULT_TRESOS_HOME_LINUX = Path("/opt/FlexCFG")


# =============================================================================
# 错误类型
# =============================================================================


class ProjectConfigError(RuntimeError):
    """``ProjectConfig`` 加载 / 校验失败。"""


# =============================================================================
# 平台默认探测
# =============================================================================


def default_tresos_home() -> Path | None:
    """按平台返回默认 EB tresos 安装目录；不存在则返回 ``None``。

    - Win: ``C:\\Program Files (x86)\\FlexCFG``
    - Linux: ``/opt/FlexCFG``
    - 其他: ``None``（用户须显式提供）
    """
    if sys.platform == "win32":
        candidate = _PLATFORM_DEFAULT_TRESOS_HOME_WIN
    elif sys.platform.startswith("linux"):
        candidate = _PLATFORM_DEFAULT_TRESOS_HOME_LINUX
    else:
        return None
    if candidate.is_dir():
        return candidate.resolve()
    return None


# =============================================================================
# 极简 YAML 1.2 解析（无 PyYAML 依赖）
# =============================================================================


def load_yaml(path: Path) -> dict[str, Any]:
    """读 YAML 文件为 dict。

    极简解析器：只支持契约 6 描述的字段（str / ``null`` / list[str]）。
    - 文件不存在 → ``{}``
    - 解析错误 → ``{}``（容错；用户级 / 工程级 YAML 不阻塞 init）
    - 顶层不是 dict → ``{}``
    """
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    try:
        parsed = _parse_yaml_simple(text)
    except _YAMLError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return parsed


class _YAMLError(Exception):
    """极简 YAML 解析失败。"""


def _parse_yaml_simple(text: str) -> Any:
    """极简 YAML 解析（只支持 契约 6 schema）。

    支持：
        key: "value"          # 引号字符串
        key: value            # 无引号字符串
        key: null             # null
        key:                  # null
        key:                  # nested dict
          sub: "v"
        - "item"               # list
        - item                 # list
        # comment             # 注释
    """
    lines = _strip_comments_and_blanks(text)
    if not lines:
        return {}
    # 顶层必须是 dict（list 不符合 autoc.yaml 契约）
    value, _ = _parse_block(lines, 0, 0)
    if value is None:
        return {}
    return value


def _strip_comments_and_blanks(text: str) -> list[str]:
    """逐行去掉 ``#`` 注释和空行，保留行内引号。"""
    out: list[str] = []
    for raw in text.splitlines():
        # 去掉行尾注释（但保留 # 出现在引号内的情况）
        in_str = False
        quote_char = ""
        cleaned_chars: list[str] = []
        i = 0
        while i < len(raw):
            ch = raw[i]
            if in_str:
                if ch == "\\" and i + 1 < len(raw):
                    cleaned_chars.append(ch)
                    cleaned_chars.append(raw[i + 1])
                    i += 2
                    continue
                if ch == quote_char:
                    in_str = False
                cleaned_chars.append(ch)
                i += 1
                continue
            if ch in ('"', "'"):
                in_str = True
                quote_char = ch
                cleaned_chars.append(ch)
                i += 1
                continue
            if ch == "#":
                break
            cleaned_chars.append(ch)
            i += 1
        line = "".join(cleaned_chars).rstrip()
        if line.strip():
            out.append(line)
    return out


def _indent_of(line: str) -> int:
    """返回行首缩进空格数。"""
    return len(line) - len(line.lstrip(" "))


def _parse_block(lines: list[str], start: int, indent: int) -> tuple[Any, int]:
    """解析一个 block（dict 或 list），从 lines[start] 起。

    Returns:
        (parsed_value, next_index)。next_index 指向 block 之后的第一行。
    """
    if not lines or start >= len(lines):
        return None, start
    first_indent = _indent_of(lines[start])
    if first_indent < indent:
        return None, start
    # 判断 dict 还是 list
    s = lines[start].lstrip()
    if s.startswith("- "):
        return _parse_list(lines, start, indent)
    return _parse_dict(lines, start, indent)


def _parse_dict(lines: list[str], start: int, indent: int) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    i = start
    while i < len(lines):
        line = lines[i]
        cur_indent = _indent_of(line)
        if cur_indent < indent:
            break
        if cur_indent > indent:
            raise _YAMLError(f"unexpected indent at line {i + 1}: {line!r}")
        s = line.lstrip()
        if s.startswith("- "):
            break
        # 找到 key 与 value 分隔点
        if ":" not in s:
            raise _YAMLError(f"expected key:value at line {i + 1}: {line!r}")
        key_part, _, value_part = s.partition(":")
        key = key_part.strip()
        value_part = value_part.lstrip()
        if not value_part:
            # nested block：子行 indent > cur_indent
            if i + 1 < len(lines) and _indent_of(lines[i + 1]) > cur_indent:
                # 用实际子行 indent 解析（不强制 cur_indent + 1）
                nested, i = _parse_block(lines, i + 1, _indent_of(lines[i + 1]))
                result[key] = nested
                continue
            result[key] = None
            i += 1
            continue
        result[key] = _parse_scalar(value_part)
        i += 1
    return result, i


def _parse_list(lines: list[str], start: int, indent: int) -> tuple[list[Any], int]:
    result: list[Any] = []
    i = start
    while i < len(lines):
        line = lines[i]
        cur_indent = _indent_of(line)
        if cur_indent < indent:
            break
        if cur_indent > indent:
            raise _YAMLError(f"unexpected indent in list at line {i + 1}: {line!r}")
        s = line.lstrip()
        if not s.startswith("- "):
            break
        item_str = s[2:].strip()
        if not item_str:
            # 多行 list item
            if i + 1 < len(lines) and _indent_of(lines[i + 1]) > cur_indent:
                # 用实际子行 indent 解析（不强制 cur_indent + 1）
                nested, i = _parse_block(
                    lines,
                    i + 1,
                    _indent_of(lines[i + 1]),
                )
                result.append(nested)
                continue
            result.append(None)
            i += 1
            continue
        result.append(_parse_scalar(item_str))
        i += 1
    return result, i


def _parse_scalar(token: str) -> Any:
    """解析标量：str / null。"""
    token = token.strip()
    if not token:
        return None
    if token == "null" or token == "~":
        return None
    if (token.startswith('"') and token.endswith('"')) or (
        token.startswith("'") and token.endswith("'")
    ):
        # 解引号 + 反转义
        inner = token[1:-1]
        if token.startswith('"'):
            return inner.replace('\\"', '"').replace("\\\\", "\\")
        # YAML single-quoted: '' 表示单引号
        return inner.replace("''", "'")
    return token


# =============================================================================
# ProjectConfig
# =============================================================================


@dataclass(frozen=True)
class ProjectConfig:
    """EB tresos 工程配置（不可变；三层合并后冻结）。

    Attributes:
        project_root: EB tresos 工程根（含 ``.prefs/``）。必填。
        tresos_home: EB tresos 安装目录（用于 copy BSWMD）；可空。
        bswmd_root: BSWMD 副本根目录（默认 ``<project_root>/.autoc/bswmd/r22/``）。
        extra_bswmd_paths: 三方 CDD BSWMD 搜索路径。
    """

    project_root: Path
    tresos_home: Path | None
    bswmd_root: Path
    extra_bswmd_paths: tuple[Path, ...] = field(default_factory=tuple)

    # ------------------------------------------------------------------
    # 构造
    # ------------------------------------------------------------------

    @classmethod
    def load(
        cls,
        *,
        cwd: Path | None = None,
    ) -> ProjectConfig:
        """三层合并加载（D13 决定 cwd 驱动）。

        1. ``<cwd>/.autoc/autoc.yaml``              # 工程本地（最高优先）
        2. ``~/.autoc/agent/autoc.yaml``             # 用户级
        3. 平台默认 ``tresos_home`` 探测              # 兜底

        全部缺失 → 抛 :class:`ProjectConfigError`（D12 决定强制）。
        ``project_root`` 缺字段 → 抛错并指出字段名。

        Args:
            cwd: 起始目录；``None`` 时用 :func:`os.getcwd`。
        """
        base_dir = Path(cwd) if cwd is not None else Path(os.getcwd())
        local_path = (base_dir / _LOCAL_CONFIG).resolve()
        user_path = _USER_CONFIG

        local_data = load_yaml(local_path)
        user_data = load_yaml(user_path)

        # 三层合并：local 覆盖 user
        merged = _merge_yaml(user_data, local_data)

        # 必填字段校验
        project_root_raw = merged.get(_FIELD_PROJECT_ROOT)
        if not project_root_raw or not isinstance(project_root_raw, str):
            raise ProjectConfigError(
                f"未找到 autoc.yaml 或缺字段 '{_FIELD_PROJECT_ROOT}'。"
                f"请先运行 `autoc init` 配置 EB tresos 工程。",
            )

        # 可选字段
        tresos_home_raw = merged.get(_FIELD_TRESOS_HOME)
        tresos_home: Path | None
        if tresos_home_raw is None or tresos_home_raw == "":
            tresos_home = default_tresos_home()
        elif isinstance(tresos_home_raw, str):
            tresos_home = Path(tresos_home_raw).expanduser()
        else:
            raise ProjectConfigError(
                f"字段 '{_FIELD_TRESOS_HOME}' 必须是字符串路径或 null。",
            )

        extra_raw = merged.get(_FIELD_EXTRA_BSWMD_PATHS) or []
        if not isinstance(extra_raw, list):
            raise ProjectConfigError(
                f"字段 '{_FIELD_EXTRA_BSWMD_PATHS}' 必须是字符串列表。",
            )
        extra_paths: list[Path] = []
        for item in extra_raw:
            if not isinstance(item, str):
                raise ProjectConfigError(
                    f"'{_FIELD_EXTRA_BSWMD_PATHS}' 列表元素必须是字符串。",
                )
            extra_paths.append(Path(item).expanduser())

        # 解析 project_root 为绝对路径
        project_root = Path(project_root_raw).expanduser()
        if not project_root.is_absolute():
            project_root = (base_dir / project_root).resolve()
        else:
            project_root = project_root.resolve()

        # bswmd_root 默认 <project_root>/.autoc/bswmd/r22/
        bswmd_root = (project_root / ".autoc" / "bswmd" / "r22").resolve()

        return cls(
            project_root=project_root,
            tresos_home=tresos_home,
            bswmd_root=bswmd_root,
            extra_bswmd_paths=tuple(extra_paths),
        )

    # ------------------------------------------------------------------
    # 不可变操作
    # ------------------------------------------------------------------

    def with_extra_bswmd_path(self, p: Path) -> ProjectConfig:
        """不可变地追加一个 extra BSWMD 路径。返回新实例。"""
        return ProjectConfig(
            project_root=self.project_root,
            tresos_home=self.tresos_home,
            bswmd_root=self.bswmd_root,
            extra_bswmd_paths=(*self.extra_bswmd_paths, p.expanduser()),
        )

    # ------------------------------------------------------------------
    # 序列化
    # ------------------------------------------------------------------

    def to_yaml(self) -> str:
        """序列化为 ``autoc.yaml`` 格式字符串（契约 6 schema）。

        字段名 snake_case；路径用 ``"`` 引号包（避免反斜杠转义问题）。
        """
        lines: list[str] = []
        lines.append("# 由 `autoc init` 生成；可手动编辑")
        lines.append(f"{_FIELD_PROJECT_ROOT}: {_quote(self.project_root.as_posix())}")
        if self.tresos_home is not None:
            lines.append(
                f"{_FIELD_TRESOS_HOME}: {_quote(self.tresos_home.as_posix())}",
            )
        else:
            lines.append(f"{_FIELD_TRESOS_HOME}: null")
        if self.extra_bswmd_paths:
            lines.append(f"{_FIELD_EXTRA_BSWMD_PATHS}:")
            for p in self.extra_bswmd_paths:
                lines.append(f"  - {_quote(p.as_posix())}")
        else:
            lines.append(f"{_FIELD_EXTRA_BSWMD_PATHS}: []")
        return "\n".join(lines) + "\n"


# =============================================================================
# 内部：YAML dict 合并
# =============================================================================


def _merge_yaml(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """简单 dict 合并：override 覆盖 base；不递归（autoc.yaml 顶层结构）。"""
    out: dict[str, Any] = dict(base)
    for k, v in override.items():
        out[k] = v
    return out


def _quote(s: str) -> str:
    """YAML 双引号字符串；内部双引号转义。"""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


# 显式暴露给 type checker：platform 模块已使用（占位防 lint 警告）
_ = platform
