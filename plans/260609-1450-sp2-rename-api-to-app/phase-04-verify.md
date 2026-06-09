---
phase: 4
title: "Verify"
status: completed
priority: P1
effort: "30m"
dependencies: [1, 2, 3]
---

# Phase 4: Verify

## Overview

Run the full regression gate. Rename is mechanical, so the existing suite + linters + container smoke are the acceptance proof. No new tests written (behavior unchanged).

## Requirements

- All existing tests pass under the renamed module/dir.
- Lint, type-check, import-linter green.
- App entry + Docker CMD boot.
- Zero stale `pocketquant-api` / `pocketquant.api` in live code/config/docs.

## Implementation Steps

1. **Relock check** (idempotent):
   ```bash
   uv sync
   ```
2. **Lint + format + types**:
   ```bash
   just lint
   just types
   ```
3. **import-linter** (run via the dev tool; CI uses it too):
   ```bash
   uv run lint-imports
   ```
   Expect all 7 contracts pass with top layer `pocketquant.app`.
4. **Tests** (renamed dir):
   ```bash
   just test                 # full suite
   just test-pkg app         # the renamed package's tests (tests/app_test/)
   ```
   > NOTE: requires `.env` present (conftest seeds placeholders, but bare `Settings()` fails without env) — `cp ../pocketquant-config/local/all-local.env .env` if missing, and `just up` for Mongo/Redis testcontainers/integration.
5. **Entry point**:
   ```bash
   uv run pocketquant --help 2>&1 | head     # command name still 'pocketquant', target pocketquant.app.main:run
   ```
6. **Docker CMD smoke** (validates `pocketquant.app.main:app` import path):
   ```bash
   docker build -f deploy/Dockerfile -t pocketquant-sp2-smoke .
   docker run --rm --env-file .env -p 41921:41920 pocketquant-sp2-smoke &
   sleep 8 && curl -fsS http://localhost:41921/health && echo " OK"
   docker stop $(docker ps -q --filter ancestor=pocketquant-sp2-smoke) 2>/dev/null || true
   ```
   (Or, lighter: `uv run uvicorn pocketquant.app.main:app --port 41921` then curl `/health`.)
7. **Final residual grep** (the acceptance metric):
   ```bash
   rg 'pocketquant-api|pocketquant\.api' \
     --glob '!plans/**' --glob '!uv.lock' --glob '!repomix-output.xml' \
     --glob '!.venv/**' --glob '!packages/pocketquant-web/node_modules/**'
   ```
   Expect **0 hits**. (`plans/` excluded per D2; `uv.lock` should already be 0 after sync; `repomix-output.xml` is a stale generated snapshot — ignore or regenerate separately.)
8. **Diff review** — confirm no `/api/v1`, `api_prefix`, or `register_routes` was touched:
   ```bash
   git diff --stat
   git diff | rg -n 'api_prefix|/api/v1|register_routes' || echo "clean: no URL/var collateral"
   ```

## Success Criteria

- [ ] `just lint` + `just types` clean.
- [ ] `uv run lint-imports` — all contracts pass.
- [ ] `just test` — full suite green (same pass count as pre-rename baseline).
- [ ] `uv run pocketquant --help` resolves; command name unchanged.
- [ ] Docker build + `/health` 200 (or uvicorn `pocketquant.app.main:app` boots).
- [ ] Final grep = 0 live hits.
- [ ] `git diff` shows no change to `/api/v1`, `api_prefix`, `register_routes`.

## Risk Assessment

- **Test env missing** (Med) → `.env` + `just up` required; see [[pocketquant-tests-need-env-or-bare-settings-fails]]. Pre-rename baseline pass count must match post-rename.
- **repomix-output.xml false positives** (Low) → generated stale snapshot, not live code; exclude from grep or regenerate post-merge.
- **Container can't reach Mongo/Redis in smoke** (Low) → `/health` may report degraded but the import path (the thing being verified) still proves the CMD resolves; uvicorn-only fallback isolates the import check.

## Next Steps

- Mark plan completed; commit (conventional: `refactor: rename pocketquant-api package to pocketquant-app`).
- SP3 (split app/bff) can now build on the correct `pocketquant.app` base name.
