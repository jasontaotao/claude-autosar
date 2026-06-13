"""``verify`` — EB tresos ``--validate`` 输出结构化解析器。

Sprint 9.3 T9.3-α：

* ``TresosVerifyIssue`` — 单条问题（severity / code / message / module / file / line）
* ``TresosVerifyReport`` — 完整报告（issues + raw stdout/stderr + returncode + duration_ms）
* ``parse_tresos_verify_stdout`` — 把 tresos_cmd stdout + stderr 解析成 ``TresosVerifyReport``

下游消费方：

* T9.3-β ``mcp_server.bsw_verify`` 工具（拼装 dispatch）
* T9.3-γ ``inspector`` 报告嵌入（issue → Markdown）

设计取舍：EB tresos 实际 stdout 形态用户没提供样本，用 fixture 模拟；
真实工程验证推 Sprint 9.5。本模块**不**消费 ``CompletedProcess`` 类型，
只消费字符串 + returncode，方便单元测试覆盖。
"""

from claude_autosar.core.bsw.verify.tresos_parser import (
    TresosParserError,
    TresosVerifyIssue,
    TresosVerifyReport,
    parse_tresos_verify_stdout,
)

__all__ = [
    "TresosParserError",
    "TresosVerifyIssue",
    "TresosVerifyReport",
    "parse_tresos_verify_stdout",
]
