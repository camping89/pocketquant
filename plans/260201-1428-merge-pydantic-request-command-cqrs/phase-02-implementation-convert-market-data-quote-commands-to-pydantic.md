# Phase 2: Market Data Quote Commands

## Context

- Parent: [plan.md](plan.md)
- Depends on: Phase 1

## Overview

- **Priority:** P2
- **Status:** pending
- **Effort:** 20m

Convert market_data/quote commands from dataclass to Pydantic. These are simpler as they have no corresponding Request classes in routes.

## Files to Modify

| File | Changes |
|------|---------|
| `src/features/market_data/quote/command.py` | dataclass → Pydantic BaseModel |

## Implementation Steps

### 1. Convert command.py

Before:
```python
from dataclasses import dataclass

@dataclass
class SubscribeCommand:
    symbol: str
    exchange: str

@dataclass
class StartQuoteFeedCommand:
    pass
```

After:
```python
from pydantic import BaseModel, Field

class SubscribeCommand(BaseModel):
    """Subscribe to real-time quotes for a symbol."""
    symbol: str = Field(..., description="Trading symbol")
    exchange: str = Field(..., description="Exchange name")

class UnsubscribeCommand(BaseModel):
    """Unsubscribe from real-time quotes for a symbol."""
    symbol: str = Field(..., description="Trading symbol")
    exchange: str = Field(..., description="Exchange name")

class StartQuoteFeedCommand(BaseModel):
    """Start the quote WebSocket feed."""
    pass

class StopQuoteFeedCommand(BaseModel):
    """Stop the quote WebSocket feed."""
    pass
```

## Todo

- [ ] Convert all 4 command classes to Pydantic
- [ ] Verify handler imports still work
- [ ] Run pyright

## Success Criteria

- [ ] All quote commands are Pydantic BaseModel
- [ ] No type errors
- [ ] Quote routes still work

## Notes

- Empty commands (StartQuoteFeedCommand, StopQuoteFeedCommand) still valid as Pydantic models
- No route changes needed (quote routes already use commands directly)
