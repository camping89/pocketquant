---
phase: 4
title: "Parametrize large test files (optional <12k LOC)"
status: completed
priority: P3
effort: "3-4h"
dependencies: [3]
---

# Phase 4: Parametrize large test files (optional — only if LOC > 12k after P3)

## Overview

**Conditional phase.** Run ONLY if P3's measurement leaves test LOC above the 12k acceptance bar. Pure mechanical reduction: collapse repeated test-case shapes into `@pytest.mark.parametrize` + shared fixtures. Zero behavior-coverage change — same inputs, same assertions, fewer lines. If P3 already lands < 12k, set this phase `cancelled` and stop.

## Requirements

- Functional: identical assertion coverage before/after — parametrize ids enumerate every original case. No case dropped, no input changed.
- Non-functional: each touched file shrinks 25–40%; `just test` count may *drop* (cases become params of one test fn) but logical coverage identical.

## Architecture

Target files (verified largest, repetitive-shape candidates):
- `tests/backtest_test/test_backtest_request_queue.py` (548 LOC) — queue ops with repeated enqueue/assert shapes.
- `tests/engine_test/test_strategy_service.py` (436 LOC).
- `tests/backtest_test/test_backtest_request_service.py` (391 LOC).
- `tests/core_test/infra/binance/test_binance_websocket_client.py` (390 LOC) — reconnect/backoff cases.
- `tests/scripts/test_audit_bar_quality.py` (282 LOC).

Pattern: where N tests differ only by input value + expected output, fold into one parametrized fn with N `pytest.param(..., id="...")` entries. Extract repeated setup into a fixture. Do NOT merge tests that exercise different code paths or assertions — only those that are structural clones.

This is opportunistic: pick files in descending LOC until the < 12k bar is cleared, then stop (YAGNI — don't parametrize everything).

## Related Code Files

- Modify (in priority order, stop when < 12k): `test_backtest_request_queue.py`, `test_strategy_service.py`, `test_backtest_request_service.py`, `test_binance_websocket_client.py`, `test_audit_bar_quality.py`.

## Implementation Steps

1. **Gate check:** read recorded LOC from P3. If < 12,000 → set this phase `cancelled`, done. Else continue.
2. For each target file (largest first):
   a. Read fully; identify clone-shaped test groups (same body, differing literals).
   b. Refactor to `@pytest.mark.parametrize` with explicit `id=` per case + shared fixture for setup.
   c. `pytest <file> -q` green; `pytest <file> --co -q` shows each param case collected (verify count == original logical cases).
   d. `wc -l <file>`; recompute total test LOC.
   e. If total < 12,000 → stop refactoring further files.
3. `just test` full green; `just lint`/`just types`.
4. Record final LOC + wall time.

## Success Criteria

- [ ] Either: P3 already < 12k → phase cancelled; OR test LOC reduced to < 12,000.
- [ ] Every parametrized case maps 1:1 to an original case (collect-only count matches logical case count).
- [ ] No assertion or input value changed — pure structural fold.
- [ ] `just test`/`just lint`/`just types` green.

## Risk Assessment

- **Over-parametrizing distinct paths:** merging tests that look similar but assert different things hides regressions. Mitigation: only fold structural clones; keep distinct-path tests separate even if verbose.
- **Param id drift makes failures unreadable:** Mitigation: explicit `id=` strings describing each case.
- **Scope creep:** temptation to refactor all large files. Mitigation: stop the moment LOC clears 12k (Step 2e).
