---
phase: 3
title: "Harden verify cron"
status: completed
priority: P2
effort: "1.5h"
dependencies: [2]
---

# Phase 3: Harden verify cron

## Overview

Mở rộng `sync_verify_cascade` để compare full OHLCV (không chỉ close), tighten threshold, tăng coverage. Mục tiêu: catch regression tương tự (in-progress bar capture, volume drift, H/L truncation) trong 1 cron cycle.

## Context Links

- Existing job: `packages/pocketquant-api/src/pocketquant/api/market_data/app_services/sync_jobs.py` (sync_verify_cascade, lines 406-545)
- Phase 02 phải xong để verify chạy trên data clean

## Requirements

**Functional:**
- Compare cả O/H/L/C/V giữa cascade-stored bars và REST ground truth.
- Per-field threshold (price vs volume khác nhau):
  - `O/H/L/C`: lệch > **0.01% relative** → divergence (BTC $80k → $8; ETH $3k → $0.30; scale theo asset)
  - `V`: lệch > **5% relative** → divergence
- Alert trigger: > **5% bars divergent** trong sample (giữ nguyên)
- Coverage: TẤT CẢ tracked symbols, không round-robin (vẫn chạy hourly).
- Alert format: `cascade.divergence_alert` log với field-level breakdown để debug nhanh.
- **Replace** logic hiện tại (`abs(close - close) > $0.01 absolute`, close-only) — không scale theo asset, miss H/L/V drift.
- Optional: Push alert qua Redis pub/sub channel `alerts:market_data` (defer nếu chưa có alert infra).

**Non-functional:**
- Verify cron không vượt quá 30s wallclock (tránh chèn `sync_1m`).
- Rate limit safe: 6 symbols × 12 bars × 1 call/symbol = 6 calls. OK.

## Architecture

```
sync_verify_cascade (every hour, second=0):
  for ts in tracked_symbols:                      # MOI symbol, không round-robin
    rest_bars = provider.fetch_ohlcv(MINUTE_5, n=12)
    db_bars   = bar_repo.find(MINUTE_5, ...)
    for rest_b, db_b in zip_by_datetime:
      check open delta:  abs(rest.open  - db.open ) / rest.open  > 0.0005
      check high delta:  abs(rest.high  - db.high ) / rest.high  > 0.0005
      check low  delta:  abs(rest.low   - db.low  ) / rest.low   > 0.0005
      check close delta: abs(rest.close - db.close) / rest.close > 0.0005
      check vol  delta:  abs(rest.volume - db.volume) / rest.volume > 0.05
      if any divergent: log + counter++
    if counter / compared > 5%: cascade.divergence_alert
```

**Refactor:** Extract `_compare_bar_fields(rest_bar, db_bar) -> dict[str, bool]` thành pure function để unit test dễ.

## Related Code Files

**Modify:**
- `packages/pocketquant-api/src/pocketquant/api/market_data/app_services/sync_jobs.py` — `sync_verify_cascade` function

**Create:**
- `packages/pocketquant-api/tests/unit/market_data/test_sync_verify_cascade.py` — unit tests cho new comparison logic

**Read for context:**
- Phase 1's `binance_client.py` — provider behavior

## Implementation Steps

1. **Read** `sync_verify_cascade` hiện tại để hiểu flow.
2. **Extract** comparison vào pure function:
   ```python
   PRICE_THRESHOLD_PCT = 0.0001  # 0.01% — BTC $80k → $8; ETH $3k → $0.30
   VOLUME_THRESHOLD_PCT = 0.05   # 5%

   def _compare_bar_fields(rest_b: Bar, db_b: Bar) -> dict[str, bool]:
       def diff_pct(a, b):
           return abs(a - b) / a if a else 0.0
       return {
           "open":  diff_pct(rest_b.open,   db_b.open)   > PRICE_THRESHOLD_PCT,
           "high":  diff_pct(rest_b.high,   db_b.high)   > PRICE_THRESHOLD_PCT,
           "low":   diff_pct(rest_b.low,    db_b.low)    > PRICE_THRESHOLD_PCT,
           "close": diff_pct(rest_b.close,  db_b.close)  > PRICE_THRESHOLD_PCT,
           "volume": diff_pct(rest_b.volume, db_b.volume) > VOLUME_THRESHOLD_PCT,
       }
   ```
3. **Replace round-robin với loop tất cả symbols:**
   - Remove `_verify_cascade_counter` global
   - Iterate `tracked` instead
4. **Update divergence detection:**
   - Mỗi bar comparison: track per-field divergence
   - Aggregate: divergence_count = bars có ANY field divergent
   - Alert when `divergence_count / compared > 0.05`
5. **Enrich log payload:**
   ```python
   logger.warning(
       "cascade.divergence_alert",
       symbol=symbol, exchange=exchange,
       divergence_count=divergence_count, compared=compared,
       sample_divergences=[
           {"datetime": b.datetime.isoformat(), "fields": fields_diff}
           for b, fields_diff in samples[:3]  # first 3 for debugging
       ],
   )
   ```
6. **Write unit tests:**
   - `test_compare_bar_fields_no_diff` — identical bars → all False
   - `test_compare_bar_fields_open_divergent` — open differs > threshold
   - `test_compare_bar_fields_volume_divergent` — volume +10% → True
   - `test_compare_bar_fields_within_tolerance` — open differs but < 0.05% → False
7. **Run tests:** `just test-pkg api`
8. **Local smoke test:** invoke verify_cascade manually với cleaned DB → expect 0 divergence alerts.

## Todo List

- [ ] Read existing `sync_verify_cascade`
- [ ] Extract `_compare_bar_fields` pure function với threshold constants
- [ ] Replace round-robin với all-symbols loop
- [ ] Enrich divergence log payload với per-field breakdown
- [ ] Write 4 unit tests
- [ ] `just test-pkg api` pass
- [ ] Local smoke test → 0 alerts on clean data
- [ ] Commit: `feat(market-data): harden cascade verify with full OHLCV comparison`

## Success Criteria

- [ ] All existing sync_jobs tests pass
- [ ] 4 new unit tests pass
- [ ] Verify cron runs <30s wallclock cho 6 tracked symbols (measure trên VPS)
- [ ] Local smoke test: 0 divergence alerts on backfilled clean data
- [ ] Manual injection test: artificially modify 1 DB bar → next verify cycle alerts với field breakdown

## Risk Assessment

| Risk | Mitigation |
|---|---|
| Threshold 0.01% quá nhạy → noise alerts | Phase 4 docs ghi note; review sau 7 ngày baseline (xem rates of false positive trên log); nếu cần loosen lên 0.05% |
| All-symbols loop làm cron chạy quá lâu | Measure trên VPS; fallback: vẫn round-robin nhưng compare full OHLCV |
| Volume threshold 5% sai cho low-cap altcoin | Hiện tại tracked symbols là BTC/ETH/major coins → 5% OK; revisit khi add altcoin |
| Verify cron chạy lúc cron sync_1m → contention | Sync_verify_cascade run hourly at second=0; sync_1m at second=2. Khác phase, không xung đột. |

## Security Considerations

- Không liên quan auth/data sensitive.

## Next Steps

→ Phase 04: Docs sync + journal
