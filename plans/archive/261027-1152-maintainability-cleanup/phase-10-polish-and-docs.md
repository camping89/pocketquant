# Phase 10 — Polish and docs

- `main_extensions.py`: one `_cancel(task)`, one `enable_jobs` gate, and the startup failure path becomes `logger.exception` + raise.
- One SSE poll helper for `stream_bars` and `stream_quote`; re-raise `CancelledError`; drop the unused `request` parameter.
- The `market_data.py` sync-status routes return the DTO.
- Fix stale comments and the remaining non-English text.
- Docs: `system-architecture.md`, `codebase-summary.md`, `project-overview-pdr.md`, `README.md`, and the CLAUDE.md sentence for decision 11.

Verify: gates + full pytest + web build; grep docs for `okx`, `/trading/`, `Idempotency`.
