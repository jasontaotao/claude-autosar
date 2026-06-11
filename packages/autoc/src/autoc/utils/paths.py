"""跨平台路径解析。

约定：
    - 全局配置：``~/.autoc/agent/``（由 platformdirs 决定 Windows/Linux/macOS）
    - 全局会话：``~/.autoc/agent/sessions/``
    - 全局日志：``<user_log_dir>/autoc-tool/``
    - 项目配置：``<cwd>/.autoc/``
"""

from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_config_dir, user_data_dir, user_log_dir

APP_NAME = "autoc"
APP_AUTHOR = "autoc-tool"


def global_config_dir() -> Path:
    """全局配置目录：``~/.autoc/agent/``（跨平台）。"""
    p = Path(user_config_dir(APP_NAME, APP_AUTHOR, roaming=False))
    p.mkdir(parents=True, exist_ok=True)
    return p


def global_data_dir() -> Path:
    """全局数据目录。"""
    p = Path(user_data_dir(APP_NAME, APP_AUTHOR, roaming=False))
    p.mkdir(parents=True, exist_ok=True)
    return p


def global_session_dir() -> Path:
    """全局会话目录：``<config_dir>/sessions/``。"""
    p = global_config_dir() / "sessions"
    p.mkdir(parents=True, exist_ok=True)
    return p


def global_log_dir() -> Path:
    """全局日志目录。"""
    p = Path(user_log_dir(APP_NAME, APP_AUTHOR))
    p.mkdir(parents=True, exist_ok=True)
    return p


def project_config_dir(cwd: Path | str | None = None) -> Path:
    """项目级配置目录：``<cwd>/.autoc/``。

    若不存在会自动创建。``cwd`` 默认 ``Path.cwd()``。
    """
    base = Path(cwd) if cwd else Path.cwd()
    p = base / ".autoc"
    p.mkdir(parents=True, exist_ok=True)
    return p


def find_ancestor_file(
    filename: str,
    start: Path | str | None = None,
) -> Path | None:
    """从 ``start`` 向上逐级查找 ``filename``，找到返回绝对路径，否则 None。"""
    base = Path(start) if start else Path.cwd()
    base = base.resolve()
    for ancestor in [base, *base.parents]:
        candidate = ancestor / filename
        if candidate.is_file():
            return candidate
    return None


def normalize_path(path: str | Path) -> Path:
    """规范化路径：展开 ``~`` 与环境变量，转为绝对路径。"""
    return Path(os.path.expandvars(os.path.expanduser(str(path)))).resolve()
