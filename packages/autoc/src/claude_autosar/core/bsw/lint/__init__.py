"""BSW 配置 lint 框架 — Sprint 9.4 — T9.4-α。

扫配置反模式（10 条规则覆盖 COM / CanIf / EcuM / Nm / Gen / DEM 模块），
产结构化 violation list。设计要点（plan smooth-spinning-dolphin §4.2）：

* ``LintSeverity`` — severity 三档常量（frozen dataclass + ClassVar）
* ``LintViolation`` — 单条违规（frozen dataclass，含 location / module / suggestion）
* ``LintRule`` — Protocol 接口，rule 实现 ``check(extracted)`` 即可
* 不与具体规则耦合 — runner 接受任意 LintRule tuple

公共 API：

- :func:`LintSeverity` 常量 — ``ERROR`` / ``WARNING`` / ``INFO``
- :class:`LintViolation` — frozen dataclass
- :class:`LintRule` — Protocol
- :func:`lint_all` — 一站式入口（按 suffix 选 arxml / xdm extractor + 全部规则）

详细 runner / extract / 规则文件：

- :mod:`claude_autosar.core.bsw.lint.runner` — LintRunner + LintSummary
- :mod:`claude_autosar.core.bsw.lint.extract` — ArxmlLintData / XdmLintData
- :mod:`claude_autosar.core.bsw.lint.rules` — 10 条规则注册
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Protocol

from claude_autosar.core.bsw.lint.extract import (
    ArxmlLintData,
    XdmLintData,
    extract_arxml_for_lint,
    extract_xdm_for_lint,
)

__all__ = [
    "LintSeverity",
    "LintViolation",
    "LintRule",
    "LintRunner",
    "LintSummary",
    "ArxmlLintData",
    "XdmLintData",
    "extract_arxml_for_lint",
    "extract_xdm_for_lint",
    "lint_file",
    "lint_all",
]


# ---------------------------------------------------------------------------
# 严重度常量（frozen dataclass + ClassVar — 防止误改）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LintSeverity:
    """Lint 违规严重度常量（3 档）。

    使用 ClassVar 而非 ClassVar[str] 是因为冻结 dataclass 上 ClassVar
    字段不会被 dataclass 机制当成实例字段，方便外部直接读
    ``LintSeverity.ERROR``，又不会污染 ``__init__``。
    """

    ERROR: ClassVar[str] = "error"
    WARNING: ClassVar[str] = "warning"
    INFO: ClassVar[str] = "info"


# ---------------------------------------------------------------------------
# 违规表示
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LintViolation:
    """单条 lint 违规记录（frozen — 不允许修改）。

    :param rule_id: 规则 ID（e.g. ``"COM-AP-001"``）
    :param severity: 严重度（``LintSeverity.ERROR`` / ``WARNING`` / ``INFO``）
    :param message: 一句话描述（人读）
    :param location: 违规位置（IPdu 名 / Signal 名 / leaf path）
    :param module: 涉及的 BSW 模块名（Com / Can / EcuM ...）
    :param suggestion: 修复建议（可为 None）
    """

    rule_id: str
    severity: str
    message: str
    location: str
    module: str
    suggestion: str | None = None


# ---------------------------------------------------------------------------
# 规则接口（Protocol — duck typing）
# ---------------------------------------------------------------------------


class LintRule(Protocol):
    """单条 lint 规则的 Protocol 接口。

    实现要求：
      - ``rule_id`` ClassVar[str]
      - ``severity_default`` ClassVar[str]
      - ``applies_to`` ClassVar[str] — 命名空间 tag（``"arxml"`` / ``"xdm"`` /
        ``"both"``）；缺省 ``"both"``（向后兼容）。``lint_file`` 会按文件
        suffix 过滤，避免 arxml-only 规则被喂 XDM 数据而抛
        ``AttributeError``。
      - ``check(extracted)`` 返回 ``Iterable[LintViolation]``
    """

    rule_id: str
    severity_default: str
    applies_to: str

    def check(self, extracted: Any) -> Iterable[LintViolation]: ...


# ---------------------------------------------------------------------------
# Runner / Summary — 重导出避免上层多 1 个 import
# ---------------------------------------------------------------------------


# 采用延迟 import 避免循环（rules → runner → __init__ 的反向引用）
# 注：lint_file / lint_all 在下面调用 runner 时才真触发；这里只做符号
# 可用性 + 类型注解兼容。


def __getattr__(name: str) -> Any:  # PEP 562
    """延迟 import — 避免 lint.runner 强依赖 lint.__init__。"""
    if name in ("LintRunner", "LintSummary"):
        from claude_autosar.core.bsw.lint.runner import LintRunner, LintSummary

        if name == "LintRunner":
            return LintRunner
        return LintSummary
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ---------------------------------------------------------------------------
# 一站式入口
# ---------------------------------------------------------------------------


def lint_file(
    path: Path,
    *,
    runner: Any | None = None,
) -> tuple[LintViolation, ...]:
    """按文件 suffix 路由到 arxml / xdm extractor，跑全部规则。

    :param path: ``.arxml`` 或 ``.xdm`` 文件路径
    :param runner: 自定义 LintRunner（默认 = ``LintRunner(ALL_RULES)``）
    :return: 违规 tuple（可能为空）
    :raises FileNotFoundError: 文件不存在
    """
    from claude_autosar.core.bsw.lint.runner import LintRunner

    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"file not found: {p}")

    suffix = p.suffix.lower()
    if suffix == ".arxml":
        extracted: Any = extract_arxml_for_lint(p)
        ns = "arxml"
    elif suffix in (".xdm", ".datamodel"):
        extracted = extract_xdm_for_lint(p)
        ns = "xdm"
    else:
        # 不支持格式 → 0 violation（不误报）
        return ()

    if runner is None:
        from claude_autosar.core.bsw.lint.rules import rules_for_namespace

        runner = LintRunner(rules_for_namespace(ns))

    return runner.run(extracted)


def lint_all(
    paths: Iterable[Path],
    *,
    runner: Any | None = None,
) -> tuple[LintViolation, ...]:
    """批量 lint — 把多个文件的违规合并成一个 tuple（按文件顺序）。

    :param paths: 文件路径 iterable
    :param runner: 透传到 :func:`lint_file`
    :return: 全部 violation tuple
    """
    out: list[LintViolation] = []
    for p in paths:
        out.extend(lint_file(p, runner=runner))
    return tuple(out)
