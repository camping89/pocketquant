# Advice: closing out the docs purge and no-docstring rule

Date: 2026-10-30 (Asia/Bangkok). Input: "any other advises? or we can close this". Flags: `--agent`.
Repo: `D:/w/_me/algotrading/pocketquant`, branch `develop`. Companion repo: `../pocketquant-config`.

## Verdict

Close it. The refactor itself is finished and proven: it is one commit on `origin/develop` (`d5c45781`, 429 files, +1643/-6652) and the CI run on the commit right after it (`40969706082` on `762b8233`) passed the full pytest suite, import-linter and the code-metric ratchet on Linux. Nothing about that commit needs to change. What is left is four small loose ends that would otherwise sit silently pending: one two-line comment that restores the only verified knowledge loss, four evidence reports that are still untracked, three env files uncommitted in `pocketquant-config`, and one push that carries it all through CI. That is well under an hour of work, and the main discipline is to resist doing more than that.

## What you should do

1. Restore the one lost quirk in `src/pocketquant/app/common/symbol_validation.py`. The pre-purge module docstring (verified via `git show d5c45781^:...`) said that URL clients must percent-encode `:` as `%3A` and that FastAPI decodes it before the validator runs. That is an external-client fact the code cannot show, which is exactly what the comment policy keeps. Put it as a `#` comment directly above `def validate_composite_symbol`, for example: `# URL clients send ":" as "%3A"; FastAPI decodes it before this runs, so the pattern matches the raw ":" form.` Do not restore anything else from that docstring; the format and the 400 behaviour are visible in the code.
2. Run `uv run pytest tests/core_test/unit/test_no_docstrings.py` and `uv run ruff check src tests scripts` locally. There is no unit test for the validator itself (grep for `validate_composite_symbol` and `INVALID_SYMBOL_FORMAT` under `tests/` returns nothing), so the no-docstring scan plus CI is the gate.
3. Commit in two small commits so the history stays readable: one `fix(app): ...` or `refactor(app): ...` for the comment, one `docs(reports): add docs-purge decision evidence` for the four reports (`kongming-261029-2126-docs-debate-{auditor,defender,prosecutor}.md`, `kongming-261029-2158-docs-purge-review.md`). Commit only those five files plus this report and its state file if you want the advisory trail kept.
4. Push `develop` once. The push carries the four unpushed deploy commits (`17026288`, `e555b429`, `065b38ad`, `c137af42`). CI triggers because `.py` files change; note that the workflow has `paths-ignore` for `docs/**`, `plans/**` and `**/*.md`, so a reports-only push would not have run CI at all. Watch the run to completion with `gh run watch`.
5. In `pocketquant-config`, commit the three `local/*.env` files (`all-local`, `remote-db-local-redis`, `remote-db`; +40/-66). The removed keys are `DEFAULT_BROKER`, `OKX_DEMO_MODE`, `PAPER_SLIPPAGE_PERCENT`, and none has a reader under `src/`. Do not stage the untracked `.claude/` directory there; it is agent memory, not configuration.
6. Verify the finish line: `git status --short` in `pocketquant-config` shows no `local/` changes, the four reports are tracked, the comment is present, and the newest `develop` run is `success`.

## What you shouldn't do

- Do not split or amend `d5c45781`. It is on `origin/develop`; rewriting it means force-pushing shared history for no functional gain.
- Do not fix the 322 `ruff check .` errors or the 32 `ruff format --check .` files as part of this. They are all pre-existing, concentrated in `plans/archive/*/scripts` and `scripts/rubric/*`, and none is CI-enforced. If you want them gone, that is its own change with its own CI decision.
- Do not add a replacement for the `description` field on `GET /strategies/{code}`. You decided to drop it (A1); the strategy query service, the app layer and `web/src` have no remaining reference, so the work is already complete.
- Do not do a second pass converting other removed docstrings into comments. The spot check found four candidates; three were "symbol must be composite", which `COMPOSITE_SYMBOL_PATTERN` already enforces in code. The `%3A` note is the only real loss.
- Do not touch `vps/default/.env` to remove the three dead keys now. Prod env is out of scope, and `Settings` has `extra="ignore"`, so the keys are inert. Drop them the next time that file is edited for a real reason.
- Do not sweep the other untracked files (the 2026-10-28 journal, the exness and parallel-runtime reports, the modified `code-reviewer/MEMORY.md`) into these commits. The memory diff is from the 2026-10-28 live-path review; they belong to the deploy and runtime workstream and should be judged there.

## What could be better / more efficient

1. Lowest effort, highest return: do steps 1 to 4 in a single sitting so one push and one CI run cover everything. Splitting the push leaves the deploy commits unverified for longer.
2. Since `uv run ruff check src tests scripts` already passes, adding that single command to CI would make the current clean state a floor instead of a snapshot. It is cheap, but it is a separate decision and not part of closing this work.
3. The `test_no_docstrings.py` gap (`/**` only caught at line start, and `web/vite.config.ts` / `web/vitest.config.ts` outside the scanned paths) is cosmetic. Leave it unless someone actually slips a mid-line `/**` past it.

## My take and how to get there

Treat this as a closeout, not a continuation. Current state: refactor pushed and green; four loose ends open. Route: comment in the validator, narrow test and ruff locally, two commits, one push, watch CI, commit the env files in the config repo, run the finish-line checks. If CI fails on the pushed head, the closeout change is a comment and markdown, so look at the four deploy commits first.

## Benefits

- Nothing silently pending: every artifact of the decision is either committed or explicitly left to another workstream.
- The repo alone teaches the rule: `CLAUDE.md`, `docs/code-standards.md` and `test_no_docstrings.py` are already in place, and the one external-client quirk the purge dropped is back where a reader meets it.
- The evidence behind the decision (the three-way debate and the purge review) is findable under `plans/reports/` rather than only in one machine's working tree.
- CI confirms the final head, including the deploy commits riding along.

## Trade-offs

- Pushing bundles two workstreams. If the run fails you must attribute the failure; the small size of the closeout change makes that quick, but it is still a shared run.
- Dropping `description` with no replacement (your call) breaks any consumer outside this repo that read it. I found none inside the repo and would have made the same choice; the cost is only real if an external client exists.
- The three dead keys stay in prod env until the next edit. Harmless because of `extra="ignore"`, but a reader of that file sees keys nothing consumes.
- The recommendation stops being right if a later review shows more real knowledge losses than the one found. Then the fix is still per-file `#` comments, not a docstring revival, and the cost to switch is one commit per file.

## Unverified

- No consumer of `description` outside this repository. Looked at `src/`, `web/src`, and the strategy query service; an external client could only be found by asking its owner.
- The `mongodump` / `mongorestore` lines in `docs/deployment.md` were tested container-only, not through the ssh wrapper against prod. A single dry run on the VPS would confirm them; it is not part of this closeout.
- Whether `tests/core_test/unit/test_no_docstrings.py` runs without Docker. It is a file scan, so I believe it does, but the project note says local tests generally need Docker Desktop up.

## Work checklist

- [ ] Add the `%3A` / FastAPI-decodes `#` comment above `validate_composite_symbol` in `src/pocketquant/app/common/symbol_validation.py`
- [ ] Run `uv run pytest tests/core_test/unit/test_no_docstrings.py` and `uv run ruff check src tests scripts`
- [ ] Commit the comment (`fix(app)` or `refactor(app)`)
- [ ] Commit the four evidence reports under `plans/reports/` (`docs(reports)`), optionally with this advice report and its state file
- [ ] `git push origin develop`; `gh run watch` until the run completes with `success`
- [ ] In `pocketquant-config`: commit `local/all-local.env`, `local/remote-db-local-redis.env`, `local/remote-db.env`; leave `.claude/` untracked
- [ ] Final check: validator comment present, four reports tracked, config `local/` clean, newest `develop` CI run green

## Success metrics

- `grep -n "%3A" src/pocketquant/app/common/symbol_validation.py` returns one line.
- `git ls-files plans/reports | grep -c "kongming-261029-21"` returns 4.
- `gh run list --branch develop --limit 1 --json conclusion` returns `success` for a head that includes the comment commit.
- `git -C ../pocketquant-config status --short local/` prints nothing.
- `grep -rn "description" src/pocketquant/engine/strategy/strategy_query_service.py` prints nothing (already true; stays true).

## Handoff brief

```text
Objective: Close out the docs purge / no-docstring refactor (already pushed as d5c45781) by settling its four loose ends without touching that commit.
Done means: (1) src/pocketquant/app/common/symbol_validation.py has a `#` comment above validate_composite_symbol stating that URL clients send ":" as "%3A" and FastAPI decodes it before the validator; (2) plans/reports/kongming-261029-2126-docs-debate-{auditor,defender,prosecutor}.md and kongming-261029-2158-docs-purge-review.md are committed; (3) in ../pocketquant-config, local/all-local.env, local/remote-db-local-redis.env and local/remote-db.env are committed and `git status --short local/` is clean; (4) GET /strategies/{code} has no `description` field and nothing replaces it (already true, keep it); (5) develop is pushed and the newest CI run on develop concludes success.
Out of scope: the 322 ruff errors and 32 ruff-format files under plans/archive and scripts/rubric; amending or splitting d5c45781; editing vps/default/.env; the 2026-10-28 journal, the exness/parallel-runtime reports and the modified .claude/agent-memory/code-reviewer/MEMORY.md; the four unpushed deploy commits beyond letting them ride the push; the untracked .claude/ directory in pocketquant-config.
Constraints: no history rewrite on pushed develop; no Python docstrings or /** */ blocks anywhere; `#` comments only for WHY or external quirks; plain English; conventional commits without AI references; no secrets in the pocketquant repo.
Stop and ask only if: CI fails on the pushed head for a reason you cannot trace to the four deploy commits or to the comment; any step would require a force-push or deleting data; a change outside pocketquant and pocketquant-config seems necessary.
```
