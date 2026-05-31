---
title: "Move package test suites to root tests/"
description: "Consolidate 4 in-package pytest suites under root tests/ as <pkg>_test dirs; rewire 6 config/doc touchpoints. No behavior change."
status: completed
priority: P2
branch: "develop"
tags: [refactor, tests, monorepo]
blockedBy: []
blocks: []
created: "2026-05-31T00:36:59.180Z"
createdBy: "ck:plan"
source: skill
---

# Move package test suites to root tests/

## Overview

Move `packages/pocketquant-{core,backtest,trading,api}/tests/` → root
`tests/{core,backtest,trading,api}_test/` via `git mv` (history preserved).
Collapse `testpaths` to `["tests"]` and rewire pyright, justfile, CI, and 2 doc
refs. Conftests move as-is (no consolidation). Pure mechanical refactor — same
test count before/after, no source or test-logic changes.

Design doc: [brainstorm-summary.md](./brainstorm-summary.md)

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [Move and Rewire](./phase-01-move-and-rewire.md) | Completed |
| 2 | [Validate](./phase-02-validate.md) | Completed |

## Dependencies

None. Sibling plans (`260529-docs-optimization`, `260530-comment-sweep-and-policy-rule`)
touch doc content, not test structure — no overlap.
