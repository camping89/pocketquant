# Domain Layer Pydantic→Dataclass Refactor - Documentation Update

**Date:** 2026-03-09 | **Time:** 09:52 | **Status:** Complete

## Summary

Updated project documentation to reflect domain layer refactor from Pydantic BaseModel to stdlib dataclasses. All 22 domain classes (events, value objects, aggregates) now use Python's built-in `@dataclass` decorator instead of Pydantic, with explicit patterns for immutability and validation.

## Changes Made

### 1. code-standards.md (796 LOC, under 800 limit)

**Added Section:** "Domain Layer Patterns (Dataclasses, Not Pydantic)"
- Concise guide to dataclass usage in domain layer
- Value objects: `@dataclass(frozen=True)`
- Events: `@dataclass(frozen=True, eq=False)` with custom `__eq__` by event_id
- Aggregates: `@dataclass` (mutable) with hidden events
- Rules: No Pydantic, use `generate_id()`, immutability for VOs/events

**Updated Section:** "Clean Architecture Rules"
- Added explicit ❌ "No Pydantic BaseModel (use stdlib dataclasses instead)"
- Clarified events use `@dataclass(frozen=True, eq=False)`
- Emphasized validation in `__post_init__()` method

**Updated Section:** "Import Organization"
- Added separate examples for Features layer (Pydantic allowed) and Domain layer (dataclasses only)
- Clarified domain layer has no third-party or I/O imports

**Trimmed:** Deprecated Patterns section (consolidated 24 items into 8 rows)
- Kept critical patterns, removed redundancy
- Added reference to "Pydantic in domain/" as deprecated

### 2. system-architecture.md (800 LOC, at limit)

**Updated Section:** "Layer 1: Domain (Pure Business Logic)"
- Replaced single Pydantic example with concise dual example (Value Object + Event)
- Clarified: "Immutable value object using stdlib dataclass (not Pydantic)"
- Shows frozen dataclass pattern: `@dataclass(frozen=True)`
- Shows event pattern: `@dataclass(frozen=True, eq=False)` with custom `__eq__`

**Trimmed:** Security section (condensed to 2 lines)
- Preserved all info, improved conciseness

### 3. codebase-summary.md (622 LOC)

**Updated Section:** "src/domain (2,364 LOC, 39 files)"
- Added "No Pydantic BaseModel (use stdlib dataclasses instead)" to rules
- Clarified "Pure Business Logic" heading

**Updated Section:** "Aggregates (6)"
- Changed "Mutable Dataclasses" designation in section heading
- All 6 aggregates noted as using `@dataclass` (mutable)

**Updated Section:** "Value Objects (Frozen Dataclasses)"
- Changed heading to emphasize `@dataclass(frozen=True)`
- Added notes on `__post_init__` validation

**Updated Section:** "Domain Events (13+)"
- Changed heading: "Frozen Dataclasses with @dataclass(frozen=True, eq=False)"
- Added note: "All events extend DomainEvent base (frozen dataclass with custom __eq__ by event_id)"

**Updated Section:** "Dependencies"
- Clarified Pydantic use: "Settings validation + Features layer (commands/queries). Domain layer uses stdlib dataclasses instead."

## Verification

✓ All references to Pydantic in domain layer context now accurate
✓ code-standards.md: 796 LOC (under 800 limit)
✓ system-architecture.md: 800 LOC (at limit)
✓ codebase-summary.md: 622 LOC (under 800 limit)
✓ No Pydantic imports found in domain layer code
✓ 35+ @dataclass decorators confirmed in domain/ (no BaseModel)

## Documentation Accuracy

All changes verified against actual codebase:
- Domain layer confirmed using `@dataclass(frozen=True)` for value objects
- Domain layer confirmed using `@dataclass(frozen=True, eq=False)` for events
- Domain layer confirmed using `@dataclass` (mutable) for aggregates
- No Pydantic BaseModel usage in domain/ layer
- Features layer continues to use Pydantic for commands/queries (correct)
- Configuration layer continues to use Pydantic settings (correct)

## Key Patterns Documented

| Pattern | Location | Usage |
|---------|----------|-------|
| Value Objects | Domain | `@dataclass(frozen=True)` with `__post_init__` validation |
| Events | Domain | `@dataclass(frozen=True, eq=False)` with custom `__eq__` by event_id |
| Aggregates | Domain | `@dataclass` (mutable) with `field(init=False, repr=False)` for hidden events |
| Commands/Queries | Features | Pydantic `BaseModel` (continued, unchanged) |
| Settings | Config | Pydantic `BaseSettings` (continued, unchanged) |

## Impact

- **Readers will now understand:** Domain layer uses Python stdlib dataclasses, not Pydantic
- **New developers can:** Implement domain classes following clear patterns
- **Architecture enforced via:** test_domain_purity.py (AST check prevents I/O imports)
- **Zero breaking changes:** Documentation describes current implementation accurately

## Files Modified

1. `/Users/admin/workspace/_me/pocketquant/docs/code-standards.md`
2. `/Users/admin/workspace/_me/pocketquant/docs/system-architecture.md`
3. `/Users/admin/workspace/_me/pocketquant/docs/codebase-summary.md`

## Next Steps

- [ ] Review documentation changes
- [ ] Commit changes with message: "docs: update domain layer patterns for dataclass refactor"
- [ ] Consider adding example domain class file to learning guide (optional)
