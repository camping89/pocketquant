---
phase: 4
title: "Apply the chosen Database API + sweep call sites"
status: pending
priority: P2
effort: "1.5h"
dependencies: [3]
---

# Phase 4: Apply Database API decision + sweep call sites

## Overview

Mechanical: read Phase 3's decision report, apply the diff to `mongodb.py`, sweep every call site in the inventory, update `test_strategy_id_migration.py` to match, and re-run Phase 2's lifespan smoke tests. Ship.

## Requirements

- Functional:
  - `packages/pocketquant-core/src/pocketquant/core/persistence/mongodb.py` matches Phase 3's diff sketch.
  - All call sites in Phase 3 inventory updated (no `db.get_database()` or `db.database` references that contradict the chosen API).
  - `test_strategy_id_migration.py` passes against develop HEAD.
  - Phase 2's `test_lifespan_boot.py` passes against develop HEAD.
  - Full `uv run pytest packages/` suite green.
- Non-functional:
  - Single PR / single mergeable commit set on `develop`.
  - Update `docs/code-standards.md` `Database` section IF Phase 3 changed the public surface.
  - Update `Database` class docstring if Phase 3 changed encapsulation policy.

## Architecture

Depends on Phase 3 outcome:

- **If A (public property):** add `@property database`, leave `get_database()` as alias, no consumer-side rewrites (existing `get_database()` calls keep working).
- **If B (domain helpers):** add methods, deprecate `get_database()`, sweep every consumer of raw `AsyncDatabase` to use a helper or `get_collection()`.
- **If C (hybrid):** A's code + a doc note in `mongodb.py` + a short `docs/code-standards.md` blurb steering future code to helpers/`get_collection`.

## Related Code Files

(Mutated)
- `packages/pocketquant-core/src/pocketquant/core/persistence/mongodb.py`
- `packages/pocketquant-api/src/pocketquant/api/main_extensions.py` (already on `get_database()` since 260528-2000; may flip back to `.database` if A or C)
- `packages/pocketquant-api/tests/unit/test_strategy_id_migration.py`
- Possibly: `packages/pocketquant-{backtest,trading,api}/src/.../persistence/*_repository.py` if B and helpers replace direct collection access (unlikely — repositories already use `get_collection`).
- `docs/code-standards.md` (if Phase 3 changed public surface)

## Implementation Steps

1. Read Phase 3 report; copy the diff sketch out.
2. Apply the diff to `mongodb.py`. Verify `python3 -c "import ast; ast.parse(open('...').read())"` parses.
3. For Phase 3 option A or C: optionally revert `main_extensions.py` from `get_database()` → `.database` (cosmetic; either form works once the property exists).
4. For Phase 3 option B: rewrite every consumer per inventory. Verify with `grep` after.
5. Update `test_strategy_id_migration.py` to match (most likely just stays as `db.database` for A/C, or gets per-helper rewrites for B).
6. Run `uv run pyright packages/pocketquant-core/ packages/pocketquant-api/` — fix any type errors surfaced by the API change.
7. Run `uv run ruff check packages/pocketquant-core/ packages/pocketquant-api/` — fix lint.
8. Run `uv run pytest packages/pocketquant-api/tests/ -v` — all green.
9. Run the full `uv run pytest packages/` (including core, backtest, trading) — all green.
10. If Phase 3 changed public surface: update `docs/code-standards.md` `Database` paragraph + the class docstring in `mongodb.py`.
11. Push to `develop`. CI must show `tests` job + the 4 normal jobs all green.
12. Verify post-deploy: `ssh "$(cat ../pocketquant-config/vps/default/host)" 'docker exec pocketquant-app curl -s http://localhost:41920/health'` → 200.

## Success Criteria

- [ ] Diff applied + parses + type-checks + lints.
- [ ] All call sites in Phase 3 inventory updated (verified by re-running the grep from Phase 3 step 1; expected: all hits match the chosen API).
- [ ] `test_strategy_id_migration.py` passes locally.
- [ ] Phase 2's `test_lifespan_boot.py` passes locally.
- [ ] Full `uv run pytest packages/` passes locally.
- [ ] CI on `develop` green (4 jobs + new `tests` job).
- [ ] VPS `/health` 200 after the deploy.
- [ ] `docs/code-standards.md` updated if needed (Phase 3 decision determines).

## Risk Assessment

| Risk | Mitigation |
|---|---|
| Sweep misses a call site → runtime AttributeError reappears | Phase 2's lifespan boot test catches this (that's its job). |
| Type checker complains about property returning `AsyncDatabase | None` semantics | Property raises `RuntimeError` on `None` like `get_database()` does; signature is `-> AsyncDatabase`. |
| Choosing B explodes scope (many helpers needed) | Phase 3 step 4 already scoped the helpers; Phase 4 only adds those. New helpers added on demand later. |
| Pyright or ruff disagrees with the new shape | Fix as part of the same commit set — don't punt. |
| `docs/code-standards.md` Database section drifts | Step 10 mandatory if Phase 3 changed surface. Use Phase 3 report's wording verbatim. |

## Next Steps

- (Optional, separate plan) Investigate why CI never had a pytest gate before this plan. Likely tech-debt — but resolved as a side-effect of Phase 2.
- Close `cook-deferred-items-and-questions.md` "Tech debt" items 4 + 5.
