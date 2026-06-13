"""Sprint 9.1 — BSW 配置 inspector（单文件 → 一页式 HTML 报告）。

子模块：

- :mod:`arxml_report` — AUTOSAR r4.x ARXML 报告（Sprint 9.1 T9.1.2）
- :mod:`xdm_report` — EB tresos DataModel2 报告（Sprint 9.1 T9.1.3）

设计原则（plan §2.1）：

  - **不抽象 InstanceTree** — 每个格式独立解析 / 序列化 / 渲染
  - **inspector 不引入新的 ECUC walker** — 复用 :mod:`core.bsw.arxml_io`
    低层 helpers（xpath + get_child_text 等）
  - **复用 :mod:`utils.html_utils`**（T9.1.1）— inline CSS + XSS escape +
    URL 白名单 + 三色 callout

公共 API：

  - ``render_arxml_report(path) -> str``
  - ``export_arxml_report(path, output=None) -> Path``
  - ``render_xdm_report(path) -> str``
  - ``export_xdm_report(path, output=None) -> Path``
"""

from __future__ import annotations

from claude_autosar.core.bsw.inspector.arxml_report import (
    export_arxml_report,
    render_arxml_report,
)
from claude_autosar.core.bsw.inspector.xdm_report import (
    export_xdm_report,
    render_xdm_report,
)

__all__ = [
    "render_arxml_report",
    "export_arxml_report",
    "render_xdm_report",
    "export_xdm_report",
]
