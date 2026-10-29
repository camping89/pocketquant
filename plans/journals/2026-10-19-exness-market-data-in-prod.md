# Exness Market Data in Prod: Two Pre-existing Defects Surfaced by the Verify

**Date**: 2026-10-19
**Severity**: Medium
**Component**: `core/infra/exness/`, `core/infra/calendars/exness_session_calendar_adapter.py`, `engine/market_data/app_services/integrity_jobs.py`, `core/common/tracing/request_logging.py`
**Status**: Resolved (prod on master `7c3ca77`, live trading off)

---

## What Happened

`XAUUSD:EXNESS`, `EURUSD:EXNESS` and `BTCUSD:EXNESS` were seeded in prod and sync through develop's existing jobs. They stream live ticks over the Exness WS. This was the first release under the master-only deploy model: develop CI ran tests, then a fast-forward of `master` deployed. It took two releases, because the prod verify caught two defects that the unit tests had missed.

1. **A 1000-bar sync stored 999.** `ExnessAdapter` anchored its first candle page at the current time. During market hours that page therefore carried the in-progress candle. The adapter counted the candle against the request, then dropped it. Every later page also re-counted its inclusive boundary candle. Pages now end one second before the bar in progress, and then one second before the oldest bar fetched. A direct in-container call returned exactly 1000 unique bars.
2. **The quote SSE sent nothing, for every provider.** `RequestLoggingMiddleware` buffered the whole body of any response whose path was not on a one-entry list. Only the bars stream was on it. The endless quote stream was therefore held back until the client disconnected; not even headers left. Redis already held fresh `quote:latest:*:EXNESS` keys, so the inbound path worked. The middleware now passes any `text/event-stream` response through unread.

A code review before the first release found a third defect: `check_integrity` counted today's unfinished D1 bar as missing on every calendar, and CME's 02:00 4h bar too. The `CRYPTO_24_7` calendar hid it, because the cascade stores a partial daily bar. It now stops expected instants at the calendar's own bar in progress.

---

## Decisions Recorded

- Sessions are held in `America/New_York`. The recorded UTC tables were shifted by the EDT offset of their recording date (2026-10-13). From 2026-11-01 the UTC edges move one hour later without a code change.
- Exness weeks open on Sunday 00:00Z, verified by a prod W1 read. `BTCUSD:EXNESS` has its own `EXNESS_CRYPTO` calendar for that reason, and its 1d comes from REST only.
- `periods_per_year` counts bar opens in a reference week. FX prints 6 daily bars a week (Sunday evening has its own) and 1 weekly. Dividing open hours gave about 260 and 37.
- The code-metrics ceiling moved to the measured `tiny_share 0.4877` and `delegations 87`, by the user's decision, rather than contorting the new port members.

---

## Lessons

- A plan's prod verify must test the property, not a count that grows with time. `total_bars >= 1000` would have passed a minute later through accrued bars. The direct `len(fetch_ohlcv(..., 1000)) == 1000` check is what proves the fix.
- A route allow-list for "do not buffer this" fails silently for the next route. Judge by the response instead.
- The full local suite needs Docker Desktop running; without it, 109 testcontainers suites error at setup.
