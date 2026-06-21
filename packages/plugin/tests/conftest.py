"""Plugin 测试 conftest。

为 hooks 测试提供 tmp_path fixture（pytest 内建）+ sys.path 已加 hooks 目录。
"""

from pathlib import Path
import sys

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = PLUGIN_ROOT / "plugins" / "claude-autosar" / "hooks"
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))


@pytest.fixture
def plugin_root() -> Path:
    return PLUGIN_ROOT


@pytest.fixture
def hooks_dir() -> Path:
    return HOOKS_DIR
