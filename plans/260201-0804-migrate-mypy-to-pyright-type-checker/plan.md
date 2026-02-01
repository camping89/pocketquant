---
title: "Migrate mypy to pyright-only type checking"
description: "Consolidate type checking to pyright strict mode"
status: complete
priority: P2
effort: 25m
branch: feat/strategy-init
tags: [devops, type-checking]
created: 2026-02-01
---

# Migrate mypy to pyright-only Type Checking

## Overview

Consolidate dual type checker setup (mypy strict + pyright basic) to single pyright strict mode.

## Context

- **Brainstorm Report:** [brainstorm-260201-0804-mypy-vs-pyright-type-checker-decision.md](../reports/brainstorm-260201-0804-mypy-vs-pyright-type-checker-decision.md)
- **Current State:** Both tools configured with conflicting modes
- **Decision:** Pyright only (faster, native VSCode/Pylance, Pydantic v2 support)

## Phases

| Phase | Description | Status |
|-------|-------------|--------|
| [Phase 1](./phase-01-update-pyright-config.md) | Update pyrightconfig.json to strict mode | ✅ Complete |
| [Phase 2](./phase-02-remove-mypy-config-dependency-cache.md) | Remove mypy config/dep/cache, add pyright dep | ✅ Complete |
| [Phase 3](./phase-03-update-docs-mypy-to-pyright.md) | Update docs: replace mypy → pyright with rationale | ✅ Complete |

## Success Criteria

- [ ] `pyright src/ tests/` passes with strict mode *(2020 pre-existing errors need incremental fixing)*
- [x] No mypy config, dependency, or cache remains
- [x] All docs reference pyright/Pylance instead of mypy

## Dependencies

- None (standalone config migration)

## Risks

| Risk | Mitigation |
|------|------------|
| Pyright stricter than mypy basic | Run pyright first, fix errors if any |
| Missing Pydantic plugin features | Pydantic v2 native support covers most cases |
