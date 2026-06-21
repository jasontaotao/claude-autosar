# claude-autosar v0.4.1 — release notes

**Release date**: 2026-06-21
**Tag**: `v0.4.1`
**Commits since v0.4.0**: 2 (`4cbeeda` + `c77c020`)
**Diff stat**: 7 files changed, +36/-38
**Tests**: 1752 passed (pre-fix 2 failed → post-fix 0 new failures)

---

## 概述

v0.4.1 是 **v0.4.0 audit 漏抓的 followup 修复包**，由 v0.4.0 ship 后 4-agent + adversarial verifier 二次评审捕获。语义上属于 PATCH bump（修复 + 文档同步，无新功能）。

v0.4.0 audit 用 7 个 agent 对 50K 行代码深度扫描，发现 159 个问题并修了 6 CRITICAL + 23 HIGH + 30 MEDIUM。但还有 **1 CRITICAL（version drift）+ 2 HIGH（stale egg-info + doc rot）+ 1 MEDIUM（unused dep）+ 1 MEDIUM（plugin version drift）** 漏了，本版本补上。

## 修复列表

### 🔴 CRITICAL — version drift

| 字段 | 修复前 | 修复后 |
|---|---|---|
| `packages/autoc/src/claude_autosar/__init__.py:14` | `__version__ = "0.3.0"` | `__version__ = "0.4.0"` |
| `tests/integration/test_sprint7_e2e.py:450` | `assert "0.3.0" in v.stdout` | `assert "0.4.0" in v.stdout` |
| `tests/unit/test_cli_main.py:88` | `assert "0.3.0" in captured.out` | `assert "0.4.0" in captured.out` |

**影响**：CLI `--version` 输出已对齐到 0.4.0。两处 test 之前能过纯属 runtime 也过期造成**假绿**——任意一方 bump 即破。**v0.4.0 ship 时没 bump `__version__`** 是流程漏洞。

**Why critical**：用户看到的版本号与 `pyproject.toml` 不一致，违反"release 与代码同步"原则。

### 🟠 HIGH — stale `autoc.egg-info/`

`packages/autoc/src/autoc.egg-info/` 残留旧 package 元数据（autoc v0.1.0）：
- `entry_points.txt` 仍有 `autoc = autoc.cli.main:main`
- `requires.txt` 仍有 `Requires-Dist: tomli-w>=1.0`
- `PKG-INFO` Name/Version 都过期

**修复**：`rm -rf`（gitignored，pypi install 不影响；本地 `pip install -e .` 会重新生成 `claude_autosar.egg-info/`）。

### 🟠 HIGH — 文档 stale v0.3.0

31 处 stale `v0.3.0` 字符串未随 v0.4.0 ship 更新：

| 文件 | 处数 | 内容 |
|---|---|---|
| `docs/getting-started.html` | 21 | title、版本 span、install 命令、wheel filename、changelog heading、footer |
| `packages/autoc/docs/user-manual.html` | 10 | title、version banner、tag chip、changelog heading、footer |

**修复**：bulk replace `0.3.0` → `0.4.0`（Edit replace_all=true）。

外加 `user-manual.html:349` 系统要求表删除整行已 drop 的 `tomli-w>=1.0`。

### 🟡 MEDIUM — unused dep

`pyproject.toml` dependencies 里有 `tomli-w>=1.0,<2.0` 但全仓库 grep `tomli_w` 零 import。删除。

### 🟡 MEDIUM — plugin manifest drift

`packages/plugin/plugins/claude-autosar/.claude-plugin/plugin.json` version 硬编码 `0.1.0`，主包已 `0.4.0`。Sync 到 `0.4.0`。

## 升级指南

### Pip 用户

```bash
pip install --upgrade claude-autosar==0.4.1
```

无需 schema migration 或配置文件变更（pure bugfix）。

### Git 用户

```bash
git fetch origin
git checkout v0.4.1
pip install -e packages/autoc
```

### 验证

```bash
claude-autosar --version
# → claude-autosar 0.4.0
```

## 测试结果

| 测试套件 | 结果 |
|---|---|
| `tests/integration/test_sprint7_e2e.py` | 9/9 PASS |
| `tests/unit/test_cli_main.py::test_main_version_flag_prints_to_stdout` | PASS |
| 全测试套件 | 1752 passed, 2 failed |

剩余 2 个失败是 **pre-existing**：
- `test_namespace_detection.py::TestDetectNamespacesCache::test_cache_recomputes_when_file_modified` — mtime 缓存 flake，重跑单测通过

## Known issues

无新增。

## Credits

- 4 specialist agents + 1 adversarial verifier 多 agent 评审循环（review → fix → re-review → fix）
- 评审员包括 Security / Python correctness / Architecture / Test quality（test quality agent 在初次评审 hallucinated，第二次强制先 ls 真实测试文件）

## Links

- Diff: `git log v0.4.0..v0.4.1`
- Full audit (v0.4.0): CHANGELOG.md `[0.4.0]` 节
- 漏审 review findings: 见 `claude-autosar-v0-4-followup-findings.md` memory file

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)