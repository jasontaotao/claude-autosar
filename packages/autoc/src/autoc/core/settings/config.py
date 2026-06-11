"""JSON 配置文件读取与三级深度合并。

合并规则：
    - 标量值直接覆盖
    - dict 值递归合并
    - list / tuple 整体覆盖（不元素级合并）
    - 入参不可变（不修改 base / override）

读取规则：
    - 文件不存在或非 dict → 返回空 dict
    - JSON 解析错误 → 返回空 dict（不抛）
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """深度合并两个 dict：override 覆盖 base，嵌套 dict 递归合并。

    Args:
        base: 基础配置（不会被修改）
        override: 覆盖配置（不会被修改）

    Returns:
        新的合并后 dict
    """
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    """读 JSON 文件为 dict。

    容错策略：
        - 文件不存在 → 返回 {}
        - 解析错误 → 返回 {}
        - 顶层不是 dict（如 list / scalar）→ 返回 {}
    """
    if not path.is_file():
        return {}
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def load_merged_settings(
    global_path: Path,
    project_path: Path | None = None,
) -> dict[str, Any]:
    """加载并合并配置。

    优先级（高到低）：``project_path`` → ``global_path``。

    Args:
        global_path: 全局配置路径（``~/.autoc/agent/settings.json``）
        project_path: 项目级配置路径（``<cwd>/.autoc/settings.json``），可选
    """
    merged: dict[str, Any] = load_json(global_path)
    if project_path is not None:
        project_cfg = load_json(project_path)
        merged = deep_merge(merged, project_cfg)
    return merged
