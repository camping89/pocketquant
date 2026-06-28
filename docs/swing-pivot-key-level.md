# Swing pivot & key-level cho take-profit

`EngulfingStrategy` (và `hitnrun2`) đặt take-profit không chỉ theo risk-reward thuần, mà còn tham chiếu **key-level** lấy từ swing high/low gần nhất. Doc này giải thích swing pivot là gì, cách engine xấp xỉ nó, và vì sao dùng làm TP.

## Swing high / swing low là gì

- **Swing high**: một đỉnh cục bộ — bar có high cao hơn các bar xung quanh, nơi giá quay đầu giảm.
- **Swing low**: một đáy cục bộ — bar có low thấp hơn các bar xung quanh, nơi giá quay đầu tăng.

Swing pivot là nơi thị trường "đã từng phản ứng". Lệnh chờ và thanh khoản hay tụ quanh các mức này, nên giá có xu hướng phản ứng lại khi quay về.

## Cách engine xấp xỉ (proxy, KHÔNG phải pivot detection thật)

Engine **không** detect swing pivot theo nghĩa hình học (so sánh đỉnh/đáy với các bar lân cận hai phía). Thay vào đó nó dùng một proxy đơn giản — **max/min của cửa sổ N bar gần nhất**:

```
LONG  key_level = max(highs[-N:])   # đỉnh cao nhất trong N bar trước
SHORT key_level = min(lows[-N:])    # đáy thấp nhất trong N bar trước
```

với `N = key_level_lookback_bars` (default 20). Cửa sổ này được snapshot **trước** khi thêm bar hiện tại, nên key-level luôn là N bar **strictly trước** pattern — không gồm chính bar đang vào lệnh.

> **Caveat — đây là proxy, không phải swing-pivot detection.** `max/min` của cửa sổ thô không phân biệt một đỉnh thật (có phản ứng giá hai phía) với một spike nhất thời. Pivot detection hình học đã được cân nhắc và **loại khỏi scope** (xem brainstorm-report). Đừng đọc key-level như "swing pivot đã xác nhận".

## TP = max(RR 1:1, key-level)

`EngulfingStrategy` lấy TP là mức **xa hơn** giữa risk-reward 1:1 và key-level:

```
LONG:  risk = entry - SL;  tp_rr = entry + risk;  TP = max(tp_rr, key_level)
SHORT: risk = SL - entry;  tp_rr = entry - risk;  TP = min(tp_rr, key_level)
```

Lý do: đặt TP tại mức giá hay phản ứng (key-level) hợp lý hơn một con số tròn tùy ý, nhưng không bao giờ nhận RR thấp hơn 1:1.

### Ví dụ 1 — key-level xa hơn RR → TP nhảy lên key

```
        key_level (max 20 highs) = 110
          ┌──────────────────────────── TP = 110  (xa hơn tp_rr)
          │
   entry 101 ───────────────●
          │     risk = 4.2
   tp_rr 105.2 ─ ─ ─ ─ ─ ─ ─ (RR 1:1, nhưng thấp hơn key)
          │
   SL   96.8 ──────────────
```
key-level (110) > tp_rr (105.2) → `TP = max(105.2, 110) = 110`.

### Ví dụ 2 — key-level gần → rơi về RR 1:1

```
   tp_rr 105.2 ─────────────── TP = 105.2  (RR 1:1, vì key gần hơn)
          │
        key_level = 102  ─ ─ ─ (đỉnh gần, dưới tp_rr)
   entry 101 ───────────────●
          │     risk = 4.2
   SL   96.8 ──────────────
```
key-level (102) < tp_rr (105.2) → `TP = max(105.2, 102) = 105.2`. TP luôn ≥ RR 1:1.

## Chart "show all patterns" ≠ tập tín hiệu strategy

Nút toggle **Engulfing** trên chart vẽ **mọi** body-engulfing pattern. Strategy chỉ entry một **subset**:

- **Warmup**: pattern xuất hiện trong `key_level_lookback_bars` bar đầu (chưa đủ cửa sổ key-level) → có marker trên chart nhưng **không** có trade.
- **Position cap**: tối đa một vị thế cùng lúc — pattern xuất hiện khi đang có lệnh mở → có marker nhưng **không** entry.

Đây là chủ ý, không phải bug. Marker trên chart KHÔNG có nghĩa "strategy đã/sẽ vào lệnh tại đây".

## Strong-threshold trên chart là visual aid cố định

Chart tô màu strong/weak ở ngưỡng FE **cố định 0.30** (`STRONG_THRESHOLD` trong `web/src/lib/indicators/engulfing.ts`). Strategy đọc `max_rejection_wick_pct` từ config (tune-được qua backtest). Nếu một backtest tune ngưỡng khác 0.30, màu trên chart **không** phản ánh config đó — coloring chỉ là aid trực quan, không phải dự đoán "entry hay không" cho một backtest cụ thể.
