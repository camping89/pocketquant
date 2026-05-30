---
phase: 3
title: "Sweep backtest"
status: completed
priority: P2
effort: "2h"
dependencies: [2]
---

# Phase 3: Sweep backtest

## Overview

Sweep `pocketquant-backtest` — 52 src files / 3387 loc + 11 test files / 1705 loc, 73 full-line `#`. Backtest engine, optimization, PaperBroker usage.

## Requirements
- Functional: redundant comments/docstrings removed per Keep Bar; test pass/skip counts identical to baseline.
- Non-functional: preserve any numerical/edge-case docstrings on optimization math (those are contract docs → KEEP).

## Architecture
Depends only on core. Backtest domain entities, engine app service, repositories. Watch for docstrings documenting metric formulas / param ranges — KEEP.

## Related Code Files
- Modify: `packages/pocketquant-backtest/**/*.py` (src + tests), excluding venv/pycache.

## Implementation Steps
Follow Per-Phase Sweep Protocol (plan.md):
1. `just test-pkg backtest` → green baseline (infra up if needed).
2. Agent reads each src+test `.py`, applies Keep Bar, edits in place.
3. `just lint` → `just fmt`.
4. `just test-pkg backtest` → green, same counts.
5. Commit: `refactor: trim redundant comments in pocketquant-backtest`.

## Success Criteria
- [ ] `just test-pkg backtest` green, pass/skip counts match baseline
- [ ] `just lint` clean
- [ ] Optimization/metric contract docstrings preserved
- [ ] Commit made

## Risk Assessment
- Over-deleting formula docstrings. Mitigation: treat any docstring with param/return/edge detail as KEEP.
