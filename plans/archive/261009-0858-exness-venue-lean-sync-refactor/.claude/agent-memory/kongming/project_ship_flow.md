---
name: project-ship-flow
description: PocketQuant ship flow — push to master deploys prod via CI; user gates merge; Kongming is consulted as a go/no-go checkpoint before each phase commit
metadata:
  type: project
---

Pushing to `master` deploys prod through `.github/workflows/cicd.yml` (tests → build → deploy; `plans/**`, `docs/**`, `**/*.md` are path-ignored). The user approves merge/push personally; phase ship tasks commit on a feature branch first.

**Why:** Single-process prod runtime (scheduler, WS feed, reconcile loop in one container), so every merge is a live deploy; the user wants an independent go/no-go on the diff before committing.

**How to apply:** When consulted at an `ak:cook --advice` checkpoint, inspect the real diff vs `master` (DI lifecycle, route surface, signature changes), confirm the baseline snapshots (`tests/baseline`) were not regenerated, and name the single top deploy risk. CI runs only `lint-imports` + `pytest tests/ -q`; ruff/pyright/`ruff format` are local-only gates, so pre-existing format drift is not a CI blocker.
