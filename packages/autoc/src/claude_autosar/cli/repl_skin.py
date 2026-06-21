"""AutoC Rich-based CLI 样式层（Sprint 5 — T5.2）。

提供：
- :data:`AUTOC_THEME`: 语义化样式集合（success / error / warning / info / hint 等）
- :func:`make_console`: 标准 Console 工厂（处理 no-color / force-terminal）
- :func:`detect_no_color`: 探测 ``NO_COLOR`` 环境 + ``isatty()``
- :class:`ReplSkin`: 业务层样式 API（status messages / table / callout / banner）

设计原则：
- 0 新依赖（``rich>=13`` 已在 pyproject）
- 注入式 ``console`` 参数（便于测试 + 多 context 复用）
- 不可变性贯穿：所有 ``print_*`` 方法只读不写，调用者决定何时何地打印
"""

from __future__ import annotations

import os
import sys
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.theme import Theme

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

AUTOC_THEME: Theme = Theme(
    {
        "success": "bold green",
        "error": "bold red",
        "warning": "bold yellow",
        "info": "cyan",
        "hint": "dim",
        "accent": "bold magenta",
        "muted": "grey50",
        "border": "grey50",
    }
)


# ---------------------------------------------------------------------------
# Console 工厂 / no-color 探测
# ---------------------------------------------------------------------------


def detect_no_color() -> bool:
    """按 :rfc:`NO_COLOR` 约定 + isatty() 探测是否禁用颜色。

    优先级：
    1. ``NO_COLOR`` 环境变量被设置（任意非空值）→ True
    2. ``sys.stdout`` 不是 TTY（管道 / 重定向）→ True
    3. 否则 → False
    """
    if "NO_COLOR" in os.environ:
        return True
    try:
        return not sys.stdout.isatty()
    except (AttributeError, ValueError):
        return True


def make_console(
    *,
    no_color: bool | None = None,
    force_terminal: bool | None = None,
) -> Console:
    """构造带 autoc 主题的标准 :class:`rich.console.Console`。

    :param no_color: 显式禁用 ANSI；``None`` 时按 :func:`detect_no_color` 探测
    :param force_terminal: True/False 强制；``None`` 让 Rich 自动检测
    """
    if no_color is None:
        no_color = detect_no_color()
    return Console(
        theme=AUTOC_THEME,
        no_color=no_color,
        force_terminal=force_terminal,
        soft_wrap=False,
        highlight=False,
    )


# ---------------------------------------------------------------------------
# ReplSkin
# ---------------------------------------------------------------------------


class ReplSkin:
    """autoc CLI 业务层样式 API。

    用法::

        skin = ReplSkin("autoc", console=Console())
        skin.success("Project saved")
        skin.table(["ID", "Name"], [["1", "alpha"]])
    """

    #: 成功前缀
    _OK = "✓"
    #: 失败前缀
    _ERR = "✗"
    #: 警告前缀
    _WARN = "⚠"
    #: 信息前缀
    _INFO = "●"
    #: 提示前缀
    _HINT = "→"

    def __init__(
        self,
        software: str,
        version: str = "0.1.0",
        *,
        console: Console | None = None,
    ) -> None:
        self.software = software
        self.version = version
        self.console = console if console is not None else make_console()

    # ---- 状态消息 -------------------------------------------------------

    def success(self, message: str) -> None:
        self.console.print(f"[success]{self._OK} {message}[/success]")

    def error(self, message: str) -> None:
        self.console.print(f"[error]{self._ERR} {message}[/error]")

    def warning(self, message: str) -> None:
        self.console.print(f"[warning]{self._WARN} {message}[/warning]")

    def info(self, message: str) -> None:
        self.console.print(f"[info]{self._INFO} {message}[/info]")

    def hint(self, message: str) -> None:
        self.console.print(f"[hint]{self._HINT} {message}[/hint]")

    # ---- 结构化元素 -----------------------------------------------------

    def section(self, title: str) -> None:
        """Section header：粗体标题 + 横线。"""
        self.console.rule(f"[accent]{title}[/accent]")

    def table(
        self,
        headers: list[str],
        rows: list[list[Any]],
        *,
        title: str = "",
    ) -> None:
        """绘制 box-drawing 表格。"""
        t = Table(*headers, title=title or None, show_lines=False, show_header=bool(headers))
        # 默认所有列左对齐
        for _ in headers:
            t.add_column()
        for row in rows:
            t.add_row(*[str(c) for c in row])
        self.console.print(t)

    def status_block(self, items: dict[str, str], title: str = "") -> None:
        """两列 key-value 显示（无边框）。"""
        t = Table(
            show_header=False,
            box=None,
            title=title or None,
            padding=(0, 1),
        )
        t.add_column(style="accent", no_wrap=True)
        t.add_column()
        for k, v in items.items():
            t.add_row(str(k), str(v))
        self.console.print(t)

    # ---- autoc 专用 -----------------------------------------------------

    def print_result_table(self, title: str, rows: list[dict[str, Any]]) -> None:
        """展示 BSW 改参结果。

        :param title: 表格标题（典型为模块名 + "改参"）
        :param rows: 每行是一个 dict，列名由 dict 的 keys 决定
        """
        if not rows:
            self.hint(f"{title}（无数据）")
            return
        headers = list(rows[0].keys())
        body = [[str(row.get(h, "")) for h in headers] for row in rows]
        self.table(headers, body, title=title)

    def print_diff_callout(self, diff: str, *, title: str = "Changes") -> None:
        """统一 diff callout：绿 + 黄 - 三色，inline 渲染。

        行级语义（按 diff 文本逐行）：
        - ``+ ...`` → 绿色（added）
        - ``- ...`` → 红色（removed）
        - ``@@ ...`` → muted（hunk header）
        - 其他 → 普通
        """
        lines: list[str] = []
        for line in diff.splitlines():
            if line.startswith("+++") or line.startswith("---"):
                continue  # 文件头 skip
            if line.startswith("+"):
                lines.append(f"[success]{line}[/success]")
            elif line.startswith("-"):
                lines.append(f"[error]{line}[/error]")
            elif line.startswith("@@"):
                lines.append(f"[muted]{line}[/muted]")
            else:
                lines.append(line)
        body = "\n".join(lines) if lines else "（无变化）"
        self.console.print(Panel(body, title=f"[accent]{title}[/accent]", border_style="border"))


__all__ = [
    "AUTOC_THEME",
    "ReplSkin",
    "detect_no_color",
    "make_console",
]
