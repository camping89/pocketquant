# Phase 4: Strategy Commands

## Context

- Parent: [plan.md](plan.md)
- Depends on: Phase 1

## Overview

- **Priority:** P2
- **Status:** pending
- **Effort:** 15m

Convert strategy commands from dataclass to Pydantic and simplify routes.

## Files to Modify

| File | Changes |
|------|---------|
| `src/features/strategy/handlers/commands.py` | dataclass → Pydantic |
| `src/features/strategy/api/routes.py` | Remove LoadStrategyRequest, simplify |

## Implementation Steps

### 1. Convert commands.py

Before:
```python
from dataclasses import dataclass
from pathlib import Path

@dataclass
class LoadStrategyCommand:
    config: StrategyConfig | None = None
    path: Path | None = None

@dataclass
class StartStrategyCommand:
    strategy_id: str
```

After:
```python
from pydantic import BaseModel, Field
from pathlib import Path

class LoadStrategyCommand(BaseModel):
    """Load a strategy from configuration."""
    config: StrategyConfig | None = None
    path: Path | None = Field(default=None, description="Alternative: load from file")

class StartStrategyCommand(BaseModel):
    """Start a loaded strategy."""
    strategy_id: str = Field(..., description="Strategy identifier")

class StopStrategyCommand(BaseModel):
    """Stop a running strategy."""
    strategy_id: str = Field(..., description="Strategy identifier")
```

### 2. Simplify routes.py

Before:
```python
class LoadStrategyRequest(BaseModel):
    path: str

@router.post("/load")
async def load_strategy(body: LoadStrategyRequest, mediator: ...):
    path = Path(body.path)
    config = StrategyLoader.load(path)
    strategy_id = await mediator.send(LoadStrategyCommand(config=config))
    ...
```

After:
```python
@router.post("/load")
async def load_strategy(cmd: LoadStrategyCommand, mediator: ...):
    # Note: StrategyLoader.load() logic might need adjustment
    strategy_id = await mediator.send(cmd)
    ...
```

- Remove: LoadStrategyRequest class
- Note: Current route loads config in route, may need to move to handler

## Todo

- [ ] Convert all 3 command classes to Pydantic
- [ ] Simplify routes
- [ ] Handle StrategyLoader.load() logic (keep in route or move to handler)
- [ ] Run pyright

## Success Criteria

- [ ] All strategy commands are Pydantic models
- [ ] Routes simplified
- [ ] No type errors
- [ ] Strategy endpoints work

## Notes

- LoadStrategyCommand has special handling (loads config via StrategyLoader)
- May keep route logic for now, or move StrategyLoader call to handler
- StartStrategyCommand and StopStrategyCommand are simple pass-through
