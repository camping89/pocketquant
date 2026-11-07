---
name: 1d-cascade-followup-plan-advice
description: 2026-11-03 consult on the post-MTF "small plan" (late-1m fold, 1d check, read limit, positions route, TTLCache race, local ports) — decisions advised and the prod evidence behind them
metadata:
  type: project
---

Advised 2026-11-03 for the follow-up plan after `261101-0843-stf-to-mtf-foundation` closed:

- Late 1m fold: add a 7-day cascade (lookback_minutes=10080) to `sync_repair` and `sync_backfill`
  via one `_cascade_all` helper (three callers incl. `sync_1m`); keep `lookback_minutes`, no
  `range_start` param. Drop 5m-1d from the REST repair path (keep them in backfill: insert-only
  deep history). Known bounded side effect: the 1m-history edge bucket of a symbol tracked
  < 7 days gets a partial cascade overwrite of its REST backfill bar.
- 1d check: advised stored-1d vs aggregate-of-stored-1m (self-consistency) in the hourly verify
  job, not REST-vs-stored; removes the Binance REST-1d measurement phase and has no
  newest-bucket race.
- Binance `_invoke_callback`: advised to KEEP the re-raise (one failure in the trader log since
  2026-11-02T08:49Z; swallowing would log per aggTrade at 50-500/s on a persistent bug).
- `TTLCache.get()` in cachetools 7.1.4 freezes its timer (`_TimedCache._Timer` context), so
  `_CACHE.get(key, sentinel)` is race-free; `key in cache` then `cache[key]` is not.

**Why:** Prod worker log 2026-11-02T08:49Z to 11-03 (two repair runs): `integrity.repaired`
6x 1m, 2x 5m; `still_missing` 2x 1m, 2x 5m. So late 1m fills happen every run and the 5m
REST resync (5000 bars, skip_filter) fires on venue-empty gaps it cannot fill. Prod logs are
ANSI-coloured: strip `\x1b\[[0-9;]*m` before grepping `key=value` pairs.

**How to apply:** When the plan phases are reviewed, check these decisions were kept or
consciously reversed; the phase order advised was A (limit + route + cache) -> B (repair
cascade) -> C (1d check), with the local port move outside the repo done first.
