---
phase: 3
title: "Docs & references sweep"
status: completed
priority: P2
effort: "45m"
dependencies: [1, 2]
---

# Phase 3: Docs & references sweep

## Overview

Update all live documentation and stray references to the renamed package: `README.md`, `CLAUDE.md`, every `docs/*.md` mentioning the package, and the one `web` TS comment. Per D2, historical `plans/` are NOT rewritten (git holds history).

## Requirements

- Functional: docs describe the current system — package is `pocketquant-app`, module path `pocketquant.app`.
- Non-functional: follow CLAUDE.md Documentation Policy (AS-IS, no changelog/migration banners, Vietnamese prose with English code terms).

## Architecture

Docs reference the package two ways:
- Monorepo tree + dependency graph (`pocketquant-api/` box, `... ◁ api` edge, `web → api`).
- Inline module paths / dist name (`pocketquant.api.di.container`, `pocketquant-api`).

Both swap to `app`. The dependency-graph edge label `api` (e.g. `core ◁ ... ◁ api`, `web → api`) → `app`. Keep `/api/v1` URL examples in README curl snippets **unchanged** (those are live HTTP paths).

## Related Code Files

- Modify: `README.md` — monorepo tree (`pocketquant-api/` → `pocketquant-app/`), dependency direction (`... ◁ api`, `web → api` → `app`). **Keep** all `/api/v1` curl URLs + `:41920/api/v1/docs`.
- Modify: `CLAUDE.md` — monorepo tree, dependency graph, Package Imports block (`from pocketquant.api.di.container import create_container` etc.), DI Container section ("6 providers in `pocketquant.api.di/`"), any `pocketquant-api` box.
- Modify: `docs/README.md` (index)
- Modify: `docs/system-architecture.md`
- Modify: `docs/code-standards.md`
- Modify: `docs/project-overview-pdr.md`
- Modify: `docs/websocket-architecture.md`
- Modify: `docs/handler-pipelines.md`
- Modify: `docs/features/strategy-lifecycle.md`
- Modify: `docs/journals/sp1-declarative-control-plane-shipped-260609.md` — contains `pocketquant.api` path refs; update to `pocketquant.app` so the path named matches the tree that now exists (git preserves the original).
- Modify: `packages/pocketquant-web/src/constants/active-intervals.ts` — line 4 comment `pocketquant.api.market_data.app_services.sync_jobs` → `pocketquant.app.market_data.app_services.sync_jobs` (comment only; D4 keeps `web` package name).

## Implementation Steps

1. **Discover exact hits** (re-confirm — Phase 1/2 may have shifted counts):
   ```bash
   rg -n 'pocketquant-api|pocketquant\.api' --glob '!plans/**' --glob '!uv.lock' --glob '!repomix-output.xml' --glob '!.venv/**' --glob '!packages/pocketquant-web/node_modules/**'
   ```
2. **Edit docs prose** file-by-file (do NOT blind-sed docs — tree boxes + graph edges need the bare `api`→`app` label change *and* dotted paths; review each). Replace:
   - `pocketquant-api` → `pocketquant-app`
   - `pocketquant.api` → `pocketquant.app`
   - graph edge labels `api` → `app` (only in the dependency-graph/tree context, e.g. `◁ api`, `web → api`)
3. **Keep unchanged**: `/api/v1` URL paths, `api/v1/docs`, `api/v1/openapi.json` in README — these are HTTP endpoints, not module names.
4. **Web TS comment** — single-line edit in `active-intervals.ts`.
5. **CLAUDE.md** — verify Package Imports examples + DI section + naming-table examples (`pocketquant.api.di/`) all updated; this file is read by every future session, so accuracy matters most.

## Success Criteria

- [ ] `rg 'pocketquant-api|pocketquant\.api'` over the repo, excluding `plans/`, `uv.lock` history, `repomix-output.xml`, `.venv/`, `web/node_modules/` = 0 hits.
- [ ] README monorepo tree + dependency graph show `pocketquant-app` / `app`; `/api/v1` curl URLs intact.
- [ ] CLAUDE.md Package Imports + DI Container + tree/graph use `pocketquant.app`.
- [ ] All listed `docs/*.md` updated; no changelog/migration banner added (AS-IS policy).
- [ ] `active-intervals.ts` comment references `pocketquant.app...`.

## Risk Assessment

- **Blind-sed corrupts a `/api/v1` URL in docs** (Med) → edit docs by hand or use a path-anchored pattern (`pocketquant.api` / `pocketquant-api` only, never bare `api`); diff-review README curl block.
- **Missed graph edge label** (Low) → the `◁ api` / `web → api` edges use bare `api`; explicitly check README + CLAUDE.md graphs.
- **Journal AS-IS conflict** (Low) → editing the journal path ref is a value-correction (path that exists now), not a history rewrite; git keeps the original. No new dated banner added.

## Next Steps

→ Phase 4: full verification gate (uv sync, lint, types, import-linter, tests, Docker CMD smoke, final grep).
