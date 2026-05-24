# Brainstorm Report — Backtest Storage & Semantics Refactor

**Date:** 2026-05-23
**Session:** Brainstorm — answers to 4 user questions on hitnrun2 strategy + backtest infrastructure
**Status:** Design approved, ready for /ck:plan

---

## 1. Problem Statement

User asked 4 questions about backtest subsystem after `hitnrun2` strategy landed (commit cf3c5c9):

1. Confirm `hitnrun2` strategy is in place.
2. Backtest orders + stats present? UI exists?
3. In backtest, "position = order" because broker is paper — how to distinguish semantically?
4. Backtest data stored properly + semantically? Code-review storage.

---

## 2. Findings

### 2.1 HitNRun2 strategy — confirmed

- File: `packages/pocketquant-core/src/pocketquant/core/concepts/strategy/services/hitnrun2.py:40-149`
- Class: `HitNRun2Strategy(IStrategy)`
- Logic: 1m breakdown LONG / breakup SHORT with capped technical SL/TP
- Defaults: `entry_lookback=240` (4h), `sl_lookback=480` (8h), `tp_lookback=60` (1h), `max_loss_pct=1%`, `min_profit_pct=2%`, `direction="both"`
- Position cap = 1. `on_fill` resets `_open_direction` when broker auto-fills SL/TP

### 2.2 Backtest backend — fully present

- `BacktestAppService` orchestrates: reset broker → load bars → replay → finalize → save
- `BacktestResultCollector` uses FIFO `LotTracker`, emits closed records, equity curve, commission
- `build_metrics`: total_return, CAGR, Sharpe, Sortino, max DD, win rate, profit factor, trade counts, avg win/loss, duration, commission
- `BacktestRepository`: save/list/best/upsert_status/save_for_subscription/mark_stale_running_as_failed
- Handlers `RunAllBacktests`, `GetSubscriptionBacktest` in `pocketquant-trading/handlers/strategy/`

### 2.3 Frontend — out of scope (deferred per user)

- `pocketquant-web` has `backtest-panel-header.tsx`, `backtest-status-badge.tsx` only
- Missing: trigger form, equity chart, trades table, metrics dashboard, optimization view
- User decision: separate phase, brainstorm later

### 2.4 Order vs Position in backtest — semantic gap

Current implementation has all 4 concepts but **naming is inverted** vs industry:

| Industry (Backtrader + QuantConnect) | Pocketquant currently | Verdict |
|-------------------------------------|----------------------|---------|
| Order = intention to buy/sell with lifecycle | `OrderAggregate` in-memory only in PaperBroker | ❌ Not persisted |
| OrderEvent = status change notification | None | ❌ Missing |
| Fill = execution event (atomic) | `TradeRecord` ⚠️ wrong name | ❌ Should be Fill |
| Trade = round-trip economic (0→X→0) | `PositionRecord` ⚠️ wrong name | ❌ Should be Trade |
| Position = current holding snapshot | `PositionAggregate` runtime + open lots in array | ⚠️ Partial |

Sources: [Backtrader Orders](https://www.backtrader.com/docu/order/), [Backtrader Trade](https://www.backtrader.com/docu/trade/), [Backtrader Position](https://www.backtrader.com/docu/position/), [QuantConnect Order Events](https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-events), [QuantConnect Trading Key Concepts](https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/key-concepts).

### 2.5 Storage concerns code-review

**Current schema (single collection `backtest_runs`):**

```
backtest_runs document
  ├── _id, strategy_id, status, dates, error
  ├── config_snapshot, metrics, parameters
  ├── equity_curve[]   — embed
  ├── trades[]         — embed (actually fills)
  └── positions[]      — embed (mixed closed round-trips + open lots)
```

| # | Concern | Severity |
|---|---------|----------|
| P1 | TradeRecord vs PositionRecord naming inverted vs Backtrader/QC | 🔴 |
| P2 | 16MB doc cap risk when equity_curve grows (high-freq, multi-month) | 🟠 |
| P3 | No audit trail for orders (especially LIMIT non-fill, CANCELLED) | 🟠 |
| P4 | `positions[]` mixes closed + open — query complexity | 🟡 |

**LIMIT non-fill persist standard confirmed:** Backtrader has Accepted/Cancelled/Expired/Rejected statuses. QuantConnect has New/Submitted/Filled/Canceled. Forward-test parity requires full order lifecycle to be auditable.

---

## 3. Evaluated Approaches (Storage)

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| A. Rename only (KISS) | Min risk, 1 PR | Doesn't fix P2/P3 | ❌ |
| B. Split collections logically + NoSQL embed (phased) | Fix P1+P3+P4 now, P2 deferred clean | More collections, migration script | ✅ Chosen |
| C. Hybrid embed-then-spillout | Adaptive | Over-engineering, debug complexity | ❌ |

---

## 4. Final Recommended Design

### 4.1 Collections (all prefixed `backtest_`)

**Collection 1: `backtest_runs`** (existing, slimmed)

```
{
  _id: run_id,
  strategy_id, subscription_id?, status, started_at, completed_at, error_message?,
  config_snapshot: {symbol: "BTCUSDT:BINANCE", interval, start_date, end_date, params},
  parameters: {...},
  metrics: {sharpe_ratio, sortino_ratio, max_drawdown, ...},
  equity_curve: [{timestamp, equity, drawdown}, ...],   # embed (MVP); spillout when size becomes issue
  open_positions: [...]   # embed snapshot of lots still open at end of run
}
```

Removed: `trades[]`, `positions[]` (closed). Indexes unchanged.

**Collection 2: `backtest_orders`** (NEW — full lifecycle audit)

```
{
  _id: order_id,
  run_id, strategy_id, symbol,
  side: BUY|SELL,
  order_type: MARKET|LIMIT|STOP,
  quantity, price?, sl_price?, tp_price?,
  status: SUBMITTED|ACCEPTED|PARTIAL|FILLED|CANCELLED|REJECTED|EXPIRED,
  submitted_at, last_updated_at,
  events: [                              # embed: lifecycle audit (NoSQL leaf)
    {timestamp, from_status, to_status, reason?}
  ],
  fills: [                               # embed: atomic execution events
    {fill_id, timestamp, qty, price, commission, slippage}
  ],
  resulting_trade_id?                    # ref → backtest_trades when closes a round-trip
}
```

Indexes: `run_id`, `(strategy_id, status)`, `submitted_at`, `(run_id, status)`.

**Collection 3: `backtest_trades`** (NEW — round-trip, replaces `PositionRecord` semantics)

```
{
  _id: trade_id,
  run_id, strategy_id, symbol,
  direction: LONG|SHORT,
  entry: {order_id, price, time, qty},
  exit:  {order_id, price, time},
  sl_price?, tp_price?,                  # planned levels at entry
  pnl, commission, duration_seconds
}
```

Indexes: `run_id`, `(strategy_id, direction)`, `entry.time`, `pnl`.

**Collection 4: `backtest_optimization_runs`** (RENAME from `optimization_runs`)

Existing structure preserved; just collection name prefix to satisfy convention.

### 4.2 Code-level naming (Backtrader/QuantConnect alignment)

| Current | New |
|---------|-----|
| `TradeRecord` (value object) | `Fill` (value object) |
| `PositionRecord` (value object, round-trip) | `Trade` (value object) |
| (n/a) | `Order` (persisted value/aggregate) |
| (n/a) | `OrderEvent` (embedded record in Order) |
| `BacktestRepository.save(result)` | Split into per-collection writers via UoW or repo facade |

### 4.3 Migration

One-time idempotent script for 22 prod docs:
- Read each old `backtest_runs` doc
- Reconstruct `backtest_orders` from `trades[]` (fills) — backfill nullable order_id when not reconstructable
- Reconstruct `backtest_trades` from `positions[]` (closed round-trips)
- Update `backtest_runs`: keep config_snapshot/metrics/equity_curve/open_positions, drop trades/positions
- Rename `optimization_runs` → `backtest_optimization_runs`
- Backup target collections to `*_backup_YYMMDD` before write
- Dry-run flag, residual_count verify

### 4.4 NoSQL philosophy preserved

- `events[]` + `fills[]` embedded in order doc (leaves of order, always co-accessed)
- `equity_curve` embedded in run (defer spillout until size hit)
- `open_positions` embedded snapshot of run end state
- Split standalone entities only when cross-run query justifies it (orders, trades, optimization)

---

## 5. Implementation Considerations

- Files touched (estimate ~12-15):
  - `packages/pocketquant-backtest/src/pocketquant/backtest/domain/{entities.py, value_objects.py}` — rename + new entities
  - `packages/pocketquant-backtest/src/pocketquant/backtest/engine/result_collector.py` — emit Fill/Trade/Order
  - `packages/pocketquant-backtest/src/pocketquant/backtest/persistence/` — new repositories (`order_repository.py`, `trade_repository.py`), rename optimization repo
  - `packages/pocketquant-backtest/src/pocketquant/backtest/persistence/migrations/` — new migration script
  - `packages/pocketquant-core/src/pocketquant/core/infrastructure/brokers/paper/paper_broker.py` — emit OrderEvent on status change
  - DI providers in `pocketquant-api/di/`
  - Tests in `packages/pocketquant-backtest/tests/`

- Risk: Migration on 22 prod docs — mitigation via backup + dry-run + idempotent
- Risk: Read paths (UI) expecting old embedded arrays — needs API layer adapter or coordinated FE update (deferred to UI phase)

---

## 6. Success Criteria

- ✅ All 4 collections created with proper indexes (`backtest_runs`, `backtest_orders`, `backtest_trades`, `backtest_optimization_runs`)
- ✅ `Fill`, `Trade`, `Order`, `OrderEvent` value objects align with Backtrader/QC vocab
- ✅ PaperBroker emits OrderEvent on every status transition + Fill on execution
- ✅ ResultCollector persists Orders, Fills (embedded), Trades, Equity (embedded in run), Open positions (embedded in run)
- ✅ Migration script idempotent, dry-run verified, 22 prod docs migrated with residual_count=0
- ✅ All existing tests pass (including `test_hitnrun2_backtest.py`)
- ✅ LIMIT order test added to verify non-fill orders persist with CANCELLED/EXPIRED status

---

## 7. Out of Scope (this brainstorm)

- Frontend backtest panel (trigger form, equity chart, trades table) — separate phase
- Equity curve spillout to dedicated collection (P2 deferred; trigger when size actually exceeds threshold)
- Live trading order persistence refactor (live already has order collection; this work is backtest-only)

---

## 8. Unresolved Questions

1. Live `OrderAggregate` vs new backtest `Order` value object — keep separate types or unify into one persisted Order with `mode` discriminator? Defer to plan phase.
2. Should `backtest_runs.open_positions` reference `backtest_trades` (with exit=null) instead of embedding lot snapshot? Marginal — defer.
3. Subscription-scoped cache (`_id = sub_id` in current repo) — preserve as-is or move to `backtest_subscription_cache`? Tentatively preserve.
