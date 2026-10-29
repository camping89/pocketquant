# Exness API Read-Only Spike: Access Point Routing, Real Limits and Feasibility

**Date**: 2026-10-13
**Severity**: Medium
**Component**: `scripts/exness_spike.py`; fixtures in `tests/core_test/infra/exness/fixtures/`
**Status**: Resolved (feasible; inputs recorded for the Exness market-data and broker phases)

---

## What Happened

The read-only spike ran in the prod container against the Exness Trading API (host `api.exness.com`) on Tuesday 2026-10-13 during FX hours. `fetched_at` was `2026-10-13T09:28:05+00:00`, and ticks were collected for 600 s. It settled assumptions A-i..A-v with real numbers and recorded the redacted fixtures listed below.

It took four deploys to get one clean run. Each failed run exposed an assumption that the published material had stated wrongly or left unstated:

1. **The `access_point` value is a full URL.** `GET /v1/trading/access-point` returns `"access_point": "https://ap-<id>.exness.com"`. The docs example shows a bare host, and the endpoint is missing from `exness_api.yaml` 1.0.2. `allowed_access_point` now accepts either form and returns the bare host. It rejects any other scheme, a port, userinfo, a path, a query or a fragment.
2. **Account endpoints answer only on the access point.** `api.exness.com` returns a bare 404 with no error envelope for every account route: configuration, market data, history and trading. The access point answers all of them. On the access point, a foreign account id returns 403 `AUTH_PERMISSION_DENIED`, not 404. The base host is therefore a discovery endpoint only. The spike now sends every call after discovery to the access point.
3. **The deals window must stay strictly inside `history_age_days`.** `limits` reports `history_age_days: 30` and `history_range_days: 30` for `getDealsHistory` and `getOrdersHistory`. A `from` of exactly now minus 30 days returns 400 `REQUEST_INVALID_TIME_RANGE`, and now minus 29 days returns 200. The spike reads the age from `limits` and subtracts one day.
4. **A 429 can arrive below the published rate.** The third run hit `REQUEST_RATE_LIMIT` on the second M1 candles request. Requests were spaced 0.6 s apart, which is under the published 2 per second. Three read-only replays of the same sequence returned 200 throughout. No response carried a `Retry-After` or rate-limit header. The spike now retries a 429 up to 3 times (1, 2 and 4 s). The clean run needed one retry (`rate_limited_retries: 1`), so the limiter fires below the published numbers in steady state. The trigger is still unverified. The spec says REST limits are "reported for the whole AP cluster"; whether that is the cause is my inference.

---

## Findings

### Transport

- WS subprotocol: `exness-ws-protocol` was accepted on the access point (`ws_host: access_point`). The first frame acknowledges the subscription as `{"id", "code"}`, and tick frames follow as `{"instrument", "bid", "ask", "timestamp"}`.
- `ticks_subscribe_mode: add`. A second `subscribe` message adds instruments to the stream; it does not replace the earlier ones.
- The events WS answers `{"id": "spike-tx", "code": "200"}` to a `transactions` subscription.

### Limits

- `max_candles_per_request`: 1000. A `count=-1000` request returns 1000 candles that end at `from`, so a negative count reads backward.
- `global_account_rate`: 10 per 1 s.
- 2 per 1 s: `getCandleHistory`, `getDealsHistory`, `getOrdersHistory`, `getLimits`, `getAvailableInstrumentList`, `getTradingStateSnapshot`.
- 4 per 1 s: `getAccountDetails`, `getInstrumentCondition`, `placePendingOrder`, `modifyOrder`, `cancelPendingOrder`, `openPosition`, `closePosition`.
- 10 per 1 s: `getOperationStatus`.
- WebSocket: up to 10 active connections, an inbound limit of 50 messages per second per account, 25 tick subscription operations per second, and a strike system of threshold 10 that refills 1 per 600 s.

### Instruments (account currency USD)

| Code | Exness name | contract_size | volume_min | volume_step | point_digits | Sessions (UTC) |
|---|---|---|---|---|---|---|
| XAUUSD | `XAUUSD` | 100 | 0.01 | 0.01 | 3 | Sun 22:01:30 to Fri 20:57:59, daily break Mon–Thu 20:58:00–22:00:29 |
| EURUSD | `EURUSD` | 100000 | 0.01 | 0.01 | 5 | Sun 21:05:00 to Fri 20:58:59, no daily break |
| BTCUSD | `BTCUSD` | 1 | 0.01 | 0.01 | 2 | 24x7 |

None of the names has a suffix. `trade_sessions` holds several contiguous `enabled` segments; the boundaries at 22:01:59/22:02:00 and 22:04:59/22:05:00 are split points, not gaps. A market calendar has to merge adjacent `enabled` segments and treat `trading_disabled` entries as closures.

### Candles (bid)

Every series has `all_aligned: true` on the 24x7 grid, and its last candle is in progress at `fetched_at`.

| Series | Count | First | Last |
|---|---|---|---|
| XAUUSD M1 | 1000 | 2026-10-12T15:47:00Z | 2026-10-13T09:28:00Z |
| EURUSD M1 | 1000 | 2026-10-12T16:47:00Z | 2026-10-13T09:28:00Z |
| BTCUSD M1 | 1000 | 2026-10-12T16:49:00Z | 2026-10-13T09:28:00Z |
| XAUUSD M5, M15, H1, H4, D1 | 10 each | – | 09:25, 09:15, 09:00, 08:00, 2026-10-13 00:00 |

The XAUUSD M1 window starts earlier than EURUSD's because the 1000 bars skip the XAUUSD daily break; this is my inference from the session table. Candles carry a `volume` field, which the spec describes only as "Candle volume".

### Ticks (600 s)

| Code | Ticks | Median spread | Max gap |
|---|---|---|---|
| XAUUSD | 713 | 0.168 | 1.90 s |
| EURUSD | 471 | 0.00006 | 4.30 s |
| BTCUSD | 605 | 4.48 | 1.94 s |

No tick error frames were recorded.

### Deals and account state

- Deal types seen in the last 29 days: `balance` only. The account has no trades yet, so the broker phase's tests must fill `close` deals from the spec schema inside the recorded envelope `{items, has_more, range}`.
- The snapshot holds `account_state`, `orders` (0) and `positions` (0).

### Sizer

With the default `max_exposure_percent` of 0.10, the minimum balance needed to reach one minimum lot is 41,836.06 USD for XAUUSD, 11,178.40 USD for EURUSD and 8,335.82 USD for BTCUSD. The current balance reaches none of them. Live trading is off in this plan, so this only informs tests and docs.

---

## Assumptions

- A-i: confirmed: XAUUSD, EURUSD and BTCUSD exist as CFDs under those exact names with `trade_mode: enabled`.
- A-ii: confirmed: `price_type=bid` works for M1 through D1, and every series is aligned to the bar grid.
- A-iii: confirmed: candles carry a `volume` field (for example 382.0 on an XAUUSD M5 bar). The spec only calls it "Candle volume"; that it is a tick count is my inference, and the strategies do not read it.
- A-iv: confirmed: the spike changes nothing in `src/`; the code metric ratchet exits 0 after every spike commit.
- A-v: changed: the policy (WS ticks live plus REST native-timeframe candles every minute, no cascade) is feasible, with two adjustments. Every call after discovery must go to the access point. The REST poller must space requests by the strictest published rate and absorb a 429 with backoff, because the limiter fires below the published numbers. `getCandleHistory` allows 120 requests per minute, well above the 30 the plan requires.

A-v feasible: yes
access_point: resolved
rest_host: access_point
ws_subprotocol: exness-ws-protocol
ticks_subscribe_mode: add
instrument_names: XAUUSD=XAUUSD, EURUSD=EURUSD, BTCUSD=BTCUSD
sizer_feasibility: XAUUSD=no, EURUSD=no, BTCUSD=no

---

## Stop Conditions Checked

- (a) Every instrument name resolved, so it is clear.
- (b) Every XAUUSD timeframe has `all_aligned: true`, so it is clear.
- (c) `getCandleHistory` allows 120 requests per minute, which is at least 30, so it is clear.
- (d) XAUUSD recorded 713 ticks, so it is clear.
- (e) XAUUSD and EURUSD both have non-empty `trade_sessions`, and every entry has `week_start_time` and `week_end_time`, so it is clear.
- (f) Every XAUUSD series has candles, and M1 ends at 09:28:00, inside the 24 hours up to `fetched_at`. The check command prints `True`, so it is clear.

---

## Fixtures

The fixtures are in `tests/core_test/infra/exness/fixtures/`: `limits`, `account`, `instruments`, `conditions_{XAUUSD,EURUSD,BTCUSD}`, `candles_{XAUUSD,EURUSD,BTCUSD}_M1`, `candles_XAUUSD_{M5,M15,H1,H4,D1}`, `snapshot`, `deals`, `ticks_sample`, `events_snapshot` and `summary`. Identity fields read `REDACTED`, money fields read `0.00`, and the account id is replaced by `0`. The per-account access point host is deliberately left out, because `access_point.json` is not copied.

---

## Follow-up for the Market-Data and Broker Phases

- Route every operation after `getAccessPoint` to the access point; the base URL serves discovery only.
- Read the history age from `limits` and keep the deals window strictly inside it.
- Budget REST calls below the published rate and retry 429 with backoff. Count the retries so the margin can be tuned.
- Build the market calendar by merging contiguous `enabled` session segments.
