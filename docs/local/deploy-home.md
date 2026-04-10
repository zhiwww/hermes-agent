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

## Deployment phases

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

## Post-deployment TODO

- [ ] Re-authenticate any provider that needs it (Anthropic, Codex) via
      `hermes auth login` if applicable
- [ ] Configure scheduled cron jobs if any (legacy `cron/` was empty —
      jobs probably lived in `state.db` which we excluded)
