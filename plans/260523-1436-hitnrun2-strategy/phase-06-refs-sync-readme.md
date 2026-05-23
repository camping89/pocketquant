---
phase: 6
title: "Refs sync + README"
status: completed
priority: P2
effort: "1-2h"
dependencies: [3]
---

# Phase 6: Refs sync + README

## Overview

Sweep remaining `ma_crossover` / `hit_and_run` / `ma-cross-btc-5m` / `hitnrun-btcusdt-5m` mentions across docs + tests + Bruno HTTP fixtures. Replace with `hitnrun2` everywhere live, drop everywhere historical/audit-only.

## Requirements

- After this phase: `grep -r "ma_crossover\|hit_and_run\|ma-cross-btc-5m\|hitnrun-btcusdt-5m"` returns **only** plan/journal/historical-report files (anything under `plans/`, `.claude/agent-memory/`). Code, tests, README, docs/*.md ⇒ zero hits.

## Architecture

Touched buckets:

| Bucket | Files | Action |
|---|---|---|
| Live API tests | `test_run_all_backtest_cascade.py`, `test_concurrent_run_all.py`, `test_add_symbol_handler_autoload.py` | Replace strategy_id strings with `hitnrun2` + adjust parameter dicts (lookbacks). Verify still pass. |
| HTTP fixtures | `tests/http/backtest/*.bru`, `tests/http/strategies/load-strategy.bru`, `tests/manual/api-test.http` | Update strategy_id payloads to `hitnrun2` + parameter shape. |
| Docs | `README.md`, `docs/codebase-summary.md`, `docs/system-architecture.md`, `docs/run-and-test-guide.md`, `docs/debug-audit-order-execution.md` | Replace strategy-id mentions; note "1m breakdown" replaces "MA crossover" / "double-bottom". |
| Stale comments | `value_objects.py`, `services/__init__.py`, `handlers/strategy/__init__.py` | Docstrings mention old strategies — update or remove. |
| Memory/journals | `.claude/agent-memory/code-reviewer/MEMORY.md`, `plans/reports/*` | **Leave alone** — historical record. Plans/reports are append-only. |

## Related Code Files

**Modify (code/tests):**
- `packages/pocketquant-api/tests/integration/test_run_all_backtest_cascade.py`
- `packages/pocketquant-api/tests/integration/test_concurrent_run_all.py`
- `packages/pocketquant-trading/tests/test_add_symbol_handler_autoload.py`
- `packages/pocketquant-core/src/pocketquant/core/concepts/strategy/value_objects.py` (docstring example only)
- `packages/pocketquant-trading/src/pocketquant/trading/handlers/strategy/__init__.py` (docstring/comment)

**Modify (docs):**
- `README.md`
- `docs/codebase-summary.md`
- `docs/system-architecture.md`
- `docs/run-and-test-guide.md`
- `docs/debug-audit-order-execution.md`

**Modify (HTTP fixtures):**
- `tests/http/backtest/run-backtest.bru`
- `tests/http/backtest/list-results.bru`
- `tests/http/backtest/run-optimization.bru`
- `tests/http/strategies/load-strategy.bru` (may delete entirely since YAML loading still exists but examples were removed in phase 1 — verify)
- `tests/manual/api-test.http`

**Leave alone:**
- `plans/reports/*` (historical)
- `.claude/agent-memory/*` (historical)
- Phase plan files themselves.

## Implementation Steps

1. `grep -rn "ma_crossover\|hit_and_run\|MACrossoverStrategy\|HitAndRunStrategy\|ma-cross-btc-5m\|hitnrun-btcusdt-5m" packages tests docs README.md` — full inventory.
2. For each live test file, read context, replace strategy_id strings, adjust `parameters` dict to hitnrun2 shape (`entry_lookback_bars`, `sl_lookback_bars`, etc.). Use defaults so tests don't depend on tuning.
3. For docstrings in `value_objects.py` etc., update YAML example block to use `hitnrun2`.
4. For docs `*.md`, search "ma_crossover" / "hit_and_run" and replace with "hitnrun2" or remove sentences that referred to old behavior (e.g. "double/triple bottom" → "breakdown buy").
5. For Bruno `.bru` files, update JSON bodies' `strategy_id` to `hitnrun2`. If a fixture loaded a deleted YAML, replace with an inline `parameters` payload (the backtest API accepts strategy_id + parameters directly per `RunBacktestCommand`).
6. `strategies/load-strategy.bru` loads YAML files we deleted. Two choices: (a) delete the fixture; (b) point at a remaining valid YAML. Since YAML loading itself is still supported but we removed all examples, delete the fixture and add a one-line note in README that YAML loader still works but no examples are shipped.
7. Final grep — confirm zero hits in code/tests/docs.
8. Run `just test` (or `just test-pkg core`/`backtest`/`api`/`trading` per package) + `just lint`.

## Success Criteria

- [ ] `grep -rn "ma_crossover\|hit_and_run" packages tests docs README.md` returns nothing.
- [ ] `grep -rn "ma-cross-btc-5m\|hitnrun-btcusdt-5m" packages tests docs README.md` returns nothing.
- [ ] All previously-passing tests still pass: `just test`.
- [ ] `just lint` + `just types` clean.
- [ ] README "Current backtest strategy IDs" section lists only `hitnrun2`.
- [ ] Bruno HTTP collection runs without 404/422 against running API (smoke-tested manually).

## Risk Assessment

- **Risk:** Integration tests `test_run_all_backtest_cascade.py` may iterate multiple strategy_ids — replacing with a single `hitnrun2` reduces the loop. Check intent: was the test verifying "all strategies", or specific behavior? **Mitigation:** read tests first; if they expected ≥2 strategies, reduce assertion or stub a second test-only registry entry.
- **Risk:** Docs sweep may break diagram references / anchors. **Mitigation:** use docs-manager agent to verify links after edits.
- **Risk:** Bruno fixtures may be relied on by CI smoke tests. **Mitigation:** verify CI configs — currently no `.bru`-based CI step.
