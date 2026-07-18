# Test B — Multi-symbol validation (BTC/ETH/SOL): engulfing+structure KHÔNG generalize

> Timestamp: 2026-07-13 (Asia/Saigon). Research execution (chạy script có sẵn + bootstrap phụ + diễn giải). Câu tiếng Việt, term tiếng Anh giữ nguyên.
> Nối tiếp: [validation plan](./brainstorm-maker-vs-taker-cost-inversion-and-alpha-validation-plan.md) · [research vòng 2 (BTC)](./from-research-to-user-engulfing-structure-level-taker-profit-report.md).
> Trả lời câu hỏi #1 chưa giải quyết: 3 variant (A/B/C) có generalize sang ETH/SOL không, hay chỉ là BTC-artifact?

---

## TL;DR (đọc cái này)

**KHÔNG generalize. Edge là BTC-artifact / trend-beta, không phải alpha thật.**

- Chỉ **BTC** giữ OOS net@taker dương cả 3 variant (+14 → +20 bps).
- **ETH** lẫn lộn dấu: A/B dương mỏng (+12.6 / +1.0), C âm (−12.3).
- **SOL** âm mạnh cả 3 variant (−36 → −52 bps), win rate sụp còn 0.08–0.15.
- **Không variant nào dương cả 3 symbol** → dấu KHÔNG nhất quán → fail generalize.
- **drop3_out âm ở TẤT CẢ (symbol × variant)**, kể cả BTC → net dương phụ thuộc top-3 winner ở mọi nơi.
- **Pooled CI vẫn chứa 0** và point estimate pooled rơi về ~0/âm (A +2.0, B −2.3, C −8.8): pooling KHÔNG co CI khỏi 0 như kỳ vọng edge thật — ngược lại, SOL âm triệt tiêu BTC dương.

→ **Test C kill condition fail cả 4.** Kết luận cuối theo brainstorm doc: engulfing+structure không tradeable ở retail taker cost. Dừng directional engulfing; pivot Frame C (trend-beta tử tế) hoặc đóng sổ.

---

## Setup (cùng config, cùng split, fair cross-asset)

- **Data prefetch** (prod Mongo read-only, window 2024-07-01 → 2026-07-08, cả 3 symbol đầy đủ, KHÔNG có EMPTY):

| symbol | 1m bars | range |
|---|---|---|
| BTCUSDT:BINANCE | 1,054,221 | 2024-07-01 → 2026-07-07 |
| ETHUSDT:BINANCE | 1,045,303 | 2024-07-12 → 2026-07-07 |
| SOLUSDT:BINANCE | 1,045,170 | 2024-07-12 → 2026-07-07 |

- **Cơ chế** (không đổi so với vòng 2): 1h engulfing trigger → gate trend 1d (EMA20, bar đã đóng) + swing structure level 1d (pivot k=3, no-lookahead) → exit fixed-RR dài, maxbars=480, tie=SL.
- **Walk-forward split**: SPLIT_EPOCH = 2026-01-06. IN = trước, OUT = từ đó (≈6 tháng OOS). Friction = **taker 10 bps** round-trip.
- **3 variant**: A (prox=60, rr=3.0, wick=0.5) · B (prox=100, rr=3.0, wick=0.6) · C (prox=120, rr=4.0, wick=0.6).

---

## Kết quả per-symbol (số thật từ `pq_multi_symbol_validate.py`)

| Variant | Symbol | IN net (n) | **OUT net@taker (n)** | wr_out | drop3_out |
|---|---|---|---|---|---|
| **A** | BTC | +17.9 (132) | **+19.1 (66)** | 0.35 | **−4.7** |
| A | ETH | +44.0 (58) | **+12.6 (44)** | 0.32 | **−25.0** |
| A | SOL | +11.9 (67) | **−40.9 (37)** | 0.11 | **−76.3** |
| **B** | BTC | +21.2 (176) | **+14.3 (83)** | 0.31 | **−4.6** |
| B | ETH | +43.9 (95) | **+1.0 (58)** | 0.28 | **−29.3** |
| B | SOL | +3.3 (111) | **−35.6 (47)** | 0.15 | **−65.2** |
| **C** | BTC | +24.9 (196) | **+19.7 (85)** | 0.28 | **−3.8** |
| C | ETH | +41.8 (109) | **−12.3 (59)** | 0.22 | **−39.5** |
| C | SOL | +8.5 (133) | **−52.2 (51)** | 0.08 | **−84.0** |

### Cross-asset OOS net@taker matrix

```
variant                BTCUSDT     ETHUSDT     SOLUSDT
A conservative            +19.1       +12.6       -40.9
B balanced                +14.3        +1.0       -35.6
C wide-RR                 +19.7       -12.3       -52.2
```

Dương cả hàng = generalize. **Không hàng nào dương cả 3 cột.**

### Bootstrap 95% CI (bổ sung — `pq_multi_symbol_bootstrap.py`, kill-criterion #3)

Script `validate` gốc không in CI per-symbol → tôi viết script phụ (5000 resample, seed=42) tính CI per-symbol + POOLED (gộp OOS trades 3 symbol, đúng tinh thần Test B "pool → CI co").

| Variant | Symbol | n | net@taker | 95% CI | Verdict |
|---|---|---|---|---|---|
| **A** | BTC | 66 | +19.1 | [−17.1, +57.9] | spans 0 |
| A | ETH | 44 | +12.6 | [−35.6, +71.9] | spans 0 |
| A | SOL | 37 | −40.9 | [−78.9, +5.5] | spans 0 |
| A | **POOLED** | 147 | **+2.0** | **[−22.5, +29.9]** | **spans 0** |
| **B** | BTC | 83 | +14.3 | [−18.0, +48.5] | spans 0 |
| B | ETH | 58 | +1.0 | [−42.7, +51.4] | spans 0 |
| B | SOL | 47 | −35.6 | [−72.4, +6.8] | spans 0 |
| B | **POOLED** | 188 | **−2.3** | **[−24.7, +21.6]** | **spans 0** |
| **C** | BTC | 85 | +19.7 | [−17.5, +59.2] | spans 0 |
| C | ETH | 59 | −12.3 | [−53.5, +33.8] | spans 0 |
| C | SOL | 51 | −52.2 | [−85.8, −11.2] | **CI < 0 (âm significant)** |
| C | **POOLED** | 195 | **−8.8** | **[−32.4, +16.8]** | **spans 0** |

**Điểm chết người:** pooling n≈3× KHÔNG kéo CI tách khỏi 0. Với edge thật, gộp mẫu phải co CI + tách zero. Ở đây pooled point estimate rơi về ~0 hoặc âm vì SOL âm ăn hết BTC dương. Đây là chữ ký "no edge", không phải "small-sample chưa đủ mẫu".

---

## Đánh giá 4 kill-criteria (brainstorm doc, brutally honest)

| # | Criterion | Kết quả | Đạt? |
|---|---|---|---|
| 1 | OOS net@taker dương ≥3 symbol, **cùng dấu** | Chỉ BTC dương cả 3 variant. ETH lẫn lộn. SOL âm mọi variant. Không variant nào dương đủ 3 symbol. | ❌ FAIL |
| 2 | Không phụ thuộc top-3 winner (drop3_out) | drop3_out **âm ở 9/9** (symbol × variant), kể cả BTC (+19.1 → drop3 −4.7). Bỏ 3 winner là âm khắp nơi. | ❌ FAIL |
| 3 | Bootstrap 95% CI không chứa 0 | 8/9 per-symbol CI spans 0; 1/9 (SOL-C) CI<0 (sai hướng). Cả 3 pooled CI spans 0, point ~0/âm. | ❌ FAIL |
| 4 | Cùng cơ chế robust cross-asset | Cùng cơ chế nhưng chỉ "sống" ở BTC. SOL win rate sụp 0.08–0.15 → fixed-RR dài chết trong regime SOL. Không robust. | ❌ FAIL |

**Fail cả 4/4** → Test C kill condition kích hoạt.

---

## Diễn giải: alpha thật hay BTC-artifact/trend-beta?

**BTC-artifact / trend-beta.** Bằng chứng:

1. **Chỉ BTC sống.** BTC là symbol cache dài nhất + regime trending mạnh nhất 2024–2026. ETH mỏng dần theo tp_rr (A+ → C−); SOL âm mạnh và win rate sụp về ~0.1 → OUT window của SOL là regime choppy/reversal, nơi fixed-RR dài (giữ move to) bị cắt SL hàng loạt. Đây chính là "trend beta phụ thuộc regime" mà research vòng 2 cảnh báo.

2. **Dấu KHÔNG nhất quán cross-asset** = định nghĩa của không-generalize. Nếu engulfing+structure mang directional alpha độc lập asset, ETH/SOL phải cùng dấu BTC. Chúng không.

3. **Pooled CI chứa 0 + point ~0.** Gộp 3 symbol không cứu được — SOL âm triệt tiêu BTC dương. Nếu là small-sample thuần (edge thật nhưng ít mẫu), pooling phải co CI về phía dương; thực tế nó kéo về zero.

4. **drop3 âm phổ quát.** Ngay cả BTC dương cũng do 1–3 winner khổng lồ (right-skew trend-following y hệt vòng 2). Không phải "median lệnh dương" — là "vài lệnh đuôi phải cứu cả tập". Trên SOL không có đuôi phải đó → âm.

→ Kết quả này **xác nhận** dự đoán "brutal honesty" của brainstorm doc: *engulfing không alpha; cái duy nhất sống được = trend-beta, và trend-beta không generalize khi asset/regime đổi.*

---

## Caveats (không tô hồng)

- **Cache window khác report vòng 2.** Vòng 2 dùng BTC cache 2025-06 start (n_out A=48, net +7.5); ở đây cache 2024-07 start → structure level 1d history dài hơn → tập entries khác → BTC n_out A=66, net +19.1. **Không so 1-1 với report cũ được**, nhưng dấu + độ lớn (BTC dương ~+14..+20) đồng hướng. Cross-asset comparison vẫn fair vì cả 3 symbol dùng CÙNG window.
- **first-touch pessimistic.** Exit path-aware nhưng tie=SL + bỏ qua path intrabar dưới 1m; có thể bi quan hơn thực tế. Không đổi kết luận (bi quan đều tay cả 3 symbol).
- **n_out nhỏ** (37–85 per symbol) → CI rộng là điều dự kiến; nhưng pooled n=147–195 vẫn chứa 0 đã đủ để bác "edge co CI".
- **Funding chưa trừ.** Giữ lệnh fixed-RR dài (median vài chục giờ) → funding perp đáng kể, làm net taker TỆ HƠN nữa. Con số hiện tại là cận trên lạc quan.
- **Cache /tmp ephemeral** — mất giữa session; phải chạy lại `pq_prefetch_multi.py` (đọc prod DB) trước khi tái lập.
- **taker-only.** Test B này chỉ taker; net@maker chưa chạy đa symbol (Test A). Nhưng maker chỉ giảm cost ~6bps/RT — không sửa được việc SOL âm −36..−52 và dấu không nhất quán. Cost không phải nguyên nhân gốc của fail-generalize.

---

## Kết luận & khuyến nghị

**Engulfing+structure+fixed-RR KHÔNG tách được alpha khỏi trend-beta, và trend-beta đó không generalize sang ETH/SOL.** Test C kill condition (cả 4 tiêu chí) fail. Theo brainstorm doc:

> Nếu maker + đa symbol không đạt cả 4 → kết luận cuối: engulfing không tradeable ở retail cost. Dừng directional engulfing. Pivot Frame C hoặc đóng sổ.

- **Dừng** cày thêm variant/param directional engulfing (evidence giờ vượt STRONG: dead cả cross-asset).
- **Test A (maker) đã mất phần lớn ý nghĩa** với 3 variant này: cost không phải nút thắt gốc — dấu không nhất quán + SOL âm sâu không phải vấn đề 6bps cost. Chỉ đáng chạy nếu muốn đóng sổ Frame A dứt điểm cho hồ sơ.
- **Nếu tiếp**: pivot Frame C — trend-following đa symbol tử tế (vol-targeting + drawdown control), engulfing chỉ là entry timer. Cần brainstorm riêng, thiết kế khác hẳn.

---

## Câu hỏi chưa giải quyết

- SOL OUT window (2026-01 → 2026-07) là regime gì cụ thể (downtrend/choppy)? Win rate 0.08–0.15 gợi ý reversal-heavy; nếu confirm thì đây thuần là regime risk của trend-beta, không phải lỗi signal.
- Nếu chạy Test A (maker/rebate) đa symbol, SOL có bớt âm đủ để đổi kết luận không? (Dự đoán: không — gap quá lớn so với 6bps cost saving.)
- Frame C: trend-following đa symbol với vol-targeting có generalize tốt hơn engulfing-gated không? (Ngoài scope; cần plan riêng.)
- Funding thực tế trên 3 perp trong window này bao nhiêu bps/lệnh? Trừ vào sẽ đẩy pooled net âm rõ hơn.

---

## Tái lập

```bash
# 1. Prefetch (bắt buộc — /tmp ephemeral)
cd /Users/admin/workspace/_me/algo-trading/pocketquant
uv run python plans/260712-0849-engulfing-structure-level-taker-profit/scripts/pq_prefetch_multi.py

# 2. Validation + bootstrap (skills venv có numpy)
cd plans/260712-0849-engulfing-structure-level-taker-profit/scripts
~/.claude/skills/.venv/bin/python3 pq_multi_symbol_validate.py
~/.claude/skills/.venv/bin/python3 pq_multi_symbol_bootstrap.py   # CI per-symbol + pooled
```
