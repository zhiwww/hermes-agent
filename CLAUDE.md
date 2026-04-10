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
- ❌ **不要 `git push upstream`** — upstream remote 是只读的（push URL 已设为 `no_push`）。
- ❌ **不要 `git rebase`** 已推送到 `origin/main` 的 commit — 会破坏上游 merge 的可追溯性。
- ❌ **不要在代码里硬编码** `zhiwww` / Docker Hub token / fork 专属 URL — 敏感信息走 GitHub Secrets，URL 走 env 变量。
- ❌ **不要为了「让 diff 更干净」重构上游代码** — 每一次无关重构都会放大未来 merge 冲突。
- ❌ **不要 "修复" 上游自己也没修的警告/错误** — 如果上游 CI 长期容忍某个 warning（比如 FlakeHub 认证失败），fork 也应该容忍。试图单方面修复会引入上游文件改动，得不偿失。先查上游 CI 状态再决定是否动手。

## 诊断启发式（排查问题前必看）

CI 或 workflow 失败时，**先问三个问题**再下手：

1. **上游自己现在是什么状态？** 用 `gh run list --repo NousResearch/hermes-agent --workflow=<name> --branch main` 看上游最近几次的状态。
   - 如果上游同一个 workflow 也在失败 → 不是 fork 的锅，是上游回归。选择：等上游修 / 自己加 additive 补丁。
   - 如果上游是绿的 → 问题在 fork 引入的改动，聚焦排查最近的本地化 commit。
2. **这个 workflow 有 fork 门禁吗？** `grep 'github.repository' .github/workflows/<name>.yml`
   - 有门禁（如 `docker-publish.yml` / `deploy-site.yml`）→ 可以安全新建 `fork-*.yml` 并行替代。
   - 无门禁（如 `nix.yml` / `Tests`）→ 新建并行文件会**双跑**，必须另想办法（忽略、或违反原则直接改文件）。
3. **这个错误是 fatal 还是 warning？** 看 workflow 最终的 exit code，不要被 annotations 里的 ❌ 误导。annotation 可能只是 `continue-on-error` 步骤的软失败，不影响 job 结果。

**真实案例**（2026-04-10）：
- 第一天 merge 上游后 `fork-docker-publish.yml` 失败 on `pip resolution-too-deep`。查了上游 main 的 `docker-publish.yml`，上游同一个错误已经连续失败多次 → 不是 fork 的锅，等上游修。
- Nix workflow 的 FlakeHub 认证警告，上游自己也有，不修，align with upstream。
- home- 部署后 Slack 测试失败，litellm 日志显示 "No api key passed in"。第一反应：hermes 没展开 `${VAR}`。**错了** —— 那条 litellm 日志是我 1 分钟前跑的 curl 留下的，hermes 请求**从未到达 litellm**。真正的错误是 Python httpx 不信任私有 CA（TLS `CERTIFICATE_VERIFY_FAILED`），被 hermes 包装成 "Connection error"。**教训：多源日志要先对齐时间戳再下因果判断**。

## Hermes-specific 陷阱

- ⚠️ **Python `ssl` 模块不读 macOS Keychain**，所有 Python HTTPS（httpx / requests / openai SDK / aiohttp）只认 `certifi` 包里的 Mozilla CA bundle。如果 hermes 要访问一个用**私有 CA 签名的 LLM endpoint**（比如你自建的 `llm.zwi` 反代），curl 能过但 Python 会 `CERTIFICATE_VERIFY_FAILED`。**fix-friendly 方案**：在 venv 里装 `truststore` 并写 `sitecustomize.py` 做启动注入，让 Python 使用 macOS Security framework（= Keychain）。详见 `docs/local/deploy-home.md` 的「Phase 2.5」段。**这和 venv 无关**，系统 Python 也一样。
- ⚠️ **`hermes doctor --fix` 会把 config.yaml 里的 `${VAR}` 引用展开成明文**。如果你在 `config.yaml` 里用了 `api_key: ${LLM_ZWI_API_KEY}` 之类的 env 变量引用，跑 `--fix` 之后会变成 `api_key: sk-xxxxxxxx` 明文写回文件，撤销 env 变量间接化。**默认不要跑 `hermes doctor --fix`**。如果必须跑，修完后立刻用 sed 把明文 key 恢复成 `${VAR}` 引用。注意：env 变量引用**本身工作正常** —— gateway 路径会正确展开 `${VAR}`，只是 `doctor --fix` 写回时会落成明文。
- ⚠️ **`HERMES_HOME` 不能等于 fork repo 根目录**。`tools/skills_sync.py` 会 `shutil.copytree(<repo>/skills/, $HERMES_HOME/skills/)`，同路径会 `FileExistsError`。标准布局：repo 在 `~/Projects/hermes-agent`，HERMES_HOME 用默认 `~/.hermes`。
- ⚠️ **home- 的 `~/Projects` 是 symlink 到 `/Volumes/Store/Projects`**（外置 SSD）。`hermes --version` 显示的 `Project: /Volumes/Store/...` 是规范化后的真实路径，不是另一个安装。

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
- **Fork 专属 workflow** 命名前缀 `fork-`，例如 `fork-docker-publish.yml`，便于识别和维护。新建前先确认对应的上游 workflow 有 fork 门禁（见诊断启发式 #2）。
- **Docker Hub namespace** 固定为 `zhiwww/`，镜像名 `zhiwww/hermes-agent`。
- **本地化 commit message** 必须加前缀 `[fork]`，例如 `[fork] add fork-docker-publish workflow`，方便 `git log --grep='\[fork\]'` 快速定位本地化历史。**上游 merge commit 不加** `[fork]` 前缀（用 `chore: sync upstream <date>`），这样两种历史一眼可分。
- **fork-* workflow 的 concurrency**：注意 `cancel-in-progress: true` 会在快速连续 push 时取消前一次 run；调试时要等完整结果，避免误判（前一次 run 可能只是被取消不是真的失败）。
