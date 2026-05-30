---
phase: 2
title: "Sweep web (TypeScript SPA)"
status: completed
priority: P2
effort: "2h"
dependencies: [1]
---

# Phase 2: Sweep web (TypeScript SPA)

<!-- Updated: Validation Session 1 — web has no project Python; scope is the TS/TSX SPA instead -->

## Overview

Sweep `pocketquant-web` frontend — **103 `.ts/.tsx` files** under `src/` (TanStack Router/Query SPA, lightweight-charts). Apply the same WHY-not-WHAT keep-bar to JS comments (`//`, `/** */`). Web has zero project Python (its only `.py` is vendored `node_modules/flatted/flatted.py`, out of scope).

## Requirements
- Functional: redundant `//` comments + name-echo JSDoc removed; component behavior unchanged.
- Non-functional: eslint clean, `tsc -b` compiles. `node_modules`, `dist`, `.vite` OUT.

## Architecture
Vite + TanStack SPA. Files in `src/api`, `src/components/*`, `src/routes`, hooks. KEEP: comments explaining chart-primitive math, timezone handling, WebSocket/SSE reconnect quirks, lightweight-charts API gotchas, `// eslint-disable` reasons, `// @ts-expect-error` reasons. REMOVE: `// fetch data`, name-echo JSDoc, section banners.

## Related Code Files
- Modify: `packages/pocketquant-web/src/**/*.{ts,tsx}` (103 files), excluding node_modules/dist/.vite.

## Implementation Steps
1. Baseline: `cd packages/pocketquant-web && npm run lint` (eslint) + `npx tsc -b` → record clean.
2. Agent reads each `.ts/.tsx`, applies JS keep-bar, edits in place.
3. `npm run lint` → fix any new issues.
4. `npx tsc -b` → compiles clean.
5. Commit: `refactor: trim redundant comments in pocketquant-web`.

## Success Criteria
- [ ] `npm run lint` clean
- [ ] `tsc -b` compiles
- [ ] Redundant `//` + name-echo JSDoc gone; chart/WS/ts-expect-error notes intact
- [ ] Commit made

## Risk Assessment
- Deleting `// @ts-expect-error`/`// eslint-disable` justification comments → lint/type breakage or silent suppression. Mitigation: KEEP all suppression-reason comments; `tsc -b` + eslint gate catches removals.
- Larger than originally scoped (103 files vs assumed 1). Effort bumped to ~2h.
