# AutoC Claude Code 插件 - 进度交接文档

> 给"换窗口后继续干"用的状态快照。最后更新：2026-06-11。

## 换窗口继续（直接说这句就行）

> **"继续 autoc-cc，从 Sprint 4 开始"**

或更直接：

> **"跑 Sprint 4 任务 T4.1"** → 我开干
> **"先 git init"** → 我先 `git init` + 首 commit

## 一句话状态

**Sprint 0+1+2+3（plan 中）全部完成，266 测试通过，coverage 86.42%，所有 lint/mypy 干净。**

下一个待办是 **Sprint 4（plan 中）**：会话存储/树/导出 + changelog + `cli/commands/{session,export,log}.py`。

## 当前 HEAD 状态

- **git**: 仓库未 init（前面 sprint 都没初始化；如要 git 化让我先 `git init`）
- **测试**: 266 passed / 86.42% coverage
- **静态检查**: ruff / isort / black / mypy strict 全干净
- **安全**: bandit -ll 0 high / 0 medium（6 low 全部 pre-existing subprocess 模式）
- **分支头**: 工作区，HEAD = 工作区文件

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

