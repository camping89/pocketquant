---
title: "hitnrun2 strategy + PaperBroker SL/TP auto-fill"
description: "Replace ma_crossover + hit_and_run with hitnrun2 (1m breakdown buy/sell). Add PaperBroker bar-event SL/TP auto-fill so strategies that set sl_price/tp_price actually get exits."
status: completed
priority: P2
effort: "1-2d"
branch: "worktree-hitnrun2-strategy"
tags: [strategy, backtest, broker, cleanup]
blockedBy: []
blocks: []
created: "2026-05-23T08:02:55.744Z"
createdBy: "ck:plan"
source: skill
brainstorm: ../reports/brainstorm-260523-1436-hitnrun2-strategy.md
---

# hitnrun2 strategy + PaperBroker SL/TP auto-fill

**Brainstorm:** [`brainstorm-260523-1436-hitnrun2-strategy.md`](../reports/brainstorm-260523-1436-hitnrun2-strategy.md)

## Overview

Two coupled deliverables:

1. **Strategy refresh.** Delete `ma_crossover` + `hit_and_run` (code + YAML examples + test/README refs). Add `hitnrun2` — 1m breakdown buy/sell with configurable lookback (4h entry, 8h SL technical, 1h TP technical) + percent-account caps (1% loss, 2% profit min).
2. **Broker SL/TP fix.** `PaperBroker` currently stores `sl_price`/`tp_price` as metadata only — no engine ever fills them. Subscribe `BarCompletedEvent` and emit synthetic fills when bar range crosses SL/TP. Required by hitnrun2 for closed loop; benefits any future strategy.

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [Cleanup old strategies](./phase-01-cleanup-old-strategies.md) | Completed |
| 2 | [PaperBroker SL/TP auto-fill](./phase-02-paperbroker-sl-tp-auto-fill.md) | Completed |
| 3 | [Implement HitNRun2 class](./phase-03-implement-hitnrun2-class.md) | Completed |
| 4 | [Unit tests](./phase-04-unit-tests.md) | Completed |
| 5 | [Integration backtest tests](./phase-05-integration-backtest-tests.md) | Completed |
| 6 | [Refs sync + README](./phase-06-refs-sync-readme.md) | Completed |

## Phase Dependencies

```
1 (cleanup)         ──┐
2 (broker SL/TP)    ──┼──> 3 (hitnrun2) ──> 4 (unit) ──> 5 (integration)
                      │
                      └──> 6 (refs)  (parallel after 1, finalized after 5)
```

- Phase 1 + Phase 2 are independent — can run in parallel.
- Phase 3 needs broker SL/TP fill to exist (relies on `sl_price`/`tp_price` actually firing).
- Phase 4 tests both the strategy (phase 3) and broker (phase 2).
- Phase 5 needs phase 3 strategy registered.
- Phase 6 finalises after everything else is green.

## Success Criteria

- `STRATEGY_REGISTRY == {"hitnrun2": HitNRun2Strategy}` — only one entry.
- No file in `packages/`, `strategies/examples/`, `tests/http/` or `README.md` mentions `ma_crossover`, `hit_and_run`, `MACrossoverStrategy`, `HitAndRunStrategy`, `ma-cross-btc-5m`, `hitnrun-btcusdt-5m`.
- `uv run pytest packages/pocketquant-core/tests/unit/concepts/strategy/test_hitnrun2.py packages/pocketquant-core/tests/unit/infrastructure/brokers/test_paper_broker_sl_tp_fill.py packages/pocketquant-backtest/tests/engine/test_hitnrun2_backtest.py` — all green.
- `just lint` + `just types` — clean.
- Manual: POST `/api/v1/backtest/run` `{strategy_id: "hitnrun2", symbol: "BTCUSDT:BINANCE", interval: "1m", start_date, end_date}` returns `status: completed` and `metrics.total_trades >= 1` against synced 1m data.

## Dependencies

No cross-plan blockers. `plans/260511-1408-backtest-analysis-panel` is FE panel work — file scopes do not overlap.

## Risks

1. **Broker SL/TP fill order semantics.** When a single bar's range covers BOTH SL and TP (gap bar / wide-range bar), which fires first? Conservative default: SL first (worst case). Documented in phase 2.
2. **Test data realism.** Unit tests with synthetic monotonic OHLCV may not exercise the SL-cap branch. Phase 4 explicitly fabricates `lows[-480:]` so the 8h-low lies beyond 1% from entry — forcing the cap path.
3. **Frontend impact.** Web app reads strategy IDs dynamically via API (`useStrategiesList`) — no hardcoded refs. Verified in brainstorm. README + Bruno HTTP collection still hardcoded — phase 6.
