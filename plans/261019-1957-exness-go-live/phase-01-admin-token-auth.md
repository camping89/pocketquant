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
- 17 mutation routes exist. 4 are guarded, all on `tracked_symbols_router` (`routes/market_data.py:369-370`, `:380-383`, `:398-401`, `:419-429`). 13 are open: `routes/market_data.py:65,79,93,112,123`, `routes/strategy.py:56,69,93,102,141`, `routes/backtest.py:52,83,94`.
- Every API router is included into one `api` router (`app/main_extensions.py:439`, includes up to `:461`). A dependency there covers every route. It must skip safe methods, because `EventSource` cannot send headers (`web/src/hooks/use-realtime-bar.ts:48`, `use-realtime-quote.ts:80`).
- Prod has `ENVIRONMENT=production` and no `ADMIN_TOKEN`. Tests run with `development` (`tests/conftest.py:38`, `tests/app_test/conftest.py:28`).
- SPA mutations use `apiPost`/`apiPatch` (`web/src/api/api-client.ts:35-53`) plus two raw `fetch` DELETEs (`web/src/api/strategy-api.ts:35-46`). nginx forwards request headers (`web/nginx.conf`, `location /api/`).

## Gates in this phase
None. The `develop` push (Task 1.9) is authorized by the plan (tests only, no deploy).

## Entry gate
Run first. On a miss: edit nothing, spawn no `kongming`, leave the phase pending, and end with:
```
Status: BLOCKED
NOT_YET: <reason>
Resume: /eve:cook-plan D:/w/_me/algotrading/pq-develop/plans/261019-1957-exness-go-live --from 01 after <UTC time>
```
- `docker ps` exits 0. If not, start `"/c/Program Files/Docker/Docker/Docker Desktop.exe"` in the background, wait 10 s, retry once. Still failing → `NOT_YET: Docker Desktop is not running`.
- `git status --porcelain -- src web deploy tests scripts docs` prints nothing (else `NOT_YET: uncommitted code changes`).

## Tasks

### Task 1.1 — Fail-closed guard that skips safe methods
- Goal: mutations need the token; GET/HEAD/OPTIONS never do; production without a token returns 503.
- Target files and symbols: `src/pocketquant/app/middleware/admin_auth_middleware.py` → `verify_admin_token`.
- Steps:
  1. Signature: `verify_admin_token(request: Request, x_admin_token: str | None = Header(default=None))`.
  2. Return at once when `request.method` is `GET`, `HEAD` or `OPTIONS`.
  3. Token unset and `settings.environment == "production"` → `raise HTTPException(503, "ADMIN_TOKEN not configured")`.
  4. Token unset in any other environment → keep the current warning and allow.
  5. Keep the `hmac.compare_digest` check. Update the module docstring to say the guard sits on the `api` router.
- Success criteria: the function has the three branches above.
- Verify: no verification needed (Task 1.6 tests it).

### Task 1.2 — One router-level dependency
- Goal: every route under `/api/v1` carries the guard.
- Target files and symbols: `src/pocketquant/app/main_extensions.py:439` (`api = APIRouter(...)`).
- Steps:
  1. Change to `APIRouter(prefix=settings.api_prefix, route_class=DishkaRoute, dependencies=[Depends(verify_admin_token)])` and import both names.
  2. Leave `/health` on `app` (not covered).
- Success criteria: the `api` router has the dependency.
- Verify: no verification needed (Task 1.6 structural test).

### Task 1.3 — Remove the per-route uses
- Goal: one guard, no duplicates.
- Target files and symbols: `src/pocketquant/app/routes/market_data.py` (4 uses at `:369-429`).
- Steps:
  1. Delete the 4 per-route `Depends(verify_admin_token)` uses and the now-unused `Depends`/`verify_admin_token` imports.
  2. Keep "Requires X-Admin-Token" in docstrings; the header is still required.
- Success criteria: no reference left in that file.
- Verify: `grep -c "verify_admin_token" src/pocketquant/app/routes/market_data.py` prints `0`.

### Task 1.4 — SPA client sends the token and re-prompts on 401
- Goal: SPA mutations carry `X-Admin-Token`; a 401 prompts once and retries once.
- Target files and symbols: `web/src/api/api-client.ts` → new private `send(path, init)`, `apiPost`, `apiPatch`, new `apiDelete(path): Promise<void>`.
- Steps:
  1. `send` adds `X-Admin-Token` from `localStorage['pq.adminToken']` when set.
  2. On 401: `window.prompt('Admin token')`, store the answer, retry once. A second non-OK throws `toApiError`.
  3. `apiPost`, `apiPatch` and `apiDelete` use `send`. Never inject the token at build time (a `VITE_*` value ships in the bundle).
- Success criteria: three exported functions route through `send`.
- Verify: no verification needed (Task 1.7).

### Task 1.5 — Raw DELETEs use `apiDelete`
- Goal: deletes carry the token.
- Target files and symbols: `web/src/api/strategy-api.ts` → `removeSubscription`, `deleteStrategy`.
- Steps: replace the raw `fetch` calls with `apiDelete`.
- Success criteria: no raw `fetch(` DELETE remains in that file.
- Verify: `grep -c "method: 'DELETE'\|method: \"DELETE\"" web/src/api/strategy-api.ts` prints `0`.

### Task 1.6 — Backend tests
- Goal: the guard is proven per route and per environment.
- Target files and symbols: create `tests/app_test/integration/test_admin_token_guard.py` (use `app_factory`; monkeypatch `get_settings` in the middleware module).
- Steps:
  1. Structural: collect every `APIRoute` under `/api/v1` whose methods include POST, PUT, PATCH or DELETE; assert each has `verify_admin_token` among its dependencies; `assert len(routes) == 17`.
  2. Token set: POST without the header → 401; wrong header → 401; right header → not 401; GET without header → 200.
  3. Production, no token: POST → 503; GET → 200.
  4. Development, no token: POST passes the guard.
- Success criteria: four test groups exist with behaviour names.
- Verify: `docker ps` exits 0, then `uv run python -m pytest tests/app_test/integration -q` exits 0.

### Task 1.7 — Web test
- Goal: the client header and retry are pinned.
- Target files and symbols: create `web/src/api/api-client.test.ts` (vitest runs in `node`; stub `fetch`, `localStorage`, `window` with `vi.stubGlobal`).
- Steps: cases: header sent when stored; a 401 prompts once and retries once with the new token; a second 401 throws `ApiError` with status 401.
- Success criteria: three cases.
- Verify: `npm --prefix web test` exits 0 and `npm --prefix web run build` exits 0.

### Task 1.8 — Docs
- Goal: the env table and route rule describe the guard.
- Target files and symbols: `docs/deployment.md` env table; `docs/code-standards.md` "Routes & Services".
- Steps:
  1. Add an `ADMIN_TOKEN` row: "Required in production; mutations return 503 while unset. Sent as `X-Admin-Token`."
  2. Add one bullet: "Mutations are guarded once, on the `api` router; do not add per-route auth."
- Success criteria: both lines present.
- Verify: `grep -c "ADMIN_TOKEN" docs/deployment.md` prints a number ≥ 1 and `grep -c "guarded once, on the" docs/code-standards.md` prints `1`.

### Task 1.9 — Quality gates and push
- Goal: the phase is on `origin/develop` with green gates.
- Target files and symbols: whole repo.
- Steps:
  1. `uv run ruff check src tests/app_test/integration/test_admin_token_guard.py`.
  2. `uv run pyright src tests/app_test/integration/test_admin_token_guard.py`.
  3. `uv run lint-imports`.
  4. `uv run python scripts/code_metrics.py --ratchet`.
  5. Commit (conventional message, no plan or phase ids), then push with the `camping89` token (the active gh account cannot push; never print the token): `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin`.
- Success criteria: all four gates pass and the push succeeds.
- Verify: ruff prints `All checks passed!`; pyright prints `0 errors`; lint-imports prints `Contracts: 8 kept, 0 broken.`; the ratchet exits 0; `test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `pushed`.

## Risk
- Prod mutations return 503 if deploy A runs before `ADMIN_TOKEN` is set (M/L). Phase 08 sets it first; the failure is closed and data jobs run on.
- A router dependency may not apply under `DishkaRoute` (L/H). The structural test proves it per route.
- The token sits in `localStorage` (L/M). The bundle ships npm code (echarts, lightweight-charts, @tanstack/*) and nginx sends no CSP; a CSP and a masked input were rejected for scope (`plan.md` "Red Team Review"). Phase 09 rotates the token in deploy B.

## Rollback
Revert the commit. No data or config shape changes.

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same
failure evidence to the user. Never continue by self-reasoning.
