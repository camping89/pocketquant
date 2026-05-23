---
phase: 1
title: "Cleanup old strategies"
status: completed
priority: P2
effort: "1h"
dependencies: []
---

# Phase 1: Cleanup old strategies

## Overview

Delete `ma_crossover` and `hit_and_run` artefacts. Leave registry **empty** at the end of this phase — phase 3 repopulates it with `hitnrun2`. Tests/README refs are touched in phase 6; this phase only touches files that compile-fail without cleanup.

## Requirements

- Functional: `STRATEGY_REGISTRY` must remain importable (empty dict allowed) so other packages compile.
- Non-functional: zero references to the deleted class names in `packages/` after this phase.

## Architecture

Touch only the strategy-services module + the YAML examples directory. The two referenced strategy IDs (`ma-cross-btc-5m`, `hitnrun-btcusdt-5m`) live only in YAML + Bruno HTTP fixtures; HTTP fixtures handled in phase 6.

## Related Code Files

**Delete:**
- `packages/pocketquant-core/src/pocketquant/core/concepts/strategy/services/ma_crossover.py`
- `packages/pocketquant-core/src/pocketquant/core/concepts/strategy/services/hit_and_run.py`
- `strategies/examples/ma-crossover-btc-usdt.yaml`
- `strategies/examples/hitnrun-btcusdt-5m.yaml`

**Modify:**
- `packages/pocketquant-core/src/pocketquant/core/concepts/strategy/services/__init__.py` — drop the two imports; keep `STRATEGY_REGISTRY: dict[str, type] = {}` and `__all__ = ["STRATEGY_REGISTRY"]`.

## Implementation Steps

1. `git rm` the four files listed above.
2. Edit `services/__init__.py`:
   ```python
   """Strategy services - concrete strategy implementations."""

   STRATEGY_REGISTRY: dict[str, type] = {}

   __all__ = ["STRATEGY_REGISTRY"]
   ```
3. `uv run python -c "from pocketquant.core.concepts.strategy.services import STRATEGY_REGISTRY; print(STRATEGY_REGISTRY)"` — must print `{}` with no ImportError.
4. `uv run pytest packages/pocketquant-core/tests packages/pocketquant-backtest/tests -x --co -q` — collection only, must succeed (test code may still reference deleted IDs but should not import the classes).

## Success Criteria

- [ ] Four files deleted.
- [ ] `services/__init__.py` exports empty registry.
- [ ] `grep -r "MACrossoverStrategy\|HitAndRunStrategy\|ma_crossover\|hit_and_run" packages/pocketquant-core/src packages/pocketquant-backtest/src packages/pocketquant-trading/src packages/pocketquant-api/src` returns nothing.
- [ ] `uv run python -c "from pocketquant.core.concepts.strategy.services import STRATEGY_REGISTRY"` exits 0.

## Risk Assessment

- **Risk:** Other modules import the deleted classes directly (not via registry). **Mitigation:** ran `Grep` during brainstorm — only `services/__init__.py` imports them. Step 3 catches anything missed.
- **Risk:** Backtest API tests reference `ma_crossover`/`hit_and_run` strings. **Mitigation:** they reference strategy *IDs* (strings), not classes; collection still works. Updates happen in phase 6.
