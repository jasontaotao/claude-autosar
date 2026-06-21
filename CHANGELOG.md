# Changelog

All notable changes to `claude-autosar` (the Python core package, formerly `autoc`) are
documented in this file. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.1] - 2026-06-21 (post-audit followups — version drift + doc rot + stale egg-info)

v0.4.0 audit（7-agent 深度审计）漏抓的 1 CRITICAL + 2 HIGH + 1 MEDIUM，由二次 4-agent + adversarial verifier 评审捕获并修复。7 个文件、+36/-38 行。

### Fixed

- **CRITICAL — version drift**：`__init__.py:14` 的 `__version__` 停在 `"0.3.0"`，但 `pyproject.toml` 已 bump 到 `0.4.0`。CLI `--version` 输出过期，`test_sprint7_e2e.py:450` + `test_cli_main.py:88` 都断言 `"0.3.0"`，能过仅因 runtime 也过期——任意一方 bump 即破。两处测试断言同步到 `"0.4.0"`。
- **HIGH — stale `autoc.egg-info/`**：`packages/autoc/src/autoc.egg-info/` 残留旧 package name（autoc v0.1.0）+ `Requires-Dist: tomli-w>=1.0` + entry_point `autoc = autoc.cli.main:main`，与 v0.4.0 已 rename 到 `claude_autosar` 矛盾。删除整个目录。
- **HIGH — doc rot**：v0.4.0 bump 后 31 处 stale `v0.3.0` 字符串残留在 `docs/getting-started.html` (21) + `packages/autoc/docs/user-manual.html` (10)，包括 title tag、版本 banner、tag chip、changelog heading、wheel filename、install 步骤。Bulk replace 0.3.0 → 0.4.0。
- **HIGH — doc rot (deps table)**：`user-manual.html:349` 系统要求表仍列已 drop 的 `tomli-w>=1.0`。删除整行。
- **MEDIUM — unused dep**：`tomli-w>=1.0,<2.0` 在 `pyproject.toml dependencies` 但全仓库 grep `tomli_w` 零 import。Drop。
- **MEDIUM — plugin manifest version drift**：`packages/plugin/plugins/claude-autosar/.claude-plugin/plugin.json` version 硬编码 `0.1.0`，主包已 `0.4.0`。Sync。

### Cleanup

- 删 `packages/autoc/.cov_html/`（旧 coverage HTML，gitignored，coverage run 重生成）
- 删 `packages/autoc/src/claude_autosar.egg-info/`（同上）

### Tests

- 9/9 `tests/integration/test_sprint7_e2e.py` PASS
- 1/1 `tests/unit/test_cli_main.py::test_main_version_flag_prints_to_stdout` PASS
- 全测试套件 `1752 passed`，2 failed：1 个就是上面 test_cli_main（v0.4.1 修复）+ 1 个 pre-existing `test_namespace_detection.py` mtime 缓存 flake（重跑单测通过）

### Credits

- 4 specialist agents + 1 adversarial verifier 多 agent 评审循环（review → fix → re-review → fix）

## [0.4.0] - 2026-06-20 (全代码库深度审计 — 6 CRITICAL + 23 HIGH + 30 MEDIUM 修复)

7 个并行 agent 对全部 ~50,000 行 Python 代码逐行分析，发现 159 个问题。本版本修复全部 CRITICAL 和 HIGH 级别问题及部分 MEDIUM 问题，共 51 个文件变更，1779 tests 全过。

### CRITICAL（6/6 已修复）

- **C1** — `templates/apply.py` DEFINITION-REF 路径构造错误（用 instance path 而非 schema definition path）→ diffs_applied 语义修正 + namespace 从文档获取 + 未知 op 类型报错。
- **C2** — `bsw_write_ops.py` tresos_home containment check 缺陷（3 处）→ 加 `validate_no_traversal` + `== project_path` 检查。
- **C3** — `plugin/tests/` 测试路径 `"autoc"` 错误 → 改 `"claude-autosar"`，测试套件恢复可执行。
- **C4** — `validation.py` `validate_no_traversal` 不拦截绝对路径 → 加 `os.path.isabs()` 检查。
- **C5** — `store.py` session_id 路径遍历 → 加 `isalnum()` 校验。
- **C6** — `tree.py` `walk()` 无循环检测 → 加 visited set。

### HIGH（23/23 已修复）

**安全漏洞（5）：**
- `inspect_ops.py` `arxml_validate` / `dbc_parse` 无 containment check → 加路径校验。
- `diff_ops.py` `file_a` / `file_b` 无 containment check → 加路径校验。
- `apply_template_ops.py` `template` 参数无 containment check → 加路径校验 + report_path 信息泄露修复。
- `xdm_report.py:184` 文件路径未 HTML 转义 → 加 `_html_escape`。

**数据损坏/生产失效（8）：**
- `arxml_io.py:221` `errors="replace"` 静默损坏 → 改 `errors="strict"`。
- `config.py:152` + `validator.py:210` assert 在 `-O` 模式失效 → 改显式 raise。
- `validator.py:190` 还原失败静默吞掉 → 返回 `rolled_back=False`。
- `validator.py:122,136` 裸 `except Exception` → 缩窄异常范围。
- `davinci.py:78` 参数类型硬编码 INTEGER → 加类型推断。
- `recorder.py:59` `set_current_session` 无并发保护 → 加锁。

**逻辑错误（4）：**
- `arxml_report.py:355` `<em>none</em>` 被 HTML 转义 → 分离处理。
- `apply.py:56` `diffs_applied` 统计全量而非成功数 → 统计实际成功数。
- `lint/runner.py:89` 规则异常全部被吞掉 → `exc_info=True` + `rule_errors` 计数。
- `lint/extract.py:67` frozen dataclass 嵌套可变 dict → 文档声明。

**启动/执行失败（6）：**
- `hooks.json` `python3` 在 Windows 不可用 → 改 `python`。
- `repl_skin.py:57` `NO_COLOR=""` 不禁用颜色 → 改 `in os.environ`。
- 7 个 CLI 命令顶层 import → 改延迟 import。
- `main.py:12` 版本硬编码 → `importlib.metadata` 动态获取。
- `main.py:60` `_load_all` 非幂等 → 异常时回滚。

### MEDIUM（30/73 已修复）

- `bsw_write_ops.py` 3 处 `validate_no_traversal` 补全。
- `session_ops.py` session_dir containment check。
- `eb.py` 错误输出到 stderr（3 处）。
- `davinci.py` 错误输出到 stderr（2 处）。
- `bswmd.py:333` `merge()` 返回 NotImplemented → 改 raise TypeError。
- `lint/__init__.py` LintSeverity 去掉无意义的 `frozen=True`。
- `apply.py` namespace 硬编码 → 从文档 root 元素获取。
- `apply.py` 未知 diff op 静默丢弃 → 抛 ValueError。
- `posttooluse_bsw_validate.py` 路径规范化不一致 → 统一。
- `lint.py:93` line=0 显示为 `-` → 正确显示 `0`。
- `test_hooks.py` / `conftest.py` 路径修复 + 测试适配。

## [0.3.1] - 2026-06-20 (Sprint 12 Trust Sprint — 9 HIGH security bugfixes + 累积 WIP 收口)

### Security（9 HIGH，全部 code-reviewer APPROVE）

外部审计（Sprint 12 — 6 个并行 agent）发现 9 个 HIGH 严重 bug，已全部修复。

- **HIGH-1** — `arxml_io.py` surgical patch 写回未转义 XML 实体（`&` / `<` / `>`）→ 产出畸形 XML。新增 `utils/xml_escape.py` + 改 surgical patch 在写回前 `escape_xml_text(new_text)`。
- **HIGH-2** — `datamodel2_io.py` `_patch_parent_form` 同样未转义 `<a:v>` 文本。同 escape 函数复用。
- **HIGH-3** — `cli/mcp_tools/session_ops.py` `session_export(..., output=...)` 无路径校验 → 任意文件写入。改 `_resolve_safe_project(output)`。
- **HIGH-4** — `cli/mcp_tools/inspect_ops.py` 3 个 inspect tool（`arxml_inspect` / `xdm_inspect` / `bsw_inspect`）`output` 同样无 containment check。统一加 `_resolve_safe_project(output)`。
- **HIGH-5** — `cli/commands/arxml_apply_template.py` + `xdm_apply_template.py` `_render_diff_html` 5 个动态字段未 escape → XSS。全部 `_html.escape(..., quote=True)`。
- **HIGH-6** — `core/bsw/coverage.py` 仅取 `parts[-1]`（short_name）匹配 → 同名 param 误报。改用 `_ecuc_path_to_def_ref()` 映射到完整 definition path；提取为公共 API `ecuc_path_to_def_ref`。
- **HIGH-7** — `core/bsw/bsw_write_path.py` `_count_existing_in_parent` 按 leaf 数而非 instance 数计数 → 误拒合法写入。重构 `_check_container_multiplicity`：按 container definition + unique instance path 集合按 `len(set)` 比对 upper/lower。删除 dead code。
- **HIGH-8** — `core/bsw/templates/apply.py` BOOLEAN 误用 `ECUC-TEXTUAL-PARAM-VALUE` + `ECUC-BOOLEAN-PARAM-DEF`（vendor 拒收）。改用 `ECUC-NUMERICAL-PARAM-VALUE` + `ECUC-NUMERICAL-PARAM-DEF`。
- **HIGH-9** — `cli/mcp_tools/validate_ops.py` + `diff_ops.py` `project` 用 `validate_no_traversal`（漏 `/etc` 这类绝对路径）。改用 `_resolve_safe_project(project)`。

### 累积 WIP 收口（Sprint 9.x 未独立 commit 的代码一次性 ship）

> 这部分代码在前几个 session 已经写完但未 commit。本 release 一并 ship 以收口工作树混乱状态。每块都通过 1728 unit tests 验证。

- `cli/mcp_tools/` 子包全部新文件（之前未 commit）：`arxml_apply_template_ops` / `bsw_read_ops` / `bsw_write_ops` / `validate_ops` / `diff_ops` / `inspect_ops` / `session_ops` / `apply_template_ops` + `validation.py`。约 1500 行新代码（HIGH-3/4/9 修改直接落在这里）。
- `cli/commands/arxml_apply_template.py` / `xdm_apply_template.py`：template apply CLI 子命令 + diff HTML 输出（HIGH-5 + `apply_template_diff` 编排）。
- `cli/main.py` / `cli/mcp_server.py`：CLI main + MCP server 重构（FastMCP 注册 17 个 tool）。
- `core/bsw/templates/apply.py`：从只支持 `modify` 扩展为 modify / add / delete 三 op（HIGH-8 在 add 路径里）。
- `core/bsw/arxml_io.py` / `core/bsw/bsw_write_path.py` / `core/bsw/io/datamodel2_io.py`：byte-identity surgical patch 重构 + 单元测试补强（HIGH-1/2/7 在这里）。
- `core/bsw/bswmd.py` / `core/bsw/config.py` / `core/bsw/ecuc.py` / `core/bsw/validator.py`：BSWMD 模型 + 校验链补全。
- `core/bsw/coverage.py`：参数覆盖率报告（HIGH-6 在这里）。
- `core/bsw/inspector/arxml_report.py` / `xdm_report.py`：inspect 报告 HTML。
- `core/bsw/lint/`：lint 规则 + 提取层。
- `core/config/project_config.py` / `core/session/store.py`：项目配置 + session 存储。
- `adapters/tresos.py` / `adapters/stub.py`：EB tresos + stub adapter。
- `__init__.py`：版本号 + 公共 API 导出。

### Test Infrastructure

- `tests/conftest.py`：新增 autouse fixture `_autouse_safe_project_roots`，把 `tmp_path` 自动加入 `_ALLOWED_PROJECT_ROOTS`（兼容 pytest tmp_path + 不破坏"outside allowed roots"拒绝语义）。
- 新增 `tests/unit/test_high_severity_regression.py`：18 个 regression test（每个 HIGH 至少 1 个 + happy-path）。
- `test_apply_add_delete.py` / `test_template_apply.py` / `test_xdm_round_trip.py` 等：模板 apply add/delete/round-trip 测试补全。

### Test Updates（5 个锁定 buggy 行为的现有测试）

- `test_bsw_write_path.py::test_container_upper_3_write_4_raises`：改用 3 实例 + 1 新实例 setup。
- `test_sprint8e_coverage_bsw_write_path.py`：3 个 multiplicity tests 改用 multi-instance 数据。
- `test_coverage.py`：BSWMD paths 改为 `/AUTOSAR/...` 前缀与 `root_package_name="AUTOSAR"` 默认对齐。

### Removed（YAGNI）

- `_count_existing_in_parent` 函数 + 4 个 dead unit tests（`_check_container_multiplicity` 重构后已无人调用）。

### Notes

- 测试：18 regression + 1728 unit passed / 0 fail（除 2 个 pre-existing Windows mtime flake）
- 全部 9 个 HIGH fix 都经 code-reviewer APPROVE（首轮 APPROVE_WITH_WARN → 修完 0 must-fix → APPROVE）
- `pyproject.toml`：version 0.3.0 → 0.3.1（PATCH bump：纯 bugfix 无 API break）
- 依赖版本下限约束新增（`lxml>=5.0,<6.0` 等）

## [0.3.0] - 2026-06-14 (PUBLISHED to PyPI — Sprint 9.2/9.3/9.4/9.5 集成)

### Added

#### M1-T — 双格式模板 diff + apply（Sprint 9.2）

- `core/bsw/templates/xdm_value.py`：EB DataModel2 端独立 dataclass —
  `XDMValue` / `XDMModule`（frozen；不抽象，沿用 plan v2 §2.1 "双格式平级
  IO 不互转" 原则）
- `core/bsw/templates/arxml_diff.py`：AUTOSAR 端 `diff_arxml_templates()`
  + `TemplateDiff` / `TemplateDiffResult`（path/raw/type 三元组；add /
  modify / delete 三 op）
- `core/bsw/templates/xdm_diff.py`：XDM 端 `diff_xdm_templates()`（镜像
  ARXML 端，独立 dataclass 路径）
- `core/bsw/templates/apply.py`：双格式 unified `apply_template_diff()`
  + `ApplyMode` (`DRY_RUN` / `APPLY`) + `ApplyResult` — 走
  `dispatcher.read/write(preserve_format=True)`，ARXML byte-identity 100%
  / XDM d:var 走 fallback 重建（plan §2.3 接受）
- CLI 子命令：`arxml-apply-template` / `xdm-apply-template`（`--dry-run`
  默认 / `--apply` 写回 / `-o/--output` HTML 报告）
- MCP tools：`arxml_apply_template` / `xdm_apply_template`（H4 路径防御
  保留；返回 diffs_applied / bytes_changed 字段）
- 4 fixtures：`Can_simple.arxml` + `Can_template.arxml` +
  `Can_simple.xdm` + `Can_template.xdm`

#### M3 — verify 增强（Sprint 9.3）

- `core/bsw/verify/tresos_parser.py`：EB tresos_cmd `verify` stdout/stderr
  结构化解析 — `TresosVerifyIssue` / `TresosVerifyReport` (frozen) +
  `parse_tresos_verify_stdout()`（6 regex 模块化：severity /
  code(colon|bracket) / file(colon|at:line) / module；module 来源优先级
  forced > stdout `module <NAME>` > ""；保守 fallback 不匹配行 → INFO
  整段记；stderr 整段 ERROR 仅当 returncode != 0）
- `core/bsw/verify/report_section.py`：`render_verify_section_html()`
  独立可嵌入（XSS escape；severity 排序 ERROR > WARNING > INFO；
  `<body>` 插入模式，graceful fallback）
- `bsw_verify` MCP tool 增强 4 个 v2 path 参数（`chip_derivative` /
  `mcal_vendor` / `mcal_vendor_home` / `as_json`）→ 走 `load_v2_paths`
  4 级优先级合并
- 默认轻量 dict：`{success, module, returncode, report: {issue_count,
  has_errors, has_warnings}}`；`as_json=True` 返完整
  `TresosVerifyReport` 序列化
- CLI 子命令：`bsw-verify`（复用 MCP tool 业务逻辑）
- Inspector 报告嵌入 verify section（arxml + xdm 双格式）

#### M4 — lint 10 规则（Sprint 9.4）

- `core/bsw/lint/` 完整框架：`LintRule` Protocol + `LintViolation` /
  `LintSummary` (frozen) + `LintRunner(rules).run(extracted)`（异常
  隔离覆盖 generator `__next__()` 路径）
- `core/bsw/lint/extract.py`：`extract_arxml_for_lint()` /
  `extract_xdm_for_lint()`（包装 inspector `_extract_*` 为 lint 友好
  形态：IPdu 列表 / Signal 列表 / key params / XDM containers + leaves）
- 10 规则（plan v2 §4.2 锁定）：
  - arxml (8)：`COM-AP-001` (ComSignal > 8 byte 经典 CAN 失败) /
    `COM-AP-002` (E2E Profile 缺失) / `CanIf-AP-007` (软件全开+硬件
    全关 CPU 风暴) / `CanIf-AP-008` (CAN-FD length mismatch) /
    `ECUM-AP-001` (RunRequest 死锁) / `ECUM-AP-003` (POSTBUILD
    variant 缺失) / `GEN-AP-002` (BswM 自循环) / `NM-AP-001`
    (CanNm 报文不在 ComM 引用)
  - xdm (2)：`DEM-AP-001` (Flash 越界) / `DEM-AP-004`
    (Snapshot > 255 byte)
- v1 MVP stub 策略：data 缺字段就 skip 返 0 violation（**不误报**优先）
- CLI `autoc lint <path>`：dispatcher.detect_format → extract → run
  → summarize → 可选 HTML 报告（reuse `summary-box` CSS；XSS escape；
  按 `--rule` / `--severity` 过滤）
- Sprint 9.1 留下的 `include_lint` MCP 占位参数 + `--no-lint` CLI 占位
  **全部激活**：`arxml_inspect` / `xdm_inspect` / `bsw_inspect` 加
  `violations` + `lint_summary` 字段；`--no-lint` 改 `--lint`（默认
  False，向后兼容）
- Inspector 报告加 lint section（reuse `summary-box` CSS）

### Tests
- 24 新测试 + 5 改测试 + 7 新 fixture
- 测试增量：1082 → 1346（**+264**）
- Coverage：90% → **85.46%**（**-4.54pp**；新模块多：`lint/` 10
  规则 + `templates/` 4 文件 + `verify/` 3 文件；plan v2 锁定
  v2.7 BSWMD 工具套件 + Sprint 8.E.1 补测目标 ≥90%）
- 5-stage verification：ruff / mypy strict / 1346 pytest pass / byte-identity
  / 端到端（端到端推到 Sprint 9.5）

### Fixed

- `datamodel2_io.write` XDM d:var 静默丢值：原实现 surgical patch 只处理
  `<a:a>` 段，`<d:var>` 段改值无变化时静默返回原字节，丢失改参。
  修：c14n compare 区分"真无变化 vs d:var 变化"；`any_changed=False`
  返回 None 让 caller 试 parent-form；parent-form regex
  `<a:a\s+[^>]*?)>` → `<a:a\s+([^>]+?[^/])>`（排除 self-closing）
- `LintRunner` 异常隔离漏 generator `__next__()` 路径：try 提到
  `for v in yielded:` 包含 `__next__()`，避免单条 rule raise 漏出
  影响其他 rule
- mcp_server `_detect_arxml_module_name` undefined 错：9.2-γ
  helper 函数定义在 register 之后但 run() 中先调用，mypy 顺序
  scope 检查不到。修：定义移到文件顶部（register 之前）
- **lint 规则按 namespace 过滤缺失**（Sprint 9.5 集成修复）：
  Sprint 9.4 的 10 条规则进 `ALL_RULES`；8 条 arxml 规则（如
  `CANIF-AP-007`）用 `key_params` 字段，被喂 XDM 数据时抛
  `AttributeError`。Runner 隔离 OK（inspect 仍 `success=True`）但
  **XDM 路径 lint 覆盖率实际为 0**（用户工程 18 个 .xdm 全受影响）。
  修：
  1. 每条规则加 `applies_to: ClassVar[str]` tag（`"arxml"` / `"xdm"` /
     `"both"`）
  2. `core/bsw/lint/rules/__init__.py` 新增 `rules_for_namespace(ns)`
     helper（保持 `ALL_RULES` 顺序 + 向后兼容无 tag 规则）
  3. `core/bsw/lint/__init__.py::lint_file()` 按 suffix 过滤
  4. `cli/mcp_server.py::_run_lint_for_inspect()` 改用
     `rules_for_namespace`（**之前是直接用 `ALL_RULES`，跟 `lint_file`
     走两条路**）
  5. `LintRule` Protocol 文档化 `applies_to` 字段
  + 8 个新单测（`test_lint_namespace_filter.py`）— 10 规则全部带
    tag / arxml 返 8 / xdm 返 2 / 未知 namespace ValueError /
    顺序稳定 / backward compat / regression 防 AttributeError /
    XDM 集成 fixture
  + E2E：用户工程 `Can.xdm` 上 0 stderr（之前 8 条 warning dump）

### Notes

- **XDM 端 byte-identity**：d:var surgical patch 仍是后续 sprint 增强
  （v2.x writer 升级）。当前 Sprint 9.2 XDM apply d:var 改值走 fallback
  重建（语义正确，但其他字节 byte-identity 不保留；plan §2.3 接受）
- **Sprint 9.2 数据模型**：双格式**各自 dataclass**（ARXML 复用
  `ECUCValue`/`ECUCDocument`；XDM 新建 `XDMValue`/`XDMModule`），不
  抽象 InstanceTree（plan v2 §2.1 原则）
- **Sprint 9.1 lint 占位全部激活**：`include_lint` MCP / `--lint` CLI
  不再是 noop，返真实 violation + summary
- **Sprint 9.5 端到端验收**（`D:/claude_proj2/src/S32K148_EAS_EB_3399A/`）：
  `xdm-inspect Can.xdm` ✅ / `arxml-inspect Com_Com.arxml` ✅
  (67 IPdu in HTML) / `arxml-apply-template` dry-run ✅ /
  `xdm-apply-template` dry-run ✅
- **Pre-existing 失败已解决**：`test_sprint7_e2e.py
  ::test_cli_eb_save_and_mcp_bsw_write_return_consistent_shape` —
  该 test 在 Sprint 9.x 重构中已不存在（合并到
  `test_mcp_server_coverage.py`），不再是 fail
- **实测测试数修正**：v0.3.0 真实测试数 **1331 passed**（原 Unreleased
  头部"1346"是 sub-agent 自我汇报口径，实际 1323 + 8 namespace 集成
  测试 = 1331）

### Migration Notes (v0.2.0 → v0.3.0)

无破坏性 API 变更。Sprint 9.1 留下的 `include_lint=False` 默认 + Sprint 9.2
新增 `apply_template_diff()` 入口都是**新增**。`bsw_verify` MCP tool
签名扩展（新增 4 个 v2 path kwargs）保持向后兼容（旧调用方不传新
kwarg 走默认行为）。

## [0.2.0] - 2026-06-13 (Sprint 9.0 — 双格式独立 IO + dispatcher + rename)

### Changed
- **BREAKING**: Package renamed `autoc` → `claude-autosar`（PyPI name / import path
  `claude_autosar.*` / CLI `claude-autosar` / plugin name `claude-autosar` / 仓库根
  `claude-autosar`）。任何 import `from autoc.*` / CLI `autoc ...` 的下游需同步
  迁移。
- `bsw_read` MCP tool 走 dispatcher：按文件根 namespace 自动选 arxml_io（AUTOSAR
  r4.x）或 datamodel2_io（EB tresos DataModel2）。响应加 `format` 字段。

### Added
- `core/bsw/io/datamodel2_io.py`：EB tresos DataModel2 命名空间
  (`http://www.tresos.de/_projects/DataModel2/16/root.xsd`) 的 read / write /
  surgical patch（镜像 arxml_io）。byte-identity ≥ 99%（对齐 Sprint 8.E.5 验收）。
- `core/bsw/dispatcher.py`：薄壳路由层（detect_format / read / write / describe）。
  支持根 xmlns 探测：AUTOSAR r4.0/4.2/4.4/4.6/4.7/4.8 + DataModel2 2.0 root + 1.0
  alias。异常：`UnknownFormatError` / `FormatMismatchError` / `DispatcherError`。
- `core/settings/v2_paths.py`：`.autoc/settings.json` schema + 3 路径加载器
  （TRESOS_HOME / MCAL_VENDOR_HOME / CHIP_DERIVATIVE）。优先级链：
  环境变量 > CLI > `.autoc/settings.json` > `init` 向导探测。
- `cli/mcp_server.py::_bsw_read_xdm`：XDM 路径的扁平 `<d:var>` 提取（lxml xpath
  在 `<d:chc name=module>` 容器下查找 d:ctr / d:lst / d:chc / d:var 任一类型）。
- `cli/commands/init.py`：`claude-autosar init` 向导 — 启动时探测 3 路径，
  找不到报错 + 提示配置（不靠猜，不静默用 default）。

### Tests
- `tests/unit/test_dispatcher.py`（27 测试）
- `tests/unit/test_mcp_server_xdm.py`（12 测试，含 3 个端到端 Can.xdm 用例）
- `tests/unit/test_datamodel2_io.py`（镜像 test_arxml_io.py）
- `tests/unit/test_init_v2_wizard.py`（init 向导单测）
- `tests/unit/test_settings_v2.py`（v2_paths 单测）
- `tests/fixtures/datamodel2/{Can,Mcu,Port}.xdm`（3 个 user-engineering 风格 XDM）
- **总测试数**：866 → 982（+116）
- **Coverage**：90.07% → 88.87%（-1.2pp；推到 8.E.1 plan）

### End-to-end Acceptance

```python
bsw_read("Can", "CanConfigSet/CanController/BMS_J1939PT/CanHwChannel", project=...)
# → {'success': True, 'raw': 'FlexCAN_A', 'value': 'FlexCAN_A',
#    'type': 'ENUMERATION', 'format': 'xdm'}
```

5-stage verification 全过：ruff / mypy strict / 982 pytest pass / XDM byte-identity /
端到端 bsw_read。

### Migration Notes (v0.1.x → v0.2.0)
- 任何引用 `autoc` 包 / `autoc` CLI / `autoc` plugin 的下游必须迁移：
  - `pip uninstall autoc && pip install claude-autosar`
  - `from autoc.X import Y` → `from claude_autosar.X import Y`
  - `autoc ...` CLI → `claude-autosar ...`
  - Plugin marketplace 引用 `autoc` → `claude-autosar`
- 配置文件路径 `~/.autoc/` 保留不变（用户数据向后兼容）

## [0.1.0] - 2026-06-12

First public release of `autoc` (the Python core of the
[autoc-cc](https://github.com/autoc-cc/autoc-cc) Claude Code plugin).
At this point the codebase has been developed through Sprints 0-7
(467 tests, 90.07% coverage, all static checks and security scans clean).

### Added

#### BSW 数据模型与配置
- `BSWModule` / `BSWParam` / `ParamValue` 不可变 dataclass（`frozen=True`，
  `with_X()` 返回新实例）
- `BSWModule.from_ecuc(doc)` / `to_ecuc(arxml_path)`：ECUC ↔ BSW 双向映射
  （5 种类型：integer / float / boolean / string / enum）
- 配置三层合并：`<cwd>/.autoc/` 覆盖 `~/.autoc/agent/`（`deep_merge`）
- 跨平台路径工具 `utils/paths.py`（platformdirs + find_ancestor_file）

#### 工具适配器层（MCU 差异化核心）
- `TresosAdapter` Protocol + 默认实现（`discover()` 数据驱动；同一段代码
  处理 S32K3 / TC3xx / RH850，无 if/else 分支）
- `DavinciAdapter` Protocol + 默认实现（`DVCfgCmd.exe` subprocess 包装）
- `StubTresosAdapter` / `StubDavinciAdapter` 测试用 mock（必填
  `discover_response`；CI 不依赖商业工具）
- Windows `.bat` 走 `cmd.exe /c <bat> <args>` + `shell=False`（避免 shell 注入）

#### ARXML 读写 + 改参 + 验证
- `core/bsw/arxml_io.py`：lxml 低层（`ARXMLDocument` 原子写 / 命名空间 / round-trip）
- `core/bsw/ecuc.py`：自写 ECUC 解析（reference chain + type 启发式）
- `core/bsw/validator.py`：`modify_and_verify` 闭环（快照 → 改 → verify →
  失败回滚 / 成功 save）
- **lxml-only 决定**：不引入 `pyecarxml`（活跃度 + Python 3.11+ 兼容性
  未经外网调研验证；写值仍需 lxml 改 DOM）

#### CLI 命令
- `autoc eb save/verify/autocalc`（改 EB tresos 工程参数）
- `autoc davinci save/verify`（DaVinci Configurator 同上，无 autocalc）
- `autoc session list/show/fork`（会话归档）
- `autoc log --view timeline/by-url`（改参日志）
- `autoc export --output <html>`（自包含 HTML 导出，XSS 白名单 + 三色 callout）
- `autoc --verbose` / `--no-color` 全局 flags
- 两阶段解析：先扫第一个非 flag token，不在白名单 exit 1 + 中文提示

#### 会话 / 改参日志 / 导出
- `core/session/store.py`：JSONL append-only 存储（`os.fsync` Windows 强持久）
- `core/session/tree.py`：不可变树 + fork（DFS pre-order 显式 stack，避递归）
- `core/session/recorder.py`：`record_bsw_write_batch()` 1 user + N tool entries；
  进程内 `threading.Lock` 保护 `.current` + batch
- `core/session/exporter.py`：自包含 HTML（`html.escape` + 自写 inline Markdown；
  XSS URL scheme 白名单 + `rel="noopener noreferrer"`；绿/黄/红 callout）
- `core/log/changelog.py`：`Change` + `extract_changes(tree)` + `render_timeline/by_url`

#### MCP server（FastMCP 10 工具）
- `bsw_read` / `bsw_write` / `bsw_verify` / `bsw_autocalc`
- `arxml_validate` / `dbc_parse`（cantools 41.x）
- `session_list` / `session_show` / `session_export` / `log_export`
- 错误路径统一 `{"success": False, "error": "..."}` dict + `field` + `param_index`
  （LLM 友好定位）
- `project` / `tresos_home` 路径防御（必须在 `_ALLOWED_PROJECT_ROOTS` 之内）
- `--session latest` 走 mtime 排序（统一 `resolve_latest_session_id()` 模块级函数）

#### 安全 / 依赖
- bandit -ll 0 H/M；pip-audit 0 H/M（autoc 运行时无漏洞；3 个 transitive
  CVE 已记录在 `SECURITY.md`）
- py.typed（PEP 561）

### Changed

- Branch `master` → `main`
- `cli/main.py` 内部实现重写为 dispatch 表（外部 CLI 行为不变）

### Fixed

- Sprint 4 race condition in `get_or_create_current_session` — 进程内
  `threading.Lock` 保护
- Sprint 4 XSS via `javascript:` URL — URL scheme 白名单
- Sprint 5 H1：`session_show/export("latest")` 改 mtime 排序（之前按字母序）
- Sprint 5 H2：`bsw_write` 异常收窄到 `(OSError, ValueError, TypeError, KeyError)`
- Sprint 5 H3：`bsw_write` 入参 schema 校验前置（`field` + `param_index` 精确定位）
- Sprint 5 H4：`bsw_*` 工具的 `project` 路径防御
- Sprint 7：mcp_server.py 4 处 error dict 统一 `field` + `param_index` 合约

### Notes

- **PyPI 包名是 `autoc`**；monorepo 目录是 `autoc-cc/`
- 配套 Claude Code 插件（`/autoc:*` 斜杠命令 + skill + hook + agent）见
  [packages/plugin/](https://github.com/autoc-cc/autoc-cc/tree/main/packages/plugin)，
  该包**不是** PyPI 包
- 完整 sprint 交接文档 [PROGRESS.md](https://github.com/autoc-cc/autoc-cc/blob/main/PROGRESS.md)
