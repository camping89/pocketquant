# SP3 App/BFF Docs Sweep Report

**Timestamp:** 2026-06-09 22:41  
**Scope:** Update all docs to reflect SP3 (two-process app/bff split from single image)  
**Verification:** All stale topology/port refs updated; code already correct

---

## Files Changed

### 1. README.md (5 edits)
- Added `pocketquant-bff` to monorepo layout tree
- Updated dependency graph: `{app, bff}` top tier; added note on app↔bff via MongoDB/Redis only
- Updated backend quick-start: added `just bff`, changed API URLs from :41920 → :41921 (bff)
- Fixed Vite proxy target: `http://localhost:41921` (bff), was :41920
- Updated "Serve Built UI" section: changed from "FastAPI serves dist" to Docker stack + nginx
- Updated smoke test curl examples: :41920 → :41921

### 2. CLAUDE.md (1 edit)
- Updated Layout tree: added `pocketquant-bff`, reordered app description (headless runtime)
- Updated dependency graph: `{app, bff}` as siblings, no cross-imports (verified by import-linter)

### 3. docs/README.md (2 edits)
- Added `pocketquant-bff` to repo shape tree; updated to 6-package layout
- Updated OpenAPI docs URL: :41920 → :41921 (maintenance note)
- Added note on two processes from one image (1-image-2-CMD topology)

### 4. docs/system-architecture.md (4 edits + 1 new section)
- Updated high-level diagram: split app (headless, /health only) from bff (gateway, :41921)
- Fixed Vite proxy comment: :41920 → :41921
- Fixed API proxy description: :41920 → :41921
- Updated lifespan step 13: both app (:41920) + bff (:41921) ports noted
- **NEW SECTION: "SP3: App/BFF Two-Process Architecture"**
  - Mermaid diagram: web → bff → app → mongo/redis topology
  - Detailed app responsibilities: scheduler, WS, strategy lifecycle, reconcile, backtest worker
  - Detailed bff responsibilities: stateless gateway, read/write routes, backtest enqueue, no engine
  - Dependency graph (top tier): both import core/infra/backtest/trading; no cross-imports
  - Local dev ports: app :41920 /health, bff :41921 /api/v1/docs, Vite → bff
  - Container network: app/bff internal only, nginx proxies /api/* to bff service name

### 5. docs/system-relationship-map.md (1 edit)
- Updated compose network diagram: split web + bff + app (with bff↓ depends_on app health)
- Clarified ports: web :80, bff :41921, app :41920 (/health only)

### 6. docs/deployment.md (6 edits + new subsection)
- Updated platform summary: "5 containers" → "6 containers" (app + bff split)
- Updated prod URL note: web proxies /api to bff (:41921), not app
- Updated env: removed APP_PORT (no longer needed; ports hardcoded internal)
- Added REDIS_PASSWORD to env var table
- Added new "Operator Runbook → Services & Health" subsection:
  - Health checks: app :41920, bff :41921, web :80
  - Restart strategies: bff-only (safe), app-only (risky), both
- Updated local-dev instructions: added `just bff`, Vite proxy → :41921
- Updated troubleshooting: health check → bff :41921 (was app :41920)

### 7. docs/features/strategy-lifecycle.md (1 edit)
- Updated UI entry point: "http://localhost:41920/" → "http://localhost/" (nginx serves via bff)

---

## Verification

**Grep sweep for stale refs:**
- `:41920` as proxy target → **0 instances** (all converted to :41921 bff or noted as internal /health)
- `FastAPI serves dist` → **0 instances** (all updated to nginx/bff)
- Remaining `:41920` refs → all correct (headless app /health, local dev app port)
- Remaining `:41921` refs → all correct (bff gateway)

**Code validation:**
- `vite.config.ts`: proxy target = `:41921` ✓
- `nginx.conf`: proxy_pass = `http://bff:41921` ✓
- `compose.prod.yml`: app cmd port 41920, bff cmd port 41921, web depends_on bff health ✓
- Both services have `env_file: .env`, no APP_PORT or BFF_PORT env vars needed ✓

**NO stale refs left:**
- All proxy-target refs now point to bff (:41921)
- All nginx/web refs correctly route to bff
- All health-check refs split: app /health (internal), bff /health (internal), web :80 (public via nginx)
- All API doc URLs now point to bff :41921

---

## Edits Summary by File

| File | Changes | Type |
|------|---------|------|
| README.md | 5 | Core quick-start (ports, URLs, architecture, run instructions) |
| CLAUDE.md | 1 | Layout + dependency graph |
| docs/README.md | 2 | Repo shape, OpenAPI URL, architecture notes |
| docs/system-architecture.md | 4 + 1 section | High-level diagram, app/bff split section (Mermaid + prose) |
| docs/system-relationship-map.md | 1 | Compose network topology (app/bff split) |
| docs/deployment.md | 6 + 1 section | Platform, URLs, env, local dev, ops health/restart guide |
| docs/features/strategy-lifecycle.md | 1 | UI entry point (nginx/bff, not direct app) |

---

## Unchanged (Verified Correct)

- `docs/websocket-architecture.md` — WS feed stays in app; all source-path refs (`pocketquant-app/.../ws_subscription_manager.py` etc.) still valid
- `docs/code-standards.md` — No app/bff topology refs
- `docs/design-guidelines.md` — No port/topology refs
- Any route/API ref that points to actual implementation in `pocketquant-app/src/...` or `pocketquant-bff/src/...` — unchanged

---

## No Unresolved Questions

All app/bff split topology is now reflected in docs AS-IS, matching the current code state. No changelog/migration/dated-narrative added per CLAUDE.md Documentation Policy.

**Status:** DONE  
**Summary:** Updated 7 doc files to reflect SP3 app/bff split; verified code already correct (vite, nginx, compose); no stale proxy-target or "FastAPI serves dist" claims remain.  
**Concerns:** None.
