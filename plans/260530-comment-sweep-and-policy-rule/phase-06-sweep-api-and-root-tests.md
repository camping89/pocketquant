---
phase: 6
title: "Sweep api and root tests"
status: completed
priority: P1
effort: "3.5h"
dependencies: [5]
---

# Phase 6: Sweep api and root tests

## Overview

Sweep `pocketquant-api` — 121 src files / 5807 loc + 33 test files / 4091 loc, 193 full-line `#` — plus the 6 root `tests/` files. **Highest-care package**: holds the load-bearing DI/async-suspension wiring notes in `main.py`. Final phase; full-suite verification.

## Requirements
- Functional: redundant comments/docstrings removed per Keep Bar; full-suite pass/skip counts identical to baseline.
- Non-functional: `main.py` async-wiring and DI ordering comments PRESERVED verbatim where they explain preemption/ordering.

## Architecture
Composition root: FastAPI, Dishka DI, CQRS handler registration, middleware. `main.py` has the most critical why-comments in the repo (container wire-before-await, migration-before-register, generator cleanup order). These are the explicit highest-value PRESERVE targets.

## Related Code Files
- Modify: `packages/pocketquant-api/**/*.py` (src + tests), excluding venv/pycache.
- Modify: root `tests/**/*.py` (6 files).

## Implementation Steps
Follow Per-Phase Sweep Protocol:
1. `just test-pkg api` + root tests → green baseline (infra up).
2. Agent reads each src+test `.py`. CRITICAL: in `main.py` and DI providers, KEEP every ordering/suspension/migration-sequence note. Remove banner dividers (`# Trading (4)`), restatements, name-echo docstrings. **Validation S1:** strip name-echo docstrings on FastAPI routes too (OpenAPI summaries may blank — accepted); keep only param/contract/edge-case docstrings.
3. `just lint` → `just fmt`.
4. `just test-pkg api` → green; then full `just test` → green, counts match baseline.
5. Commit: `refactor: trim redundant comments in pocketquant-api and root tests`.
6. Final: `just qa` (lint+fmt+types) sanity check across whole repo.

## Success Criteria
- [ ] `just test-pkg api` + full `just test` green, counts match baseline
- [ ] `just lint` clean; `just types` no new errors
- [ ] `main.py` / DI ordering+suspension notes preserved
- [ ] Banner dividers + name-echo docstrings removed
- [ ] Commit made

## Risk Assessment
- `main.py` is the single highest-risk file — deleting a wire-before-await note could mask a future concurrency bug. Mitigation: diff every `main.py` change line-by-line before commit; when in doubt KEEP.
- Full-suite flakiness vs baseline. Mitigation: compare counts, re-run flaky tests, distinguish pre-existing skips from new failures.
