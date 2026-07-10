---
phase: 3
title: "Execute Recompute"
status: pending
effort: ""
---

# Phase 3: Execute Recompute

## Overview

Backfill: recompute the 5 finished non-0.5 runs to 0.5 bps using the Phase-2 script, on a host with low-latency Mongo access, then verify each run end-to-end.

## Target Runs (query at execution time, don't hardcode)

```
db.backtest_runs.find(
  { status: "finished", "config_snapshot.slippage_bps": { $ne: 0.5 } },
  { _id: 1, "config_snapshot.slippage_bps": 1, name: 1 }
)
```
Expected: 4 runs @ 10.0 bps + 1 run @ 5.0 bps (the 2 failed @ 5.0 are excluded by `status: finished`). Confirm exactly 5 before running.

## Execution Host — pick low-latency Mongo

The per-run save is ~26k individual upserts. Over the remote VPS link that was **~26 min/run** (~2 h for 5). On the VPS against local Mongo it's seconds.

- **Preferred:** run on the VPS. First verify how prod runs code (`docs/deployment-guide.md` + memory `vps-prod-access-reality`: prod is `root@…:22`, Mongo host-port 52017). If the app container has the repo (image or mount), run `docker exec pocketquant-app python scripts/recompute_backtest_slippage.py --all-finished --dry-run` then without `--dry-run`. If the script isn't in the container yet, `git pull` on the VPS / redeploy first (Phase 1+2 must be pushed).
- **Fallback:** run locally over the remote link (script already env-driven via `.env` → VPS Mongo). Correct but slow; fine for a one-time backfill. Use `--run-id` per run to checkpoint, or run detached.

## Implementation Steps

1. Ensure Phase 1 + 2 committed and pushed (script available to the chosen host).
2. `--dry-run` first: confirm the target list is exactly the 5 expected runs.
3. Execute the recompute (all 5, or one `--run-id` at a time for checkpointing).
4. Per-run verification (script does this; also spot-check via DB):
   - `config_snapshot.slippage_bps == 0.5`, `status == finished`, display name preserved.
   - `metrics.total_trades` == `backtest_trades` count for the run == `backtest_orders`-derived count.
   - TP-exit slippage math + gross-PnL identity pass.
   - Metrics moved in the expected direction (less slippage → higher return / profit_factor, same trade count).
5. Frontend check: open each run at `localhost:5173/backtest/<run_id>/trades` — data + config chip show 0.5 bps.
6. Cross-run sanity: no run left with 0 trades (would signal a delete-then-failed-rerun); re-run any such id.

## Related Code Files

- Use: `scripts/recompute_backtest_slippage.py` (Phase 2)
- Reference: `docs/deployment-guide.md` (execution host), memory `vps-prod-access-reality`.

## Success Criteria

- [ ] All 5 target runs: `slippage_bps = 0.5`, recomputed metrics, consistent order/trade counts, names preserved.
- [ ] No `finished` run left with `slippage_bps != 0.5` (except any intentionally out-of-scope) and none with 0 trades.
- [ ] Frontend renders updated data for each run.

## Risk Assessment

- **Irreversible metric overwrite:** old 10/5-bps metrics replaced. User-confirmed. Semi-reversible — re-runnable at the old slippage from the same bars if ever needed (bars are the source of truth and unchanged).
- **Heterogeneous run configs:** each run inherits its own `config_snapshot` (symbol/interval/date-range/params), only slippage overridden — so a run over a symbol/range whose bars are gone will fail its re-run. Mitigation: `--dry-run` + per-run isolation + the "0-trades" post-check; re-run failures individually.
- **Bars availability:** all 5 were `finished` originally, so their bars existed; assume still present. Verify no run drops to 0 trades post-run.
- **Rollback:** none automated; re-run the script with the prior slippage value to restore a given run's old metrics.
