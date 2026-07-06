# Swing pivot & key-level for take-profit

`EngulfingStrategyService` (and `HitNRun2StrategyService`) set take-profit not by pure risk-reward alone, but also by referencing a **key-level** taken from the nearest swing high/low. This doc explains what a swing pivot is, how the engine approximates it, and why it is used as the TP.

## What a swing high / swing low is

- **Swing high**: a local peak — a bar whose high is higher than the surrounding bars, where price turns down.
- **Swing low**: a local trough — a bar whose low is lower than the surrounding bars, where price turns up.

A swing pivot is where the market "has reacted before". Pending orders and liquidity tend to cluster around these levels, so price tends to react again when it returns.

## How the engine approximates it (a proxy, NOT true pivot detection)

The engine does **not** detect swing pivots in the geometric sense (comparing a peak/trough against neighboring bars on both sides). Instead it uses a simple proxy computed by `BarBuilderDomainService` — the **max/min over the most recent N-bar window**:

```
LONG  key_level = max(highs[-N:])   # highest high in the previous N bars
SHORT key_level = min(lows[-N:])    # lowest low in the previous N bars
```

where `N = key_level_lookback_bars` (default 20). This window is snapshotted **before** the current bar is added, so the key-level is always the N bars **strictly before** the pattern — it does not include the entry bar itself.

> **Caveat — this is a proxy, not swing-pivot detection.** The `max/min` of a raw window does not distinguish a real peak (with a price reaction on both sides) from a momentary spike. Geometric pivot detection was considered and **left out of scope** (see brainstorm-report). Don't read the key-level as a "confirmed swing pivot".

## TP = max(RR 1:1, key-level)

`EngulfingStrategyService` takes the TP to be the **farther** of risk-reward 1:1 and the key-level:

```
LONG:  risk = entry - SL;  tp_rr = entry + risk;  TP = max(tp_rr, key_level)
SHORT: risk = SL - entry;  tp_rr = entry - risk;  TP = min(tp_rr, key_level)
```

Rationale: placing the TP at a price level that often reacts (the key-level) is more sensible than an arbitrary round number, but it never accepts an RR lower than 1:1.

### Example 1 — key-level farther than RR → TP jumps up to the key

```
        key_level (max 20 highs) = 110
          ┌──────────────────────────── TP = 110  (farther than tp_rr)
          │
   entry 101 ───────────────●
          │     risk = 4.2
   tp_rr 105.2 ─ ─ ─ ─ ─ ─ ─ (RR 1:1, but lower than the key)
          │
   SL   96.8 ──────────────
```
key-level (110) > tp_rr (105.2) → `TP = max(105.2, 110) = 110`.

### Example 2 — key-level near → falls back to RR 1:1

```
   tp_rr 105.2 ─────────────── TP = 105.2  (RR 1:1, because the key is nearer)
          │
        key_level = 102  ─ ─ ─ (near peak, below tp_rr)
   entry 101 ───────────────●
          │     risk = 4.2
   SL   96.8 ──────────────
```
key-level (102) < tp_rr (105.2) → `TP = max(105.2, 102) = 105.2`. TP is always ≥ RR 1:1.

## Chart "show all patterns" ≠ the strategy's signal set

The **Engulfing** toggle on the chart draws **every** full-candle engulfing pattern (body engulfs body **and** range engulfs range — the current candle's high/low must fully cover the previous candle's high/low). `EngulfingStrategyService` only enters a **subset**:

- **Warmup**: a pattern appears within the first `key_level_lookback_bars` bars (the key-level window is not yet full) → there is a marker on the chart but **no** trade.
- **Position cap**: at most one position at a time — a pattern appears while a position is open → there is a marker but **no** entry.

This is intentional, not a bug. A marker on the chart does NOT mean "the strategy did/will enter here".

## The strong-threshold on the chart is a fixed visual aid

The chart colors strong/weak at a **fixed FE threshold of 0.30** (`STRONG_THRESHOLD` in `web/src/lib/indicators/engulfing.ts`). The strategy reads `max_rejection_wick_pct` from config (tunable via backtest). If a backtest tunes the threshold to something other than 0.30, the chart colors do **not** reflect that config — the coloring is only a visual aid, not a prediction of "entry or not" for a specific backtest.
