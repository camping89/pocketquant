# Brainstorm: Collapse 6 subpackages → 4, single backend process

Date: 2026-06-11 | Session: brainstorm | Status: consensus reached, user approved

## Problem Statement

User asked: analyse relationship between `app, backtest, bff, core, engine, trading`; reduce folders where overlap exists or separation-of-concerns is not enough reason to split.

## Scout Findings (verified on develop)

| Package | Files | LOC | Verdict |
|---|---|---|---|
| core | 110 | 7,688 | Keep — domain + infra + common, healthy foundation |
| engine | 29 | 3,758 | Keep — strategy/order/position + market_data services |
| backtest | 23 | 2,389 | Keep — cohesive, real boundary |
| trading | 17 | 1,986 | **Dissolve** — thin CRUD services (~470 LOC) + OKX adapter (~1,300) + dead webhooks (~110) |
| app | 17 | 1,448 | **Merge with bff** |
| bff | 24 | 1,614 | **Merge with app** |

Key evidence:

1. `trading`'s 3 services (`strategy_command_service`, `strategy_query_service`, `orders_positions_service`) are thin CRUD over `core` repos + `engine` app_services. No domain logic of their own.
2. OKX broker imports only `core.domain` — identical dependency shape to `paper_broker` already at `core/infra/brokers/paper/`. Two `IBroker` impls in two different packages = the real inconsistency.
3. `trading/webhooks/` (~110 LOC) is dead code: zero importers, not in any DI container. Verified by grep across src + tests.
4. `bff/di/` is a near-verbatim copy of `app/di/` (persistence.py 79/80 lines identical; docstrings self-describe as "Isolated copy"). ~160 LOC duplication, every new repo = 2 edits.
5. Pre-existing bug: `/trading/orders|positions` routes mounted in bff, but `OrderPositionQueryService` only registered in app DI; app mounts no feature routes → endpoints always 500 in both processes (admitted in `bff/routes/trading_orders_positions.py:5-7`).
6. Import edges confirm layering: nothing imports `app` or `bff`; `bff` never imports `app`; `backtest ⊥ trading`.

## Decisions (user-confirmed 2026-06-11)

1. **Dissolve `trading`**: services → `engine`, OKX broker → `core/infra/brokers/okx/`, webhooks **deleted** (YAGNI; git history retains).
2. **Merge `app` + `bff` → single package `app`, single process, single entrypoint.** User explicitly reversed SP3 two-process split: "we only need one entry point from backend side. So job and api and app runtime into one." Trade-off surfaced and accepted: losing bff-restart-cheap / crash-isolation property from SP3; one process means scheduler/WS/backtest share the event loop with API traffic.
3. **Name = `app`** (not `runtime`).
4. **500 fix**: merging fixes it structurally — single DI container registers `OrderPositionQueryService` + in-RAM `OrderAppService`/`PositionAppService`, same process mounts the routes. No extra work needed beyond the merge. OpenAPI schema unchanged (routes already in snapshot); behavior 500→200.

## Target Structure (6 → 4)

```text
src/pocketquant/
├── core/       # + infra/brokers/okx/ (moved from trading)
├── engine/     # + strategy_command_service, strategy_query_service,
│               #   orders_positions_service (moved from trading)
├── backtest/   # unchanged
└── app/        # merged app+bff — ONE FastAPI process
    ├── di/             # single container: app providers + ex-bff services provider; delete bff dup copies
    ├── routes/         # from bff/routes + bff/system_jobs
    ├── middleware/     # admin_auth (from bff)
    ├── common/         # symbol_validation (from bff/common)
    ├── market_data/    # ws_subscription_manager, quote_app_service, tracked_symbol_seeder (unchanged)
    ├── main.py         # full lifespan: migrations, indexes, scheduler, WS feed, reconcile, backtest worker + ALL routes + SPA serving
    └── main_extensions.py
```

Import-linter contracts collapse to: `core ◁ engine ◁ backtest ◁ app` (layers) + existing `core.domain ⊥ core.infra`. Sibling contracts for trading/bff deleted.

## Deploy / Runtime Changes

- compose (local + prod): delete `bff` service; single `app` service listens **41921** (the port web nginx + Vite proxy already target) → web nginx upstream rename `bff` → `app` in nginx conf.
- justfile: drop `just bff`; `just be` runs the single entrypoint on 41921. Drop 41920.
- Healthcheck: one, on app:41921 `/health`. `web` depends_on app healthy.
- FastAPI title/desc merge; docs at `/api/v1/docs` unchanged.

## Evaluated Alternatives

- **A (6→5, dissolve trading only)**: lowest risk, keeps SP3 split, accepts DI dup. Rejected by user — wants one entrypoint.
- **B (6→4, two entrypoints in one `runtime/` pkg)**: keeps 2 processes, shares DI. Superseded — user chose single process outright.
- **Chosen (6→4, one process)**: simplest end-state; fixes 500 for free; deletes ~270 LOC (webhooks + DI dup); fewer containers, simpler compose/justfile.

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Heavy backtest/optimization load degrades API latency (shared event loop) | Accepted by user; grid optimizer already semaphore-bounded (`max_workers`); revisit only if observed |
| App crash now takes API down (SP3 property lost) | Accepted; `restart: unless-stopped` in compose; solo project, low blast radius |
| Move churn across ~40 files of imports | TDD: SP3 baseline regression net (OpenAPI snapshot, contract tests, smoke) re-used; every phase ends green |
| OpenAPI diff | Expect zero schema diff; `/trading/*` paths already in snapshot. The 500→200 behavioral change is intended, document in plan |
| nginx upstream rename missed → web 502 | Phase must include `web/` nginx conf + compose in same commit, smoke test via `just up` |

## Success Criteria

- `find src/pocketquant -maxdepth 1 -type d` → core, engine, backtest, app only
- `just test`, `just lint-imports`, `just types`, `just lint` all green
- Single `uvicorn pocketquant.app.main:app --port 41921` serves: all API routes + /health + SPA; scheduler, WS feed, reconcile, backtest worker run in-process
- `GET /api/v1/trading/orders` returns 200 (bug fixed)
- `trading/`, `bff/` dirs gone; webhooks gone; bff DI dup gone
- compose has one backend service; `just up` full stack works

## Next Steps

→ `/ck:plan --tdd` with this report as context.

## Unresolved Questions

- None blocking. Minor: keep `BFF_PORT` env var name or rename to `APP_PORT` (suggest rename, trivial).
