---
title: "Recompute backtests at 0.5 bps + default slippage 0.5"
description: ""
status: completed
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
| 1 | [Config Defaults](./phase-01-config-defaults.md) | Done (committed) |
| 2 | [Recompute Script](./phase-02-recompute-script.md) | Done (reviewed) |
| 3 | [Execute Recompute](./phase-03-execute-recompute.md) | Done (verified) |

## Dependencies

- Phase 3 depends on Phase 2 (needs the script) and Phase 1 (default in place so re-runs pick 0.5 consistently).
- Phase 1 and Phase 2 are independent — can proceed in parallel.
- No cross-plan dependencies (scanned `plans/`: `260630-mae-mfe`, `260706-engulfing-1m` — no slippage-config overlap).

## Acceptance Criteria

- [x] All backtest cost defaults committed on `develop`: slippage 0.5 bps + commission 3.0 bps (backtest config, command service, live paper, engine dispatch fallback).
- [x] `scripts/recompute_backtest_costs.py` exists: `--slippage-bps` + `--commission-bps`, `--dry-run`, per-run isolation, env-only Mongo URL, self-verifying (degenerate-replay guard, TP-slippage + gross-PnL identity, cost-snapshot + trade-count consistency). Dry-run lists the 5 targets.
- [x] All 6 finished runs show `config_snapshot.slippage_bps = 0.5` AND `commission_bps = 3.0`, recomputed metrics, order/trade counts consistent (`metrics.total_trades == trade docs == distinct entry_times`, orders ≈ 2× trades), names preserved. Verified at DB level on the VPS. `--all-finished --dry-run` now returns "No targets". Frontend/API render not re-checked this session.
- [x] ruff + pyright clean on the recompute script.
- [x] Recompute resilient to an engine trade double-persist race (see Incident): verify-count + retry per run, batch fans out to one child process per run. Underlying engine race left for a separate fix.

## Incident: trade double-persist race

`--all-finished` (5 runs, one process) persisted every trade/order **twice** (2× docs, correct metrics — the run doc's equity/metrics come from the in-memory replay, so only the `backtest_trades`/`backtest_orders` collections were polluted). Root cause: the engine intermittently double-subscribes trade closures (`on_trade` fires twice per closure → two `Trade`s with fresh ids). Reproduced once even in single-run mode, so it is a race, not batch-only. Recovery: recompute each run per-run until the trade-doc count matched; `019f1780-6b52` needed the retry. Tooling hardened (retry-until-clean + subprocess-per-run fan-out + child `LOG_LEVEL=WARNING`). **Follow-up:** fix the engine subscription race so a single replay is always 1× (idempotent `subscribe_trades`, or deterministic wiring) — do not leave the script retry as the only guard long-term.
