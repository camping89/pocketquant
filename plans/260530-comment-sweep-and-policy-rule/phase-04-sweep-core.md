---
phase: 4
title: "Sweep core"
status: completed
priority: P1
effort: "3h"
dependencies: [3]
---

# Phase 4: Sweep core

## Overview

Sweep `pocketquant-core` — 99 src files / 6342 loc + 21 test files / 2652 loc, 155 full-line `#`. Domain, common, persistence, infra ports. **High-care package** — holds async-suspension and bar-hydration intent comments.

## Requirements
- Functional: redundant comments/docstrings removed per Keep Bar; test pass/skip counts identical to baseline.
- Non-functional: domain purity AST test (`test_domain_purity.py`) must still pass — sweep touches comments only, never imports.

## Architecture
0-dep root package. Contains `BarBuilder` hydration notes, mediator/event-bus ordering comments, repository `to_mongo`/`from_mongo` contracts. These why-notes are load-bearing → KEEP.

## Related Code Files
- Modify: `packages/pocketquant-core/**/*.py` (src + tests), excluding venv/pycache.

## Implementation Steps
Follow Per-Phase Sweep Protocol:
1. `just test-pkg core` → green baseline (infra up if needed).
2. Agent reads each src+test `.py`. EXTRA CARE: bar hydration, mediator/event ordering, async-suspension notes → KEEP. Remove only true restatements + banners + name-echo docstrings.
3. `just lint` → `just fmt`.
4. `just test-pkg core` → green, same counts.
5. Commit: `refactor: trim redundant comments in pocketquant-core`.

## Success Criteria
- [ ] `just test-pkg core` green, counts match baseline (incl. `test_domain_purity.py`)
- [ ] `just lint` clean
- [ ] Async-suspension / hydration / ordering why-notes preserved
- [ ] Commit made

## Risk Assessment
- Deleting load-bearing concurrency notes. Mitigation: manual per-file review; when in doubt KEEP; diff-review before commit.
