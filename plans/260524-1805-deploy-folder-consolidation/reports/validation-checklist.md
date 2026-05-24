# Validation Checklist — Deploy Folder Consolidation

**Run:** 2026-05-24 ~19:10 local
**Branch:** develop

## Final Grep Sweep

- [x] **zero orphan refs in active code/config** for `docker/compose`, `docker/scripts/`, `docker/mongo-init`, `scripts.one_time_purge_legacy_strategies`, `bash deploy.sh`, `bash verify.sh`
- [x] **expected survivors** (all justified):
  - `docs/deployment-guide.md` — VPS Migration Runbook + Rollback Runbook intentionally reference old paths (operator follows them once on the VPS)
  - `docs/project-changelog.md` — changelog entry describes the move in past tense
  - `plans/260524-1805-*/` — this plan's own self-references
  - Other `plans/2605*` — historical / completed plans, excluded per Phase 8 success criteria
  - `.gitattributes` `Dockerfile text eol=lf` glob — still matches `deploy/Dockerfile`, no update needed

## just Recipes

- [x] `just down` → exit 0, output `docker compose -f deploy/compose.yml down`
- [x] `just up`   → mongodb + redis containers started, health: starting/healthy
- [x] `just down` → clean teardown, all containers + network removed
- [ ] `just check` → **N/A — recipe does not exist** (logged in `implementation-questions.md`)

## Docker Builds

- [x] `docker build -f deploy/Dockerfile -t pocketquant:smoke .` → exit 0, image `pocketquant:smoke` (332MB) created
- [x] `docker build -f packages/pocketquant-web/Dockerfile -t pocketquant-web:smoke ./packages/pocketquant-web` → exit 0, image `pocketquant-web:smoke` (50MB) created (regression — no change intended)

## Local Prod-Stack Simulation

- [x] `compose.prod.yml up -d --remove-orphans` → containers created using `--env-file deploy/.env`, all images resolve, network + volumes provisioned
- [x] compose syntax + path wiring validated end-to-end (proof: `app` and `web` containers reached `Created` state from `local/...` tagged images; only failure was data-layer auth, not deploy-folder wiring)
- [ ] MongoDB healthy → **NOT validated locally** — local `deploy/.env` is dev-shaped (no `MONGO_USER`/`MONGO_PASSWORD`); prod compose requires them. This is environmental, NOT a defect of the refactor. Operator must run with a real prod `.env` on VPS.
- [ ] `/health` returns 200 → blocked by above
- [ ] `verify.sh` report = HEALTHY → blocked by above
- [x] `compose down -v` → clean teardown, volumes removed

## Script Dry-Traces

- [x] `deploy/deploy.sh` — no `docker/` refs, `cd "$(dirname "$0")"` anchors CWD to `deploy/`, all sibling paths (`.env`, `compose.prod.yml`) resolve correctly
- [x] `deploy/verify.sh` — only `.env` ref (line 150), no `docker/` substring; report dir = `./reports` (lands in `deploy/reports/` on VPS, intentional per plan)
- [x] `deploy/scripts/server-setup.sh` — `mkdir -p /opt/pocketquant/deploy/scripts/patches`; echo strings updated

## Configuration Touch-Points

- [x] `.dockerignore` — `docker/` → `deploy/` so build context excludes compose files / .env / scripts (avoids image bloat + secret leakage)
- [x] `.github/workflows/ci.yml` — `file: deploy/Dockerfile` added to build-api job; build-web unchanged
- [x] `justfile` — 4× `docker/compose.yml` → `deploy/compose.yml`
- [x] `docs/deployment-guide.md` — all live invocations use `deploy/...` paths; VPS Migration + Rollback runbooks inserted
- [x] `docs/project-overview-pdr.md` — 2× `docker/compose.yml` → `deploy/compose.yml`
- [x] `docs/project-changelog.md` — top entry documents the move + BREAKING flag + cross-link to runbook
- [x] `README.md` — quickstart updated (`cp deploy/.env.example deploy/.env`, `just be` instead of stale `just dev`)
- [x] `scripts/README.md` — preamble distinguishes data-ops from deployment

## Post-Merge Follow-ups

- [ ] **CI green on first push** — required; check Actions tab after pushing the branch
- [ ] **VPS migration runbook executed before next prod deploy** — see `docs/deployment-guide.md` § "VPS Migration Runbook"
- [ ] **Operator validates `/health` + `verify.sh` HEALTHY** on the real VPS after migration (the local-prod-sim couldn't run end-to-end without prod creds)

## Divergences Logged

5 divergences logged during implementation — see `implementation-questions.md`. None affect the refactor's intent; all are reality-vs-plan adjustments (stale plan assumptions corrected).

## Verdict

**Ready to commit + push.** All refactor wiring validated. Only end-to-end app-start verification deferred to VPS where prod `.env` lives. Rollback runbook published.
