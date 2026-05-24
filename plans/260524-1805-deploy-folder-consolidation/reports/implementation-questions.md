# Implementation Questions & Divergences

Append entries here during implementation. Format defined in `../plan.md` § Divergence Protocol.

At session end, print a summary line pointing the user at this file.

---

<!-- Append entries below this line -->

## [phase-1] Stale one_time_purge block already absent — 2026-05-24 18:45
**Context:** Plan said deploy.sh contained lines ~52-65 with `# ─── One-time migrations ───` block invoking `scripts.one_time_purge_legacy_strategies`. Actual deploy.sh (57 lines total) has no such block — goes directly from "Starting services" → "Cleaning old images".
**Decision:** Skipped removal step (already cleaned, likely in a prior session). Phase 1 step 1 noted as N/A. Proceeding with reference audit per step 2.
**Question for review:** [N] no action needed.

## [phase-1] scripts/check_env.py does not exist — 2026-05-24 18:50
**Context:** Plan Phase 5 expects `scripts/check_env.py` (line 50) hard-codes `docker/compose.yml`. Repo scan shows no such file. Actual scripts/: audit_bar_quality.py, backfill_1m_from_binance.py, backfill_regression_window.py, resync_2y_from_binance.py, __init__.py, README.md.
**Decision:** Phase 5 step "scripts/check_env.py" becomes N/A. Will skip with note.
**Question for review:** [N] file genuinely absent.

## [phase-1] justfile `check` and `dev` recipes do not exist — 2026-05-24 18:50
**Context:** Plan success criteria reference `just check` and `just dev`. Actual justfile recipes: install, up, down, reset, test, test-pkg, lint, fmt, types, qa, redis, be, fe. No `check`, no `dev`. README L45 also says `just dev` — stale.
**Decision:** Phase 5 success criterion "`just check` succeeds" interpreted as `just up && just down` (the recipes that actually exist and were modified). `just dev` mention in plan ignored. README will be updated in Phase 6 (replace `just dev` with `just be`).
**Question for review:** [N] adapting to reality.

## [phase-1] .dockerignore line 16 `docker/` — not in plan scope — 2026-05-24 18:50
**Context:** `.dockerignore` excludes `docker/` from the build context. After Phase 2 deletes `docker/` and creates `deploy/`, the ignore rule is dead AND new `deploy/.env`, compose files, scripts will be included in the build context (potentially bloating image / leaking secrets).
**Decision:** Phase 4 will replace `docker/` with `deploy/` in `.dockerignore`. Adding to Phase 4 scope.
**Question for review:** [N] obvious follow-on.

## [phase-2] docker/mongo-init.js is an empty DIRECTORY, not a file — 2026-05-24 18:55
**Context:** Plan Phase 2 step 3 includes `git mv docker/mongo-init.js deploy/mongo-init.js`. Reality: `docker/mongo-init.js` is an empty directory (created in error long ago), not a tracked file. `git ls-files docker/` shows only `docker/scripts/cleanup.sh` and `docker/scripts/server-setup.sh` are tracked. No file in the repo (compose.yml, compose.prod.yml, any .sh, any .md) references `mongo-init`.
**Decision:** Removed empty directory via `rmdir docker/mongo-init.js`. Skipped the move. Phase 6 changelog will NOT mention mongo-init.js as moved. If a real mongo-init.js file is needed in future, it'll be created fresh in `deploy/`.
**Question for review:** [N] no impact — file wasn't doing anything.

## [phase-1] justfile `redis` recipe at line 52, not 56 — 2026-05-24 18:50
**Context:** Plan Phase 5 step 4 says line 56. Actual is line 52.
**Decision:** Use correct line; cosmetic line-number drift only.
**Question for review:** [N] no-op.
