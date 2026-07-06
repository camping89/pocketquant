# Brainstorm — `engulfing_pullback30_touch` strategy variant

- **Ngày:** 2026-07-06
- **Chủ đề:** Biến thể của `engulfing` — chờ pullback 30% body của bar engulfing rồi mới vào lệnh.
- **Cờ:** không (`--html`/`--wiki` không dùng).
- **Trạng thái:** Design đã duyệt, sẵn sàng bàn giao `/ck:plan`.

## Problem statement

Strategy `engulfing` hiện vào lệnh **ngay tại close của bar engulfing**. Người dùng muốn một biến thể vào giá tốt hơn: bỏ qua entry tại bar engulfing, chờ bar kế tiếp; nếu giá thoái lui (pullback) 30% body của bar engulfing thì mới vào. Giữ nguyên bản gốc.

- Body = `|close − open|` của bar engulfing.
- 30% = thoái lui 30% từ close về phía open.

## Quyết định (đã chốt với người dùng)

| Trục | Chốt |
|---|---|
| Mô hình thực thi | **A — Market tại close bar N+1** (state machine thuần, không đụng broker) |
| Trigger pullback | **Chạm intrabar** — `low(N+1) ≤ level` (LONG) / `high(N+1) ≥ level` (SHORT) |
| Cửa sổ chờ | **Chỉ đúng bar kế tiếp**; không chạm → huỷ setup |
| Tên | `engulfing_pullback30_touch` |
| Guard SL | `low(N+1) ≤ SL` (LONG) → **skip** (chạm SL trong bar = coi như bị quét stop) |

## Approaches đã cân nhắc

### Execution model
- **A — Market @ close(N+1)** ✅ chọn. Ưu: khớp engine hiện tại, gói gọn 1 file strategy + 1 dòng registry, zero rủi ro pending-order. Nhược: giá khớp = close(N+1), không phải đúng mức 30%.
- **B — LIMIT @ đúng mức 30%.** Ưu: giá vào đúng mức pullback, SL sát, đúng ý đồ sách vở. Nhược: vòng đời limit + expiry sau 1 bar không khớp gọn với contract strategy (strategy không giữ broker handle; `expire_pending_orders` chỉ chạy cuối run) → nhiều mảnh động, rủi ro pending treo. Để dành nâng cấp sau.

### Cấu trúc code
- **Class standalone mới** ✅ chọn — giữ bản gốc bất khả xâm phạm, dùng lại pure `detect_engulfing`, phần trùng nhỏ (~40 dòng SL/TP).
- Subclass / parameterize bản gốc — DRY hơn nhưng thêm nhánh vào strategy đang được tin dùng, rủi ro regression; registry map code→class nên vẫn cần entry riêng.

## Recommended solution

Class `EngulfingPullback30TouchStrategyService` (file `engulfing_pullback30_touch_strategy_service.py`), đăng ký code `engulfing_pullback30_touch` trong `STRATEGY_REGISTRY`.

### State machine (1 vị thế/lần)

```
Bar N — engulfing đạt filter (direction + rejection_wick ≤ max):
    ARM state {direction, open_N, close_N, pullback_level, sl_anchor, key_level}
    KHÔNG phát signal.

Bar N+1:
    LONG :  low(N+1)  ≤ pullback_level  và  low(N+1) > SL      → LONG  market @ close(N+1)
    SHORT:  high(N+1) ≥ pullback_level  và  high(N+1) < SL     → SHORT market @ close(N+1)
    ngược lại → huỷ setup, reset.
```

### Công thức

- `pullback_pct` = tham số, default `0.30`.
- **LONG** (bullish): `level = close_N − pullback_pct × (close_N − open_N)`; trigger `low(N+1) ≤ level`.
- **SHORT** (bearish): `level = close_N + pullback_pct × (open_N − close_N)`; trigger `high(N+1) ≥ level`.

### SL/TP (neo theo pattern như gốc; entry thấp hơn → risk co lại → R:R tốt hơn)

- **LONG:** `pattern_low = min(low_N, low_prev)`; `SL = pattern_low×(1−sl_buffer_pct)`; `risk = entry − SL`; `TP = max(entry + risk, max(key_highs))`.
- **SHORT:** mirror.
- Key-level window snapshot tại **bar N** (lúc detect).

### Guard
- **Skip nếu chạm SL trong bar N+1:** LONG `low(N+1) ≤ SL` / SHORT `high(N+1) ≥ SL` → không vào (setup coi như đã bị quét stop).
- **Risk > 0:** LONG cần `entry > SL`, SHORT cần `entry < SL`, ngược lại skip.

### Tham số
Kế thừa gốc: `direction`, `sl_buffer_pct`, `key_level_lookback_bars`, `max_rejection_wick_pct`. Thêm: `pullback_pct` (default `0.30`).

## Touchpoints

| File | Thay đổi |
|---|---|
| `src/pocketquant/core/domain/strategy/services/engulfing_pullback30_touch_strategy_service.py` | Tạo mới |
| `src/pocketquant/core/domain/strategy/services/__init__.py` | Thêm entry `STRATEGY_REGISTRY` + `__all__` |
| `tests/core_test/unit/domain/strategy/` | Unit test state machine |
| `tests/backtest_test/engine/` | Integration test (mirror `test_engulfing_backtest.py`) |
| Frontend | Không đổi (detection identical, chọn qua `strategy_code`) |

## Acceptance criteria

- Backtest với `strategy_code = engulfing_pullback30_touch` chạy được, không lỗi registry.
- Bar engulfing đạt filter → **không** vào tại close bar đó.
- Bar N+1 chạm mức 30% (low≤level LONG) và không thủng SL → vào market tại close(N+1).
- Bar N+1 không chạm → không vào, setup reset.
- Bar N+1 chạm SL (`low≤SL`) → không vào.
- SL/TP neo theo pattern, risk = entry(N+1) − SL; entry thấp hơn close bar engulfing khi có pullback thật.
- Bản gốc `engulfing` và golden fixture **không đổi**.

## Rủi ro / đánh đổi

- Giá khớp = close(N+1), không phải đúng mức 30% → không lấy được giá tối ưu (chấp nhận; nâng cấp Model B sau).
- Chạm rồi bật mạnh: entry có thể cao hơn close_N ở cú đó (khớp tệ hơn bản gốc). Guard SL-violation giảm case xấu nhất.
- Vào ít lệnh hơn bản gốc (thêm điều kiện lọc) — cần backtest so sánh để xác nhận có cải thiện expectancy không.

## Success metrics (validate qua backtest)

So sánh `engulfing` vs `engulfing_pullback30_touch` trên cùng symbol/interval: win-rate, avg R:R, expectancy, số lệnh, max drawdown. Kỳ vọng: R:R trung bình cao hơn, số lệnh thấp hơn.

## Next steps

- `/ck:plan` để lập plan triển khai theo touchpoints trên.
- Sau khi có, backtest đối chứng 2 strategy để đo cải thiện.

## Câu hỏi chưa giải quyết

- Chưa xác định symbol/interval chuẩn để backtest đối chứng (đề xuất dùng bộ dữ liệu đang có sẵn của bản gốc engulfing).
