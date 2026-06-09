---
title: "SP2 — Rename pocketquant-api → pocketquant-app"
description: "Mechanical rename of the composition-root package api→app. No behavior change. Module path, dist name, entry import, configs, test dir, docs."
status: completed
priority: P2
branch: "develop"
tags: [rename, refactor, monorepo, sp2]
blockedBy: []
blocks: []
created: "2026-06-09T07:57:25.801Z"
createdBy: "ck:plan"
source: skill
---

# SP2 — Rename pocketquant-api → pocketquant-app

## Overview

Package `pocketquant-api` is the composition root + runtime host (DI, migrations, scheduler, WS feed, strategy lifecycle), not an API/BFF layer. Rename to `pocketquant-app` to match its real role. Pure mechanical rename — zero behavior change. Existing test suite is the regression net.

Source: brainstorm report `plans/reports/brainstorm-260609-1137-sp2-rename-api-to-app-report.md`.

Verified scope: `pocketquant.api` = 253 occ / 109 `.py` files. Top layer — no backend package imports it, so rename cannot break layering. `web → api` is HTTP-only (no Python import).

## Locked decisions (user-confirmed 2026-06-09)

| # | Decision | Value |
|---|----------|-------|
| D1 | CLI command name | **Keep** `pocketquant`; only change import target → `pocketquant.app.main:run` |
| D2 | Rewrite historical `plans/` | **No** — git holds history. Only edit live code/config + `docs/` + `README.md` + `CLAUDE.md` |
| D3 | Test dir `tests/api_test/` | **Rename** → `tests/app_test/`; update CI path + pyright include + internal imports |
| D4 | `web` package | **Unchanged** — HTTP consumer only |
| D5 | CI job/label `build-api` | **Rename** → `build-app` + step label; update `needs[]` refs |

## Non-goals (do NOT touch)

- URL prefix `/api/v1` — HTTP path, not a module name. Stays.
- Bare token `api` in code (`api_prefix`, `register_routes` var) — only `pocketquant.api` / `pocketquant-api` get replaced.
- Docker Hub image name `pocketquant` (prod) — already not `pocketquant-api`. Compose `container_name: pocketquant-app` already exists. No image/compose change.
- SP1 plan files (already merged/completed) and SP3 brainstorm — history.

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [Package & module rename + import codemod](./phase-01-package-module-rename-import-codemod.md) | Completed |
| 2 | [Build/run/CI config + test dir rename](./phase-02-build-run-ci-config-test-dir-rename.md) | Completed |
| 3 | [Docs & references sweep](./phase-03-docs-references-sweep.md) | Completed |
| 4 | [Verify](./phase-04-verify.md) | Completed |

## Dependencies

- SP1 (declarative control plane) — **completed/merged**. SP1's new code lives under `pocketquant.api.*`; the codemod sweeps it too. No ordering constraint.
- SP3 (split app/bff) — brainstorm only, not yet a plan. SP3 will split HTTP out of `app` into a new `bff`; this rename gives SP3 the correct base name. No bidirectional update needed (no SP3 plan frontmatter exists).
