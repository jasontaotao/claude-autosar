---
name: change-traceability
description: |
  改参留痕与会话回放。JSONL append-only 会话存储、timeline 视图、by-url 视图、HTML 导出。
  触发词：「会话」「session」「timeline」「by-url」「留痕」「回放」「export」「changelog」「diff」。
---

# 改参留痕与回放

## 设计目标

- 每次 `bsw_write` 记录到 `~/.autoc/agent/sessions/<session_id>.jsonl`
- 用户可回放某次会话的所有改参动作（时间线 / 按模块分组）
- HTML 导出：自包含页面，三色 callout（add=绿/modify=黄/delete=红）
- 进程内 `threading.Lock` 保护 `.current` 标记与 batch 写入

## 存储格式（JSONL append-only）

每行一个 JSON 对象（`SessionEntry`）：

```json
{
  "id": "0190f4d2-3b7c-7e1a-bf8e-...",
  "session_id": "20260611-143000-abc123",
  "parent_id": "0190f4d2-3b7c-7e1a-bf8e-...",
  "kind": "user" | "tool",
  "timestamp": "2026-06-11T14:30:00.123456Z",
  "tool": "bsw_write",
  "args": {"module": "Mcu", "path": "Clock0/ClockFreq", "value": 80000000},
  "result": {"success": true, "old_value": 60000000}
}
```

**kinds**：
- `user`：用户请求（「改 Mcu 时钟到 80MHz」）
- `tool`：MCP 工具调用结果（bsw_read / bsw_write / bsw_verify / bsw_autocalc）

## 会话目录

```
~/.autoc/agent/sessions/
├── .current                      # 标记当前 session_id（一行文本）
├── 20260611-143000-abc123.jsonl  # 第一次 session
├── 20260611-150000-def456.jsonl  # 第二次 session
└── 20260611-160000-ghi789.jsonl
```

`.current` 由 `record_bsw_write_batch()` 维护：

- 首次调用：创建新 session（ID = `new_session_id()`）
- 后续调用：复用 `.current` 中的 ID
- 用户 `set_current_session <id>` 可显式切换

## 视图

### Timeline（按时间倒序）

`autoc log --view timeline --session latest`：

```
[2026-06-11 14:30:01] Mcu.Clock0.ClockFreq  60000000 → 80000000  ✓
[2026-06-11 14:30:03] Mcu.Clock0.ClockSrc   1 → 1  (skip)
[2026-06-11 14:30:05] Port.PortPin.Pin0.Dir IN → OUT  ✓
[2026-06-11 14:30:07] Can.CanIfTxPduCfg_EngineData.CanIfTxPduCanId 0x100 → 0x100  (skip)
```

### by-url（按 (module, path) 分组）

`autoc log --view by-url`：

```
Mcu/Clock0/ClockFreq
  14:30:01  60000000 → 80000000  ✓  (commit: 20260611-143000-abc123)
  16:45:12  80000000 → 100000000 ✓  (commit: 20260611-164500-mno345)

Port/PortPin/Pin0/Dir
  14:30:05  IN → OUT  ✓
```

## HTML 导出

`autoc export --output report.html`：

- 自包含：inline `<style>`、inline SVG callout
- 零外部资源（无需 CDN）
- URL scheme 白名单防 XSS（http / https / mailto / file）
- 外部链接 `rel="noopener noreferrer"`
- 三色 callout：add=绿 / modify=黄 / delete=红
- Markdown 渲染自写 inline（`**bold**` / `` `code` `` / `[link](url)`）

## 进程并发

- **进程内**：`threading.Lock` 保护 `.current` 读写 + 整个 batch 写入
- **跨进程**：**不保证**（多个 autoc 进程同时改参会丢条目；Sprint 4 范围外）
- 解决：单进程 + 串行调用；或用 file lock（fcntl / msvcrt）跨进程

## XSS 防御

```python
# 1. html.escape 所有文本
# 2. URL 严格白名单
_ALLOWED_URL_SCHEMES = frozenset({"http", "https", "mailto", "file"})

# 3. 外部链接加 rel="noopener noreferrer"
if url.startswith(("http://", "https://")):
    rel = "noopener noreferrer"
```

## 回放与调试

```python
# 列所有 session
from autoc.core.session.store import SessionStore, list_session_ids
ids = list_session_ids()  # 字母序

# 按 mtime 找最新
from autoc.core.session.store import resolve_latest_session_id
latest = resolve_latest_session_id()  # 按 mtime 倒序

# 读 session 详情
from autoc.core.session.store import SessionStore
entries = SessionStore(latest).read_all()
```

## MCP 工具

`autoc mcp_server` 暴露：

- `session_list` → 列出所有 session ID
- `session_show(id)` → 返回 entry 列表
- `session_export(id, "html")` → 返回 HTML 路径
- `log_export(id, "timeline"|"by-url")` → 返回 timeline 文本

## 不要做的

- ❌ 不要直接编辑 `.jsonl`（会破坏时间线连续性）
- ❌ 不要在多进程中并发改参（无跨进程锁）
- ❌ 不要导出未转义的 HTML（XSS 风险）
- ❌ 不要清理旧 session（保留至少 90 天用于回溯）
- ❌ 不要把 session_id 当 commit hash 用（UUID 形式，不语义）
