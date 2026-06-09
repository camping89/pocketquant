---
phase: 1
title: "Package & module rename + import codemod"
status: completed
priority: P1
effort: "1h"
dependencies: []
---

# Phase 1: Package & module rename + import codemod

## Overview

Rename the package directory, the module dir, the dist name, the entry-point import target, and sweep all 253 `pocketquant.api` import references across 109 `.py` files. This phase produces a tree that imports under `pocketquant.app` but is not yet re-synced (Phase 2 runs `uv sync` + config).

## Requirements

- Functional: every `from pocketquant.api...` / `import pocketquant.api...` resolves to `pocketquant.app`; dist name `pocketquant-app`; module dir `.../pocketquant/app/`.
- Non-functional: zero behavior change; no over-replace of bare `api` token or `/api/v1` URL prefix.

## Architecture

`pocketquant-api` is the top layer (composition root). Nothing in core/infrastructure/execution/backtest/trading imports it (verified), so the codemod cannot break layering. Only two replacement patterns are valid:

- `pocketquant.api` → `pocketquant.app` (dotted module path)
- `pocketquant-api` → `pocketquant-app` (hyphenated dist name — handled in Phase 2 for config; the package's own `pyproject.toml` here)

**Forbidden replacements** (must NOT match): bare `api`, `api_prefix`, `/api/v1`, `register_routes`, `api=` local vars, route tags.

## Related Code Files

- Rename dir: `packages/pocketquant-api/` → `packages/pocketquant-app/`
- Rename dir: `packages/pocketquant-app/src/pocketquant/api/` → `.../src/pocketquant/app/`
- Modify: `packages/pocketquant-app/pyproject.toml` — `name = "pocketquant-app"`; `[project.scripts] pocketquant = "pocketquant.app.main:run"`; `[tool.hatch.build.targets.wheel] packages = ["src/pocketquant"]` (unchanged — namespace dir stays `pocketquant`)
- Modify: 109 `.py` files containing `pocketquant.api` (codemod) — package internals + `tests/api_test/`

## Implementation Steps

1. **Pre-flight inventory** — capture baseline so Phase 4 can diff:
   ```bash
   rg -c 'pocketquant\.api' --glob '*.py' | sort
   rg -l 'pocketquant\.api' --glob '*.py' | wc -l   # expect 109
   rg 'pocketquant\.api' --glob '*.py' | wc -l       # expect 253
   ```
2. **Rename module dir** (git-aware to preserve history):
   ```bash
   git mv packages/pocketquant-api/src/pocketquant/api packages/pocketquant-api/src/pocketquant/app
   ```
3. **Rename package dir**:
   ```bash
   git mv packages/pocketquant-api packages/pocketquant-app
   ```
4. **Codemod imports** — replace ONLY the dotted module path across `.py` files. Restrict to the exact string `pocketquant.api` (word-boundary safe — `.api` cannot be a prefix of `apiX` because next char after the path segment is `.`/space/`)`/newline):
   ```bash
   rg -l 'pocketquant\.api' --glob '*.py' | xargs sed -i '' 's/pocketquant\.api/pocketquant.app/g'   # macOS sed: -i ''
   ```
   > NOTE on macOS BSD sed: use `sed -i ''`. The `pocketquant.api` string only ever appears as a module path in `.py` files; there is no `/api/v1` or `api_prefix` collision because those never contain the literal `pocketquant.api`.
5. **Edit the package's own `pyproject.toml`** (`packages/pocketquant-app/pyproject.toml`):
   - `name = "pocketquant-api"` → `name = "pocketquant-app"`
   - `pocketquant = "pocketquant.api.main:run"` → `pocketquant = "pocketquant.app.main:run"` (command name unchanged per D1)
   - `description` — optional: "composition root" wording stays accurate.
   - `[tool.hatch.build.targets.wheel] packages = ["src/pocketquant"]` — **unchanged** (namespace root dir is still `pocketquant`).
6. **Sanity grep** (still inside this phase, before sync):
   ```bash
   rg 'pocketquant\.api' --glob '*.py'                 # expect 0
   rg 'from pocketquant\.app' --glob '*.py' | head     # spot-check shape
   ```

## Success Criteria

- [ ] `packages/pocketquant-app/src/pocketquant/app/` exists; old `packages/pocketquant-api/` gone.
- [ ] `rg 'pocketquant\.api' --glob '*.py'` = 0 hits.
- [ ] Package `pyproject.toml`: `name = "pocketquant-app"`, entry `pocketquant.app.main:run`, command still `pocketquant`.
- [ ] No edits to `/api/v1`, `api_prefix`, `register_routes`, or any bare `api` token (verify via `git diff` spot-check).
- [ ] `git status` shows renames (R) not delete+add, so history is preserved.

## Risk Assessment

- **Over-replace bare `api`** (Med) → mitigation: sed pattern anchored to literal `pocketquant\.api`; this substring never appears in URL prefixes or local vars. Review `git diff` for any `api_prefix`/`/api/v1`/`register_routes` change (expect none).
- **git mv vs plain mv** (Low) → use `git mv` so history follows; if a tool already moved files, `git add -A` reconciles.
- **Namespace dir accidentally renamed** (Med) → the `pocketquant/` namespace dir must stay; only its child `api/` → `app/`. Hatch wheel target `src/pocketquant` unchanged.

## Next Steps

→ Phase 2: `uv sync`, fix build/run/CI config + workspace sources + import-linter + Dockerfile CMD + test dir rename.
