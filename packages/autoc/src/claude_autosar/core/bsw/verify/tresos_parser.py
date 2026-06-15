"""``tresos_parser`` — EB tresos ``--validate`` stdout/stderr 结构化解析器。

Sprint 9.3 T9.3-α（独立切片，只动 verify 包内）。设计要点：

* ``TresosVerifyIssue`` frozen dataclass：单条 issue
* ``TresosVerifyReport`` frozen dataclass：完整报告 + ``has_errors``/``has_warnings`` property
* ``parse_tresos_verify_stdout`` 纯函数：保守 fallback — 解析不出就当 INFO 整段记一条
* ``TresosParserError`` ValueError 子类：输入为非字符串时抛出

解析规则（**保守 fallback** — 不强行猜）：

1. 逐行扫描 stdout / stderr
2. 行首匹配 ``ERROR`` / ``WARNING`` / ``INFO``（不区分大小写）→ severity
3. 行内 ``code: <CODE>`` 或 ``[<CODE>]`` → code
4. 行内 ``file: <path>`` 或 ``at <path>:<line>`` → file + line
5. module 来源（按优先级）：
   a. 调用方显式传入 ``module`` 参数 → 强制绑定到所有 issue
   b. stdout 行内 ``module <NAME>`` → 从该行提取
   c. 都没有 → 留空字符串 ``""``
6. stderr 整段当作一条 ERROR 附加（仅当 ``returncode != 0``）
7. 不匹配规则的 stdout 行 → 当 INFO issue，整行作 message

EB tresos 实际 stdout 形态用户没提供样本（plan §0.2.1 提到），用 fixture
模拟；真实工程验证推 Sprint 9.5。本模块**不**消费 ``CompletedProcess`` 类型，
只消费字符串 + returncode，方便单元测试覆盖。
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Final, Literal

__all__ = [
    "TresosParserError",
    "TresosVerifyIssue",
    "TresosVerifyReport",
    "parse_tresos_verify_stdout",
]


Severity = Literal["ERROR", "WARNING", "INFO"]


# =============================================================================
# 错误类型
# =============================================================================


class TresosParserError(ValueError):
    """tresos verify stdout 解析失败（输入为非字符串 / 字段类型错误）。"""


# =============================================================================
# 数据结构（frozen dataclass — 不可变）
# =============================================================================


@dataclass(frozen=True)
class TresosVerifyIssue:
    """单条 tresos verify issue。

    字段：
    * ``severity``: ``"ERROR"`` / ``"WARNING"`` / ``"INFO"``（大写归一化）
    * ``code``: EB tresos 错误码（从 stdout 提取）；无 → 空字符串
    * ``message``: 错误消息（一行）
    * ``module``: 涉及模块名；从调用方 ``module`` 参数或 stdout 提取；无 → 空字符串
    * ``file``: 涉及文件路径（可空）；无 → ``None``
    * ``line``: 行号（可空）；无 → ``None``
    """

    severity: Severity
    code: str
    message: str
    module: str
    file: str | None
    line: int | None


@dataclass(frozen=True)
class TresosVerifyReport:
    """tresos verify 完整报告。

    字段：
    * ``issues``: issue 元组（frozen 不可变；顺序 = 解析顺序）
    * ``returncode``: tresos_cmd returncode
    * ``duration_ms``: 调用耗时（毫秒）；调用方未提供 → ``0``
    * ``raw_stdout``: 原始 stdout（保留用于诊断）
    * ``raw_stderr``: 原始 stderr（保留用于诊断）

    property：
    * ``has_errors``: 任意 issue.severity == "ERROR"
    * ``has_warnings``: 任意 issue.severity == "WARNING"
    """

    issues: tuple[TresosVerifyIssue, ...]
    returncode: int
    duration_ms: int
    raw_stdout: str
    raw_stderr: str

    @property
    def has_errors(self) -> bool:
        """任意 issue.severity == "ERROR" → True。"""
        return any(i.severity == "ERROR" for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        """任意 issue.severity == "WARNING" → True。"""
        return any(i.severity == "WARNING" for i in self.issues)


# =============================================================================
# 解析逻辑（正则）
# =============================================================================

# 行首 severity 关键字（不区分大小写；后接冒号、空格或行尾）
_RE_SEVERITY: Final[re.Pattern[str]] = re.compile(
    r"^\s*(ERROR|WARNING|INFO)\s*[:\-]?\s*(.*)$",
    re.IGNORECASE,
)

# 行内 ``code: <CODE>`` 或 ``[<CODE>]``
_RE_CODE_COLON: Final[re.Pattern[str]] = re.compile(
    r"\bcode\s*[:=]\s*([A-Za-z0-9_\-]+)",
    re.IGNORECASE,
)
_RE_CODE_BRACKET: Final[re.Pattern[str]] = re.compile(
    r"\[([A-Za-z0-9_\-]{2,})\]",
)

# 行内 ``file: <path>`` 或 ``at <path>:<line>``
_RE_FILE_COLON: Final[re.Pattern[str]] = re.compile(
    r"\bfile\s*[:=]\s*(\S+)",
    re.IGNORECASE,
)
_RE_AT_PATH_LINE: Final[re.Pattern[str]] = re.compile(
    r"\bat\s+(\S+?):(\d+)\b",
)

# 行内 ``module <NAME>``（在 severity 后）
_RE_MODULE: Final[re.Pattern[str]] = re.compile(
    r"\bmodule\s+([A-Za-z0-9_]+)",
    re.IGNORECASE,
)


# =============================================================================
# 公共入口
# =============================================================================


def parse_tresos_verify_stdout(
    stdout: str,
    stderr: str = "",
    *,
    returncode: int = 0,
    duration_ms: int = 0,
    module: str | None = None,
) -> TresosVerifyReport:
    """解析 EB tresos verify stdout + stderr。

    Parameters
    ----------
    stdout:
        tresos_cmd stdout 字符串（必填；非字符串 → ``TresosParserError``）。
    stderr:
        tresos_cmd stderr 字符串；空 → 不附加 stderr issue。
    returncode:
        tresos_cmd returncode（默认 ``0``）；非 ``0`` 时整段 stderr 附加一条
        ``ERROR`` issue。
    duration_ms:
        调用耗时（毫秒，默认 ``0`` 表示未提供）；负数 → ``0``。
    module:
        CLI ``--module`` 参数；非空 → 强制绑定到所有解析出的 issue。

    Returns
    -------
    TresosVerifyReport:
        issues 元组（解析顺序）+ returncode + duration_ms + raw stdout/stderr。

    Raises
    ------
    TresosParserError:
        ``stdout`` / ``stderr`` 不是字符串。
    """
    if not isinstance(stdout, str):
        raise TresosParserError(f"stdout must be str, got {type(stdout).__name__}")
    if not isinstance(stderr, str):
        raise TresosParserError(f"stderr must be str, got {type(stderr).__name__}")

    # duration_ms 兜底：负数 / 非 int 视为未提供
    if not isinstance(duration_ms, int) or duration_ms < 0:
        duration_ms = 0

    forced_module = (module or "").strip()

    issues: list[TresosVerifyIssue] = []
    for raw_line in stdout.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            # 空行跳过
            continue
        issues.append(_parse_line(line, forced_module))

    # stderr 整段附加一条 ERROR（仅 returncode != 0）
    if returncode != 0 and stderr.strip():
        issues.append(
            TresosVerifyIssue(
                severity="ERROR",
                code="",
                message=f"tresos_cmd exit {returncode}: {stderr.strip()}",
                module=forced_module,
                file=None,
                line=None,
            )
        )

    return TresosVerifyReport(
        issues=tuple(issues),
        returncode=returncode,
        duration_ms=duration_ms,
        raw_stdout=stdout,
        raw_stderr=stderr,
    )


# =============================================================================
# 内部辅助
# =============================================================================


def _parse_line(line: str, forced_module: str) -> TresosVerifyIssue:
    """解析单行 stdout → ``TresosVerifyIssue``。

    规则（保守 fallback）：
    1. 行首 ``ERROR``/``WARNING``/``INFO`` → severity（找不到 → INFO）
    2. code → ``code:`` 或 ``[CODE]``；前者优先
    3. file/line → ``file:`` 或 ``at <path>:<line>``；前者优先
    4. module → ``forced_module``（非空）or stdout ``module <NAME>``；都没有 → ``""``
    5. message → severity 后的剩余文本（去 code/file/module 标记）
    """
    severity: Severity = "INFO"
    message = line

    m_sev = _RE_SEVERITY.match(line)
    if m_sev is not None:
        sev_raw = m_sev.group(1).upper()
        if sev_raw in ("ERROR", "WARNING", "INFO"):
            severity = sev_raw  # type: ignore[assignment]
        message = m_sev.group(2).strip()

    # code：code: 优先，[] 次之
    code = ""
    m_code = _RE_CODE_COLON.search(line)
    if m_code is not None:
        code = m_code.group(1)
    else:
        m_bracket = _RE_CODE_BRACKET.search(line)
        if m_bracket is not None:
            code = m_bracket.group(1)

    # file / line
    file: str | None = None
    line_no: int | None = None
    m_file = _RE_FILE_COLON.search(line)
    if m_file is not None:
        file = m_file.group(1).rstrip(",;")
    else:
        m_at = _RE_AT_PATH_LINE.search(line)
        if m_at is not None:
            file = m_at.group(1)
            try:
                line_no = int(m_at.group(2))
            except ValueError:
                line_no = None

    # module：forced > stdout > ""
    module_name = forced_module
    if not module_name:
        m_mod = _RE_MODULE.search(line)
        if m_mod is not None:
            module_name = m_mod.group(1)

    # message 兜底：全部规则都没识别 → 整行
    if not message:
        message = line

    return TresosVerifyIssue(
        severity=severity,
        code=code,
        message=message,
        module=module_name,
        file=file,
        line=line_no,
    )
