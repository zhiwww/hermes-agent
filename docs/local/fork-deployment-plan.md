# Hermes-Agent Fork 本地化部署计划

## Context

用户 fork 了 `NousResearch/hermes-agent` 到自己的仓库，希望将项目中硬编码指向 Nous Research 组织、域名、Docker Hub 镜像、推理 API 等上游专属资源的地方替换/剥离，以便在自己的基础设施上自由部署（构建镜像、发布文档站、使用自己的推理端点等）。

本计划只做「最小可用」范围规划，不涉及功能改动。后续可以按优先级逐步补充。

### 基本坐标

| 项 | 值 |
|---|---|
| Fork 仓库 | `git@github.com:zhiwww/hermes-agent.git` (`zhiwww/hermes-agent`) |
| Upstream 仓库 | `git@github.com:NousResearch/hermes-agent.git` (`NousResearch/hermes-agent`) |
| Docker Hub namespace | `zhiwww/` （镜像将推送为 `zhiwww/hermes-agent:<tag>`） |
| 作者/维护者 | `zhiwww` |

---

## 核心策略

**最高目标**：未来 `git merge upstream/main` 零冲突或极少冲突。

三条原则（按优先级）：

1. **能新增文件就不改上游文件** —— 零冲突的最佳方式是不碰它
2. **能走 env / config 就不改代码** —— 把 diff 留在配置层
3. **必须改的文件尽量只改最少行数** —— 减小冲突表面积

### 冲突面分析

| 文件 | 上游改动频率 | 本地化策略 | 冲突风险 |
|---|---|---|---|
| `.github/workflows/docker-publish.yml` | 低 | **新增** `docker-publish-fork.yml` 替代，原文件不动 | ⭐ 零 |
| `.github/workflows/deploy-site.yml` | 低 | 同上（或完全不部署文档站） | ⭐ 零 |
| `pyproject.toml` | 中（版本/依赖） | 只改 `authors` 一行 | ⭐⭐ 极低 |
| `package.json` | 低 | 只改 `repository`/`bugs`/`homepage` 三行 | ⭐⭐ 极低 |
| `hermes_constants.py` | 中 | env override（一行改两行） | ⭐⭐ 极低 |
| `docs/local/*` | — | fork 专属目录，upstream 不会动 | ⭐ 零 |
| `CLAUDE.md` | — | 新增文件（upstream 目前无此文件） | ⭐ 零（未来若 upstream 新增则需手动合并） |

**关键洞察**：上游 `docker-publish.yml` 和 `deploy-site.yml` 已经用 `if: github.repository == 'NousResearch/hermes-agent'` 做了 fork 门禁 —— 它们在你的 fork 上**本身就不会运行**。所以你根本不需要修改它们，只需要新增并行的 fork 专属 workflow 文件即可。

---

## 改动清单（按优先级）

### P0 — 必须改，否则 fork 无法独立构建/发布

#### 1. GitHub Actions 工作流（additive 策略）
**不修改上游的 `docker-publish.yml` / `deploy-site.yml`**，它们在 fork 上自带门禁不会跑。

- **新增** `/.github/workflows/fork-docker-publish.yml`
  - 触发：`push` to main / `release`
  - 门禁：`if: github.repository == 'zhiwww/hermes-agent'`
  - 镜像 tag：`zhiwww/hermes-agent:latest` / `:${{ github.sha }}` / `:${{ github.event.release.tag_name }}`
  - 直接从上游 `docker-publish.yml` 复制结构修改即可
- **文档站**（可选）：如果要发布，同样新增 `fork-deploy-site.yml`；短期不需要可跳过
- Secrets：`github.com/zhiwww/hermes-agent/settings/secrets/actions` 添加 `DOCKERHUB_USERNAME=zhiwww` / `DOCKERHUB_TOKEN=<your-token>`
- **好处**：未来上游改 `docker-publish.yml`（比如加 cache 优化、升级 action 版本）你直接 merge，你的 fork-workflow 完全不受影响

#### 2. 包元数据
- `/pyproject.toml:6` — `name = "hermes-agent"` （可保留或改为 `hermes-agent-zhiwww` 避免 PyPI 冲突；本地自用可不改）
- `/pyproject.toml:11` — `authors = [{ name = "Nous Research" }]` → `[{ name = "zhiwww" }]`
- `/package.json:9-17` — `repository.url` / `bugs.url` / `homepage` 里的 `NousResearch/Hermes-Agent` → `zhiwww/hermes-agent`

### P1 — 影响运行时行为，建议走 env 覆盖

#### 3. Nous 推理 API 端点
`NOUS_API_BASE_URL` 在约 20 个文件里被引用（provider 解析、测试、gateway、run_agent 等）。

- `/hermes_constants.py:114-115` — 定义 `NOUS_API_BASE_URL` / `NOUS_API_CHAT_URL`
- 推荐做法：把这两行改为 `os.getenv("NOUS_API_BASE_URL", "https://inference-api.nousresearch.com/v1")`，保持默认值不变，这样 upstream diff 最小。部署时通过 env 指向你自己的代理或直接不启用 Nous provider。
- 同样方式审视 `HERMES_PORTAL_BASE_URL`（已经是 env 驱动，确认即可）
- 其它 provider 端点（OpenRouter/AI Gateway/Anthropic OAuth）都是公共服务，**不需要改**

#### 4. 默认配置示例
- `/cli-config.yaml.example` — 确认默认 provider / 模型是否符合你的部署；如果用不到 Nous，把默认 provider 调整为 OpenRouter 或你的自建端点

### P2 — 文档站与品牌（可选，只在发布文档时需要）

#### 5. Docusaurus 配置
- `/website/docusaurus.config.ts:10` — `url: 'https://hermes-agent.nousresearch.com'`
- `/website/docusaurus.config.ts:13-14` — `organizationName` / `projectName`
- `/website/docusaurus.config.ts` — `editUrl`（搜索 `github.com/NousResearch`）
- `/website/docs/user-guide/docker.md` — Docker 镜像引用 `nousresearch/hermes-agent`

#### 6. README / 文档中的仓库链接
- `/README.md`、`/CONTRIBUTING.md`、`/RELEASE_v0.8.0.md` 等 markdown 中指向上游仓库的链接
- 建议策略：**不动**。fork 的 README 继续指向上游有助于追溯；只改真正影响构建/运行的地方

---

## 不需要动的部分

- **LICENSE** — MIT，自由复用
- **Secret redaction** (`agent/redact.py`) — 通用凭证脱敏
- **OAuth adapters** (Anthropic / Codex / xAI / MiniMax) — 公共服务端点
- **Telemetry** — 代码库中未发现遥测/回传
- **Dockerfile** 本身 — 通用，无组织特定内容（只有 `HERMES_HOME=/opt/data`）

---

## 验证步骤

按以下顺序跑一遍确认 fork 可独立运转：

1. **本地构建**：`pip install -e .` 确认 `pyproject.toml` 改名后可安装
2. **Docker 构建**：`docker build -t zhiwww/hermes-agent:local .` 确认 Dockerfile 没有隐藏依赖
3. **CI smoke test**：推一个 commit 到 `zhiwww/hermes-agent` 的 main，确认 `docker-publish.yml` 的仓库判断能通过、能推到 `hub.docker.com/r/zhiwww/hermes-agent`
4. **运行时**：
   - 不设 `NOUS_API_BASE_URL` env，用 OpenRouter 跑 `python run_agent.py --help` 确认默认流程正常
   - 设 `NOUS_API_BASE_URL=<你的端点>` 确认 env 覆盖生效
5. **文档站**（可选）：`cd website && npm run build` 本地构建通过

---

---

## Upstream Sync 策略（核心）

### 分支模型：单主分支 + 追踪远程

推荐**最简模型**。不搞多分支 overlay，因为本地化 diff 足够小。

```
┌─────────────────────────────────────┐
│  upstream (NousResearch/hermes-agent) │
│         └── upstream/main            │
└───────────────┬─────────────────────┘
                │  git fetch upstream
                │  git merge upstream/main
                ▼
┌─────────────────────────────────────┐
│  origin (zhiwww/hermes-agent)        │
│         └── main  ← 日常工作 + 部署  │
└─────────────────────────────────────┘
```

- 只有一个 `main` 分支，既是开发分支也是部署分支
- `upstream` remote 只读，永远不 push
- 本地化 commit 直接落在 `main` 上，和上游 commit 交织（merge commit 会自然分层）

**为什么不用双分支 `upstream-sync` + `deploy`？** 对于本地化 diff < 10 行的情况，双分支是 over-engineering：
- 双分支要求每次同步都走 `upstream-sync → deploy` 的 merge，仪式感重
- 优势（隔离 local 改动）可以用 `git diff upstream/main main` 实现，不需要专门分支

### 一次性初始化

```sh
cd /Users/zwi/Projects/hermes-agent
git remote add upstream git@github.com:NousResearch/hermes-agent.git
git fetch upstream
git remote -v   # 确认 origin=zhiwww, upstream=NousResearch
```

### 日常同步流程

每周或每次看到上游有重要 commit 时执行：

```sh
# 1. 确保本地 main 干净
git checkout main
git status   # 必须 clean

# 2. 拉上游
git fetch upstream

# 3. 预览将要 merge 的内容
git log --oneline main..upstream/main        # 新增 commit
git diff main..upstream/main -- pyproject.toml package.json hermes_constants.py  # 重点文件

# 4. Merge（保留历史，不要 rebase）
git merge upstream/main --no-ff -m "chore: sync upstream $(date +%Y-%m-%d)"

# 5. 冲突解决（如有）见下节
# 6. 推送
git push origin main
```

### Merge vs Rebase 决策

**一律用 merge，不用 rebase**。理由：

| 维度 | merge | rebase |
|---|---|---|
| 保留上游 commit hash | ✅ | ❌（重写） |
| 可追溯上游 commit | ✅ `git log upstream/main` 对得上 | ❌ |
| fork 的 PR 引用 upstream 的 commit | ✅ | ❌ |
| 多人协作安全性 | ✅ | ❌（force push 风险） |
| 历史线性 | ❌ | ✅ |

**唯一例外**：你自己的本地化 commit，在推送到 `origin/main` 之前可以 rebase 到最新 `upstream/main` 上（保持线性），但一旦推送就不能 rebase 了。

### 冲突处理预案

按本地化策略实施后，理论上只有这几个文件可能冲突：

| 文件 | 冲突概率 | 解决方式 |
|---|---|---|
| `pyproject.toml` | 中（upstream 会改版本号/依赖） | 接受上游全部改动，手动保留你的 `authors` 字段 |
| `package.json` | 低 | 接受上游全部改动，手动保留你的 `repository`/`bugs`/`homepage` |
| `hermes_constants.py` | 低 | 接受上游新常量，保留你的 `os.getenv(...)` 包装 |

**冲突解决模板**（当 `git merge` 报冲突时）：

```sh
# 打开冲突文件，一般用 "接受 upstream + 打补丁" 的方式
# 例如 pyproject.toml：
git checkout --theirs pyproject.toml     # 先完全接受上游版本
# 然后手动加回你的改动（authors 字段）
vim pyproject.toml
git add pyproject.toml
git merge --continue
```

### 核选项：`.gitattributes` merge driver

如果未来 `pyproject.toml` 冲突变得很烦，可以启用 `merge=ours` 策略**只对特定字段**生效：

```gitattributes
# .gitattributes
pyproject.toml merge=union
```

`merge=union` 会把双方改动都保留（适合 authors 列表这种场景）。但这个是双刃剑，**默认不启用**，等真遇到问题再说。

### 红线

- ❌ **永远不要** `git push upstream`
- ❌ **永远不要** `git rebase` 已经推送到 `origin/main` 的 commit
- ❌ **永远不要** 在 fork 专属文件上放敏感信息（Dockerhub token 必须走 GitHub Secrets）
- ❌ **不要修改** `.github/workflows/docker-publish.yml` / `deploy-site.yml`（改了就破坏 additive 策略）

> 以上红线已同步到 `/CLAUDE.md`，确保所有 Claude Code 会话都会遵守。修改红线时必须两处同步更新。

### 半自动化：定期同步 workflow（可选）

未来可以加一个 `.github/workflows/fork-sync-upstream.yml`，每周定时 `fetch upstream && merge`，遇到冲突自动开一个 PR 让你手动处理。等 P0 稳定之后再考虑。

---

## 已做出的决定（避免未来重复讨论）

### FlakeHub Nix cache：放弃配置，与上游对齐

- **背景**：`nix.yml` 里的 `magic-nix-cache-action@v13` 要求 FlakeHub 认证。上游自己也没配好（annotations 里一直有 `Unable to authenticate to FlakeHub` 的 ❌ warning，但 build 照样过）。
- **尝试过**：fork 上注册了 FlakeHub 账号 + 在 repo settings 把 Workflow permissions 设为 "Read and write"（开启 `id-token: write`）。结果错误从「未注册」变成「Cannot find netrc credentials」—— 因为缺少 `DeterminateSystems/flakehub-login-action` 这一步把 OIDC token 写成 `~/.netrc`。
- **为什么不修**：修复需要在 `nix.yml` 里插入一个 login step，这是修改上游文件，违反 additive 原则。而且 `nix.yml` 没有 fork 门禁，新建 `fork-nix.yml` 会和上游重复跑。
- **决定**：放弃，与上游状态对齐。Nix build 当前 2-8 分钟可接受；未来上游如果自己给 `nix.yml` 加了 login step，我们 merge 时自动继承。
- **不影响**：本地开发想用 FlakeHub cache 的话，直接 `flakehub login` 写 `~/.netrc` 即可，和 CI 解耦。

## 后续补充方向（不在本次范围）

- 把 `.env.example` 整理一份 fork 专属版本
- fork 专属的 CHANGELOG / RELEASE notes
- 自动化 upstream sync workflow
