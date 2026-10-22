---
phase: 8
title: "Verify-Cascade Race Fix and Futures Paper Sizing"
status: completed
priority: P2
effort: "0.5d"
dependencies: [7]
---

## Context

User decisions, 2026-10-22 (Phase 10 measurement, Session 12):

- **Row 11, fix now.** `sync_verify_cascade` fires at HH:00:00 and `sync_1m` at HH:00:02.
  The verify compares the newest stored 5m bucket while it still lacks its last 1m bar.
  Proven on prod for all 8 runs on 2026-10-22: the ES 1m `(HH-1):49` bar was created 3-5 s
  after the verify read (for example 02:49 created 03:00:05), and BTC `(HH-1):59` likewise,
  so the feed delay is not the cause. Counsel:
  `plans/reports/kongming-261022-1745-phase8-row10-row11-failures.md`.
- **G2, route leverage into futures paper sizing, with a futures-only paper balance.** At
  10,000 USD the 2 % risk term alone sizes ES to zero whatever the leverage (200 USD over an
  engulfing stop of at least ~8 points x 50). Prod set 200,000 USD and leverage 25 (Phase 9).

"Futures" here means a contract spec with `multiplier != 1.0`, the predicate the position
calculator already uses. Only the seeded index futures have it.

## Constraints

- `develop`, English, read `CLAUDE.md`. No prod access in this phase.
- Defaults keep today's behaviour exactly: crypto and CFD paper sizing, balances and
  metrics are unchanged when the new settings are unset.

## Tasks

### Task 1 — Verify skips the still-filling bucket

- In `_verify_one_symbol` (`src/pocketquant/engine/market_data/app_services/sync_jobs.py`),
  drop the newest matched bucket before comparing. Stored 1m bars arrive in order, so only
  the bucket that holds the 1m frontier can be short; no lag value is needed.
- Unit test in `tests/app_test/unit/market_data/test_sync_verify_cascade.py`: a newest bucket
  short of one minute is not counted, and an older divergent bucket still is.

### Task 2 — Futures paper settings

- `Settings`: `paper_futures_initial_balance: float | None = None` (None falls back to
  `paper_initial_balance`) and `paper_futures_leverage: float = Field(default=1.0, ge=1)`.
- `ContractSpec.is_contract` (`multiplier != 1.0`); use it in the position calculator too.

### Task 3 — Route them

- Reconcile (`engine/live/strategy_reconcile_app_service.py`): a `paper` subscription whose
  contract spec `is_contract` gets `RiskConfig(leverage=paper_futures_leverage)`; Exness
  keeps its own; everything else keeps `RiskConfig()`. Wire in `app/di/services.py`.
- Paper broker balance: a contract-spec paper broker starts at the futures balance
  (`BrokerFactory` paper branch reads a `futures_initial_balance` key from the default
  broker config).
- `LiveMetricsQueryService`: a futures subscription's equity curve starts at the futures
  balance, so its drawdown is measured against the account it traded.
- Tests for each, including the defaults-unchanged case.

### Task 4 — Gates and commit

- `uv run pytest` (Docker running; the 4 Windows `tzset` tests are the known red),
  `uv run ruff check src tests scripts`, `uv run lint-imports`, metrics ratchet.
- Docs: the two settings in the owning config doc.
- Commit on `develop`; push `develop` (tests only, no deploy).

## Success criteria

- New tests fail before the change and pass after; the suite is otherwise unchanged.
- With the settings unset, a futures paper subscription sizes exactly as before.

## Risks and rollback

- Code only; rollback is `git revert`. The prod effect waits for Phase 9.
