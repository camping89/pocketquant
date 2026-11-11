---
name: codebase-deletion-audit-2026-11-11
description: Whole-codebase deletion audit findings on 2026-11-11 that are not obvious from the code, and where the report lives
metadata:
  type: project
---

Whole-codebase deletion audit delivered 2026-11-11 at `D:/w/_me/algotrading/plans/reports/kongming-261111-1229-codebase-deletion-audit.md` (outside the repo, the path the controller gave).

Non-obvious findings at that date (verify before citing):
- `GET /subscriptions/{sub_id}/metrics` had no caller anywhere and no `require_admin_token`, unlike its sibling reads.
- `/health` "degraded" was unreachable: `credentialed` and the exness probe both came from `ExnessClient.is_configured`.
- Two `INTERVAL_SECONDS` tables existed (`core/common/constants.py`, `core/domain/shared/value_objects.py`).
- `rich`, `pyyaml`, `pre-commit`, `pytest-cov` had no user; `tzlocal` was imported but only arrived through apscheduler.
- `scripts/backfill/test_binance_bars.py` sat outside `testpaths`, so CI never ran it.
- `LICENSE` was Apache 2.0 text while `pyproject.toml` and README said MIT.
- All 7 cron jobs are re-registered with `replace_existing` at each worker takeover, so the Mongo job store only serves the UI's `next_run`.

**Why:** the owner asked delete > simplify > optimize > automate; the controller implements afterwards, so a later consult may ask what was already decided.

**How to apply:** check `git log` for the follow-up commits before repeating any item. A repo hook blocks Bash reads under `.venv`, so library internals cannot be read from there; say so instead of guessing. Related: [[project_docs_governance_purge_2026_10_29]].
