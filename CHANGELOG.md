# Changelog

All notable changes to `autoc` (the Python core package) are documented in
this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
