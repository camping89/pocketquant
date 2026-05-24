# Reference Audit — Deploy Folder Consolidation

**Generated:** 2026-05-24 18:50
**Scope:** active code/config/docs only. Excludes `.venv`, `node_modules`, caches, plan/journal/brainstorm files.

## Legend

- **MUST UPDATE** — active file; later phase rewrites this ref
- **SKIP** — plan/journal/brainstorm/historical; leave as-is

## Inventory

### `docker/compose` references

| File | Line | Old | Disposition | Phase |
|------|------|-----|-------------|-------|
| `deploy.sh` | 8 | `docker/compose.prod.yml` (comment) | MUST UPDATE | 3 |
| `deploy.sh` | 50 | `docker/compose.prod.yml` + `--env-file docker/.env` | MUST UPDATE | 3 |
| `docs/deployment-guide.md` | 97 | `scp ... docker/compose.prod.yml` | MUST UPDATE | 6 |
| `docs/deployment-guide.md` | 152 | `scp ... docker/compose.prod.yml` | MUST UPDATE | 6 |
| `docs/deployment-guide.md` | 298 | `docker compose -f docker/compose.prod.yml --env-file docker/.env` | MUST UPDATE | 6 |
| `docs/deployment-guide.md` | 301 | same + `bash deploy.sh` | MUST UPDATE | 6 |
| `docs/project-overview-pdr.md` | 509 | `docker compose -f docker/compose.yml up -d` | MUST UPDATE | 6 |
| `docs/project-overview-pdr.md` | 517 | `docker compose -f docker/compose.yml up -d` | MUST UPDATE | 6 |
| `justfile` | 17 | `docker compose -f docker/compose.yml up -d` (recipe `up`) | MUST UPDATE | 5 |
| `justfile` | 21 | same (`down`) | MUST UPDATE | 5 |
| `justfile` | 25 | same `down -v` (`reset`) | MUST UPDATE | 5 |
| `justfile` | 52 | same `up -d redis` (`redis`) — note: plan said line 56, actual is 52 | MUST UPDATE | 5 |
| `plans/260524-1805-*/` (all phase files) | n/a | self-refs | SKIP | — |

### `docker/.env` references

| File | Context | Disposition | Phase |
|------|---------|-------------|-------|
| `deploy.sh` lines 26, 27, 33, 50 | various | MUST UPDATE | 3 |
| `verify.sh` line 150 | `source docker/.env 2>/dev/null \|\| true` | MUST UPDATE | 3 |
| `docs/deployment-guide.md` (multiple) | scp + docker compose invocations | MUST UPDATE | 6 |

### `docker/scripts/` references

| File | Line | Old | Disposition |
|------|------|-----|-------------|
| (no active code refs found) | — | — | — |
| All matches in `plans/` (this plan) | — | self-refs | SKIP |

### `docker/mongo-init` references

| File | Line | Disposition |
|------|------|-------------|
| (no active code refs found) | — | — |
| All matches in `plans/` (this plan) | — | SKIP |

### `scripts.one_time_purge_legacy_strategies`

| File | Disposition |
|------|-------------|
| `deploy.sh` | NOT PRESENT — already cleaned (see implementation-questions.md entry) |
| All other matches in `plans/`, reports | SKIP |

### `bash deploy.sh` references

| File | Lines | Disposition | Phase |
|------|-------|-------------|-------|
| `deploy.sh` 9, 12 | header comments | MUST UPDATE | 3 |
| `docs/deployment-guide.md` 104, 146, 153, 160, 301 | VPS ssh invocations | MUST UPDATE | 6 |

### `bash verify.sh` references

| File | Lines | Disposition | Phase |
|------|-------|-------------|-------|
| `verify.sh` 8 | header comment | MUST UPDATE | 3 |
| `docs/deployment-guide.md` 123 | VPS ssh invocation | MUST UPDATE | 6 |

### `Dockerfile` references (active, non-plan)

| File | Lines | Old | Disposition | Phase |
|------|-------|-----|-------------|-------|
| `.gitattributes` 22, 23 | `Dockerfile text eol=lf` / `Dockerfile.* text eol=lf` | LEAVE (glob still matches `deploy/Dockerfile`) | — |
| `.github/workflows/ci.yml` 32 | `docker/build-push-action@v5` with `context: .` — no `file:` line | MUST UPDATE (add `file: deploy/Dockerfile`) | 4 |
| `.dockerignore` | excludes `docker/` (line 16) | MUST UPDATE (`docker/` → `deploy/`) | 4 |
| `packages/pocketquant-web/Dockerfile` | n/a — out of scope per plan | SKIP | — |

### `.env` paths (shell/yml/Dockerfile)

| File | Disposition | Phase |
|------|-------------|-------|
| `deploy.sh` `docker/.env` paths | MUST UPDATE → `.env` (sibling) | 3 |
| `verify.sh` `docker/.env` | MUST UPDATE → `.env` (sibling) | 3 |
| `docs/deployment-guide.md` | MUST UPDATE | 6 |
| `README.md` line 42 `cp .env.example .env` | LEAVE (still valid — refers to local dev env at repo root or deploy/.env via `just up`) — but better: update to `cp deploy/.env.example deploy/.env` post-move | MUST UPDATE | 6 |
| `.gitignore` line 59 `.env` (glob) | LEAVE (matches `deploy/.env` automatically) | — |

### Spot-check (per Phase 1 success criteria)

- [x] `justfile` 4× — found at lines 17, 21, 25, 52 (plan said line 56)
- [ ] `scripts/check_env.py:50` — **NOT FOUND** — file `check_env.py` does not exist in `scripts/`. See implementation-questions.md.
- [x] `Dockerfile` (COPY) — present at repo root; will move via `git mv` in Phase 2
- [x] `.github/workflows/ci.yml` — confirmed; needs `file:` line added
- [x] `docs/deployment-guide.md` — multiple refs confirmed
- [x] `docs/project-overview-pdr.md` — 2 refs at L509, L517

### Additional finding (not in plan)

- `.dockerignore` line 16 `docker/` → should become `deploy/` so Docker excludes deploy/.env, compose files, scripts from the build context (currently `docker/` is excluded, but post-move there's no docker/ to exclude).

### Divergences from plan (logged separately)

See `implementation-questions.md`:
1. `deploy.sh` stale `one_time_purge` block — already absent
2. `scripts/check_env.py` — file does not exist
3. `justfile` `check` recipe — does not exist (only `qa`, `lint`, `fmt`, `types`, `test`, `up`, `down`, `reset`, `redis`, `be`, `fe`, `install`, `test-pkg`)
4. `just dev` recipe (referenced in README L45 + plan success criteria) — does not exist
5. `.run/` — only `main.py.run.xml` exists; no deploy/docker refs in it (grep clean)
