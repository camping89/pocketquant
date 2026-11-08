---
title: "Exness US index CFDs as replacements for ES1!, NQ1!, YM1!"
date: 2026-10-28
author: researcher (read-only)
context: TradingView removal; bars and quotes must come from the broker that executes orders
---

# Exness US index CFDs as replacements for ES1!, NQ1!, YM1!

## 0. Bottom line

- **Verified:** the live Exness account lists the US index CFDs `US500`, `USTEC`, `US30` (and the bigger versions `US500_x100`, `USTEC_x100`, `US30_x10`). `getInstrumentCondition` returns full specs for all of them.
- **Verified:** this account gets **no market data** for them. Every `getCandleHistory` call returned `404 MARKET_INSTRUMENT_NOT_FOUND` (code 4000). That covers all 6 symbols, M1/H1/D1, bid and ask, and every date from now back 12 years. A ticks WS subscribe for them got the frame `{"code": 4000, "error_message": "MARKET_INSTRUMENT_NOT_FOUND"}`. The `XAUUSD` subscription on the same socket was acked with 200 and returned 55 ticks in 45 s.
- **Verified:** every instrument in the `Indices` (15) and `Stocks` (102) categories has `trade_mode: trading_disabled`. The 3 tested (`US500`, `DE30`, `AAPL`) return the same 404 on candles. `trading_disabled` by itself does not block data: `AUDCZK` is also `trading_disabled` and still returns candles.
- **Conclusion (inference from the above):** on the account in `pocketquant-config/vps/default/.env`, Exness **cannot** supply bars or quotes for ES/NQ/YM substitutes today. To use them, Exness has to enable indices on this account, or the project needs a different account or account type. Section 7 lists the questions for Exness.
- Everything below the mapping table describes how the substitutes would behave once data is enabled. It comes from the API specs, the Exness docs, and `XAUUSD` as a stand-in where noted.

## 1. Mapping

| TradingView | Exness symbol (verified name + description) | Bigger contract | Note |
|---|---|---|---|
| `ES1!` (CME E-mini S&P 500) | `US500`, "US SPX 500 Index" | `US500_x100` (contract 100) | data blocked on this account |
| `NQ1!` (CME E-mini Nasdaq-100) | `USTEC`, "US Tech 100 Index" | `USTEC_x100` (contract 100) | data blocked on this account |
| `YM1!` (CBOT E-mini Dow) | `US30`, "US Wall Street 30 Index" | `US30_x10` (contract 10) | data blocked on this account |

- **Verified:** there are no dated or futures-style instruments. None of the 334 names has a month code or expiry. The other index CFDs are `AUS200`, `DE30`, `FR40`, `HK50`, `IN50`, `JP225`, `STOXX50`, `UK100` and `DXY` (`cfd_leverage`).
- **Verified:** the names have no suffix. I also probed `US500m`, `USTECm`, `US30m`, `SPX500`, `NAS100` and `US100`; all returned 404.
- **Verified:** the instrument list is the same 334 names as the spike fixture recorded on 2026-10-13 (`tests/core_test/infra/exness/fixtures/instruments.json`).

## 2. Facts per symbol (verified from `getInstrumentCondition`, 2026-10-28 ~02:30Z)

| Field | US500 | US500_x100 | USTEC | USTEC_x100 | US30 | US30_x10 |
|---|---|---|---|---|---|---|
| category / calc_mode | Indices / cfd | same | same | same | same | same |
| contract_size | 1 | 100 | 1 | 100 | 1 | 10 |
| point_digits | 2 | 2 | 2 | 2 | 1 | 1 |
| volume_min / step / max | 0.14 / 0.01 / 1000 | 0.01 / 0.01 / 20 | 0.05 / 0.01 / 500 | 0.01 / 0.01 / 20 | 0.05 / 0.01 / 500 | 0.01 / 0.01 / 20 |
| margin_percent | 0.0025 | 0.0025 | 0.0025 | 0.0025 | 0.0025 | 0.0025 |
| swap_long / swap_short | -161.5 / 0 | -161.5 / 0 | -652 / 0 | -652 / 0 | -106 / 0 | -106 / 0 |
| triple swap | FRI x3, SAT/SUN 0 | same | same | same | same | same |
| currencies | USD | USD | USD | USD | USD | USD |
| trade_mode | trading_disabled | same | same | same | same | same |

- **Verified:** account settings are currency USD, leverage `1000`, account `trade_mode` `enabled`, `account_status` `active`, `is_demo` false. The account name contains "pro". That it is a Pro account is my inference: the match is a substring and is weak evidence.
- **Verified (Exness docs, "Indices" article, updated 2026-10-05):** these indices have fixed leverage 1:400, which matches `margin_percent` 0.0025. They carry dividend adjustments and swaps, with a triple swap on Friday.
  - Commission: Raw Spread pays 0.125 USD per lot per side on US500 and 0.3125 USD on USTEC/US30. Zero pays 0.25 / 0.625 USD.
  - The doc lists pip size 0.1 for US500/USTEC and 1 for US30.
  - The doc says US500_x100 has a minimum of 0.03 lot; the API says 0.01. The two sources disagree.
- **Not obtained:** the current spread. No ticks or ask candles arrived for these symbols. For comparison, XAUUSD's median tick spread was 0.168 over 55 ticks, the same as the spike's figure.
- **Inferred, not verified:** whether the CFD is priced off the cash index or the futures. The Exness dividend doc says the index price falls on ex-dividend dates. That is how the cash index behaves, while futures already price dividends in.

## 3. Sessions

**From the API (verified):** all 6 symbols return the same 26-segment `trade_sessions` table, in UTC. Every segment reads `trading_disabled`, so on this account the API mode cannot tell open from closed. Only the segment boundaries carry information:
- Sun: 22:00:00 and 22:05:00.
- Mon–Thu: 20:59:00, 21:00:00, 22:00:00 and 22:01:00.
- Fri: 20:55:00.

**From the Exness docs (verified):** the article "Trading Hours Update: End of US Daylight Saving Time (01 Nov 2026)", updated 2026-10-27, gives the schedule for US30, US30x10, US500, US500x100, USTEC, USTECx100 and JP225. Its boundaries match the API split points exactly.

| Day | During US DST (now) | After 2026-11-01 (US standard time) |
|---|---|---|
| Sun | closed until 22:00, close-only 22:00–22:05, open 22:05– | closed until 23:00, close-only 23:00–23:05, open 23:05– |
| Mon–Thu | open –20:59, close-only 20:59–21:00, closed 21:00–22:00, close-only 22:00–22:01, open 22:01– | open –21:59, close-only 21:59–22:00, closed 22:00–23:00, close-only 23:00–23:01, open 23:01– |
| Fri | open –20:55, then closed | open –21:55, then closed |
| Sat | closed | closed |

**CME Globex equity futures:** Sunday–Friday 17:00–16:00 Chicago, with a daily 16:00–17:00 maintenance break. The repo's `cme_globex_calendar_adapter.py` uses this model through `pandas_market_calendars`, and web sources confirm it. Converted to UTC:
- **Summer (CDT, now):** open Sun 22:00Z, break 21:00–22:00Z, close Fri 21:00Z.
- **Winter (CST, from 2026-11-01):** open Sun 23:00Z, break 22:00–23:00Z, close Fri 22:00Z.

**Comparison (inference from the two tables):** both follow US DST.
- The daily break is the same hour.
- Exness adds one close-only minute on each side of the break.
- Exness opens 5 minutes later on Sunday and closes 5 minutes earlier on Friday.
- Holiday schedules differ. Exness publishes its own list in the "Holiday trading hours" article, which I did not read in detail; CME's comes from `pandas_market_calendars`.

## 4. Calendar implications

- **Verified (code):** `ExnessSessionCalendarAdapter` is generic over a `week_sessions` list. It holds sessions in `America/New_York` and merges adjacent enabled segments. That model fits these indices: they follow US DST, so the docs schedule moves +1 h in UTC on 2026-11-01.
- **Verified:** none of the three existing tables (`EXNESS_FX`, `EXNESS_XAUUSD`, `EXNESS_CRYPTO`) matches. FX has no daily break. XAU's break is 20:58–22:00:29 and its Friday close is 20:57:59.
- **Inference:** this needs one new calendar id, for example `EXNESS_US_INDEX`, shared by all six symbols, plus a recorded session table. The table cannot be copied verbatim from this account's API, because every segment says `trading_disabled`. It would have to be re-read once indices are enabled, or built from the docs table above.
- **Open decision:** whether the 1-minute close-only windows count as open. The XAU table treats its close-only window (22:01:30–22:04:59) as `enabled` in the API. Whether bars print during close-only minutes is unverified, because no index data was available.
- **Inference (from code and the spike):** session date and daily bars change meaning.
  - The CME calendar's session date is the next day, because the session opens at 17:00 Chicago the evening before.
  - The Exness calendar uses the UTC date, and its D1 candle opens at 00:00Z (spike, XAUUSD).
  - A strategy or backtest that uses 1d bars would see different daily OHLC than it does on `ES1!`.

## 5. History depth and limits

- **Verified:** `max_candles_per_request` is 1000. `getCandleHistory` allows 2 requests per second, and the account-wide global limit is 10 per second.
- **Verified (spec 1.0.2):** the spec says depth depends on timeframe: S1 1 day, M1/M3 1 year, M5/M10 2 years, M15/M30 3 years, H1 and above "full available history". It also lists timeframes S1–MN and `price_type` `bid`, `ask` or `both`.
- **Verified for XAUUSD, as a stand-in:** a forward probe (`count=+2` from 2000-01-03) returned the first candle for each timeframe, and a backward bisect agreed for M1. The M1 depth here is deeper than the spec's 1 year.

  | Timeframe | First candle |
  |---|---|
  | M1 | 2024-05-01T00:00Z (about 2.5 years) |
  | M5 | 2023-05-01T00:00Z |
  | H1 | 2019-03-25T09:00Z |
  | D1 | 2019-03-25 |

- **Unknown:** depth for the index CFDs; every call returned 404. That they would match XAUUSD is an assumption.
- **Not measured:** gaps around the daily break and the weekend for the indices. With no data, I measured no gaps.

## 6. Differences vs CME futures that matter for strategies and backtests

**Price level and pricing**
- **Inference:** the CFD price is not the futures price. ES normally trades at a carry basis to the cash index, and that basis shrinks to zero at expiry. Price levels, and any rules tied to absolute levels, will not transfer one for one.

**Roll gaps vs swaps and dividends**
- **Verified (TradingView support doc):** continuous `1!` series roll at expiry and are not back-adjusted unless "Adjust for contract changes" (B-ADJ) is turned on.
- **Verified (code):** the repo's TradingView adapter passes `fut_contract` and no adjustment option.
- **Inference:** the stored `ES1!` series is therefore unadjusted, with a quarterly roll gap. Exness CFDs have no roll gap.
- **Verified (docs):** instead, CFDs pay or charge a swap, triple on Friday, and dividend cash adjustments at 22:00 UTC Sunday–Thursday. The index price drops on ex-dividend dates.
- **Inference:** a backtest on CFD bars needs swap and dividend costs to match live P&L. None of these reach the bar series.

**Bid-based candles**
- **Verified (code):** `ExnessAdapter` requests `price_type=bid`. The quote adapter uses bid as `last_price`.
- **Inference:** a long entry fills at the ask, so bid bars understate long-entry cost by the spread. CME bars are trade prices.

**Volume**
- **Verified (code and spike):** Exness `volume` is a tick count. It is not the exchange-traded volume that `ES1!` carries.
- **Inference:** volume-based strategy logic would change meaning.

**Contract units**
- **Verified sizes:** US500 is 1 USD per point, US500_x100 is 100 USD per point, USTEC is 1 USD and US30 is 1 USD per point.
- **Verified (web specs):** ES is 50 USD per point with a 0.25 tick.
- **Not verified this session (known contract specs):** NQ is 20 USD per point and YM is 5 USD.
- `ContractSpec` values for the futures do not carry over.

**Sessions**
- Exness opens Sunday 5 minutes later and closes Friday 5 minutes earlier, and it has close-only minutes (section 3). Holiday calendars differ.

## 7. Open questions

1. Why are Indices and Stocks market data refused on this account? Possible causes are account type (the name contains "pro"), jurisdiction, or Trader API product scope. This needs Exness support or the Personal Area. A demo account of another type could test it.
2. Once enabled, does `trade_sessions` mark the close-only minutes as `enabled`? Do candles print in them?
3. Is the Exness index CFD priced off the cash index or the front futures, and how large is the typical spread by session?
4. What is the index history depth, and is it the same as XAUUSD (M1 from 2024-05-01, H1 from 2019-03-25)?
5. Is the 404 the same on a fresh access point or another account? I tested one account only.

## 8. Side effects and method notes

**Network**
- **Verified:** `*.exness.com` (API, help center, website) is unreachable from this workstation; TLS is reset. `www.exness-api.com` works. All API calls went through a temporary SSH SOCKS tunnel via the prod VPS. The tunnel is now closed and its normalized key copy deleted.
- **Verified:** the Exness help center was read through its Zendesk JSON API, because the HTML page sits behind Cloudflare.

**Read-only scope**
- Calls used were `getLimits`, `getAvailableInstrumentList`, `getInstrumentCondition` (334, once each), `getAccountDetails`, `getCandleHistory` and the ticks WS. No order endpoint was called, and `exness_live_trading` was forced false in the script's settings.

**Rate limits**
- **Verified:** many `429 REQUEST_RATE_LIMIT` retries during the candle run, about 02:20–03:16Z, even at half the published rate.
- **Inference:** prod shares this account's rate budget, so prod's Exness candle sync may have seen extra 429s in that window. I did not check prod logs.

**WS strikes**
- **Verified:** the two rejected WS subscriptions count as strikes under the account-wide WS strike limit (threshold 10, refill 1 per 600 s).
- **Inference:** they had refilled within about 20 minutes.

**Code consequence**
- **Verified (code):** `ExnessQuoteAdapter.subscribe` only checks that the name is in `instruments()`, and `US500` passes. So, if `US500:EXNESS` were mapped today, every reconnect would send a rejected subscribe and add a strike.
- **Inference:** `ExnessAdapter.fetch_ohlcv` would raise `ExnessApiError(404)`. The instrument list is not proof of data access.

**Scratch outputs (no secrets)**
- `C:/Users/evele/AppData/Local/Temp/pq-exness-check/out/` holds `conditions/*.json`, `candles.json`, `controls.json` and `ticks.json`.

## Sources

- Live Exness Trader API on the prod account (read-only), 2026-10-28 02:20–03:20Z.
- Exness OpenAPI 1.0.2: https://www.exness-api.com/exness_api.yaml
- Exness Help Center, "Indices": https://get.exness.help/hc/en-us/articles/17854383867548-Indices
- Exness Help Center, "Trading Hours Update: End of US Daylight Saving Time (01 Nov 2026)": https://get.exness.help/hc/en-us/articles/31342732737180
- Exness Help Center, "Instrument trading hours": https://get.exness.help/hc/en-us/articles/4405235684498-Instrument-trading-hours
- Exness Help Center, "How dividends impact indices": https://get.exness.help/hc/en-us/articles/6546089955996-How-dividends-impact-indices
- TradingView, back-adjustment for continuous futures: https://www.tradingview.com/support/solutions/43000685266-how-can-i-enable-backadjustment-for-continuous-futures/
- CME ES hours (secondary): https://ninjatrader.com/futures/futures-contracts/equity-index/e-mini-s-p-500/
- Repo: `src/pocketquant/core/infra/exness/*`, `src/pocketquant/core/infra/calendars/exness_session_calendar_adapter.py`, `src/pocketquant/core/infra/calendars/cme_globex_calendar_adapter.py`, `docs/journals/2026-10-13-exness-api-spike.md`
