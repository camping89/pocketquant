# Commission 3 bps recompute — the trade double-persist race

## Goal

Lower default commission to 3 bps (already committed in code) and recompute the 6 finished prod backtest runs to the current cost model (slippage 0.5 bps + commission 3.0 bps), then verify.

## What happened

The commission default was already `3.0` on `develop`, so the real work was recomputing existing runs. Since the same 6 runs were also the pending slippage-0.5 backfill target, both costs were folded into one replay: the slippage recompute CLI was generalized to `recompute_backtest_costs.py` (`--slippage-bps` + `--commission-bps`, override both in the replay payload).

A prior session was already running the old slippage-only recompute inside the VPS container; waited it out to avoid colliding on the same `delete → replay` per `run_id`. Then pushed, let CI rebuild the image (`COPY scripts/`), and ran `--all-finished` in the container against local Mongo.

The batch run **double-persisted every trade and order** — 2× docs per run, correct metrics. The run doc's equity/metrics come from the in-memory replay, so only `backtest_trades`/`backtest_orders` were polluted.

## Root cause

The engine's paper broker fans trade closures to a list of callbacks; the report collector's `on_trade` builds a `Trade` with a fresh id and appends. Under some async timing the collector is subscribed twice, so each closure produces two `Trade`s (identical content, different ids). Confirmed by grouping the polluted collection: each `entry_time` appeared exactly twice with the **same** commission value — both copies from the new comm=3 replay, not stale + fresh. So `delete_by_run` worked; the replay itself wrote 2×.

Reproduced once even in single-run mode (`019f1780-6b52`), so it is a **race**, not a batch-only leak — despite each `run_single` building a fresh sandbox/bus/broker.

## Recovery

Recomputed each run per-run until the trade-doc count matched `metrics.total_trades`. Two self-inflicted setbacks along the way: a foreground 2-min timeout killed a `docker exec` mid-save (no `-t` → dies on client disconnect) leaving a run with deleted+partial docs; and a full replay's per-bar `order_filled` INFO logs flooded stdout and broke the ssh pipe (exit 137), truncating a run to 0 trades. Both fixed by running detached and with `LOG_LEVEL=WARNING`. Final state: all 6 runs at (0.5, 3.0), `total_trades == trade docs == distinct entry_times`, orders ≈ 2× trades.

## Fix shipped (script only)

`recompute_backtest_costs.py` now:
- verifies the trade-doc count after each replay and **retries delete+replay until clean** (bounded);
- fans a batch out to **one child process per run** so a stuck run can't leak into the next;
- runs batch children at `LOG_LEVEL=WARNING` to keep replay logs from breaking the pipe.

The `019f1780-6b52` recovery through the fixed script converged to 1× — the retry is proven.

## Lesson / follow-up

Verify persisted counts against the in-memory metric before trusting a replay; never assume `delete → replay` yields 1× when the engine can double-fire a subscription. **The engine subscription race is the real bug** — make `subscribe_trades` idempotent or the sandbox wiring deterministic so one replay is always 1×; the script retry should be a backstop, not the primary guard.
