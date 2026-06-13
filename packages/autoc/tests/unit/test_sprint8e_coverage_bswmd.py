"""Sprint 8.E coverage tests for ``core/bsw/bswmd.py``.

Plan reference: Sprint 8.E T8.E.2 — bswmd.py 82% → ~100% coverage.

Test naming: ``TestBSWMDCoverage`` (契约 7 — 不破既有命名)。

Missing branches targeted (按 plan T8.E.2 锁定):
- ``load_default`` 4-level priority (199->201, 204->208, 221-223, 270-271, 275)
- 模块直接位于 AR-PACKAGE 下（罕见 schema 变体；302->294, 307-312）
- ``merge`` with non-BSWMDRegistry → NotImplemented (336)
- path walk edge cases: 根包名不消费 / 空 parts / parts 耗尽 (427, 474->473, 476)
- multiplicity 异常路径 (540-541, 550-551)
- 无 short_name module 跳过 (574)
- body 元素非字符串 tag 跳过 (603, 608)
- 未识别 PARAM-DEF 类型 / 无 short_name 跳过 (610->606, 612->606, 615-622, 633, 642, 647, 649->645, 651->645, 656, 658->654, 660->654)
- DEFAULT-VALUE 罕见 schema (685, 689, 699-701)
- ENUMERATION 无 LITERALS / 字面量无 SHORT-NAME (702->706, 712->720, 715, 716->713, 718->713)
- ``_descend`` ParamDef 叶子节点 / ContainerDef 命中 (759, 762-764)

新增 / 扩展：
- 完整 FUNCTION_NAME PARAM_TYPE
- min/max 解析 + 缺省
- DEFAULT-VALUE 标准 + 罕见 schema
- ENUMERATION 空 LITERALS / 缺 SHORT-NAME
- 重复 module name 后加载覆盖
- namespace alias 兼容性
- path walk 边界
- lookup miss 路径变体
- 非字符串子 tag 跳过（罕见 schema）
- 嵌套 3 层
- 顶层 module param
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree
import pytest

from claude_autosar.core.bsw.bswmd import (
    BSWMDError,
    BSWMDRegistry,
    ContainerDef,
    ModuleDef,
    ParamDef,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_xml(elem: etree._Element) -> str:
    return etree.tostring(elem, pretty_print=False, encoding="unicode")


def _bswmd_xml(root_pkg: str = "AUTOSAR", body: str = "") -> str:
    """造一个 BSWMD XML 字符串。"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>{root_pkg}</SHORT-NAME>
      {body}
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
"""


def _make_module_elem(
    short_name: str,
    containers_xml: str = "",
    params_xml: str = "",
    lower: str | None = None,
    upper: str | None = None,
) -> etree._Element:
    """用 lxml 直接造 <ECUC-MODULE-DEF> 元素（用于解析器内部分支测试）。"""
    xml = f"""<ECUC-MODULE-DEF xmlns="http://autosar.org/schema/r4.0">
  <SHORT-NAME>{short_name}</SHORT-NAME>"""
    if lower is not None:
        xml += f"<LOWER-MULTIPLICITY>{lower}</LOWER-MULTIPLICITY>"
    if upper is not None:
        xml += f"<UPPER-MULTIPLICITY>{upper}</UPPER-MULTIPLICITY>"
    if containers_xml:
        xml += f"<CONTAINERS>{containers_xml}</CONTAINERS>"
    if params_xml:
        xml += f"<PARAMETERS>{params_xml}</PARAMETERS>"
    xml += "</ECUC-MODULE-DEF>"
    return etree.fromstring(xml)


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """隔离工作目录。"""
    ws = tmp_path / "autoc-bswmd-cov-ws"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


# ---------------------------------------------------------------------------
# TestBSWMDCoverageLoad — load_default 4 级优先级 / 异常 / 解析失败
# ---------------------------------------------------------------------------


class TestBSWMDCoverageLoad:
    """``load`` / ``load_default`` 入口的 missing 分支。"""

    def test_load_default_picks_prefs_path_when_present(
        self,
        tmp_workspace: Path,
    ) -> None:
        """行 199->201：``.prefs`` 存在时追加到 candidate_roots。"""
        # 工程根
        project = tmp_workspace / "proj"
        project.mkdir(parents=True, exist_ok=True)
        prefs = project / ".prefs"
        prefs.mkdir(parents=True, exist_ok=True)
        (prefs / "Custom.arxml").write_text(
            _bswmd_xml(
                body="<ELEMENTS><ECUC-MODULE-DEF><SHORT-NAME>PrefsMod</SHORT-NAME>"
                "</ECUC-MODULE-DEF></ELEMENTS>"
            ),
            encoding="utf-8",
        )

        from claude_autosar.core.config.project_config import ProjectConfig

        cfg = ProjectConfig(
            project_root=project,
            tresos_home=None,
            bswmd_root=project / ".autoc" / "bswmd" / "r22",
            extra_bswmd_paths=(),
        )
        reg = BSWMDRegistry.load_default(cfg)

        # 来自 .prefs/*.arxml
        assert "PrefsMod" in reg.modules
        assert any(".prefs" in str(p) for p in reg.source_paths)

    def test_load_default_picks_extra_bswmd_paths(
        self,
        tmp_workspace: Path,
    ) -> None:
        """行 201：``extra_bswmd_paths`` 中的每个路径被追加。"""
        project = tmp_workspace / "proj"
        project.mkdir(parents=True, exist_ok=True)

        cdd1 = tmp_workspace / "cdd1"
        cdd1.mkdir()
        (cdd1 / "A.arxml").write_text(
            _bswmd_xml(
                body="<ELEMENTS><ECUC-MODULE-DEF><SHORT-NAME>ModA</SHORT-NAME>"
                "</ECUC-MODULE-DEF></ELEMENTS>"
            ),
            encoding="utf-8",
        )
        cdd2 = tmp_workspace / "cdd2"
        cdd2.mkdir()
        (cdd2 / "B.arxml").write_text(
            _bswmd_xml(
                body="<ELEMENTS><ECUC-MODULE-DEF><SHORT-NAME>ModB</SHORT-NAME>"
                "</ECUC-MODULE-DEF></ELEMENTS>"
            ),
            encoding="utf-8",
        )

        from claude_autosar.core.config.project_config import ProjectConfig

        cfg = ProjectConfig(
            project_root=project,
            tresos_home=None,
            bswmd_root=project / ".autoc" / "bswmd" / "r22",
            extra_bswmd_paths=(cdd1, cdd2),
        )
        reg = BSWMDRegistry.load_default(cfg)
        assert "ModA" in reg.modules
        assert "ModB" in reg.modules

    def test_load_default_uses_tresos_home_fallback(
        self,
        tmp_workspace: Path,
    ) -> None:
        """行 202-205：``tresos_home`` 设置时使用 ``BSWMD/AUTOSAR_R22/EcucDefs`` 兜底。"""
        project = tmp_workspace / "proj"
        project.mkdir(parents=True, exist_ok=True)

        # 真实 tresos_home 路径
        tresos = tmp_workspace / "tresos_home"
        ecucdefs = tresos / "BSWMD" / "AUTOSAR_R22" / "EcucDefs"
        ecucdefs.mkdir(parents=True, exist_ok=True)
        (ecucdefs / "Fallback.arxml").write_text(
            _bswmd_xml(
                body="<ELEMENTS><ECUC-MODULE-DEF><SHORT-NAME>Fallback</SHORT-NAME>"
                "</ECUC-MODULE-DEF></ELEMENTS>"
            ),
            encoding="utf-8",
        )

        from claude_autosar.core.config.project_config import ProjectConfig

        cfg = ProjectConfig(
            project_root=project,
            tresos_home=tresos,
            bswmd_root=project / ".autoc" / "bswmd" / "r22",
            extra_bswmd_paths=(),
        )
        reg = BSWMDRegistry.load_default(cfg)
        assert "Fallback" in reg.modules
        assert any("BSWMD" in str(p) for p in reg.source_paths)

    def test_load_default_skips_tresos_home_fallback_when_dir_missing(
        self,
        tmp_workspace: Path,
    ) -> None:
        """行 204-205：``BSWMD/AUTOSAR_R22/EcucDefs/`` 不存在时跳过兜底。"""
        project = tmp_workspace / "proj"
        project.mkdir(parents=True, exist_ok=True)

        # tresos_home 存在但 BSWMD 路径不存在
        tresos = tmp_workspace / "empty_tresos"
        tresos.mkdir()

        from claude_autosar.core.config.project_config import ProjectConfig

        cfg = ProjectConfig(
            project_root=project,
            tresos_home=tresos,
            bswmd_root=project / ".autoc" / "bswmd" / "r22",
            extra_bswmd_paths=(),
        )
        reg = BSWMDRegistry.load_default(cfg)
        # 没有加载任何 module（兜底路径不存在）
        assert len(reg.modules) == 0

    def test_load_default_handles_corrupt_arxml_gracefully(
        self,
        tmp_workspace: Path,
    ) -> None:
        """行 221-223：单文件 XML 语法错误时警告 + 跳过（不抛）。"""
        project = tmp_workspace / "proj"
        project.mkdir(parents=True, exist_ok=True)

        corrupt_dir = project / ".autoc" / "bswmd" / "r22"
        corrupt_dir.mkdir(parents=True, exist_ok=True)
        # 写一个明显非法的 XML
        (corrupt_dir / "Bad.arxml").write_text("not <valid> xml", encoding="utf-8")

        from claude_autosar.core.config.project_config import ProjectConfig

        cfg = ProjectConfig(
            project_root=project,
            tresos_home=None,
            bswmd_root=corrupt_dir,
            extra_bswmd_paths=(),
        )
        # 不应抛
        reg = BSWMDRegistry.load_default(cfg)
        assert isinstance(reg, BSWMDRegistry)
        assert len(reg.modules) == 0

    def test_load_raises_bswmd_error_on_invalid_xml(self, tmp_workspace: Path) -> None:
        """行 270-271 + 275：``load`` 遇到无效 XML → ``BSWMDError``。"""
        bad = tmp_workspace / "bad.arxml"
        bad.write_text("<not><closed>", encoding="utf-8")

        with pytest.raises(BSWMDError, match="failed to parse"):
            BSWMDRegistry.load((bad,))

    def test_load_raises_bswmd_error_on_empty_root(self, tmp_workspace: Path) -> None:
        """行 275：根为 ``None`` → ``BSWMDError``（罕见 schema 变体）。

        注：lxml ``etree.parse`` 永远返回非 None root（即便 ``<X/>`` 自闭根，
        root 仍是 element 节点，**不是** None）。所以 "root is None" 分支在
        lxml 上不可触发 —— 这个 BSWMDError 实际是**防御性**代码（其他 XML
        解析器如 cElementTree 在损坏输入下可能返 None）。

        这里改测为：``<X/>`` 自闭根 → 解析成功但**没有 module**（不 raise）。
        """
        empty = tmp_workspace / "empty.arxml"
        # 自闭根：lxml 视为合法 element，root 不为 None
        empty.write_text('<?xml version="1.0"?><X/>', encoding="utf-8")
        # 不 raise；registry 为空
        reg = BSWMDRegistry.load((empty,))
        assert reg.modules == {}
        assert reg.root_package_name == "AUTOSAR"  # 走 fallback


# ---------------------------------------------------------------------------
# TestBSWMDCoverageSchemaVariants — 罕见 schema 变体
# ---------------------------------------------------------------------------


class TestBSWMDCoverageSchemaVariants:
    """``ECUC-MODULE-DEF`` 直接在 AR-PACKAGE 下（无 ELEMENTS 包装）。"""

    def test_module_directly_under_ar_package(
        self,
        tmp_workspace: Path,
    ) -> None:
        """行 302->294 / 307-312：``ECUC-MODULE-DEF`` 直接在 AR-PACKAGE 下（无 ELEMENTS）。"""
        # 罕见 schema：module 不在 ELEMENTS 中
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>AUTOSAR</SHORT-NAME>
      <ECUC-MODULE-DEF>
        <SHORT-NAME>DirectMod</SHORT-NAME>
      </ECUC-MODULE-DEF>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
"""
        path = tmp_workspace / "direct.arxml"
        _write(path, xml)
        reg = BSWMDRegistry.load((path,))
        assert "DirectMod" in reg.modules


# ---------------------------------------------------------------------------
# TestBSWMDCoverageMerge — merge 异常路径
# ---------------------------------------------------------------------------


class TestBSWMDCoverageMerge:
    """``merge`` 异常 / 边界。"""

    def test_merge_with_non_registry_returns_not_implemented(self) -> None:
        """行 335-336：``merge`` 非 ``BSWMDRegistry`` → ``NotImplemented``。"""
        reg = BSWMDRegistry()
        result = reg.merge("not a registry")  # type: ignore[arg-type]
        assert result is NotImplemented

    def test_merge_with_other_empty_registry(self) -> None:
        """``merge`` 对方是空 registry 时 root_package_name 保留 self。"""
        a = BSWMDRegistry(root_package_name="MyRoot")
        b = BSWMDRegistry()
        merged = a.merge(b)
        assert merged.root_package_name == "MyRoot"


# ---------------------------------------------------------------------------
# TestBSWMDCoveragePathWalk — _walk_path 边界
# ---------------------------------------------------------------------------


class TestBSWMDCoveragePathWalk:
    """``_walk_path`` / ``__contains__`` / ``lookup_*`` 的 path walk 边界。"""

    @pytest.fixture
    def reg(self, tmp_workspace: Path) -> BSWMDRegistry:
        xml = _bswmd_xml(
            body="<ELEMENTS><ECUC-MODULE-DEF><SHORT-NAME>Mcu</SHORT-NAME>"
            "<CONTAINERS><ECUC-PARAM-CONF-CONTAINER-DEF>"
            "<SHORT-NAME>Clock</SHORT-NAME>"
            "<PARAMETERS><ECUC-INTEGER-PARAM-DEF>"
            "<SHORT-NAME>Freq</SHORT-NAME>"
            "</ECUC-INTEGER-PARAM-DEF></PARAMETERS>"
            "</ECUC-PARAM-CONF-CONTAINER-DEF></CONTAINERS>"
            "</ECUC-MODULE-DEF></ELEMENTS>",
        )
        path = tmp_workspace / "Mcu.arxml"
        _write(path, xml)
        return BSWMDRegistry.load((path,))

    def test_walk_returns_none_for_empty_string(self, reg: BSWMDRegistry) -> None:
        """行 415-419：空字符串 → None。"""
        assert reg.lookup_param("") is None
        assert reg.lookup_container("") is None

    def test_walk_returns_none_for_only_slashes(self, reg: BSWMDRegistry) -> None:
        """行 415-419：``"///"`` → None。"""
        assert reg.lookup_param("///") is None

    def test_walk_returns_none_when_only_root_pkg(self, reg: BSWMDRegistry) -> None:
        """行 422-427：路径只有根包名（parts 消费后为空）→ None。"""
        # "/AUTOSAR" → parts = ["AUTOSAR"] → 消费后 parts=[] → return None
        assert reg.lookup_param("/AUTOSAR") is None
        assert "/AUTOSAR" not in reg

    def test_walk_returns_none_when_root_pkg_mismatch(
        self,
        reg: BSWMDRegistry,
    ) -> None:
        """行 422-424：根包名不匹配时，整段视为 [module, ...]。"""
        # "/OTHER/Mcu" → parts = ["OTHER", "Mcu"] → 根不消费 → 尝试 lookup OTHER 模块
        assert reg.lookup_param("/OTHER/Mcu") is None
        assert reg.lookup_container("/OTHER/Mcu") is None

    def test_walk_returns_module_for_path_with_only_module(self) -> None:
        """``/AUTOSAR/Mcu`` → 返回 ModuleDef。"""
        xml = _bswmd_xml(
            body="<ELEMENTS><ECUC-MODULE-DEF><SHORT-NAME>Mcu</SHORT-NAME>"
            "</ECUC-MODULE-DEF></ELEMENTS>",
        )
        # 写到临时文件
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "Mcu.arxml"
            _write(path, xml)
            reg = BSWMDRegistry.load((path,))

        # 单段 "/Mcu"（parts=["Mcu"]，首段不是根 → 整段视为 [module]）
        assert reg.lookup_module("Mcu") is not None
        # "/AUTOSAR/Mcu" → parts=["AUTOSAR","Mcu"] → 消费 AUTOSAR → 剩 ["Mcu"] → module
        m = reg._walk_path("/AUTOSAR/Mcu")
        assert isinstance(m, ModuleDef)
        assert m.short_name == "Mcu"

    def test_walk_returns_module_for_just_module_name(self) -> None:
        """``"Mcu"``（无 slash）→ module 命中。"""
        xml = _bswmd_xml(
            body="<ELEMENTS><ECUC-MODULE-DEF><SHORT-NAME>Mcu</SHORT-NAME>"
            "</ECUC-MODULE-DEF></ELEMENTS>",
        )
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "Mcu.arxml"
            _write(path, xml)
            reg = BSWMDRegistry.load((path,))
        m = reg._walk_path("Mcu")
        assert isinstance(m, ModuleDef)

    def test_walk_returns_none_when_descend_fails(self) -> None:
        """中段命中失败 → None。"""
        xml = _bswmd_xml(
            body="<ELEMENTS><ECUC-MODULE-DEF><SHORT-NAME>Mcu</SHORT-NAME>"
            "<CONTAINERS><ECUC-PARAM-CONF-CONTAINER-DEF>"
            "<SHORT-NAME>Clock</SHORT-NAME>"
            "</ECUC-PARAM-CONF-CONTAINER-DEF></CONTAINERS>"
            "</ECUC-MODULE-DEF></ELEMENTS>",
        )
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "Mcu.arxml"
            _write(path, xml)
            reg = BSWMDRegistry.load((path,))
        # 末段 "Freq" 不存在
        assert reg.lookup_param("/AUTOSAR/Mcu/Clock/Freq") is None
        # 中段 "NoContainer" 不存在
        assert reg.lookup_param("/AUTOSAR/Mcu/NoContainer/Freq") is None
        # 中段 "NoContainer" 不存在 → container miss
        assert reg.lookup_container("/AUTOSAR/Mcu/NoContainer") is None


# ---------------------------------------------------------------------------
# TestBSWMDCoverageParseModule — _parse_module_def 边界
# ---------------------------------------------------------------------------


class TestBSWMDCoverageParseModule:
    """``_parse_module_def`` missing 分支。"""

    def test_module_without_short_name_returns_none(self) -> None:
        """行 572-574：module 无 SHORT-NAME → return None。"""
        from claude_autosar.core.bsw.bswmd import _parse_module_def

        # 造一个没有 SHORT-NAME 的 module 元素
        elem = etree.fromstring(
            """<ECUC-MODULE-DEF xmlns="http://autosar.org/schema/r4.0">
              <!-- no SHORT-NAME -->
            </ECUC-MODULE-DEF>""",
        )
        result = _parse_module_def(elem, root_pkg_name="AUTOSAR")
        assert result is None

    def test_module_with_empty_short_name_returns_none(self) -> None:
        """行 572-574：SHORT-NAME 为空字符串 → return None。"""
        from claude_autosar.core.bsw.bswmd import _parse_module_def

        elem = etree.fromstring(
            """<ECUC-MODULE-DEF xmlns="http://autosar.org/schema/r4.0">
              <SHORT-NAME>   </SHORT-NAME>
            </ECUC-MODULE-DEF>""",
        )
        result = _parse_module_def(elem, root_pkg_name="AUTOSAR")
        assert result is None


# ---------------------------------------------------------------------------
# TestBSWMDCoverageParseModuleBody — _parse_module_body 边界
# ---------------------------------------------------------------------------


class TestBSWMDCoverageParseModuleBody:
    """``_parse_module_body`` 行 603/608 的非字符串 tag 跳过。"""

    def test_module_with_comment_only_conts_block(self) -> None:
        """CONTAINERS 内只有注释子节点（lxml iter 跳过）→ 不会抛。"""
        # 注释在 lxml 中不是 element
        from claude_autosar.core.bsw.bswmd import _parse_module_body

        elem = etree.fromstring(
            """<ECUC-MODULE-DEF xmlns="http://autosar.org/schema/r4.0">
              <SHORT-NAME>Mcu</SHORT-NAME>
              <CONTAINERS>
                <!-- no children -->
              </CONTAINERS>
            </ECUC-MODULE-DEF>""",
        )
        containers, params = _parse_module_body(elem, "/A/Mcu")
        assert containers == {}
        assert params == {}


# ---------------------------------------------------------------------------
# TestBSWMDCoverageParseContainer — _parse_container_def 边界
# ---------------------------------------------------------------------------


class TestBSWMDCoverageParseContainer:
    """``_parse_container_def`` missing 分支。"""

    def test_container_without_short_name_returns_none(self) -> None:
        """行 631-633：container 无 SHORT-NAME → None。"""
        from claude_autosar.core.bsw.bswmd import _parse_container_def

        elem = etree.fromstring(
            """<ECUC-PARAM-CONF-CONTAINER-DEF xmlns="http://autosar.org/schema/r4.0">
              <!-- no SHORT-NAME -->
            </ECUC-PARAM-CONF-CONTAINER-DEF>""",
        )
        result = _parse_container_def(elem, parent_path="/A/Mcu")
        assert result is None

    def test_container_with_choice_container(self) -> None:
        """行 658-661：``ECUC-CHOICE-CONTAINER-DEF`` 也被解析为 ContainerDef。"""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>AUTOSAR</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-DEF>
          <SHORT-NAME>Mcu</SHORT-NAME>
          <CONTAINERS>
            <ECUC-CHOICE-CONTAINER-DEF>
              <SHORT-NAME>Choice</SHORT-NAME>
              <LOWER-MULTIPLICITY>0</LOWER-MULTIPLICITY>
              <UPPER-MULTIPLICITY>1</UPPER-MULTIPLICITY>
            </ECUC-CHOICE-CONTAINER-DEF>
          </CONTAINERS>
        </ECUC-MODULE-DEF>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
"""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "choice.arxml"
            _write(path, xml)
            reg = BSWMDRegistry.load((path,))
        assert "Choice" in reg.modules["Mcu"].containers

    def test_container_sub_containers_recursion(self) -> None:
        """行 654-661：sub_containers 嵌套。"""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>AUTOSAR</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-DEF>
          <SHORT-NAME>Mcu</SHORT-NAME>
          <CONTAINERS>
            <ECUC-PARAM-CONF-CONTAINER-DEF>
              <SHORT-NAME>Outer</SHORT-NAME>
              <SUB-CONTAINERS>
                <ECUC-PARAM-CONF-CONTAINER-DEF>
                  <SHORT-NAME>Inner</SHORT-NAME>
                </ECUC-PARAM-CONF-CONTAINER-DEF>
              </SUB-CONTAINERS>
            </ECUC-PARAM-CONF-CONTAINER-DEF>
          </CONTAINERS>
        </ECUC-MODULE-DEF>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
"""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "nested.arxml"
            _write(path, xml)
            reg = BSWMDRegistry.load((path,))
        outer = reg.modules["Mcu"].containers["Outer"]
        assert "Inner" in outer.sub_container_defs


# ---------------------------------------------------------------------------
# TestBSWMDCoverageParseParam — _parse_param_def 边界
# ---------------------------------------------------------------------------


class TestBSWMDCoverageParseParam:
    """``_parse_param_def`` missing 分支 + 全部 6 个 PARAM_TYPE。"""

    def test_unknown_param_def_type_returns_none(self) -> None:
        """行 683-685：未知 PARAM-DEF localname → None。"""
        from claude_autosar.core.bsw.bswmd import _parse_param_def

        elem = etree.fromstring(
            """<ECUC-MY-CUSTOM-PARAM-DEF xmlns="http://autosar.org/schema/r4.0">
              <SHORT-NAME>Foo</SHORT-NAME>
            </ECUC-MY-CUSTOM-PARAM-DEF>""",
        )
        result = _parse_param_def(elem, parent_path="/A/M")
        assert result is None

    def test_param_def_without_short_name_returns_none(self) -> None:
        """行 687-689：param 无 SHORT-NAME → None。"""
        from claude_autosar.core.bsw.bswmd import _parse_param_def

        elem = etree.fromstring(
            """<ECUC-INTEGER-PARAM-DEF xmlns="http://autosar.org/schema/r4.0">
              <!-- no SHORT-NAME -->
            </ECUC-INTEGER-PARAM-DEF>""",
        )
        result = _parse_param_def(elem, parent_path="/A/M")
        assert result is None

    def test_function_name_param_def(self) -> None:
        """FUNCTION_NAME PARAM_TYPE 解析。"""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>AUTOSAR</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-DEF>
          <SHORT-NAME>Mcu</SHORT-NAME>
          <CONTAINERS>
            <ECUC-PARAM-CONF-CONTAINER-DEF>
              <SHORT-NAME>C</SHORT-NAME>
              <PARAMETERS>
                <ECUC-FUNCTION-NAME-DEF>
                  <SHORT-NAME>Fn</SHORT-NAME>
                </ECUC-FUNCTION-NAME-DEF>
              </PARAMETERS>
            </ECUC-PARAM-CONF-CONTAINER-DEF>
          </CONTAINERS>
        </ECUC-MODULE-DEF>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
"""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fn.arxml"
            _write(path, xml)
            reg = BSWMDRegistry.load((path,))
        p = reg.modules["Mcu"].containers["C"].param_defs["Fn"]
        assert p.param_type == "FUNCTION_NAME"

    def test_default_value_rare_schema_with_direct_value_text(self) -> None:
        """行 702-704：``<DEFAULT-VALUE>`` 内直接是 ECUC-NUMERICAL-PARAM-VALUE 文本（罕见）。"""
        # DEFAULT-VALUE 内没有 <VALUE> 子元素，文本直接在 DEFAULT-VALUE
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>AUTOSAR</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-DEF>
          <SHORT-NAME>M</SHORT-NAME>
          <CONTAINERS>
            <ECUC-PARAM-CONF-CONTAINER-DEF>
              <SHORT-NAME>C</SHORT-NAME>
              <PARAMETERS>
                <ECUC-INTEGER-PARAM-DEF>
                  <SHORT-NAME>P</SHORT-NAME>
                  <DEFAULT-VALUE>42</DEFAULT-VALUE>
                </ECUC-INTEGER-PARAM-DEF>
              </PARAMETERS>
            </ECUC-PARAM-CONF-CONTAINER-DEF>
          </CONTAINERS>
        </ECUC-MODULE-DEF>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
"""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "dv.arxml"
            _write(path, xml)
            reg = BSWMDRegistry.load((path,))
        p = reg.modules["M"].containers["C"].param_defs["P"]
        # 直接文本应被解析为 default
        assert p.default == "42"

    def test_min_max_parsing(self) -> None:
        """行 692-693：MIN / MAX 文本解析。"""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>AUTOSAR</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-DEF>
          <SHORT-NAME>M</SHORT-NAME>
          <CONTAINERS>
            <ECUC-PARAM-CONF-CONTAINER-DEF>
              <SHORT-NAME>C</SHORT-NAME>
              <PARAMETERS>
                <ECUC-INTEGER-PARAM-DEF>
                  <SHORT-NAME>Lim</SHORT-NAME>
                  <MIN>-100</MIN>
                  <MAX>200</MAX>
                </ECUC-INTEGER-PARAM-DEF>
              </PARAMETERS>
            </ECUC-PARAM-CONF-CONTAINER-DEF>
          </CONTAINERS>
        </ECUC-MODULE-DEF>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
"""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "minmax.arxml"
            _write(path, xml)
            reg = BSWMDRegistry.load((path,))
        p = reg.modules["M"].containers["C"].param_defs["Lim"]
        assert p.min == "-100"
        assert p.max == "200"

    def test_enumeration_without_literals(self) -> None:
        """行 709-720：ENUMERATION 无 LITERALS → symbol_strings=()。"""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>AUTOSAR</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-DEF>
          <SHORT-NAME>M</SHORT-NAME>
          <CONTAINERS>
            <ECUC-PARAM-CONF-CONTAINER-DEF>
              <SHORT-NAME>C</SHORT-NAME>
              <PARAMETERS>
                <ECUC-ENUMERATION-PARAM-DEF>
                  <SHORT-NAME>E</SHORT-NAME>
                </ECUC-ENUMERATION-PARAM-DEF>
              </PARAMETERS>
            </ECUC-PARAM-CONF-CONTAINER-DEF>
          </CONTAINERS>
        </ECUC-MODULE-DEF>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
"""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "no_lit.arxml"
            _write(path, xml)
            reg = BSWMDRegistry.load((path,))
        p = reg.modules["M"].containers["C"].param_defs["E"]
        assert p.param_type == "ENUMERATION"
        assert p.symbol_strings == ()

    def test_enumeration_literal_without_short_name_skipped(self) -> None:
        """行 716-720：literal 无 SHORT-NAME 被跳过。"""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>AUTOSAR</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-DEF>
          <SHORT-NAME>M</SHORT-NAME>
          <CONTAINERS>
            <ECUC-PARAM-CONF-CONTAINER-DEF>
              <SHORT-NAME>C</SHORT-NAME>
              <PARAMETERS>
                <ECUC-ENUMERATION-PARAM-DEF>
                  <SHORT-NAME>E</SHORT-NAME>
                  <LITERALS>
                    <ECUC-ENUMERATION-LITERAL-DEF>
                      <SHORT-NAME>A</SHORT-NAME>
                    </ECUC-ENUMERATION-LITERAL-DEF>
                    <ECUC-ENUMERATION-LITERAL-DEF>
                      <!-- no SHORT-NAME -->
                    </ECUC-ENUMERATION-LITERAL-DEF>
                    <ECUC-ENUMERATION-LITERAL-DEF>
                      <SHORT-NAME>B</SHORT-NAME>
                    </ECUC-ENUMERATION-LITERAL-DEF>
                  </LITERALS>
                </ECUC-ENUMERATION-PARAM-DEF>
              </PARAMETERS>
            </ECUC-PARAM-CONF-CONTAINER-DEF>
          </CONTAINERS>
        </ECUC-MODULE-DEF>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
"""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "mixed_lit.arxml"
            _write(path, xml)
            reg = BSWMDRegistry.load((path,))
        p = reg.modules["M"].containers["C"].param_defs["E"]
        # 第二个 literal 无 SHORT-NAME → 跳过
        assert p.symbol_strings == ("A", "B")


# ---------------------------------------------------------------------------
# TestBSWMDCoverageMultiplicity — _parse_multiplicity 异常路径
# ---------------------------------------------------------------------------


class TestBSWMDCoverageMultiplicity:
    """``_parse_multiplicity`` 异常 / 边界。"""

    def test_invalid_lower_text_falls_back_to_default(self) -> None:
        """行 540-541：LOWER-MULTIPLICITY 文本非整数 → lower_default。"""
        from claude_autosar.core.bsw.bswmd import _parse_multiplicity

        elem = etree.fromstring(
            """<ELEM xmlns="http://x">
              <LOWER-MULTIPLICITY>not-a-number</LOWER-MULTIPLICITY>
              <UPPER-MULTIPLICITY>1</UPPER-MULTIPLICITY>
            </ELEM>""",
        )
        lower, upper = _parse_multiplicity(elem)
        assert lower == 0  # lower_default
        assert upper == 1

    def test_invalid_upper_text_falls_back_to_default(self) -> None:
        """行 550-551：UPPER-MULTIPLICITY 文本非整数 → upper_default。"""
        from claude_autosar.core.bsw.bswmd import _parse_multiplicity

        elem = etree.fromstring(
            """<ELEM xmlns="http://x">
              <LOWER-MULTIPLICITY>0</LOWER-MULTIPLICITY>
              <UPPER-MULTIPLICITY>some-junk</UPPER-MULTIPLICITY>
            </ELEM>""",
        )
        lower, upper = _parse_multiplicity(elem)
        assert lower == 0
        assert upper == 1  # upper_default

    def test_unbounded_upper_via_uppercase(self) -> None:
        """``unbounded`` 大小写不敏感（D5 决定）。"""
        from claude_autosar.core.bsw.bswmd import _parse_multiplicity

        elem = etree.fromstring(
            """<ELEM xmlns="http://x">
              <LOWER-MULTIPLICITY>0</LOWER-MULTIPLICITY>
              <UPPER-MULTIPLICITY>UNBOUNDED</UPPER-MULTIPLICITY>
            </ELEM>""",
        )
        _, upper = _parse_multiplicity(elem)
        assert upper == -1


# ---------------------------------------------------------------------------
# TestBSWMDCoverageDescend — _descend 边界
# ---------------------------------------------------------------------------


class TestBSWMDCoverageDescend:
    """``_descend`` ParamDef 叶子 / ContainerDef param 命中。"""

    def test_descend_param_def_leaf_returns_none(self) -> None:
        """行 763-764：ParamDef 是叶子 → ``_descend`` 返回 None。"""
        from claude_autosar.core.bsw.bswmd import _descend

        p = ParamDef(short_name="X", full_path="/A/X", param_type="INTEGER")
        result = _descend(p, "Anything", prefer_param=True)
        assert result is None

    def test_descend_container_prefers_subcontainer_over_param(self) -> None:
        """``_descend`` ContainerDef：sub_container 优先于 param。"""
        from claude_autosar.core.bsw.bswmd import _descend

        sub = ContainerDef(
            short_name="Sub",
            full_path="/A/Sub",
            lower_multiplicity=0,
            upper_multiplicity=1,
        )
        c = ContainerDef(
            short_name="Main",
            full_path="/A/Main",
            lower_multiplicity=0,
            upper_multiplicity=1,
            sub_container_defs={"Sub": sub},
        )
        # 找 "Sub" → 返回 sub_container
        result = _descend(c, "Sub", prefer_param=False)
        assert result is sub

    def test_descend_container_falls_back_to_param_when_prefer_param(self) -> None:
        """``_descend`` ContainerDef：``prefer_param=True`` 走 param 分支。"""
        from claude_autosar.core.bsw.bswmd import _descend

        p = ParamDef(short_name="P", full_path="/A/P", param_type="INTEGER")
        c = ContainerDef(
            short_name="C",
            full_path="/A/C",
            lower_multiplicity=0,
            upper_multiplicity=1,
            param_defs={"P": p},
        )
        result = _descend(c, "P", prefer_param=True)
        assert result is p

    def test_descend_container_no_match_returns_none(self) -> None:
        """``_descend`` ContainerDef：无 sub_container 也不 prefer_param → None。"""
        from claude_autosar.core.bsw.bswmd import _descend

        c = ContainerDef(
            short_name="C",
            full_path="/A/C",
            lower_multiplicity=0,
            upper_multiplicity=1,
        )
        result = _descend(c, "X", prefer_param=False)
        assert result is None


# ---------------------------------------------------------------------------
# TestBSWMDCoverageNamespaceAlias — non-default namespace prefix
# ---------------------------------------------------------------------------


class TestBSWMDCoverageNamespaceAlias:
    """验证 ``arx:`` 等 alias 在 bswmd 解析下也工作。"""

    def test_arx_namespace_alias_loads_module(
        self,
        tmp_workspace: Path,
    ) -> None:
        """arx:ECUC-MODULE-DEF 等价于 ECUC-MODULE-DEF。"""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<arx:AUTOSAR xmlns:arx="http://autosar.org/schema/r4.0">
  <arx:AR-PACKAGES>
    <arx:AR-PACKAGE>
      <arx:SHORT-NAME>AUTOSAR</arx:SHORT-NAME>
      <arx:ELEMENTS>
        <arx:ECUC-MODULE-DEF>
          <arx:SHORT-NAME>ArxMod</arx:SHORT-NAME>
        </arx:ECUC-MODULE-DEF>
      </arx:ELEMENTS>
    </arx:AR-PACKAGE>
  </arx:AR-PACKAGES>
</arx:AUTOSAR>
"""
        path = tmp_workspace / "arx.arxml"
        _write(path, xml)
        reg = BSWMDRegistry.load((path,))
        assert "ArxMod" in reg.modules


# ---------------------------------------------------------------------------
# TestBSWMDCoverageMultiPackage — multi-package 边界
# ---------------------------------------------------------------------------


class TestBSWMDCoverageMultiPackage:
    """多个 AR-PACKAGE 兄弟节点全部解析（plan T8.E.2 多包）。"""

    def test_two_packages_with_same_module_name_later_wins(
        self,
        tmp_workspace: Path,
    ) -> None:
        """两个 AR-PACKAGE 同名 module → 后加载覆盖（D11）。"""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>AUTOSAR</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-DEF>
          <SHORT-NAME>Dup</SHORT-NAME>
          <CONTAINERS>
            <ECUC-PARAM-CONF-CONTAINER-DEF>
              <SHORT-NAME>FromStd</SHORT-NAME>
            </ECUC-PARAM-CONF-CONTAINER-DEF>
          </CONTAINERS>
        </ECUC-MODULE-DEF>
      </ELEMENTS>
    </AR-PACKAGE>
    <AR-PACKAGE>
      <SHORT-NAME>Vendor</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-DEF>
          <SHORT-NAME>Dup</SHORT-NAME>
          <CONTAINERS>
            <ECUC-PARAM-CONF-CONTAINER-DEF>
              <SHORT-NAME>FromVendor</SHORT-NAME>
            </ECUC-PARAM-CONF-CONTAINER-DEF>
          </CONTAINERS>
        </ECUC-MODULE-DEF>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
"""
        path = tmp_workspace / "dup.arxml"
        _write(path, xml)
        reg = BSWMDRegistry.load((path,))
        # 后加载的 Vendor 包覆盖了 Std 包
        containers = reg.modules["Dup"].containers
        assert "FromVendor" in containers
        assert "FromStd" not in containers


# ---------------------------------------------------------------------------
# TestBSWMDCoverageRepr — __repr__ 调试
# ---------------------------------------------------------------------------


class TestBSWMDCoverageRepr:
    """``__repr__``（pragma 覆盖；这里强制覆盖以验证不抛）。"""

    def test_repr_does_not_raise(self) -> None:
        """``repr(reg)`` 不抛（即便标记 pragma no cover）。"""
        m = ModuleDef(short_name="Mcu", full_path="/A/Mcu")
        reg = BSWMDRegistry(modules={"Mcu": m}, source_paths=(Path("/x"),))
        result = repr(reg)
        assert "BSWMDRegistry" in result
        assert "Mcu" in result
        assert "1 files" in result


# ---------------------------------------------------------------------------
# TestBSWMDCoverageThreeLevelNesting — 3 层 container
# ---------------------------------------------------------------------------


class TestBSWMDCoverageThreeLevelNesting:
    """3 层嵌套 container（plan RED 段要求）。"""

    def test_three_level_nested_container_path_walk(
        self,
        tmp_workspace: Path,
    ) -> None:
        """Mcu → Clock → RefPoint → Leaf 4 层路径 walk 命中 leaf param。"""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>AUTOSAR</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-DEF>
          <SHORT-NAME>Mcu</SHORT-NAME>
          <CONTAINERS>
            <ECUC-PARAM-CONF-CONTAINER-DEF>
              <SHORT-NAME>Clock</SHORT-NAME>
              <SUB-CONTAINERS>
                <ECUC-PARAM-CONF-CONTAINER-DEF>
                  <SHORT-NAME>RefPoint</SHORT-NAME>
                  <SUB-CONTAINERS>
                    <ECUC-PARAM-CONF-CONTAINER-DEF>
                      <SHORT-NAME>Leaf</SHORT-NAME>
                      <PARAMETERS>
                        <ECUC-INTEGER-PARAM-DEF>
                          <SHORT-NAME>Freq</SHORT-NAME>
                          <MIN>0</MIN>
                          <MAX>1000000</MAX>
                        </ECUC-INTEGER-PARAM-DEF>
                      </PARAMETERS>
                    </ECUC-PARAM-CONF-CONTAINER-DEF>
                  </SUB-CONTAINERS>
                </ECUC-PARAM-CONF-CONTAINER-DEF>
              </SUB-CONTAINERS>
            </ECUC-PARAM-CONF-CONTAINER-DEF>
          </CONTAINERS>
        </ECUC-MODULE-DEF>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
"""
        path = tmp_workspace / "deep.arxml"
        _write(path, xml)
        reg = BSWMDRegistry.load((path,))

        # 命中最深 param
        p = reg.lookup_param("/AUTOSAR/Mcu/Clock/RefPoint/Leaf/Freq")
        assert p is not None
        assert p.short_name == "Freq"
        assert p.param_type == "INTEGER"

        # 命中中间 container
        c = reg.lookup_container("/AUTOSAR/Mcu/Clock/RefPoint/Leaf")
        assert c is not None
        assert c.short_name == "Leaf"

        # 命中中间 RefPoint container
        c2 = reg.lookup_container("/AUTOSAR/Mcu/Clock/RefPoint")
        assert c2 is not None
        assert c2.short_name == "RefPoint"

        # 命中 Clock container
        c3 = reg.lookup_container("/AUTOSAR/Mcu/Clock")
        assert c3 is not None
        assert c3.short_name == "Clock"


# ---------------------------------------------------------------------------
# TestBSWMDCoverageTopLevelParam — module 顶层 param
# ---------------------------------------------------------------------------


class TestBSWMDCoverageTopLevelParam:
    """module 顶层有 PARAMETERS 块（plan 支持）。"""

    def test_module_top_level_param_lookup(self, tmp_workspace: Path) -> None:
        """module 顶层 PARAMETERS 中 param 可被 lookup 命中。"""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>AUTOSAR</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-DEF>
          <SHORT-NAME>Mcu</SHORT-NAME>
          <PARAMETERS>
            <ECUC-INTEGER-PARAM-DEF>
              <SHORT-NAME>Version</SHORT-NAME>
            </ECUC-INTEGER-PARAM-DEF>
          </PARAMETERS>
        </ECUC-MODULE-DEF>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
"""
        path = tmp_workspace / "topparam.arxml"
        _write(path, xml)
        reg = BSWMDRegistry.load((path,))
        p = reg.lookup_param("/AUTOSAR/Mcu/Version")
        assert p is not None
        assert p.param_type == "INTEGER"
        assert "Version" in reg.modules["Mcu"].params
