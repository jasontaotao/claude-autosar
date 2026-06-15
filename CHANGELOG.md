# Changelog

All notable changes to `claude-autosar` (the Python core package, formerly `autoc`) are
documented in this file. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
