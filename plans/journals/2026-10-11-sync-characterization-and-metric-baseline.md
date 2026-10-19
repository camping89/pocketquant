---
title: Sync characterization tests and metric baseline shipped
date: 2026-10-11
summary: Phase 02 pins sync jobs, cascade and the DI graph and records the metric baseline; a warm bar cache stops repair from refilling a just-deleted bar
---

# Sync characterization tests and metric baseline shipped

## What happened
Phase 02 of the Exness plan shipped as `3bd4439` and `ae22835`. CI run 38140117553 deployed both commits, and the VPS verdict was HEALTHY with 20/20 checks passed and 0 failures.
- `scripts/code_metrics.py` reproduces the pre-plan baseline `794 / 661 / 315 (0.4766) / 63` at `29f2f67`, and the current code measures the same.
- The sync pipeline characterization test pins the five cron registrations and what `sync_1m`, `sync_backfill`, `sync_repair`, `sync_integrity` and `sync_verify_cascade` write. The DI characterization test pins `BinanceClient`, `BinanceWebSocketClient`, `BrokerFactory` and 14 services.
- The gate passed 673 tests (1 skipped), and the venue baseline is 79 passed.

## Surprises
- At `22f04b6`, master was not clean for ruff: 4 test files had I001 errors, and CI never runs ruff. A separate `style:` commit fixed them before the baseline was recorded.
- The process-wide `_BAR_VALUE_CACHE` makes `upsert_bar` skip an identical bar even after its document was deleted, so `sync_repair` logs `upserted=100` without writing the bar back. The test clears the cache before repair, and the finding is recorded in `reports/finding-bar-value-cache-blocks-repair-refill.md`. No production code was changed.
- The plan said this push would publish the Phase 01 fixture commit. That commit does not exist yet because T1.9–T1.12 need FX market hours.

## Next steps
- Phase 01 T1.9–T1.12 runs during FX hours, and its fixture commit must be rebased onto the new master.
- In Phase 03, the characterization file should change only in its import block and fixture wiring. The `^[-+] *assert` grep in T3.10 misses changes to expected values on continuation lines, so diff everything from `# (a)` to the end of the file.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
