---
title: "Comment Sweep and Policy Rule"
description: "Package-by-package removal of redundant comments/docstrings + codify comment policy in CLAUDE.md and code-standards.md"
status: completed
priority: P2
branch: "develop"
tags: [refactor, comments, docs, tdd]
blockedBy: []
blocks: []
created: "2026-05-30T06:11:43.538Z"
createdBy: "ck:plan"
source: skill
---

# Comment Sweep and Policy Rule

## Overview

Strip redundant comments and name-echo docstrings across the `pocketquant/` monorepo (source **+ tests**), package by package, keeping only WHY / hack / race / ordering / suspension / `type:ignore` / warning notes and contract docstrings. Then codify the rule as an IMPORTANT block in `CLAUDE.md` and a fuller section in `docs/code-standards.md`.

**Goal:** cut comment LOC noise without deleting load-bearing intent comments. Approved brainstorm: `plans/260529-...` not applicable — this plan derives from the in-session comment-sweep brainstorm.

**TDD framing:** No new tests written. The **75 existing test files are the regression harness**. Each sweep phase: confirm green baseline → sweep → confirm still green. Behavior is locked by the suite before any comment is touched. Comment/docstring removal must NOT change runtime behavior, so a green suite before+after is the regression proof.

## Scope

- **In:** `pocketquant/packages/*` Python source + test `.py` files, root `tests/` (6 files), **`pocketquant-web` frontend `.ts/.tsx` (103 files)**.
- **Out:** `.venv`, `__pycache__`, `node_modules`, `dist`, generated/vendored code (e.g. `node_modules/flatted/flatted.py`), `pocketquant-config/` (separate, not in uv workspace), all `.md`/config files (except the two rule-doc targets).

**Verify-corrected (Validation S1):** web has NO project Python — its only `.py` is vendored `node_modules/flatted/flatted.py`. Web scope is the TypeScript SPA instead.

## Baseline numbers (scout)

| Package | src files / loc | test files / loc | full-line `#` (src) |
|---------|-----------------|------------------|---------------------|
| core | 99 / 6342 | 21 / 2652 | 155 |
| api | 121 / 5807 | 33 / 4091 | 193 |
| trading | 94 / 4353 | 10 / 752 | 152 |
| backtest | 52 / 3387 | 11 / 1705 | 73 |
| web (TS/TSX) | 103 files | — | (JS comments) |
| root `tests/` | — | 6 | — |

Repo-wide Python: ~588 full-line `#`, ~700 inline `#`, ~1384 docstring lines. Web is TypeScript (separate keep-bar: same WHY-not-WHAT principle, `//` and `/** */`).

## Keep Bar (authoritative — applies every phase)

**REMOVE** (restates WHAT):
- Comments echoing the line (`# increment counter`, `# Validate required X` over obvious validation)
- Banner / divider / count labels (`# Trading (4)`, `# ---- setup ----`, `# Market data (16)`)
- Docstrings echoing the symbol name (`"""Get the bar."""` on `get_bar`)
- Redundant Arrange/Act/Assert markers that add nothing

**KEEP** (non-obvious / code-related / warnings):
- WHY: races, ordering constraints, publish-before-subscribe, async-suspension/await preemption notes, invariants, trade-offs
- Hacks / workarounds + external-system quirks (OKX, Mongo, Redis, asyncio, APScheduler)
- `# type: ignore[...]` — always with its reason
- Warnings about non-obvious failure modes (`# benign — already dropped`)
- Docstrings documenting params / contracts / edge cases / non-obvious return semantics
- Test comments explaining scenario intent or non-obvious setup
- **No plan/phase/finding refs** in any comment (per global review-audit rule) — explain the invariant, not the origin.

⚠️ **Highest-value PRESERVE targets:** the async-suspension wiring notes in `pocketquant-api/main.py` and `pocketquant-core` app services. A regex would delete these — manual review only.

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [Rule and Baseline](./phase-01-rule-and-baseline.md) | Complete |
| 2 | [Sweep web](./phase-02-sweep-web.md) | Complete |
| 3 | [Sweep backtest](./phase-03-sweep-backtest.md) | Complete |
| 4 | [Sweep core](./phase-04-sweep-core.md) | Complete |
| 5 | [Sweep trading](./phase-05-sweep-trading.md) | Complete |
| 6 | [Sweep api and root tests](./phase-06-sweep-api-and-root-tests.md) | Complete |

## Execution Results

| Phase | Package | Baseline | After sweep | Commit |
|-------|---------|----------|-------------|--------|
| 1 | docs | full suite: 3 fail / 391 pass / 12 skip (3 fails pre-existing in `tests/scripts/`) | — | `32eb2e1` |
| 2 | web | eslint 0 err / 6 warn, tsc clean | identical | `374171e` (58 del) |
| 3 | backtest | 66 pass | 66 pass | `987eb42` |
| 4 | core | 132 pass | 132 pass | `d0426c3` |
| 5 | trading | 31 pass | 31 pass | `fbf3ad6` |
| 6 | api + root | 113 pass / 12 skip; full 3 fail / 391 pass / 12 skip | identical | `c6f56d2` |

Regression-neutral: all per-package + full-suite pass/skip counts identical before+after every sweep. The 3 full-suite failures are pre-existing `tests/scripts/` signature drift (`insert_many(source=...)` kwarg), unrelated to comments. Repo-wide ruff errors dropped 43 → 17 (long comment lines removed). main.py left 100% untouched.

Execution sequential. Phase 1 writes the policy doc + establishes green baseline (the keep-bar must exist before any file is touched). Phases 2→6 sweep one package each in risk order (leaf→root): web (TS/TSX, isolated from Python) → backtest → core → trading → api. Web first (separate language/toolchain, no Python coupling); api last (most load-bearing Python comments).

## Per-Phase Sweep Protocol (Python phases 3–6)

```
1. Baseline: just test-pkg <pkg>   (PREFER infra up via `just up`).
   FALLBACK if infra unavailable: just lint + just types + import-linter
   + `pytest packages/pocketquant-<pkg>/tests --collect-only` (catches syntax/import breaks).
2. Agent reads each src+test .py in pkg, judges every comment/docstring vs Keep Bar, edits in place
3. just lint        (ruff check .)
4. just fmt         (ruff format . — reflows after removals; reflow noise stays in same commit — accepted)
5. just test-pkg <pkg>   → green, same pass/skip counts as baseline (or fallback gate green)
6. git commit: "refactor: trim redundant comments in pocketquant-<pkg>"
```
Green→next. Red→fix or revert that file, never commit red.

**Docstring stance (Validation S1):** strip ALL name-echo docstrings, including on FastAPI routes/handlers — accepted that OpenAPI summaries may blank. Keep only docstrings with param/return/contract/edge-case content.

**Web phase (2) protocol:** TS/TSX — gate on `cd packages/pocketquant-web && npm run lint` (eslint) + `tsc -b` (typecheck via build). No pytest. Apply WHY-not-WHAT to `//` and `/** */`.

## Verification commands

- Baseline / regression: `just test-pkg <pkg>` (and `just test` at end)
- Lint+format: `just lint` then `just fmt`
- Infra (if needed): `just up` (Mongo+Redis), `just down` after
- Type check (optional gate): `just types` (pyright)

## Key constraints

- Comment removal is behavior-neutral → identical test pass/skip counts before and after each sweep is the acceptance proof.
- `just lint` is `ruff check` only; `just fmt` is separate — run both.
- One commit per package (5 sweep commits + 1 rule-doc commit).
- Some test suites need Mongo/Redis — bring infra up before baselining or note skips are consistent.

## Dependencies

No cross-plan dependencies. `plans/260529-docs-optimization` is completed and docs-only (no source comment overlap).

## Validation Log

### Session 1 — 2026-05-30
**Trigger:** `/ck:plan validate` after plan creation (`--tdd`).
**Questions asked:** 4

#### Verification Results
- Claims checked: 6 (Full tier, 6 phases)
- Verified: 5 | Failed: 1 | Unverified: 0
- VERIFIED: `test_domain_purity.py` path, `main.py` path, root `tests/` count (6), package names, root tests in `testpaths`.
- FAILED: Phase 2 "web has 1 py file" — only `.py` is vendored `node_modules/flatted/flatted.py`. Web has no project Python.

#### Questions & Answers
1. **[Scope]** Web has zero real .py (only vendored flatted). What do?
   - Options: Drop Phase 2 | Keep N/A | Expand to JS/TS
   - **Answer:** Expand to sweep web JS/TS too (103 `.ts/.tsx` files)
   - **Rationale:** Web SPA still benefits from comment sweep; keeps coverage complete.
2. **[Risk]** Infra (Mongo+Redis) gating for regression check?
   - Options: Require infra/real test (Rec) | lint+types+import-linter fallback | lint+collect-only
   - **Answer:** Fall back to lint+types+import-linter when infra unavailable
   - **Rationale:** Comment removal is behavior-neutral; static gates acceptable when infra down.
3. **[Architecture]** Docstring removal vs FastAPI/OpenAPI + `__doc__` asserts?
   - Options: Keep route/public docstrings (Rec) | Strip all name-echo | Grep __doc__ first
   - **Answer:** Strip all name-echo regardless (incl routes)
   - **Rationale:** Accept OpenAPI summary blanking; only param/contract docstrings survive.
4. **[Tradeoff]** ruff format reflow inflating diffs?
   - Options: fmt same commit (Rec) | skip fmt | fmt separate commit
   - **Answer:** Run fmt, accept reflow in same commit
   - **Rationale:** Keeps repo formatted; reflow noise tolerated in refactor commit.

#### Confirmed Decisions
- Phase 2 retargeted: web TS/TSX (103 files), eslint + `tsc -b` gate — NOT Python.
- Infra-down fallback gate: `just lint` + `just types` + import-linter + `pytest --collect-only`.
- Strip ALL name-echo docstrings incl FastAPI routes; keep only contract docstrings.
- `just fmt` runs each sweep; reflow stays in same commit.

#### Impact on Phases
- Phase 2: fully rewritten to TS/TSX sweep.
- Phases 3–6: added infra-down fallback gate to protocol (in plan.md).
- Phase 6: docstring stance note — strip route name-echo docstrings, OpenAPI summaries may blank.

### Whole-Plan Consistency Sweep
- Re-read plan.md + all 6 phase files. Searched: web/warmup/1-file/144/.py terms.
- Fixed: plan.md:75 "Web first as warmup" → "Web first (separate language/toolchain)" — stale 1-file framing removed.
- No other contradictions: Python phases 3–6 correctly say `.py`; web phase says `.ts/.tsx`; scope table updated; baseline numbers consistent.
- **Result: 0 unresolved contradictions.**
