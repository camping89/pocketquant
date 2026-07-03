# Paper Broker — Position / Trade / PnL / Commission Accounting

**Context:** Explaining how backtest position/trade/P&L/commission are computed, to resolve confusion about engulfing backtest data. Branch `develop`. Resume point after machine swap.

## TL;DR — two parallel accounting systems

Numbers in the backtest UI come from the **ResultCollector**, NOT the broker. The broker never knows about commission.

| | PaperBroker (`_balance`) | ResultCollector / LotTracker (what UI shows) |
|---|---|---|
| Model | Futures/margin, cash-based | Trade & equity bookkeeping |
| Slippage | baked into fill price | inherited (prices already slipped) |
| **Commission** | **none at all** | charged per fill |
| Drives | position sizing, MTM equity, **Sharpe/Sortino** | trades table, **total P&L, total_return, win rate** |

## Pipeline for one trade

```
EngulfingStrategy         PositionSizer            PaperBroker              ResultCollector
  emits Signal      →     computes qty       →     fills order        →     records Trade + equity
  (entry/SL/TP)          (risk vs exposure)       (+slippage, no comm)      (+commission, gross pnl)
```

### 1. Strategy — `src/pocketquant/core/domain/strategy/services/engulfing.py`
Decides prices only, no size.
- LONG: `entry = close`, `SL = pattern_low*(1 - sl_buffer_pct)` (buffer default 0.001), `TP = max(entry+risk, key_high)`
- SHORT mirror.

### 2. Position sizing — `src/pocketquant/core/domain/risk/services/position_sizer.py`
Model `PERCENT_RISK`, defaults `risk_per_trade=0.02`, `max_exposure_percent=0.10` (`risk/value_objects.py`).
```
risk_amount = balance * 0.02
size_risk   = risk_amount / |entry − SL|
max_size    = balance * 0.10 / entry     # exposure cap
qty         = min(size_risk, max_size)   # cap almost always wins
```
Called at `engine/app_services/strategy_app_service.py:360` with `balance.available_balance`.

**KEY:** engulfing SLs are tight (~1–3%), so `size_risk` is huge and the **10% exposure cap binds nearly every trade**. Position ≈ **10% of cash equity in notional**, NOT 2%-risk-based. First surprise.

### 3. PaperBroker fill — `src/pocketquant/core/infra/brokers/paper/paper_broker.py`
- Slippage `_apply_slippage` (default 0.1%): BUY fills higher, SELL fills lower.
- **No commission.**
- Futures model: opening position moves no cash; balance changes only by realized-PnL delta on close (`_reduce_and_credit`, `:515`).

### 4. ResultCollector — `src/pocketquant/backtest/engine/result_collector.py`
Source of UI numbers:
- `commission = fill_price * fill_qty * 0.001` on **every fill** (entry AND exit → 2 charges/round trip), `:101`. `commission_percent = commission_bps/10000`, default `commission_bps=10`.
- `Trade.pnl` = **gross** price PnL only: `(exit − entry) * qty`, `:364`. Slippage inside prices; **commission NOT subtracted**.
- `Trade.commission` = entry portion + exit portion, separate column, `:261` (portions from `LotTracker`, `backtest/engine/lot_tracker.py`).
- Equity curve IS net: `-= commission` per fill, `+= gross pnl` on close.

## Worked example (defaults: cap=10%, comm=0.1%, slip=0.1%, equity $10k)

Engulfing LONG, close=100, pattern_low=98 → SL=97.902, TP hit at 104:

| Step | Calc | Value |
|---|---|---|
| size_risk | 200 / (100−97.902) | 95.3 units |
| max_size (10% cap) | 10000·0.10 / 100 | **10 units** ← wins |
| Entry fill (BUY +slip) | 100 × 1.001 | 100.10 |
| Entry commission | 100.10 × 10 × 0.001 | $1.00 |
| Exit fill (SELL −slip) | 104 × 0.999 | 103.90 |
| Exit commission | 103.90 × 10 × 0.001 | $1.04 |
| **`Trade.pnl` (gross)** | (103.90 − 100.10) × 10 | **$37.96** |
| **`Trade.commission`** | 1.00 + 1.04 | **$2.04** |
| **Net (compute yourself)** | 37.96 − 2.04 | **$35.92** |
| Final equity | 10000 − 1.00 − 1.04 + 37.96 | 10035.92 |

A row showing `pnl=37.96, commission=2.04` actually made **$35.92**. UI does not do this subtraction.

## Three gotchas (explain the confusion)

1. **Trade P&L is gross.** Net = `pnl − commission`. Win rate / profit factor / avg_win computed on **gross** `t.pnl` (`metrics_builder.py:47-50`) — a trade `pnl=+0.5, commission=2.04` counts as a WIN despite net loss.
2. **Slippage is invisible.** Folded into fill prices; `Fill.slippage` hardcoded `0.0` (`result_collector.py:246`). Can't see its cost; just makes fills worse.
3. **Commission missing from Sharpe/Sortino.** They annualize off broker MTM curve (`broker.get_balance().total_equity`, no commission) while `total_return`/final equity include it. Risk-adjusted ratios slightly optimistic.

## Unresolved questions / decisions for next session

- Add a **net PnL** column (or subtract commission from pnl display) so win rate reflects reality?
- Make win-rate/profit-factor use net instead of gross `t.pnl`?
- Is Sharpe-excludes-commission intentional or a bug (fold commission into MTM curve)?
- Is the 10% exposure cap dominating sizing intended (engulfing = fixed-10%-notional, not 2%-risk)? Adjust `max_exposure_percent` if not.

## Key files (resume map)

- `src/pocketquant/core/domain/strategy/services/engulfing.py` — entry/SL/TP
- `src/pocketquant/core/domain/risk/services/position_sizer.py` — sizing (+ `risk/value_objects.py` defaults)
- `src/pocketquant/engine/app_services/strategy_app_service.py:336-373` — sizing call + order create
- `src/pocketquant/core/infra/brokers/paper/paper_broker.py` — fills, slippage, futures balance
- `src/pocketquant/backtest/engine/result_collector.py` — commission, trades, equity
- `src/pocketquant/backtest/engine/lot_tracker.py` — FIFO lots, commission portions
- `src/pocketquant/backtest/engine/metrics_builder.py` — gross-based metrics
- `src/pocketquant/backtest/models/backtest_config.py` — bps→percent conversion
- `src/pocketquant/core/domain/position/entities.py` — PositionAggregate realized PnL

Note: local MongoDB not running during analysis (`27017` refused) — example uses defaults, not a live run. To ground in a real run later, start Mongo and query `backtest_trades` / `backtest_runs`.
