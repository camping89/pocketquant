---
phase: 2
title: "Recompute Script"
status: done
effort: ""
---

# Phase 2: Recompute Script

## Overview

Promote the validated `/tmp` one-off into `scripts/recompute_backtest_costs.py` — a reusable, idempotent CLI that re-executes one or more existing runs through the engine at target trading costs (`--slippage-bps` + `--commission-bps`), preserving run_id + display name, and self-verifies. This is the safe mechanism for Phase 3 and any future slippage/commission recompute.

## Requirements

- **Functional:** select runs by explicit `--run-id` (repeatable) OR `--all-finished` filter; re-run each at `--slippage-bps` (default 0.5) + `--commission-bps` (default 3.0) into the same run_id; delete stale orders/trades first; restore post-run display name; verify each run.
- **Non-functional:** idempotent (safe re-run), per-run failure isolation (one bad run doesn't abort the batch), `--dry-run` mutates nothing, `MONGODB_URL` from env only (never a flag — repo secret rule), structured log per run with before/after metrics.

## Architecture

Reuse the proven path from last turn's verification:

```
for run_id in targets:
    before  = run_repo.get(run_id)                       # capture metrics + name + counts
    payload = {**before.config_snapshot, "slippage_bps": t_slip, "commission_bps": t_comm}  # inherit ALL config, override both costs
    order_repo.delete_by_run(run_id); trade_repo.delete_by_run(run_id)   # fresh ids on re-run → must clear
    run_single(deps, payload, run_id=run_id)             # engine replays, upserts run doc by _id
    run_repo.set_name(run_id, before.name)               # config.name may differ from display name
    verify(run_id)                                        # see Verification
```

Key facts (verified in code last turn):
- `BacktestOrderRepository` / `BacktestTradeRepository` have `delete_by_run(run_id)` and `save_many` = `replace_one(upsert)` keyed by fresh `_id` → **delete-before-rerun is mandatory** or old docs linger as duplicates.
- `BacktestRepository.save` = `replace_one({_id}, upsert)` → run doc replaces cleanly.
- `run_single(deps, payload, run_id)` in `backtest_dispatch.py` builds an isolated sandbox; `_config_from_dict` reads `slippage_bps` and `commission_bps` from payload, threading `commission_bps` into `sandbox.create_broker`.
- Display name is set post-run via `set_name`; `config_snapshot.name` may be the original (`test`) — capture `before.name` and restore.

## Related Code Files

- Create: `scripts/recompute_backtest_costs.py`
- Reference (no change): `scripts/audit_bar_quality.py` (connection + `get_settings()` + `Database` pattern, docstring convention), `src/pocketquant/engine/backtest/backtest_dispatch.py`, the three `backtest_*_repository.py`.

## CLI Contract

```
uv run python scripts/recompute_backtest_costs.py --run-id <id> [--run-id <id> ...] [--slippage-bps 0.5] [--commission-bps 3.0] [--dry-run]
uv run python scripts/recompute_backtest_costs.py --all-finished [--slippage-bps 0.5] [--commission-bps 3.0] [--dry-run]
```
- `--all-finished` selects `status=finished AND (config_snapshot.slippage_bps != <t_slip> OR config_snapshot.commission_bps != <t_comm>)` (skips failed runs and already-correct runs).
- `--dry-run` prints the target run list + planned per-run actions and exits without mutating.
- Exit non-zero if `MONGODB_URL` unset or any run fails (report which).

## Verification (built into the script, runs after each re-run)

1. `config_snapshot.slippage_bps == t_slip`, `config_snapshot.commission_bps == t_comm`, and `status == finished`.
2. Order/trade counts match `metrics.total_trades` / re-fetched list lengths.
3. **TP-exit slippage math** on ≥3 TP trades: SHORT exit `== tp × (1 + target/1e4)`, LONG exit `== tp × (1 − target/1e4)`.
4. **Gross-PnL identity** on a sample: `pnl == sign·(exit − entry)·qty` (commission tracked separately; `pnl` is gross — confirmed in `position/entities.py:149`), `rel_err < 1e-4`.

## Implementation Steps

1. Author `scripts/recompute_backtest_costs.py` with module docstring (usage + "run on VPS container for local-Mongo speed" note, mirroring `audit_bar_quality.py`).
2. `argparse` for the CLI contract above; guard `MONGODB_URL` present.
3. Connect via `get_settings()` + `Database.connect`; build the 4 repos + `BacktestDispatchDeps`.
4. Implement run selection (explicit ids vs `--all-finished` query).
5. Per-run: capture-before → `--dry-run` short-circuit → delete → `run_single` → `set_name` → verify; wrap in try/except so one failure logs + continues.
6. Print a summary table (run_id, before→after total_return / sharpe / trades, verify pass/fail).
7. Smoke test locally with `--dry-run` against prod Mongo (read-only; lists the 5 targets, no mutation).

## Success Criteria

- [x] Script runs `--dry-run` and correctly lists the 5 finished runs not yet at (slip 0.5, comm 3.0) without mutating.
- [ ] `--run-id` and `--all-finished` selection both work.
- [ ] `MONGODB_URL` unset → clean error, exit non-zero.
- [ ] Built-in verification asserts slippage math + PnL identity + count consistency per run.

## Risk Assessment

- **Wrong-run mutation:** mitigated by `--dry-run` default-review step and explicit `--run-id` for the real run. `--all-finished` is filtered to non-target finished only.
- **Partial batch failure:** per-run try/except + summary makes reruns safe (idempotent: delete+rerun is repeatable).
- **Strategy no longer in registry / missing bars for a run's range:** script reports the per-run failure; does not corrupt other runs (each run's orders/trades cleared only inside its own try, after which re-run either completes or the run is left empty — note this: a run that deletes then fails to re-run ends up empty. Mitigation: delete inside the same step immediately before `run_single`, and on failure log LOUDLY so the operator re-runs that id. Acceptable for backfill tooling.)
