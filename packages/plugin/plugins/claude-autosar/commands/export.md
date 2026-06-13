---
name: export
description: |
  导出会话为自包含 HTML。底层调用 `claude-autosar export --output <path>`。
  用法：`/claude-autosar:export --output <path-to-html> [--session <id|latest>]`
allowed-tools: Bash
---

# /claude-autosar:export

把当前（或指定）会话导出为可分享的 HTML。

## 用法

```
/claude-autosar:export --output report.html
/claude-autosar:export --output report.html --session latest
/claude-autosar:export --output report.html --session 20260611-143000-abc123
```

## 输出

自包含 HTML（inline CSS + SVG + JavaScript，零外部资源）：

- 三色 callout：add=绿 / modify=黄 / delete=红
- URL scheme 白名单防 XSS（http / https / mailto / file）
- 外部链接 `rel="noopener noreferrer"`
- inline Markdown 渲染（`**bold**` / `` `code` `` / `[link](url)`）

## 示例

```
> 帮我导出这次会话为 HTML
> /claude-autosar:export --output ./reports/sprint5.html

报告已生成：./reports/sprint5.html
大小：124 KB
条目：12（5 user + 7 tool）
改参：5 个（Mcu=3, Port=2）
```

## 在浏览器中打开

```bash
# Windows
start ./reports/sprint5.html
# macOS
open ./reports/sprint5.html
# Linux
xdg-open ./reports/sprint5.html
```

## 前置条件

- 有可导出的 session（运行过 `claude-autosar eb save` / `claude-autosar davinci save`）
- 目标目录可写

## 安全说明

HTML 自包含意味着你**可以**邮件附件发给团队 / 上传到 wiki，不会泄漏
XSS（URL 严格白名单 + 文本 escape）。但也不要把不信任的 Markdown 内容
贴到 .jsonl 里再 export（虽然有 escape，XSS 攻击面还是更大）。
