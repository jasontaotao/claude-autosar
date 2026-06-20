"""AutoC 共享 pytest fixtures。

所有 fixture 用 ``tmp_path``（pytest 内置，自动清理）作为根，跨平台。
"""

from __future__ import annotations

from collections.abc import Iterator
import json
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _autouse_safe_project_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """把 ``tmp_path`` 加入 MCP ``_ALLOWED_PROJECT_ROOTS``，让需要 ``project=tmp_path`` 的
    测试与 ``_resolve_safe_project``（H4 防御）兼容。

    测试若想验证 *outside allowed roots* 拒绝路径，应使用绝对路径如
    ``/nonexistent_root_for_test_*`` —— 这类路径既不在 cwd 也不在 tmp_path，
    仍会被正确拒绝。

    Sprint 12 审计修复（HIGH-9）：``bsw_validate`` / ``bsw_diff`` 现在
    走 ``_resolve_safe_project`` 替 ``validate_no_traversal``，需要
    ``project`` 落在 allowed roots；旧测试用 ``project=tmp_path`` 不能直接通过，
    由本 fixture 兜底。
    """
    import claude_autosar.cli.mcp_server as srv

    roots = frozenset({Path.cwd().resolve(), tmp_path.resolve()})
    monkeypatch.setattr(srv, "_ALLOWED_PROJECT_ROOTS", roots)


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Iterator[Path]:
    """临时工作目录。"""
    workspace = tmp_path / "autoc-workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    yield workspace


@pytest.fixture
def sample_arxml(tmp_workspace: Path) -> Path:
    """最小合法 ARXML 文件：描述一个 Mcu 模块，含时钟频率参数。"""
    arxml = tmp_workspace / "EcuC.arxml"
    arxml.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>Ecuc</SHORT-NAME>
      <ELEMENTS>
        <ECUC-MODULE-CONFIGURATION-VALUES>
          <SHORT-NAME>Mcu</SHORT-NAME>
          <DEFINITION-REF DEST="ECUC-MODULE-DEF">/AUTOSAR/EcucDefs/Mcu/Mcu</DEFINITION-REF>
          <PARAMETER-VALUES>
            <ECUC-NUMERICAL-PARAM-VALUE>
              <DEFINITION-REF DEST="ECUC-INTEGER-PARAM-DEF">/AUTOSAR/EcucDefs/Mcu/Mcu/McuClockFrequency</DEFINITION-REF>
              <VALUE>80000000</VALUE>
            </ECUC-NUMERICAL-PARAM-VALUE>
          </PARAMETER-VALUES>
        </ECUC-MODULE-CONFIGURATION-VALUES>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
""",
        encoding="utf-8",
    )
    return arxml


@pytest.fixture
def sample_dbc(tmp_workspace: Path) -> Path:
    """最小 DBC 文件：描述一个 CAN 报文 Engine_Status。"""
    dbc = tmp_workspace / "example.dbc"
    dbc.write_text(
        """VERSION "1.0"

NS_ :

BS_:

BU_: ECM TCU

BO_ 100 Engine_Status: 8 ECM
 SG_ EngineSpeed : 0|16@1+ (0.1,0) [0|6553.5] "rpm" TCU
 SG_ EngineTemp  : 16|8@1+ (1,-40) [-40|215] "degC" TCU
""",
        encoding="utf-8",
    )
    return dbc


@pytest.fixture
def temp_autosar_project(
    tmp_workspace: Path,
    sample_arxml: Path,
    sample_dbc: Path,
) -> Path:
    """完整 AUTOSAR 工程结构（含 ``.project`` 标记、``Config/ECUC`` 目录）。"""
    project_dir = tmp_workspace / "bsw-project"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "Config").mkdir(exist_ok=True)
    (project_dir / "Config" / "ECUC").mkdir(exist_ok=True)
    (project_dir / "EcuC.arxml").write_bytes(sample_arxml.read_bytes())
    (project_dir / "example.dbc").write_bytes(sample_dbc.read_bytes())
    (project_dir / ".project").write_text(
        "<project><name>test-project</name></project>",
        encoding="utf-8",
    )
    return project_dir


@pytest.fixture
def sample_settings_json(tmp_workspace: Path) -> Path:
    """样例 settings.json。"""
    cfg = tmp_workspace / "settings.json"
    cfg.write_text(
        json.dumps(
            {
                "theme": "dark",
                "defaultThinkingLevel": "medium",
                "compaction": {"enabled": True, "reserveTokens": 16384},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return cfg


@pytest.fixture
def global_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """将 platformdirs 指向临时目录，返回全局 settings.json 路径。"""
    cfg_dir = tmp_path / "global_autoc"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    settings = cfg_dir / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "theme": "dark",
                "compaction": {"enabled": True, "reserveTokens": 16384},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "claude_autosar.utils.paths.user_config_dir",
        lambda *a, **kw: str(cfg_dir),
    )
    return settings


# =============================================================================
# Adapter 测试用工厂（fake tresos 安装 + fake project）
# =============================================================================


def _build_fake_tresos(
    home: Path,
    chip_id: str,
    enabled_modules: list[str],
) -> None:
    """在 ``home`` 下建一个 fake EB tresos 安装。

    结构：
        <home>/
        ├── bin/tresos_cmd.bat           (空文件，subprocess 测试用 stub 替换)
        └── plugins/Mcu_<chip_id>_bswmd.arxml
    """
    (home / "bin").mkdir(parents=True, exist_ok=True)
    (home / "bin" / "tresos_cmd.bat").write_text("@echo off\necho fake-tresos\n", encoding="utf-8")
    (home / "plugins").mkdir(parents=True, exist_ok=True)
    # 每个芯片一个 BSWMD 占位
    (home / "plugins" / f"Mcu_{chip_id}_bswmd.arxml").write_text(
        f'<?xml version="1.0"?><AR-PACKAGE><SHORT-NAME>Mcu_{chip_id}</SHORT-NAME></AR-PACKAGE>',
        encoding="utf-8",
    )
    # 其它通用 BSWMD
    (home / "plugins" / "Port_bswmd.arxml").write_text(
        '<?xml version="1.0"?><AR-PACKAGE><SHORT-NAME>Port</SHORT-NAME></AR-PACKAGE>',
        encoding="utf-8",
    )
    (home / "plugins" / "Can_bswmd.arxml").write_text(
        '<?xml version="1.0"?><AR-PACKAGE><SHORT-NAME>Can</SHORT-NAME></AR-PACKAGE>',
        encoding="utf-8",
    )

    # 模拟 enabled_modules 对应的 BSWMD
    for mod in enabled_modules:
        path = home / "plugins" / f"{mod}_bswmd.arxml"
        if not path.exists():
            path.write_text(
                f'<?xml version="1.0"?><AR-PACKAGE><SHORT-NAME>{mod}</SHORT-NAME></AR-PACKAGE>',
                encoding="utf-8",
            )


def _build_fake_project_tresos_style(
    project_dir: Path,
    target: str,
    derivate: str,
    pn: str,
    autosar_version: str,
) -> None:
    """建 EB tresos 原生风格的 .project（用 ``<tresos:property name=...>``）。"""
    project_dir.mkdir(parents=True, exist_ok=True)
    project_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<tresos:project xmlns:tresos="http://www.tresos.de/xsd/tresos_002">
  <tresos:property name="target">{target}</tresos:property>
  <tresos:property name="derivate">{derivate}</tresos:property>
  <tresos:property name="pn">{pn}</tresos:property>
  <tresos:property name="AutosarVersion">{autosar_version}</tresos:property>
</tresos:project>
"""
    (project_dir / ".project").write_text(project_xml, encoding="utf-8")


def _build_fake_project_simple_style(
    project_dir: Path,
    target: str,
    derivate: str,
    pn: str,
    autosar_version: str,
) -> None:
    """建简化风格的 .project（用 ``<target>...</target>``）。"""
    project_dir.mkdir(parents=True, exist_ok=True)
    project_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<project>
  <target>{target}</target>
  <derivate>{derivate}</derivate>
  <pn>{pn}</pn>
  <autosarVersion>{autosar_version}</autosarVersion>
</project>
"""
    (project_dir / ".project").write_text(project_xml, encoding="utf-8")


def _build_fake_project_prefs(project_dir: Path, modules: list[str]) -> None:
    """在 ``<project>/.prefs/`` 下建模块 .xdm 文件，模拟已启用模块。"""
    prefs = project_dir / ".prefs"
    prefs.mkdir(parents=True, exist_ok=True)
    for mod in modules:
        (prefs / f"{mod}_Cfg.xdm").write_text(
            f'<?xml version="1.0"?><AR-PACKAGE><SHORT-NAME>{mod}</SHORT-NAME></AR-PACKAGE>',
            encoding="utf-8",
        )


@pytest.fixture
def fake_tresos_install(tmp_path: Path) -> Path:
    """返回 fake EB tresos HOME（无芯片项目）。"""
    home = tmp_path / "tresos_home"
    return home


@pytest.fixture
def fake_s32k3_project(tmp_path: Path) -> Path:
    """S32K3 风格工程 fixture（含 .project + .prefs + 配对 fake tresos home）。

    返回 ``(project_path, tresos_home_path)`` 元组——测试直接拿 home，
    无需自己猜路径。
    """
    project = tmp_path / "s32k3_proj"
    _build_fake_project_tresos_style(
        project,
        target="ARM",
        derivate="S32K344",
        pn="S32K344",
        autosar_version="4.4.0",
    )
    _build_fake_project_prefs(project, ["Mcu", "Port", "Dio", "Can"])
    home = tmp_path / "tresos_home_s32k3"
    _build_fake_tresos(home, chip_id="S32K3", enabled_modules=["Mcu", "Port", "Dio", "Can"])
    return project, home


@pytest.fixture
def fake_tc3xx_project(tmp_path: Path) -> Path:
    """TC3xx 风格工程 fixture。返回 ``(project_path, tresos_home_path)``。"""
    project = tmp_path / "tc3xx_proj"
    _build_fake_project_tresos_style(
        project,
        target="TC38XQ",
        derivate="TC38XQ",
        pn="TC38XQ",
        autosar_version="4.2.2",
    )
    _build_fake_project_prefs(project, ["Mcu", "Port", "Spi", "Adc"])
    home = tmp_path / "tresos_home_tc3xx"
    _build_fake_tresos(home, chip_id="TC3", enabled_modules=["Mcu", "Port", "Spi", "Adc"])
    return project, home


@pytest.fixture
def fake_rh850_project(tmp_path: Path) -> Path:
    """RH850 风格工程 fixture（用简化 schema）。返回 ``(project_path, tresos_home_path)``。"""
    project = tmp_path / "rh850_proj"
    _build_fake_project_simple_style(
        project,
        target="RH850",
        derivate="R7F701Z3",
        pn="R7F701Z3",
        autosar_version="4.0.3",
    )
    _build_fake_project_prefs(project, ["Mcu", "Port"])
    home = tmp_path / "tresos_home_rh850"
    _build_fake_tresos(home, chip_id="RH850", enabled_modules=["Mcu", "Port"])
    return project, home


@pytest.fixture
def fake_tc3xx_tresos_home(fake_tc3xx_project: Path) -> Path:
    """配对 TC3xx 工程的 fake tresos home。"""
    return fake_tc3xx_project[1]
