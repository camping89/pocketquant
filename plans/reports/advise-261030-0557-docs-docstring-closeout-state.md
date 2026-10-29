# advise-state
phase: advise (delivered 2026-10-30 ~06:15 +0700)
input: "any other advises? or we can close this" (closeout check for the docs purge + no-docstring rule work on develop)
flags: --agent

## scout-findings (verified 2026-10-30, repo D:/w/_me/algotrading/pocketquant, branch develop)
- The brief said "nothing committed"; that is stale. The whole change is commit `d5c45781 refactor: drop docstrings, move tracing middleware to app and trim docs` (429 files, +1643/-6652), on `origin/develop`. Splitting the commit now would mean rewriting pushed history.
- CI run 40969706082 (headSha 762b8233, the commit right after d5c45781) concluded `success` on 2026-10-29T22:57Z, so the full pytest suite + lint-imports + code-metric ratchet passed on Linux with the docstring purge in the tree. CI does not run ruff check/format or pyright.
- `uv run ruff check src tests scripts` passes. `ruff check .` reports 322 errors and `ruff format --check .` 32 files, all pre-existing and concentrated in `plans/archive/*/scripts` plus `scripts/rubric/*` and a few tests; none is CI-enforced.
- Working tree (re-checked 06:05): 16 untracked files (this state file, the 2026-10-28 journal, exness/parallel-runtime brainstorm/explore/kongming reports, and the four docs-decision reports: kongming-261029-2126-docs-debate-{auditor,defender,prosecutor}.md + kongming-261029-2158-docs-purge-review.md) and one modified `.claude/agent-memory/code-reviewer/MEMORY.md`.
- NEW since last turn: `b21dbe49` is now pushed; four deploy commits (`17026288`, `e555b429`, `065b38ad`, `c137af42`, 06:03-06:05 +0700, "three services from one image" / deploy lock / role roll) sit unpushed on local develop. They are a separate workstream; `d5c45781` remains an ancestor of HEAD. Any closeout commit will be pushed together with them.
- `description` field: was `(strategy_class.__doc__ or "")` in `engine/strategy/strategy_query_service.py::get_one`; removed. `web/src` has no `description` on strategy types/hooks/components; no `__doc__`/`getdoc` use remains anywhere under src/scripts/tests. grep re-confirmed 06:05: no `description` in the strategy query service.
- Comment-conversion spot check (removed docstring lines containing contract words with no `#` comment added in the same file) flagged 4 files; 3 are "symbol must be composite" which `COMPOSITE_SYMBOL_PATTERN` already enforces. One real loss: `app/common/symbol_validation.py` lost the note that URL clients must percent-encode `:` as `%3A` and FastAPI decodes before the validator (grep for `%3A`/`percent` in that file returns nothing, re-confirmed 06:05) — an external-client quirk the comment policy says to keep.
- `test_no_docstrings.py` scans src/scripts/tests (all tracked .py live there) and `web/src` (only `web/vite.config.ts`, `web/vitest.config.ts` fall outside). Rule gap is cosmetic: `/**` is only caught at line start.
- `pocketquant-config`: `local/*.env` (3 files: all-local, remote-db-local-redis, remote-db; +40/-66) still uncommitted (re-checked 06:05); removed keys DEFAULT_BROKER, OKX_DEMO_MODE, PAPER_SLIPPAGE_PERCENT have no reader in `src/` (verified dead) but still sit in `vps/default/.env` (prod); harmless because `Settings` has `extra="ignore"`.
- `docs/deployment.md` mongodump/mongorestore lines are untested against prod via the ssh wrapper (brief says container-only test).

## qa-log
- Q1: Keep or drop the `description` field on GET /strategies/{code}? -> A1: Bỏ luôn (drop the field, no replacement).
- Q2: Confirm the reframing below (preview skipped)? -> A2: Đúng, tư vấn đi (confirmed as drafted).

## re-verified at delivery (06:12)
- Working tree, unpushed deploy commits, CI 40969706082 success, no `description` left, no `%3A` in symbol_validation.py, config `local/*.env` still modified: all unchanged from scout.
- Pre-purge docstring (git show d5c45781^) confirmed the `%3A` / FastAPI-decodes sentence.
- CI workflow has paths-ignore for docs/**, plans/**, **/*.md: a reports-only push would not run CI.
- code-reviewer/MEMORY.md diff is from the 2026-10-28 live-path review, not this work.
- No tests reference validate_composite_symbol / INVALID_SYMBOL_FORMAT.

## reframing-draft
problem: The docs purge + no-docstring refactor is already pushed to origin/develop as one CI-green commit (d5c45781). "Closing" it does not mean touching that commit; it means settling the four loose ends it left behind so nothing is silently pending and future agents can follow the new rules from the repo alone.
requirements:
1. GET /strategies/{code} ships without `description` and nothing replaces it (A1). Verifiable: no `description` key on the strategy DTO, route, or web types; tests pass.
2. The one verified knowledge loss is restored: `src/pocketquant/app/common/symbol_validation.py` carries a `#` comment that URL clients send `:` as `%3A` and FastAPI decodes it before the validator runs.
3. The `pocketquant-config` change (`local/*.env`, 3 files) is committed in that repo; the dead keys are not re-added anywhere.
4. The four docs-decision evidence reports (three kongming docs-debate reports + the docs-purge review) are committed under `plans/reports/`.
5. CI is green on the resulting head of develop.
goals: close with nothing silently pending; the repo alone (CLAUDE.md, docs/code-standards.md, test_no_docstrings.py) is enough for a future agent to follow the no-docstring rule; the evidence behind the decision stays findable.
done means: `description` absent and tests green; `%3A` comment present in symbol_validation.py; `git status` clean in pocketquant-config `local/`; the four evidence reports tracked; latest develop CI run = success.
non-goals: reformatting the 32 pre-existing ruff-format files or fixing the 322 ruff errors under plans/archive and scripts/rubric; splitting or amending d5c45781; touching prod env (vps/default/.env); the other untracked reports (exness/parallel-runtime), the journal, and the four unpushed deploy commits (separate workstream, judged on their own).
constraints: no history rewrite on pushed develop; code is the source of truth, docs stay AS-IS English; `#` comments only for WHY/quirks, never restated docstrings.

## preview
skipped (closeout checklist has no structure worth drawing) -- confirmed-by-question instead (Q2)

## next
Done. Advice written to D:/w/_me/algotrading/pocketquant/plans/reports/advise-261030-0557-docs-docstring-closeout.md; ADVICE_READY emitted.
