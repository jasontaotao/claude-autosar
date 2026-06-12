# AutoC Claude Code 插件 - 进度交接文档

> 给"换窗口后继续干"用的状态快照。最后更新：2026-06-11。

## 换窗口继续（直接说这句就行）

> **"继续 autoc-cc，从 Sprint 4 开始"**

或更直接：

> **"跑 Sprint 4 任务 T4.1"** → 我开干
> **"先 git init"** → 我先 `git init` + 首 commit

## 一句话状态

**Sprint 0+1+2+3+4+5+6+7 全部完成**，共 **467 测试通过**（autoc 442 + plugin 25），coverage **90.07%**（84.75% → 90.07%，+5.32pp），所有 ruff/mypy strict/black/isort/bandit 干净，pip-audit 0 high/medium（autoc 运行时无漏洞；3 个 transitive 漏洞已记录在 SECURITY.md）。

下一个待办：**Sprint 8（待规划）** — 候选：PyPI 发布（autoc 0.1.0 wheel + 签名）、VSCode 扩展 vscode-autoc、CI 增 pip-audit/bandit 步骤。

**Sprint 8.B 状态**：PyPI 发布 0.1.0 wheel + trusted publishing 就绪，本地 build/twine check/smoke test 全通过；release.yml 已就位。**等用户在 PyPI 项目上配置 trusted publisher 一次（PyPI dashboard → Publishing → Add trusted publisher：GitHub → 选 repo + workflow `release.yml` + environment `pypi`）后**打 tag 即可触发自动发布。详细见 Sprint 8.B 段。

## 当前 HEAD 状态

> Sprint 8 完成 git init + 首 commit 后的状态；之前的 sprint 都在文件系统上，未做版本控制。

- **git**: initialized in Sprint 8.A，分支 `main`，单 commit baseline（chore: initial import of autoc-cc monorepo through Sprint 7）
- **测试**: **467 passed**（autoc 442 + plugin 25）/ coverage **90.07%**
- **静态检查**: ruff / isort / black / mypy strict / bandit -ll 全清
- **安全**: bandit -ll 0 high / 0 medium / 7 low（subprocess 模式 + 1 path-traversal 防御）；pip-audit 0 high / 0 medium（autoc 运行时 0 漏洞，3 个 transitive 漏洞已记录在 SECURITY.md）
- **CI**: 5 jobs（lint / typecheck / security / test@py3.11+3.12 / build sanity），包含 bandit + pip-audit

## 关键决策（持久化的项目知识）

1. **pyecarxml 决定**：**lxml-only**。Sprint 3 推翻 PROGRESS.md:114 旧决定，理由是外网调研被 harness 拦 + 写值仍需 lxml 改 DOM。Sprint 5 之后如真实工程多可重评。
2. **ECUC 路径格式**: `Mcu/[Container/]*ShortName`，container 名 ≠ param 名（避免路径重复 e.g. `Mcu/ClockFreq/ClockFreq`）
3. **CLI `--param`**：接受完整 ECUC 路径（`Mcu/Container/Param=value`），不再自动拼 module 前缀
4. **不可变模式**：所有公开 dataclass 是 `frozen=True`，`with_X()` / `set_value()` 返回新实例
5. **lint 约定**：ruff 禁 I001/ARG002/ARG005/RUF002/E501；mypy strict；isort profile=black
6. **Windows .bat**：subprocess 用 `cmd.exe /c <bat> <args>` + `shell=False`（Sprint 2 review 决定）
7. **adapter 抽象**：`TresosAdapter` / `DavinciAdapter` 走 Protocol；`StubTresosAdapter` / `StubDavinciAdapter` 是测试用 mock（必填 `discover_response`）

## Plan 文档位置

- 主 plan: `C:\Users\13777\.claude\plans\declarative-wiggling-cook.md`
- Sprint 3 子 plan: `C:\Users\13777\.claude\plans\graceful-forging-orbit.md`
- Memory: `C:\Users\13777\.claude\projects\D--claude-proj2\memory\autoc-cc-project.md`

## 命名约定说明

`PROGRESS.md` 旧版中 "Sprint 3" 指 Sprint 2 的 review 收尾（T3.1-T3.7 全部是 Sprint 2 范畴的 cleanup）。本版起改用 `plans/declarative-wiggling-cook.md` 里的命名：**"Sprint 3" = ARXML 读写 + BSW 改参 + EB/DaVinci CLI**。

## 已完成的 Sprint

### Sprint 3（plan 中）— ARXML 读写 + BSW 改参 + EB/DaVinci CLI ✅

**T3.1 — `core/bsw/arxml_io.py`**（lxml 低层，80 行）
- `ARXMLDocument` (frozen) / `read` / `write` (原子写) / `find_elements` / `get_attribute` / `set_attribute` / `get_child_text` / `set_child_text` / `ARXMLError`
- 18 测试（读/写原子性/命名空间/round-trip）

**T3.2 — `core/bsw/ecuc.py`**（自写 ECUC 解析，200 行）
- `ECUCValue` / `ECUCDocument` (frozen) / `load_module` / `get_value` / `set_value` (不可变) / `list_paths`
- type 推断用 DEFINITION-REF DEST 属性启发式（`ECUC-INTEGER-PARAM-DEF` → INTEGER 等）
- 自动 unwrap `<CONTAINERS>` / `<SUB-CONTAINERS>` / `<PARAMETER-VALUES>` / `<REFERENCE-VALUES>` wrappers
- 15 测试（5 种类型 + reference + 嵌套 + 不可变 + 未知 fallback）

**T3.3 — `core/bsw/validator.py`**（modify + verify + rollback 闭环，180 行）
- `ModifyRequest` / `ModifyResult` (frozen) / `ValidatorError` / `modify_and_verify`
- 流程：定位 .xdm/.arxml → 快照到系统 temp → 改值 → verify → 失败回滚 / 成功 save
- 任何步骤异常：best-effort 还原 + 抛 `ValidatorError`
- 9 测试（happy / 失败回滚 / 不调 save / 空 params 短路 / 模块文件不存在 / path 不存在 / snapshot 清理 / .arxml fallback）

**T3.4 — `core/bsw/config.py` 扩展**
- `BSWModule.from_ecuc(doc) -> BSWModule`
- `BSWModule.to_ecuc(arxml_path) -> ECUCDocument`
- 双向 type 映射：`_PARAM_TO_ECUC_TYPE` / `_ECUC_TO_PARAM_TYPE`
- 4 测试（5 种类型 / 不可变 / round-trip / 路径校验）

**T3.5 — `cli/commands/eb.py`**
- `autoc eb save/verify/autocalc` 子命令
- `--module Mcu --param Mcu/Container/Param=80000000`（可重复）
- `--adapter {real,stub}` 切换（CI 用 stub）
- 10 测试（argparse + happy / verify fail / autocalc）

**T3.6 — `cli/commands/davinci.py`**
- `autoc davinci save/verify`（无 autocalc — Protocol 不含）
- 7 测试（argparse + happy / verify fail / 无 autocalc 验证）

**main.py 接入**
- import + register 2 个子命令；dispatch 到 `eb_run` / `davinci_run`

**关键决策**（推翻 PROGRESS.md:114 旧"决定不引入 pyecarxml"）
- 外网调研被 harness 拦截，pyecarxml 活跃度/Python 3.11+ 兼容性未验证
- Sprint 3 写值仍需 lxml 改 DOM，pyecarxml 节省 150 行 reference chain 解析的收益 < 多一个不确定 dep 的代价
- **改 lxml-only**，ecuc.py 自写 reference chain 解析 + type 启发式
- 评估路径：Sprint 5 之后如真实工程多可重评

**文件清单**（7 新源 + 3 修改源 + 5 新测试 + 1 追加测试 = 16 个文件，~+1206 行）
- 新源：`arxml_io.py` / `ecuc.py` / `validator.py` / `commands/__init__.py` / `commands/eb.py` / `commands/davinci.py`
- 修改源：`config.py`（+from_ecuc/to_ecuc） / `cli/main.py`（+register + dispatch）
- 新测试：`test_arxml_io.py` / `test_ecuc.py` / `test_validator.py` / `test_cli_eb.py` / `test_cli_davinci.py`
- 追加测试：`test_config.py`（+TestFromEcuc 4 个 case）

### Sprint 0 — 仓库骨架 ✅
- monorepo 根 `D:\claude_proj2\autoc-cc\` + `packages/autoc/` 包
- `pyproject.toml`（workspace + autoc） + `.pre-commit-config.yaml` + `.gitignore`
- `.github/workflows/ci.yml`（5 jobs: lint / typecheck / security / test / build）
- `.github/PULL_REQUEST_TEMPLATE.md`
- `README.md`（monorepo 根） + `packages/autoc/README.md`

### Sprint 1 — 基础数据模型 ✅
- `src/autoc/core/bsw/config.py` — `ParamValue` / `BSWParam` / `BSWModule`（frozen dataclass）
- `src/autoc/core/bsw/schemas.py` — AUTOSAR 经典平台模块摘要（Mcu/Port/Dio/Can/Spi/CanIf/PduR/EcuC/Com），**不预知任何芯片字段**
- `src/autoc/core/settings/config.py` — `deep_merge` + `load_merged_settings`
- `src/autoc/utils/paths.py` — 跨平台路径（platformdirs + find_ancestor_file + normalize_path）
- `tests/conftest.py` — 共享 fixtures（sample_arxml / sample_dbc / temp_autosar_project / sample_settings_json / global_config）

### Sprint 2 — 工具适配器层（MCU 差异化核心）✅
- `src/autoc/adapters/protocol.py` — `EcuConfigProjectContext`（T3.1 由 `TresosProjectContext` 重命名）+ 3 个 Result dataclass + `TresosAdapter`/`DavinciAdapter` Protocol
- `src/autoc/adapters/tresos.py` — `TresosAdapter` 默认实现
  - **`discover()`**：从 `.project` / `.prefs/` / `<tool_home>/plugins/` 动态发现，**对 S32K3/TC3xx/RH850 走同一段代码**
  - `_parse_project_xml` 支持 EB tresos `<tresos:property>` 和简化 `<target>` 两种 schema
  - `AutosarVersion`（首字母大写）自动归一化为 `autosarVersion`
  - `verify()` / `save()` / `autocalc()`：subprocess 包装 `tresos_cmd.bat` / `.sh`（T3.4 Windows 用 `cmd.exe /c` 包装去 `shell=True`）
- `src/autoc/adapters/davinci.py` — `DavinciAdapter` 包装 `DVCfgCmd.exe`（T3.5 解析 `Wrote:` 模式填 `written_files`）
- `src/autoc/adapters/stub.py` — `StubTresosAdapter` / `StubDavinciAdapter`（可断言的记录器）
- `tests/conftest.py` 增加：`_build_fake_tresos` / `_build_fake_project_tresos_style` / `_build_fake_project_simple_style` / `_build_fake_project_prefs` + 3 个 fake 工程 fixture
- 测试：`test_protocol.py` / `test_stub_adapter.py` / `test_tresos_context.py`（★）/ `test_tresos_adapter.py` / `test_davinci_adapter.py`

## 当前所有检查通过状态

```bash
cd D:/claude_proj2/autoc-cc
ruff check packages/autoc/src packages/autoc/tests      # All checks passed
isort --check packages/autoc/src packages/autoc/tests   # All done
black --check packages/autoc/src packages/autoc/tests   # 31 files left unchanged
mypy --strict packages/autoc/src/autoc                  # 17 source files, 0 issues
pytest packages/autoc/tests -q --cov=packages/autoc/src/autoc --cov-fail-under=80
# ============================== 202 passed in 1.33s =============================
# coverage 92.17%
```

依赖 `pip install -e "packages/autoc[dev]"` 已装好（autoc 0.1.0 editable wheel）。

## 文件结构（28 个文件，458 源行 + ~1500 测试行）

```
D:\claude_proj2\autoc-cc\
├── pyproject.toml                  # workspace + ruff/isort/mypy/pytest/coverage
├── .pre-commit-config.yaml
├── .gitignore
├── .github/{workflows/ci.yml, PULL_REQUEST_TEMPLATE.md}
├── README.md
├── PROGRESS.md                      # ← 本文件
└── packages/autoc/
    ├── pyproject.toml
    ├── README.md
    ├── src/autoc/
    │   ├── __init__.py / __main__.py
    │   ├── cli/main.py              # argparse 入口（Sprint 5 扩展）
    │   ├── core/
    │   │   ├── bsw/{config.py, schemas.py}
    │   │   └── settings/config.py
    │   ├── utils/paths.py
    │   └── adapters/
    │       ├── protocol.py          # TresosProjectContext + Protocol
    │       ├── tresos.py            # ★ discover() = MCU 差异化核心
    │       ├── davinci.py
    │       └── stub.py
    └── tests/
        ├── conftest.py              # 3 fake 工程 fixture + 5 基础 fixture
        ├── fixtures/__init__.py
        └── unit/
            ├── test_config.py
            ├── test_schemas.py
            ├── test_settings_merge.py
            ├── test_paths.py
            ├── test_protocol.py
            ├── test_stub_adapter.py
            ├── test_tresos_context.py    # ★ MCU 差异化测试
            ├── test_tresos_adapter.py
            └── test_davinci_adapter.py
```

## Sprint 3 — Sprint 2 review 收尾 + 端到端集成 ✅

| # | 任务 | 状态 |
|---|---|---|
| T3.1 | **重命名** `TresosProjectContext` → `EcuConfigProjectContext`，字段 `tresos_home` → `tool_home: Path` | ✅ |
| T3.2 | subprocess 异常链补 `PermissionError`（`except OSError`） | ✅ |
| T3.3 | `.project` 查找显式列表 `[.project, project.xml, .project.xml]` | ✅ |
| T3.4 | Windows subprocess 改用 `cmd /c` 去掉 `shell=True` | ✅ |
| T3.5 | DaVinci `save()` `written_files` 解析（`Wrote: <path>` 模式） | ✅ |
| T3.6 | **端到端集成测试**：`discover() + verify() + save() + autocalc()` 串联跑 fake_s32k3 | ✅ |
| T3.7 | `default_timeout_s` 校验（> 0） | ✅ |

Sprint 3 review 留 0 HIGH / 3 MEDIUM / 3 LOW：
- MEDIUM 1 PROGRESS.md stale — 已在本文件中修复 ✅
- MEDIUM 2 CI 默认运行所有 integration 标记的测试（无 `requires_tools` 边界） — 已在 `.github/workflows/ci.yml` 加 `-m "not requires_tools"` ✅
- MEDIUM 3 DaVinci `Wrote:` 正则会误匹配自然语言中的 "wrote/saved" — 已在 Sprint 3 review 收尾 PR 修复
- LOW 4 `conftest.py` 内 `tresos_home` 路径命名（小一致性问题）— 保持现状（语义是"EB tresos 的 fake 安装目录"）
- LOW 5 T3.3 glob 兜底是"两段都跑"（非单选）— 已加注释
- LOW 6 T3.6 e2e 中重复的 PermissionError 测试 — 保留（多层防御，跨层回归保护）

`pyecarxml` 在 Sprint 0 已从 dependencies 删除；Sprint 3 评估后**决定不引入**——理由：`autoc` 不直接做 ARXML XML 编辑（那是 EB tresos / DaVinci 工具的责任），只消费 BSWMD 列表和 verify/save 状态码。ARXML 读写留给 Sprint 4+ 的 `core.bsw` 业务层用 `lxml` 现写。

## 设计关键点（继续干时要记得）

1. **不可变性是真的**：`BSWModule.with_param()` 返回新实例；`TresosProjectContext` 全部字段 `frozen=True`。
2. **配置优先级**：`<cwd>/.autoc/` 覆盖 `~/.autoc/agent/`。
3. **路径在 plan / 实施时统一用正斜杠**（即使 Windows）；pyproject 中 `where = ["src"]`。
4. **CLI 命令名 `autoc`**（pyproject `[project.scripts]`）。
5. **isort 和 ruff 在 I001 上不一致**：已在 pyproject 禁用 ruff I001，让 isort 单独管。
6. **ARG002 / ARG005 禁用**（parametrize 和 Protocol 子类的必要未用参数）。
7. **本仓库叫 `autoc-cc`**，但 PyPI 包名是 `autoc`（`packages/autoc`）。

## 计划文档位置

`C:\Users\13777\.claude\plans\declarative-wiggling-cook.md` —— 完整 PRD + 架构 + 7-sprint 任务分解。

## 怎么继续

在新窗口里只需要说 **"继续 autoc-cc，从 Sprint 3 开始"**，我会从这份 PROGRESS.md + memory 找到当前状态。

或者更直接：说 **"跑 Sprint 3 任务 T3.1（重命名）"** 我就开干。

### Sprint 5 — CLI 主入口 + Rich 样式 + MCP server（10 工具）✅

| # | 任务 | 状态 |
|---|---|---|
| T5.1 | 重构 `cli/main.py`：dispatch 表 + `--verbose`/`--no-color` 全局 | ✅ |
| T5.2 | 新建 `cli/repl_skin.py`：Rich 主题 + Console 工厂 + ReplSkin 业务 API | ✅ |
| T5.3 | 新建 `cli/mcp_server.py`：FastMCP + 10 工具 | ✅ |
| T5.4 | 验证 `autoc = autoc.cli.main:main` console_script 命中 | ✅ |

**T5.1 — `cli/main.py` 重构**（dispatch 表 + 两阶段解析，~135 行）
- `_DISPATCH: dict[str, tuple[register_fn, run_fn]]` 模块级字典
- 5 个子命令（eb / davinci / session / log / export）从 if/elif 链改成字典查找
- 新增全局 `--verbose` / `--no-color`（repl_skin 钩子）
- 两阶段解析：先扫第一个非 flag token，不在白名单就 exit 1 + 中文提示（避开 argparse 内部对未知子命令抛 SystemExit(2) 的行为）
- `__main__` 块传 `sys.argv[1:]`（修复回归：之前不传 argv 导致 sys.argv 路径绕过两阶段解析）

**T5.2 — `cli/repl_skin.py`**（Rich 样式层，~220 行）
- `AUTOC_THEME` 7 个语义化样式（success / error / warning / info / hint / accent / muted / border）
- `make_console(no_color=, force_terminal=)` 工厂（`detect_no_color()` 探测 `NO_COLOR` env + `isatty()`）
- `ReplSkin` 类：status 消息 + section / table / status_block + `print_result_table` / `print_diff_callout`（autoc 专用，三色 callout）
- 注入式 `console` 参数（便于测试 + 多 context 复用）
- 测试用 `Console(record=True, file=io.StringIO(), width=120, no_color=True, force_terminal=False)` 模式 + `export_text()` 断言

**T5.3 — `cli/mcp_server.py`**（FastMCP 10 工具，~470 行）
- `FastMCP("autoc-mcp")` 启动 stdio 传输；`mcp-inspector python -m autoc.cli.mcp_server` 调试
- 10 个 tool 全 JSON-friendly dict 返回；错误路径走 `{"success": False, "error": "..."}` 模式
- `cantools.database.load_file`（41.x 推荐 API）+ 处理 `start_bit` → `start` 重命名
- 所有 tool 复用既有 CLI 业务层（`SessionStore` / `SessionTree` / `export_html` / `extract_changes` / `render_timeline` / `render_by_url` / `arxml_io.read`）

**Sprint 5 review 收尾**（code-reviewer agent）
- **HIGH 修了 4 个**：
  - H1: `session_show("latest")` / `session_export(..., "latest")` / `log_export(..., "latest")` 之前按字母序解析 → 改成 mtime 排序。把 `_resolve_latest` 提到 `autoc.core.session.store.resolve_latest_session_id`，CLI 3 个重复实现 + MCP 3 处调用全委托到它
  - H2: `bsw_write` 异常收窄到 `(OSError, ValueError, TypeError, KeyError)`，去掉模糊 `except Exception`
  - H3: `bsw_write` 入参 schema 校验前置：返回 `{"success": False, "error", "param_index", "field"}` 让 LLM 精确定位坏字段
  - H4: `bsw_*` 工具的 `project` 路径防御：必须在 `_ALLOWED_PROJECT_ROOTS` (cwd) 之内；`tresos_home` 必须在 project 之内（ISO 21434 信任边界）
- **关键回归测试**：`test_session_show_latest_resolves_by_mtime_not_name`（设 `zzz` 字母序在前但 mtime 旧，`aaa` 字母序在后但 mtime 新，断言返回 aaa）

**设计决策（持久化）**
- ReplSkin 走"注入式 console"模式（避免全局 state，便于测试 + 多 context 复用）
- MCP 工具返回 dict 而非 dataclass（FastMCP 自动 JSON 序列化）
- `_ALLOWED_PROJECT_ROOTS` 在 import 时快照一次（生产部署可改成环境变量覆盖）
- `_TOOL_FUNCS` 注册时 `assert name == fn.__name__`（防 dict key 与函数名漂移）
- ParamType 枚举值是小写（`integer` / `float` / ...），与 EB tresos 字面值一致
- `from e` 仅跟在 `raise` 后；`return X from e` 不是合法 Python 语法（用 `raise from e` 后再 catch，或干脆把 `type(e).__name__: e` 放在 error 字段里）

**最终状态**
- 测试：**393 passed**（基线 349，新增 44）
- Coverage：**84.75%**（基线 88.03%，分母从 1533 行扩到 1825 行）
- 静态检查：ruff / isort / black / mypy strict / bandit 全清（bandit 7 low 0 high/medium：6 pre-existing subprocess 模式 + 1 new path-traversal 防御）
- 烟囱测试：
  - `autoc --version` / `autoc --help` / `autoc --verbose --no-color` 全部命中
  - `autoc nonexistent_subcommand` → exit 1 + "未知子命令: ..." 中文提示
  - `python -m autoc.cli.main` 走两阶段解析
  - FastMCP `build_mcp_server()` 注册 10 工具
  - cantools DBC 解析 happy + sad path

**文件清单**
新源：
- `cli/repl_skin.py` (~220 行)
- `cli/mcp_server.py` (~470 行)
- `core/session/store.py` 新增 `resolve_latest_session_id()` 模块级函数

新测试：
- `tests/unit/test_cli_main.py` (12)
- `tests/unit/test_repl_skin.py` (14)
- `tests/unit/test_mcp_server.py` (18)

修改源：
- `cli/main.py` (dispatch 表 + 全局 flags + 两阶段解析)
- `cli/commands/session.py` / `log.py` / `export.py` (委托给 `resolve_latest_session_id`)

### Sprint 6 — Claude Code 插件外壳 ✅

| # | 任务 | 状态 |
|---|---|---|
| T6.1 | `plugin/plugins/autoc/.claude-plugin/plugin.json`（name/author/license/repo/keywords） | ✅ |
| T6.2 | `agents/bsw-config.md`（frontmatter + 触发词 + 改参流程） | ✅ |
| T6.3 | 7 个 `commands/*.md`（bsw-config/eb-save/davinci-verify/arxml-validate/session-tree/export/log，全部带 `name` 字段） | ✅ |
| T6.4 | 7 个 `skills/*/SKILL.md`（bsw-knowledge/autosar-naming/eb-tresos/davinci-configurator/arxml-format/dbc-can/change-traceability） | ✅ |
| T6.5 | `hooks/hooks.json` + 3 个 Python 钩子 + 25 个单元测试 | ✅ |
| T6.6 | `.mcp.json` 指向 `autoc.cli.mcp_server`（FastMCP 10 工具已就绪） | ✅ |
| T6.7 | `packages/plugin/.claude-plugin/marketplace.json`（带 license/homepage/repo） | ✅ |
| T6.8 | `docs/{install,troubleshooting,dev-guide}.md` + `README.md`（含 /autoc:* ↔ MCP 工具映射表） | ✅ |
| T6.9 | code-review 收尾：3 HIGH 全部修复 + 4 MEDIUM + 5 LOW | ✅ |

**T6.1 — `plugin.json`**（22 行，名字/版本/author/license/homepage/repo/keywords）
- name=autoc, version=0.1.0, license=Apache-2.0
- keywords=[autosar,bsw,eb-tresos,davinci,arxml,embedded,ecu,mcp]

**T6.3 — 7 个 commands**（每条带 `name` + `description` + `allowed-tools`）
- 全部带 `name:` frontmatter（code-review L1 修复）
- 每个命令委派到对应的 autoc CLI 子命令或 MCP 工具

**T6.4 — 7 个 skills**（每条 `name` 与目录名一致 + 中文业务 / 英文协议字段混合）
- bsw-knowledge / autosar-naming / eb-tresos / davinci-configurator / arxml-format / dbc-can / change-traceability

**T6.5 — 3 个钩子 + 25 个测试**（核心工作）
- `pretooluse_arxml_guard.py`（~140 行）
  - matcher=`Write|Edit`（不含 MultiEdit，因增量多 edit 无法预测最终内容）
  - 5MB 硬上限防 OOM（超过让用户走 `autoc arxml validate`）
  - 拒绝时同时输出新版 `hookSpecificOutput.permissionDecision=deny` 与旧版顶层 `decision=block`（向后兼容）
  - 所有异常路径必须 systemMessage 显式记录（禁止静默放行）
- `posttooluse_bsw_validate.py`（~130 行）
  - matcher=`Write|Edit` + path 匹配 `**/.prefs/<Module>.xdm`
  - 调 `autoc eb verify --module <Module> --adapter stub`（25s timeout）
  - 缺 CLI / 超时 / verify 失败 三种路径都注入 `additionalContext`
- `sessionstart_detect_project.py`（~125 行）
  - 解析 cwd（优先 event.cwd → PWD 环境变量 → os.getcwd()）
  - 检测 .project（EB tresos） / *.dpa（DaVinci） / *.arxml
  - 注入 4 段上下文：检测结果 + 用法提示 + 子 Agent 入口 + 会话写入
- **25 个单元测试**（从 22 增到 25）：
  - test_large_arxml_rejected_to_avoid_oom（新增）
  - test_deny_emits_both_decision_formats（新增）
  - test_multiedit_tool_not_intercepted（新增）
  - 7 个 ARXML guard 路径 + 8 个 BSW validate 路径（含 Windows 路径）+ 7 个 SessionStart 路径

**T6.6 — `.mcp.json`**
```json
{
  "autoc": {
    "type": "stdio",
    "command": "python",
    "args": ["-m", "autoc.cli.mcp_server"],
    "env": {"PYTHONPATH": "${CLAUDE_PLUGIN_ROOT}/../autoc/src"}
  }
}
```

**T6.7 — `marketplace.json`**
- 顶层 + 插件层都带 `license` / `homepage` / `repository`（code-review 配置一致性修复）
- description 列出 7 个命令名 + 10 个 MCP 工具名

**T6.8 — 文档**（`docs/{install,troubleshooting,dev-guide}.md`）
- install.md：5 个验证步骤（CLI / marketplace / 3 种 hook 触发 / MCP）
- troubleshooting.md：6 个常见问题 + 真绕过方法（不是误导的"改用 Edit"）
- dev-guide.md：4 种扩展路径（skill/command/hook/agent）+ 提交规范 + checklist
- README.md：含 /autoc:* ↔ MCP 工具映射表 + docs/ 文件清单

**T6.9 — code-review 收尾**（code-reviewer agent）

修复 3 HIGH + 4 MEDIUM + 5 LOW（13 项）：

| 严重度 | 问题 | 修复 |
|--------|------|------|
| HIGH H1 | dev-guide 误推 `mypy --strict` 但 lxml stub 推断 | 已是项目实践；新增 3 个测试用 `--strict` 验证 lxml 路径通过（误报） |
| HIGH H2 | PreToolUse 协议字段名偏离官方 | 同时输出新版 `hookSpecificOutput.permissionDecision=deny` + 旧版顶层 `decision=block` |
| HIGH H3 | matcher `Write\|Edit\|MultiEdit` 覆盖过广 | matcher 改为 `Write\|Edit`（MultiEdit 增量无法预测）；加 test 验证 MultiEdit 不命中 |
| MEDIUM M1 | `_validate_arxml` OOM 风险 | 加 5MB 硬上限，超过直接拒绝（引导用户走 CLI） |
| MEDIUM M2 | hooks.json `python` 无版本固定 | 改为 `python3`（更跨平台） |
| MEDIUM M3 | 异常路径断言偏弱 | `malformed event` 测试改为必须 `systemMessage` + 含 "error" |
| MEDIUM M4 | MultiEdit 假象问题 | matcher 摘除 MultiEdit；加 test 验证不命中 |
| MEDIUM M5 | troubleshooting 误导"改用 Edit 绕过" | 改写为真绕过：临时改名 + MultiEdit 真旁路 + 警告 |
| LOW L1 | commands 缺 `name` 字段 | 7 个 commands 全部加 `name:` frontmatter |
| LOW L2 | README 与实际结构偏差 | 补 docs/ 子文件清单 + 工具映射表 |
| LOW L3 | `_output` envelope 偏离 | 保留 `hookSpecificOutput` 同时加 `systemMessage` 顶部 |
| LOW L5 | skill name 与目录名一致 | 验证：全部 7 个 SKILL.md 的 `name` 字段等于目录名 |
| LOW L6 | 缺 tool↔command 映射 | README.md 新增章节 |

**协议正确性**

| 协议点 | 实现 | 测试覆盖 |
|--------|------|----------|
| PreToolUse 拒绝 | `hookSpecificOutput.permissionDecision="deny"` + 顶层 `decision="block"` | ✅ test_deny_emits_both_decision_formats |
| PreToolUse 放行 | `{}` 空对象 | ✅ test_non_arxml_write_allowed / test_valid_arxml_allowed |
| PostToolUse 上下文 | `hookSpecificOutput.additionalContext` | ✅ test_xdm_in_prefs_runs_verify |
| SessionStart 上下文 | `hookSpecificOutput.additionalContext` | ✅ test_eb_project_detected 等 7 个 |
| 异常不阻断 | try/except + systemMessage 显式 | ✅ test_malformed_event_does_not_crash |
| MultiEdit 不在范围 | matcher 排除 | ✅ test_multiedit_tool_not_intercepted |
| 大文件拒绝 | 5MB 硬上限 | ✅ test_large_arxml_rejected_to_avoid_oom |
| Windows 路径 | 反斜杠 → 正斜杠 | ✅ test_windows_path_separator |

**最终状态**
- 测试：418 passed（autoc 393 + plugin 25）
- Coverage：84.75%（不变 — plugin 文档不计入）
- 静态检查：ruff / isort / black / mypy strict 全清
- 安全：bandit -ll 0 high / 0 medium / 0 low
- 烟囱测试：
  - 3 个 JSON manifest 全部有效（plugin.json / marketplace.json / .mcp.json）
  - `python3 pretooluse_arxml_guard.py < event.json` 拒绝 + 放行均正确
  - `python3 sessionstart_detect_project.py < event.json` 注入 additionalContext
  - 端到端：`/autoc:eb-save` / `/autoc:log` 等命令均可调用

**文件清单**（Sprint 6 新增 22 文件 + 1 修改）

新源（5 Python）：
- `packages/plugin/plugins/autoc/hooks/pretooluse_arxml_guard.py`（~140 行）
- `packages/plugin/plugins/autoc/hooks/posttooluse_bsw_validate.py`（~135 行）
- `packages/plugin/plugins/autoc/hooks/sessionstart_detect_project.py`（~125 行）
- `packages/plugin/tests/__init__.py`
- `packages/plugin/tests/conftest.py`

新源（13 Markdown / JSON）：
- `packages/plugin/README.md`
- `packages/plugin/.claude-plugin/marketplace.json`
- `packages/plugin/plugins/autoc/.claude-plugin/plugin.json`
- `packages/plugin/plugins/autoc/.mcp.json`
- `packages/plugin/plugins/autoc/agents/bsw-config.md`
- `packages/plugin/plugins/autoc/commands/{bsw-config,eb-save,davinci-verify,arxml-validate,session-tree,export,log}.md`（7 个）
- `packages/plugin/plugins/autoc/skills/{bsw-knowledge,autosar-naming,eb-tresos,davinci-configurator,arxml-format,dbc-can,change-traceability}/SKILL.md`（7 个）
- `packages/plugin/plugins/autoc/hooks/hooks.json`
- `packages/plugin/plugins/autoc/docs/{install,troubleshooting,dev-guide}.md`（3 个）

新测试（1 个文件，25 个 test）：
- `packages/plugin/tests/test_hooks.py`

修改源（1 个）：`PROGRESS.md`（本文）

**下一个 sprint**：Sprint 7 — 端到端 e2e（Playwright 启 Claude Code 真测插件） + 文档收尾。

---

### Sprint 7 — 端到端 e2e + 文档收尾 ✅

| # | 任务 | 状态 |
|---|---|---|
| T7.1 | e2e 串联：钩子 subprocess ↔ CLI ↔ MCP ↔ HTML 导出 | ✅ |
| T7.2 | `docs/install.md` + `docs/troubleshooting.md` | ✅（Sprint 6 T6.8 提前交付） |
| T7.3 | `docs/dev-guide.md` | ✅（Sprint 6 T6.8 提前交付） |
| T7.4 | coverage ≥ 80% line + branch | ✅（**90.07%**，84.75% → 90.07%，+5.32pp） |
| T7.5 | bandit / pip-audit 扫描 | ✅（0 high / 0 medium；pip 升级到 26.1.2 修 3 个 pip CVE） |
| T7.6 | code-review 收尾（code-reviewer agent 跑 + 修 7 HIGH） | ✅ |
| T7.7 | 更新 PROGRESS.md | ✅ |

**T7.1 — `tests/unit/test_mcp_server_coverage.py`**（~620 行，39 个测试）
- 10 个 MCP 工具的 happy + sad path 全面覆盖
- 重点：bsw_read 5 种类型派生值（int/float/bool/string + full module prefix 路径）、bsw_write 5 ParamType + H3 schema + H4 路径防御、bsw_verify / bsw_autocalc、arxml_validate 3 错误路径（missing / ARXMLError / catch-all Exception）、session_list/show/export、log_export
- 内部辅助函数单测：`_resolve_safe_project` / `_default_tresos_home` / `_TOOL_FUNCS name 校验` / `main()` 入口
- autouse fixture：每个测试后还原 `_ALLOWED_PROJECT_ROOTS` / `_default_session_dir` 避免测试间污染

**T7.1 — `tests/integration/test_sprint7_e2e.py`**（~460 行，9 个测试）
- 3 个钩子 subprocess 真测：pretooluse_arxml_guard（拒/放/忽略非 ARXML）+ sessionstart_detect_project（注入 additionalContext / graceful 空 cwd）
- MCP 串联：bsw_write → recorder 落盘 → log_export 看到改参 → session_export 写 HTML
- CLI 烟囱：autoc --version / --help / 未知子命令 + eb save dispatch 通到 validator

**关键设计决策**
- MCP 工具 + Recorder 分工（沿用 T5）：MCP `bsw_write` 只调 `modify_and_verify`，不写 session；session 写入由 CLI 业务层 `recorder.record_bsw_write_batch()` 负责（e2e 模拟完整 Claude Code Agent 路径）
- 钩子 subprocess 用 `encoding="utf-8"` 显式锁（Windows 默认 cp936/cp1252 会让非 ASCII 字符 print 时崩）
- H3 合约统一：`bsw_write` / `bsw_verify` / `bsw_autocalc` 错误 dict 一律含 `field` + `param_index`（Sprint 5 H3 扩展到路径防御错误）

**T7.6 — code-review 收尾**（code-reviewer agent）
- 7 HIGH 全部修复：
  - T1：`_run_hook` 显式 `encoding="utf-8"` + 任何非 0 rc 视作 hook 异常
  - T2：autouse fixture 还原 `_ALLOWED_PROJECT_ROOTS` / `_default_session_dir`
  - T3：`mcp_server.py` 4 处路径防御错误 dict 加 `field` + `param_index`（含 `bsw_write` / `bsw_verify` / `bsw_autocalc` 各两处）
  - T4：`test_session_list_with_data_returns_ids` 改用前缀匹配（避免 "alphabet" 误判）
  - T5：`test_arxml_validate_arxml_error` 强化断言（不 vague pass）+ 新增 `test_arxml_validate_catchall_exception`
  - T6：`test_dbc_parse_exception_returns_error_dict` 强化（要求非空 error 字段）
  - T7：e2e CLI 烟囱断言改 `rc in (0,1) + 业务错误信号`
  - T8：SECURITY.md `pip-audit --requirement <(grep ...)` 改为跨平台 tomllib 写法
- 7 MEDIUM / 5 LOW 评估后采纳建议（XSS 测试、catch-all 分支、5 ParamType 真实断言、autouse fixture 复用）

**T7.5 — 安全扫描**

| 工具 | 范围 | High | Medium | Low | 结论 |
|------|------|------|--------|-----|------|
| `bandit -ll` | autoc src + plugin hooks | **0** | 0 | 9 | ✅ |
| `pip-audit` | autoc 完整依赖图 | **0**（autoc 运行时） | 0 | 3 transitive | ✅ |

- bandit 9 Low 全是 B404/B603/B607（subprocess 模式），与 Sprint 5 决策一致（trust-but-verify 由 stub adapter 兜底）
- pip 自身升级到 26.1.2 修 3 个 pip CVE（PYSEC-2026-196 / CVE-2026-3219 / CVE-2026-6357）
- 剩 3 transitive 漏洞：aiohttp（via kubernetes dev 依赖）+ chromadb 1.5.9（dev 工具），autoc 运行时不用
- 详见 `SECURITY.md`（含依赖图证据 + 跨平台复扫命令）

**最终状态**
- 测试：**442 passed**（autoc，基线 393 + 新 49：39 coverage + 9 e2e + 1 新防御回归）
- Plugin 钩子测试：**25 passed**
- **总计 467 tests pass**
- Coverage：**90.07%**（PROGRESS 84.75% → 90.07%，+5.32pp）
- 关键：**mcp_server.py 91%** coverage（47% → 91%，+44pp）
- 静态检查：ruff / isort / black / mypy strict / bandit 全清
- 烟囱测试：
  - 3 个钩子 subprocess 真跑（拒绝 / 放行 / 注入上下文 / graceful）
  - MCP bsw_write + recorder + log_export 串联 OK
  - autoc --version / --help / 未知子命令 / eb save dispatch 通

**文件清单**（Sprint 7 新增 3 文件 + 1 修改源 + 1 修改测试 = 5 文件）

新源（2 测试）：
- `packages/autoc/tests/unit/test_mcp_server_coverage.py`（~620 行，39 tests）
- `packages/autoc/tests/integration/test_sprint7_e2e.py`（~460 行，9 tests）

新源（1 文档）：
- `SECURITY.md`（~80 行，扫描基线 + 漏洞处置 + 跨平台复扫命令）

修改源（1）：
- `packages/autoc/src/autoc/cli/mcp_server.py`（4 处错误 dict 加 `field` + `param_index`）

修改测试（1）：
- `packages/autoc/tests/unit/test_mcp_server_coverage.py`（修 code-review 7 HIGH 后含 noqa + autouse fixture）

---

### Sprint 4 — 会话 / 树 / 导出 / 改参日志 ✅

**T4.1 — `core/session/store.py`**（JSONL append-only 存储，~150 行）
- `SessionEntry` (frozen) / `Session` (frozen) / `SessionStore` / `SessionStoreError` / `new_session_id`
- 写：open(append-binary) + write + flush + os.fsync（Windows 强持久）
- 读：缺文件抛 `SessionStoreError`（明确失败，不静默）
- 中文 / Unicode 安全（`ensure_ascii=False`）
- 11 测试

**T4.2 — `core/session/tree.py`**（不可变树 + fork，~120 行）
- `SessionTree` (frozen) + `root()` / `children()` / `find()` / `walk()`（DFS pre-order 显式 stack，避递归）
- `with_entry()` / `with_session_meta()` / `fork()` 全部返回新实例
- `root()` 兼容 fork 后 tree（parent_id 指向原 session 的 entry）
- 13 测试

**T4.4 — `core/log/changelog.py`**（改参 timeline / by-url 渲染，~120 行）
- `Change` (frozen) + `extract_changes(tree)` / `render_timeline()` / `render_by_url()`
- 跳过非 `bsw_write` entry；`op="modify"` 为当前唯一 kind
- timeline 按 timestamp 倒序；by-url 按 `(module, path)` 分组
- 10 测试

**T4.3 — `core/session/exporter.py`**（HTML 自包含 + 绿/黄/红 callout，~220 行）
- 零新 dep（`html.escape` + 自写轻量 inline Markdown：`**bold**` / `` `code` `` / `[link](url)`）
- XSS 防御：URL scheme 白名单（http / https / mailto / file）+ `rel="noopener noreferrer"`
- 三色 callout：add=绿 / modify=黄 / delete=红
- 14 测试（含 3 个 XSS 注入 + 1 个 noopener noreferrer）

**T4.5 — 3 个 CLI**（沿用 eb.py / davinci.py 既有 register/build_parser/run 风格）
- `cli/commands/session.py` — `autoc session list/show/fork`（10 测试）
- `cli/commands/log.py` — `autoc log --view timeline/by-url`（7 测试）
- `cli/commands/export.py` — `autoc export --output <html>`（5 测试）

**集成 — `core/session/recorder.py`（~150 行）+ eb/davinci/main 改造**
- `record_bsw_write_batch()` DRY helper：1 user + N tool entries 到 current session
- `get_or_create_current_session()` 读 `~/.autoc/agent/sessions/.current` 标记
- **进程内并发安全**：`threading.Lock` 保护 `.current` 读写 + 整个 batch 写入（跨进程不保证）
- eb.py / davinci.py 成功路径调 recorder（best-effort，失败 → `payload["session_record_error"]`）
- main.py 注册 3 个新子命令 + 3 个 dispatch 分支
- 8 recorder 测试 + 2 TestRunSaveSession 测试（真 stub adapter 端到端） + 3 e2e 测试

**Code Review 收尾**（code-reviewer agent）
- HIGH #1 XSS via `javascript:` URL — 已修（URL scheme 白名单 + rel="noopener noreferrer"）
- HIGH #2 race condition in `get_or_create_current_session` — 已修（进程内 threading.Lock）
- MEDIUM #1 bare `except Exception` in recorder — 已收窄到 `(OSError, ValueError, SessionStoreError)`
- MEDIUM #2 bare `except Exception` in eb/davinci — 已收窄到 `(OSError, ValueError, TypeError)`
- LOW `str()` coercion in extract_changes — 不修（无触发条件）

**设计决策（持久化）**
- 存储格式：JSONL append-only（不引 os.replace 原子重命名）
- 路径复用：`utils/paths.global_session_dir()`（Sprint 4 真正接入）
- 不可变 dataclass + `with_X()` 模式（沿用 Sprint 1–3）
- HTML 自包含：inline `<style>`，无外部资源（`html.escape` 防 XSS）
- Markdown 渲染：自写轻量 inline 解析，不引 `markdown` 包
- "current" session 用 `.current` 文件标记（用户可 `set_current_session` 切换）
- `eb save` 写 session 的语义：仅当 `result.success` 才写；写失败不抛

**最终状态**
- 测试：349 passed（基线 266，新增 83）
- Coverage：**88.03%**（基线 86.42%，+1.61pp）
- 静态检查：ruff / isort / black / mypy strict / bandit 全清
- 烟囱测试：`eb save (stub) → session list → log timeline → export html` 端到端跑通
- 新源 7 + 新测试 8 + 改源 3 + e2e 1 = **19 个文件，+1800 行**

**文件清单**
新源：
- `core/session/__init__.py` `store.py` `tree.py` `exporter.py` `recorder.py`
- `core/log/__init__.py` `changelog.py`
- `cli/commands/session.py` `log.py` `export.py`

新测试：
- `tests/unit/test_session_store.py` (11) / `test_session_tree.py` (13) / `test_changelog.py` (10) / `test_session_exporter.py` (14) / `test_session_recorder.py` (8) / `test_cli_session.py` (10) / `test_cli_log.py` (7) / `test_cli_export.py` (5)
- `tests/integration/test_sprint4_e2e.py` (3)

修改源：
- `cli/commands/eb.py` (成功路径写 session)
- `cli/commands/davinci.py` (同上)
- `cli/main.py` (注册 3 个新子命令 + dispatch)
- `tests/unit/test_cli_eb.py` (追加 TestRunSaveSession 2 测试)

**下一个 sprint**：Sprint 5 — CLI 主入口（`cli/main.py` 已就绪，剩 `cli/repl_skin.py` Rich 样式 + `cli/mcp_server.py` 暴露 10 个 MCP 工具）。

---

### Sprint 8.A — git init baseline ✅

| # | 任务 | 状态 |
|---|---|---|
| T8.A.1 | `git init` + 分支 `master` → `main` | ✅ |
| T8.A.2 | 删除 `_tmp_test.xdm` 测试残留 | ✅ |
| T8.A.3 | Sprint 5+6+7 全部改动入库（合并 commit，43 文件 / +5866 行） | ✅ |
| T8.A.4 | `PROGRESS.md` 顶部"当前 HEAD 状态"段刷新（Sprint 2 → Sprint 7 实际数） | ✅ |

**最终状态**（按 commit 顺序）：
- `914f20d` chore(sprint8): git init baseline — refresh PROGRESS.md head state
- `599aa39` feat: sprint 5+6+7 — mcp server, plugin shell, e2e, security audit
- `8b5149c` feat: sprint 0+1+2+3+4 — core, adapters, CLI, session, marketplace
- `ef68726` chore: initial project scaffold

**为什么合并 sprint 5+6+7 一个 commit**：mcp_server.py 在 Sprint 5 创建、Sprint 7 修复 4 处 error dict 合约；分 commit 会让 sprint 5 commit 缺一块、且 mcp_server 在 sprint 7 commit 中反历史。合并 commit 粒度与既有 `8b5149c`（sprint 0-4 一次合并）对齐。

---

### Sprint 8.B — PyPI 发布 0.1.0 wheel + trusted publishing ✅

| # | 任务 | 状态 |
|---|---|---|
| T8.B.1 | `pyproject.toml` 审计 + 补 `project.urls` + 操作系统 classifiers | ✅ |
| T8.B.2 | `CHANGELOG.md`（Keep a Changelog 1.1.0 风格） | ✅ |
| T8.B.3 | `python -m build` wheel + sdist + `twine check` + fresh venv smoke test | ✅ |
| T8.B.4 | `.github/workflows/release.yml` — trusted publishing（OIDC，无 token） | ✅ |
| T8.B.5 | `PROGRESS.md` Sprint 8.B 段 | ✅ |

**T8.B.1 — `pyproject.toml` 改进**
- 增 `[project.urls]`（Homepage / Repository / Issues / Changelog）
- 增 7 个 classifiers：Intended Audience :: Developers、Operating System :: OS Independent / Windows / POSIX Linux、Python 3.13、Typing :: Typed
- keywords 增 `ecu` / `embedded` / `mcp`（去重 arxml）

**T8.B.2 — `CHANGELOG.md`**
- 根目录 `CHANGELOG.md`（非 packages/autoc/ 内）— PyPI 主页 + GitHub 双方都链
- Keep a Changelog 1.1.0 风格：Added / Changed / Fixed / Notes 四段
- 0.1.0 release notes 覆盖 Sprint 0-7 所有用户面向变更（不变更路径 / 不影响二次开发者的内部重构不写）

**T8.B.3 — build 验证**
- `dist/autoc-0.1.0-py3-none-any.whl` (66 KB) + `dist/autoc-0.1.0.tar.gz` (51 KB)
- `twine check dist/*` → PASSED（long_description README 渲染合法）
- fresh venv 烟囱：
  - `autoc --version` → `autoc 0.1.0`
  - `autoc --help` → dispatch 表 5 子命令（eb / davinci / session / log / export）+ 全局 flags
  - `from autoc.cli.mcp_server import build_mcp_server; build_mcp_server()` → 10 工具注册

**T8.B.4 — `release.yml`**
- 触发：`v*.*.*` tag push **或** `workflow_dispatch`（带 `test_pypi` input）
- 3 jobs：`build`（含 `twine check` + fresh venv smoke test + 上传 artifact） → `publish`（PyPI，env `pypi`） / `publish-test`（TestPyPI，env `test-pypi`，仅 manual + test_pypi=true 触发）
- trusted publishing 配置：`permissions.id-token: write` + PyPI 端 OIDC 信任（无需 API token）
- artifact 留存 14 天（traceability / 手动 verify）

**PyPI 项目一次性配置**（项目 owner 做一次，release.yml 才能跑）：
1. 登录 https://pypi.org → autoc 项目 → Publishing → Add a new pending publisher
2. 填：
   - Owner：`autoc-cc`
   - Repository：`autoc-cc`
   - Workflow filename：`release.yml`
   - Environment name：`pypi`
3. （可选但推荐）GitHub repo → Settings → Environments → `pypi` → Required reviewers：1 人
4. 首次发布可先去 TestPyPI 同样配置一遍（environment name 用 `test-pypi`）

**触发发布**：
```bash
git tag v0.1.0
git push origin v0.1.0
# → release.yml 自动 build + publish
```

**最终状态**
- 测试 467 passed / coverage 90.07%（不变 — 仅打包）
- ruff / isort / black / mypy strict 全清
- twine check 全 PASSED
- fresh venv smoke test OK
- wheel 路径：`dist/autoc-0.1.0-py3-none-any.whl`

**文件清单**（5 个文件）
- 新：`packages/autoc/LICENSE`（MIT 全文）
- 新：`CHANGELOG.md`（根目录）
- 新：`.github/workflows/release.yml`（trusted publishing）
- 改：`packages/autoc/pyproject.toml`（+project.urls + 7 classifiers + 3 keywords）
- 改：`packages/autoc/README.md`（Sprint 0+1 → 0.1.0 全刷；PyPI long_description 用）

**下一个 sprint**：Sprint 8.C — VSCode 扩展 vscode-autoc（把 `autoc` CLI 包成 VSCode 扩展） / Sprint 8.D — 文档收尾（CHANGELOG 入 plugin docs；plugin commands 链接审计） 二选一。



