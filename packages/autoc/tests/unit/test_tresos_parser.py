"""Sprint 9.3 T9.3-α — ``verify.tresos_parser`` 单元测试。

10 个 case：

1. parse_empty_stdout → issues 为空
2. parse_simple_error_line → 1 issue severity=ERROR
3. parse_warning_with_code → code 字段提取
4. parse_with_file_and_line → file + line 提取
5. parse_mixed_severity → ERROR + WARNING + INFO 混合
6. parse_module_default_propagated → 所有 issue 都有 module
7. parse_module_extracted_from_stdout → stdout 含 "module XXX" 时提取
8. parse_stderr_appended_on_nonzero_returncode → returncode != 0 时 stderr 整段附一条 ERROR
9. parse_unparseable_line_falls_back_to_info → 不匹配的行 → INFO
10. parse_frozen_report_is_immutable → frozen 校验

按 plan §T9.3-α 与 §Verification 第 3 项硬指标。
"""

from __future__ import annotations

import dataclasses

import pytest

from claude_autosar.core.bsw.verify import (
    TresosParserError,
    TresosVerifyIssue,
    parse_tresos_verify_stdout,
)


# =============================================================================
# 1. parse_empty_stdout → issues 为空
# =============================================================================


def test_parse_empty_stdout_returns_empty_issues() -> None:
    """空 stdout → 空 issues 元组。"""
    report = parse_tresos_verify_stdout("", returncode=0)
    assert report.issues == ()
    assert report.has_errors is False
    assert report.has_warnings is False
    assert report.returncode == 0
    assert report.duration_ms == 0
    assert report.raw_stdout == ""
    assert report.raw_stderr == ""


def test_parse_whitespace_only_stdout_returns_empty_issues() -> None:
    """纯空白 / 空行 → 空 issues（空行跳过）。"""
    report = parse_tresos_verify_stdout("\n   \n\t\n", returncode=0)
    assert report.issues == ()


# =============================================================================
# 2. parse_simple_error_line → 1 issue severity=ERROR
# =============================================================================


def test_parse_simple_error_line_yields_one_error_issue() -> None:
    """单行 ``ERROR: ...`` → 1 issue，severity=ERROR。"""
    report = parse_tresos_verify_stdout(
        "ERROR: validation failed for module",
        returncode=1,
    )
    assert len(report.issues) == 1
    issue = report.issues[0]
    assert issue.severity == "ERROR"
    assert "validation failed" in issue.message
    assert report.has_errors is True
    assert report.has_warnings is False


def test_parse_error_line_case_insensitive() -> None:
    """行首 severity 大小写不敏感 → 归一化大写。"""
    report = parse_tresos_verify_stdout(
        "error: something went wrong",
        returncode=1,
    )
    assert report.issues[0].severity == "ERROR"


# =============================================================================
# 3. parse_warning_with_code → code 字段提取
# =============================================================================


def test_parse_warning_with_code_via_colon() -> None:
    """``code: <CODE>`` → code 字段提取。"""
    report = parse_tresos_verify_stdout(
        "WARNING: deprecated config key [code: DEP001] used here",
        returncode=0,
    )
    issue = report.issues[0]
    assert issue.severity == "WARNING"
    assert issue.code == "DEP001"
    assert report.has_warnings is True
    assert report.has_errors is False


def test_parse_error_with_code_via_brackets() -> None:
    """``[CODE]`` → code 字段提取（colon 优先，没有 colon 时退到 bracket）。"""
    report = parse_tresos_verify_stdout(
        "ERROR [E1001] missing required parameter",
        returncode=2,
    )
    issue = report.issues[0]
    assert issue.severity == "ERROR"
    assert issue.code == "E1001"
    assert "missing required parameter" in issue.message


# =============================================================================
# 4. parse_with_file_and_line → file + line 提取
# =============================================================================


def test_parse_with_file_via_colon() -> None:
    """``file: <path>`` → file 字段提取。"""
    report = parse_tresos_verify_stdout(
        "ERROR: bad reference file: Config/SomeModule.xdm",
        returncode=1,
    )
    issue = report.issues[0]
    assert issue.severity == "ERROR"
    assert issue.file == "Config/SomeModule.xdm"
    assert issue.line is None


def test_parse_with_file_and_line_via_at_syntax() -> None:
    """``at <path>:<line>`` → file + line 字段提取。"""
    report = parse_tresos_verify_stdout(
        "ERROR: syntax error at SomeModule.xdm:42",
        returncode=1,
    )
    issue = report.issues[0]
    assert issue.severity == "ERROR"
    assert issue.file == "SomeModule.xdm"
    assert issue.line == 42


# =============================================================================
# 5. parse_mixed_severity → ERROR + WARNING + INFO 混合
# =============================================================================


def test_parse_mixed_severity_lines() -> None:
    """混合 ERROR + WARNING + INFO → 三个 issue，property 正确反映。"""
    stdout = (
        "ERROR: missing required parameter ComMChannelLength\n"
        "WARNING: deprecated symbol [code: W001] used\n"
        "INFO: validation completed in 123ms\n"
    )
    report = parse_tresos_verify_stdout(stdout, returncode=1)
    severities = [i.severity for i in report.issues]
    assert severities == ["ERROR", "WARNING", "INFO"]
    assert report.has_errors is True
    assert report.has_warnings is True
    assert len(report.issues) == 3


# =============================================================================
# 6. parse_module_default_propagated → 所有 issue 都有 module
# =============================================================================


def test_parse_module_default_propagated_to_all_issues() -> None:
    """调用方传入 ``module`` → 强制绑定到所有解析出的 issue。"""
    stdout = (
        "ERROR: missing required parameter\n"
        "WARNING: deprecated symbol\n"
        "INFO: validation completed\n"
    )
    report = parse_tresos_verify_stdout(
        stdout, returncode=1, module="Com"
    )
    assert len(report.issues) == 3
    for issue in report.issues:
        assert issue.module == "Com"


def test_parse_module_default_overrides_stdout_module_marker() -> None:
    """``forced_module`` 非空时优先，覆盖 stdout ``module <NAME>``。"""
    stdout = "ERROR: missing required parameter module Foo"
    report = parse_tresos_verify_stdout(
        stdout, returncode=1, module="Com"
    )
    assert report.issues[0].module == "Com"


# =============================================================================
# 7. parse_module_extracted_from_stdout → stdout 含 "module XXX" 时提取
# =============================================================================


def test_parse_module_extracted_from_stdout_when_not_forced() -> None:
    """未传 ``module``、stdout 含 ``module XXX`` → 从该行提取。"""
    stdout = "ERROR: validation failed for module Com"
    report = parse_tresos_verify_stdout(stdout, returncode=1)
    assert report.issues[0].module == "Com"


def test_parse_module_absent_yields_empty_string() -> None:
    """未传 ``module``、stdout 也无 ``module`` 标记 → module == ""。"""
    stdout = "ERROR: something bad happened"
    report = parse_tresos_verify_stdout(stdout, returncode=1)
    assert report.issues[0].module == ""


# =============================================================================
# 8. parse_stderr_appended_on_nonzero_returncode → returncode != 0 时 stderr 整段附一条 ERROR
# =============================================================================


def test_parse_stderr_appended_on_nonzero_returncode() -> None:
    """returncode != 0 且 stderr 非空 → 附加一条 ERROR issue。"""
    report = parse_tresos_verify_stdout(
        "INFO: starting validation\n",
        stderr="tresos_cmd crashed: OOM",
        returncode=137,
    )
    # 1 issue from stdout (INFO) + 1 issue from stderr (ERROR) = 2
    assert len(report.issues) == 2
    assert report.issues[0].severity == "INFO"
    assert report.issues[1].severity == "ERROR"
    assert "137" in report.issues[1].message
    assert "OOM" in report.issues[1].message
    assert report.has_errors is True


def test_parse_stderr_ignored_on_zero_returncode() -> None:
    """returncode == 0 → stderr 即使非空也不附加 issue。"""
    report = parse_tresos_verify_stdout(
        "",
        stderr="some debug noise",
        returncode=0,
    )
    assert report.issues == ()
    assert report.has_errors is False


def test_parse_stderr_empty_on_nonzero_returncode() -> None:
    """returncode != 0 但 stderr 为空 → 不附加 issue。"""
    report = parse_tresos_verify_stdout(
        "ERROR: bad config\n",
        stderr="",
        returncode=1,
    )
    assert len(report.issues) == 1
    assert report.issues[0].severity == "ERROR"


# =============================================================================
# 9. parse_unparseable_line_falls_back_to_info → 不匹配的行 → INFO
# =============================================================================


def test_parse_unparseable_line_falls_back_to_info() -> None:
    """无 severity 关键字的行 → INFO，整行作 message。"""
    stdout = "some unstructured log line"
    report = parse_tresos_verify_stdout(stdout, returncode=0)
    assert len(report.issues) == 1
    issue = report.issues[0]
    assert issue.severity == "INFO"
    assert issue.message == "some unstructured log line"


# =============================================================================
# 10. parse_frozen_report_is_immutable → frozen 校验
# =============================================================================


def test_parse_frozen_report_is_immutable() -> None:
    """``TresosVerifyReport`` frozen → 修改字段抛 ``dataclasses.FrozenInstanceError``。"""
    report = parse_tresos_verify_stdout("ERROR: x\n", returncode=1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.returncode = 99  # type: ignore[misc]


def test_parse_frozen_issue_is_immutable() -> None:
    """``TresosVerifyIssue`` frozen → 修改字段抛 ``FrozenInstanceError``。"""
    report = parse_tresos_verify_stdout("ERROR: x\n", returncode=1)
    issue = report.issues[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        issue.severity = "INFO"  # type: ignore[assignment]


def test_parse_issues_field_is_tuple_not_list() -> None:
    """``issues`` 字段是 tuple（frozen 不可变 + 顺序稳定）。"""
    report = parse_tresos_verify_stdout(
        "ERROR: a\nWARNING: b\nINFO: c\n", returncode=1
    )
    assert isinstance(report.issues, tuple)
    # tuple 不支持 append
    with pytest.raises(AttributeError):
        report.issues.append(  # type: ignore[attr-defined]
            TresosVerifyIssue(
                severity="INFO",
                code="",
                message="x",
                module="",
                file=None,
                line=None,
            )
        )


# =============================================================================
# 边界 case：类型校验
# =============================================================================


def test_parse_non_string_stdout_raises_tresos_parser_error() -> None:
    """``stdout`` 非字符串 → ``TresosParserError``。"""
    with pytest.raises(TresosParserError) as excinfo:
        parse_tresos_verify_stdout(b"bytes not allowed")  # type: ignore[arg-type]
    assert "stdout" in str(excinfo.value).lower()


def test_parse_non_string_stderr_raises_tresos_parser_error() -> None:
    """``stderr`` 非字符串 → ``TresosParserError``。"""
    with pytest.raises(TresosParserError):
        parse_tresos_verify_stdout("", stderr=123)  # type: ignore[arg-type]


def test_parse_negative_duration_falls_back_to_zero() -> None:
    """``duration_ms`` 负数 → 兜底 ``0``。"""
    report = parse_tresos_verify_stdout("", duration_ms=-5)
    assert report.duration_ms == 0


def test_parse_non_int_duration_falls_back_to_zero() -> None:
    """``duration_ms`` 非 int → 兜底 ``0``。"""
    report = parse_tresos_verify_stdout("", duration_ms="not a number")  # type: ignore[arg-type]
    assert report.duration_ms == 0


# =============================================================================
# 边界 case：report 元数据透传
# =============================================================================


def test_report_preserves_raw_stdout_and_stderr() -> None:
    """``raw_stdout`` / ``raw_stderr`` 保留原始字符串便于诊断。"""
    raw_stdout = "ERROR: x\nINFO: y\n"
    raw_stderr = "warning noise\n"
    report = parse_tresos_verify_stdout(
        raw_stdout, stderr=raw_stderr, returncode=0
    )
    assert report.raw_stdout == raw_stdout
    assert report.raw_stderr == raw_stderr


def test_report_with_only_warnings_has_no_errors() -> None:
    """只有 WARNING → ``has_errors`` False / ``has_warnings`` True。"""
    report = parse_tresos_verify_stdout(
        "WARNING: minor issue\n", returncode=0
    )
    assert report.has_errors is False
    assert report.has_warnings is True
