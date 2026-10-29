# Documentation Rules

A doc line costs reading time and goes stale when the code changes. Write one only when no file in the repo can tell the reader the same thing.

Readers are agents that can grep the repo and a human owner who reviews their work. Both read code. A doc exists for what code cannot say.

Scope: `CLAUDE.md`, `README.md`, and every tracked `*.md` under `docs/`, `scripts/`, `deploy/` and `web/`. Code comments follow the comment policy in `code-standards.md`. `plans/` is exempt.

## The Line Test

Apply it to every line you add or keep. The first rule that matches decides.

1. **Owned: delete.** If a file that the program, a test or CI reads already holds the fact, the doc does not copy it. That covers names, paths, signatures, routes, env vars, defaults, numbers, schedules, counts, lists, schemas and formulas. You may leave a pointer (`path` or `path::symbol`) when one grep would not find the owner. Never copy the value. A command or URL the reader runs is quoted whole; it is not a copy.
2. **Enforced: delete.** If a test, linter, validator or CI step checks a rule, the check is the doc. Delete the prose.
3. **One site: move.** If the reason behind a choice belongs to one function, file or line, write it as a comment there (see the comment policy in `code-standards.md`). Delete the doc line.
4. **Keep.** Keep a line only when it is one of these:
   - A decision and the alternative it rejected, when the decision spans files, processes or runtimes.
   - Negative knowledge: what does not exist, is not supported, or must not be done. A grep cannot prove absence.
   - A fact outside this repo: the VPS, Cloudflare, `pocketquant-config`, broker or data-provider behavior. Say how it was verified.
   - A procedure or checklist that touches three or more files, or runs outside the repo.
5. **Stale: fix now.** A line that no longer matches the code is fixed or deleted in the same change. Code is the source of truth.

"An LLM can find it" is not the test. "One file already holds it" is the test.

## Where Content Goes

| Content | Home |
|---|---|
| A fact the code holds | Nowhere. The code is the doc. |
| A reason tied to one site | A comment at that site. |
| A behavior that must not change | A test. Its name states the rule. |
| A rule an agent breaks without being told | `CLAUDE.md`. |
| Run, test and smoke-test commands | Root `README.md`. |
| A cross-file decision, negative knowledge, an outside-repo fact, a procedure | `docs/`. |
| Plans, reports, journals, roadmaps | `plans/`. They are records, not authority. They age. Docs and code never cite them as authority. |
| History: what changed, what was tried | Git. |

## Where Facts Live

- Routes: `app/routes/`, or the OpenAPI page at `http://localhost:41921/api/v1/docs` on a running app.
- Env vars and defaults: `src/pocketquant/core/config.py`.
- Import contracts and the code metric ceiling: `pyproject.toml`.
- Job schedules: `register_sync_jobs` in `engine/market_data/app_services/sync_jobs.py`.
- Collections and indexes: `core/common/constants.py` and each repository's `ensure_indexes`.

## Before You Add a Doc Line

1. Grep for the fact. If code, config or a test holds it, stop.
2. Grep the docs. If another doc holds it, edit that one. One fact lives in one doc.
3. Name no number, path or symbol unless it is a pointer to its owner.
4. Check that every path, symbol and env var in the doc you touched still exists.
5. Ask the owner before you add a new file under `docs/`.
