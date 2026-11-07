---
name: docs-governance-purge-2026-10-29
description: 2026-10-29 docs purge — docs/README.md deleted, governance rule "write a doc only for what one file cannot hold"; drifts found (ENABLE_JOBS retired but still in README, sync_1m at :12 not :02, 6 contracts not 8, ERD stale)
metadata:
  type: project
---

On 2026-10-29 the user started a docs purge: `docs/README.md` deleted, `docs/governance/` created (CLAUDE.md tells agents to read every file there), and a methodology for "write a doc or not" was debated by three kongming debaters (defender report: `plans/reports/kongming-261029-2126-docs-debate-defender.md`).

**Why:** the user's rule is "anything an LLM can trace easily from code, don't write doc". Verified evidence that copied facts rot: `README.md`, `docs/system-architecture.md:52`, `docs/deployment.md:218-221` still say `ENABLE_JOBS=false` while `config.py:111-114` raises `ValueError("ENABLE_JOBS is retired")` (APP_ROLES + Mongo leases replaced it); `sync_jobs.py:737` runs `sync_1m` at `second=12` but docs say :02; `pyproject.toml` has 6 import-linter contracts, README and code-standards say 8; `docs/visuals/collection-erd.mmd` claims hash `_id`s and OKX.

**How to apply:** when advising on docs here, apply the one-file test (grep finds it in one file → pointer or delete), keep only spans (cross-file/process/repo invariants), outside-repo ops facts, requirements, and rejected alternatives. Treat `docs/journals/` as records, never authority. Re-check the drift list above before citing README/system-architecture on process model or schedules; the fixes may have landed since.
