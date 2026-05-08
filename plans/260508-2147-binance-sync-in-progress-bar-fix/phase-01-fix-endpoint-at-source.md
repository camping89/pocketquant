---
phase: 1
title: "Fix endpoint at source"
status: completed
priority: P1
effort: "1.5h"
dependencies: []
---

# Phase 1: Fix endpoint at source

## Overview

Sửa `BinanceClient.fetch_ohlcv` (binance_client.py:74-101) để cap `endTime` ở biên closed bar gần nhất, loại trừ bar đang chạy. Single-point fix bảo vệ mọi caller (cron `sync_1m`, manual sync, backfill, sync_verify_cascade).

## Context Links

- Debug report: `plans/reports/debugger-260508-2116-binance-bar-mismatch.md`
- Predecessor migration: `plans/260507-1835-vps-bars-mismatch-tv-pro-fix/phase-01-binance-providers.md`

## Requirements

**Functional:**
- `fetch_ohlcv` không bao giờ trả về bar có `openTime >= floor(now / bar_duration_ms) * bar_duration_ms`.
- Nếu Binance API trả bar in-progress (do clock skew), code MUST drop nó trước khi map sang `Bar`.
- Backwards-compatible signature; không thêm tham số mới.

**Non-functional:**
- Zero performance regression (fix chỉ là 2 dòng arithmetic).
- Test coverage cho edge: clock skew, exact bar boundary, tail of fetch range.

## Architecture

```
fetch_ohlcv(n_bars=100):
  now_ms = current epoch ms
  # NEW: cap endTime ở cuối bar đã đóng
  last_closed_open_ms = (now_ms // bar_duration_ms) * bar_duration_ms
  end_time_ms = last_closed_open_ms - 1   # exclusive: last_closed_open_ms is the IN-PROGRESS bar's openTime

  while remaining > 0:
    chunk_limit = min(remaining, MAX)
    start_time_ms = end_time_ms - chunk_limit * bar_duration_ms
    params = {startTime, endTime: end_time_ms, limit: chunk_limit}
    # NOTE: Binance returns klines whose openTime ∈ [startTime, endTime]
    # endTime now points BEFORE the in-progress bar's openTime → safely excluded
```

**Defense-in-depth:** Sau khi map sang Bar list, filter lần nữa để drop bất kỳ bar nào có `bar.datetime >= floor(now/duration)*duration`. Hai tầng phòng thủ phòng case Binance latency / clock skew lệch ms.

## Related Code Files

**Modify:**
- `packages/pocketquant-core/src/pocketquant/core/infrastructure/binance/binance_client.py` (lines 76-90)

**Create:**
- `packages/pocketquant-core/tests/unit/infrastructure/binance/test_binance_client_in_progress_filter.py` — new dedicated test file

**Read for context (no modification):**
- `packages/pocketquant-core/tests/unit/infrastructure/binance/test_binance_client.py` — extend coverage
- `packages/pocketquant-core/src/pocketquant/core/infrastructure/binance/binance_mappers.py` — INTERVAL_TO_BINANCE map

## Implementation Steps

1. **Read** `binance_client.py` toàn bộ + existing tests để hiểu pattern.
2. **Modify** `fetch_ohlcv`:
   - Tính `last_closed_open_ms = (now_ms // bar_duration_ms) * bar_duration_ms`
   - Set `end_time_ms = last_closed_open_ms` (KHÔNG phải `now_ms`)
   - Giữ `params["endTime"] = end_time_ms - 1` (exclusive boundary). Vậy `endTime` = `last_closed_open_ms - 1`.
   - Thêm comment giải thích "exclude in-progress bar".
3. **Add defense-in-depth filter** sau `kline_to_bar` loop:
   ```python
   cutoff_dt = datetime.fromtimestamp(last_closed_open_ms / 1000, tz=UTC)
   chunk_bars = [b for b in chunk_bars if b.datetime and b.datetime < cutoff_dt]
   ```
4. **Write unit tests:**
   - `test_fetch_ohlcv_excludes_in_progress_bar` — mock `datetime.now` to mid-bar; verify only closed bars returned.
   - `test_fetch_ohlcv_at_exact_bar_boundary` — `now = bar_open_ms`; verify previous bar included, current excluded.
   - `test_fetch_ohlcv_with_clock_skew_binance_returns_in_progress` — mock httpx returning kline with `openTime > cutoff`; verify defense filter drops it.
   - `test_fetch_ohlcv_pagination_consistency` — n_bars=1500 over 2 chunks; verify no duplicate / missing bars.
5. **Run tests:** `just test-pkg core` — confirm new tests pass and existing 30+ tests in test_binance_client.py vẫn pass.
6. **Linting:** `just lint` (ruff) — fix any issues.
7. **Compile check:** Import the module via `python -c "from pocketquant.core.infrastructure.binance.binance_client import BinanceClient"` — no syntax errors.

## Todo List

- [ ] Read existing `binance_client.py` + `test_binance_client.py`
- [ ] Modify `fetch_ohlcv`: tính `last_closed_open_ms`, set `end_time_ms`, update `params["endTime"]`
- [ ] Add defense-in-depth filter sau kline mapping
- [ ] Write 4 unit tests (in-progress exclude, exact boundary, clock skew, pagination)
- [ ] Run `just test-pkg core` → all pass
- [ ] Run `just lint` → clean
- [ ] Compile import smoke check
- [ ] Commit: `fix(binance): exclude in-progress bar from fetch_ohlcv`

## Success Criteria

- [ ] All existing `test_binance_client.py` tests pass
- [ ] 4 new unit tests pass
- [ ] `fetch_ohlcv` returns 0 in-progress bars cho mọi `n_bars`, mọi interval, mọi `now`
- [ ] No diff in performance (test runtime ±5%)
- [ ] Linting clean

## Risk Assessment

| Risk | Mitigation |
|---|---|
| Off-by-one ở boundary (bar đúng lúc đóng) | Test `test_fetch_ohlcv_at_exact_bar_boundary` cover |
| Pagination khi n_bars > 1000: end_time_ms slide window có khả năng include in-progress lần đầu | `last_closed_open_ms` chỉ tính 1 lần ở đầu, không re-tính trong loop → an toàn |
| Misalignment với existing `drop_misaligned_bars` filter ở handler | Filter ở handler check alignment trên bar boundary; defense filter ở client check time cutoff. Hai tầng độc lập, không xung đột. |
| Test mock `datetime.now` không cover all timezones | Code dùng `datetime.now(UTC)` → chỉ test UTC scenarios; đủ |

## Security Considerations

- Không liên quan auth/authz.
- Không log credentials.
- Không thay đổi rate limit logic.

## Next Steps

→ Phase 02: Backfill regression window (depends on this fix being deployed)
