---
phase: 2
title: "Build/run/CI config + test dir rename"
status: completed
priority: P1
effort: "1.5h"
dependencies: [1]
---

# Phase 2: Build/run/CI config + test dir rename

## Overview

Update every live config that names the old package/module: root workspace sources, import-linter contracts, pyright, justfile, Dockerfile CMD, CI workflow, and rename `tests/api_test/` → `tests/app_test/`. Then `uv sync` to relock. After this phase the app builds, runs, lints, and CI paths are correct.

## Requirements

- Functional: `uv sync` succeeds; `uv run pocketquant` boots; import-linter passes with renamed top layer; Docker CMD points to `pocketquant.app.main:app`; CI runs `tests/app_test/`.
- Non-functional: lockfile committed; no stale `pocketquant-api` / `pocketquant.api` in any live config.

## Architecture

Two ref shapes to fix outside `.py`:
- Hyphenated dist `pocketquant-api` → `pocketquant-app` (workspace sources, root dep, package list, pyright includes, Dockerfile COPY, CI image-less refs).
- Dotted module `pocketquant.api` → `pocketquant.app` (root `pyproject.toml` entry/importlinter, justfile uvicorn target, Dockerfile CMD).

Docker Hub **image name stays `pocketquant`** (prod) — never was `pocketquant-api`; compose `container_name: pocketquant-app` already exists. No image/compose edits.

## Related Code Files

- Modify: root `pyproject.toml`
  - `[project] dependencies = ["pocketquant-api"]` → `["pocketquant-app"]`
  - `[tool.uv.sources] pocketquant-api = { workspace = true }` → `pocketquant-app = { workspace = true }`
  - `[tool.importlinter]` — every `pocketquant.api` (layer `pocketquant.api` in the layers contract + `pocketquant.api` in each forbidden contract) → `pocketquant.app`
- Modify: `pyrightconfig.json` — include `packages/pocketquant-api/src` → `packages/pocketquant-app/src`; include `tests/api_test` → `tests/app_test`; executionEnvironment root `tests/api_test` → `tests/app_test`
- Modify: `justfile` — `be:` recipe `pocketquant.api.main:app` → `pocketquant.app.main:app`; `test-pkg` comment lists `(core, backtest, trading, api)` → `(core, backtest, trading, app)`
- Modify: `deploy/Dockerfile`
  - line ~23 `COPY packages/pocketquant-api/pyproject.toml packages/pocketquant-api/` → `pocketquant-app`
  - line ~64 `CMD ["uvicorn", "pocketquant.api.main:app", ...]` → `pocketquant.app.main:app`
- Modify: `.github/workflows/cicd.yml`
  - step `Run pytest (pocketquant-api)` label → `(pocketquant-app)`; path `tests/api_test/` → `tests/app_test/`
  - job `build-api:` → `build-app:`
  - `needs: [build-api, build-web]` (2 places: `cleanup-tags`, `deploy`) → `[build-app, build-web]`
  - NOTE: Docker Hub repo refs (`/pocketquant`, `/pocketquant-web`) unchanged.
- Rename: `tests/api_test/` → `tests/app_test/` (git mv); internal imports already fixed by Phase 1 codemod.

## Implementation Steps

1. **Rename test dir**:
   ```bash
   git mv tests/api_test tests/app_test
   ```
2. **Root `pyproject.toml`** — edit the 3 regions (dependencies, uv.sources, importlinter). Replace `pocketquant-api`→`pocketquant-app` and `pocketquant.api`→`pocketquant.app`. The importlinter layers contract top layer `"pocketquant.api"` → `"pocketquant.app"`; every forbidden contract listing `"pocketquant.api"` → `"pocketquant.app"`.
3. **`pyrightconfig.json`** — swap the two `api`→`app` include paths + executionEnvironment root.
4. **`justfile`** — `be:` uvicorn target + `test-pkg` comment.
5. **`deploy/Dockerfile`** — COPY path (line ~23) + CMD module (line ~64).
6. **`.github/workflows/cicd.yml`** — label, test path, `build-api`→`build-app` job key, both `needs[]` arrays.
7. **Relock**:
   ```bash
   uv sync
   ```
   Expect the lockfile to update the workspace member name `pocketquant-api`→`pocketquant-app`. Commit `uv.lock`.
8. **Smoke checks** (full gate is Phase 4):
   ```bash
   uv run pocketquant --help 2>&1 | head    # entry resolves
   just types                                # pyright sees new paths
   ```

## Success Criteria

- [ ] `tests/app_test/` exists; `tests/api_test/` gone.
- [ ] `uv sync` succeeds; `uv.lock` updated to `pocketquant-app` and committed.
- [ ] Root `pyproject.toml`: dep, uv.sources key, all import-linter contracts use `pocketquant.app` / `pocketquant-app`.
- [ ] `pyrightconfig.json` includes `packages/pocketquant-app/src` + `tests/app_test`.
- [ ] `justfile be:` runs `pocketquant.app.main:app`.
- [ ] `deploy/Dockerfile` COPY + CMD use `pocketquant-app` / `pocketquant.app.main:app`.
- [ ] `cicd.yml`: job `build-app`, pytest path `tests/app_test/`, both `needs[]` reference `build-app`.
- [ ] `rg 'pocketquant-api|pocketquant\.api'` over root configs + deploy + .github = 0 hits.

## Risk Assessment

- **uv.lock / workspace drift** (Med) → re-run `uv sync`, commit fresh lock; if `--frozen` paths (Docker/CI) fail, lock is stale.
- **Dockerfile CMD typo → container dies** (Med) → Phase 4 smoke-runs the container CMD locally.
- **import-linter contract missed → CI red** (Low) → grep root `pyproject.toml` for any residual `pocketquant.api`; all 7 contracts checked.
- **CI `needs[]` left pointing at `build-api`** (Med) → graph breaks; both `cleanup-tags` and `deploy` updated.

## Next Steps

→ Phase 3: docs + README + CLAUDE.md + web TS comment sweep.
