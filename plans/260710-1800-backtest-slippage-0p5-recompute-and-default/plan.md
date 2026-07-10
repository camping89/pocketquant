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

Move all backtest slippage to **0.5 bps** (half the old 1.0-bps default):

1. **Default for future runs** — backtest config defaults already changed to 0.5 (staged); align the live paper-broker default too, then commit.
2. **Reusable tooling** — promote the one-off `/tmp` recompute into a proper `scripts/` CLI that re-executes any run through the engine at a target slippage (engine = source of truth for correct metrics), idempotently.
3. **Backfill existing runs** — recompute the 5 finished non-0.5 runs (4×10-bps + 1×5-bps) to 0.5, run on the VPS container against local Mongo (the remote link took ~26 min/run).

**Why re-run, not patch metrics:** slippage is baked into every fill price (`_apply_slippage`), which propagates into PnL, equity curve, Sharpe, drawdown, profit factor. Only a full engine replay yields internally-consistent metrics. Hand-recomputing 8k+ trades × all aggregate metrics is error-prone and rejected.

**Decisions (user-confirmed):** recompute all 5 finished non-0.5 runs; align live paper (`paper_slippage_bps`) to 0.5; skip the 2 failed runs.

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

- [x] All backtest slippage defaults = 0.5 bps (backtest config, command service, live paper, + engine dispatch fallback) — code done, commit pending user.
- [x] `scripts/recompute_backtest_slippage.py` exists: `--dry-run`, per-run isolation, env-only Mongo URL, self-verifying (degenerate-replay guard, TP-slippage + gross-PnL identity, trade-count consistency). Dry-run lists the 5 targets (4×10 + 1×5 bps).
- [ ] 5 target runs show `config_snapshot.slippage_bps = 0.5`, recomputed metrics, consistent order/trade counts, display names preserved. (Phase 3 — pending execution)
- [x] Focused suites green (190 passed); ruff + pyright clean. Frontend check deferred to Phase 3.
