# Master report — Engulfing 1m BTC: cost, edge, tree-of-thoughts

> Doc duy nhất, tự chứa. Viết theo trình tự thời gian (mỗi phase mở rộng từ phase trước). Câu tiếng Việt, term tiếng Anh giữ nguyên + giải thích trong ngoặc lần đầu; Glossary ở Phần B. Log đủ số liệu + hạ tầng để resume ở session khác.
>
> **Cost model hiện tại:** `slippage 0.5 bps/chiều` + `commission 3 bps/chiều` (= 6 bps khứ hồi). Run phân tích đã recompute về mức này qua engine (nguồn sự thật = DB, không hand-patch).

---

# PHẦN A — Cách resume (đọc trước khi làm gì)

**Dữ liệu gốc:** MongoDB prod (VPS), read-only:
- pymongo: `MONGODB_URL` (từ `.env`/`pocketquant-config/local/remote-db*.env`, không hardcode), db `pocketquant`. Chạy qua `uv run python …` (venv project có pymongo 4.16; `~/.claude/skills/.venv` KHÔNG có).
- Collections: `backtest_runs`, `backtest_trades` (fields: `_id`, `run_id`, `entry_time`, `pnl` = gross USD trước commission, `commission`), `bars` (symbol composite `BTCUSDT:BINANCE`; 1m/5m/15m/1h/4h/1d).
- Run phân tích: `_id = 019f36d2-5f4f-75cc-95c6-49a7496c3a86` — strategy `engulfing_pullback30_touch`, 1m, 2025-07-06 → 2026-07-06, vốn 10,000 USD, **`slippage_bps=0.5`, `commission_bps=3.0`** (config_snapshot), 8,629 trades.

**Python:** `~/.claude/skills/.venv/bin/python3` (numpy, KHÔNG có pymongo) cho phân tích cache; `uv run python` cho query DB.

**Toolkit** (persist cạnh doc này, thư mục `scripts/`):
- `pq_prefetch.py` — kéo bars đa timeframe + entries ra cache `/tmp/pq_cache/*.npz`. **Chạy đầu tiên** (/tmp ephemeral — mất giữa các session).
- `pq_lib.py` — lib chung:
  - `load_real_entries()` → dict(idx, price, islong, epoch, sl, tp, qty, pnl, comm) — 8,629 entry thật; `pnl` = gross USD.
  - `detect_engulfing(tf, wick_pct=, min_body_atr=)` → entries (proxy đơn giản, sinh nhiều signal hơn strat thật ~10×).
  - `trend_up_at(tf, epoch, span=20)`, `atr(tf, period=14)`, `load_bars(tf)`.
  - `first_touch(entries, tf, sl_atr=|sl_bps=, tp_atr=|sl_R=|tp_bps=, maxbars=240, tie='SL')` → gross bps.
  - `fixed_horizon(entries, tf, hbars)` → signed gross bps.
  - `in_out_masks(entries)` → split walk-forward tại 2026-01-06.
  - `summarize(bps, friction=, hold_hours=, label=)`, `show(d)`.
  - **Friction round-trip bps: `taker=10` (4.5×2 + slippage 0.5×2), `maker=4` (2×2, limit không slippage), `maker_rebate=−2`, `zero=0`**; funding ≈ 1 bps/8h qua `hold_hours=`.
- `pq_atr_optimize.py`, `pq_entry_screen.py`, `pq_horizon_decay.py`, `pq_confirm_filtered.py` — phân tích Phase 4–7.

**Chạy lại:** `python3 scripts/pq_prefetch.py` → `cd scripts && python3 pq_xxx.py`.

**Kết luận một dòng:** *Engulfing 1m không có edge tự thân — chứng minh 5 cách. Thứ duy nhất còn edge out-of-sample là trend-following khung cao (Nhánh A — mạnh nhưng là beta, ăn theo đà thị trường) và fade tín hiệu trễ ở 1m (Nhánh E — đảo ngược tín hiệu; bền nhưng mỏng).*

---

# PHẦN B — Glossary

- **bps** — phần vạn: 1 bps = 0.01%. Trên 1,000 USD, 1 bps = 0.10 USD.
- **notional** — giá trị danh nghĩa vị thế = giá × khối lượng. Phí và edge đo theo % của nó.
- **gross / net PnL** — lãi/lỗ trước / sau phí (commission + slippage + funding).
- **commission** — phí sàn mỗi lần khớp, bps của notional. **slippage** — chênh giá dự tính so giá khớp thật (baked vào fill price).
- **friction** — tổng ma sát một vòng vào-ra = commission + slippage (+ funding nếu giữ lâu).
- **stop-loss (SL) / take-profit (TP)** — mức giá tự thoát cắt lỗ / chốt lời.
- **win rate** — tỉ lệ lệnh thắng. **break-even win rate** — tỉ lệ thắng tối thiểu để hoà với một R:R cho trước.
- **R:R** — TP cách entry gấp mấy lần SL cách entry. **R-multiple** — kết quả một lệnh đo bằng đơn vị rủi ro (+2R = lãi gấp đôi khoảng SL; −1R = mất đúng khoảng SL).
- **EV (expected value)** — lãi/lỗ trung bình mỗi lệnh về dài hạn.
- **ATR** — biên độ dao động thực trung bình N nến; đo mức nhiễu hiện thời.
- **MFE / MAE** — sau entry, giá đi thuận / nghịch xa nhất bao nhiêu.
- **edge** — lợi thế thống kê: lãi trung bình mỗi lệnh nếu không phí (bps). **edge-to-cost (e/c)** — edge / friction; phải > 1 mới có cơ lời sau phí.
- **maker / taker** — lệnh chờ (limit) thêm thanh khoản, phí thấp / lệnh thị trường lấy thanh khoản, phí cao. **rebate** — hoàn phí (phí âm) bậc VIP cao. **funding fee** — với perpetual, khoản trả mỗi 8h khi giữ vị thế.
- **first-touch** — quét nến sau entry xem chạm SL hay TP trước; chạm cả hai trong một nến → tính SL (bi quan). **fixed-horizon** — thoát đúng h nến sau entry bất kể gì.
- **walk-forward / in-sample (IN) / out-of-sample (OOS)** — chia dữ liệu: nửa đầu dò tham số, nửa sau kiểm định; số OOS mới đáng tin. **overfit / curve-fit** — khớp tham số quá mức vào nhiễu quá khứ; đẹp IN, sập OOS.
- **trend-following / momentum** — đi theo chiều xu hướng. **mean-reversion / fade** — đi NGƯỢC tín hiệu, cược giá quay đầu. **continuation** — tín hiệu kỳ vọng giá tiếp diễn cùng chiều.
- **aligned / counter-trend** — entry cùng / ngược chiều trend khung lớn.
- **alpha vs beta** — alpha = edge riêng của tín hiệu; beta = lời do thị trường trôi chung.
- **control** — nhóm đối chứng (vd entry ngẫu nhiên cùng chiều trend) để xem tín hiệu có hơn ngẫu nhiên không.
- **regime** — chế độ thị trường: trending (một chiều rõ) vs sideway/chop (đi ngang, nhiễu). Edge có thể sống regime này, chết regime kia.
- **fill probability** — xác suất lệnh limit thật sự khớp. **adverse selection** — bất lợi khi limit chỉ khớp đúng lúc thị trường sắp đi ngược mình.
- **signed forward return** — lãi tương lai TÍNH THEO CHIỀU LỆNH tại một mốc sau entry (dương = giá đi đúng hướng cược).
- **autocorrelation** — quan sát gần nhau trùng thông tin → số mẫu hiệu dụng nhỏ hơn số đếm.

---

# PHẦN C — Trình tự điều tra

| Phase | Câu hỏi kích hoạt | Kết luận | Dẫn tới |
|---|---|---|---|
| 1 | Config phí sai/quá cao? | Không — tính đúng, mức thực tế | 2 |
| 2 | Sao phí nuốt lãi? | gross đã âm TRƯỚC phí; overtrading | 3 |
| 3 | Vì sao edge âm? | stop 14 bps quá chật + slippage bào | 4 |
| 4 | ATR có cứu được? | Cả grid âm; entry vô hướng (MFE≈MAE) | 5 |
| 5 | Filter nào tạo hướng? | Trend khung 1h → +3.6 bps | 6 |
| 6 | Edge bền OOS? | Bền nhưng < friction | 7 |
| 7 | Giữ lâu (cross-TF) tăng edge? | Chững ~4 bps; 16h+ là trend beta | 8 |
| 8 | Còn hướng nào? (tree-of-thoughts) | 5 nhánh: 3 DEAD, 2 survivor | 9 |
| 9 | Hai survivor là gì? | A trend-follow 1h; E fade @1m | — |

## Phase 1 — "config phí có sai không?"

Người dùng nghi cách tính `commission` + `slippage` sai vì phí quá lớn so với gross PnL. Điều tra từ run thật trên VPS.

## Phase 2 — Cost analysis: config ĐÚNG, gross đã âm trước phí

Số liệu run thật (DB, cost model 0.5/3.0):

| Chỉ số | Giá trị |
|---|---|
| Số trade (round-trip) | 8,629 (~24 lệnh/ngày) |
| gross PnL (Σ trades.pnl, trước commission) | **−422.72 USD** |
| total_commission | −3,930.29 USD |
| net PnL / return | **−4,353 USD (−43.5%)** |
| commission thực tế | 6.00 bps notional khứ hồi = đúng `3 bps × 2 fill` |
| edge gross trung bình/lệnh (notional-weighted) | **≈ −0.7 bps** (âm) |
| win rate · profit factor | 42.9% · 0.927 |
| sharpe / sortino / max drawdown | −28.6 / −23.4 / −43.5% |
| avg_win / avg_loss (USD) | +1.45 / −1.18 |

Fee sensitivity (đổi giả định commission trên cùng bộ fill, slippage 0.5 baked):

| Giả định commission (mỗi chiều) | net PnL |
|---|---|
| zero | −422.72 USD (−4.23%) |
| maker 2 bps | −3,043 USD (−30.4%) |
| **current 3 bps** | **−4,353 USD (−43.5%)** |
| taker 4.5 bps | −6,318 USD (−63.2%) |

**Kết luận Phase 2:**
- Phép tính đúng: 6.00 bps = 3 bps/chiều × 2 khớp. Không bug. Mức 3 bps thực tế, thậm chí rộng rãi (Binance futures maker 2 / taker 4.5). Strategy vào bằng `market` → thực tế là taker → backtest đang LẠC QUAN.
- **Thủ phạm thật:** kể cả commission = 0 vẫn lỗ −4.23%; raw edge/lệnh ≈ −0.7 bps — không phân biệt được với zero và xa dưới mọi friction thực (maker 4 bps). Commission chỉ phơi bày một strategy không có edge tradeable. Hạ config phí cho đẹp = tự lừa dối.

## Phase 3 — Chẩn đoán edge âm: stop quá chật + slippage bào mòn

Nghịch lý: hình học payoff (trên giấy) dương nhưng thực tế âm.

| Chỉ số | Giá trị | Ý nghĩa |
|---|---|---|
| win rate gộp | 42.9% | |
| R:R trung bình (planned) | 1.57 | |
| break-even win rate | 38.9% | thắng CAO hơn ngưỡng → trên giấy phải lời |
| kỳ vọng nếu đạt kế hoạch | +0.10 R/lệnh | dương |
| **R-multiple thực tế trung bình** | **≈ −0.05** | âm — ngược dấu |
| SL distance median | 14.1 bps của giá | cực chật |
| duration median / mean | 12 phút / 23 phút | |

Phân bố kết cục:

| Exit | Số lệnh | avg (USD) |
|---|---|---|
| TP hit | 3,706 (42.9%) | +1.45 |
| SL hit | 4,923 (57.1%) | −1.18 |

Phân bố R-multiple thực tế: ≤ −1R (ăn trọn stop) 57.1% · 0..1R 29.6% (TP bị slippage bào còn ~0.86R) · 1..2R 9.1% · ≥2R 4.3%. Long/Short đối xứng cùng lỗ → lỗi cấu trúc, không lệch một chiều.

**Cơ chế:** SL 14 bps nằm trong biên nhiễu khung 1m → 57% bị quét stop bởi dao động ngẫu nhiên. `slippage` khứ hồi ~1 bps = 7% của một đơn vị rủi ro, kéo cả lệnh thắng lẫn thua xuống. Sự bào mòn bất đối xứng này lật +0.10 (giấy) thành −0.05 (thực). **Kim chỉ nam: `edge-to-cost` — khi risk chỉ 14 bps mà friction 1–6 bps, ma sát ăn 7–40% edge, không strategy nào sống.** (Giảm slippage 1→0.5 nâng R-multiple từ −0.115 lên −0.05 — vẫn âm.)

## Phase 4 — ATR grid: cả lưới âm; entry vô hướng

Giả thuyết: dùng `ATR` cho SL/TP (`SL = ATR × weight`, đề xuất 1.27) sẽ cứu. Kiểm chứng 8,629 entry + 526,641 nến, `first-touch`.

`ATR(14)` trên 1m BTC (bps của giá): p10=2.0 · **median=3.5** · mean=4.3 · p90=7.7. **Cực nhỏ.**

| ATR weight | SL distance | Commission 6 bps chiếm |
|---|---|---|
| **1.27** (đề xuất) | **4.4 bps** | **136% risk unit** ⛔ |
| 2.0 | 6.9 bps | 86% |
| 3.0 | 10.4 bps | 58% |
| 5.0 | 17.4 bps | 35% |

Quét grid SL 1.5–5×ATR × TP {3–14×ATR, 1.5–3R}: **mọi ô gross âm.** Tốt nhất (SL 2×ATR, TP 3R) = −0.29 bps trước phí; tệ nhất = −1.84 bps.

Bằng chứng độc lập — excursion theo ATR (window 240 nến): MAE median 9.1 ATR, MFE median 8.4 ATR. **MFE ≈ MAE** = dấu vân tay entry **vô hướng**. Exit không tạo được edge mà entry vốn không có.

Volatility floor (bỏ lệnh khi ATR nhỏ) trên ô tốt nhất:

| Sàn ATR | Giữ lại | gross | net@maker |
|---|---|---|---|
| không lọc | 100% | −0.29 | −4.29 |
| ≥ 5 bps | 50.8% | −0.05 | −4.05 |
| ≥ 8 bps | 24.3% | **+1.18** | −2.82 |

Chỉ khi bỏ 76% số lệnh, gross mới dương yếu (+1.18) nhưng vẫn dưới friction maker 4 bps.

**Kết luận Phase 4:** không trọng số ATR nào cứu được; lỗi ở ENTRY (vô hướng), không phải EXIT. Cơ chế: engulfing 1m hoàn tất + chờ pullback 30% thì sóng đã đi xong → tín hiệu vào TRỄ.

## Phase 5 — Entry filter screen: trend khung 1h tạo được hướng

Đo `signed forward return` tại 15/30/60/120 phút, thử nhiều filter.

### Thuật toán (từ `pq_entry_screen.py`)

```
8,629 entry thật
    ├─ trend 1h: nến 1h ĐÓNG gần nhất trước entry (bisect_right−1, no-lookahead);
    │            h1up = close_1h > EMA20(close_1h)
    ├─ aligned_1h = (islong == h1up)
    ├─ signed fwd @h nến: sgn=(+1 long/−1 short); fwd = sgn·(close[i+h]−ep)/ep·1e4 (bps gross)
    ├─ aligned==True  → 4,318 lệnh → mean fwd@60m = +3.58  ┐ đối xứng
    └─ aligned==False → 4,311 lệnh → mean fwd@60m = −7.05  ┘ quanh baseline −1.73
```

Ba chi tiết quyết định tính đúng: `sgn·(…)` chuẩn hoá long/short cùng thước; `/ep·1e4` đổi USD → bps notional; nến 1h phải ĐÃ ĐÓNG trước entry (dùng nến đang chạy = lookahead leak).

### Vì sao trend 1h "tạo được hướng"

Filter 1h KHÔNG dự báo giá — nó **lọc bỏ nhóm entry cấu trúc-sai**. Engulfing là tín hiệu `continuation`, chỉ có giá trị khi nối tiếp xu hướng LỚN hơn:
- **Aligned** (long khi 1h lên): pullback trong uptrend kết thúc → chạy tiếp → **+3.58**.
- **Counter** (long khi 1h xuống): bull trap trong downtrend → quay đầu → **−7.05**.

**Counter âm mạnh là control quyết định:** nếu filter vô dụng, cả hai nhánh phải ≈ baseline (−1.73). Thực tế tách +3.58 / −7.05 — gương đối xứng → chiều trend 1h mang thông tin thật. Phải là khung CAO hơn: đo trend trên chính 1m (EMA200) chỉ ra −1.7 bps (cùng tầng nhiễu, vô dụng).

> Nghịch lý cốt lõi: đo được hướng ≠ kiếm được tiền. Edge sau lọc (~3.5 bps) vẫn < friction maker (4 bps) → net âm OOS (Phase 6).

| Tập con entry | 60 phút | Số lệnh |
|---|---|---|
| Tất cả (baseline) | −1.73 | 8,629 |
| **Aligned trend 1h** | **+3.58** | 4,318 |
| Counter trend 1h | −7.05 | 4,311 |
| Aligned 1h + ATR ≥ 5 bps | **+4.42** | 2,189 |
| Aligned 1h + volume z ≥ 1 | +3.42 | 483 |
| Trend EMA200 trên 1m | −1.7 | (vô dụng) |
| Fade tất cả (đảo mọi tín hiệu) | +1.73 | 8,629 |

### Bảng theo giờ — MÔ TẢ, không phải tín hiệu tradeable

Bucket theo giờ New York (DST-aware, thẳng hàng phiên cash equities Mỹ mở 9:30 ET). Vì NY theo DST, một giờ NY map sang 2 giờ UTC tùy mùa (đông NY+5 / hè NY+4); VN = UTC+7 không DST.

**Aligned (subset có edge, n≈4,318), signed fwd@60m bps:**

| NY | UTC | VN | bps | n |
|---|---|---|---|---|
| 03:00 | 07/08 | 14/15 | +6.27 | 181 |
| 04:00 | 08/09 | 15/16 | +6.82 | 190 |
| 06:00 | 10/11 | 17/18 | +5.07 | 185 |
| **09:00** | 13/14 | 20/21 | **+12.16** | 182 |
| **10:00** | 14/15 | 21/22 | **+11.70** | 158 |
| 11:00 | 15/16 | 22/23 | +6.87 | 153 |
| 12:00 | 16/17 | 23/00 | +7.57 | 184 |
| 16:00 | 20/21 | 03/04 | −2.40 | 182 |
| **17:00** | 21/22 | 04/05 | **−3.79** | 209 |
| 22:00 | 02/03 | 09/10 | +6.47 | 201 |
| 23:00 | 03/04 | 10/11 | +7.13 | 197 |

(Cụm mạnh nhất NY 09:00–12:00 = mở phiên + sáng cash equities Mỹ; yếu nhất NY 14:00–17:00 chiều Mỹ. Baseline cùng giờ âm hơn nhiều, vd NY 10:00 baseline −8.33 → aligned +11.70: chênh lệch chính là sức phân tách của trend filter.)

**Vì sao KHÔNG tradeable (ba lỗi cộng dồn):**
1. **In-sample cherry-picking:** bảng tính trên cả năm IN+OOS. Nhìn "NY 09:00 +12.16" rồi trade giờ đó = chọn winner sau khi biết kết quả.
2. **Multiple-testing artifact:** 24 bucket = 24 phép thử; với n≈180 và std forward-return 1m lớn, thuần ngẫu nhiên cũng đẻ vài bucket +10 / −8. Đỉnh +12.16 phần lớn là noise khuếch đại.
3. **OOS đã đo (Nhánh C):** `good_hours` IN +1.77 / **OOS −0.06**; `good_hours ∩ ATR≥5` IN +4.54 / **OOS −0.11**. Corr IN/OUT 0.17–0.36 (thứ tự giờ tốt/xấu nửa đầu gần như không dự báo nửa sau).

→ "Chỉ trade NY 09:00–10:00" = curve-fit. Bảng dùng để **hiểu** (phiên Mỹ mở → biến động cao → engulfing rõ hơn), KHÔNG làm rule vào lệnh. Gốc: một năm một symbol quá ít cho 24 bucket.

**Kết luận Phase 5:** engulfing 1m là tín hiệu `continuation`, chỉ có hướng khi aligned với trend khung LỚN hơn.

## Phase 6 — Walk-forward: edge THẬT nhưng dưới friction

Tập aligned 1h + ATR ≥ 5 (2,189 lệnh), 6 tháng đầu tune / 6 tháng sau validate, `first-touch`:

| | IN (tune) | OOS (chưa tune) |
|---|---|---|
| gross bps/lệnh (ô tốt nhất) | +5 đến +6 | +1.2 đến +2.5 |
| net @ maker (−4bps) | +1 đến +2 | **−1.5 đến −2.8** |
| net @ taker (−10bps) | — | ≈ −8 |

- Edge có hướng **bền OOS** (gross vẫn dương, cùng dấu IN) → không curve-fit.
- Nhưng edge (~2 bps) **< friction maker 4 bps** → net âm OOS. Ô tốt nhất IN +2.06 rớt −2.82 OOS (tune exit overfit).

**Giới hạn cấu trúc:** trên 1m BTC, sóng tự nhiên (~3.5 bps) < friction (4 bps maker). Edge < cost là bất biến của khung thời gian.

## Phase 7 — Cross-timeframe: edge chững, 16h+ hoá trend beta

Vào trên 1m nhưng giữ lâu — gross theo thời gian giữ (aligned 1h):

| Giữ | gross | net@maker | Đọc |
|---|---|---|---|
| 30 phút | +2.61 | −1.39 | edge engulfing thật |
| 1h | +3.58 | −0.42 | |
| 2h | +3.31 | −0.69 | plateau ~+3.5 |
| 4h | +3.68 | −0.32 | vẫn ≈ friction |
| 8h | +2.95 | −1.05 | |
| **16h** | **+7.84** | **+3.84** | nhảy vọt — nhưng… |
| 24h | +5.85 | +1.85 | |
| 48h | +5.99 | +1.99 | |

- **1h–4h:** edge thật, plateau ~+3.5 bps ≈ friction.
- **16h+:** con số dương to là **trend beta** (baseline không lọc ở 16h cũng dương +1.33), không phải edge engulfing. Chưa trừ funding; phương sai cao (ATR≥5 subset: 8h −0.97, 48h −7.38).

**Kết luận Phase 7:** phần lời giữ-lâu là trend beta, cần thiết kế lại như trend-following.

## Phase 8 — Tree-of-thoughts: 5 nhánh song song

5 agent song song, mỗi agent một giả thuyết, walk-forward, brutally honest.

### Nhánh A — Engulfing đa timeframe

Detect engulfing trên 5m/15m/1h/4h, filter theo trend khung cao hơn, walk-forward:

| TF | best config | n_out | gross | net@maker | net@taker | e/c@mk | Verdict |
|---|---|---|---|---|---|---|---|
| 5m | fixed-horizon 24 (2h) | 5159 | +5.37 | +1.37 | −4.63 | 1.34 | MARGINAL (chỉ sống maker) |
| 15m | fixed-horizon 24 (6h) | 1718 | +10.36 | +6.36 | +0.36 | 2.59 | MARGINAL (mỏng ở taker) |
| **1h** | **first-touch SL3×ATR TP3R** | 418 | +72.92 | **+68.92** | **+62.92** | 18.2 | **VIABLE (sống cả maker lẫn taker)** |
| 1h | fixed-horizon 24 (24h) | 416 | +35.9 | **+31.9** | **+25.9** | 9.0 | VIABLE |
| 4h | fixed-horizon 6 (24h) | 116 | +6.53 | +2.53 | −3.47 | 1.63 | MARGINAL (n mỏng) |

Control (1h, fixed-horizon 24, OOS): **aligned +35.90 / unaligned (ALL) +1.71 / counter −33.42** → gương đối xứng hoàn hảo. Edge scale đều theo thời gian giữ (h6 +20, h12 +29, h24 +36, h48 +64 gross) = trend-drift capture.
→ **Edge là TREND FILTER 1d, KHÔNG phải engulfing.** Engulfing chỉ là cò bấm.

### Nhánh B — Trend-follow 16h+ @1m: alpha hay beta?

Aligned 1h subset, so với control ngẫu nhiên (entry random cùng chiều trend 1h), net@maker + funding:

| Giữ | ENG net | CONTROL net | ALPHA (eng−ctrl) |
|---|---|---|---|
| 8h | −2.05 | +0.82 | −2.86 |
| **16h** | **+1.84** | **+1.83** | **+0.01** |
| 24h | −1.15 | −1.24 | +0.09 |
| 48h | −4.01 | +0.18 | −4.20 |

Con số dương duy nhất (16h +1.84) bị control khớp y hệt (+1.83) → alpha = +0.01. Walk-forward ALPHA_OUT âm mọi horizon. Funding lật 24h/48h thành âm.
→ **DEAD như một engulfing strategy** (là beta, không alpha).

### Nhánh C — Session / time-of-day filter

Aligned subset, chọn giờ tốt trên IN, áp OOS:

| Config | IN net@mk | OUT net@mk | n_out |
|---|---|---|---|
| baseline aligned (fh60) | −0.37 | −0.47 | 2174 |
| good_hours (18h) | +1.77 | **−0.06** | 1623 |
| good_hours ∩ ATR≥5 | +4.54 | **−0.11** | 940 |

Overfit gap: filter càng chặt càng sập. Corr IN/OUT 0.17–0.36 (~0.4 bps OOS). Weekday vô dụng.
→ **DEAD / overfit.**

### Nhánh D — Maker/limit + rebate re-pricing

| Set | gross IN | gross OUT |
|---|---|---|
| FULL | −1.58 | −1.66 |
| ALIGNED | +0.49 | **+0.08** |

net aligned: maker(4) IN −3.51 / OUT −3.92; zero(0) +0.49 / +0.08; rebate(−2) +2.49 / +2.08. Break-even friction ≈ 0 bps (OOS +0.08 nằm trong 1 SE của zero). Dương chỉ khi rebate = **rebate-harvesting**, không phải alpha. `fill probability` chưa mô phỏng.
→ **DEAD** — maker không cứu; cần phí ≤ 0 mới hoà.

### Nhánh E — Multi-filter stack + fade

Stack `aligned + atr≥X + vol_z≥Y`: **mọi combo vol_z sập OOS** (multiple-testing artifact); chỉ `atr≥8` sống marginally.

**FADE (đảo ngược tín hiệu trễ) — nguồn edge thật:**

| Leg | IN net | OUT net |
|---|---|---|
| counter-trend FOLLOW | −11.6 | −12.5 |
| **counter-trend FADE** | **+1.64** | **+2.45** |
| aligned FOLLOW | −1.37 | −1.47 |

Combined `{aligned→follow} ∪ {counter→fade}`:

| Config | IN net@mk | OUT net@mk | n_out |
|---|---|---|---|
| ALL follow (baseline) | −6.51 | −6.95 | 4338 |
| alignFollow ∪ counterFade | +0.14 | +0.49 | 4338 |
| + ATR≥5 | +0.56 | +1.41 | 2454 |
| **+ ATR≥8** | **+1.69** | **+1.73** | **1251** |

Friction sensitivity (combined): rebate +6.49 / maker +0.49 / taker −5.51.
→ **MARGINAL (bền)** — edge thật, IN≈OUT, cơ chế đúng (fade tín hiệu trễ), nhưng ~1.7 bps quá mỏng, chỉ sống maker.

### Meta-finding Phase 8

> **Pattern engulfing bản thân ~0 alpha out-of-sample.** Mọi edge quy về (1) trend-following khung cao hoặc (2) fade tín hiệu trễ. Cùng một sự thật nhìn hai mặt: theo trend, và fade nhiễu ngược trend.

## Phase 9 — Hai survivor (config chính xác)

### A — Trend-following khung 1h (edge lớn, là beta, phải rời 1m)
- **Config:** direction = chiều trend khung 1d (close > EMA20 trên 1d → long); entry = engulfing trigger trên 1h; exit = fixed-horizon 24×1h (24h). Alternative: first-touch SL 3×ATR, TP 3R → net@maker +68.9 / net@taker +62.9.
- **Số OOS:** gross +35.9 · net@maker +31.9 · net@taker +25.9 · e/c 9.0 · win rate 0.58 · n 416. Bền walk-forward cả hai nửa.
- **Bản chất:** trend-following (momentum); engulfing chỉ là cò bấm.
- **Rủi ro:** cả năm test là regime trending; năm sideway nhiều khả năng sập. Chưa validate đa regime / đa symbol.

### E — Fade tín hiệu trễ, giữ khung 1m (edge nhỏ, bền)
- **Config:** `{aligned → follow} ∪ {counter-trend → fade}`, lọc `atr_bps ≥ 8`, exit fixed-horizon 60m.
- **Số OOS:** net@maker +1.73 · n 1251 · IN +1.69 ≈ OUT. Fade counter-trend gross +7.4 (~2× aligned-follow) là nguồn edge chính.
- **Bản chất:** engulfing 1m thực ra là tín hiệu `contrarian` (fade), không phải continuation.
- **Rủi ro:** ~1.7 bps quá mỏng; chỉ sống maker (taker −5.51 giết); thao tác đảo ngược gượng gạo; fill probability chưa mô phỏng.

---

# PHẦN D — Khuyến nghị & lựa chọn tiếp

| Nếu bạn... | Đi hướng | Bản chất |
|---|---|---|
| Chấp nhận rời 1m | **A** — reframe thành trend-following khung 1h, validate đa regime + đa symbol, thêm drawdown control | Highest-EV, nhưng là momentum không phải engulfing |
| Bắt buộc giữ 1m | **E** — fade engulfing trễ, execution maker | Edge thật nhưng mỏng, treat như research lead |
| — | Bỏ engulfing như directional signal độc lập — đã chứng minh 5 cách | — |

**Đóng dứt khoát:** B (trend-beta-không-alpha), C (session overfit), D (maker-không-cứu).

Option triển khai (chưa chọn):
- Validate A đa regime / đa symbol trước (DB chỉ có BTC — cần thêm symbol).
- Đào sâu E: tối ưu exit/filter, mô phỏng fill probability, xem có nâng +1.73 lên mức tradeable không.
- Lập plan build strategy (A hoặc E) vào backtest engine thật.

Nếu build cross-timeframe / trend-following: đây là thay đổi **structure level** — strategy đa timeframe (1m/1h/1d), giữ lệnh dài, exit theo cấu trúc khung cao, cost model thêm funding.

---

# PHẦN E — Câu hỏi chưa giải quyết

- A: trend-follow 1h giữ edge trên symbol khác / năm không-trending không? Cần multi-regime + multi-symbol backtest.
- E: strat engulfing THẬT (`engulfing_pullback30_touch`, sinh ít signal nhưng chất hơn detector proxy) có nâng baseline unaligned trên cost không, hay cũng phụ thuộc hoàn toàn vào trend filter?
- E/D: fill probability của limit order chưa mô phỏng — cần model non-fill + adverse selection.
- B: funding thật BTC perp (hiện giả định phẳng 1 bps/8h).
- D/E: fee tier maker thật của tài khoản (có rebate không) — quyết định khả thi.

---

# PHẦN F — Caveat xuyên suốt

- **Một symbol (BTC), một năm, một split** → cả IN/OUT nằm trong cùng regime trending. Rủi ro này chi phối cả A lẫn E.
- `detect_engulfing` là **proxy đơn giản** (sinh nhiều signal hơn strat thật ~10×: 94,610 vs 8,629 trên 1m). Số Nhánh A/E là HƯỚNG, không phải con số production.
- Entry lấy từ backtest cũ (đã filter bằng SL 14 bps) → có selection bias nhẹ; trend filter độc lập với SL nên phát hiện vẫn vững, nhưng net chính xác cần backtest lại strategy mới.
- Long holds (16–48h) trên entry 1m bị **autocorrelation** nặng → số mẫu hiệu dụng nhỏ hơn nhiều; số alpha ~±0 không phân biệt được với zero.
- `funding` giả định phẳng 1 bps/8h; thực tế biến động, làm hold dài tệ hơn.
- `first-touch` bi quan (chạm cả hai → tính SL); `fixed-horizon` bỏ qua path intrabar.
- Proxy Phase 4–9 chạy trên cache bars thuần (gross không baked slippage); friction áp qua `summarize()`. Đổi slippage 1→0.5 chỉ dịch `taker` round-trip 11→10; `maker`/`gross`/`e/c@mk` không đổi — nên chỉ cột `net@taker` cải thiện +1 bps so với vintage trước.
- Mọi số per-lệnh = expected return per trade, đơn vị bps của notional.
