---
title: "VPS bars mismatch TradingView — root cause + TV Pro migration"
date: 2026-05-07 18:35 +07
slug: vps-bars-mismatch-tv-pro-fix
status: design-approved
type: brainstorm
related:
  - plans/260506-1959-realtime-quote-bar-pipeline/plan.md
  - plans/260507-1626-1m-historical-backfill-from-binance/plan.md
  - plans/reports/brainstorm-260507-1626-1m-historical-backfill-tv-cap.md
---

# Brainstorm — VPS bars mismatch TradingView

## Problem statement

User report: VPS chart hiển thị OHLCV không khớp giá BTCUSDT thực trên TradingView, dù pipeline đã poll từ TradingView client. Cần root cause + remediation.

## Forensic evidence collected

### Live comparison `2026-05-07T11:36:00 UTC` (BINANCE:BTCUSDT, 1m)

| Field | VPS (TV REST cron) | Binance API ground truth | Δ |
|---|---|---|---|
| Open | 80964.53 | 80964.53 | ✅ |
| High | 80964.53 | 80964.54 | flat |
| Low | 80964.53 | 80938.14 | **−$26** |
| Close | 80964.53 | 80938.15 | **−$26** |
| Volume | 0.0 | 3.18 BTC | **−100%** |

10/10 bars gần nhất từ VPS có `O=H=L=C` và `volume=0`. Bars là rác, không phải candles thật.

### Live in-progress bar (WS-built) `11:38:00`

```
VPS:     O=80937.29  H=80958.48  L=80937.28  C=80958.47  vol=63558.98 (14 ticks)
Binance: O=80937.29  H=80961.48  L=80937.28  C=80955.17  vol=4.71
```

OHLC sai lệch nhỏ (sampled lp). Volume sai 13,500x.

### Last-price snapshot

```
VPS quote.last_price = 80958.47   ✅
TV website          = 80,958.48   ✅
```

Quote tức thời ĐÚNG. Discrepancy nằm ở bar aggregation, không phải feed price.

### Config audit

```env
# TRADINGVIEW_USERNAME=
# TRADINGVIEW_PASSWORD=
```

→ Anonymous mode (`tradingview_client.py:50-52`).

## Root causes (3 lỗi độc lập)

### Bug #1 (CRITICAL) — `tvDatafeed.get_hist()` trả flat OHLC cho crypto 1m

- Anonymous TV session + crypto pair + sub-hourly tf → TV WebSocket back-channel chỉ gửi 1 datapoint/bar (open price), volume=0
- Cron `sync_1m` ghi rác vào Mongo mỗi phút từ khi pipeline live
- Cascade aggregator (5m/15m/1h/4h/1d) build trên rác → mọi tf bị nhiễm
- 5m/15m bars có range tương đối hẹp (chênh giữa "open" prices), volume=0 vĩnh viễn

### Bug #2 (HIGH) — `BarBuilder` cộng dồn cumulative volume

`bar_builder.py:79-80`:

```python
if volume is not None:
    self.volume += volume   # ❌
```

`quote.volume` từ TV WS là cumulative session volume. Mỗi tick cộng full snapshot → bar volume = `sum(cumulative snapshots)` = rubbish (~13,500x giá trị thực).

### Bug #3 (MEDIUM, by-design limit) — WS sample `lp` ~1 Hz

TV WS gửi `lp` 1 Hz, không phải mỗi trade. → 14-18 ticks/phút thay vì hàng trăm trades. → H/L underestimate intra-second extremes.

### Bug #4 (LOW, false comfort) — Integrity check value-blind

`/integrity/check` count rows, không validate values. `missing_count: 0` while bars rác → false sense of completeness.

## Approaches evaluated

### Approach A — Binance public REST cho crypto historical
- Effort 4-6h. Promote backfill script thành full IDataProvider.
- Pros: Free, real OHLCV+volume, code mẫu sẵn.
- Cons: Crypto-only, cần routing theo exchange.

### Approach B — TradingView Pro account auth ✅ CHOSEN
- Effort 30min config + recurring cost ($14.95/mo).
- Pros: Vendor-agnostic; cùng path cho crypto/stocks/forex.
- Cons: tvDatafeed unofficial → breaking risk; **chưa empirically verify Pro fix flat-bar bug crypto 1m**.
- Risk: Nếu TV Pro không fix Bug #1, không có fallback (vì user chọn xoá Binance code).

### Approach C — Fix Bug #2 + Binance WS direct
- Bỏ qua Bug #1 historical, chỉ fix live bars.

### Approach D — Hybrid (A + Binance WS)
- Toàn diện, scope lớn nhất.

## Final decision

**Approach B + Bug #2 fix + Minimal IDataProvider abstraction**

User decisions:
- ✅ Migrate sang TV Pro auth, **xoá hoàn toàn Binance script + test** (no verify gate)
- ✅ Fix Bug #2 (volume) trong cùng plan
- ✅ Generic IDataProvider — minimal scope (interface + TV impl, no router/fallback chain)
- ⏳ Legacy backfill quyết sau khi audit % nhiễm

## Recommended solution — phased plan

### Phase 1 — TV Pro auth + cleanup Binance (~1h)

- Set `TRADINGVIEW_USERNAME/PASSWORD` trong VPS `.env`
- Xoá `pocketquant/scripts/backfill_1m_from_binance.py` + `pocketquant/scripts/__init__.py`
- Xoá `pocketquant/tests/scripts/test_binance_kline_mapping.py`
- Update `pocketquant/pyproject.toml` (revert `testpaths`/`pythonpath` nếu chỉ cho Binance test)
- Update docs references (deployment-guide, codebase-summary, project-changelog)
- Restart API → verify fresh `sync` returns proper OHLCV

### Phase 2 — Fix Bug #2 (volume aggregation) (~1.5h)

**Approach:** Track `volume_baseline` per (symbol, interval) khi bar mở. Bar volume = `latest_quote.volume - baseline` (cumulative diff).

**Files:**
- `pocketquant-core/src/pocketquant/core/domain/bar/services/bar_builder.py` — change `add_tick(price, volume, ts)` → `add_tick(price, cumulative_volume, ts)`; logic: nếu `bar.open is None` → set `_volume_baseline = cumulative_volume`; else `bar.volume = cumulative_volume - _volume_baseline`. Reset baseline on session boundary (00:00 UTC).
- `pocketquant-api/src/pocketquant/api/market_data/app_services/bar_app_service.py` — propagate raw cumulative volume tới builder.
- Tests: `pocketquant-core/tests/unit/domain/bar/services/test_bar_builder.py`

**Edge cases cần handle:**
- Session reset (cumulative volume rolls back to 0 at 00:00 UTC) — detect bằng `current < baseline`
- First tick of new bar → baseline = cumulative
- Negative diff (rare TV quirks) → clamp to 0

### Phase 3 — Minimal IDataProvider interface (~1h)

**Files:**
- `pocketquant-core/src/pocketquant/core/infrastructure/tradingview/base.py` — đã có `IDataProvider` Protocol; verify `TradingViewClient` properly implements
- DI provider — không thay đổi (đã wire `TradingViewClient` qua interface)
- Document trong `docs/system-architecture.md`: provider chain extension point

KHÔNG build router/fallback. Chỉ ensure clean abstraction để future thêm provider không phải refactor lớn.

### Phase 4 — Audit legacy data nhiễm (~30min)

**Script:** `pocketquant/scripts/audit_bar_quality.py` — query Mongo, đếm:
- Bars có `O==H==L==C` per (symbol, exchange, interval)
- Bars có `volume == 0`
- Bars có `volume > sane_threshold` (vd. 1m BTC > 1000 = abnormal)
- Output % nhiễm per tf, per date range

**Decision matrix sau audit:**
- < 1% nhiễm → ignore, fix forward
- 1-10% → re-sync targeted ranges via authed TV
- > 10% → mass re-sync với rate limiting; cascade re-aggregate higher tfs

### Phase 5 — (Conditional) Re-sync legacy bars

Chạy sau Phase 4. Có thể skip nếu audit cho thấy không đáng.

## Implementation considerations & risks

| Risk | Mitigation |
|---|---|
| TV Pro auth KHÔNG fix Bug #1 cho crypto 1m | Phase 1 verify ngay bằng test fetch. Nếu fail → revert commit, restore Binance, escalate. |
| `tvDatafeed` library breaking change | Pin version trong `pyproject.toml`; monitor GitHub issues. |
| TV ban scrapers | Implement exponential backoff; respect rate limits; có fallback plan tài liệu hoá. |
| Volume baseline drift across UTC midnight | Unit test cho session reset case; manual verify đầu ngày tiếp theo. |
| Cascade aggregator vẫn output 0-volume cho 5m/15m | Sau khi 1m fixed, cascade tự correct (sum proper 1m volumes). |
| Backfill of legacy bars overwrite WS in-progress | Use `insert_many(ordered=False)` — unique index dedup; explicit `delete` only for confirmed garbage windows. |

## Success metrics

- 95%+ 1m bars có `H > L` (range > 0)
- 95%+ 1m bars có `volume > 0`
- Live in-progress bar volume sai số <5% so với Binance API tại bar close
- VPS chart visually match TradingView reference chart (no flat candles in chart UI)
- Cascade 5m bars match `tvDatafeed.get_hist(5m)` within $0.01 tại 95%+ samples

## Validation criteria

- [ ] Phase 1: After TV Pro creds set, `curl /api/v1/market-data/sync` → response shows bars with `H>L` for at least 90% of returned bars
- [ ] Phase 2: Unit tests cover normal, session-reset, negative-diff cases
- [ ] Phase 2: Live in-progress 1m bar volume tại VPS endpoint match Binance API ±5%
- [ ] Phase 3: Codebase-summary doc updated; provider extension point documented
- [ ] Phase 4: Audit report saved tới `plans/reports/audit-260507-bar-quality.md`
- [ ] Phase 5 (if executed): Integrity check + spot-check 10 random bars match Binance ground truth

## Next steps & dependencies

- **Immediate:** User cung cấp TV Pro credentials → set `.env` trên VPS
- **Plan creation:** `/ck:plan --fast` với context từ brainstorm này (slug `vps-bars-mismatch-tv-pro-fix`)
- **Order:** Phase 1 → 2 → 3 → 4 → (conditional) 5
- **Dependencies:** Plan 260506-1959 (realtime pipeline) là tiền đề; plan 260507-1626 (Binance backfill) sẽ bị deprecated trong Phase 1

## Unresolved questions

1. TV Pro session token có rotate không? Cần handle re-auth flow nếu session expire.
2. Volume baseline reset detection: dùng UTC midnight cứng hay detect by `current < previous` heuristic? Heuristic an toàn hơn cho exchanges có session khác.
3. Có nên expose audit results vào monitor UI banner (như "Data quality: 96%") không? — out of scope hiện tại nhưng đáng cân nhắc cho trust.
4. Stocks/forex symbols trong tương lai: TV Pro cùng credentials dùng được cho mọi asset class hay cần thêm subscriptions? Verify với TV pricing page.
