# Master report — Nghiên cứu strategy engulfing 1m BTC: cost, edge, tree-of-thoughts

> **Doc duy nhất, tự chứa.** Gộp toàn bộ điều tra, viết theo **trình tự thời gian** (mỗi phase mở rộng từ phase trước). Câu tiếng Việt, term tiếng Anh giữ nguyên + giải thích trong ngoặc ở lần dùng đầu; Glossary đầy đủ ở Phần B. Log đủ số liệu + hạ tầng để **resume ở session khác**.
>
> Ngôn ngữ theo rule `CLAUDE.md` → "Writing docs & prose": câu tiếng Việt, term tiếng Anh giữ nguyên kèm nghĩa trong ngoặc lần đầu dùng.

---

# PHẦN A — Cách resume (đọc trước khi làm gì)

**Dữ liệu gốc:** MongoDB prod (VPS), đọc-only:
- `dbread` connection tên `pocketquant_prod` (đã add), HOẶC pymongo: `MONGODB_URL` (từ `.env`, không hardcode), db `pocketquant`.
- Collections: `backtest_runs`, `backtest_trades`, `bars` (symbol `BTCUSDT:BINANCE`; interval 1m/5m/15m/1h/4h/1d).
- Run phân tích: `_id = 019f36d2-5f4f-75cc-95c6-49a7496c3a86` — strategy `engulfing_pullback30_touch`, 1m, 2025-07-06 → 2026-07-06, vốn 10,000 USD, `slippage_bps=1`, `commission_bps=3`.

**Python:** `~/.claude/skills/.venv/bin/python3` (có numpy + pymongo).

**Toolkit (persist cạnh doc này, thư mục `scripts/`):**
- `pq_prefetch.py` — kéo bars đa timeframe (nhiều khung nến) + entries ra cache `/tmp/pq_cache/*.npz`. **Chạy đầu tiên** để dựng lại cache (/tmp là ephemeral — bị xoá giữa các session).
- `pq_lib.py` — lib chung. API tóm tắt:
  - `load_real_entries()` → dict(idx, price, islong, epoch, sl, tp, qty, pnl, comm) — 8,629 entry thật; `pnl` = gross USD (lãi/lỗ trước phí).
  - `detect_engulfing(tf, wick_pct=, min_body_atr=)` → dict entries (proxy đơn giản, sinh nhiều signal hơn strat thật).
  - `trend_up_at(tf, epoch, span=20)` → bool|None (trend khung cao có đang đi lên tại thời điểm đó không).
  - `atr(tf, period=14)`, `load_bars(tf)` → dict(ts, o, h, l, c, v).
  - `first_touch(entries, tf, sl_atr=|sl_bps=, tp_atr=|sl_R=|tp_bps=, maxbars=240, tie='SL')` → gross bps array. (first-touch = mô phỏng exit bằng cách quét nến sau entry xem chạm SL hay TP trước.)
  - `fixed_horizon(entries, tf, hbars)` → signed gross bps array. (fixed-horizon = thoát đúng h nến sau entry bất kể gì.)
  - `in_out_masks(entries)` → (in, out) split tại 2026-01-06 (chia dữ liệu: nửa đầu để tune, nửa sau để kiểm định).
  - `summarize(bps, friction='maker'|'taker'|'maker_rebate'|'zero'|float, hold_hours=, label=)`, `show(d)`.
  - Friction (tổng ma sát một vòng vào-ra) round-trip bps: `taker=11`, `maker=4`, `maker_rebate=−2`, `zero=0`; funding ≈ 1 bps/8h qua `hold_hours=`.
- `pq_atr_optimize.py`, `pq_entry_screen.py`, `pq_horizon_decay.py`, `pq_confirm_filtered.py` — các phân tích Phase 4–7.

**Chạy lại:** `python3 scripts/pq_prefetch.py` → `cd scripts && python3 pq_xxx.py`.

**Kết luận một dòng (nếu chỉ đọc một câu):** *Engulfing 1m không có edge (lợi thế thống kê) tự thân — đã chứng minh 5 cách. Thứ duy nhất còn edge trên dữ liệu chưa-tune (out-of-sample) là **trend-following khung cao** (Nhánh A — mạnh, nhưng chỉ là beta = ăn theo đà chung của thị trường) và **fade tín hiệu trễ ở 1m** (Nhánh E — đảo ngược tín hiệu; bền nhưng mỏng).*

---

# PHẦN B — Glossary (mọi term)

- **bps** (basis point) — phần vạn: 1 bps = 0.01%. Trên lệnh 1,000 USD, 1 bps = 0.10 USD.
- **notional** — giá trị danh nghĩa vị thế = giá × khối lượng. Phí và edge đo theo % của nó.
- **gross PnL / gross return** — lãi/lỗ trước phí (chỉ so giá vào với giá ra).
- **net PnL / net return** — lãi/lỗ sau phí (commission + slippage + funding).
- **commission** — phí trả sàn mỗi lần khớp, tính bps của notional.
- **slippage** — chênh lệch giá dự tính so giá khớp thật; mua khớp cao hơn, bán khớp thấp hơn.
- **friction** — tổng ma sát một vòng vào-ra = commission + slippage (+ funding nếu giữ lâu).
- **stop-loss (SL)** — mức giá tự thoát cắt lỗ khi giá đi ngược.
- **take-profit (TP)** — mức giá tự thoát chốt lời khi giá đi thuận.
- **win rate** — tỉ lệ lệnh thắng trên tổng lệnh.
- **break-even win rate** — tỉ lệ thắng tối thiểu để hoà vốn với một R:R cho trước.
- **R:R (risk:reward)** — TP cách entry gấp mấy lần SL cách entry.
- **R-multiple** — kết quả một lệnh đo bằng đơn vị rủi ro: +2R = lãi gấp đôi khoảng SL; −1R = mất đúng khoảng SL.
- **EV (expected value)** — giá trị kỳ vọng: lãi/lỗ trung bình mỗi lệnh về dài hạn. "Highest-EV" = kỳ vọng lời cao nhất.
- **ATR (average true range)** — biên độ dao động thực trung bình N nến; đo mức nhiễu/biến động hiện thời.
- **MFE (maximum favorable excursion)** — sau khi vào lệnh, giá đi thuận xa nhất bao nhiêu.
- **MAE (maximum adverse excursion)** — sau khi vào lệnh, giá đi nghịch xa nhất bao nhiêu.
- **edge** — lợi thế thống kê: lãi trung bình mỗi lệnh nếu không mất phí (bps).
- **edge-to-cost ratio (e/c)** — edge chia friction; phải > 1 mới có cơ lời sau phí.
- **maker** — lệnh chờ (limit) thêm thanh khoản; phí thấp (Binance futures ~2 bps/chiều).
- **taker** — lệnh thị trường (market) lấy thanh khoản; phí cao (~4.5 bps/chiều).
- **rebate** — hoàn phí: bậc VIP cao sàn TRẢ tiền cho maker (phí âm).
- **funding fee** — với perpetual (perp/SWAP), khoản trả định kỳ mỗi 8h khi giữ vị thế.
- **first-touch (mô phỏng exit)** — quét nến sau entry, xem chạm SL hay TP trước; chạm cả hai trong một nến thì tính SL (bi quan).
- **fixed-horizon (mô phỏng exit)** — thoát đúng h nến sau entry bất kể gì; dùng đo edge theo thời gian giữ.
- **walk-forward** — chia dữ liệu: nửa đầu (in-sample) dò tham số, nửa sau (out-of-sample) kiểm định.
- **in-sample (IN)** — phần dữ liệu dùng tune tham số. **out-of-sample (OOS/OUT)** — phần chưa từng tune; số ở đây mới đáng tin.
- **overfit / curve-fit** — khớp tham số quá mức vào nhiễu quá khứ; đẹp IN, sập OOS.
- **trend-following / momentum** — đi theo chiều xu hướng; lời từ giá tiếp tục trôi cùng hướng.
- **mean-reversion / contrarian / fade** — đi NGƯỢC tín hiệu, cược giá quay đầu; "fade" = làm ngược cú signal.
- **continuation** — tín hiệu kỳ vọng giá tiếp diễn cùng chiều.
- **aligned / counter-trend** — entry cùng chiều trend khung lớn (aligned) hay ngược (counter).
- **alpha vs beta** — alpha = edge riêng của tín hiệu; beta = lời do thị trường trôi chung (giữ long trong năm tăng cũng lời không cần tín hiệu).
- **control (thí nghiệm)** — nhóm đối chứng (vd entry ngẫu nhiên cùng chiều trend) để xem tín hiệu có hơn ngẫu nhiên không.
- **regime** — chế độ thị trường trong một giai đoạn: trending (một chiều rõ) vs sideway/chop (đi ngang, nhiễu). Edge có thể sống ở regime này, chết ở regime kia.
- **fill probability** — xác suất lệnh limit thật sự khớp; maker có rủi ro không khớp, nhất ở nến chạy nhanh.
- **adverse selection** — bất lợi khi lệnh limit chỉ khớp đúng lúc thị trường sắp đi ngược mình.
- **drawdown** — mức sụt vốn từ đỉnh xuống đáy; đo rủi ro chịu đựng.
- **profit factor** — tổng lãi gộp chia tổng lỗ gộp; > 1 là lời.
- **timeframe (TF)** — khung nến: 1m = 1 phút, 1h = 1 giờ, 1d = 1 ngày.
- **signed forward return** — lãi tương lai TÍNH THEO CHIỀU LỆNH tại một mốc thời gian sau entry (dương = giá đi đúng hướng cược).
- **autocorrelation** — các quan sát gần nhau bị trùng thông tin → số mẫu "hiệu dụng" nhỏ hơn số đếm.

---

# PHẦN C — Trình tự điều tra (evolving)

Bảng tiến trình — mỗi phase nảy sinh từ kết luận phase trước:

| Phase | Câu hỏi kích hoạt | Kết luận | Dẫn tới |
|---|---|---|---|
| 1 | Config phí sai/quá cao? | Không — tính đúng, mức thực tế | Phase 2 |
| 2 | Sao phí nuốt lãi? | gross đã âm TRƯỚC phí; overtrading (giao dịch quá nhiều) | Phase 3 |
| 3 | Vì sao edge âm? | stop 14 bps quá chật + slippage bào | Phase 4 |
| 4 | ATR có cứu được? | Cả grid âm; entry vô hướng (MFE≈MAE) | Phase 5 |
| 5 | Filter nào tạo hướng? | Trend khung 1h → +3.6 bps | Phase 6 |
| 6 | Edge có bền out-of-sample? | Bền nhưng < friction | Phase 7 |
| 7 | Giữ lâu (cross-TF) tăng edge? | Chững ~4 bps; 16h+ là trend beta | Phase 8 |
| 8 | Còn hướng nào? (tree-of-thoughts) | 5 nhánh: 3 DEAD, 2 survivor | Phase 9 |
| 9 | Hai survivor là gì? | A trend-follow 1h; E fade @1m | Phase 10 |

---

## Phase 1 — Câu hỏi ban đầu: "config phí có sai không?"

Người dùng nghi cấu hình và cách tính `commission` (phí sàn) + `slippage` (trượt giá) sai, vì phí quá lớn so với `gross PnL` (lãi trước phí). Điều tra bắt đầu từ run thật trên VPS.

## Phase 2 — Cost analysis: config ĐÚNG, gross đã âm trước phí

Số liệu run thật (`backtest_runs` + `backtest_trades`):

| Chỉ số | Giá trị |
|---|---|
| Số trade (round-trip = một vòng vào-ra) | 8,629 (~24 lệnh/ngày) |
| gross PnL (trước phí) | **−1,039 USD** |
| total commission | −3,781 USD |
| net PnL (sau phí) | **−4,820 USD (−48.2%)** |
| notional trung bình/lệnh | 730 USD |
| commission thực tế | 6.00 bps notional khứ hồi = đúng `3 bps × 2 fill` |
| edge gộp trung bình/lệnh | **−1.7 bps** (âm) |
| win rate | 42.9% · profit factor 0.825 |
| sharpe / sortino / max drawdown | −32.7 / −26.6 / −48.2% |

Fee sensitivity (thử đổi giả định phí trên cùng bộ lệnh):

| Giả định phí (mỗi chiều) | net PnL |
|---|---|
| zero | −1,039 USD (−10.4%) |
| maker 2 bps | −3,560 USD (−35.6%) |
| **current 3 bps** | **−4,820 USD (−48.2%)** |
| taker 4.5 bps | −6,710 USD (−67.1%) |

**Kết luận Phase 2:**
- Phép tính đúng tuyệt đối: 6.00 bps = 3 bps/chiều × 2 lần khớp. Không bug.
- Mức 3 bps thực tế, thậm chí rộng rãi (Binance futures maker 2 bps, taker 4.5 bps). Strategy vào bằng lệnh `market` → thực tế là taker 4.5 bps > 3 bps → backtest đang LẠC QUAN, không phải quá cao.
- **Thủ phạm thật:** gross PnL đã âm −1,039 USD *trước phí một xu nào*. Kể cả phí = 0 vẫn lỗ −10.4%. Phí chỉ phơi bày một strategy vốn thua. Hạ config phí cho đẹp = tự lừa dối.

## Phase 3 — Chẩn đoán edge âm: stop quá chật + slippage bào mòn

Nghịch lý: hình học payoff (tỉ lệ lời/lỗ trên giấy) dương nhưng thực tế âm.

| Chỉ số | Giá trị | Ý nghĩa |
|---|---|---|
| win rate gộp | 42.9% | |
| R:R trung bình (planned) | 1.57 | |
| break-even win rate | 38.9% | thắng CAO hơn ngưỡng → trên giấy phải lời |
| kỳ vọng nếu đạt kế hoạch | +0.10 R/lệnh | dương |
| **R-multiple thực tế trung bình** | **−0.115** | âm — ngược dấu |
| median R thực tế | −1.045 | quá nửa lệnh ăn trọn stop |
| **SL distance median** | **14.1 bps** của giá | cực chật |
| duration median / mean | 12 phút / 22.8 phút | |

Phân bố kết cục:

| Exit | Số lệnh | avg |
|---|---|---|
| TP hit | 3,706 (42.9%) | +1.32 USD |
| SL hit | 4,923 (57.1%) | −1.21 USD |

| R-multiple thực tế | Tỉ lệ |
|---|---|
| ≤ −1R (ăn trọn stop) | 57.1% |
| 0..1R | 29.6% (TP "1R" bị slippage bào còn ~0.86R) |
| 1..2R | 9.1% |
| ≥ 2R | 4.3% |

Long/Short đối xứng cùng lỗ (LONG −540.6, SHORT −498.4) → lỗi cấu trúc, không phải lệch một chiều.

**Cơ chế:** SL 14 bps nằm trong biên nhiễu khung 1m → 57% bị quét stop bởi dao động ngẫu nhiên. `slippage` khứ hồi ~2 bps = 14% của một đơn vị rủi ro, kéo cả lệnh thắng lẫn thua xuống ~0.14R. Sự bào mòn bất đối xứng này lật +0.10 (giấy) thành −0.115 (thực). **Kim chỉ nam: `edge-to-cost ratio` (edge chia friction) — khi risk chỉ 14 bps mà friction 2–6 bps, ma sát ăn 15–40% edge, không strategy nào sống.**

## Phase 4 — ATR grid: cả lưới âm; entry vô hướng

Giả thuyết người dùng: dùng `ATR` (biên độ dao động) cho SL/TP sẽ cứu, `SL = ATR × weight` (đề xuất 1.27). Kiểm chứng trên 8,629 entry + 526,641 nến, mô phỏng `first-touch`.

`ATR(14)` trên nến 1m BTC (bps của giá): p10 = 2.0 · **median = 3.5** · mean = 4.3 · p90 = 7.7. **Cực nhỏ.**

| ATR weight | SL distance | Friction 6 bps chiếm |
|---|---|---|
| **1.27** (đề xuất) | **4.4 bps** | **136% risk unit** ⛔ nhỏ hơn cả friction |
| 2.0 | 6.9 bps | 86% |
| 3.0 | 10.4 bps | 58% |
| 5.0 | 17.4 bps | 35% |

Quét grid SL 1.5–5×ATR × TP {3–14×ATR, 1.5–3R} (first-touch): **mọi ô gross âm.** Ô tốt nhất (SL 2×ATR, TP 3R) = **−0.29 bps** trước phí; ô tệ nhất (SL 5×ATR, TP 14×ATR) = −1.84 bps.

Bằng chứng độc lập — excursion (giá đi xa nhất sau entry) theo đơn vị ATR (window 240 nến):

| | p25 | median | p75 | p90 |
|---|---|---|---|---|
| **MAE** (biên nghịch) | 4.3 | **9.1** | 17.7 | 30.4 ATR |
| **MFE** (biên thuận) | 3.7 | **8.4** | 16.5 | 29.5 ATR |

**MFE ≈ MAE** (nghịch hơi lớn hơn) = dấu vân tay của entry **vô hướng** (không dự báo được chiều giá). Exit không thể tạo edge mà entry vốn không có.

Volatility floor (bỏ lệnh khi ATR nhỏ) trên ô tốt nhất:

| Sàn ATR | Giữ lại | gross | net@maker |
|---|---|---|---|
| không lọc | 100% | −0.29 | −4.29 |
| ≥ 5 bps | 50.8% | −0.05 | −4.05 |
| ≥ 8 bps | 24.3% | **+1.18** | −2.82 |

Chỉ khi bỏ 76% số lệnh, giữ nhóm biến động cao nhất, gross mới dương yếu (+1.18) nhưng vẫn dưới friction maker 4 bps.

**Kết luận Phase 4:** không trọng số ATR nào cứu được; lỗi nằm ở ENTRY (vô hướng), không phải EXIT. Cơ chế giả thuyết: engulfing 1m hoàn tất + chờ pullback 30% thì sóng đã đi xong → tín hiệu vào TRỄ.

## Phase 5 — Entry filter screen: trend khung 1h tạo được hướng

Đo `signed forward return` (lãi tương lai theo chiều lệnh) tại 15/30/60/120 phút, thử nhiều filter:

### Cách đọc `bps` và `n` (áp dụng mọi bảng Phase 5)

- **`bps`** = trung bình cộng của `signed forward return` tại mốc thời gian ghi ở cột (vd 60 phút), tính **theo chiều lệnh**, đơn vị bps (phần vạn), **gross** (trước phí). Dương = trung bình giá đi ĐÚNG chiều cược; âm = đi NGƯỢC. Vd +12.16 = mỗi lệnh trung bình lời 12.16 bps gross sau 60 phút (lệnh 1,000 USD ≈ +1.22 USD trước phí).
- **`n`** = số entry (lệnh) rơi vào bucket đó = `sample size`. `n` càng lớn, `bps` càng đỡ nhiễu. Cộng dọc cột `n` ≈ tổng số lệnh của bảng.
- **Hai bảng 24 giờ khác nhau ở TẬP LỆNH, không ở cách đo:** baseline = TẤT CẢ entry (n≈8,629, phần lớn `bps` âm — vô hướng); aligned = chỉ entry cùng chiều trend 1h (n≈4,318 ≈ nửa baseline, phần lớn `bps` dương). Chênh lệch cùng-giờ giữa hai bảng (vd NY 10:00: baseline −8.33 → aligned +11.70) chính là **sức phân tách của trend filter**.

### Thuật toán định lượng (từ `scripts/pq_entry_screen.py`)

Pipeline dựng số cho cả hai bảng:

```
8,629 entry thật (backtest_trades)
    │  mỗi entry:
    ├─ trend 1h: lấy nến 1h ĐÓNG gần nhất trước entry_time (bisect_right−1, no-lookahead);
    │            h1up = close_1h > EMA20(close_1h)  → True=lên / False=xuống
    ├─ aligned_1h = (islong == h1up)   # long&lên hoặc short&xuống → True
    ├─ signed fwd return @h nến: sgn=(+1 long / −1 short); fwd = sgn·(close[i+h]−ep)/ep·1e4  (bps gross)
    │
    ├─ lọc aligned==True  → 4,318 lệnh → mean fwd@60m = +3.58  ┐ hai nhánh
    └─ lọc aligned==False → 4,311 lệnh → mean fwd@60m = −7.05  ┘ đối xứng quanh baseline −1.73
    │
    └─ bảng 24 giờ: gom entry theo dt.hour → mean(fwd@60m) = ô `bps`, count = ô `n` (in khi n≥100)
```

Ba chi tiết quyết định tính đúng đắn:
- `sgn·(…)` chuẩn hoá long/short về cùng thước "đúng hướng cược" → cộng gộp được.
- `/ep·1e4` đổi USD → **bps của notional** (÷ giá ×10,000) để so sánh across giá/thời điểm.
- Nến 1h phải **đã đóng** trước entry (bisect_right−1); dùng nến đang chạy = lookahead leak.

### Vì sao trend 1h "tạo được hướng" (cơ chế)

Filter 1h KHÔNG dự báo giá — nó **lọc bỏ nhóm entry cấu trúc-sai**. Engulfing là tín hiệu `continuation` (kỳ vọng tiếp diễn): chỉ có giá trị khi nối tiếp một xu hướng LỚN hơn.
- **Aligned** (long khi 1h lên): engulfing = pullback trong uptrend kết thúc → giá chạy tiếp → **+3.58**.
- **Counter** (long khi 1h xuống): engulfing = bull trap trong downtrend → giá quay đầu → **−7.05**.

**Counter âm mạnh là bằng chứng quyết định:** nếu filter vô dụng, cả hai nhánh phải xấp xỉ baseline (−1.73). Thực tế tách thành +3.58 / −7.05 — gương đối xứng quanh baseline. Độ tách đó chứng minh chiều trend 1h mang **thông tin thật** về kết cục engulfing (control, không phải ngẫu nhiên). Phải là khung CAO hơn: đo trend trên chính khung 1m (`aligned_m1`, EMA200) chỉ ra −1.7 bps — cùng tầng nhiễu với tín hiệu nên vô dụng; khung 1h đứng ngoài nhiễu 1m mới làm "bối cảnh" phán xử được.

> Nghịch lý cốt lõi: đo được hướng ≠ kiếm được tiền. Edge sau lọc (~3.5 bps) vẫn < friction maker (4 bps) → net âm OOS (Phase 6).

| Tập con entry | 60 phút | Số lệnh |
|---|---|---|
| Tất cả (baseline) | −1.73 | 8,629 |
| **Aligned trend khung 1h** (cùng chiều trend 1h) | **+3.58** | 4,318 |
| Counter trend khung 1h (ngược trend 1h) | −7.05 | 4,311 |
| Aligned 1h + ATR ≥ 5 bps | **+4.42** | 2,189 |
| Aligned 1h + volume z ≥ 1 | +3.42 | 483 |
| Trend EMA200 trên khung 1m | −1.7 | — (vô dụng — phải khung CAO hơn) |
| Fade tất cả (đảo ngược mọi tín hiệu) | +1.73 | 8,629 |
| Volume z ≥ 2 (60m) | +1.58 (→ +3.68 @120m) | 430 |

Theo giờ (60m signed forward return, bps) — bucket theo **giờ New York địa phương** (`America/New_York`, DST-aware) để mỗi hàng thẳng hàng với phiên cash equities Mỹ (mở 9:30 sáng ET quanh năm) bất kể mùa. Vì NY theo DST, một giờ NY map sang **2 giờ UTC** tùy mùa (NY+5 mùa đông EST / NY+4 mùa DST hè EDT), nên cột **UTC** và **VN** (Việt Nam, UTC+7, không DST) hiển thị **cả 2 giờ đồng hồ** mà bucket đó thực rơi vào. (New York mở cửa là **ET** — tức EST mùa đông, EDT mùa hè; ~8/12 tháng là EDT.)

Tóm tắt (aligned, mạnh nhất): tốt **NY 09:00** (mở phiên; UTC 13:00/14:00, VN 20:00/21:00) +12.16, **NY 10:00** (UTC 14:00/15:00, VN 21:00/22:00) +11.70, NY 12:00 (UTC 16:00/17:00) +7.57; tệ NY 17:00 (UTC 21:00/22:00, VN 04:00/05:00) −3.79, NY 16:00 (UTC 20:00/21:00) −2.40.

**Bảng đầy đủ 24 giờ — baseline (ALL entries, n≈8,629):**

| NY | UTC | VN | bps | n |
|---|---|---|---|---|
| 00:00 | 04:00/05:00 | 11:00/12:00 | −3.50 | 336 |
| 01:00 | 05:00/06:00 | 12:00/13:00 | −0.31 | 368 |
| 02:00 | 06:00/07:00 | 13:00/14:00 | −2.87 | 346 |
| 03:00 | 07:00/08:00 | 14:00/15:00 | −0.57 | 356 |
| 04:00 | 08:00/09:00 | 15:00/16:00 | +0.23 | 379 |
| 05:00 | 09:00/10:00 | 16:00/17:00 | −3.79 | 330 |
| 06:00 | 10:00/11:00 | 17:00/18:00 | +1.59 | 362 |
| 07:00 | 11:00/12:00 | 18:00/19:00 | −1.35 | 362 |
| 08:00 | 12:00/13:00 | 19:00/20:00 | −0.10 | 358 |
| 09:00 | 13:00/14:00 | 20:00/21:00 | −1.68 | 384 |
| 10:00 | 14:00/15:00 | 21:00/22:00 | **−8.33** | 358 |
| 11:00 | 15:00/16:00 | 22:00/23:00 | −1.31 | 337 |
| 12:00 | 16:00/17:00 | 23:00/00:00 | −3.80 | 373 |
| 13:00 | 17:00/18:00 | 00:00/01:00 | −4.12 | 369 |
| 14:00 | 18:00/19:00 | 01:00/02:00 | −6.40 | 330 |
| 15:00 | 19:00/20:00 | 02:00/03:00 | +0.37 | 383 |
| 16:00 | 20:00/21:00 | 03:00/04:00 | −2.97 | 340 |
| 17:00 | 21:00/22:00 | 04:00/05:00 | −2.19 | 386 |
| 18:00 | 22:00/23:00 | 05:00/06:00 | −2.20 | 358 |
| 19:00 | 23:00/00:00 | 06:00/07:00 | +0.10 | 364 |
| 20:00 | 00:00/01:00 | 07:00/08:00 | **+2.95** | 363 |
| 21:00 | 01:00/02:00 | 08:00/09:00 | −3.32 | 366 |
| 22:00 | 02:00/03:00 | 09:00/10:00 | −1.86 | 376 |
| 23:00 | 03:00/04:00 | 10:00/11:00 | +3.25 | 345 |

**Bảng đầy đủ 24 giờ — 1h-trend ALIGNED (subset có edge thật, n≈4,318):**

| NY | UTC | VN | bps | n |
|---|---|---|---|---|
| 00:00 | 04:00/05:00 | 11:00/12:00 | +0.55 | 159 |
| 01:00 | 05:00/06:00 | 12:00/13:00 | +1.81 | 181 |
| 02:00 | 06:00/07:00 | 13:00/14:00 | +2.69 | 185 |
| 03:00 | 07:00/08:00 | 14:00/15:00 | +6.27 | 181 |
| 04:00 | 08:00/09:00 | 15:00/16:00 | +6.82 | 190 |
| 05:00 | 09:00/10:00 | 16:00/17:00 | +1.63 | 156 |
| 06:00 | 10:00/11:00 | 17:00/18:00 | +5.07 | 185 |
| 07:00 | 11:00/12:00 | 18:00/19:00 | −0.09 | 167 |
| 08:00 | 12:00/13:00 | 19:00/20:00 | +4.03 | 183 |
| 09:00 | 13:00/14:00 | 20:00/21:00 | **+12.16** | 182 |
| 10:00 | 14:00/15:00 | 21:00/22:00 | +11.70 | 158 |
| 11:00 | 15:00/16:00 | 22:00/23:00 | +6.87 | 153 |
| 12:00 | 16:00/17:00 | 23:00/00:00 | +7.57 | 184 |
| 13:00 | 17:00/18:00 | 00:00/01:00 | +3.12 | 167 |
| 14:00 | 18:00/19:00 | 01:00/02:00 | −0.54 | 156 |
| 15:00 | 19:00/20:00 | 02:00/03:00 | −1.54 | 189 |
| 16:00 | 20:00/21:00 | 03:00/04:00 | −2.40 | 182 |
| 17:00 | 21:00/22:00 | 04:00/05:00 | **−3.79** | 209 |
| 18:00 | 22:00/23:00 | 05:00/06:00 | +3.79 | 182 |
| 19:00 | 23:00/00:00 | 06:00/07:00 | +0.87 | 184 |
| 20:00 | 00:00/01:00 | 07:00/08:00 | +3.45 | 195 |
| 21:00 | 01:00/02:00 | 08:00/09:00 | +2.88 | 192 |
| 22:00 | 02:00/03:00 | 09:00/10:00 | +6.47 | 201 |
| 23:00 | 03:00/04:00 | 10:00/11:00 | +7.13 | 197 |

Đọc nhanh (aligned): cụm mạnh nhất **NY 09:00–12:00** (mở phiên + buổi sáng cash equities Mỹ; VN 20:00–00:00) với đỉnh NY 09:00 +12.16 và NY 10:00 +11.70 — thẳng hàng với giờ mở cửa 9:30 ET. Yếu nhất NY 14:00–17:00 (chiều Mỹ, VN 01:00–05:00 đêm khuya).

**Vì sao bảng giờ là MÔ TẢ, không phải tín hiệu tradeable (ba lỗi cộng dồn):**

1. **In-sample cherry-picking** (chọn cherry sau khi thấy đáp án): bảng tính trên cả năm gộp IN+OOS. Nhìn thấy "NY 09:00 +12.16" rồi quyết "trade giờ đó" = chọn winner *sau khi* đã biết kết quả, không chứng minh gì về tương lai.
2. **Multiple-testing artifact** (ảo giác do thử nhiều): chia 24 bucket = 24 phép thử song song. Với n≈180/bucket và `std` forward-return 1m rất lớn (vài chục bps), thuần ngẫu nhiên cũng đẻ ra vài bucket +10 và vài bucket −8. Đỉnh +12.16 phần lớn là noise được khuếch đại bởi 24 lần thử.
3. **Bằng chứng OOS đã đo (Nhánh C, Phase 8), không phải suy đoán:** chọn giờ tốt CHỈ trên IN rồi áp nguyên lên OOS → `good_hours` IN +1.77 / **OOS −0.06**; `good_hours ∩ ATR≥5` IN +4.54 / **OOS −0.11**. Correlation IN/OUT chỉ 0.17–0.36 (thứ tự giờ tốt/xấu nửa đầu gần như không dự báo nửa sau); filter càng chặt overfit gap càng to.

→ "Chỉ trade NY 09:00–10:00" = curve-fit vào quá khứ. Bảng dùng để **hiểu** thị trường (phiên Mỹ mở → biến động cao → engulfing rõ hơn), KHÔNG để làm rule vào lệnh. Gốc rễ: một năm một symbol còn quá ít cho việc chia 24 bucket.

**Kết luận Phase 5:** engulfing 1m là tín hiệu **continuation** (kỳ vọng giá tiếp diễn cùng chiều), chỉ có hướng khi aligned với trend khung LỚN hơn. Counter-trend âm mạnh = control (nhóm đối chứng) chứng minh filter có sức phân tách thật.

## Phase 6 — Walk-forward: edge THẬT nhưng dưới friction

Tập aligned 1h + ATR ≥ 5 (2,189 lệnh), 6 tháng đầu tune / 6 tháng sau validate, exit `first-touch`:

| | In-sample (IN, dữ liệu tune) | Out-of-sample (OOS, dữ liệu chưa tune) |
|---|---|---|
| gross bps/lệnh (ô tốt nhất) | +5 đến +6 | +1.2 đến +2.5 |
| net @ maker (−4bps) | +1 đến +2 | **−1.5 đến −2.8** |
| net @ taker (−11bps) | — | ≈ −9 |

- Edge có hướng **bền OOS** (gross vẫn dương, cùng dấu với IN) → không curve-fit.
- Nhưng edge (~2 bps) **< friction maker 4 bps** → net âm OOS.
- Ô tốt nhất IN +2.06 rớt −2.82 OOS (tune exit bị overfit).

**Giới hạn cấu trúc:** trên khung 1m BTC, sóng tự nhiên (~3.5 bps) < friction (4 bps maker). Edge < cost là bất biến của khung thời gian.

## Phase 7 — Cross-timeframe: edge chững, 16h+ hoá trend beta

Câu hỏi: vào trên 1m nhưng giữ lâu / thoát theo khung cao có tăng edge? gross theo thời gian giữ (aligned 1h):

| Giữ | gross | net@maker | Đọc |
|---|---|---|---|
| 30 phút | +2.61 | −1.39 | edge engulfing thật |
| 1h | +3.58 | −0.42 | |
| 2h | +3.31 | −0.69 | plateau (chững lại) ~+3.5 |
| 4h | +3.68 | −0.32 | vẫn ≈ friction |
| 8h | +2.95 | −1.05 | |
| **16h** | **+7.84** | **+3.84** | nhảy vọt — nhưng… |
| 24h | +5.85 | +1.85 | |
| 48h | +5.99 | +1.99 | |

- **1h–4h:** edge engulfing thật, plateau ~+3.5 bps ≈ friction. Giữ lâu hơn scalp 12 phút thì tốt hơn nhưng chạm cùng bức tường.
- **16h+:** con số dương to là **trend beta** (lời do đà thị trường trôi chung), không phải edge engulfing (baseline không lọc ở 16h cũng dương +1.33). Chưa trừ funding. Phương sai cao (ATR≥5 subset: 8h −0.97, 48h −7.38).

**Kết luận Phase 7:** cross-timeframe đúng hướng về structure (strategy đa timeframe, giữ dài, exit theo cấu trúc khung cao, thêm funding) nhưng edge engulfing thật vẫn ≈ friction; phần lời giữ-lâu là trend beta, cần thiết kế lại như trend-following.

## Phase 8 — Tree-of-thoughts: 5 nhánh song song

Mở 5 agent song song, mỗi agent test một giả thuyết trên cache, walk-forward, brutally honest.

### Nhánh A — Engulfing đa timeframe

Detect engulfing trên 5m/15m/1h/4h, filter theo trend khung cao hơn (5m→1h, 15m→4h, 1h→1d, 4h→1d), walk-forward:

| TF | best config | n_out | gross | net@maker | net@taker | e/c@mk | Verdict |
|---|---|---|---|---|---|---|---|
| 5m | fixed-horizon 24 (2h) | 5159 | +5.37 | +1.37 | −5.63 | 1.34 | MARGINAL (chỉ sống maker) |
| 15m | fixed-horizon 24 (6h) | 1718 | +10.36 | +6.36 | −0.64 | 2.59 | MARGINAL→DEAD ở taker |
| **1h** | **first-touch SL3×ATR TP3R** | 418 | +72.92 | **+68.92** | **+61.92** | 18.2 | **VIABLE (sống cả maker lẫn taker)** |
| 1h | fixed-horizon 24 (24h) | 416 | +35.9 | **+31.9** | **+24.9** | 9.0 | VIABLE |
| 4h | fixed-horizon 6 (24h) | 116 | +6.53 | +2.53 | −4.47 | 1.63 | MARGINAL (n mỏng) |

Control (1h, fixed-horizon 24, OOS): **aligned +35.90 / unaligned (ALL) +1.71 / counter −33.42** → gương đối xứng hoàn hảo. Edge scale đều theo thời gian giữ (h6 +20, h12 +29, h24 +36, h48 +64 gross) = trend-drift capture (ăn đà trôi của xu hướng).
→ **Edge là TREND FILTER 1d, KHÔNG phải engulfing.** Engulfing chỉ là cò bấm.

### Nhánh B — Trend-follow 16h+ @1m: alpha hay beta?

Aligned 1h subset, so với **control ngẫu nhiên** (entry random cùng chiều trend 1h), net@maker + funding:

| Giữ | ENG net | CONTROL net | ALPHA (eng−ctrl) |
|---|---|---|---|
| 4h | −1.32 | −0.25 | −1.06 |
| 8h | −2.05 | +0.82 | −2.86 |
| **16h** | **+1.84** | **+1.83** | **+0.01** |
| 24h | −1.15 | −1.24 | +0.09 |
| 48h | −4.01 | +0.18 | −4.20 |

Con số dương duy nhất (16h +1.84) bị control ngẫu nhiên khớp y hệt (+1.83) → alpha (edge riêng của tín hiệu) = +0.01. Walk-forward ALPHA_OUT âm mọi horizon trừ +0.49 (24h, chỉ là noise). Funding lật 24h/48h thành âm. Bản thân trend-beta cũng fail walk-forward ở 1m (IN âm −9..−12, chỉ dương nửa OOS).
→ **DEAD như một engulfing strategy** (là beta, không alpha).

### Nhánh C — Session / time-of-day filter

Aligned subset, chọn giờ tốt trên IN-sample, áp OOS:

| Config | IN net@mk | OUT net@mk | n_out |
|---|---|---|---|
| baseline aligned (fh60) | −0.37 | −0.47 | 2174 |
| good_hours (18h) | +1.77 | **−0.06** | 1623 |
| good_hours ∩ ATR≥5 | +4.54 | **−0.11** | 940 |

Overfit gap: filter càng chặt càng sập (IN +8.54 → OOS +3.89). Corr IN/OUT chỉ 0.17–0.36 (tín hiệu giờ rất mờ, ~0.4 bps OOS). Weekday (lọc theo ngày trong tuần) vô dụng.
→ **DEAD / overfit** — không config nào net > 0 bền OOS.

### Nhánh D — Maker/limit + rebate re-pricing

gross bps từ dữ liệu thật, sweep friction tìm break-even:

| Set | gross IN | gross OUT |
|---|---|---|
| FULL (tất cả) | −1.58 | −1.66 |
| ALIGNED | +0.49 | **+0.08** |

net aligned: maker(4) IN −3.51 / OUT −3.92; zero(0) +0.49 / +0.08; rebate(−2) +2.49 / +2.08.
Break-even friction ≈ **0 bps** (aligned OOS +0.08 nằm trong 1 SE của zero: std 21, n 2174, SE ≈ 0.45). Ở maker chuẩn (rt 4) → −3.92 OOS. Dương chỉ khi rebate = **rebate-harvesting** (kiếm lời từ hoàn phí), không phải alpha. `fill probability` (rủi ro lệnh limit không khớp) chưa mô phỏng — chính chỗ winner sống hay chết.
→ **DEAD** — maker không cứu; cần phí ≤ 0 mới hoà, mà lúc đó "edge" thực chất là rebate.

### Nhánh E — Multi-filter stack + fade

Stack `aligned + atr_bps≥X + vol_z≥Y`: **mọi combo vol_z sập OOS** (IN +5..+9 → OOS âm) = multiple-testing artifact (ảo giác do thử quá nhiều tổ hợp); chỉ `atr≥8` sống marginally (+0.25 OOS).

**FADE (đảo ngược tín hiệu trễ) — nguồn edge thật:**

| Leg | IN net | OUT net |
|---|---|---|
| counter-trend FOLLOW (theo tín hiệu) | −11.6 | −12.5 |
| **counter-trend FADE** (đảo ngược tín hiệu) | **+1.64** | **+2.45** |
| aligned FOLLOW | −1.37 | −1.47 |

Combined `{aligned→follow} ∪ {counter→fade}` (cùng trend 1h thì theo tín hiệu; ngược trend 1h thì đảo ngược):

| Config | IN net@mk | OUT net@mk | n_out |
|---|---|---|---|
| ALL follow (baseline) | −6.51 | −6.95 | 4338 |
| alignFollow ∪ counterFade | +0.14 | +0.49 | 4338 |
| + ATR≥5 | +0.56 | +1.41 | 2454 |
| **+ ATR≥8** | **+1.69** | **+1.73** | **1251** |

Friction sensitivity (combined): rebate +6.49 / maker +0.49 / taker −6.51.
→ **MARGINAL (bền)** — edge thật, IN≈OUT, cơ chế đúng (fade các tín hiệu trễ), nhưng ~1.7 bps quá mỏng, chỉ sống maker.

### Meta-finding Phase 8

> **Pattern engulfing bản thân ~0 alpha out-of-sample.** Mọi edge quy về (1) trend-following (theo trend khung cao) hoặc (2) fade tín hiệu trễ (đảo ngược). Cùng một sự thật nhìn hai mặt: theo trend, và fade nhiễu ngược trend.

## Phase 9 — Hai survivor (config chính xác)

### A — Trend-following khung 1h (edge lớn, là beta, phải rời 1m)
- **Config:** direction = chiều trend khung 1d (close > EMA20 trên 1d → long); entry = engulfing trigger trên 1h; exit = fixed-horizon giữ 24×1h (24h). Alternative: first-touch SL 3×ATR, TP 3R → net +68.9/+61.9 (hold nhiều ngày, exit hỗn hợp).
- **Số OOS:** gross +35.9 · net@maker +31.9 · net@taker +24.9 · edge-to-cost 9.0 · win rate 0.58 · n 416. Giữ vững walk-forward cả hai nửa.
- **Bản chất:** trend-following (momentum); engulfing chỉ là cò bấm.
- **Rủi ro:** cả năm test là regime trending (thị trường một chiều rõ); năm sideway/chop (đi ngang, nhiễu) nhiều khả năng sập. Chưa validate đa regime / đa symbol.

### E — Fade tín hiệu trễ, giữ khung 1m (edge nhỏ, bền)
- **Config:** `{aligned → follow} ∪ {counter-trend → fade}` (cùng trend 1h thì theo; ngược trend 1h thì ĐẢO chiều), lọc `atr_bps ≥ 8`, exit fixed-horizon 60m.
- **Số OOS:** net@maker +1.73 · n 1251 · IN +1.69 ≈ OUT (ổn định thật). Fade counter-trend gross +7.4 (~2× aligned-follow) là nguồn edge chính.
- **Bản chất:** engulfing 1m là tín hiệu **contrarian** (đi ngược, tức fade), không phải continuation.
- **Rủi ro:** ~1.7 bps quá mỏng; chỉ sống maker (taker −6.51 giết); thao tác đảo ngược tín hiệu gốc gượng gạo; fill probability chưa mô phỏng.

---

# PHẦN D — Khuyến nghị & lựa chọn tiếp

| Nếu bạn... | Đi hướng | Bản chất |
|---|---|---|
| Chấp nhận rời 1m | **A** — reframe thành trend-following khung 1h, validate đa regime + đa symbol, thêm drawdown control | Highest-EV (kỳ vọng lời cao nhất), nhưng là momentum không phải engulfing |
| Bắt buộc giữ 1m | **E** — chiến lược fade engulfing trễ, execution maker | Edge thật nhưng mỏng, treat như research lead (manh mối để đào tiếp) |
| — | Bỏ engulfing như directional signal (tín hiệu chỉ hướng) độc lập — đã chứng minh 5 cách | — |

**Đóng dứt khoát:** B (trend-beta-không-alpha), C (session overfit), D (maker-không-cứu).

Option triển khai (chưa chọn):
- Validate A đa regime / đa symbol trước (DB chỉ có BTC — cần thêm symbol).
- Đào sâu E: tối ưu exit/filter, mô phỏng fill probability, xem có nâng +1.73 lên mức tradeable không.
- Lập plan build strategy (A hoặc E) vào hệ thống + backtest engine thật.

Nếu build cross-timeframe / trend-following: đây là thay đổi **structure level** — strategy đa timeframe (1m/1h/1d), giữ lệnh dài, exit theo cấu trúc khung cao, cost model thêm funding.

---

# PHẦN E — Câu hỏi chưa giải quyết

- A: trend-follow 1h giữ edge trên symbol khác / năm không-trending không? Cần multi-regime + multi-symbol backtest.
- A: build trend-following overlay như một strategy mới (tách khỏi engulfing) có đáng không?
- E: strat engulfing THẬT (`engulfing_pullback30_touch`, sinh ít signal nhưng chất hơn detector proxy) có nâng baseline unaligned trên cost không, hay cũng phụ thuộc hoàn toàn vào trend filter?
- E/D: fill probability của limit order chưa mô phỏng — cần model non-fill + adverse selection.
- B: funding thật BTC perp (hiện giả định phẳng 1 bps/8h; roadmap `trading-calulation-fix` đã defer funding sim).
- D/E: fee tier maker thật của tài khoản (có rebate không) — quyết định khả thi.

---

# PHẦN F — Caveat xuyên suốt (đọc trước khi tin bất kỳ số nào)

- **Một symbol (BTC), một năm, một split** → cả IN/OUT đều nằm trong cùng regime trending. Rủi ro này chi phối cả A lẫn E.
- `detect_engulfing` trong lib là **proxy đơn giản** (sinh nhiều signal hơn strat thật ~10×: 94,610 vs 8,629 trên 1m), test "engulfing-trigger + filter" tổng quát, không phải production strategy. Số Nhánh A/E là HƯỚNG, không phải con số production.
- Entry lấy từ backtest cũ (đã filter bằng SL 14 bps) → có selection bias nhẹ; trend filter độc lập với SL nên phát hiện vẫn vững, nhưng net chính xác cần backtest lại strategy mới (sinh lại entry).
- Long holds (16–48h) trên 8,629 entry 1m bị **autocorrelation** nặng (quan sát gần nhau trùng thông tin) → số mẫu hiệu dụng nhỏ hơn nhiều; số alpha ~±0 không phân biệt được với zero.
- `funding` giả định phẳng 1 bps/8h; thực tế biến động, làm hold dài tệ hơn.
- `first-touch` dùng quy tắc bi quan (chạm cả hai → tính SL); `fixed-horizon` bỏ qua path intrabar / rủi ro thanh lý trong nến.
- Mọi số per-lệnh = expected return per trade (gross trước phí / net sau phí), đơn vị bps của notional.
