## 改动说明

<!-- 简述这次 PR 做了什么、为什么做 -->

## 关联 issue

<!-- 关联的 issue / ticket，例如 Closes #123 -->

## 验证

请勾选已跑过的检查：

- [ ] 单测：`pytest packages/autoc/tests -v`
- [ ] Coverage ≥ 80%：`pytest --cov=packages/autoc/src/claude_autosar --cov-fail-under=80`
- [ ] Lint：`ruff check packages/autoc/src/claude_autosar packages/autoc/tests`
- [ ] Format：`black --check packages/autoc/src/claude_autosar packages/autoc/tests`
- [ ] Import sort：`isort --check packages/autoc/src/claude_autosar packages/autoc/tests`
- [ ] Type check：`mypy --strict packages/autoc/src/claude_autosar`
- [ ] Security：`bandit -r packages/autoc/src/claude_autosar -ll`
- [ ] 端到端（如适用）：描述

## 影响范围

- 影响的包 / 模块：
- 影响的公共 API：
- 性能 / 安全影响：

## 文档

- [ ] README 更新（如适用）
- [ ] 内嵌 docstring 完整
- [ ] 计划文档（`~/.claude/plans/...md`）更新（如适用）
