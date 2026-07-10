---
title: "Recompute backtests at 0.5 bps + default slippage 0.5"
description: ""
status: pending
priority: P2
branch: "develop"
tags: []
blockedBy: []
blocks: []
created: "2026-07-10T11:04:52.999Z"
createdBy: "ck:plan"
source: skill
---

# Recompute backtests at 0.5 bps + default slippage 0.5

## Overview

Move all backtest trading costs to the current defaults — **slippage 0.5 bps + commission 3.0 bps** — for both future runs and existing runs:

1. **Default for future runs** — backtest config + live paper defaults are `slippage_bps=0.5`, `commission_bps=3.0` (committed on `develop`).
2. **Reusable tooling** — `scripts/recompute_backtest_costs.py` re-executes any run through the engine at target costs (`--slippage-bps` + `--commission-bps`, engine = source of truth), idempotently.
3. **Backfill existing runs** — recompute the finished runs not yet at (0.5, 3.0) to those costs, run on the VPS container against local Mongo (the remote link took ~26 min/run).

**Why re-run, not patch metrics:** slippage is baked into every fill price (`_apply_slippage`) and commission into position sizing + net equity — both propagate into PnL, equity curve, Sharpe, drawdown, profit factor. Only a full engine replay yields internally-consistent metrics. Hand-recomputing 8k+ trades × all aggregate metrics is error-prone and rejected.

**Decisions (user-confirmed):** recompute all finished non-target runs to (slip 0.5, comm 3.0); align live paper defaults; skip the 2 failed runs. Commission target 3.0 folded in with the slippage recompute — same runs, one replay.

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [Config Defaults](./phase-01-config-defaults.md) | Code done (commit pending) |
| 2 | [Recompute Script](./phase-02-recompute-script.md) | Done (reviewed) |
| 3 | [Execute Recompute](./phase-03-execute-recompute.md) | Pending (needs low-latency host) |

## Dependencies

- Phase 3 depends on Phase 2 (needs the script) and Phase 1 (default in place so re-runs pick 0.5 consistently).
- Phase 1 and Phase 2 are independent — can proceed in parallel.
- No cross-plan dependencies (scanned `plans/`: `260630-mae-mfe`, `260706-engulfing-1m` — no slippage-config overlap).

## Acceptance Criteria

- [x] All backtest cost defaults committed on `develop`: slippage 0.5 bps + commission 3.0 bps (backtest config, command service, live paper, engine dispatch fallback).
- [x] `scripts/recompute_backtest_costs.py` exists: `--slippage-bps` + `--commission-bps`, `--dry-run`, per-run isolation, env-only Mongo URL, self-verifying (degenerate-replay guard, TP-slippage + gross-PnL identity, cost-snapshot + trade-count consistency). Dry-run lists the 5 targets.
- [ ] 5 target runs show `config_snapshot.slippage_bps = 0.5` AND `commission_bps = 3.0`, recomputed metrics, consistent order/trade counts, display names preserved. (Phase 3 — pending execution)
- [x] ruff + pyright clean on the recompute script.
