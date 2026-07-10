---
phase: 1
title: "Config Defaults"
status: code-done-commit-pending
effort: ""
---

# Phase 1: Config Defaults

## Overview

Land 0.5-bps as the slippage default everywhere it's a real config surface, then commit. Two of three edits already staged; this phase finishes the set (live paper) and commits.

## Current State

- `src/pocketquant/core/domain/backtest/config.py:32` — `slippage_bps: float = 0.5` ✅ staged
- `src/pocketquant/engine/backtest/backtest_command_service.py:34` — `Field(default=0.5)` ✅ staged
- `src/pocketquant/core/config.py:72` — `paper_slippage_bps: float = 1.0` ⬜ still 1.0 (this phase)

## Reviewed, NOT changed (document only)

- `src/pocketquant/core/infra/brokers/paper/paper_broker_adapter.py:111` — `slippage_percent: float = 0.001` is a constructor fallback. Backtest (`broker_factory` / `sandbox.create_broker`) and live both pass slippage **explicitly**, so this default is never hit in the real paths. Leave it — changing it invites a false sense that it's the config surface. Tests pass explicit values.
- `docs/system-architecture.md` describes slippage as "configurable" only — no hardcoded default stated, so **no docs edit** (AS-IS docs policy, no changelog banners).

## Related Code Files

- Modify: `src/pocketquant/core/config.py` (line 72: `1.0` → `0.5`)
- Verify (already staged): `config.py`, `backtest_command_service.py`

## Implementation Steps

1. Edit `core/config.py:72`: `paper_slippage_bps: float = 0.5  # 0.5 bp = 0.005%`.
2. Confirm no other slippage default exists: `grep -rn "slippage" src/pocketquant --include="*.py" | grep -iE "= *[0-9]"` — expect only the reviewed adapter fallback.
3. Run tests: `uv run pytest tests/backtest_test/ tests/core_test/infra/brokers/ tests/engine_test/ -q`.
4. Commit all three config files together, conventional message (no phase/plan IDs in message per repo rule), e.g. `chore(backtest): default slippage to 0.5 bps for backtests and live paper`.

## Success Criteria

- [ ] `paper_slippage_bps = 0.5` in `core/config.py`.
- [ ] `grep` shows no un-aligned slippage default beyond the documented adapter fallback.
- [ ] Test suite green (no test asserted the old `1.0` default — verified last turn).
- [ ] Single focused commit with the three config files.

## Risk Assessment

- **Live-paper behavior change:** forward/paper trades now model 0.5-bps slippage. Intended (user-confirmed). Low blast radius — single in-process paper broker, no schema/contract change.
- **Rollback:** revert the one commit; no data touched in this phase.
