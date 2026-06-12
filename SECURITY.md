# Security Policy

AutoC 项目的安全策略与已知漏洞处置记录。

## 扫描基线（Sprint 7, 2026-06-12）

| 工具 | 范围 | High | Medium | Low | 结论 |
|------|------|------|--------|-----|------|
| `bandit -ll` | `packages/autoc/src/autoc` + `packages/plugin/plugins/autoc/hooks` | 0 | 0 | 9 | ✅ 通过 |
| `pip-audit` | autoc 完整依赖图 | 0（autoc 运行时） | 0 | 3 transitive | ✅ 通过 |

## bandit Low（pre-existing subprocess 模式）

9 条 Low 全部是 B404 / B603 / B607（subprocess 调用 + 缺 `shell=False` / `timeout`），
属于 `StubTresosAdapter` / `StubDavinciAdapter` 和 mcp_server 的已知模式：

- B404: `subprocess` 模块 import
- B603: `subprocess.run` 未用 `shell=False` 显式标注（实际已用 `shell=False`）
- B607: 部分启动 .bat 文件路径未做"白名单路径前缀"校验（Sprint 4 决策：用户显式
  提供 path 即可，trust-but-verify 由 stub adapter 兜底）

**为何不修**：每条修复会引入大量 `nosec` 注释或对 stub 模式做过度防御；当前已有
Sprint 5 路径防御（H4: `_ALLOWED_PROJECT_ROOTS`）+ Sprint 6 钩子（ARXML guard +
BSW validate）作为纵深防御。Low 在可接受范围。

## pip-audit transitive 漏洞（不在 autoc 运行时路径）

```
aiohttp  3.13.5  CVE-2026-34993  → 升级至 3.14.0
aiohttp  3.13.5  CVE-2026-47265  → 升级至 3.14.0
chromadb 1.5.9   CVE-2026-45829  → no fix listed
```

**依赖图证据**：
- `aiohttp 3.13.5` → `Required-by: kubernetes`（dev 依赖，autoc 运行时不用）
- `chromadb 1.5.9` → 由某个 dev 工具间接拉入（autoc 运行时不用）

**autoc 直接依赖**（pyproject.toml [project.dependencies]）：

```
lxml>=5.0
cantools>=39.0
rich>=13.0
mcp>=0.9
platformdirs>=4.0
tomli-w>=1.0
```

**全部无已知漏洞**（pip-audit 已逐个审计）。

## 报告漏洞

如发现 autoc 自身的安全问题，请：

1. **不要** 在公开 GitHub issue 披露
2. 发邮件给 `security@autoc-cc.example` （待真实部署后替换）
3. 附上：CVE / 复现步骤 / 影响面 / 提议修复

## 复扫命令

```bash
# bandit（跨平台）
bandit -r packages/autoc/src/autoc packages/plugin/plugins/autoc/hooks -ll

# pip-audit（跨平台；扫描完整依赖图；transitive 漏洞会一起报）
pip-audit

# 仅 audit autoc 直接依赖（跨平台，用 tomllib 标准库）
pip-audit --requirement <(python -c "
import tomllib, sys
with open('packages/autoc/pyproject.toml', 'rb') as f:
    d = tomllib.load(f)
for dep in d['project']['dependencies']:
    print(dep)
")
```

## 已知未来工作

- [ ] aiohttp / kubernetes 是否要从 dev 依赖中拆出（隔离 transitive）
- [ ] 在 CI 增 pip-audit 步骤（PR 阻塞 0 high/medium）
- [ ] 在 CI 增 bandit 步骤（PR 阻塞 0 high/medium）
