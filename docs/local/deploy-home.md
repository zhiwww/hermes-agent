# Deploying Fork to `home-` Server (Runbook)

## Context

Deploy the fork (`zhiwww/hermes-agent`) to the remote macOS host `home-`
(Tailscale: `zwi-mini.tail30560e.ts.net`, `~` = `/Users/zwi`), migrating
selected state from `~/legacy-hermes/` on the local workstation to
`~/.hermes/` on the server.

**Repo** lives at `~/Projects/hermes-agent` on home- (note: `~/Projects`
is a symlink to `/Volumes/Store/Projects`, so `hermes --version` will
show the canonical `/Volumes/Store/...` path — same directory).

**HERMES_HOME** = `~/.hermes` (default layout — NOT the repo dir; see
[Path conflict](#why-hermes_home--repo-dir-is-forbidden) below).

## Operating model: home- is the single source of truth ⚠️

**2026-04-10 decision**: all hermes operations (git and runtime) happen
**on home- only**. The workstation is no longer part of the deployment
loop.

| Machine | Role |
|---|---|
| **home-** (`zwi-mini.tail30560e.ts.net`) | The only place hermes lives. Repo, venv, CLI, HERMES_HOME, launchd services, git remotes — all on home-. |
| **workstation** (your daily Mac) | Not involved. If a historical `/Users/zwi/Projects/hermes-agent/` checkout exists, it's frozen — do not edit, do not rsync, do not push from there. Safe to delete. |

Two ways to execute commands on home-, pick whichever fits your context:

1. **Remote (ssh from anywhere)**: `ssh home- '<command>'` — works from
   the workstation, a laptop, your phone over Tailscale, anywhere.
2. **Local-on-home-**: directly on home- (sitting at it, tmux session,
   VS Code Remote SSH, etc.). Drop the `ssh home- '...'` wrapper.

**Sanity checks before any stateful command** (file edit, rsync, gateway
restart, launchd install/uninstall, config change, service kill):

- [ ] Confirm you are operating on home-: `ssh home- hostname` should
      return `zwi-mini`, or if local-on-home-, `hostname` shows
      `zwi-mini`.
- [ ] Never edit files under `/Users/zwi/Projects/hermes-agent/` on the
      workstation — that checkout is frozen history.
- [ ] For the assistant: state the execution context explicitly, e.g.
      "this runs on home- via ssh from the workstation" or "this runs
      on home- locally".

The commands below are written in **SSH form** (`ssh home- '...'`) for
the common case of driving home- from a laptop. Strip the wrapper when
running directly on home-.

## Deployment phases (one-time bootstrap, historical reference)

> **⚠️ These phases describe the initial deployment that migrated data
> from `~/legacy-hermes` on the workstation to home-. That migration
> happened on 2026-04-10 and will not repeat under normal operation.**
>
> **For ongoing maintenance (upstream merges, fork patches, gateway
> restarts), skip to [Version updates / upgrading the fork](#version-updates--upgrading-the-fork)
> below — all steps run on home- via ssh, no workstation involvement.**
>
> **Re-read these phases only if**:
> - Deploying to a brand-new server
> - Disaster recovery from a wiped home-
> - You're debugging how the current setup was built

### Phase 0 — Build staging dir (on workstation)

```sh
STAGING=/tmp/hermes-home-staging
rm -rf "$STAGING"
mkdir -p "$STAGING/profiles/coder" "$STAGING/profiles/ea"

# Main-level
cp ~/legacy-hermes/config.yaml   "$STAGING/"
cp ~/legacy-hermes/.env          "$STAGING/"
cp ~/legacy-hermes/SOUL.md       "$STAGING/"
cp ~/legacy-hermes/honcho.json   "$STAGING/"
cp -R ~/legacy-hermes/docs       "$STAGING/"   # Slack manifests
cp -R ~/legacy-hermes/cron       "$STAGING/"
find "$STAGING/cron" -name '.tick.lock' -delete

# Per-profile (coder, ea) — IMPORTANT: each profile has its own .env
# (a dotfile, easy to miss with plain `ls`). Profiles read their own
# .env, not the main ~/.hermes/.env, so missing it means no Slack tokens
# and the gateway starts with "No messaging platforms enabled".
for p in coder ea; do
  cp ~/legacy-hermes/profiles/$p/.env        "$STAGING/profiles/$p/"
  cp ~/legacy-hermes/profiles/$p/config.yaml "$STAGING/profiles/$p/"
  cp ~/legacy-hermes/profiles/$p/SOUL.md     "$STAGING/profiles/$p/"
  cp ~/legacy-hermes/profiles/$p/honcho.json "$STAGING/profiles/$p/"
  cp -R ~/legacy-hermes/profiles/$p/cron      "$STAGING/profiles/$p/"
  cp -R ~/legacy-hermes/profiles/$p/skins     "$STAGING/profiles/$p/"
  cp -R ~/legacy-hermes/profiles/$p/platforms "$STAGING/profiles/$p/"
  find "$STAGING/profiles/$p/cron" -name '.tick.lock' -delete
done

# === Modifications ===

# 1. config.yaml — URL rename + api_key → ${LLM_ZWI_API_KEY}
sed -i '' 's|https://llm\.zwi\.monster/v1|https://llm.zwi/v1|g' "$STAGING/config.yaml"
sed -i '' 's|Llm\.zwi\.monster|Llm.zwi|g'                     "$STAGING/config.yaml"
sed -i '' 's|api_key: sk-G44kshLqGjulGtUd0_vo8A|api_key: ${LLM_ZWI_API_KEY}|g' "$STAGING/config.yaml"

# 2. .env — add the env var referenced above
printf '\n# Migrated from config.yaml plaintext\nLLM_ZWI_API_KEY=sk-G44kshLqGjulGtUd0_vo8A\n' >> "$STAGING/.env"

# 3. profiles/ea/config.yaml — delete stale api_key leftover
sed -i '' '/^  api_key: sk-G44kshLqGjulGtUd0_vo8A$/d' "$STAGING/profiles/ea/config.yaml"
```

### Exclusion list (why these are NOT migrated)

Intentionally **excluded** from staging:

| Item | Reason |
|---|---|
| `auth.json`, `auth.lock` | per decision — re-authenticate on new host |
| `sessions/`, `memories/` | per decision — fresh start |
| `state.db*` | per decision — runtime state |
| `skills/` | use the repo's up-to-date bundled skills (seeded by `setup-hermes.sh`) |
| `hermes-agent/` (subdir) | legacy repo clone from upstream; we deploy our fork instead |
| `cache/`, `logs/`, `images/`, `image_cache/`, `audio_cache/`, `sandboxes/`, `webui/`, `whatsapp/`, `checkpoints/`, `bin/`, `hooks/`, `pairing/` | runtime caches |
| `models_dev_cache.json`, `.skills_prompt_snapshot.json`, `.update_check`, `.hermes_history` | runtime caches |
| `channel_directory.json`, `gateway_state.json` | runtime messaging state |
| `profiles/*/workspace/`, `profiles/*/plans/` | runtime workspace state |

### Phase 1 — rsync repo

```sh
ssh home- 'mkdir -p ~/Projects'
rsync -az \
  --exclude='venv/' --exclude='__pycache__/' --exclude='*.pyc' \
  --exclude='node_modules/' --exclude='.pytest_cache/' \
  --exclude='*.swp' --exclude='.DS_Store' \
  --exclude='.mypy_cache/' --exclude='.ruff_cache/' \
  /Users/zwi/Projects/hermes-agent/ home-:Projects/hermes-agent/
```

`.git/` is intentionally included so `git pull origin main` keeps working on home-.

### Phase 2 — setup-hermes.sh on home-

```sh
ssh home- 'cd ~/Projects/hermes-agent && printf "n\n" | ./setup-hermes.sh'
```

Creates `~/Projects/hermes-agent/venv`, runs `uv sync --all-extras --locked`,
seeds `~/.hermes/skills/` with 77 bundled skills, symlinks `~/.local/bin/hermes`.

### Phase 2.5 — Inject truststore (REQUIRED for private-CA LLM endpoints)

Python's `ssl` module uses `certifi`'s Mozilla CA bundle and does NOT
read macOS Keychain. If the LLM endpoint (`llm.zwi`) is behind a reverse
proxy with a private CA you've trusted in Keychain, Python will reject
the TLS handshake with `CERTIFICATE_VERIFY_FAILED` even though `curl`
from the same machine works fine.

**Fix**: install `truststore` and add a `sitecustomize.py` hook so all
Python processes using this venv automatically inject it at startup.
This makes Python `ssl` delegate to macOS Security framework (Keychain).

```sh
ssh home- '
VENV=~/Projects/hermes-agent/venv
VIRTUAL_ENV=$VENV uv pip install truststore
SITE=$($VENV/bin/python -c "import sysconfig; print(sysconfig.get_paths()[\"purelib\"])")
cat > "$SITE/sitecustomize.py" << "PY"
"""Auto-injected at Python startup: use macOS/OS trust store for TLS.
Makes Python httpx/requests/etc. trust any CA in macOS Keychain
(matches curl/Safari behavior). No code changes in hermes required.
"""
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass
PY
'
```

**Verify**:
```sh
ssh home- '~/Projects/hermes-agent/venv/bin/python -c "
import ssl, httpx
ctx = ssl.create_default_context()
assert \"truststore\" in type(ctx).__module__, \"truststore not active\"
r = httpx.get(\"https://llm.zwi/v1/models\", timeout=15)
print(\"OK\", r.status_code)
"'
```

Should print `OK 401` (401 is expected without api key). If you see
`CERTIFICATE_VERIFY_FAILED` instead, the sitecustomize.py didn't run
(check the path with `$VENV/bin/python -c "import sysconfig; print(sysconfig.get_paths()['purelib'])"`).

**Skip this phase if** all LLM endpoints use public CAs (OpenAI, Anthropic,
Codex via chatgpt.com, public OpenRouter endpoints, etc.).

### Phase 3 — rsync staging → remote HERMES_HOME

```sh
rsync -avz /tmp/hermes-home-staging/ home-:.hermes/
```

**Do NOT pass `--delete`** — we must preserve `~/.hermes/skills/` seeded in Phase 2.

### Phase 4 — verify

```sh
ssh home- '~/.local/bin/hermes status'
ssh home- '~/.local/bin/hermes doctor'
```

`hermes doctor` will report 1 migration issue (config schema bump). **See the
`hermes doctor --fix` gotcha below before running it.**

## Gotchas

### Python `ssl` doesn't read macOS Keychain (TLS trust)

See Phase 2.5. Symptom: `hermes gateway` logs show "Connection error"
for LLM calls, and you find `httpx.ConnectError: [SSL:
CERTIFICATE_VERIFY_FAILED] self-signed certificate in certificate chain`
in the error details. Meanwhile `curl https://<endpoint>` works fine on
the same machine. The fix is `truststore` + `sitecustomize.py` (Phase
2.5). This has nothing to do with the venv — system Python behaves the
same way.

**Debugging tip**: before blaming a config issue (missing api key, bad
URL, wrong headers), confirm the HTTPS connection itself is reachable
from the venv Python:

```sh
$VENV/bin/python -c "
import httpx
print(httpx.get('https://<endpoint>/v1/models', timeout=10).status_code)
"
```

If this raises a TLS error, fix the trust chain first. Application-level
errors (401, 404, etc.) only matter once this works.

### `hermes doctor --fix` expands `${VAR}` to plaintext

`hermes doctor --fix` writes the **resolved** in-memory config back to
`config.yaml`, which means any `${LLM_ZWI_API_KEY}` reference becomes the
literal `sk-...` string. This silently undoes the env var indirection
from decision 4b.

**Important**: env var references themselves work fine in the gateway
path — `gateway/run.py` reads the api_key through `hermes_cli/config.py`
which calls `_expand_env_vars()`. It's only `doctor --fix`'s write-back
that loses the indirection.

**Workaround**: run the fix, then immediately re-apply the env var
references (and sync staging back from the fixed file):

```sh
ssh home- '~/.local/bin/hermes doctor --fix'
ssh home- "sed -i '' 's|api_key: sk-G44kshLqGjulGtUd0_vo8A|api_key: \${LLM_ZWI_API_KEY}|g' ~/.hermes/config.yaml"
scp home-:.hermes/config.yaml /tmp/hermes-home-staging/config.yaml
```

Or: **never run `hermes doctor --fix`** and accept the schema version
warning; the legitimate fixes it applies are usually just additive field
defaults (e.g. `agent.service_tier: ''`) and a `_config_version` bump,
both of which can be hand-applied.

### Why `HERMES_HOME = repo dir` is forbidden

`tools/skills_sync.py` copies `<repo>/skills/` → `$HERMES_HOME/skills/`.
If both resolve to the same path, `shutil.copytree` raises
`FileExistsError`. Keep them separate: repo at `~/Projects/hermes-agent`,
HERMES_HOME at `~/.hermes`.

### `~/Projects` → `/Volumes/Store/Projects` symlink

On home-, `~/Projects` is a symlink to `/Volumes/Store/Projects`. Python
canonicalizes the path, so `hermes --version` shows
`Project: /Volumes/Store/Projects/hermes-agent`. This is **not** a
separate install — same directory, different path.

## Rollback

```sh
ssh home- 'rm -rf ~/Projects/hermes-agent ~/.hermes ~/.local/bin/hermes'
```

This removes the fork clone, HERMES_HOME (including migrated state),
and the CLI symlink. `~/.zshrc` was not modified.

## Post-deployment: install gateway services

Each profile has its own gateway launchd service. After Phase 3:

```sh
# Default profile gateway
ssh home- '~/.local/bin/hermes gateway install'

# Per-profile — create alias first so hermes -p <name> works, then install
ssh home- '~/.local/bin/hermes profile alias coder && ~/.local/bin/hermes -p coder gateway install'
ssh home- '~/.local/bin/hermes profile alias ea    && ~/.local/bin/hermes -p ea gateway install'
```

This creates three launchd plists:
- `~/Library/LaunchAgents/ai.hermes.gateway.plist` (default)
- `~/Library/LaunchAgents/ai.hermes.gateway-coder.plist`
- `~/Library/LaunchAgents/ai.hermes.gateway-ea.plist`

Verify via `launchctl list | grep ai.hermes.gateway` (not `hermes profile
list` — that command's Gateway column has a display bug and reports
"stopped" for profile gateways even when running).

**Note**: all three profiles have independent Slack Apps in the legacy
setup. Logs should show three distinct `Authenticated as @<bot>` lines:
`@agent` (default), `@z-bot` (coder), `@ea` (ea).

## Version updates / upgrading the fork

Routine workflow when upstream ships new commits or you add local fork
patches. **All steps run on home-** — via `ssh home- '...'` from any
laptop, or local-on-home- by dropping the ssh wrapper.

### Step 1 — sync upstream on home-

```sh
ssh home- '
cd ~/Projects/hermes-agent
git status                                       # must be clean
git fetch upstream
git log --oneline main..upstream/main            # preview new commits
git diff main..upstream/main -- pyproject.toml package.json hermes_constants.py
'
```

Review the commit list and the diff of the 3 conflict-prone files.
Decide whether to merge. If clean, proceed:

```sh
ssh home- '
cd ~/Projects/hermes-agent
git merge upstream/main --no-ff -m "chore: sync upstream $(date +%Y-%m-%d)"
'
```

If the merge reports conflicts in `pyproject.toml`, `package.json`, or
`hermes_constants.py`, resolve them on home- (easiest via local-on-home-
shell or VS Code Remote SSH):

```sh
ssh home- 'cd ~/Projects/hermes-agent && git status'
# For each conflicted file:
#   ssh home- "cd ~/Projects/hermes-agent && git checkout --theirs <file>"
#   # then manually re-apply the fork patch (authors, URLs, env override)
#   ssh home- "cd ~/Projects/hermes-agent && git add <file>"
# Finally:
ssh home- 'cd ~/Projects/hermes-agent && git merge --continue'
```

### Step 2 — push merged main back to origin (from home-)

```sh
ssh home- 'cd ~/Projects/hermes-agent && git push origin main'
```

home- now IS the source of truth. No rsync step needed — the code
change is already present because home- is where the merge happened.

### Step 3 — refresh deps (only if `pyproject.toml` / `uv.lock` changed)

```sh
ssh home- '
cd ~/Projects/hermes-agent
VIRTUAL_ENV=venv uv sync --all-extras --locked
'
```

Safe to skip if the merge didn't touch the lockfile. If the merge
re-created `venv/` (e.g. via aggressive clean), see Step 4.

### Step 4 — re-verify `sitecustomize.py` + `truststore`

Only needed if the venv was rebuilt, Python minor version changed, or
certifi was reinstalled. Quick check:

```sh
ssh home- '~/Projects/hermes-agent/venv/bin/python -c "
import ssl
ctx = ssl.create_default_context()
assert \"truststore\" in type(ctx).__module__, \"FIX: re-run Phase 2.5\"
print(\"OK truststore still active\")
"'
```

If this fails, re-run Phase 2.5 (install `truststore` + recreate
`sitecustomize.py`).

### Step 5 — restart all gateway services

```sh
ssh home- '
  ~/.local/bin/hermes gateway restart
  ~/.local/bin/hermes -p coder gateway restart
  ~/.local/bin/hermes -p ea gateway restart
'
```

### Step 6 — verify

```sh
# All 3 gateways running
ssh home- 'launchctl list | grep ai.hermes.gateway'

# Recent logs — look for "Authenticated as @<bot>" and no recent errors
ssh home- '
  for P in default coder ea; do
    B=~/.hermes
    [ "$P" = default ] || B=~/.hermes/profiles/$P
    echo "--- $P ---"
    grep -E "Authenticated as|response ready|API call failed" $B/logs/gateway.log | tail -3
  done
'
```

Then test each bot via Slack (if you changed anything in message
handling, auth, or providers).

### Step 7 — commit and push any new `[fork]` patches

If the upgrade prompted local fork fixes (doc updates, new gotcha
patches, etc.), commit them on home- and push:

```sh
ssh home- '
cd ~/Projects/hermes-agent
git add <files>
git commit -m "[fork] ..."
git push origin main
'
```

### Rollback of a failed upgrade

```sh
# Find the previous-known-good SHA from the log
ssh home- 'cd ~/Projects/hermes-agent && git log --oneline -20'

# Reset to it (only force-push if you already pushed the bad commit)
ssh home- 'cd ~/Projects/hermes-agent && git reset --hard <previous-sha>'
ssh home- 'cd ~/Projects/hermes-agent && git push --force-with-lease origin main'  # ONLY if needed

# Restart gateways
ssh home- '
  ~/.local/bin/hermes gateway restart
  ~/.local/bin/hermes -p coder gateway restart
  ~/.local/bin/hermes -p ea gateway restart
'
```

## Post-deployment TODO

- [ ] Re-authenticate any provider that needs it (Anthropic, Codex) via
      `hermes auth login` if applicable
- [ ] Configure scheduled cron jobs if any (legacy `cron/` was empty —
      jobs probably lived in `state.db` which we excluded)
