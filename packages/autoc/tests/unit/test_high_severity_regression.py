"""HIGH 严重 bug regression 测试（审计 2026-06-20）。

涵盖 9 个 HIGH-severity bug，每个 test 在 bug 未修时必须失败：

- HIGH-1：``arxml_io`` surgical patch 写回未转义 XML 实体 → 产生畸形 XML
- HIGH-2：``datamodel2_io._patch_parent_form`` 同样未转义
- HIGH-3：``session_export`` ``output`` 参数无路径校验 → 任意文件写入
- HIGH-4：inspect tool ``output`` 无 containment check → 任意文件写入
- HIGH-5：``_render_diff_html`` diff 字段未 escape → XSS
- HIGH-6：``coverage`` 仅按 short_name 匹配 → 同名参数误判
- HIGH-7：``_count_existing_in_parent`` 统计叶子而非实例 → multiplicity 误拒
- HIGH-8：BOOLEAN template 用 ECUC-BOOLEAN-PARAM-DEF + ECUC-TEXTUAL-PARAM-VALUE
  → 产出 vendor 拒收的 ARXML
- HIGH-9：``bsw_validate`` / ``bsw_diff`` ``project`` 缺 ``_resolve_safe_project``

策略：路径类 HIGH（3/4/9）通过 monkeypatch ``_ALLOWED_PROJECT_ROOTS`` 注入
tmp_path，从而允许 happy path 正常跑过；安全测试用绝对路径验证被拒。
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 共用 fixture：扩展 _ALLOWED_PROJECT_ROOTS 以兼容 pytest tmp_path
# ---------------------------------------------------------------------------


@pytest.fixture
def allow_tmp_in_safe_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """把 tmp_path 加入 ``_ALLOWED_PROJECT_ROOTS``。"""
    import claude_autosar.cli.mcp_server as srv

    roots = frozenset({Path.cwd().resolve(), tmp_path.resolve()})
    monkeypatch.setattr(srv, "_ALLOWED_PROJECT_ROOTS", roots)
    return tmp_path


# ---------------------------------------------------------------------------
# HIGH-1 — arxml_io surgical patch 未转义 XML 实体
# ---------------------------------------------------------------------------


class TestHigh1ArxmlIoSurgicalEscape:
    """HIGH-1：surgical patch 写回时必须 escape ``&`` ``<`` ``>``。"""

    _ARXML_WITH_AMP = b"""<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES><AR-PACKAGE><SHORT-NAME>B</SHORT-NAME><ELEMENTS>
    <ECUC-MODULE-CONFIGURATION-VALUES>
      <SHORT-NAME>Mcu</SHORT-NAME>
      <CONTAINERS>
        <ECUC-PARAM-CONF-CONTAINER>
          <SHORT-NAME>Root</SHORT-NAME>
          <PARAMETER-VALUES>
            <ECUC-TEXTUAL-PARAM-VALUE>
              <DEFINITION-REF DEST="ECUC-STRING-PARAM-DEF">/Mcu/Root/Title</DEFINITION-REF>
              <VALUE>Tom &amp; Jerry</VALUE>
            </ECUC-TEXTUAL-PARAM-VALUE>
          </PARAMETER-VALUES>
        </ECUC-PARAM-CONF-CONTAINER>
      </CONTAINERS>
    </ECUC-MODULE-CONFIGURATION-VALUES>
  </ELEMENTS></AR-PACKAGE></AR-PACKAGES>
</AUTOSAR>
"""

    def test_ampersand_round_trips_through_surgical_patch(self, tmp_path: Path) -> None:
        """VALUE 含 ``&amp;`` 时，surgical patch 改文本后写回的 XML 仍可被 lxml 解析。"""
        from lxml import etree

        from claude_autosar.core.bsw.arxml_io import _apply_surgical_patch_to_bytes, read

        src = tmp_path / "Mcu.arxml"
        src.write_bytes(self._ARXML_WITH_AMP)
        original_bytes = src.read_bytes()

        doc = read(src)
        tree = doc.tree
        ns = {"ar": "http://autosar.org/schema/r4.0"}
        value_elems = tree.getroot().xpath(".//ar:VALUE", namespaces=ns)
        assert value_elems, "test fixture broken: no <VALUE>"
        # decoded 文本 "Tom & Ben"（含 ``&``）
        value_elems[0].text = "Tom & Ben"

        patched = _apply_surgical_patch_to_bytes(original_bytes, tree)
        # 1) 写回字节必须能被 lxml 解析
        try:
            re_parsed = etree.fromstring(patched)
        except etree.XMLSyntaxError as e:
            pytest.fail(f"patched XML not well-formed: {e}\n{patched.decode('utf-8')}")

        # 2) round-trip 后值保持
        rt = re_parsed.xpath(".//ar:VALUE", namespaces=ns)[0].text
        assert rt == "Tom & Ben", f"expected 'Tom & Ben', got {rt!r}"

    def test_gt_entity_round_trips_through_surgical_patch(self, tmp_path: Path) -> None:
        """VALUE 含 ``>`` 时，surgical patch 写回的 XML 必须合法。"""
        from lxml import etree

        from claude_autosar.core.bsw.arxml_io import _apply_surgical_patch_to_bytes, read

        # value = "5 > 3"
        xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES><AR-PACKAGE><SHORT-NAME>B</SHORT-NAME><ELEMENTS>
    <ECUC-MODULE-CONFIGURATION-VALUES>
      <SHORT-NAME>Mcu</SHORT-NAME>
      <CONTAINERS>
        <ECUC-PARAM-CONF-CONTAINER>
          <SHORT-NAME>Root</SHORT-NAME>
          <PARAMETER-VALUES>
            <ECUC-TEXTUAL-PARAM-VALUE>
              <DEFINITION-REF DEST="ECUC-STRING-PARAM-DEF">/Mcu/Root/Formula</DEFINITION-REF>
              <VALUE>5 &gt; 3</VALUE>
            </ECUC-TEXTUAL-PARAM-VALUE>
          </PARAMETER-VALUES>
        </ECUC-PARAM-CONF-CONTAINER>
      </CONTAINERS>
    </ECUC-MODULE-CONFIGURATION-VALUES>
  </ELEMENTS></AR-PACKAGE></AR-PACKAGES>
</AUTOSAR>
"""
        src = tmp_path / "Mcu.arxml"
        src.write_bytes(xml)
        original_bytes = src.read_bytes()

        doc = read(src)
        ns = {"ar": "http://autosar.org/schema/r4.0"}
        value_elems = doc.tree.getroot().xpath(".//ar:VALUE", namespaces=ns)
        value_elems[0].text = "10 > 5"

        patched = _apply_surgical_patch_to_bytes(original_bytes, doc.tree)
        try:
            etree.fromstring(patched)
        except etree.XMLSyntaxError as e:
            pytest.fail(f"patched XML with ``>`` not well-formed: {e}")


# ---------------------------------------------------------------------------
# HIGH-2 — datamodel2_io _patch_parent_form 未转义
# ---------------------------------------------------------------------------


class TestHigh2Datamodel2ParentFormEscape:
    """HIGH-2：``<a:v>...</a:v>`` 文本写回时必须 escape。"""

    # parent-form: ``<a:a name="X"><a:v>Y &amp; Z</a:v></a:a>``
    _XDM_PARENT_FORM = b"""<?xml version="1.0" encoding="UTF-8"?>
<d:DATAMODEL xmlns:d="http://www.tresos.de/_projects/DataModel2/06/data.xsd"
             xmlns:a="http://www.tresos.de/_projects/DataModel2/16/attribute.xsd"
             xmlns:v="http://www.tresos.de/_projects/DataModel2/06/schema.xsd">
  <d:chc name="Mcu" type="AR-ELEMENT">
    <d:lst name="Root" type="AR-PARAM-CONF-CONTAINER">
      <d:var name="Title" type="STRING">
        <a:a name="KEEP"><a:v>constant</a:v></a:a>
        <a:a name="TITLE"><a:v>A &amp; B</a:v></a:a>
      </d:var>
    </d:lst>
  </d:chc>
</d:DATAMODEL>
"""

    def test_parent_form_ampersand_writes_valid_xml(self, tmp_path: Path) -> None:
        """parent-form ``<a:v>X &amp; Y</a:v>`` 改文本后写回仍是 well-formed XML。"""
        from lxml import etree

        from claude_autosar.core.bsw.io.datamodel2_io import (
            _apply_surgical_patch_to_bytes,
            read,
        )

        src = tmp_path / "Mcu.xdm"
        src.write_bytes(self._XDM_PARENT_FORM)
        original_bytes = src.read_bytes()

        tree = read(src)
        # ``<a:v>`` 在 attribute.xsd 命名空间；用 local-name 匹配避免耦合命名空间
        v_elems = tree.xpath(".//*[local-name()='v']")
        assert len(v_elems) == 2, f"fixture broken: expected 2 <a:v>, got {len(v_elems)}"
        # 改第二个 ``<a:v>`` 的文本（decoded "X & Y"）
        v_elems[1].text = "X & Y"

        patched = _apply_surgical_patch_to_bytes(original_bytes, tree)
        try:
            etree.fromstring(patched)
        except etree.XMLSyntaxError as e:
            pytest.fail(
                f"parent-form patched XML not well-formed: {e}\n{patched.decode('utf-8')}"
            )

        re_parsed = etree.fromstring(patched)
        rt = re_parsed.xpath(".//*[local-name()='v']")
        assert rt[1].text == "X & Y"


# ---------------------------------------------------------------------------
# HIGH-3 — session_export output 路径校验
# ---------------------------------------------------------------------------


class TestHigh3SessionExportOutputValidation:
    """HIGH-3：``session_export(..., output=...)`` 须拒绝非法路径。"""

    def test_session_export_rejects_path_traversal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``output="../../etc/evil.html"`` → 返回 error dict（不写文件）。"""
        from claude_autosar.cli.mcp_tools.session_ops import session_export
        from claude_autosar.core.session.store import SessionEntry, SessionStore

        monkeypatch.setattr(
            "claude_autosar.cli.mcp_server._default_session_dir", lambda: tmp_path
        )
        store = SessionStore(dir=tmp_path)
        store.append(
            SessionEntry(
                id="e1",
                parent_id=None,
                session_id="s1",
                timestamp="2026-01-01T00:00:00+00:00",
                kind="user",
                content="hi",
            )
        )

        evil = str(tmp_path / "subdir" / "../../etc/evil.html")
        r = session_export("s1", fmt="html", output=evil, session_dir=str(tmp_path))
        assert r["success"] is False
        assert "traversal" in r["error"].lower() or "PermissionError" in r["error"]

    def test_session_export_rejects_absolute_outside_allowed_roots(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``output="/nonexistent_root/evil.html"`` → 拒绝。"""
        from claude_autosar.cli.mcp_tools.session_ops import session_export
        from claude_autosar.core.session.store import SessionEntry, SessionStore

        monkeypatch.setattr(
            "claude_autosar.cli.mcp_server._default_session_dir", lambda: tmp_path
        )
        store = SessionStore(dir=tmp_path)
        store.append(
            SessionEntry(
                id="e1",
                parent_id=None,
                session_id="s1",
                timestamp="2026-01-01T00:00:00+00:00",
                kind="user",
                content="hi",
            )
        )

        r = session_export(
            "s1",
            fmt="html",
            output="/nonexistent_root_for_test_high3_session/evil.html",
            session_dir=str(tmp_path),
        )
        assert r["success"] is False


# ---------------------------------------------------------------------------
# HIGH-4 — inspect tool output containment
# ---------------------------------------------------------------------------


class TestHigh4InspectOutputContainment:
    """HIGH-4：``arxml_inspect`` / ``xdm_inspect`` / ``bsw_inspect`` 的
    ``output`` 参数必须在 allowed roots 内。"""

    FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
    ARXML_FIXTURE = FIXTURES_DIR / "arxml" / "Com_Com.minimal.arxml"
    XDM_FIXTURE = FIXTURES_DIR / "datamodel2" / "Can.xdm"

    def test_arxml_inspect_rejects_output_outside_allowed_roots(self, tmp_path: Path) -> None:
        """``output="/nonexistent_root/evil.html"`` → 拒绝。"""
        from claude_autosar.cli.mcp_tools.inspect_ops import arxml_inspect

        src = tmp_path / "Mcu.arxml"
        src.write_bytes(self.ARXML_FIXTURE.read_bytes())

        result = arxml_inspect(
            str(src),
            output="/nonexistent_root_for_test_inspect_high4/evil.html",
        )
        assert result["success"] is False
        assert (
            "PermissionError" in result["error"]
            or "traversal" in result["error"].lower()
        )

    def test_xdm_inspect_rejects_output_outside_allowed_roots(self, tmp_path: Path) -> None:
        """``output="/nonexistent_root/evil.html"`` → 拒绝。"""
        from claude_autosar.cli.mcp_tools.inspect_ops import xdm_inspect

        src = tmp_path / "Can.xdm"
        src.write_bytes(self.XDM_FIXTURE.read_bytes())

        result = xdm_inspect(
            str(src),
            output="/nonexistent_root_for_test_inspect_high4/evil.html",
        )
        assert result["success"] is False
        assert (
            "PermissionError" in result["error"]
            or "traversal" in result["error"].lower()
        )

    def test_bsw_inspect_rejects_output_outside_allowed_roots(self, tmp_path: Path) -> None:
        """``bsw_inspect output=...`` 绝对路径外 → 拒绝。"""
        from claude_autosar.cli.mcp_tools.inspect_ops import bsw_inspect

        src = tmp_path / "Mcu.arxml"
        src.write_bytes(self.ARXML_FIXTURE.read_bytes())

        result = bsw_inspect(
            str(src),
            output="/nonexistent_root_for_test_inspect_high4/evil.html",
        )
        assert result["success"] is False
        assert (
            "PermissionError" in result["error"]
            or "traversal" in result["error"].lower()
        )

    def test_arxml_inspect_accepts_output_in_allowed_roots(self, tmp_path: Path) -> None:
        """happy path：output 在 tmp_path 内应被接受（autouse fixture 已注入 tmp_path）。"""
        from claude_autosar.cli.mcp_tools.inspect_ops import arxml_inspect

        src = tmp_path / "Mcu.arxml"
        src.write_bytes(self.ARXML_FIXTURE.read_bytes())
        out = tmp_path / "report.html"

        result = arxml_inspect(str(src), output=str(out))
        assert result["success"] is True
        assert out.exists()


# ---------------------------------------------------------------------------
# HIGH-9 — bsw_validate / bsw_diff project 安全边界
# ---------------------------------------------------------------------------


class TestHigh9ValidateDiffSafeProject:
    """HIGH-9：``project`` 参数必须走 ``_resolve_safe_project`` 而非
    ``validate_no_traversal``。"""

    def test_bsw_validate_rejects_project_outside_allowed_roots(self) -> None:
        """``project="/nonexistent_root"`` → 返回 PermissionError error dict。"""
        from claude_autosar.cli.mcp_tools.validate_ops import bsw_validate

        result = bsw_validate("Mcu", project="/nonexistent_root_for_test_validate")
        assert result["success"] is False
        assert "PermissionError" in result["error"]

    def test_bsw_diff_rejects_project_outside_allowed_roots(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``bsw_diff(project="/nonexistent_root")`` → 返回 PermissionError。"""
        import claude_autosar.cli.mcp_server as srv

        roots = frozenset({Path.cwd().resolve(), tmp_path.resolve()})
        monkeypatch.setattr(srv, "_ALLOWED_PROJECT_ROOTS", roots)

        from claude_autosar.cli.mcp_tools.diff_ops import bsw_diff

        fa = tmp_path / "a.arxml"
        fb = tmp_path / "b.arxml"
        fa.write_text("<A/>", encoding="utf-8")
        fb.write_text("<A/>", encoding="utf-8")

        result = bsw_diff(
            "Mcu",
            str(fa),
            str(fb),
            project="/nonexistent_root_for_test_diff_high9",
        )
        assert result["success"] is False
        assert "PermissionError" in result["error"]


# ---------------------------------------------------------------------------
# HIGH-5 — _render_diff_html 未 escape（XSS）
# ---------------------------------------------------------------------------


class TestHigh5DiffHtmlEscape:
    """HIGH-5：``_render_diff_html`` 5 个字段（path / op / cur / tpl / note）
    必须 escape，否则含 ``<script>`` 的 diff value 直接渲染。"""

    def test_arxml_render_diff_html_escapes_xss_payload(self, tmp_path: Path) -> None:
        """ARXML 端：``cur`` 含 ``<script>`` → 输出应是 ``&lt;script&gt;`` 实体。"""
        from claude_autosar.cli.commands.arxml_apply_template import _render_diff_html

        # 模拟恶意 diff row：cur 含 XSS payload
        rows = ((
            "Mcu/Root/ClockName",
            "modify",
            '<script>alert("xss")</script>',  # cur
            "PLL",                              # tpl
            "",
        ),)
        out_html = _render_diff_html(
            path=tmp_path / "Mcu.arxml",
            template=tmp_path / "Mcu_tpl.arxml",
            diff_rows=rows,
        )
        # 危险：payload 应该是字面文本，不能裸 <script>
        assert "<script>" not in out_html, (
            f"XSS payload not escaped:\n{out_html}"
        )
        assert "&lt;script&gt;" in out_html
        assert "&lt;/script&gt;" in out_html

    def test_arxml_render_diff_html_escapes_all_5_fields(self, tmp_path: Path) -> None:
        """5 个字段（path / op / cur / tpl / note）全部需要 escape。"""
        from claude_autosar.cli.commands.arxml_apply_template import _render_diff_html

        rows = ((
            "Mcu/Path/<img>",   # path
            "modify",            # op
            "<cur>x",            # cur
            "<tpl>y",            # tpl
            "<note>z",           # note
        ),)
        out = _render_diff_html(
            path=tmp_path / "a.arxml",
            template=tmp_path / "b.arxml",
            diff_rows=rows,
        )
        # 5 个字段都必须 escape
        for payload in (
            "<img>",
            "<cur>x",
            "<tpl>y",
            "<note>z",
        ):
            assert payload not in out, f"payload {payload!r} not escaped"
            assert payload.replace("<", "&lt;").replace(">", "&gt;") in out

    def test_xdm_render_diff_html_escapes_xss_payload(self, tmp_path: Path) -> None:
        """XDM 端同样要 escape（与 arxml 共用相同模式）。"""
        from claude_autosar.cli.commands.xdm_apply_template import _render_diff_html

        rows = ((
            "Can/CanConfigSet/<b>",
            "modify",
            '<script>alert("xss")</script>',
            "100",
            "",
        ),)
        out_html = _render_diff_html(
            path=tmp_path / "Can.xdm",
            template=tmp_path / "Can_tpl.xdm",
            diff_rows=rows,
        )
        assert "<script>" not in out_html
        assert "&lt;script&gt;" in out_html


# ---------------------------------------------------------------------------
# HIGH-6 — coverage 按 short_name 匹配导致同名 param 误判
# ---------------------------------------------------------------------------


class TestHigh6CoveragePathDedup:
    """HIGH-6：``compute_coverage`` 必须按 *完整 definition path* 比较，
    而非仅取 instance path 的最后一段 short_name。"""

    def test_same_short_name_different_containers_distinguished(self, tmp_path: Path) -> None:
        """``McuGeneral/Timeout`` vs ``McuClockSettingConfig/Timeout`` 同名 Timeout，
        只配其中一个应只报一个 configured，不能两个都报。"""
        from claude_autosar.core.bsw.bswmd import (
            BSWMDRegistry,
            ContainerDef,
            ModuleDef,
            ParamDef,
        )
        from claude_autosar.core.bsw.coverage import compute_coverage
        from claude_autosar.core.bsw.ecuc import ECUCDocument, ECUCValue

        # ECUCDocument 只配 McuGeneral/Timeout，不配 McuClockSettingConfig/Timeout
        doc = ECUCDocument(
            path=tmp_path / "Mcu.arxml",
            module_name="Mcu",
            values=(
                ECUCValue(
                    path="Mcu/McuGeneral/Timeout",
                    raw="50",
                    type="INTEGER",
                ),
            ),
        )

        reg = BSWMDRegistry(
            modules={
                "Mcu": ModuleDef(
                    short_name="Mcu",
                    full_path="/AUTOSAR/Mcu",
                    containers={
                        "McuGeneral": ContainerDef(
                            short_name="McuGeneral",
                            full_path="/AUTOSAR/Mcu/McuGeneral",
                            lower_multiplicity=0,
                            upper_multiplicity=1,
                            param_defs={
                                "Timeout": ParamDef(
                                    short_name="Timeout",
                                    full_path="/AUTOSAR/Mcu/McuGeneral/Timeout",
                                    param_type="INTEGER",
                                ),
                            },
                        ),
                        "McuClockSettingConfig": ContainerDef(
                            short_name="McuClockSettingConfig",
                            full_path="/AUTOSAR/Mcu/McuClockSettingConfig",
                            lower_multiplicity=0,
                            upper_multiplicity=1,
                            param_defs={
                                "Timeout": ParamDef(
                                    short_name="Timeout",
                                    full_path="/AUTOSAR/Mcu/McuClockSettingConfig/Timeout",
                                    param_type="INTEGER",
                                ),
                            },
                        ),
                    },
                ),
            },
        )

        report = compute_coverage(doc, reg)
        # 2 个 param，1 个配了 → 1 configured, 1 missing
        assert report.total_params == 2, f"expected 2 params, got {report.total_params}"
        assert report.configured_params == 1, (
            f"expected 1 configured (only McuGeneral/Timeout), got {report.configured_params}; "
            f"bug = short_name match misreports McuClockSettingConfig/Timeout as configured"
        )
        # McuClockSettingConfig/Timeout 应在 missing
        assert any(
            "McuClockSettingConfig" in m and "Timeout" in m for m in report.missing_params
        ), (
            f"expected McuClockSettingConfig/Timeout in missing, got {report.missing_params}"
        )


# ---------------------------------------------------------------------------
# HIGH-7 — multiplicity 统计 leaf 而非 instance
# ---------------------------------------------------------------------------


class TestHigh7MultiplicityInstanceCount:
    """HIGH-7：``validate_writes_against_bswmd`` 必须按 *实例去重* 计数，
    而非按 leaf 数。Bug 在多 param 容器下误拒合法写入。"""

    def test_multi_param_container_multi_instance_within_upper_passes(self) -> None:
        """容器 upper=3，含 4 个 INTEGER param：
        已有 2 个实例 Cfg_0 / Cfg_1，每个 4 leaves（共 8 leaves），
        准备在已有实例 Cfg_0 上再写 1 个 param → instance 数仍 2 ≤ upper=3 → 应通过。

        bug 行为：现有 leaves 4 (Cfg_0) + writes 1 = 5 > 3 → 误抛 UPPER。
        fix 行为：unique instance path 数 = {Cfg_0, Cfg_1} = 2 ≤ 3 → 通过。
        """
        from claude_autosar.core.bsw.bswmd import (
            BSWMDRegistry,
            ContainerDef,
            ModuleDef,
            ParamDef,
        )
        from claude_autosar.core.bsw.bsw_write_path import (
            validate_writes_against_bswmd,
        )
        from claude_autosar.core.bsw.config import BSWParam, ParamValue, ParamType
        from claude_autosar.core.bsw.ecuc import ECUCValue

        # 容器有 4 个 INTEGER param（min=0, max=100）
        param_defs = {
            f"P{i}": ParamDef(
                short_name=f"P{i}",
                full_path=f"/AUTOSAR/Mcu/Cfg/P{i}",
                param_type="INTEGER",
                min="0",
                max="100",
            )
            for i in range(4)
        }
        reg = BSWMDRegistry(
            modules={
                "Mcu": ModuleDef(
                    short_name="Mcu",
                    full_path="/AUTOSAR/Mcu",
                    containers={
                        "Cfg": ContainerDef(
                            short_name="Cfg",
                            full_path="/AUTOSAR/Mcu/Cfg",
                            lower_multiplicity=0,
                            upper_multiplicity=3,
                            param_defs=param_defs,
                        ),
                    },
                ),
            },
            root_package_name="AUTOSAR",
        )

        # 已有 2 个实例 Cfg_0 / Cfg_1，每个 4 leaves
        existing = (
            ECUCValue(path="Mcu/Cfg_0/P0", raw="10", type="INTEGER"),
            ECUCValue(path="Mcu/Cfg_0/P1", raw="20", type="INTEGER"),
            ECUCValue(path="Mcu/Cfg_0/P2", raw="30", type="INTEGER"),
            ECUCValue(path="Mcu/Cfg_0/P3", raw="40", type="INTEGER"),
            ECUCValue(path="Mcu/Cfg_1/P0", raw="50", type="INTEGER"),
            ECUCValue(path="Mcu/Cfg_1/P1", raw="60", type="INTEGER"),
            ECUCValue(path="Mcu/Cfg_1/P2", raw="70", type="INTEGER"),
            ECUCValue(path="Mcu/Cfg_1/P3", raw="80", type="INTEGER"),
        )
        # 写 1 个新 param 到已有实例 Cfg_0（不创建新 instance）
        writes = (
            BSWParam(
                path="Mcu/Cfg_0/P3",
                value=ParamValue(raw="99", type=ParamType.INTEGER),
            ),
        )
        # bug 行为：existing_in_parent("Mcu/Cfg_0") = 4 + writes 1 = 5 > 3 → 误抛
        # fix 行为：unique instance path = {Cfg_0, Cfg_1} = 2 ≤ 3 → 通过
        validate_writes_against_bswmd(reg, "Mcu", existing, writes)

    def test_multi_instance_exceeds_upper_raises(self) -> None:
        """3 个已有实例 + 写第 4 个新实例 → 4 > upper=3 → 应抛。

        bug 行为：parent_path="Mcu/Cfg_3" 不在 existing 中 → count=0 → 不抛（漏报）。
        fix 行为：unique instance path = {Cfg_0, Cfg_1, Cfg_2, Cfg_3} = 4 > 3 → 抛。
        """
        from claude_autosar.core.bsw.bswmd import (
            BSWMDRegistry,
            ContainerDef,
            ModuleDef,
            ParamDef,
        )
        from claude_autosar.core.bsw.bsw_write_path import (
            BSWWritePathError,
            validate_writes_against_bswmd,
        )
        from claude_autosar.core.bsw.config import BSWParam, ParamValue, ParamType
        from claude_autosar.core.bsw.ecuc import ECUCValue

        param_defs = {
            f"P{i}": ParamDef(
                short_name=f"P{i}",
                full_path=f"/AUTOSAR/Mcu/Cfg/P{i}",
                param_type="INTEGER",
                min="0",
                max="100",
            )
            for i in range(4)
        }
        reg = BSWMDRegistry(
            modules={
                "Mcu": ModuleDef(
                    short_name="Mcu",
                    full_path="/AUTOSAR/Mcu",
                    containers={
                        "Cfg": ContainerDef(
                            short_name="Cfg",
                            full_path="/AUTOSAR/Mcu/Cfg",
                            lower_multiplicity=0,
                            upper_multiplicity=3,
                            param_defs=param_defs,
                        ),
                    },
                ),
            },
            root_package_name="AUTOSAR",
        )

        # 已有 3 个实例（每个 1 leaf），共 3 leaves
        existing = (
            ECUCValue(path="Mcu/Cfg_0/P0", raw="10", type="INTEGER"),
            ECUCValue(path="Mcu/Cfg_1/P0", raw="20", type="INTEGER"),
            ECUCValue(path="Mcu/Cfg_2/P0", raw="30", type="INTEGER"),
        )
        # 写第 4 个新实例 → 4 > upper=3 → 应抛
        writes = (
            BSWParam(
                path="Mcu/Cfg_3/P0",
                value=ParamValue(raw="40", type=ParamType.INTEGER),
            ),
        )
        with pytest.raises(BSWWritePathError) as exc_info:
            validate_writes_against_bswmd(reg, "Mcu", existing, writes)
        assert "UPPER-MULTIPLICITY=3" in str(exc_info.value)


# ---------------------------------------------------------------------------
# HIGH-8 — BOOLEAN template DEST/pv_tag 错
# ---------------------------------------------------------------------------


class TestHigh8BooleanTemplateTags:
    """HIGH-8：BOOLEAN 必须用 ``ECUC-NUMERICAL-PARAM-VALUE`` +
    ``ECUC-NUMERICAL-PARAM-DEF``。bug 用 ``ECUC-TEXTUAL-PARAM-VALUE`` +
    ``ECUC-BOOLEAN-PARAM-DEF``（vendor 不识别）。"""

    def test_boolean_add_uses_numerical_tags(self, tmp_path: Path) -> None:
        """add 一个 BOOLEAN param → 写出 ``ECUC-NUMERICAL-PARAM-VALUE`` +
        ``DEST="ECUC-NUMERICAL-PARAM-DEF"``。"""
        from lxml import etree

        from claude_autosar.core.bsw.ecuc import ECUCValue, load_module
        from claude_autosar.core.bsw.templates.apply import ApplyMode, apply_template_diff
        from claude_autosar.core.bsw.templates.arxml_diff import (
            TemplateDiff,
            TemplateDiffResult,
        )

        _MCU_V1 = """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES><AR-PACKAGE><SHORT-NAME>B</SHORT-NAME><ELEMENTS>
    <ECUC-MODULE-CONFIGURATION-VALUES>
      <SHORT-NAME>Mcu</SHORT-NAME>
      <CONTAINERS>
        <ECUC-PARAM-CONF-CONTAINER>
          <SHORT-NAME>Root</SHORT-NAME>
          <PARAMETER-VALUES>
            <ECUC-NUMERICAL-PARAM-VALUE>
              <DEFINITION-REF DEST="ECUC-INTEGER-PARAM-DEF">/Mcu/Root/ClockFreq</DEFINITION-REF>
              <VALUE>80000000</VALUE>
            </ECUC-NUMERICAL-PARAM-VALUE>
          </PARAMETER-VALUES>
        </ECUC-PARAM-CONF-CONTAINER>
      </CONTAINERS>
    </ECUC-MODULE-CONFIGURATION-VALUES>
  </ELEMENTS></AR-PACKAGE></AR-PACKAGES>
</AUTOSAR>
"""
        f = tmp_path / "Mcu.arxml"
        f.write_text(_MCU_V1, encoding="utf-8")

        diff = TemplateDiffResult(
            module_name="Mcu",
            diffs=(
                TemplateDiff(
                    path="Mcu/Root/IsEnabled",
                    current=None,
                    template=ECUCValue(
                        path="Mcu/Root/IsEnabled",
                        raw="true",
                        type="BOOLEAN",
                    ),
                    op="add",
                ),
            ),
        )
        apply_template_diff(f, diff, mode=ApplyMode.APPLY)

        # 重读，验证 pv_tag 和 DEST
        doc = load_module(f, "Mcu")
        # 加载原始 XML tree 来检查 tag/DEST
        from claude_autosar.core.bsw.arxml_io import read as arxml_read

        arxml_doc = arxml_read(f)
        ns = {"ar": "http://autosar.org/schema/r4.0"}
        pv_elements = arxml_doc.tree.getroot().xpath(
            ".//ar:PARAMETER-VALUES/*[ar:DEFINITION-REF]",
            namespaces=ns,
        )
        bool_pv = None
        for pv in pv_elements:
            ref = pv.find("ar:DEFINITION-REF", namespaces=ns)
            if ref is not None and "IsEnabled" in (ref.text or ""):
                bool_pv = pv
                break
        assert bool_pv is not None, "IsEnabled param-value not found"

        # 1) tag 必须是 ECUC-NUMERICAL-PARAM-VALUE（不是 TEXTUAL）
        tag_local = etree.QName(bool_pv.tag).localname
        assert tag_local == "ECUC-NUMERICAL-PARAM-VALUE", (
            f"BOOLEAN used wrong pv_tag={tag_local!r}, "
            f"should be ECUC-NUMERICAL-PARAM-VALUE"
        )
        # 2) DEST 必须是 ECUC-NUMERICAL-PARAM-DEF（不是 BOOLEAN）
        ref = bool_pv.find("ar:DEFINITION-REF", namespaces=ns)
        dest = ref.get("DEST")
        assert dest == "ECUC-NUMERICAL-PARAM-DEF", (
            f"BOOLEAN used wrong DEST={dest!r}, should be ECUC-NUMERICAL-PARAM-DEF"
        )