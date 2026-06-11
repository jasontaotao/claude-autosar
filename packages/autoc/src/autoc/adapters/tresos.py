"""EB tresos 适配器默认实现。

核心方法：
    - ``discover()``：从 ``.project`` / ``.prefs/`` / ``<tool_home>/plugins/`` 构造
      ``EcuConfigProjectContext``。**MCU 差异化全部由这一处动态处理**——同一段
      代码处理 S32K3 / TC3xx / RH850，不写 if/else。
    - ``verify()`` / ``save()`` / ``autocalc()``：subprocess 包装 ``tresos_cmd.bat``。
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess

from lxml import etree

from autoc.adapters.protocol import (
    CalcResult,
    EcuConfigProjectContext,
    SaveResult,
    VerifyResult,
)


class TresosAdapterError(RuntimeError):
    """EB tresos 适配器错误。"""


class TresosAdapter:
    """EB tresos 默认实现（subprocess 包装）。"""

    DEFAULT_TIMEOUT_S: int = 300
    """subprocess 默认超时（秒）。"""

    def __init__(self, default_timeout_s: int = DEFAULT_TIMEOUT_S) -> None:
        if default_timeout_s <= 0:
            raise ValueError(f"default_timeout_s must be > 0, got {default_timeout_s}")
        self.default_timeout_s = default_timeout_s

    # ------------------------------------------------------------------
    # .project 解析
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_project_xml(project_xml: Path) -> dict[str, str]:
        """解析 ``.project`` 风格的 XML，提取 target / derivate / autosar_version / pn。

        支持两种 schema：
            1. EB tresos 原生：``<tresos:project><tresos:property name="X">V</tresos:property>``
            2. 简化：``<project><target>V</target><derivate>V</derivate>...``

        返回字段集，缺什么 key 给空字符串。
        """
        if not project_xml.is_file():
            raise TresosAdapterError(f".project not found: {project_xml}")
        try:
            tree = etree.parse(str(project_xml))
        except etree.XMLSyntaxError as e:
            raise TresosAdapterError(f"malformed .project XML at {project_xml}: {e}") from e

        root = tree.getroot()
        props: dict[str, str] = {}

        # 1. EB tresos 风格：<tresos:property name="key">value</tresos:property>
        # lxml 用 namespaced XPath
        for prop in root.iter():
            if not prop.tag.lower().endswith("property"):
                continue
            name = prop.get("name")
            if name and prop.text:
                props[name.strip()] = prop.text.strip()

        # 2. 简化风格：<target>V</target>
        for tag in ("target", "derivate", "pn", "autosarVersion", "autosar_version"):
            elems = root.findall(f".//{tag}")
            if elems and elems[0].text:
                props[tag] = elems[0].text.strip()

        # 3. EB tresos 原生常见大小写变体 "AutosarVersion"（首字母大写）→ 归一为 "autosarVersion"
        if "AutosarVersion" in props and "autosarVersion" not in props:
            props["autosarVersion"] = props["AutosarVersion"]

        return props

    # ------------------------------------------------------------------
    # 插件 + 已启用模块扫描
    # ------------------------------------------------------------------

    @staticmethod
    def _list_bswmd_plugins(tool_home: Path) -> tuple[Path, ...]:
        """列 ``<tool_home>/plugins/`` 下所有 ``*_bswmd.arxml``，按路径排序。"""
        plugins_dir = tool_home / "plugins"
        if not plugins_dir.is_dir():
            return ()
        results = sorted(plugins_dir.rglob("*_bswmd.arxml"))
        return tuple(results)

    @staticmethod
    def _list_enabled_modules_from_prefs(project_path: Path) -> tuple[str, ...]:
        """从 ``<project>/.prefs/`` 下所有 ``*.xdm`` 文件名提取已启用模块名。

        EB tresos 约定：``<project>/.prefs/<ModuleName>_Cfg.xdm``（部分版本用
        ``<ModuleName>.xdm``）。取文件名去后缀即可，不读 XML 内部。
        """
        prefs_dir = project_path / ".prefs"
        if not prefs_dir.is_dir():
            return ()
        names: set[str] = set()
        for xdm in sorted(prefs_dir.glob("*.xdm")):
            stem = xdm.stem
            # 去掉 ``_Cfg`` 后缀
            if stem.endswith("_Cfg"):
                stem = stem[:-4]
            if stem:
                names.add(stem)
        return tuple(sorted(names))

    # ------------------------------------------------------------------
    # discover（MCU 差异化核心）
    # ------------------------------------------------------------------

    def discover(
        self,
        project_path: Path,
        tool_home: Path,
    ) -> EcuConfigProjectContext:
        """从工程目录 + tresos 安装目录动态发现上下文。

        调用链路：
            1. 读 ``<project>/.project`` → 提取 target / derivate / pn / autosar_version
            2. 扫 ``<project>/.prefs/*.xdm`` → 列出已启用模块
            3. 扫 ``<tool_home>/plugins/*_bswmd.arxml`` → 列出可用 BSWMD

        **对 S32K3 / TC3xx / RH850 走同一段代码**——所有差异在 ``.project`` 和
        ``plugins/`` 目录里，代码不预知任何具体芯片字段。
        """
        project_path = Path(project_path).resolve()
        tool_home = Path(tool_home).resolve()

        if not project_path.is_dir():
            raise TresosAdapterError(f"project_path is not a directory: {project_path}")
        if not tool_home.is_dir():
            raise TresosAdapterError(f"tool_home is not a directory: {tool_home}")

        # 显式候选列表（按优先级），覆盖 EB tresos 标准命名 + 客户工程常见变体
        project_xml_candidates: list[Path] = [
            project_path / ".project",  # EB tresos 标准
            project_path / "project.xml",  # 部分客户使用
            project_path / ".project.xml",  # 部分客户使用
        ]

        # 兜底：找任意 ``*.project`` 或 ``.project*`` 隐藏文件（处理非标命名）
        # 仅在显式列表全部缺失时启用
        if not any(c.is_file() for c in project_xml_candidates):
            # 两个 glob 都会扫描——保留两个候选以让后续错误信息列出全部可能位置。
            # 第一个 is_file() 命中即被使用（见 next()），故第二个只在第一个不存在时生效。
            for cand in sorted(project_path.glob("*.project")):
                if cand not in project_xml_candidates:
                    project_xml_candidates.append(cand)
                    break
            for cand in sorted(project_path.glob(".project*")):
                if cand.is_file() and cand not in project_xml_candidates:
                    project_xml_candidates.append(cand)
                    break

        project_xml = next(
            (c for c in project_xml_candidates if c.is_file()),
            None,
        )
        if project_xml is None:
            raise TresosAdapterError(
                f"no .project file found in {project_path} (looked for: "
                f"{[str(c) for c in project_xml_candidates]})"
            )

        props = self._parse_project_xml(project_xml)
        target = props.get("target") or props.get("ecudertarget") or "UNKNOWN"
        derivate = props.get("derivate") or "UNKNOWN"
        pn = props.get("pn") or derivate
        autosar_version = props.get("autosarVersion") or props.get("autosar_version") or "UNKNOWN"

        return EcuConfigProjectContext(
            project_path=project_path,
            tool_home=tool_home,
            target=target,
            derivate=derivate,
            pn=pn,
            autosar_version=autosar_version,
            enabled_modules=self._list_enabled_modules_from_prefs(project_path),
            available_plugins=self._list_bswmd_plugins(tool_home),
        )

    # ------------------------------------------------------------------
    # subprocess 包装
    # ------------------------------------------------------------------

    def _tresos_cmd_path(self, ctx: EcuConfigProjectContext) -> Path:
        """定位 ``tresos_cmd`` 可执行文件。"""
        suffix = ".bat" if os.name == "nt" else ".sh"
        candidates = [
            ctx.tool_home / "bin" / f"tresos_cmd{suffix}",
            ctx.tool_home / f"bin/tresos_cmd{suffix}",
        ]
        for c in candidates:
            if c.is_file():
                return c
        raise TresosAdapterError(
            f"tresos_cmd not found under {ctx.tool_home}/bin/ " f"(tried {suffix})"
        )

    def _run_tresos_cmd(
        self,
        ctx: EcuConfigProjectContext,
        args: list[str],
    ) -> subprocess.CompletedProcess[str]:
        """运行 tresos_cmd 子命令，统一处理 cwd / timeout / 编码。

        Windows + .bat：用 ``cmd.exe /c <bat> <args>`` 包装，``shell=False``——避免
        ``C:\\Program Files\\EB tresos`` 等带空格路径被 ``shell=True`` 误解析。
        """
        cmd_path = self._tresos_cmd_path(ctx)
        bat_suffix = cmd_path.suffix.lower() == ".bat"
        if os.name == "nt" and bat_suffix:
            # Windows + .bat：显式 cmd.exe /c 包装
            cmd = ["cmd.exe", "/c", str(cmd_path), *args]
        else:
            # Unix 或 .exe：直接执行
            cmd = [str(cmd_path), *args]
        try:
            result = subprocess.run(
                cmd,
                cwd=str(ctx.project_path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.default_timeout_s,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as e:
            raise TresosAdapterError(
                f"tresos_cmd timed out after {self.default_timeout_s}s: " f"{' '.join(cmd)}"
            ) from e
        except OSError as e:
            # OSError 覆盖 FileNotFoundError / PermissionError / IsADirectoryError
            # 等所有 "执行 tresos_cmd 失败" 的 IO 错误
            raise TresosAdapterError(
                f"tresos_cmd not invocable ({type(e).__name__}: {e}): {cmd_path}"
            ) from e
        return result

    def verify(
        self,
        ctx: EcuConfigProjectContext,
        module: str | None = None,
    ) -> VerifyResult:
        """调用 ``tresos_cmd --validate``。"""
        args = ["--validate"]
        if module:
            args.extend(["--module", module])
        result = self._run_tresos_cmd(ctx, args)
        return VerifyResult(
            success=result.returncode == 0,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    def save(
        self,
        ctx: EcuConfigProjectContext,
        module: str | None = None,
    ) -> SaveResult:
        """调用 ``tresos_cmd --save``。"""
        args = ["--save"]
        if module:
            args.extend(["--module", module])
        result = self._run_tresos_cmd(ctx, args)
        written = self._extract_written_files(ctx, result.stdout)
        return SaveResult(
            success=result.returncode == 0,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            written_files=written,
        )

    def autocalc(self, ctx: EcuConfigProjectContext) -> CalcResult:
        """调用 ``tresos_cmd --autocalc``。"""
        result = self._run_tresos_cmd(ctx, ["--autocalc"])
        return CalcResult(
            success=result.returncode == 0,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    # ------------------------------------------------------------------
    # stdout 解析（提取写入文件路径）
    # ------------------------------------------------------------------

    _WRITTEN_FILE_RE = re.compile(r"(?:wrote|written|saved)\s+(?:to\s+)?([^\s]+\.xdm)")

    @classmethod
    def _extract_written_files(
        cls,
        ctx: EcuConfigProjectContext,
        stdout: str,
    ) -> tuple[Path, ...]:
        """从 tresos_cmd 输出中提取已写入的 .xdm 文件路径。

        tresos_cmd 的输出格式可能因版本而异，使用宽松正则匹配
        ``wrote/written/saved ... .xdm``。匹配项相对于 ``ctx.project_path`` 解析。
        """
        results: set[Path] = set()
        for m in cls._WRITTEN_FILE_RE.finditer(stdout):
            raw = m.group(1)
            p = Path(raw)
            if not p.is_absolute():
                p = ctx.project_path / p
            try:
                p = p.resolve()
            except OSError:
                continue
            results.add(p)
        return tuple(sorted(results))
