# CLAUDE.md

本仓库是 `NousResearch/hermes-agent` 的 fork，维护于 `zhiwww/hermes-agent`，用于独立部署。

完整部署 / 同步策略见 [`docs/local/fork-deployment-plan.md`](docs/local/fork-deployment-plan.md)。
以下是所有会话必须遵守的**持久化原则**。

---

## Fork 本地化原则（按优先级）

1. **能新增文件就不改上游文件** — 零冲突的最佳方式是不碰它。workflows、配置、文档优先用 additive 方式扩展，不要原地修改。
2. **能走 env / config 就不改代码** — 代码层面只做最小侵入（例如 `os.getenv(..., default)` 包装），把 diff 留在配置层。
3. **必须改的文件尽量只改最少行数** — 目前已识别的修改点：`pyproject.toml` (authors)、`package.json` (repo URLs)、`hermes_constants.py` (env override)。新增本地化时优先评估能否塞进已有的改动点，而不是新开一个。

## 红线（永远不要做）

- ❌ **不要修改** `.github/workflows/docker-publish.yml` / `.github/workflows/deploy-site.yml` — 它们已有 `if: github.repository == 'NousResearch/hermes-agent'` 自动在 fork 上禁用。本地需求一律通过**新增** `.github/workflows/fork-*.yml` 文件实现。
- ❌ **不要 `git push upstream`** — upstream remote 是只读的。
- ❌ **不要 `git rebase`** 已推送到 `origin/main` 的 commit — 会破坏上游 merge 的可追溯性。
- ❌ **不要在代码里硬编码** `zhiwww` / Docker Hub token / fork 专属 URL — 敏感信息走 GitHub Secrets，URL 走 env 变量。
- ❌ **不要为了「让 diff 更干净」重构上游代码** — 每一次无关重构都会放大未来 merge 冲突。

## Upstream 同步规范

- 上游同步**一律用 merge，不用 rebase**。理由：保留上游 commit hash 可追溯，避免 force push 风险。
- 同步命令模板：
  ```sh
  git fetch upstream
  git log --oneline main..upstream/main   # 预览
  git merge upstream/main --no-ff -m "chore: sync upstream $(date +%Y-%m-%d)"
  ```
- 已知可能冲突的 3 个文件：`pyproject.toml` / `package.json` / `hermes_constants.py`。解决模板：接受上游全部改动，再手动打回 fork 的小补丁。详见 `docs/local/fork-deployment-plan.md` 的「冲突处理预案」。

## Fork 专属约定

- **Fork 专属文档**放在 `docs/local/` 目录。该目录 upstream 不会写入，零冲突。
- **Fork 专属 workflow** 命名前缀 `fork-`，例如 `fork-docker-publish.yml`，便于识别和维护。
- **Docker Hub namespace** 固定为 `zhiwww/`，镜像名 `zhiwww/hermes-agent`。
- **本地化 commit message** 建议加前缀 `[fork]`，例如 `[fork] add fork-docker-publish workflow`，方便 `git log --grep='\[fork\]'` 快速定位本地化历史。
