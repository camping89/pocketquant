---
name: parallel-exness-only-direction
description: Owner decisions 2026-10-28 (stronger machine, true multi-core, TradingView deprecated, ES/NQ/YM to move to Exness US500/USTEC/US30) and the reanalysis verdict: drop the CME bisect, worker split first, Exness index data is 404 on the account
metadata:
  type: project
---

Owner decisions (2026-10-28): the prod machine will be stronger; the owner wants true multi-core parallelism, not a cheaper single loop; TradingView is deprecated and bars/quotes must come from the broker that executes orders; ES/NQ/YM are to become Exness `US500/USTEC/US30`.

Reanalysis verdict (`plans/reports/kongming-261028-1020-parallel-exness-only-reanalysis.md`): the CME calendar bisect is dropped as throwaway; do the loop-lag probe + skip-listener fix now; land `worker` (scheduler + jobs) as a separate process first with `app` = api + trader, split api from trader only on probe evidence; one worker, no process pool, no symbol sharding; free-threaded 3.14t rejected again (`httptools` has no cp314t wheel in uv.lock; money-path state is loop-confined; no CPU-bound job survives TV removal).

Verified blockers and prod facts:
- Exness returns 404 `MARKET_INSTRUMENT_NOT_FOUND` for every Indices/Stocks candle and tick on the prod account (researcher report 261028-0920); `US500/USTEC/US30` cannot be mapped until that changes, and mapping them early would take a WS strike per reconnect.
- Prod logs 7 days to 2026-10-28: Exness WS reconnects cluster at 00h/12h UTC (the `sync_repair` stall windows) and Binance WS at 00h/12h too; all 4 `exness_ws.circuit_breaker_open` and 47 of 72 Exness 429 retries fell inside the researcher's read-only probe window (02:20-03:20Z) on the same account. Correlation only; mechanism unknown.
- Live trading disarmed since 2026-10-22; go-live Phase 11 called off (no profitable strategy); only paper runs exist (two BTCUSDT 1m, one ES1! 15m `01a178ef`).

**Why:** the earlier review (`kongming-261028-0848`) optimised for 2 vCPU + GIL + TradingView; the owner rejected that framing.

**How to apply:** do not re-propose the bisect, threads, process pools or sharded workers. Treat the Exness account's REST budget and WS strike budget as the scarce resources after TV removal. Never run a second Exness client (scripts, local dev with WS) against the prod account while the trader runs. Deleting `ES1!:TRADINGVIEW` cascades the `01a178ef` paper subscription; the owner must confirm that explicitly (supersedes the older "never stop/delete" note once TV removal is scheduled).
