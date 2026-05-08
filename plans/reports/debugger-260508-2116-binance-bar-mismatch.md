# Debug Report — Binance Sync Bar Mismatch

**Date:** 2026-05-08 21:16 (Asia/Bangkok) | **Branch:** develop | **Severity:** HIGH (data correctness)

## Executive Summary

Tất cả OHLCV bars (1m + cascaded 5m/15m/1h/4h/1d) trong MongoDB đang **lệch đáng kể với Binance gốc**. 1m bars chỉ chứa data của ~2 giây đầu mỗi phút (snapshot ở thời điểm cron `+2s` chạy), không phải cả phút. Các timeframe cao hơn (cascade từ 1m) thừa hưởng lỗi → toàn bộ market data trên hệ thống đều sai.

**Root cause:** `BinanceClient.fetch_ohlcv` không loại bar in-progress khi gọi `/api/v3/klines`. Cron `sync_1m` chạy ở giây +2 mỗi phút, fetch về 100 bar bao gồm cả bar **đang chạy**, ghi xuống Mongo. Lần cron sau, `filter_new_bars` thấy bar đó đã tồn tại → bỏ qua → partial data nằm vĩnh viễn.

**Fix at source:** Cap `endTime` ở biên closed bar gần nhất hoặc reject bar có `openTime >= floor(now/duration)*duration`.

---

## Evidence

### 1. User-reported discrepancy (15m bar 2026-05-08 09:30 UTC)

| Field | DB | Binance REST | Δ |
|---|---|---|---|
| Open  | 79908.10  | 79908.10  | 0 ✓ |
| High  | 79931.37  | 79934.19  | -2.82 |
| Low   | 79857.95  | 79847.81  | +10.14 |
| Close | 79864.74  | 79863.71  | +1.03 |
| Volume | 6.347   | 88.201    | **-93%** |

> User screenshot DB cũ hơn (O=H=80000.69) — DB đã được update sau đó nhưng vẫn sai.

### 2. 1m bar 2026-05-08 09:30 UTC — smoking gun

| Field | DB | Binance | Notes |
|---|---|---|---|
| Open       | 79908.10 | 79908.10 | match |
| High       | 79908.10 | 79933.58 | DB H == DB O |
| Low        | 79900.03 | 79900.03 | match |
| Close      | 79907.19 | 79931.36 | DB ≈ price tại t≈2s |
| Volume     | 4.81045  | 9.03078  | ~53% |
| tick_count | 286      | 1047     | ~27% |
| created_at | **2026-05-08 09:30:02.581** | — | **2.58s sau bar open** |
| updated_at | **2026-05-08 09:30:02.581** | — | không update lần 2 |

Bar được insert đúng 2.58 giây sau khi bar bắt đầu, sau đó không bao giờ được sửa lại.

### 3. Pattern khắp các 1m bar khác

`tick_count` từ 3–286 (Binance thường 500–1500/phút), `volume` chỉ 0.001–4.8 BTC (Binance ~3–30 BTC), range H-L thường < 0.05 USD trên BTC ~$80k. Đây là footprint của **2-second snapshot**, không phải full minute.

---

## Architecture (verified)

```
┌─────────────────────────────────────────────────────────────────┐
│  WebSocket @aggTrade (BinanceWebSocketClient)                   │
│  → QuoteAppService.on_quote_update                              │
│  → BarAppService.add_tick → BarBuilder (in-memory)              │
│  → on bar close: BarCompletedEvent (NO Mongo write)             │
│  → comment ở bar_app_service.py:119:                            │
│    "cron is the SOLE Mongo writer"                              │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  Cron sync_1m  (*/1 * * * * second=2)                           │
│  → SyncSymbolHandler                                            │
│      → fetch_with_retry → BinanceClient.fetch_ohlcv(n_bars=100) │
│      → filter_new_bars (drops existing by datetime)             │
│      → drop_misaligned_bars                                     │
│      → bar_repo.insert_many (NOT upsert)                        │
│  → cascade_for_symbol (1m → 5m/15m/1h/4h/1d via upsert_bar)     │
└─────────────────────────────────────────────────────────────────┘
```

DI: `BinanceClient` thực sự được wire (`infrastructure.py:35`), không phải mock.

---

## Root Cause Trace

### `BinanceClient.fetch_ohlcv` (binance_client.py:74–101)

```python
now_ms = int(datetime.now(UTC).timestamp() * 1000)
end_time_ms = now_ms

while remaining > 0:
    chunk_limit = min(remaining, _MAX_BARS_PER_CALL)
    start_time_ms = end_time_ms - chunk_limit * bar_duration_ms

    params = {
        "symbol": validated_symbol,
        "interval": binance_interval,
        "startTime": start_time_ms,
        "endTime": end_time_ms - 1,        # ← BUG: chỉ trừ 1ms từ now
        "limit": chunk_limit,
    }
```

Cron fires lúc `09:30:02.000` UTC:
- `now_ms = 1778232602000` (09:30:02)
- `endTime = 1778232601999` (09:30:01.999)
- `startTime = endTime - 100*60_000 = 07:50:01.999`

Binance trả về kline có `openTime ∈ [startTime, endTime]`. Bar 09:30 có `openTime=1778232600000` (09:30:00.000) — **nằm trong khoảng**, được trả về với data của 2 giây đầu (price=79908.10, low=79900.03 nhưng chưa kịp leo lên 79933.58).

### Hệ quả ở `SyncSymbolHandler.handle` (handler.py:67–77)

```python
if not request.skip_filter:
    pre = len(records)
    records = await filter_new_bars(records, ...)   # ← drop bars đã tồn tại
    filtered_existing = pre - len(records)
...
inserted_count = await self._bar_repo.insert_many(records)  # ← INSERT, không UPSERT
```

Lần cron 09:31:02:
- Fetch 100 bars (bao gồm 09:30 closed-but-stale-in-DB và 09:31 in-progress).
- `filter_new_bars` thấy 09:30 đã có trong DB → **drop**.
- Insert chỉ 09:31 (lại là partial 2s).
- 09:30 partial **không bao giờ được sửa**.

### Cascade nhân lỗi

`cascade_for_symbol` aggregate 1m → 5m/15m/1h/4h/1d:
```python
high = max(b.high for b in sorted_bars)
low = min(b.low for b in sorted_bars)
volume = sum(b.volume for b in sorted_bars)
```

Vì 1m source đã bị thu hẹp range + thiếu volume, mọi higher-tf đều thừa hưởng:
- 15m H = max của 15 bar 1m partial → vẫn nhỏ hơn Binance H thật
- 15m volume = sum 15 partial volumes → ~7% Binance

### Tại sao verify cron không catch?

`sync_verify_cascade` (sync_jobs.py:406) so sánh cascade 5m close vs REST 5m close, threshold > 0.01 USD cho > 5% bars. Nhưng:
1. Chỉ so sánh **close**, không so H/L/Volume → nhiều case close gần đúng ngẫu nhiên (DB 79864.74 vs Binance 79863.71, lệch 1.03 nhưng < 0.01? không, vẫn > 0.01) → 5% threshold có thể ngụy trang.
2. Round-robin 1 symbol/giờ → coverage thấp.
3. Chỉ log warning, không trigger fix.

---

## Why migration timing matters

Recent commits (530ed1a → f6998fe) chuyển provider TradingView → Binance. Trước đó TradingView REST có thể có cơ chế khác (snapshot bar ổn định hoặc gọi với endTime cũ). Migration không bù được sự khác biệt này.

---

## Fix Options

### Option A — Cap `endTime` ở biên closed bar (recommended)

```python
# binance_client.py
last_closed_open_ms = (now_ms // bar_duration_ms) * bar_duration_ms - bar_duration_ms
last_closed_close_ms = last_closed_open_ms + bar_duration_ms - 1
end_time_ms = min(now_ms, last_closed_close_ms + 1)  # +1 vì sẽ trừ 1 ngay sau
```

Pros: fix at source, mọi caller đều an toàn, không phụ thuộc cron offset.
Cons: từ chối hoàn toàn in-progress data (bao gồm cả use case "current bar preview" nếu có).

### Option B — Drop in-progress bar tại handler

Filter ở `drop_misaligned_bars` hoặc thêm `drop_in_progress_bars`:

```python
def drop_in_progress_bars(records, interval):
    duration = INTERVAL_SECONDS[interval]
    now_floor = (datetime.now(UTC).timestamp() // duration) * duration
    cutoff = datetime.fromtimestamp(now_floor, tz=UTC)
    return [b for b in records if b.datetime and b.datetime < cutoff]
```

Pros: scope nhỏ, dễ test.
Cons: phải nhớ thêm vào mọi sync path mới.

### Option C — Đổi `insert_many` → `upsert_many` trong `_persist_bars`

Pros: nếu Binance settle muộn, lần cron sau sẽ overwrite partial data.
Cons:
- Vẫn để partial bar nằm DB từ cron đầu tiên cho đến khi cron tiếp theo chạy (ít nhất 1 phút có dữ liệu sai).
- Cần invalidate cascade output sau upsert (nếu không cascade-aggregated values vẫn dùng partial data lần đầu).
- `filter_new_bars` không còn đúng nghĩa, cần review.

### Option D — One-time backfill

Sau khi fix root cause, chạy `sync_backfill` (đã có sẵn, fetches 5000 bars) hoặc tool ad-hoc để **delete + reinsert** mọi bar bị partial. Heuristic detect: `tick_count < threshold` hoặc `H-L < epsilon` hoặc compare-with-Binance.

**Recommend: A + D.** Fix endpoint trước, sau đó backfill toàn bộ data sai.

---

## Verification protocol after fix

1. Deploy fix lên staging hoặc 1 symbol thử nghiệm.
2. Chờ 5 phút, query 1m bars mới → so với `curl https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&limit=5` → phải khớp tuyệt đối O/H/L/C, volume sai số < 0.001 BTC.
3. Mở rộng `sync_verify_cascade` để so sánh **O+H+L+C+V** thay vì chỉ close.
4. Add unit test: `BinanceClient.fetch_ohlcv` với mocked `now` không được trả bar có `openTime >= floor(now/duration)*duration`.

---

## Files involved

- `packages/pocketquant-core/src/pocketquant/core/infrastructure/binance/binance_client.py` (BUG line 87–88)
- `packages/pocketquant-api/src/pocketquant/api/market_data/handlers/sync/sync_one/handler.py` (filter_new_bars + insert_many)
- `packages/pocketquant-api/src/pocketquant/api/market_data/app_services/sync_jobs.py` (sync_1m cron at +2s)
- `packages/pocketquant-api/src/pocketquant/api/market_data/app_services/cascade_aggregator.py` (downstream amplifier)
- `packages/pocketquant-api/src/pocketquant/api/market_data/app_services/quote_app_service.py` + `bar_app_service.py` (live bars in-memory, không liên quan trực tiếp tới bug nhưng giải thích design intent)

---

## Status

**DONE_WITH_CONCERNS**

**Summary:** Root cause = BinanceClient fetch in-progress bar; cron persist; filter_new_bars khóa cứng partial data.

**Concerns:**
1. Toàn bộ historical 1m bars từ ngày bật Binance migration (~2024-05-08 trở đi qua snapshot 2s) **đều có thể sai**. Cần audit + backfill scope rộng.
2. Cascade output (5m–1d) cũng sai theo → strategies / backtests dùng data này có kết quả không tin cậy.
3. Higher TFs có cascade upsert idempotent — sau fix có thể tự sửa nếu 1m source được sửa và rerun cascade.
4. WebSocket @aggTrade path không bị lỗi này (chỉ build in-memory, không write Mongo) — nhưng nếu trong tương lai bật persist từ ws, cần đảm bảo handle bar-close đầy đủ.

## Open questions

1. Có muốn fix endpoint (Option A) hay drop ở handler (B)? A đơn giản hơn nhưng affect any future caller cần in-progress.
2. Backfill scope: chỉ tracked symbols hay tất cả symbols có bar trong DB? Range từ ngày nào?
3. Có cần migration script để **delete partial bars** trước khi backfill, hay dùng upsert?
4. Cron offset hiện tại +2s — sau fix Option A, có muốn giảm xuống +1s để giảm latency không? Hoặc giữ +2s cho an toàn settle?
