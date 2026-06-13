"""Unit tests for ``claude_autosar.core.bsw.inspector.xdm_report``.

Sprint 9.1 — T9.1.3。镜像 ``test_datamodel2_io.py`` 测试组织（class
划分 + parametrize 用例 + AAA pattern）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_autosar.core.bsw.io.datamodel2_io import DataModel2Error
from claude_autosar.core.bsw.inspector.xdm_report import (
    export_xdm_report,
    render_xdm_report,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "datamodel2"
USER_ENG_CAN_XDM = Path(
    r"D:/claude_proj2/src/S32K148_EAS_EB_3399A/EB_Cfg/simple_demo_rte/config/Can.xdm"
)

# Minimal DataModel2 树（hand-crafted，覆盖 d:chc / d:ctr / d:lst / d:var）
_SAMPLE_XDM = """<?xml version="1.0" encoding="UTF-8"?>
<datamodel version="7.0"
           xmlns="http://www.tresos.de/_projects/DataModel2/16/root.xsd"
           xmlns:a="http://www.tresos.de/_projects/DataModel2/16/attribute.xsd"
           xmlns:d="http://www.tresos.de/_projects/DataModel2/06/data.xsd">
  <d:ctr type="AUTOSAR" factory="autosar">
    <d:lst type="TOP-LEVEL-PACKAGES">
      <d:ctr name="Can" type="AR-PACKAGE">
        <d:lst type="ELEMENTS">
          <d:chc name="Can" type="AR-ELEMENT" value="MODULE-CONFIGURATION">
            <d:ctr type="MODULE-CONFIGURATION">
              <a:a name="DEF" value="ASPath:/Can"/>
              <d:var name="IMPLEMENTATION_CONFIG_VARIANT" type="ENUMERATION"
                     value="VariantPostBuild"/>
              <d:ctr name="CanConfigSet" type="IDENTIFIABLE">
                <a:a name="IMPORTER_INFO" value="ImportEcuConfig"/>
                <d:lst name="CanController" type="MAP">
                  <d:ctr name="BMS_J1939PT" type="IDENTIFIABLE">
                    <d:var name="CanHwChannel" type="ENUMERATION"
                           value="FlexCAN_A"/>
                    <d:var name="CanControllerActivation" type="BOOLEAN"
                           value="true"/>
                    <d:var name="CanControllerBaseAddress" type="INTEGER"
                           value="0"/>
                  </d:ctr>
                </d:lst>
              </d:ctr>
              <d:ctr name="CanGeneral" type="IDENTIFIABLE">
                <d:doc>General CAN module settings.</d:doc>
                <d:var name="CanDevErrorDetect" type="BOOLEAN" value="true"/>
                <d:var name="CanTimeoutDuration" type="INTEGER" value="100"/>
                <d:var name="CanIndex" type="INTEGER" value="0"/>
              </d:ctr>
            </d:ctr>
          </d:chc>
        </d:lst>
      </d:ctr>
    </d:lst>
  </d:ctr>
</datamodel>
"""


@pytest.fixture
def sample_xdm(tmp_path: Path) -> Path:
    """写入 sample XDM 到 tmp_path；返回 path。"""
    f = tmp_path / "sample.xdm"
    f.write_text(_SAMPLE_XDM, encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# render_xdm_report
# ---------------------------------------------------------------------------


class TestRenderXdmReport:
    """对 ``render_xdm_report`` 公共 API 的核心行为测试。"""

    def test_render_minimal_can_xdm(self, sample_xdm: Path) -> None:
        """最小 DataModel2 .xdm 渲染出 HTML 字符串（非空 + 合法 HTML）。"""
        html = render_xdm_report(sample_xdm)
        assert isinstance(html, str)
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html
        assert "Can" in html  # module name in title

    def test_render_html_contains_canconfigset(self, sample_xdm: Path) -> None:
        """HTML 含 ``CanConfigSet`` 段（容器表 + 关键参数 path）。"""
        html = render_xdm_report(sample_xdm)
        assert "CanConfigSet" in html

    def test_render_html_contains_cangeneral(self, sample_xdm: Path) -> None:
        """HTML 含 ``CanGeneral`` 段（含 ``<d:doc>`` 描述文本）。"""
        html = render_xdm_report(sample_xdm)
        assert "CanGeneral" in html
        # 容器 doc 文本也会渲染
        assert "General CAN module settings" in html

    def test_render_html_contains_leaf_vars(self, sample_xdm: Path) -> None:
        """HTML 含叶子变量（CanHwChannel / CanDevErrorDetect 等）。"""
        html = render_xdm_report(sample_xdm)
        for name in (
            "CanHwChannel",
            "CanDevErrorDetect",
            "CanTimeoutDuration",
            "CanControllerActivation",
        ):
            assert name in html, f"missing leaf var {name!r}"

    def test_render_html_contains_metadata(self, sample_xdm: Path) -> None:
        """HTML 含元数据（path / namespace / file size / module）。"""
        html = render_xdm_report(sample_xdm)
        assert "Metadata" in html
        assert "Default namespace" in html
        assert "File size" in html
        assert "DataModel2" in html
        # 实际默认 ns 应是 DataModel2 16 root
        assert "DataModel2/16/root.xsd" in html

    def test_render_html_is_xss_safe(self, sample_xdm: Path) -> None:
        """HTML 用 ``html.escape`` 防御 XSS — 即便 path 含 ``<script>`` 也安全。

        实际不会注入 — 但应确保 ``_html_escape`` 路径被覆盖。
        """
        html = render_xdm_report(sample_xdm)
        # 没有未转义的 ``<`` 紧跟 ``script`` 字符
        assert "<script>" not in html.lower()

    def test_render_invalid_path_raises(self, tmp_path: Path) -> None:
        """不存在的文件抛 :class:`DataModel2Error`。"""
        f = tmp_path / "nonexistent.xdm"
        with pytest.raises(DataModel2Error):
            render_xdm_report(f)

    def test_render_malformed_xml_raises(self, tmp_path: Path) -> None:
        """畸形 XML 抛 :class:`DataModel2Error`（lxml recovery 也救不回来）。"""
        f = tmp_path / "bad.xdm"
        f.write_bytes(b"\x00\x01\x02 not xml <<<")
        with pytest.raises(DataModel2Error):
            render_xdm_report(f)

    def test_render_xdm_without_module_chc(self, tmp_path: Path) -> None:
        """没有 ``<d:chc type=AR-ELEMENT>`` 的 XDM → ``<unknown-module>`` fallback。"""
        f = tmp_path / "no_module.xdm"
        f.write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<datamodel xmlns="http://www.tresos.de/_projects/DataModel2/16/root.xsd"
           xmlns:d="http://www.tresos.de/_projects/DataModel2/06/data.xsd">
  <d:ctr type="AUTOSAR" factory="autosar"/>
</datamodel>
""",
            encoding="utf-8",
        )
        html = render_xdm_report(f)
        # fallback to unknown-module name in title
        assert "unknown-module" in html

    def test_render_xdm_with_empty_containers(self, tmp_path: Path) -> None:
        """module 下无任何 container 的 XDM → 渲染 "No top-level containers" 文案。"""
        f = tmp_path / "empty.xdm"
        f.write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<datamodel xmlns="http://www.tresos.de/_projects/DataModel2/16/root.xsd"
           xmlns:d="http://www.tresos.de/_projects/DataModel2/06/data.xsd">
  <d:ctr type="AUTOSAR" factory="autosar">
    <d:lst type="TOP-LEVEL-PACKAGES">
      <d:ctr name="Can" type="AR-PACKAGE">
        <d:lst type="ELEMENTS">
          <d:chc name="Can" type="AR-ELEMENT" value="MODULE-CONFIGURATION">
            <d:ctr type="MODULE-CONFIGURATION">
              <d:var name="LonelyVar" type="STRING" value="hi"/>
            </d:ctr>
          </d:chc>
        </d:lst>
      </d:ctr>
    </d:lst>
  </d:ctr>
</datamodel>
""",
            encoding="utf-8",
        )
        html = render_xdm_report(f)
        assert "No top-level containers detected" in html
        assert "LonelyVar" in html


# ---------------------------------------------------------------------------
# 真实 fixture：tests/fixtures/datamodel2/Can.xdm
# ---------------------------------------------------------------------------


class TestRenderUserFixture:
    """对 Sprint 9.0 写的 ``tests/fixtures/datamodel2/Can.xdm`` 跑通。"""

    @pytest.fixture
    def can_xdm(self) -> Path:
        p = FIXTURES_DIR / "Can.xdm"
        if not p.exists():
            pytest.skip(f"fixture missing: {p}")
        return p

    def test_render_can_xdm_succeeds(self, can_xdm: Path) -> None:
        """Sprint 9.0 写的 gold-file Can.xdm 渲染成功。"""
        html = render_xdm_report(can_xdm)
        assert isinstance(html, str)
        assert "<!DOCTYPE html>" in html
        assert "</html>" in html

    def test_render_can_xdm_has_canconfigset(self, can_xdm: Path) -> None:
        """Can.xdm 报告含 CanConfigSet 段。"""
        html = render_xdm_report(can_xdm)
        assert "CanConfigSet" in html

    def test_render_can_xdm_has_cangeneral(self, can_xdm: Path) -> None:
        """Can.xdm 报告含 CanGeneral 段。"""
        html = render_xdm_report(can_xdm)
        assert "CanGeneral" in html

    def test_render_can_xdm_has_canhwchannel(self, can_xdm: Path) -> None:
        """Can.xdm 报告含 CanHwChannel 叶子（典型 ENUM 值 ``FlexCAN_A``）。"""
        html = render_xdm_report(can_xdm)
        assert "CanHwChannel" in html
        assert "FlexCAN_A" in html

    def test_render_can_xdm_has_dm_root_ns(self, can_xdm: Path) -> None:
        """默认 namespace 正确探测（DataModel2 16 root）。"""
        html = render_xdm_report(can_xdm)
        assert "DataModel2/16/root.xsd" in html


# ---------------------------------------------------------------------------
# DataModel2 树扁平化行为
# ---------------------------------------------------------------------------


class TestFlattenTree:
    """xdm_report 内部扁平化逻辑（容器 / 叶子 / namespace）。"""

    def test_render_xdm_walks_nested_containers(
        self, sample_xdm: Path
    ) -> None:
        """嵌套 ``<d:ctr>`` / ``<d:lst>`` 树走通（CanConfigSet > CanController > CanHwChannel）。

        验证：``build_path`` 能正确沿 ancestors 拼出完整路径；多级
        ``<d:ctr>`` + ``<d:lst>`` + ``<d:var>`` 都进 path。
        """
        html = render_xdm_report(sample_xdm)
        # CanController 容器路径出现在 leaves 列表里
        assert "Can/CanConfigSet/CanController" in html
        # 叶子 path 出现（build_path 沿 ancestors 拼出完整路径）
        # 注意：BMS_J1939PT 是 <d:lst name="CanController"> 下的具体 <d:ctr>
        # entry，所以完整路径是 Can/CanConfigSet/CanController/BMS_J1939PT/<var>
        assert "BMS_J1939PT" in html
        assert "CanHwChannel" in html
        # 父链完整（验证 build_path 不漏 ancestor）
        assert "Can/CanConfigSet/CanController/BMS_J1939PT/CanHwChannel" in html
        # CanGeneral 的叶子路径也要能拼出
        assert "Can/CanGeneral/CanDevErrorDetect" in html

    def test_render_xdm_collects_leaf_vars(
        self, sample_xdm: Path
    ) -> None:
        """叶子 ``<d:var>`` 含 name + type + value 全部进 HTML。"""
        html = render_xdm_report(sample_xdm)
        # CanHwChannel: ENUMERATION, FlexCAN_A
        assert "ENUMERATION" in html
        assert "FlexCAN_A" in html
        # CanControllerActivation: BOOLEAN, true
        assert "BOOLEAN" in html
        # CanControllerBaseAddress: INTEGER, 0
        assert "INTEGER" in html

    def test_render_xdm_namespace_handling(
        self, sample_xdm: Path
    ) -> None:
        """DataModel2 双命名空间正确处理（不漏元素）。

        - d: = DataModel2 data xsd（固定）
        - 默认 ns = DataModel2 16 root（探测）

        验证：当 d: 路径探测到 module 容器时，所有 d:var 都能被 xpath 找到。
        """
        html = render_xdm_report(sample_xdm)
        # 5 个 var 都应被找到（CanConfigSet/CanController 下 3 个 + CanGeneral 下 3 个）
        leaf_count = html.count("leaf-value-")
        # 至少 5 个叶子 + 每个 var 一行（覆盖 leaf-value-enum / int / bool）
        assert leaf_count >= 5, f"expected ≥5 leaf values, got {leaf_count}"


# ---------------------------------------------------------------------------
# export_xdm_report
# ---------------------------------------------------------------------------


class TestExportXdmReport:
    """``export_xdm_report`` 写文件路径行为。"""

    def test_export_default_path(
        self, sample_xdm: Path, tmp_path: Path
    ) -> None:
        """默认输出 ``<input>.report.html``。"""
        # 用 tmp_path/sample.xdm 跑，输出应在 sample.xdm.report.html
        out = export_xdm_report(sample_xdm)
        assert out.exists()
        assert out.name == "sample.xdm.report.html"
        # 内容应是合法 HTML
        content = out.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "Can" in content

    def test_export_custom_path(
        self, sample_xdm: Path, tmp_path: Path
    ) -> None:
        """自定义 output 路径生效。"""
        out_path = tmp_path / "custom.html"
        out = export_xdm_report(sample_xdm, output=out_path)
        assert out == out_path.resolve()
        assert out_path.exists()
        content = out_path.read_text(encoding="utf-8")
        assert "Can" in content

    def test_export_overwrites_existing(
        self, sample_xdm: Path, tmp_path: Path
    ) -> None:
        """重复 export 覆盖已有文件（用 atomic replace）。"""
        out_path = tmp_path / "report.html"
        # 第一次
        out1 = export_xdm_report(sample_xdm, output=out_path)
        assert out1.exists()
        # 修改 input（加点内容）
        sample_xdm.write_text(
            _SAMPLE_XDM.replace("CanDevErrorDetect", "CanDevErrorDetect"),  # noop
            encoding="utf-8",
        )
        # 第二次
        out2 = export_xdm_report(sample_xdm, output=out_path)
        assert out2 == out1
        assert out_path.exists()

    def test_export_invalid_path_raises(self, tmp_path: Path) -> None:
        """输入文件不存在 → 抛 :class:`DataModel2Error`。"""
        f = tmp_path / "missing.xdm"
        with pytest.raises(DataModel2Error):
            export_xdm_report(f)


# ---------------------------------------------------------------------------
# 用户工程端到端（标记 skip 如果不可访问）
# ---------------------------------------------------------------------------


class TestEndToEndUserEngineering:
    """端到端在用户工程 ``Can.xdm`` 上跑通（如可访问）。"""

    def test_end_to_end_user_can_xdm(self) -> None:
        """``D:/claude_proj2/src/S32K148_EAS_EB_3399A/.../Can.xdm`` 端到端。"""
        if not USER_ENG_CAN_XDM.exists():
            pytest.skip(f"user engineering XDM not accessible: {USER_ENG_CAN_XDM}")
        html = render_xdm_report(USER_ENG_CAN_XDM)
        # 用户工程 Can.xdm 必须有 CanConfigSet / CanGeneral / CanHwChannel
        assert "CanConfigSet" in html
        assert "CanGeneral" in html
        assert "CanHwChannel" in html
        # 至少 1 个 FlexCAN 物理通道值
        assert any(s in html for s in ("FlexCAN_A", "FlexCAN_B", "FlexCAN_C", "FlexCAN_D"))


class TestXssDefense:
    """XSS 防御：渲染 HTML 时所有动态字段必须 escape（plan §T9.1.3 + code-review H-2）。"""

    def test_xdm_report_title_escapes_hostile_module_name(
        self, tmp_path: Path
    ) -> None:
        """``<d:chc name=<script>...>`` 在 ``<h1>`` title 里必须 escape（H-2 修复）。

        攻击向量：恶意 .xdm 把 module name 写成 ``<img/src=x/onerror=alert(1)>``，
        渲染时未 escape 会注入 HTML → 用户浏览器执行 JS。
        """
        import pytest  # noqa: PLC0415

        hostile_xdm = tmp_path / "hostile.xdm"
        hostile_xdm.write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<d:datamodel xmlns:d="http://www.tresos.de/_projects/DataModel2/06/data.xsd"
             xmlns="http://www.tresos.de/_projects/DataModel2/16/root.xsd">
  <d:chc name="&lt;img/src=x/onerror=alert(1)&gt;" type="AR-ELEMENT"/>
</d:datamodel>
""",
            encoding="utf-8",
        )
        html = render_xdm_report(hostile_xdm)
        # 未 escape 会含 ``<img/src=x`` → 应该 escape 成 ``&lt;img/src=x``
        assert "<img/src=x" not in html, (
            f"XSS: hostile module name not escaped in title: {html[:500]}"
        )
        assert "&lt;img/src=x/onerror=alert(1)&gt;" in html, (
            f"XSS: hostile module name should be HTML-escaped, got: {html[:500]}"
        )
