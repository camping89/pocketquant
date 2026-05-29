# Binance per-minute sync regression — in-progress bar capture

**Date:** 2026-05-08 | **Severity:** HIGH (data correctness) | **Plan:** `260508-2147-binance-sync-in-progress-bar-fix`

## What happened

After the Binance migration (v2.0.0, 2026-05-08 ~07:30 UTC), every minute the
cron `sync_1m` called `BinanceClient.fetch_ohlcv(n_bars=100)`. Because Binance
returns the *current* kline whose `openTime == floor(now/duration)*duration`
populated with whatever trades have been seen so far (often ~2 seconds of
data), each minute we were inserting a fresh "almost-empty" 1m row, then on
the next minute `filter_new_bars` saw the openTime as already-present and
refused to overwrite it. End result: the 1m collection contained 303 partial
bars out of 486 in the regression window, and cascade-built 5m/15m/1h/4h
buckets inherited the corruption (100% partial in window).

`sync_verify_cascade`, the existing hourly canary, never alerted because it
compared **only `close`** with an **absolute `$0.01`** threshold and only
sampled one symbol per hour round-robin. With prices ticking $80k, an
absolute $0.01 close-only check is well inside trading noise — the regression
was invisible to monitoring.

## What we did

Three thin code changes plus an ops-only backfill:

1. **`BinanceClient.fetch_ohlcv` caps `endTime`** at
   `floor(now/duration)*duration - 1` (exclusive); we also added a
   defense-in-depth filter that drops any kline whose `openTime >= cutoff` in
   case Binance still returns one under clock skew. Two-tier protection in a
   single function.
2. **`sync_verify_cascade` switched to full OHLCV** with relative thresholds
   (price 0.01% / volume 5%) and now iterates all tracked symbols every cycle.
3. **`scripts/backfill_regression_window.py`** — one-shot, drives the existing
   `BarRepository.delete_many_by_range` + `SyncSymbolCommand` + cascade. We
   ran it on the VPS after pausing `sync_1m` (`ENABLE_JOBS=false` + recreate)
   and re-deploying the patched `binance_client.py` via `docker cp`, then
   resumed cron. Mongodump backup taken first
   (`/tmp/pq-backup-260508-backfill/bars.archive`, 350 MB).

## Why predecessor migration validation missed this

The migration plan (`260507-1835-vps-bars-mismatch-tv-pro-fix`) validated by
re-running the bulk 2y resync, then auditing flat/zero-vol percentages —
which look at *closed* bars and were 0.0% across the board. The bug only
manifests in the **incremental cron path** that runs continuously after the
bulk sync finishes. The audit script never observed an in-progress capture
because it ran once, on completed data.

**Lesson 1 — post-migration validation must observe the cron in steady
state**, not just the bulk sync output. A single full audit isn't enough;
let the cron run for ≥ 1 cycle and re-audit.

**Lesson 2 — verify cron must compare full OHLCV with relative thresholds
from day one**, not close-only absolute. Day-one parity should also include
*tick_count* sanity (a partial bar has 10–50 ticks where a full 1m BTC bar
has 500–4000); we deliberately didn't add a Prometheus metric (codebase has
no metrics infra → YAGNI), but `tick_count<50` is a useful invariant that
the next audit script should check explicitly.

## Out of scope (deliberate)

- **Upsert-on-conflict** instead of insert-skip for `bars` (Option C in the
  debug report) — fix-at-source means partial rows never reach the repository
  layer, so the change isn't needed.
- **Full 2y re-sync** — bars before 07:30 UTC on 2026-05-08 were verified
  clean by the migration's post-fix audit; only the regression window needed
  backfill.
- **Prometheus / formal metric** — no metrics infrastructure in the project,
  adding a single counter would be the slippery-slope start of one.

## Follow-ups

- Hot-patch on VPS is ephemeral. After git push to `develop`, CI will rebuild
  `camping89/pocketquant:latest`; the VPS pull restores the durable fix.
- Review divergence-alert log for 7 days; if false-positive rate is non-zero,
  loosen `PRICE_THRESHOLD_PCT` to 0.0005. Untested under low-cap altcoin
  prices — re-evaluate when symbols beyond BTC/ETH are added.
- Cleanup `/tmp/pq-backup-260508-backfill/bars.archive` and
  `/tmp/binance_client_patched.py`, `/tmp/backfill_regression_window.py` on
  VPS after 24h of clean cron cycles.
