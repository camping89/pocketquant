---
title: "HitAndRun Strategy Implementation"
description: "Implement HitAndRun (hit and run) strategy — double/triple bottom/top pattern with ATR-based clustering and dynamic SL/TP from 10-bar range"
status: pending
priority: P2
effort: 2h
branch: feat/web
tags: [strategy, trading, python]
created: 2026-03-30
blockedBy: []
blocks: []
---

# HitAndRun Strategy Implementation

## Summary

Implement `HitAndRunStrategy` — a Python class following existing `IStrategy` pattern.
YAML config handles parameters only; SL/TP are dynamic (from 10-bar high/low), so Python code is mandatory.

## Context

- **Brainstorm:** brainstorm session 2026-03-30
- **Pattern:** follow `ma_crossover.py` exactly
- **Interface:** `IStrategy` in `packages/pocketquant-core/src/pocketquant/core/concepts/strategy/interfaces.py`

## Phases

| # | Phase | Status | Priority | Effort |
|---|-------|--------|----------|--------|
| 1 | [HitAndRunStrategy Python class](phase-01-hitnrun-strategy-class.md) | pending | P0 | M |
| 2 | [YAML config example](phase-02-yaml-config.md) | pending | P1 | S |

## Key Design Decisions

- **ATR-based bottom/top clustering** — scales with volatility, not fixed %
- **Dynamic SL/TP** — derived from `min(lows[-lookback:])` and `max(highs[-lookback:])` ± offset%, NOT `config.orders.stop_loss.distance_percent`
- **MA trend filter** — price < MA(ma_period) = downtrend (long), price > MA = uptrend (short)
- **Trigger:** `current bar.low` touches bottom zone for long; `current bar.high` touches top zone for short
- **direction param:** `"long"`, `"short"`, or `"both"`
