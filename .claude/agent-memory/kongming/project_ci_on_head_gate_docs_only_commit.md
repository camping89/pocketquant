---
name: ci-on-head-gate-docs-only-commit
description: Plan 261028-0652 entry gates (Phases 05, 06) look up a CI run for `git rev-parse HEAD`; a phase-close commit touching only plans/*.md never gets a CI run (cicd.yml paths-ignore), so the gate prints nothing and the runner exits NOT_YET forever
metadata:
  type: project
---

Fact (verified 2026-10-29): `.github/workflows/cicd.yml` ignores `docs/**`, `plans/**`, `**/*.md`. Each phase of plan `261028-0652-exness-only-parallel-runtime` ends with a docs-only "close the phase" commit (Phase 04: `caea4037`), so `origin/develop` HEAD has no CI run. Phase 05 and Phase 06 entry gate line 3 select the run by `headSha == $(git rev-parse HEAD)` and print empty, which the Conventions treat as a gate miss.

**Why:** The gate was written assuming HEAD is the last code commit; the consistency sweep checked seams, not this.

**How to apply:** Before a phase that checks CI on HEAD runs, append a correction: look up the newest commit that touches code, e.g. `$(git log -1 --format=%H -- src tests scripts web pyproject.toml uv.lock .github)`, or accept the run of that SHA explicitly. Same fix for the resume variant (`origin/develop`). Phase 06 line 3 needs it too.
