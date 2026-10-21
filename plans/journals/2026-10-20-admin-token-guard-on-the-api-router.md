---
title: Admin token guard on the api router
date: 2026-10-20
summary: Mutations under /api/v1 now need X-Admin-Token; shipped to develop as ed85d1d.
---

# Admin token guard on the api router

## What happened
- The `api` router now carries one `Depends(verify_admin_token)`. It covers all 17 mutation routes and replaces the 4 per-route uses.
- The guard skips GET, HEAD and OPTIONS, because EventSource streams cannot send headers.
- In production with no `ADMIN_TOKEN`, the guard returns 503. In other environments it logs a warning and allows the request.
- The SPA sends mutations through a private `send()`. It reads the token from `localStorage['pq.adminToken']`, prompts once on a 401 and retries once. Raw DELETE calls now use `apiDelete`.
- A structural test asserts that every mutation route under `/api/v1` has the guard.

## Friction
- nvm-windows refused to run npm (NVM4306, "delegated script identity changed"). The user fixed it; the agent did not bypass it.
- The web dependencies were not installed in this checkout, so `npm --prefix web ci` was needed.
- `npm run build` runs `tsc -b` before `vite build`. On a fresh checkout `src/routeTree.gen.ts` (gitignored) does not exist yet, so tsc fails until Vite has run once. `web/Dockerfile` runs only `vite build`, so prod never hits this.

## Risks noted
- Prod has `ENVIRONMENT=production` and no `ADMIN_TOKEN`. Master must not get this commit until the token is set, or every prod mutation returns 503.
- `IdempotencyMiddleware` replays a cached POST/PATCH response by `Idempotency-Key` before routing. It runs nothing again and the SPA never sends the header, so it can disclose an earlier response but cannot bypass the guard. Revisit with the token rotation work.

## Next steps
- Phase 02: subscription broker selection.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
