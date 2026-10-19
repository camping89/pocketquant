---
phase: 1
title: "Admin-token auth on every mutation route (B5)"
status: pending
priority: P1
effort: 0.5d
dependencies: []
---

# Phase 01: Admin-token auth on every mutation route (B5)

## Context
- `verify_admin_token` (`src/pocketquant/app/middleware/admin_auth_middleware.py:18-36`) compares `X-Admin-Token` with `Settings.admin_token` (`core/config.py:132`) and skips the check when the token is unset (`:28-31`).
- There are 17 mutation routes. 4 are guarded, all on `tracked_symbols_router`: `routes/market_data.py:369-370`, `:380-383`, `:398-401` and `:419-429`. 13 are open: `routes/market_data.py:65,79,93,112,123`, `routes/strategy.py:56,69,93,102,141` and `routes/backtest.py:52,83,94`.
- Every API router is included into one `api` router (`app/main_extensions.py:439-461`). A dependency on that router covers every current and future route. It must skip safe methods, because `EventSource` cannot send headers (`web/src/hooks/use-realtime-bar.ts:48`, `use-realtime-quote.ts:80`) and GET routes stay public.
- Prod `.env` has `ENVIRONMENT=production` and no `ADMIN_TOKEN` (key counted, value not read). `environment` is `Literal["development","staging","production"]` (`core/config.py:49`). Tests run with `development` (`tests/conftest.py:38`, `tests/app_test/conftest.py:28`), so existing API tests keep passing.
- SPA mutations go through `apiPost`/`apiPatch` (`web/src/api/api-client.ts:35-53`), plus two raw `fetch` DELETEs (`web/src/api/strategy-api.ts:35-46`). Callers: `backtest-api.ts:226,358,364`, `monitor-api.ts:9,21`, `strategy-api.ts:32`, `hooks/use-strategy-mutations.ts:13,17`. nginx forwards request headers to the app (`web/nginx.conf`, `location /api/`).

## Files
- Modify: `src/pocketquant/app/middleware/admin_auth_middleware.py`, `src/pocketquant/app/main_extensions.py`, `src/pocketquant/app/routes/market_data.py`, `web/src/api/api-client.ts`, `web/src/api/strategy-api.ts`, `docs/deployment.md` (env table), `docs/code-standards.md` ("Routes & Services")
- Create: `tests/app_test/integration/test_admin_token_guard.py`, `web/src/api/api-client.test.ts`

## Steps
1. `verify_admin_token(request: Request, x_admin_token: str | None = Header(default=None))`:
   - return at once for `GET`, `HEAD` and `OPTIONS`;
   - when the token is unset and `settings.environment == "production"`, raise `HTTPException(503, "ADMIN_TOKEN not configured")`, so mutations fail closed while market data keeps running;
   - when the token is unset in any other environment, keep the current warning and allow the request;
   - leave the `hmac.compare_digest` check unchanged, and update the module docstring.
2. `main_extensions.py:439`: `APIRouter(prefix=..., route_class=DishkaRoute, dependencies=[Depends(verify_admin_token)])`. `/health` stays on `app` and is not covered.
3. `routes/market_data.py`: remove the 4 per-route uses (DRY) and the now-unused `Depends` and `verify_admin_token` imports. Drop "Requires X-Admin-Token" from those docstrings only if it now reads wrong; the header is still required.
4. `api-client.ts`: add one private `send(path, init)` that adds `X-Admin-Token` from `localStorage['pq.adminToken']` when set. On a 401 it asks once with `window.prompt('Admin token')`, stores the answer and retries once; any other non-OK response throws `toApiError`. `apiPost` and `apiPatch` use it, and a new `apiDelete(path): Promise<void>` uses it too. Never inject the token at build time: a `VITE_*` value would be published in the bundle.
5. `strategy-api.ts`: `removeSubscription` and `deleteStrategy` call `apiDelete`.
6. Tests in `test_admin_token_guard.py` use `app_factory` and monkeypatch `get_settings` in the middleware module:
   - structural: every `APIRoute` under `/api/v1` whose methods include POST, PUT, PATCH or DELETE has `verify_admin_token` among its dependencies (the test prints the count, expected 17);
   - with a token set: a POST without the header and one with a wrong header return 401, a POST with the right header does not, and a GET without the header returns 200;
   - in production with no token: a POST returns 503 and a GET returns 200;
   - in development with no token: a POST passes the guard.
7. `api-client.test.ts` (vitest runs in the `node` environment, so stub `fetch`, `localStorage` and `window` with `vi.stubGlobal`): the header is sent when stored; a 401 prompts once and retries once with the new token; a second 401 throws `ApiError` with status 401.
8. Docs: add an `ADMIN_TOKEN` row to the `docs/deployment.md` env table ("Required in production; mutations return 503 while unset. Sent as `X-Admin-Token`."), and add one bullet under "Routes & Services" in `docs/code-standards.md`: "Mutations are guarded once, on the `api` router; do not add per-route auth."

## Validation
- `uv run python -m pytest tests/app_test/integration/test_admin_token_guard.py tests/app_test/integration -q` exits 0 (Docker running).
- `npm --prefix web test` and `npm --prefix web run build` exit 0.
- `uv run ruff check src tests/app_test/integration/test_admin_token_guard.py`, `uv run pyright src tests/app_test/integration/test_admin_token_guard.py` and `uv run lint-imports` (`Contracts: 8 kept, 0 broken.`) pass.
- `uv run python scripts/code_metrics.py --ratchet` exits 0. No new `src` function is added, so the ceiling is not expected to move.
- `grep -c "verify_admin_token" src/pocketquant/app/routes/market_data.py` prints `0`.
- Ship: `git push origin develop` (tests only; no deploy).

## Risk
- Prod mutations return 503 if Phase 04 deploys before `ADMIN_TOKEN` is set (M/L). The failure is closed and data jobs are unaffected; Phase 04 sets the token first.
- The token travels over plain HTTP on port 80 (see D5), and a script on the SPA origin can read it from `localStorage` (L/M). The SPA loads no third-party scripts [inference, not audited].
- A router-level dependency may not apply as expected with `DishkaRoute` (L/H). The structural test in step 6 proves it per route.

## Rollback
Revert the commit. No data or config shape changes. `ADMIN_TOKEN` in prod is harmless under the old code.
