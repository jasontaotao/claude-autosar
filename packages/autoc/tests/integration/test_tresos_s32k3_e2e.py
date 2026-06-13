"""端到端集成测试：discover → verify → save → autocalc 完整链路（S32K3）。

不依赖真实 EB tresos 工具（CI 不安装商业工具），用 ``subprocess.run`` mock
模拟 tresos_cmd 输出。**目的**：验证 DTO 在四个 API 之间流转不丢字段、
Result 对象的字段填充正确、调用顺序符合协议。

跨芯片用例：
    - S32K3（EB tresos 风格 .project，faked plugins）
    - TC3xx（EB tresos 风格，faked plugins）
    - RH850（简化风格 .project，faked plugins）

每个 fixture 都跑同一套断言（参数化）—— 证明 discover() 跨芯片统一代码路径。
"""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from claude_autosar.adapters.tresos import TresosAdapter, TresosAdapterError

# 集成测试 marker（pyproject 已注册）
pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "project_fixture",
    ["fake_s32k3_project", "fake_tc3xx_project", "fake_rh850_project"],
)
class TestTresosE2EFlow:
    """discover → verify → save → autocalc 完整调用链，跨 S32K3 / TC3xx / RH850。"""

    def test_full_flow_returns_consistent_dto(
        self,
        project_fixture: str,
        request: pytest.FixtureRequest,
    ) -> None:
        """完整链路返回的 ctx 在每次调用后字段不变（frozen dataclass）。"""
        project_path, tool_home = request.getfixturevalue(project_fixture)
        adapter = TresosAdapter()

        # 1) discover —— 读真实 fake 工程结构（不 mock）
        ctx = adapter.discover(project_path, tool_home)

        # DTO 字段全部填充
        assert ctx.project_path == project_path.resolve()
        assert ctx.tool_home == tool_home.resolve()
        assert ctx.target != "UNKNOWN"
        assert ctx.derivate != "UNKNOWN"
        assert ctx.autosar_version != "UNKNOWN"
        assert len(ctx.enabled_modules) > 0
        assert len(ctx.available_plugins) > 0
        assert all(p.suffix == ".arxml" for p in ctx.available_plugins)

        # 2) verify / save / autocalc —— mock subprocess.run
        with patch("claude_autosar.adapters.tresos.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="OK", stderr=""
            )

            verify_result = adapter.verify(ctx, module="Mcu")
            assert verify_result.success is True

            save_result = adapter.save(ctx, module="Mcu")
            assert save_result.success is True

            calc_result = adapter.autocalc(ctx)
            assert calc_result.success is True

        # 3) 验证三次调用
        assert mock_run.call_count == 3

        # verify 调用了 --validate
        verify_args = mock_run.call_args_list[0][0][0]
        assert "--validate" in verify_args
        assert "--module" in verify_args
        assert "Mcu" in verify_args

        # save 调用了 --save
        save_args = mock_run.call_args_list[1][0][0]
        assert "--save" in save_args

        # autocalc 调用了 --autocalc
        calc_args = mock_run.call_args_list[2][0][0]
        assert "--autocalc" in calc_args

    def test_save_extracts_xdm_written_files(
        self,
        project_fixture: str,
        request: pytest.FixtureRequest,
    ) -> None:
        """save() 把 tresos_cmd stdout 中的 ``wrote *.xdm`` 解析为 written_files。

        这是 DTO 链路关键环节：stdout 文本 → Path tuple → SaveResult.written_files。
        """
        project_path, tool_home = request.getfixturevalue(project_fixture)
        adapter = TresosAdapter()
        ctx = adapter.discover(project_path, tool_home)

        with patch("claude_autosar.adapters.tresos.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="wrote Mcu.xdm\nwrote Port.xdm\n",
                stderr="",
            )
            result = adapter.save(ctx, module="Mcu")

        # 解析后 written_files 包含相对路径（相对于 project_path）
        assert len(result.written_files) == 2
        names = {p.name for p in result.written_files}
        assert "Mcu.xdm" in names
        assert "Port.xdm" in names
        for p in result.written_files:
            assert p.is_absolute()  # 解析后必须是绝对路径

    def test_subprocess_failure_propagates_in_e2e(
        self,
        project_fixture: str,
        request: pytest.FixtureRequest,
    ) -> None:
        """subprocess 失败时 verify/save/autocalc 都返回 success=False，不抛异常。

        E2E 业务层依赖 success 字段做分支，不靠异常流。
        """
        project_path, tool_home = request.getfixturevalue(project_fixture)
        adapter = TresosAdapter()
        ctx = adapter.discover(project_path, tool_home)

        with patch("claude_autosar.adapters.tresos.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="tresos_cmd failed"
            )
            v = adapter.verify(ctx)
            s = adapter.save(ctx)
            c = adapter.autocalc(ctx)

        assert v.success is False and v.returncode == 1
        assert s.success is False and s.returncode == 1
        assert c.success is False and c.returncode == 1

        # 真正的 IO 错误（如 PermissionError）应包成 TresosAdapterError
        with patch("claude_autosar.adapters.tresos.subprocess.run") as mock_run:
            mock_run.side_effect = PermissionError("EACCES")
            with pytest.raises(TresosAdapterError):
                adapter.verify(ctx)

    def test_ctx_is_immutable_across_calls(
        self,
        project_fixture: str,
        request: pytest.FixtureRequest,
    ) -> None:
        """discover() 返回的 ctx 在 verify/save/autocalc 调用后**不变**（frozen 保证）。"""
        project_path, tool_home = request.getfixturevalue(project_fixture)
        adapter = TresosAdapter()
        ctx = adapter.discover(project_path, tool_home)

        snapshot = (
            ctx.project_path,
            ctx.tool_home,
            ctx.target,
            ctx.derivate,
            ctx.pn,
            ctx.autosar_version,
            ctx.enabled_modules,
            ctx.available_plugins,
        )

        with patch("claude_autosar.adapters.tresos.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            adapter.verify(ctx)
            adapter.save(ctx)
            adapter.autocalc(ctx)

        # frozen dataclass 字段值不可变
        assert (
            ctx.project_path,
            ctx.tool_home,
            ctx.target,
            ctx.derivate,
            ctx.pn,
            ctx.autosar_version,
            ctx.enabled_modules,
            ctx.available_plugins,
        ) == snapshot
