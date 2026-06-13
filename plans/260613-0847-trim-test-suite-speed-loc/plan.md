---
title: "Trim test suite — speed + LOC"
description: "Cut test runtime 35s→~12-15s and LOC 16k→<12k by removing deployed uuid7 boot migrations + their tests, consolidating 4 duplicate testcontainer pairs to one root pair, and deleting/merging redundant tests. Behavior coverage for live code unchanged."
status: pending
priority: P2
branch: "develop"
tags: [tests, refactor, cleanup, tdd]
blockedBy: []
blocks: []
created: "2026-06-13T01:48:02.243Z"
createdBy: "ck:plan"
source: skill
---

# Trim test suite — speed + LOC

## Overview

Baseline (verified): 617 tests / 114 files / 15,957 test LOC; full run **35.1s** (612 passed, 5 skipped). Bottleneck is **4 duplicate session-scoped Mongo+Redis testcontainer pairs** (one per suite conftest), each ~3.4–3.9s setup + ~5s teardown. ~2,150 test LOC pin dead/one-shot code: 7 uuid7 boot migrations already deployed+verified on prod (git `791cbbe`, `2cd9813`, …) and a one-shot `resync_2y_from_binance` script.

Goal: speed **+** LOC. Brainstorm report: `plans/reports/brainstorm-260613-0837-trim-test-suite-speed-loc-report.md`.

Acceptance (user-confirmed): full run **< 15s**, test LOC **< 12k**, live-code behavior coverage unchanged, `just lint`/`just types`/import-linter green.

TDD framing for a test-trim: each phase captures the current green baseline first (full run + count), then mutates, then re-runs to prove surviving coverage holds. No new behavior — the "test" is the suite itself staying green with equal live-code coverage.

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [Remove uuid7 boot migrations (src + tests)](./phase-01-remove-uuid7-boot-migrations-src-tests.md) | Completed |
| 2 | [Consolidate testcontainers to root conftest](./phase-02-consolidate-testcontainers-to-root-conftest.md) | Completed |
| 3 | [Delete/merge redundant tests](./phase-03-delete-merge-redundant-tests.md) | Completed |
| 4 | [Parametrize large test files (optional <12k LOC)](./phase-04-parametrize-large-test-files-optional-12k-loc.md) | Completed (parametrize-only; LOC floor 13,971) |

## Expected Outcome

| Metric | Before | After P1-3 | After P4 (actual) |
|---|---|---|---|
| Tests (passed) | 612 | 558 | 558 |
| Test LOC | 15,957 | 13,989 | 13,971 |
| Full run (warm) | ~23s | ~10s | ~10.7s |
| Src LOC | 18,955 | ~18,200 | ~18,200 |

P1+P2 delivered the speed win (35s baseline → ~10s warm) and the bulk of the LOC cut. P3 removed obvious dead/dup tests. P4 (parametrize-only, zero coverage loss) folded structural clones in 4 files for **18 LOC** — the targeted files are distinct-path tests, not boilerplate, so parametrize tables cost nearly as many lines as the terse tests they replace.

**LOC outcome vs goal:** the `< 12k` bar was NOT reached. Parametrize-only floor is 13,971 (gap to clear was 1,990 LOC; the 5 target files total only ~2,047 LOC). User accepted this revised outcome ("parametrize, accept ~13.3k") rather than deeper coverage-touching cuts. Speed goal fully met. Reaching `< 12k` would require deleting/merging live-code tests — explicitly out of scope this round.

## Dependencies

- P2 depends on P1 (P1 deletes 7 migration test files in `app_test`; consolidating that suite's conftest after avoids churn).
- P3 independent of P1/P2 (different files) but sequence after P2 so each runs against a fast suite.
- P4 depends on P1-3 (measure LOC gap before deciding to run).
- No cross-plan dependencies — all sibling plans (`260612-0035-uuid7-id-centralization`, etc.) are `completed`.
