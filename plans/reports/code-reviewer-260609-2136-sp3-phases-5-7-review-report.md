# Code Review — SP3 phases 5-7 (app/bff split, final slice)

Scope: uncommitted `git diff HEAD` + untracked `tests/app_test/integration/test_app_standalone_runtime.py`, `tests/bff_test/`.
Phases 1-4 committed in `05be010` (bff package, backtest queue, control-plane lifecycle, DI split + 2 entrypoints) — out of scope, treated as baseline.

## Verdict

**No blocking issues. No regressions found.** Every focus item verified against live code/tests, not plan text. Ship-ready.

Verification run (all green):
- `lint-imports` — **9 contracts kept, 0 broken**.
- New isolation tests — **9 passed, 8.6s**, deterministic (no sleeps).
- Full suite `pytest tests/ -q` — **470 passed, 12 skipped, 0 failed**.
- pyright new files — **0 errors**. ruff new files — **clean**.
- `compose.prod.yml config` — structurally **valid** (depends_on graph is a DAG).
- bash `-n` on both vps scripts — **OK**.
- FE dead-code grep — **0 remaining consumers** of deleted symbols.

---

## Findings by severity

### Critical
None.

### High
None.

### Medium
None blocking. See informational items below — all pre-existing patterns, not SP3 regressions.

### Low / Informational

**L1 — bff `/health` returns HTTP 200 even when a dependency is unhealthy.**
`health_check` returns the coordinator dict (`status: unhealthy` in body) but never sets a non-2xx code (`main_extensions.py:97-105`). Docker healthcheck uses `curl -f`, which only trips on non-2xx — so a bff with dead Mongo/Redis stays docker-"healthy". **Pre-existing**: app `/health` behaves identically; SP3 just mirrors it. The verify script (`11-verify.sh`) reads the `status` field, not the HTTP code, so verify still catches it. Not introduced here — noting for a future hardening pass (return 503 on `unhealthy`). Consistent app+bff behavior is arguably fine for now.

**L2 — `web` healthcheck `curl -f http://localhost:80` only checks nginx liveness, not upstream bff reachability.** Pre-existing pattern, unchanged. Acceptable: `depends_on: bff service_healthy` gates startup ordering.

---

## Focus-item verification (the 7 asked)

**1. compose.prod.yml correctness — PASS.**
- App healthcheck `curl -f http://localhost:41920/health` runs **inside** the container; container-internal localhost works fine with no published port. Removing `ports` does not break the healthcheck. Verified.
- **No deadlock.** depends_on graph is a DAG: `app → {mongodb, redis}`, `bff → {app, mongodb, redis}`, `web → bff`. app does NOT depend on bff, so the `bff→app healthy` edge is one-directional. Confirmed via `docker compose config`.
- `web→bff` service-name resolution: nginx `proxy_pass http://bff:41921` resolves on the compose default network (service name `bff`). Container name `pocketquant-bff` is irrelevant to DNS; compose uses the **service key** `bff`. Correct.
- Migration-before-healthy ordering is sound: app runs migrations + ensure_indexes in lifespan **before** `yield`, so `/health` only 200s after schema ready ⇒ `bff depends_on app service_healthy` guarantees schema is ready before bff serves. Verified reasoning holds.

**2. import-linter contracts — PASS.**
- `pocketquant.app | pocketquant.bff` layers syntax is correct import-linter "independent siblings in same layer" notation — `lint-imports` parsed & kept it.
- Two one-directional forbidden contracts (`bff↛app`, `app↛bff`) are the **right** choice over a combined contract: import-linter `forbidden` is directional by `source_modules`→`forbidden_modules`. A single contract cannot express mutual prohibition; two are required. Correct.
- bff added to **all** lower-layer forbidden lists: core, infrastructure, execution, backtest-siblings, trading-siblings. Checked each — none missed.
- 9 kept / 0 broken on live run.

**3. Dockerfile — PASS.**
- Cache-layer now copies all 7 Python pyprojects (added infra + execution + bff; infra/execution were missing before SP3 too — net correctness improvement).
- **No build-cache correctness risk**: the pre-source COPY block is purely a layer-caching optimization for `uv sync`. The subsequent `COPY packages/ packages/` brings full source, and `uv sync --frozen --no-dev --no-editable` resolves the whole workspace (`members = ["packages/*"]`) regardless of which pyprojects were pre-copied. A missing entry would only reduce cache hits, never produce a wrong image. Now complete anyway.
- `uv sync --frozen` covers all members. Wheel contains both `pocketquant.app.main:app` + `pocketquant.bff.main:app` (workspace install).

**4. Test correctness — PASS, tests prove real isolation (not tautological).**
- App standalone test (`test_app_standalone_runtime.py`) builds the container from the **exact prod provider set** (`PersistenceProvider, InfrastructureProvider, ExecutionProvider, MarketDataProvider, HandlerProvider, BacktestWorkerProvider`) — only `CoreProvider→TestCoreProvider` swapped for settings injection. Faithful prod graph. It resolves all 4 runtime types, drives a real `_reconcile()` tick (desired=running → actual=running, asserted in DB) and a real `_drain_once()` (claim→dispatch→failed). Proves the app owns the full runtime with zero bff.
- bff stateless test (`test_bff_stateless_serve.py`) calls the **real** `create_bff_container()` (prod factory, not the test factory) and asserts `NoFactoryError` on each runtime type. **`NoFactoryError` is the correct, specific assertion** — verified the bff providers (core/persistence/market_data/handlers) carry **no** provider for JobScheduler/StrategyAppService/Reconcile/Worker, so dishka raises exactly `NoFactoryError` (not a broad `DishkaError`). A broader assertion would be weaker; this one is precise and meaningful.
- POST `/start` test asserts `desired_state=running` + `actual_state=stopped` over the real ASGI app — proves bff writes only the declarative boundary and runs no reconcile. Matches `StartStrategyHandler` (pure `update_desired_state`).
- **No flakiness**: timing driven by direct `_reconcile()`/`_drain_once()` calls, zero sleeps. Re-ran — 9/9 pass in 8.6s.

**5. Dead-code deletion safety — PASS.**
- `grep -rn "runBacktest|useBacktest|BacktestResponse|StrategySelector|strategy-selector|use-backtest" packages/pocketquant-web/src/` → **NO_REFERENCES_FOUND**. Deleted files confirmed gone.
- Live backtest path intact: backend `POST /backtest/run` (enqueue) + poll route still exist, bff registers `RunBacktestHandler` (per D5). FE simply has no single-backtest UI — subscription-based backtest UI untouched. Deletion is safe.
- Kept symbols verified present: `fetchStrategies` + live types (`BacktestPosition/Metrics/EquityPoint/Status/SubscriptionBacktest`).

**6. Deploy/verify scripts — PASS.**
- `wait_health()` helper: bash-correct. Local vars (`container/port/timeout/deadline`) properly scoped with `local`; `$(( ... + timeout ))` arithmetic fine; `docker exec ... curl -fsS` probe + `exit 1` on deadline. Probes app(60s) then bff(30s). `bash -n` clean.
- `11-verify.sh` APP_PORT→WEB_PORT change: correct — app+bff are now internal-only, so the only host-published listener is `web` (nginx). Checking `:${WEB_PORT:-80}` is the right port to assert. App/bff health verified via `docker exec` internal curl instead.
- bff health-JSON parsing reuses the app's proven grep (`'"database":{[^}]*}'`, `'"redis":{[^}]*}'`). The health body nests these under `dependencies` but the grep is unanchored, so it matches; top-level `status` is grabbed via `head -1`. Same compact JSON (no spaces) as app. Works.

**7. Regression to phases 1-4 — none found.**
- Full suite 470 passed / 0 failed (≥ SP1 baseline 444). import-linter 9/9. No stray `41920` left in FE; `APP_PORT` fully removed from `deploy/` (now-unused env, correct since app is internal). nginx + vite both retargeted to bff:41921 consistently.

---

## Unresolved questions

1. **bff `/health` 200-on-unhealthy (L1)** — leave as-is to match app, or harden both to 503? Out of SP3 scope; flag for owner. Not blocking.
2. **`pocketquant-config` repo (separate)** — phase-06 note says no new `APP_PORT`/`BFF_PORT` env needed (app+bff internal-only). The unused `APP_PORT` may still sit in the VPS `.env`; harmless but worth a cleanup line in config repo. Cannot verify (external repo).
3. **Manual docker crash-isolation smoke** (kill bff → app keeps ticking) is documented as out-of-pytest in phase-07 and was not executed here (no live stack). Integration tests cover the logic; the true crash test remains a manual VPS step. Recommend running once on the next deploy and recording in a verify report.

---

**Status:** DONE
**Summary:** SP3 phases 5-7 verified correct end-to-end — 9 import contracts kept, 470 tests pass, isolation tests prove real (non-tautological) app/bff separation with precise `NoFactoryError` assertions, compose depends_on is a deadlock-free DAG, Dockerfile cache layer complete (and was never a correctness risk), dead-code deletion has zero live consumers, deploy/verify scripts bash-correct. No blocking issues, no regressions.
**Concerns:** Two pre-existing (not SP3-introduced) informational items: bff `/health` returns 200 even when a dependency is down (mirrors app), and web healthcheck checks only nginx liveness. Both acceptable; flagged for a future hardening pass. Manual docker crash-isolation smoke still pending a live deploy.
