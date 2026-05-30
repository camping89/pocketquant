---
phase: 1
title: "Rule and Baseline"
status: completed
priority: P1
effort: "1h"
dependencies: []
---

# Phase 1: Rule and Baseline

## Overview

Codify the comment policy in `CLAUDE.md` (IMPORTANT block) and `docs/code-standards.md` (fuller section), and establish a green test baseline so later sweeps have a regression reference. The rule must exist BEFORE any file is swept — it is the authoritative keep-bar agents apply.

## Requirements
- Functional: rule present in both `pocketquant/CLAUDE.md` and `docs/code-standards.md`; baseline test result captured.
- Non-functional: rule concise, example-driven, no plan/phase refs; consistent with existing doc tone (AS-IS, no changelog banners per CLAUDE.md doc policy).

## Architecture

Two placements:
- `CLAUDE.md` — short operational `## [IMPORTANT] Comment Policy` block agents read every session.
- `docs/code-standards.md` — fuller "Comment Policy" section with keep/remove examples, sibling to the existing async-suspension patterns section.

## Related Code Files
- Modify: `pocketquant/CLAUDE.md` (add IMPORTANT comment-policy block)
- Modify: `docs/code-standards.md` (add Comment Policy section)
- Create: none

## Implementation Steps

1. Bring infra up if needed: `just up` (Mongo+Redis). Capture green baseline: `just test` — record pass/skip/fail counts per package. This is the regression reference for phases 2–6.
2. Add to `pocketquant/CLAUDE.md` a block (place near the existing naming/doc-policy sections):

```markdown
## [IMPORTANT] Comment Policy — Explain WHY, Not WHAT

Comments cost LOC and rot. Default: no comment. Add one only when code can't speak for itself.

REMOVE / never write:
- Comments restating the line (`# increment counter`, `# validate creds` over obvious validation)
- Banner / divider / count labels (`# Trading (4)`, `# ---- setup ----`)
- Docstrings echoing the symbol name (`"""Get bar."""` on `get_bar`)
- Filler Arrange/Act/Assert markers that add nothing

KEEP / write only for:
- WHY: races, ordering/suspension constraints, invariants, trade-offs, await-preemption notes
- Hacks / workarounds + external-system quirks (OKX, Mongo, Redis, asyncio, APScheduler)
- `# type: ignore[...]` — always with its reason
- Warnings about non-obvious failure modes
- Docstrings documenting params / contracts / edge cases (not name restatement)
- Test comments explaining scenario intent or non-obvious setup

No plan/phase/finding refs in comments — explain the invariant, not the origin.
Applies to Python (`#`, `"""`) and TS/JS (`//`, `/** */`) alike.
```

3. Add a parallel "Comment Policy" section to `docs/code-standards.md` with the same keep/remove rules plus 2-3 real before/after examples drawn from the codebase (e.g. preserve `main.py` async-suspension note; remove a `# Trading (4)` banner). Note the route-docstring stance: name-echo docstrings on FastAPI routes are removed even though OpenAPI summaries may blank — only contract docstrings survive.
4. Verify both docs render and contain no plan/phase references.

## Success Criteria
- [ ] `just test` baseline captured (pass/skip/fail per package recorded in the commit body or plan notes)
- [ ] `CLAUDE.md` has the IMPORTANT Comment Policy block
- [ ] `docs/code-standards.md` has a Comment Policy section with examples
- [ ] No plan/phase refs in either doc; tone matches existing AS-IS doc policy
- [ ] Commit: `docs: add comment policy rule (CLAUDE.md + code-standards)`

## Risk Assessment
- Rule too vague → agents over/under-delete. Mitigation: concrete before/after examples in code-standards.
- Baseline skipped → no regression reference. Mitigation: this phase blocks all sweeps; baseline is step 1.
