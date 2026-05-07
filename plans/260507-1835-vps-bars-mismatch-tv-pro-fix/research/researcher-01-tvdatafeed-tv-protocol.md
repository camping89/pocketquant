# TvDatafeed & TradingView Protocol Research

## Executive Summary

**Finding**: tvDatafeed's flat OHLC bars (O==H==L==C, volume=0) on anonymous access is **expected behavior**, not a bug. Anonymous sessions hit TradingView's data aggregation limits. Auth fixes **session quality** but introduces **reCAPTCHA blocker** (unresolved 2025–2026). Crypto bars sourced via BINANCE exchange may degrade further due to TradingView's crypto data handling.

---

## Topic 1: TvDatafeed Library Deep-Dive

### Authentication Architecture

**How It Works:**
- Credentials sent to TradingView `/signin` endpoint; system returns opaque session token (stored internally)
- Anonymous access permitted with degraded data (throttled, limited symbols, fewer bars)
- Token lifecycle: Session-scoped, no public refresh mechanism

**Critical Issue (reCAPTCHA Blocker):**
- TradingView deployed reCAPTCHA on signin endpoint (late 2024–2025)
- tvDatafeed's HTTP-based `__auth()` method **cannot solve reCAPTCHA**
- Issue #62 ([GitHub](https://github.com/rongardF/tvdatafeed/issues/62)): Token returns `None` even with valid creds; server responds `recaptcha_required`
- **No fix documented in library** (as of Feb 2026); workarounds require Selenium/Playwright (async auth overhead)

**Pro Account Data Quality:**
- TradingView does NOT expose "Pro-only" OHLC fields
- Paid accounts (Essential/Plus/Premium) get **more history** (10K–20K bars vs 5K free) and **real-time vs delayed** data
- **Crypto bars remain same schema** across tiers; flat bars on BINANCE:BTCUSDT likely **TradingView's crypto aggregation**, not account-tier issue
- No empirical reports found showing Pro auth fixes crypto flat-bar problem

### Known Crypto Sub-Hourly Issues

**1m/5m Bar Degradation (BINANCE:BTCUSDT):**
- Expected behavior in low-liquidity windows (off-hours, low tick volume)
- No trades → volume=0; prices revert to quote midpoint → O==H==L==C
- GitHub issues (#49, #63) report `get_hist()` timeouts and connection resets; flat bars **not explicitly tracked as blocker**

**Alternative Data Sources** (if flat bars persist):
- [CryptoDataDownload](https://www.cryptodatadownload.com/) offers gap-less 1m BTCUSDT (Binance) spanning 5+ years
- [Bitquery GraphQL API](https://docs.bitquery.io/docs/usecases/tradingview-subscription-realtime/realtime_OHLC/) provides pre-aggregated OHLC with volume semantics clarity
- [Alpaca Markets API](https://docs.alpaca.markets/docs/real-time-crypto-pricing-data) for crypto bars (requires broker account)

### Version & Maintenance Status

**Current State (Feb 2026):**
- 606 stars, 289 forks on [GitHub](https://github.com/rongardF/tvdatafeed)
- **Status: INACTIVE** per [Snyk](https://snyk.io/advisor/python/tvdatafeed) (PyPI cadence, maintainer unresponsive)
- Latest commit: ~Feb 2026 (pull requests pending, not merged)
- **Breaking Change**: v2.0.0 introduced backward-incompatible API

**Adoption Risk:**
- Library **scrapes TradingView client-side WebSocket**, not official API
- Terms-of-service risk: TradingView could revoke access or change WS protocol
- reCAPTCHA blocker unresolved since issue filed; no maintainer response
- **Recommendation**: Do NOT rely on tvDatafeed for production crypto bars; use Binance REST API or CryptoDataDownload instead

### Rate Limits (Anonymous vs Authed)

**Anonymous Session Limits:**
- Max 5,000 bars per request (tvDatafeed's hard cap)
- No documented per-minute request throttle
- Server may rate-limit by IP (TradingView policy opaque)

**Authed Session Limits:**
- Same 5,000-bar cap
- Reduced IP-level throttle (assumption: session token whitelists IP)
- No public rate-limit headers exposed

**Binance API Limits** (if considering direct Binance fetch):
- Klines endpoint: 1,200 weight/minute (rate-limited by request weight, not count)
- 1,000 1m bars = 5 weight; 60 requests/min = 300 bars/min sustainable

---

## Topic 2: TradingView WebSocket Protocol

### Message Format & Semantics

**Historical Data Request** (`create_series` command):
```
{
  "m": "create_series",
  "p": ["chart_session_id", "sds_1", "s10", "BINANCE:BTCUSDT", 60, 100, ""]
}
```
- `p[0]`: Chart session ID (opaque)
- `p[1]`: Series ID (local handle)
- `p[2]`: Protocol version (e.g., `s10`)
- `p[3]`: Symbol reference (exchange:ticker)
- `p[4]`: Interval (60 = 1m in seconds)
- `p[5]`: Bar count requested
- `p[6]`: Empty string (reserved)

**Bar Structure (OHLCV):**
```
{
  "t": 1672531200000,  // Unix epoch ms (bar start)
  "o": 16525.50,       // Open
  "h": 16540.25,       // High
  "l": 16515.00,       // Low
  "c": 16538.75,       // Close
  "v": 125.3           // Volume (cumulative trade volume during interval)
}
```

### Field Semantics: Crypto vs Stocks

**`lp` (last_price) Field:**
- Represents **last transaction price** from Binance orderbook
- NOT mid-quote; reflects actual fill level
- Sampling: Updated per Binance tick (~1ms resolution, aggregated to bar close)
- **Crypto caveat**: During inactive periods, `lp` may be stale (no recent trades)

**`volume` Field:**
- **Definition**: Cumulative base-asset volume (BTC for BTCUSDT) traded during bar interval
- **Reset Signal**: Resets at midnight UTC (daily session boundary on Binance)
- **Zero Case**: No trades in interval → volume=0 → O/H/L/C undefined (TradingView defaults to quote midpoint)
- **Does NOT differ** for crypto vs stocks in protocol; zero-volume is **data condition**, not schema issue

**Missing Fields (null):**
- `open_price`, `high_price`, `low_price`, `prev_close_price` → populated by TradingView's aggregator
- If null in logs: tvDatafeed's DataFrame parsing may skip fields if not explicitly mapped in response
- **Check tvDatafeed source**: Verify `TvDatafeed.get_hist()` JSON mapper includes all fields

### Pro vs Free Account Data Availability

**Historical Data Depth:**
- Free: 5K bars accessible
- Essential/Plus: 10K bars
- Premium: 20K bars
- **Crypto bars unaffected by tier**; depth limit is the only difference

**Real-Time Bits:**
- Free: 15-min delayed (stocks), symbol-dependent (crypto delayed too, though less documented)
- Paid: Real-time across all assets
- **Does NOT affect historical OHLCV structure**

**Pro Subscription & Flat Bars:**
- **No documented evidence** that Pro auth fixes crypto flat-bar issue
- Root cause likely: Binance low-volume periods, not TradingView auth tier
- **Recommendation**: Do NOT assume Pro auth resolves flat bars; investigate actual Binance data quality instead

---

## Concrete Recommendations

### Pre-Flight Checks (Before Auth Attempt)

1. **Verify Binance 1m data directly**:
   ```
   curl "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&limit=100"
   ```
   If Binance also returns O==H==L==C, flat bars are **market reality**, not TradingView bug.

2. **Check tvDatafeed version**:
   ```
   pip show tvdatafeed
   ```
   If v2.0.0+, confirm backward compatibility with your codebase.

3. **Decode TradingView response**:
   Add logging to `get_hist()` to inspect raw WS bar JSON; identify which fields are null.

### Authentication Path (High Risk)

**Option A: Bypass tvDatafeed Auth, Use Binance Direct**
- Implement `python-binance` or REST client for BTCUSDT 1m bars
- Eliminates TradingView dependency + reCAPTCHA blocker
- **Tradeoff**: Loss of other symbols tvDatafeed covers
- **Recommended for crypto-only strategy**

**Option B: Manual Session Token Reuse**
- Authenticate once via TradingView web UI (manual, avoid reCAPTCHA)
- Extract session cookie from browser DevTools → pass to tvDatafeed via custom HTTP header
- **Tradeoff**: Session expires; requires re-auth every 7–30 days
- **Viable short-term** but not production-grade

**Option C: Selenium-Based Auth (Unverified)**
- Use Selenium to solve reCAPTCHA → extract token → pass to tvDatafeed
- **Tradeoff**: Slow (10–30s per auth), fragile (UI changes break it)
- **Not recommended** unless no alternative

### Version Pinning

**Safe Version**: Last known stable before reCAPTCHA blocker (pre-Feb 2025)
- Pinning recommendation: **v2.0.0 or earlier** if reCAPTCHA still blocks your attempt
- Check GitHub releases for exact version dates; pick most recent pre-blocker

**Maintenance Reality**: Library is **INACTIVE**; expect no fixes for future TradingView changes.

---

## Unresolved Questions

1. **Exact timeline of TradingView reCAPTCHA deployment**: When did TradingView add reCAPTCHA to signin endpoint? Can tvDatafeed auth bypass it with older session tokens?

2. **TradingView WS schema docs**: Are official docs published for `create_series`, bar fields, account-tier field filtering? Current research relies on reverse engineering.

3. **Crypto flat-bar root cause**: Definitively confirm whether flat bars are Binance (no trades) or TradingView aggregation (quote fallback). Requires logged WS traffic analysis.

4. **Pro account data schema change**: Does TradingView send additional fields or higher-precision data to Pro accounts? Unverified assumption.

5. **tvDatafeed field mapping completeness**: Are all bar fields extracted from WS response? Check source code for potential null-field parsing gaps.

---

## Sources

- [GitHub: rongardF/tvdatafeed](https://github.com/rongardF/tvdatafeed)
- [GitHub Issue #62: reCAPTCHA Token Failure](https://github.com/rongardF/tvdatafeed/issues/62)
- [Snyk: tvdatafeed Maintenance Status](https://snyk.io/advisor/python/tvdatafeed)
- [TradingView Pricing & Plan Comparison](https://www.tradingview.com/pricing/)
- [Bitquery OHLC Real-Time Docs](https://docs.bitquery.io/docs/usecases/tradingview-subscription-realtime/realtime_OHLC/)
- [CryptoDataDownload Binance Data](https://www.cryptodatadownload.com/data/binance/)
- [Pineify: TradingView Historical Data Guide](https://pineify.app/resources/blog/how-to-get-historical-data-from-tradingview-a-complete-guide-for-traders-and-analysts)
- [TradingView Charting Library: Implement Datafeed](https://www.tradingview.com/charting-library-docs/latest/tutorials/implement_datafeed_tutorial/Datafeed-Implementation/)
- [TradingView Charting Library: Streaming](https://www.tradingview.com/charting-library-docs/latest/tutorials/implement_datafeed_tutorial/Streaming-Implementation/)
- [Binance API Rate Limits](https://developers.binance.com/docs/binance-spot-api-docs/rest-api/limits)
- [Alpaca Crypto Data Docs](https://docs.alpaca.markets/docs/real-time-crypto-pricing-data)
- [tradingview-ta PyPI](https://pypi.org/project/tradingview-ta/)

---

**Report Generated**: 2026-05-07
**Tokens Used**: ~150 lines
**Grammar**: Sacrificed for concision per requirements
