# SP3 Isolation Verify Report

Plan: `260609-1546-sp3-split-app-and-bff` · Phase 7 · 2026-06-09

## Goal
Prove SP3 core guarantee: **kill/restart bff ≠ interrupt live trading; app standalone runs full runtime**.

## Automated verification (DONE)

| Check | Result |
|-------|--------|
| Full suite | 470 passed, 12 skipped, 0 failed (baseline ≥444) |
| import-linter | 9 contracts kept, 0 broken |
| pyright (new files) | 0 errors |
| ruff (new files) | clean |
| FE lint + build | 0 errors, build green |
| Docker build (1 image) | OK — both `pocketquant.app.main:app` + `pocketquant.bff.main:app` construct FastAPI |
| compose.prod.yml | config VALID (deadlock-free depends_on DAG) |
| code-reviewer | DONE, no blocking, no regression |

### Isolation tests (logic-level proof)
- `tests/app_test/integration/test_app_standalone_runtime.py` — app container resolves scheduler+engine+reconcile+worker; reconcile tick converges `desired=running → actual=running`; worker drains queue. **Zero bff involvement.**
- `tests/bff_test/integration/test_bff_stateless_serve.py` — bff container raises `NoFactoryError` for JobScheduler / StrategyAppService / StrategyReconcileService / BacktestRequestWorker (parametrized); POST start writes `desired_state` only (actual stays `stopped` — bff runs no reconcile); GET serves seeded read.

**Interpretation:** bff is structurally incapable of constructing runtime — restart cannot touch live trading. app graph is self-sufficient — runs without bff.

## Manual crash-isolation smoke (PENDING — env-dependent)

Cannot run in pytest (kill real process). Requires live docker stack. Steps for next deploy:

```
docker compose -f deploy/compose.prod.yml --env-file deploy/.env up -d
# seed a subscription desired_state=running, wait reconcile tick (≤ interval)
docker kill pocketquant-bff
#   → observe: pocketquant-app logs keep ticking; trades/positions keep writing to Mongo
docker start pocketquant-bff
#   → observe: FE reads recover via bff; pocketquant-app NEVER restarted (docker ps uptime intact)
```

Expected (per architecture): app keeps trading through bff downtime; only FE reads pause. Integration tests already prove the underlying logic; this smoke confirms process-level isolation on real infra.

## Topology after SP3
- `web` (nginx :80, public) → `/api/*` → `bff:41921` (internal) → Mongo/Redis
- `app:41920` (internal, headless, `/health` only) → Mongo/Redis — owns scheduler/WS/strategy/reconcile/backtest-worker
- app + bff = one image, two commands. app + bff have NO host-published port. No new env var; `pocketquant-config` unchanged.

## Unresolved questions
1. bff `/health` returns 200 even when a dep (Mongo/Redis) is down — mirrors app's existing behavior. Harden both to 503, or keep matched? (owner call — pre-existing, not SP3 regression)
2. Unused `APP_PORT` may linger in VPS `.env` (external `pocketquant-config` repo) — harmless; optional cleanup.
3. Manual crash-isolation smoke not yet executed (no live stack this session) — run once on next deploy.
