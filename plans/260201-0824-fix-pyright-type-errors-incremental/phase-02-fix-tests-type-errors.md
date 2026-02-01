# Phase 2: Fix tests/ Type Errors

## Context
- **Parent Plan:** [plan.md](./plan.md)
- **Depends On:** Phase 1
- **Note:** `reportPrivateUsage` is disabled for tests/ (best practice)

## Overview
- **Priority:** Medium
- **Status:** Pending
- **Description:** Fix ~19 type errors in tests/ directory

## Files to Fix

| File | Errors |
|------|--------|
| tests/conftest.py | 4 |
| tests/unit/infrastructure/tradingview/test_websocket.py | 3 |
| tests/unit/common/test_event_bus.py | 3 |
| tests/unit/domain/test_value_objects.py | 2 |
| tests/unit/common/test_mediator.py | 2 |
| tests/integration/tradingview/test_websocket_integration.py | 2 |
| Other test files | ~3 |

## Common Error Types in Tests

1. **reportOptionalMemberAccess** - Mock objects accessed without None check
   ```python
   # Error
   mock._ws.send.assert_called()

   # Fix: Assert not None first
   assert mock._ws is not None
   mock._ws.send.assert_called()
   ```

2. **Untyped fixtures** - pytest fixtures without return types
   ```python
   # Fix: Add return type
   @pytest.fixture
   def mock_client() -> AsyncMock:
       return AsyncMock()
   ```

## Implementation Steps

1. Run `npx pyright tests/` to get current error list
2. Fix conftest.py first (shared fixtures)
3. Fix unit tests
4. Fix integration tests
5. Verify with `npx pyright tests/`

## Todo
- [ ] Fix tests/conftest.py (4 errors)
- [ ] Fix tests/unit/ files
- [ ] Fix tests/integration/ files

## Success Criteria
- [ ] `npx pyright tests/` shows 0 errors
- [ ] All tests still pass: `pytest tests/`

## Next Steps
→ Run full pyright check: `npx pyright src/ tests/`
→ Commit all changes
