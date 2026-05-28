# Deferred items + open questions surfaced during /ck:cook of plan 260528-2000

Captured per user request: "log questions later, do not ask me to run".

## Bugs found + fixed during smoke-test (NOT in original plan scope)

### 1. `db.database` AttributeError in `migrate_strategy_id_fields`

- **Location:** `packages/pocketquant-api/src/pocketquant/api/main_extensions.py` lines 138, 148, 160, 186.
- **Root cause:** `Database` wrapper exposes only `get_database()` (public) and `get_collection()`. Name-mangled `__database` is not reachable via `db.database`. Code attempted direct attribute access → `AttributeError` at boot.
- **Fix applied:** `db.database` → `db.get_database()` (4 sites). Commit `a6e6262`.
- **Why this leaked into the smoke-test:** App was already broken on the registry image used by the running VPS containers (kept alive from before the migration commit landed). The instant `deploy.sh` recreated the app container with the latest image, the bug surfaced. Pre-existed `260528-2000` plan; only discovered because this plan first executed `deploy.sh` end-to-end.

### 2. `deploy/vps/deploy.sh` validates env vars not present in `pocketquant-config/vps/default/.env`

- Plan assumed prod `.env` was complete. Reality: `MONGO_PASSWORD`, `MONGO_USER`, `WEB_PORT` were missing. `MONGO_PASSWORD` was inlined in `MONGODB_URL` but never separately exported — so the running Mongo container had been initialized once 2 weeks ago and never re-validated.
- **Fix applied:** appended the 3 keys to `pocketquant-config/vps/default/.env`. Commit `40eef0d` (pocketquant-config).

### 3. GitHub Actions heredoc output requires trailing newline

- **Symptom:** `Invalid value. Matching delimiter not found 'DOTENV_EOF'`.
- **Root cause:** `printf '%s'` (no `\n`) appended `DOTENV_EOF` to the last line of value → GH could not detect delimiter on its own line.
- **Fix applied:** `printf '%s\n'` in composite action heredocs + in deploy job's `Setup SSH` / `Write prod .env` steps. Commits `4596c5d` + `ed7008a`.

### 4. SSH key trailing newline

- **Symptom:** `Load key "/home/runner/.ssh/id_rsa": error in libcrypto` → `Permission denied`.
- **Root cause:** Same family as #3 — `$(normalize ...)` strips trailing newline; consumer must re-add `\n` when writing to `~/.ssh/id_rsa`. OpenSSH refuses a key missing its trailing LF.
- **Fix applied:** `printf '%s\n' "$SSH_KEY"`.

### 5. `DOCKERHUB_USERNAME` not in prod `.env`

- **Symptom:** `ERROR: DOCKERHUB_USERNAME not set in deploy/.env`.
- **Root cause:** Docker Hub creds live in `docker-hub.env`, not `.env`. `deploy.sh` validates against `.env`.
- **Fix applied:** `Write prod .env` step appends `DOCKERHUB_USERNAME=<cfg.outputs.dockerhub_username>` after writing `ENV_CONTENT`. Commit `3bf5da1`.

## Open question — log scrub minor leak

- VPS IP appears once in the workflow log because `pocketquant-config/vps/default/.env` starts with a comment:
  `# PocketQuant Production Configuration (VPS: 207.148.79.60)`
- GH masks discrete values registered via `::add-mask::`. The IP is registered as a value (via `vps_host` mask) but the masker matches substrings, and the comment also got masked in body content — except the YAML preamble dump of `env:` block prints `ENV_CONTENT: # *** Production Configuration (VPS: 207.148.79.60)`, where the IP slipped through because nothing else registered the IP-only substring before that line printed.
- Severity: **Low** — IP of a running prod VPS is not credential material (port-scanned anyway); but pedantically violates the "zero plaintext leaks" criterion.
- Possible fixes: (a) strip the VPS-IP comment from `.env`; (b) issue `::add-mask::<ip-only>` early in the composite action by parsing `host` for the IP portion. Defer.

## Tech debt to address in a future plan

- ~~**Node.js 20 deprecation warnings**~~ — **CLOSED 2026-05-28.** Bumped actions/checkout v4→v5, docker/setup-buildx v3→v4, docker/login v3→v4, docker/metadata v5→v6, docker/build-push v5→v7, actions/upload-artifact v4→v7. Workflow runs with zero Node 20 warnings (verified gh run 26588574964).
- ~~**`deploy/vps/deploy.sh` REQUIRED_VARS reconciliation**~~ — **CLOSED 2026-05-28.** Extracted to `deploy/vps/required-env-vars.txt` (single source of truth, tracked in repo). `deploy.sh` reads the file + lists ALL missing keys at once. New `Validate prod .env` step in cicd.yml fails the deploy job pre-rsync (~5 s) instead of mid-VPS-boot.
- ~~**Minor log leak: VPS IP in `.env` comment header**~~ — **CLOSED 2026-05-28.** Stripped IP from `pocketquant-config/vps/default/.env` line 1. Comment now reads "# PocketQuant Production Configuration".
- **`packages/pocketquant-api/src/pocketquant/api/main_extensions.py` lacks a test** for the migration path that would have caught the `db.database` AttributeError. STILL OPEN.
- **`Database` wrapper API debate.** `db.database` AttributeError suggests `Database` is fighting consumers. Consider exposing the underlying `AsyncDatabase` as a public `database` property (without name mangling) and dropping `get_database()` — or removing `db.<anything>` accesses outside the wrapper. STILL OPEN.

## Deviations from plan

- Plan called for committing only `.github/actions/get-vps-config/action.yml + .github/workflows/cicd.yml` on the throwaway branch. In practice, the smoke branch also bundled the still-uncommitted artifacts from superseded plan `260528-1700` (ci.yml → cicd.yml rename, `deploy/scripts-to-deploy/` → `deploy/vps/` move, `docs/deployment-guide.md` → `docs/deployment.md`, `.env.example` relocation, plans/ tree). Without this bundling, CI/CD would have lacked `deploy/vps/{deploy,verify,server-setup,cleanup}.sh` and the workflow file itself — making a smoke test impossible.
- Plan assumed `MONGO_USER` / `MONGO_PASSWORD` / `WEB_PORT` already present in prod `.env`. Not true; added per item #2 above.
- Old GH secrets `VPS_HOST`, `VPS_SSH_KEY`, `PROD_ENV` returned 404 on delete because plan `260528-1700` never created them. Only `DOCKERHUB_USERNAME` + `DOCKERHUB_TOKEN` actually existed and were deleted.
