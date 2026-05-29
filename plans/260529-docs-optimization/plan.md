---
title: "Docs Optimization: consolidate 28 to 12 canonical files"
description: ""
status: completed
priority: P2
branch: "develop"
tags: []
blockedBy: []
blocks: []
created: "2026-05-29T13:24:53.750Z"
createdBy: "ck:plan"
source: skill
---

# Docs Optimization: consolidate 28 to 12 canonical files

## Overview

Docs-only reorganization of `pocketquant/docs/` (28 files / ~6,980 lines → ~12 canonical files). Removes the 5-way overlap in the architecture cluster, trims handler-pipelines, archives historical snapshots to `docs/archive/`, deletes one stale duplicate, and reconciles every inbound link. No code changes. Source: approved brainstorm at `plans/260529-docs-optimization-brainstorm.md`.

**Goal:** single source of truth per architecture fact (kills drift that already produced wrong path `codebase-summary.md:143`), an index that matches reality, history preserved via git + `archive/`.

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [Architecture Consolidation](./phase-01-architecture-consolidation.md) | Completed |
| 2 | [Trim Handler Pipelines](./phase-02-trim-handler-pipelines.md) | Completed |
| 3 | [Archive and Delete](./phase-03-archive-and-delete.md) | Completed |
| 4 | [Index Rewrite and Link Fixes](./phase-04-index-rewrite-and-link-fixes.md) | Completed |

Execution is sequential. Phases 1–3 mutate/move/delete files (leaving links temporarily dangling); Phase 4 is the final reconciliation that fixes every link and verifies zero dangling references repo-wide.

## Final canonical set (12 files)

`README.md` (index, rewritten), `system-architecture.md`, `architecture-visual-map.md`, `handler-pipelines.md` (trimmed), `code-standards.md` (+DDD rules), `deployment.md`, `run-and-test-guide.md`, `project-overview-pdr.md`, `project-changelog.md`, `strategy-lifecycle.md`, `websocket-architecture.md`, `feature-add-symbol.md` (VI).

Plus `docs/archive/` (4 relocated docs + `journals/`), not counted as canonical.

## Key constraints

- **Markdown only** — no `.py`, no behavior. No tests to run; validation = link integrity + content-preservation diff.
- **Preserve high-value detail verbatim** when merging: codebase-summary's "Where Does X Live?" table and the env/config table.
- **Fix during merge:** `codebase-summary.md:143` path `api/features/{...}` is wrong — real layout is `trading/handlers/`, `backtest/handlers/`, `api/market_data/` (verified against package tree).

## Dependencies

No cross-plan blockers. Note: `plans/260529-bug-backlog-tick-count-and-yaml-path-context.md` references `docs/migration-doubts-and-notes.md` (archived by this plan) — its links are updated in Phase 4. Not a blocking relationship.
