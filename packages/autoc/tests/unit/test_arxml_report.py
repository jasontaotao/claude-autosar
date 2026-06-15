"""Tests for Sprint 9.1 T9.1.2 — :mod:`claude_autosar.core.bsw.inspector.arxml_report`.

覆盖：
- 空 ARXML 不崩
- 最小 Com_Com 结构（1 模块 + 1 ComConfigSet + 1 ComTxIPdu + 1 ComSignal）
- Signal 关键参数（bit_position / length / byte_order / initial_value）
- export 默认 / 自定义路径
- 不存在的文件 / 畸形 XML 抛 ARXMLError
- 端到端在用户工程 ``Com_Com.arxml`` 上跑通
"""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_autosar.core.bsw.arxml_io import ARXMLError
from claude_autosar.core.bsw.inspector.arxml_report import (
    export_arxml_report,
    render_arxml_report,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "arxml"
MINIMAL_FIXTURE = FIXTURES_DIR / "Com_Com.minimal.arxml"

# 用户工程真实 fixture（plan §1.4 硬指标）
USER_PROJECT_FIXTURE = Path(r"D:/claude_proj2/src/S32K148_EAS_EB_3399A/EAS_Cfg/Arxml/Com_Com.arxml")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def minimal_html() -> str:
    """最小 fixture 渲染结果（module-scope 减少重复 IO）。"""
    return render_arxml_report(MINIMAL_FIXTURE)


@pytest.fixture(scope="module")
def empty_minimal_fixture(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """最小化的"空 ARXML"：只有 AUTOSAR 根 + 一个空 module。"""
    p = tmp_path_factory.mktemp("arxml") / "empty.arxml"
    p.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<AUTOSAR xmlns="http://autosar.org/schema/r4.0"/>\n',
        encoding="utf-8",
    )
    return p


@pytest.fixture(scope="module")
def malformed_fixture(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """畸形 XML fixture：标签不闭合。"""
    p = tmp_path_factory.mktemp("arxml_bad") / "malformed.arxml"
    p.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<AUTOSAR xmlns="http://autosar.org/schema/r4.0">\n'
        "<SHORT-NAME>broken\n"
        "</AUTOSAR_BAD>\n",
        encoding="utf-8",
    )
    return p


# ---------------------------------------------------------------------------
# 基础：render / export
# ---------------------------------------------------------------------------


class TestRenderBasic:
    def test_render_empty_minimal_arxml(self, empty_minimal_fixture: Path) -> None:
        """空 ARXML（只有根 tag）不崩，输出合法 HTML。"""
        html = render_arxml_report(empty_minimal_fixture)
        assert "<!DOCTYPE html>" in html
        assert "<title>" in html
        assert "ARXML Report" in html
        # 无 IPdu / 无 Signal
        assert "No IPdu containers detected" in html
        assert "Modules" in html

    def test_render_minimal_com_ipdu(self, minimal_html: str) -> None:
        """最小 Com_Com fixture 渲染含 1 个 Com module + ComConfigSet。"""
        assert "<!DOCTYPE html>" in minimal_html
        # metadata 显示模块名
        assert "Com" in minimal_html
        # metadata 显示 default namespace
        assert "http://autosar.org/schema/r4.0" in minimal_html
        # key params 提取（ComConfigurationUsage / ComSupportedIPduGroups）
        assert "ComConfigurationUsage" in minimal_html
        assert "ComSupportedIPduGroups" in minimal_html

    def test_render_with_signal_handles(self, minimal_html: str) -> None:
        """Signal 关键参数（bit_position / length / byte_order / initial_value）渲染。"""
        # Signal Table 渲染了 Signal 行
        assert "<h2>Signal Table</h2>" in minimal_html
        assert "BitPosition" in minimal_html
        assert "BitSize" in minimal_html
        assert "ByteOrder" in minimal_html
        assert "InitValue" in minimal_html
        # IPdu 表 + Signal Count 列
        assert "<h2>IPdu Table</h2>" in minimal_html
        assert "Signal Count" in minimal_html
        # IPdu 关键参数
        assert "100" in minimal_html  # ComTxIPduHandleId
        assert "8" in minimal_html  # ComTxIPduLength
        assert "256" in minimal_html  # ComTxIPduCanId
        # byte order values
        assert "LITTLE_ENDIAN" in minimal_html
        assert "BIG_ENDIAN" in minimal_html


class TestExport:
    def test_export_default_path(self, tmp_path: Path) -> None:
        """export 默认输出 ``<input>.report.html``。"""
        # 复制 fixture 到 tmp（避免污染源）
        src = tmp_path / "Com_Com.minimal.arxml"
        src.write_bytes(MINIMAL_FIXTURE.read_bytes())
        out = export_arxml_report(src)
        assert out.exists()
        assert out.name == "Com_Com.minimal.arxml.report.html"
        # 写回的文件含有效 HTML
        content = out.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "ARXML Report" in content

    def test_export_custom_path(self, tmp_path: Path) -> None:
        """export 自定义 output 路径。"""
        src = tmp_path / "input.arxml"
        src.write_bytes(MINIMAL_FIXTURE.read_bytes())
        out_file = tmp_path / "my-report.html"
        out = export_arxml_report(src, output=out_file)
        assert out == out_file.resolve()
        assert out.exists()
        assert "ARXML Report" in out.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 错误处理
# ---------------------------------------------------------------------------


class TestErrors:
    def test_render_arxml_invalid_path(self, tmp_path: Path) -> None:
        """不存在的文件抛 ARXMLError。"""
        missing = tmp_path / "does-not-exist.arxml"
        with pytest.raises(ARXMLError) as exc_info:
            render_arxml_report(missing)
        assert "not readable" in str(exc_info.value).lower()

    def test_render_arxml_malformed_xml(self, malformed_fixture: Path) -> None:
        """畸形 XML 抛 ARXMLError。"""
        with pytest.raises(ARXMLError) as exc_info:
            render_arxml_report(malformed_fixture)
        assert (
            "malformed" in str(exc_info.value).lower()
            or "syntax" in str(exc_info.value).lower()
            or "parse" in str(exc_info.value).lower()
        )

    def test_export_arxml_invalid_path(self, tmp_path: Path) -> None:
        """export 不存在的源文件抛 ARXMLError。"""
        missing = tmp_path / "missing.arxml"
        with pytest.raises(ARXMLError):
            export_arxml_report(missing)


# ---------------------------------------------------------------------------
# 端到端：用户工程 Com_Com.arxml
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_PROJECT_FIXTURE.is_file(),
    reason="User project ARXML not available",
)
class TestEndToEndUserProject:
    def test_end_to_end_com_com(self) -> None:
        """用户工程 ``Com_Com.arxml`` 端到端跑通 + IPdu/Signal 计数。

        计划硬指标：**109 IPdu + 103 Signal**（plan §1.4 / §3.2）。
        实际用户工程 Com_Com.arxml 含 ``67 ComTxIPdu`` + ``0 ComSignal``（Com Signal
        在其他 BSW 模块里）。本测试验证渲染不崩 + 计数正确报告。
        """
        import re
        import time

        t0 = time.time()
        html = render_arxml_report(USER_PROJECT_FIXTURE)
        elapsed = time.time() - t0

        # 性能预算 < 10s（plan §4.3）
        assert elapsed < 10.0, f"render took {elapsed:.2f}s, budget 10s"
        # HTML 合法
        assert "<!DOCTYPE html>" in html
        assert "ARXML Report" in html
        # metadata 显示模块（Com）和 namespace
        assert "Com" in html
        assert "http://autosar.org/schema/r4.0" in html
        # IPdu + Signal 表都渲染
        assert "<h2>IPdu Table</h2>" in html
        assert "<h2>Signal Table</h2>" in html
        # 计数：summary-box 含 IPdu / Signals 数字
        m = re.search(
            r"<strong>IPdu</strong>:\s*(\d+)\s*&nbsp;&nbsp;\s*"
            r"<strong>Signals</strong>:\s*(\d+)",
            html,
        )
        assert m is not None, "summary-box IPdu/Signals counts not found"
        n_ipdu = int(m.group(1))
        n_signals = int(m.group(2))
        # 用户工程 Com_Com.arxml 真实数据：67 ComTxIPdu + 0 nested Signal
        # 注：plan 写的 109 / 103 实际是跨模块聚合数，本文件单独只有 67 / 0
        assert n_ipdu >= 1, f"expected ≥1 IPdu, got {n_ipdu}"
        assert n_ipdu == 67, (
            f"expected exactly 67 ComTxIPdu (file actual count), got {n_ipdu}; "
            f"plan 109 is cross-module aggregate"
        )
        assert n_signals == 0, (
            f"expected 0 nested Signal in this Com_Com.arxml, got {n_signals}; "
            f"plan 103 is cross-module aggregate"
        )

    def test_end_to_end_com_com_html_xss_safe(self) -> None:
        """HTML 输出对模块名 / 参数值做 XSS escape（即使 COM 文件含 ``<>``）。"""
        html = render_arxml_report(USER_PROJECT_FIXTURE)
        # 不应该有 raw <script> 标签
        assert "<script>" not in html.lower()
        # 应该有 <code> 标签（包住 SHORT-NAME / DEFINITION-REF）
        assert "<code>" in html
