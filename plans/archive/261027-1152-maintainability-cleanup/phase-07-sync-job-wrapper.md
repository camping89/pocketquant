# Phase 07 — Sync-job wrapper (Deploy B point)

- `sync_jobs.py`: one `_tracked(name, body)` owns the job-history document for the six jobs; one local `_detail(**kw)`; inline the single-caller `_run_*` helpers.
- Per-symbol try/except in integrity and repair; run the cascade even when a REST sync failed.
- A failed run is recorded once: the wrapper records it, the scheduler error hook does not record it again.
- Fix the round-robin comment and the matching docs line. Remove the duplicate `set_container` call.

Verify: `tests/app_test/unit/market_data`, `tests/engine_test/market_data`, job-history tests, full pytest.
