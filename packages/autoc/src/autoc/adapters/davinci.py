"""DaVinci Configurator 适配器默认实现。

对应 Vector ``DVCfgCmd.exe`` 命令行工具。``DVCfgCmd`` 默认在
``${SIP}/DaVinciConfigurator/Core/DVCfgCmd.exe``（SIP 路径从 ``.dpa`` 解析，
本适配器复用 ``EcuConfigProjectContext.tool_home`` 字段作 DAVINCI_HOME，调用方
按需从 ``.dpa`` 解析后填入）。

当前 Sprint 2 仅实现 verify / save 两个核心子命令，覆盖率需求 80%+
（Sprint 3+ 会扩展 ``Generate`` / ``Import`` 等）。
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess

from autoc.adapters.protocol import (
    EcuConfigProjectContext,
    SaveResult,
    VerifyResult,
)


class DavinciAdapterError(RuntimeError):
    """DaVinci 适配器错误。"""


class DavinciAdapter:
    """DaVinci Configurator 默认实现。"""

    DEFAULT_TIMEOUT_S: int = 300

    def __init__(self, default_timeout_s: int = DEFAULT_TIMEOUT_S) -> None:
        if default_timeout_s <= 0:
            raise ValueError(f"default_timeout_s must be > 0, got {default_timeout_s}")
        self.default_timeout_s = default_timeout_s

    def _dvcfg_path(self, ctx: EcuConfigProjectContext) -> Path:
        """定位 ``DVCfgCmd.exe``。"""
        suffix = ".exe" if os.name == "nt" else ""
        candidates = [
            ctx.tool_home / "Core" / f"DVCfgCmd{suffix}",
            ctx.tool_home / f"Core/DVCfgCmd{suffix}",
        ]
        for c in candidates:
            if c.is_file():
                return c
        raise DavinciAdapterError(
            f"DVCfgCmd not found under {ctx.tool_home}/Core/ (tried {suffix or 'no-suffix'})"
        )

    def _run_dvcfg(
        self,
        ctx: EcuConfigProjectContext,
        args: list[str],
    ) -> subprocess.CompletedProcess[str]:
        """运行 DVCfgCmd 子命令。"""
        cmd_path = self._dvcfg_path(ctx)
        cmd = [str(cmd_path), *args]
        try:
            return subprocess.run(
                cmd,
                cwd=str(ctx.project_path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.default_timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            raise DavinciAdapterError(
                f"DVCfgCmd timed out after {self.default_timeout_s}s: {' '.join(cmd)}"
            ) from e
        except OSError as e:
            # OSError 覆盖 FileNotFoundError / PermissionError / IsADirectoryError
            # 等所有 "执行 DVCfgCmd 失败" 的 IO 错误
            raise DavinciAdapterError(
                f"DVCfgCmd not invocable ({type(e).__name__}: {e}): {cmd_path}"
            ) from e

    def verify(
        self,
        ctx: EcuConfigProjectContext,
        module: str | None = None,
    ) -> VerifyResult:
        """调用 ``DVCfgCmd AutocVerify``。"""
        args = ["AutocVerify"]
        if module:
            args.extend(["--module", module])
        result = self._run_dvcfg(ctx, args)
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
        """调用 ``DVCfgCmd Save``。

        从 stdout 解析 ``Wrote: <path>`` 模式以填充 ``written_files``，相对路径
        相对于 ``ctx.project_path`` 解析。DaVinci 写出的是 ``.arxml`` 而非 ``.xdm``。
        """
        args = ["Save"]
        if module:
            args.extend(["--module", module])
        result = self._run_dvcfg(ctx, args)
        written = self._extract_written_files(ctx, result.stdout)
        return SaveResult(
            success=result.returncode == 0,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            written_files=written,
        )

    # ------------------------------------------------------------------
    # stdout 解析（提取写入文件路径）
    # ------------------------------------------------------------------

    # DaVinci DVCfgCmd 的 Save 输出格式（Vector 文档）：
    #   "Wrote: <relative-or-absolute-path>"     (最常见)
    #   "Wrote file <path>"                     (旧版本)
    #   "Saved <path>"                          (罕见)
    #
    # 必须左锚定到行首 + 强制扩展名，否则会误匹配自然语言中的 "wrote/saved"
    # （如 "Configuration was not saved due to validation errors" 会被错配为路径 "due"）。
    _WRITTEN_FILE_RE = re.compile(
        r"(?:^|\n)\s*(?:wrote|written|saved)\s*(?:file\s*)?:?\s+(\S+\.(?:arxml|xdm))",
        re.IGNORECASE,
    )

    @classmethod
    def _extract_written_files(
        cls,
        ctx: EcuConfigProjectContext,
        stdout: str,
    ) -> tuple[Path, ...]:
        """从 DVCfgCmd 输出中提取已写入的文件路径。

        相对路径相对于 ``ctx.project_path`` 解析。
        """
        results: set[Path] = set()
        for m in cls._WRITTEN_FILE_RE.finditer(stdout):
            raw = m.group(1).rstrip(".,;")
            p = Path(raw)
            if not p.is_absolute():
                p = ctx.project_path / p
            try:
                p = p.resolve()
            except OSError:
                continue
            results.add(p)
        return tuple(sorted(results))
