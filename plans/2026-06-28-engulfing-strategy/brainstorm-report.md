---
title: Engulfing Strategy — Brainstorm Report
date: 2026-06-28
skill: brainstorm
modes: []
status: design-approved
---

# Engulfing Strategy — Brainstorm Report

## 1. Problem Statement

Thêm strategy `engulfing` cho PocketQuant với 2 layer tách biệt:

1. **Visualization layer** — hiển thị **tất cả** engulfing pattern trên chart trước (kể cả pattern không vào lệnh), tô màu phân biệt **strong/weak**.
2. **Strategy/backtest layer** — chỉ entry các engulfing **mạnh**; mỗi entry có SL dưới low pattern + buffer, TP tối thiểu RR 1:1, ưu tiên key-level nếu cho R:R cao hơn.

### Yêu cầu cụ thể (exact requirements)

| Mục | Giá trị chốt |
|---|---|
| Expected output | Strategy `engulfing` chạy được trong backtest (markers + SL/TP box); nút toggle "Engulfing" trên chart vẽ mọi pattern tô màu strong/weak; 2 file doc |
| Acceptance | (1) `GET /backtest/strategies` liệt kê `engulfing`; (2) backtest chạy ra trades với SL/TP đúng công thức; (3) toggle chart vẽ engulfing markers, đậm=strong nhạt=weak; (4) golden fixture test pass cả TS lẫn Python với cùng kết quả |
| Out of scope | Scale-out / multi-TP / partial close (đẩy roadmap); backend pattern-detection API; full-range engulfing; trend filter |
| Constraints | Không sửa `Signal`/`PaperBroker`/`LotTracker`/routes/DI; client-side detection (TS); UUIDv7; single-process; docs AS-IS tiếng Việt |
| Touchpoints | `core/domain/strategy/services/`, `core/domain/strategy/patterns/` (mới), `web/src/lib/indicators/`, `web/src/components/controls/indicator-toggles.tsx`, `web/src/components/chart/trading-chart.tsx`, `web/src/types/market-data.ts`, `docs/` |

## 2. Codebase Context (scout findings)

- **Strategy interface**: `core/domain/strategy/interfaces.py` — `IStrategy.on_bar(bar) -> Signal | None`. Bar = dict `{open,high,low,close,volume,timestamp,symbol,interval}`.
- **Blueprint gần nhất**: `core/domain/strategy/services/hitnrun2.py` — entry-on-close + SL/TP = looser của technical level & account cap; position cap 1 lệnh; state reset trong `on_fill`.
- **Registry**: `core/domain/strategy/services/__init__.py` → `STRATEGY_REGISTRY` dict. Thêm 1 dòng là API tự expose.
- **Signal**: `core/domain/strategy/value_objects.py` — đã có `entry_price`, `stop_loss_price`, `take_profit_price`, `entry_logic`. **Một** TP duy nhất.
- **Pipeline**: `Signal` → `StrategyAppService._process_signal` (`engine/app_services/strategy_app_service.py:289`) → `OrderAggregate` → `PaperBroker`. PaperBroker auto-fill SL/TP trên `BarCompletedEvent`, đóng **toàn bộ** position (`_fire_synthetic_exit`, `paper_broker.py:636`).
- **Position key**: `subscription_id:symbol` (`paper_broker.py:454`) → **một** position mỗi strategy/symbol; lệnh thứ 2 bị merge, không chạy song song.
- **Chart**: `web/src/components/chart/trading-chart.tsx` — `lightweight-charts` v5. Backtest markers set qua `createSeriesMarkers(candleRef, markers)`. Indicators tính **client-side TS** (`web/src/lib/indicators/`), toggle qua `IndicatorConfig` (sma/ema/rsi/macd/bollinger).
- **KHÔNG tồn tại sẵn**: candlestick pattern detection, khái niệm key-level/support-resistance, cơ chế vẽ marker không qua backtest.

## 3. Định nghĩa Engulfing (khóa chung TS + Python)

**Strict body engulfing** — so sánh thân nến (open/close), 2 chiều:

```
Bullish (→ LONG):
  prev đỏ:   prev_close < prev_open
  curr xanh: close > open
  body bao trùm: open <= prev_close  AND  close >= prev_open

Bearish (→ SHORT): mirror
  prev xanh; curr đỏ
  body bao trùm: open >= prev_close  AND  close <= prev_open
```

### Quality filter — close-location CÓ HƯỚNG (chống weak/fake)

Body-only engulfing mù với **rejection**: nến nuốt body nhưng close cách xa extreme (wick ngược chiều dài) = lực đảo chiều cuối phiên = tín hiệu yếu. Filter phải **có hướng** vì:

| Pattern | Wick gây rejection (xấu) | Wick vô hại/tốt |
|---|---|---|
| Bullish → LONG | upper wick `high-close` dài → bị bán ngược ở đỉnh | lower wick dài → người mua đỡ đáy (bullish) |
| Bearish → SHORT | lower wick `close-low` dài → bị mua ngược ở đáy | upper wick dài → người bán đè đỉnh (bearish) |

→ Body-dominance ratio (body/range) bị loại vì **không có hướng** — phạt oan lower wick tốt của nến LONG.

```
LONG:  (high - close) / (high - low) <= max_rejection_wick_pct
SHORT: (close - low)  / (high - low) <= max_rejection_wick_pct
# close phải nằm gần extreme theo chiều lệnh; default 0.30; =1.0 để tắt
# guard: nếu high == low (range 0) → coi như fail/skip để tránh chia 0
```

**Một metric, hai consumer**: detector tính body-engulf + wick metric một lần; chart tô màu theo metric, strategy entry theo ngưỡng.

## 4. Entry / SL / TP (Python strategy)

```
LONG (bullish engulfing pass filter):
  entry       = close
  pattern_low = min(low_curr, low_prev)            # low của CẢ 2 nến
  SL          = pattern_low * (1 - sl_buffer_pct)
  risk        = entry - SL
  tp_rr       = entry + risk                        # RR 1:1 sàn
  key_level   = max(highs[-N:])                     # swing high N bar trước
  TP          = max(tp_rr, key_level)               # ưu tiên key-level nếu xa hơn

SHORT: mirror
  pattern_high = max(high_curr, high_prev)
  SL           = pattern_high * (1 + sl_buffer_pct)
  risk         = SL - entry
  tp_rr        = entry - risk
  key_level    = min(lows[-N:])                     # swing low N bar
  TP           = min(tp_rr, key_level)
```

`max()`/`min()` đảm bảo đúng "tối thiểu 1:1, ưu tiên key-level": key-level chỉ thắng khi cho R:R > 1; nếu quá gần thì rơi về sàn 1:1.

### Params (default tune-được)

```python
_DEFAULTS = {
    "direction": "both",              # long | short | both
    "sl_buffer_pct": 0.001,           # 0.1% dưới/trên pattern extreme
    "key_level_lookback_bars": 20,    # N bar swing high/low
    "max_rejection_wick_pct": 0.30,   # close-location filter; 1.0 = tắt
}
```

- Position cap = 1 lệnh/lúc (`_open_direction`, reset trong `on_fill` — copy pattern `hitnrun2`).
- Warmup: cần ≥ `key_level_lookback_bars` bar trước khi tính key-level.

## 5. Evaluated Approaches

### 5a. Show-all-patterns: A vs B vs C

| | A — Client TS toggle (CHỌN) | B — Backend API | C — chỉ backtest entries |
|---|---|---|---|
| Bản chất | detect + vẽ thuần frontend | API trả occurrences, FE render | marker = entry backtest |
| Single source | ✗ (2 impl) | ✓ | n/a |
| Chi phí | thấp | cao (endpoint+UI) | thấp nhất |
| Đáp ứng "show all" | ✓ | ✓ | ✗ (mất pattern không vào lệnh) |

**Chọn A**: detection là pure function ~8 dòng; "show all" (TS) và "entry markers" (Python) **vốn là 2 tập khác nhau** nên 2 impl không hẳn duplicate. Khóa đồng nhất bằng **golden fixture chung** (cùng OHLC input → cùng expected output) + docstring định nghĩa, test 2 bên.

### 5b. Scale-out / 2-TP: KHÔNG khả thi với engine hiện tại

| Tầng | Giới hạn | File |
|---|---|---|
| `Signal` | một `take_profit_price` | `value_objects.py:17` |
| `IStrategy.on_bar` | trả một `Signal`, không phải list | `interfaces.py:37` |
| `PaperBroker` | một `tp_price`/position; `_fire_synthetic_exit` đóng toàn bộ qty | `paper_broker.py:636` |
| Position | `subscription_id:symbol` → một position; lệnh 2 bị merge | `paper_broker.py:454` |

**Quyết định: baseline 1-TP** (`TP = max(RR 1:1, key-level)`), scale-out đẩy roadmap + viết doc giải thích giới hạn. Lý do: scale-out là thay đổi cross-cutting public contract (Signal, broker, lot-tracker, position-box render, nhiều test) → rủi ro cao, nên là project riêng sau khi baseline có dữ liệu.

## 6. Recommended Solution

Strategy Python thuần (giống `hitnrun2`) + client-side TS visualization, một định nghĩa engulfing khóa bằng golden fixture.

### Files

**Backend (mới/sửa):**
- `core/domain/strategy/patterns/engulfing_detector.py` *(mới)* — pure function: input 2 bar → `{is_bullish, is_bearish, rejection_wick_pct, ...}`
- `core/domain/strategy/services/engulfing.py` *(mới)* — `EngulfingStrategy(IStrategy)`
- `core/domain/strategy/services/__init__.py` *(sửa 1 dòng)* — `"engulfing": EngulfingStrategy`
- `tests/core_test/.../test_engulfing.py` *(mới)* — unit + golden fixture
- `tests/backtest_test/.../test_engulfing_backtest.py` *(mới)* — integration

→ **Không đụng** `Signal`, `PaperBroker`, `LotTracker`, routes, DI.

**Frontend (mới/sửa):**
- `web/src/lib/indicators/engulfing.ts` *(mới)* — detect → markers (đậm strong / nhạt weak)
- `web/src/types/market-data.ts` *(sửa)* — `+ engulfing: boolean` vào `IndicatorConfig`
- `web/src/components/controls/indicator-toggles.tsx` *(sửa)* — thêm nút "Engulfing"
- `web/src/components/chart/trading-chart.tsx` *(sửa)* — **merge** engulfing markers + backtest markers chung 1 array
- golden fixture test *(mới)* dùng chung input với Python

**Docs (deliverable, trong `docs/`):**
- Doc 1 — vì sao engine không hỗ trợ scale-out/multi-TP/partial close (4 tầng giới hạn ở §5b)
- Doc 2 — education swing pivot / swing high-low: là gì, cách tính, vì sao dùng làm key-level, ví dụ minh họa

## 7. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Markers chồng/override: `createSeriesMarkers` gọi 2 lần sẽ ghi đè | Merge engulfing + backtest vào **một** array trước `setMarkers`; điểm tích hợp quan trọng nhất ở FE |
| 2 impl (TS/Python) lệch định nghĩa theo thời gian | Golden fixture JSON chung + docstring định nghĩa; test 2 bên assert cùng kết quả |
| Chia 0 khi `high == low` (range 0) trong wick filter | Guard: range 0 → fail filter / skip |
| Filter quá khắt khe → ít tín hiệu | `max_rejection_wick_pct` tune-được, =1.0 tắt hẳn |
| Scale-out bị kỳ vọng nhầm là có | Doc giải thích giới hạn engine + roadmap entry |

## 8. Success Metrics

- `engulfing` xuất hiện trong `GET /backtest/strategies`.
- Backtest sinh trades; SL/TP từng trade khớp công thức §4 (verify bằng integration test synthetic bars).
- Toggle "Engulfing" vẽ markers; strong đậm, weak nhạt; không override backtest markers.
- Golden fixture: TS test và Python test ra **cùng** tập pattern + cùng rejection metric.
- `just lint && just types && just test` xanh; `cd web && npm run lint && npm run build` xanh.

## 9. Open Questions (defaults đề xuất, tune được khi plan)

1. `sl_buffer_pct = 0.001` (0.1%) — OK default?
2. `key_level_lookback_bars = 20` — OK default?
3. `max_rejection_wick_pct = 0.30` — OK default?
4. "low pattern" = `min(low 2 nến)` (đề xuất) — đồng ý, hay chỉ low của engulfing bar?

(Không block implementation — có thể chốt khi `/ck:plan`.)

## 10. Next Steps

- `/ck:plan` (default mode) — feature mới, không refactor business logic hiện có nên không cần `--tdd` bắt buộc; tuy nhiên golden-fixture-first vẫn nên áp dụng trong từng phase.
- Truyền report path này làm context cho plan.
