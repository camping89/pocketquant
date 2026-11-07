---
name: doc-check-loop-flags-unqualified-relative-paths
description: The plan "names exist" doc-check loop (backticked tokens with a slash, resolved repo-relative or under src/pocketquant/) flags sibling-repo paths, scripts/-relative names and keyword pairs like try/finally; they are not stale, fix = qualify the path
metadata:
  type: project
---

The doc-check loop used in plan 261101-0843 Phase 17 Task 17.8 step 2 scans every backticked token containing `/` in each doc changed since the plan base and resolves it repo-relative or under `src/pocketquant/`. On 2026-11-03 it printed 11 "missing" lines, none stale: `backfill/*.py` (real path `scripts/backfill/*.py`, the `scripts/` prefix was implied by `python scripts/<path>` one paragraph up), `vps/default/*` and `one-time/bootstrap-gh.sh` (sibling repo `../pocketquant-config/`), and `try/finally` (Python keywords). All 11 lines came from commit d5c45781 (2026-10-30), before the plan base; the loop scans whole files, not the diff.

**Why:** the checker is a heuristic with no notion of a path-prefix context or a sibling repo. The honest pass is to qualify each path in the doc's own convention (`scripts/...`, `../pocketquant-config/...`, already used at deployment.md:35-36,102 and code-standards.md:12,82,148), not to weaken the loop or accept a non-zero count.

**How to apply:** when a future plan reuses this loop and prints non-zero, first `git blame` the lines and test the targets; if they exist, qualify the path and keep the step's prescribed commit. Resolving `../pocketquant-config/...` makes the check depend on the sibling checkout being present (it is on the owner's machine). See [[exness-cook-prod-and-gate-quirks]] and [[phase-report-gate-keys-bare-lines]].
