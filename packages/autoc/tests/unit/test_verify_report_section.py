"""Sprint 9.3 T9.3-γ — :mod:`claude_autosar.core.bsw.verify.report_section` 测试。

8 个 case 覆盖：

1. ``test_render_empty_issues_returns_placeholder`` — 空 issues → 占位行
2. ``test_render_single_error_issue_full_html`` — 单 ERROR 完整 HTML 结构
3. ``test_render_severity_sort_error_warning_info`` — severity 排序
4. ``test_render_with_xss_payload_escapes_html`` — XSS 防御
5. ``test_render_with_nonzero_returncode_marks_summary`` — returncode 标记
6. ``test_render_duck_typing_accepts_plain_object`` — duck-typing fallback
7. ``test_render_arxml_report_with_verify_inserts_section`` — arxml 嵌入
8. ``test_render_xdm_report_with_verify_inserts_section`` — xdm 嵌入
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from claude_autosar.core.bsw.verify.report_section import (
    render_verify_section_html,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "arxml"
MINIMAL_ARXML_FIXTURE = FIXTURES_DIR / "Com_Com.minimal.arxml"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def minimal_arxml_html() -> str:
    """最小 arxml fixture 渲染结果（module-scope）。"""
    from claude_autosar.core.bsw.inspector.arxml_report import (
        render_arxml_report,
    )

    return render_arxml_report(MINIMAL_ARXML_FIXTURE)


@pytest.fixture(scope="module")
def minimal_xdm_html() -> str:
    """最小 xdm fixture 渲染结果（module-scope）。"""
    from claude_autosar.core.bsw.inspector.xdm_report import (
        render_xdm_report,
    )
    import tempfile

    # XDM 没 fixture；动态写一个最小 DataModel2 树
    xdm_content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<root xmlns="http://www.tresos.de/_projects/DataModel2/16/root.xsd" '
        'xmlns:d="http://www.tresos.de/_projects/DataModel2/06/data.xsd">\n'
        '<d:lst name="CanConfigSet">\n'
        '<d:chc name="Can" type="AR-ELEMENT">\n'
        '<d:lst name="CanGeneral">\n'
        '<d:var name="CanDevErrorDetect" type="BOOLEAN" value="true"/>\n'
        '</d:lst>\n'
        '</d:chc>\n'
        '</d:lst>\n'
        '</root>\n'
    )
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".xdm", delete=False, encoding="utf-8"
    ) as f:
        f.write(xdm_content)
        xdm_path = Path(f.name)
    try:
        return render_xdm_report(xdm_path)
    finally:
        xdm_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 1. 空 issues → 占位行
# ---------------------------------------------------------------------------


def test_render_empty_issues_returns_placeholder() -> None:
    """空 issues 元组 + returncode=0 → 含 ``Verify section: 0 issues`` 占位。"""
    html = render_verify_section_html(())
    assert "<section" in html
    assert "verify-section" in html
    assert "<h2>Verify</h2>" in html
    assert "Verify section: 0 issues" in html
    assert "summary-box" in html
    assert 'verify-rc-zero' in html


# ---------------------------------------------------------------------------
# 2. 单 ERROR 完整 HTML
# ---------------------------------------------------------------------------


def test_render_single_error_issue_full_html() -> None:
    """单 ERROR issue → summary + table 单行；列顺序：Severity/Code/Module/Message/Location。"""
    issue = SimpleNamespace(
        severity="ERROR",
        code="E001",
        message="missing reference",
        module="Com",
        file="/path/to/file.c",
        line=42,
    )
    html = render_verify_section_html((issue,), returncode=2)
    assert "<table" in html
    # 列标题齐全
    assert "<th>Severity</th>" in html
    assert "<th>Code</th>" in html
    assert "<th>Module</th>" in html
    assert "<th>Message</th>" in html
    assert "<th>Location</th>" in html
    # 数据存在
    assert "ERROR" in html
    assert "E001" in html
    assert "Com" in html
    assert "missing reference" in html
    assert "/path/to/file.c" in html
    assert "42" in html
    # 非零 returncode 标红
    assert "verify-rc-nonzero" in html
    # counts
    assert "<strong>errors</strong>: 1" in html


# ---------------------------------------------------------------------------
# 3. severity 排序
# ---------------------------------------------------------------------------


def test_render_severity_sort_error_warning_info() -> None:
    """按 ERROR → WARNING → INFO 顺序排，同 severity 保持原顺序（stable）。"""
    issues = (
        SimpleNamespace(
            severity="INFO", code="I1", message="info first",
            module="A", file=None, line=None,
        ),
        SimpleNamespace(
            severity="WARNING", code="W1", message="warn first",
            module="B", file=None, line=None,
        ),
        SimpleNamespace(
            severity="ERROR", code="E1", message="err first",
            module="C", file=None, line=None,
        ),
        SimpleNamespace(
            severity="INFO", code="I2", message="info second",
            module="D", file=None, line=None,
        ),
        SimpleNamespace(
            severity="WARNING", code="W2", message="warn second",
            module="E", file=None, line=None,
        ),
        SimpleNamespace(
            severity="ERROR", code="E2", message="err second",
            module="F", file=None, line=None,
        ),
    )
    html = render_verify_section_html(issues, returncode=1)
    # 查找每个 message 在 HTML 中的出现位置
    pos = {
        msg: html.find(msg)
        for msg in (
            "info first", "warn first", "err first",
            "info second", "warn second", "err second",
        )
    }
    # 所有 message 必须存在
    for msg, p in pos.items():
        assert p >= 0, f"message '{msg}' not found"
    # ERROR 全部早于 WARNING；WARNING 全部早于 INFO
    err_max = max(pos["err first"], pos["err second"])
    warn_min = min(pos["warn first"], pos["warn second"])
    warn_max = max(pos["warn first"], pos["warn second"])
    info_min = min(pos["info first"], pos["info second"])
    assert err_max < warn_min
    assert warn_max < info_min
    # 同 severity 内保持原顺序
    assert pos["err first"] < pos["err second"]
    assert pos["warn first"] < pos["warn second"]
    assert pos["info first"] < pos["info second"]


# ---------------------------------------------------------------------------
# 4. XSS 防御
# ---------------------------------------------------------------------------


def test_render_with_xss_payload_escapes_html() -> None:
    """恶意 ``<script>alert(1)</script>`` message 渲染后不含 ``<script>`` 字符串。"""
    malicious = SimpleNamespace(
        severity="ERROR",
        code="<script>alert(1)</script>",
        message="<script>alert('xss')</script><img src=x onerror=alert(1)>",
        module="<b>evil</b>",
        file="<script>alert(2)</script>",
        line=None,
    )
    html = render_verify_section_html((malicious,), returncode=1)
    # 关键：没有 raw `<script>` 标签
    assert "<script>" not in html
    assert "</script>" not in html
    # 关键：没有 raw `<img>` 标签
    assert "<img " not in html
    # 关键：没有 raw `<b>` 标签
    assert "<b>evil</b>" not in html
    # escape 后的字符串存在
    assert "&lt;script&gt;" in html
    assert "&lt;b&gt;evil&lt;/b&gt;" in html
    # 严重度计数对
    assert "<strong>errors</strong>: 1" in html


# ---------------------------------------------------------------------------
# 5. returncode 标记
# ---------------------------------------------------------------------------


def test_render_with_nonzero_returncode_marks_summary() -> None:
    """returncode != 0 → summary box 加 ``verify-rc-nonzero`` class（红/黄视觉区分）。"""
    issue = SimpleNamespace(
        severity="INFO", code="I", message="m",
        module="M", file=None, line=None,
    )
    html_ok = render_verify_section_html((issue,), returncode=0)
    html_fail = render_verify_section_html((issue,), returncode=2)
    assert "verify-rc-zero" in html_ok
    assert "verify-rc-nonzero" not in html_ok
    assert "verify-rc-nonzero" in html_fail
    # empty + nonzero 也嵌入
    html_empty_fail = render_verify_section_html((), returncode=1)
    assert "verify-rc-nonzero" in html_empty_fail


# ---------------------------------------------------------------------------
# 6. duck-typing fallback
# ---------------------------------------------------------------------------


def test_render_duck_typing_accepts_plain_object() -> None:
    """非 :class:`TresosVerifyIssue` 但 duck-type（具有相同字段）也能渲染。"""
    issue = SimpleNamespace(
        severity="warning",  # 小写也接受（case-insensitive）
        code="W_DUCK",
        message="duck typing works",
        module="ModX",
        file="x.c",
        line=7,
    )
    html = render_verify_section_html((issue,), returncode=0)
    # severity 归一化到大写
    assert "WARNING" in html
    assert "W_DUCK" in html
    assert "duck typing works" in html
    assert "ModX" in html
    assert "x.c:7" in html
    # 不存在字段 → 降级为 INFO（不崩）
    partial = SimpleNamespace(severity="INFO", message="partial")
    html_partial = render_verify_section_html((partial,), returncode=0)
    assert "INFO" in html_partial
    assert "partial" in html_partial
    assert "—" in html_partial  # 无 file/line → location 显示 —


# ---------------------------------------------------------------------------
# 7. arxml 嵌入
# ---------------------------------------------------------------------------


def test_render_arxml_report_with_verify_inserts_section(
    self_request: Any = None,  # noqa: ARG001
) -> None:
    """``render_arxml_report_with_verify`` 把 verify section 插入到 ``</body>`` 之前。"""
    from claude_autosar.core.bsw.inspector.arxml_report import (
        render_arxml_report_with_verify,
    )

    issue = SimpleNamespace(
        severity="ERROR",
        code="E_INJECT",
        message="arxml embedded error",
        module="Com",
        file=None,
        line=None,
    )
    # 空 + rc=0 → 不嵌入（直接返 base）
    base_only = render_arxml_report_with_verify(MINIMAL_ARXML_FIXTURE)
    assert "verify-section" not in base_only
    # 注入 verify section
    html = render_arxml_report_with_verify(
        MINIMAL_ARXML_FIXTURE,
        verify_issues=(issue,),
        verify_returncode=1,
    )
    assert "<section" in html
    assert "verify-section" in html
    assert "arxml embedded error" in html
    # verify section 在 </body> 之前
    sec_pos = html.find("verify-section")
    body_close_pos = html.find("</body>")
    assert sec_pos < body_close_pos
    assert sec_pos > 0
    # 不破坏原有 ARXML 内容
    assert "ARXML Report" in html


# ---------------------------------------------------------------------------
# 8. xdm 嵌入
# ---------------------------------------------------------------------------


def test_render_xdm_report_with_verify_inserts_section(
    tmp_path: Path,
) -> None:
    """``render_xdm_report_with_verify`` 把 verify section 插入到 ``</body>`` 之前。"""
    from claude_autosar.core.bsw.inspector.xdm_report import (
        render_xdm_report_with_verify,
    )

    # 动态写一个最小 DataModel2 树到 tmp_path
    xdm_path = tmp_path / "minimal.xdm"
    xdm_path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<root xmlns="http://www.tresos.de/_projects/DataModel2/16/root.xsd" '
        'xmlns:d="http://www.tresos.de/_projects/DataModel2/06/data.xsd">\n'
        '<d:lst name="CanConfigSet">\n'
        '<d:chc name="Can" type="AR-ELEMENT">\n'
        '<d:lst name="CanGeneral">\n'
        '<d:var name="CanDevErrorDetect" type="BOOLEAN" value="true"/>\n'
        '</d:lst>\n'
        '</d:chc>\n'
        '</d:lst>\n'
        '</root>\n',
        encoding="utf-8",
    )
    issue = SimpleNamespace(
        severity="WARNING",
        code="W_XDM",
        message="xdm embedded warning",
        module="Can",
        file=None,
        line=None,
    )
    # 注入 verify section
    html = render_xdm_report_with_verify(
        xdm_path,
        verify_issues=(issue,),
        verify_returncode=0,
    )
    assert "<section" in html
    assert "verify-section" in html
    assert "xdm embedded warning" in html
    # verify section 在 </body> 之前
    sec_pos = html.find("verify-section")
    body_close_pos = html.find("</body>")
    assert sec_pos < body_close_pos
    assert sec_pos > 0
    # 不破坏原有 XDM 内容
    assert "DataModel2" in html
    # 空 + rc=0 → 不嵌入
    base_only = render_xdm_report_with_verify(xdm_path)
    assert "verify-section" not in base_only
