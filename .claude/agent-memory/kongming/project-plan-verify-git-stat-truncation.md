---
name: plan-verify-git-stat-truncation
description: Plan Verify commands that grep `git show --stat` for full paths fail on long paths because git abbreviates them to `.../`; use `--name-only` with anchored regex
metadata:
  type: project
---

Phase 01 T1.12 of the exness plan (2026-10-13) failed its Verify on a clean commit because `git show --stat --format= HEAD` printed ` .../infra/exness/fixtures/<file>` and the grep for `tests/core_test/infra/exness/fixtures/` no longer matched (15 false positives).

**Why:** git truncates stat paths to fit the terminal/stat width. The plan's ship steps (plan.md:107) copy this idiom across phases.

**How to apply:** When writing or reviewing a plan Verify that checks "commit holds only files under X", prefer `git show --name-only --format= HEAD | grep -vcE "^(X/|Y/)"` with `^` anchors. Treat such a miss as a Verify defect once `--name-only` proves the commit clean; do not re-cut the commit.
