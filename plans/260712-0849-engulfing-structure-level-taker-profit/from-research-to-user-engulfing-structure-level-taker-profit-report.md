# Engulfing + Structure Level trên BTC — 3 variant net dương ở TAKER

> Timestamp: 2026-07-12 08:49 (Asia/Saigon). Self-contained. Câu tiếng Việt, term tiếng Anh giữ nguyên (giải thích trong ngoặc lần đầu). Nối tiếp research trước [`260706-2238-engulfing-1m-strategy-research/master-report.md`](../260706-2238-engulfing-1m-strategy-research/master-report.md) — đọc phần đó để có bối cảnh 9-phase.
>
> **Yêu cầu người dùng (đã chốt qua interview):** cost bar = **TAKER** (entry `market`, ~10 bps round-trip: commission 4.5×2 + slippage 0.5×2); engulfing chỉ là **trigger**, được phép detect trên khung cao (5m/15m/1h) + **kết hợp key structure level (S/R) khung lớn** để có entry + RR tốt nhất; deliverable = **3 variant param + report** (proxy cache, walk-forward OOS).

---

## TL;DR (đọc cái này trước)

Tìm được **3 variant có net@taker dương, bền walk-forward** (dương cả in-sample lẫn out-of-sample, control counter-trend sập đối xứng). **Cả 3 cùng MỘT cơ chế**, khác nhau ở risk profile:

> **1h engulfing (trigger) → gate bằng trend 1d + swing structure level 1d → exit fixed-RR dài (3–4R).**

| Variant | prox | tp_rr | OOS net@taker | OOS net@maker | n_out | win rate | Verdict |
|---|---|---|---|---|---|---|---|
| **A — conservative** | 60 bps | 3.0 | **+7.5** | +13.5 | 48 | 0.33 | positive, mỏng |
| **B — balanced** | 100 bps | 3.0 | **+24.0** | +30.0 | 65 | 0.34 | positive, mẫu tốt nhất |
| **C — wide-RR** | 120 bps | 4.0 | **+44.1** | +50.1 | 67 | 0.30 | net cao nhất, đuôi dày nhất |

**Nhưng — sự thật brutal (bắt buộc đọc):**
1. **Không variant nào significant ở 95%.** Bootstrap CI của cả 3 đều chứa 0: A `[−30,+56]`, B `[−19,+73]`, C `[−13,+108]`.
2. **Net dương phụ thuộc 1–3 lệnh thắng khổng lồ.** Bỏ 1 winner → A âm. Bỏ 3 winner → B/C về ≈0/âm. Đây là phân phối right-skew điển hình trend-following: win rate 28–34%, **median mỗi lệnh ÂM** (−32 đến −46 bps), mean dương chỉ nhờ đuôi phải (max +361 → +1171 bps).
3. **Engulfing KHÔNG phải nguồn edge gốc.** Random entry cùng gate (trend 1d + level 1d + fixed-RR) cũng net dương OOS (+6 đến +10 bps). Engulfing chỉ **nâng** net/lệnh (marginal lift +7.6 → +34.5 bps) nhờ chọn timing tốt hơn — đúng kết luận research cũ: *"edge là trend filter 1d, engulfing chỉ là cò bấm"*.

→ **3 variant đạt tiêu chí "net dương taker walk-forward" theo point estimate, nhưng là research lead — KHÔNG phải tín hiệu production đã chứng minh.** Nguyên nhân: chạm trần dữ liệu (1 symbol BTC, 1 năm regime trending, n_out chỉ 48–67).

---

## Vì sao chỉ có một cơ chế sống được ở TAKER

Research cũ đã chứng minh: friction taker ~10 bps round-trip đòi hỏi **gross/lệnh phải ≫ 10 bps** mới net dương. Trên 1m/5m/15m, sóng tự nhiên chỉ ~3.5–6 bps → chết chắc. Sweep lần này xác nhận lại (net@taker, split 2026-01-06):

| Entry TF | struct TF | OOS gross | OOS net@taker | Đọc |
|---|---|---|---|---|
| 5m | 1h | +0.18 | −9.82 | friction nuốt sạch |
| 5m | 4h | +1.95 | −8.05 | |
| 15m | 4h | +5.80 | −4.20 | gần nhưng vẫn âm |
| 15m | 1d | +5.75 | −4.25 | |
| **1h** | **1d** | **+10.89** | **+0.89 → +44** | **chỉ TF này gross đủ lớn** |
| 4h | 1d | n<5 | — | mẫu quá mỏng |

**Cơ chế kinh tế:** để một lệnh kiếm > 10 bps sau phí, cần bắt được một *move có cấu trúc* (giá chạy từ level này sang level kia). Chỉ khung ≥ 1h + giữ lệnh dài (fixed-RR 3–4R, thực tế median hold vài chục giờ) mới cho move đủ lớn. Đây **về bản chất là trend-following** — engulfing tại một swing level chỉ là điểm khởi phát thuận lợi.

---

## Cơ chế chi tiết (3 gate + exit)

```
Cho mỗi bar 1h đóng cửa:
 1. TRIGGER   — full-candle engulfing (body+range engulf, khớp core detect_engulfing),
                rejection-wick ≤ wick_pct.
 2. TREND GATE— trend 1d của bar 1d ĐÃ ĐÓNG gần nhất (close > EMA20 → up).
                LONG chỉ khi 1d up; SHORT chỉ khi 1d down (aligned).
 3. LEVEL GATE— swing S/R trên 1d (pivot k=3, CHỈ confirm sau k bar → no-lookahead).
                LONG: bar low chạm trong prox_bps quanh nearest support < entry.
                SHORT mirror quanh nearest resistance.
 4. RISK      — SL = level ± buffer 5 bps; TP = entry ± tp_rr × risk (fixed-RR).
                bỏ lệnh nếu RR hình học < min_rr.
 5. EXIT      — first-touch path-aware, maxbars=480 (20 ngày), tie=SL (bi quan).
```

Hai chi tiết chống lookahead leak (nếu vi phạm là ăn gian): (a) swing pivot chỉ "biết" tại `ts[pivot_idx + k]`, không phải tại bar pivot — `levels_before(epoch)` lọc theo confirm-epoch; (b) trend 1d dùng bar đã đóng (`bisect_right − 1`).

**Config chính xác 3 variant** (đều `tf=1h, struct_tf=1d, trend_tf=1d, trend_span=20, pivot_k=3, sl_buffer_bps=5, maxbars=480`):

| | prox_bps | min_rr | tp_rr | wick_pct |
|---|---|---|---|---|
| A conservative | 60 | 1.5 | 3.0 | 0.5 |
| B balanced | 100 | 1.3 | 3.0 | 0.6 |
| C wide-RR | 120 | 1.3 | 4.0 | 0.6 |

---

## Bằng chứng walk-forward đầy đủ

Split IN/OUT tại **2026-01-06** (6 tháng tune / 6 tháng validate). Friction taker=10, maker=4 bps round-trip.

| Variant | half | n | wr | gross | net@taker | net@maker | median | max | min |
|---|---|---|---|---|---|---|---|---|---|
| A | IN | 49 | 0.33 | +25.3 | +15.3 | +21.3 | −46.0 | +361 | −176 |
| A | OUT | 48 | 0.33 | +17.5 | **+7.5** | +13.5 | −41.3 | +705 | −143 |
| B | IN | 67 | 0.37 | +51.2 | +41.2 | +47.2 | −32.8 | +638 | −176 |
| B | OUT | 65 | 0.34 | +34.0 | **+24.0** | +30.0 | −40.3 | +705 | −178 |
| C | IN | 75 | 0.28 | +44.0 | +34.0 | +40.0 | −44.9 | +850 | −244 |
| C | OUT | 67 | 0.30 | +54.1 | **+44.1** | +50.1 | −42.4 | +1171 | −204 |

Exit mix (SL/TP/mark-close): A 64/32/1 · B 84/47/1 · C 100/41/1. **Hầu hết lệnh chạm SL** (≈2/3); lời đến từ thiểu số lệnh chạm TP-dài. Đúng chữ ký trend-following.

### Control counter-trend (đảo chiều gate) — PHẢI sập, và nó sập

| Variant | counter IN net@taker | counter OUT net@taker |
|---|---|---|
| A | −19.86 | −32.01 |
| B | −30.89 | −44.25 |
| C | −16.22 | −42.42 |

Gương đối xứng sạch (aligned dương ↔ counter âm cả hai nửa) → **chiều trend 1d mang thông tin thật**, không phải artifact. Đây là bằng chứng mạnh nhất rằng edge có thật (dù mỏng).

### Stability surface — edge là REGION, không phải point

OOS net@taker quét lưới `tp_rr × prox` (1h→1d, trend 1d span20). Gần như mọi ô dương cả hai nửa (đánh dấu `*`):

```
rr\prox      60        80        100       120
rr=2.0     +5.0*     -2.8      +14.9*    +20.5*
rr=2.5     +7.4*     +0.3*     +17.6*    +25.3*
rr=3.0     +7.5*     +1.4*     +24.0*    +33.7*
rr=3.5    +12.9*     +7.0*     +20.0*    +32.0*
rr=4.0    +20.5*    +14.4*     +30.3*    +44.1*
```

Không phải một điểm may mắn → **không curve-fit về param**. Nhưng lưu ý: net tăng đơn điệu theo `tp_rr` và `prox` — dấu hiệu "giữ lâu hơn / lấy move to hơn = nhiều trend beta hơn", củng cố bản chất momentum.

### Trend-span nhạy (điểm yếu)

prox=100, rr=3.0: span 10 → OUT +41.9; span 20 → +24.0; **span 50 → −14.7; span 100 → −6.8**. Chỉ span ngắn (10–20) sống. Cần chốt span nhỏ; span dài giết edge.

### Marginal lift của engulfing (fair test cùng gate)

Random entry (1h bar bất kỳ, cùng trend 1d + level 1d + fixed-RR), OOS net@taker:

| Variant | engulfing OOS net | random OOS net | lift |
|---|---|---|---|
| A | +7.5 (n=48) | −0.0 (n=276) | **+7.6** |
| B | +24.0 (n=65) | +8.3 (n=371) | **+15.6** |
| C | +44.1 (n=67) | +9.7 (n=413) | **+34.5** |

Random cũng dương (trend+level tự nó có edge) → engulfing **không** phải nguồn gốc. Nhưng lift dương nhất quán → engulfing **chọn timing tốt hơn** đáng kể, nhất là ở variant C.

---

## Kiểm tra robustness (vì sao gọi là "research lead", không phải "production")

Bỏ dần top-k lệnh thắng lớn nhất khỏi tập OOS, tính lại net@taker:

| Variant | drop0 | drop1 | drop2 | drop3 | bootstrap 95% CI |
|---|---|---|---|---|---|
| A | +7.5 | −7.1 | −13.0 | −18.8 | [−30, +56] |
| B | +24.0 | +13.5 | +3.1 | −6.5 | [−19, +73] |
| C | +44.2 | +27.2 | +13.4 | −0.3 | [−13, +108] |

- **A:** chỉ cần bỏ **1** winner là âm → cực mỏng, gần như một lệnh cứu cả tập.
- **B/C:** chịu được 2 winner, sập ở 3. Bền hơn A nhưng vẫn phụ thuộc đuôi.
- **Cả 3:** CI chứa 0 → **không đủ mẫu để bác bỏ "net = 0"**. Point estimate dương, significance không đạt.

Top-3 winners của A = 1236 bps trong khi tổng OOS chỉ 842 bps (winners > tổng → phần còn lại âm ròng).

---

## Khuyến nghị

| Nếu bạn... | Làm gì |
|---|---|
| Muốn con số "net dương taker walk-forward" như đã yêu cầu | 3 variant A/B/C ở trên — **B là lựa chọn cân bằng nhất** (n_out lớn nhất, chịu 2 winner-drop, lift engulfing rõ) |
| Muốn tin được để trade thật | **Chưa đủ** — phải validate multi-symbol (ETH/SOL/…) + multi-regime (năm sideway) trước. n_out 48–67 + CI chứa 0 = chưa chứng minh |
| Muốn edge độc lập khỏi trend beta | Không có — mọi net dương taker đều ăn theo trend 1d. Engulfing chỉ là gia vị (+lift), không phải món chính |

**Bước tiếp hợp lý (chưa làm, chờ quyết định):**
1. **Multi-symbol backtest** — prefetch ETH/SOL/BNB bars từ prod (nếu có), chạy đúng 3 config, xem net dương có generalize. Đây là test quan trọng nhất.
2. **Build vào engine thật** — nếu muốn số production (persist `backtest_runs`), viết `EngulfingStructureLevelStrategyService` (1h entry + 1d trend/level gate + fixed-RR exit). Proxy hiện tại sinh signal khác strat thật.
3. **Fee tier thật** — nếu account có maker rebate, net@maker (+13 đến +50) đẹp hơn nhiều và bền hơn; nhưng entry `market` hiện tại = taker.

---

## Cách resume / tái lập

```bash
# 1. Prefetch (bắt buộc — /tmp ephemeral, mất giữa session)
cd /Users/admin/workspace/_me/algo-trading/pocketquant
uv run python plans/260706-2238-engulfing-1m-strategy-research/scripts/pq_prefetch.py

# 2. Chạy phân tích (skills venv có numpy)
cd plans/260712-0849-engulfing-structure-level-taker-profit/scripts
~/.claude/skills/.venv/bin/python3 pq_structure_sweep.py      # sweep TF rộng
~/.claude/skills/.venv/bin/python3 pq_structure_focus.py      # focus vùng 1h + control
~/.claude/skills/.venv/bin/python3 pq_stability_surface.py    # region + random control
~/.claude/skills/.venv/bin/python3 pq_finalists_confirm.py    # 3 variant + outlier
```

Scripts (`scripts/`):
- `pq_structure_lib.py` — lib cốt lõi: `swing_levels` / `levels_before` (no-lookahead S/R), `build_structure_entries` (3 gate + RR), `first_touch_levels` (path-aware exit + exit-kind), `summarize`/`show`.
- `pq_structure_sweep.py` · `pq_structure_focus.py` · `pq_stability_surface.py` · `pq_finalists_confirm.py`.

**Data:** MongoDB prod read-only (`.env` → `MONGODB_URL`, `ENABLE_JOBS=false`, KHÔNG ghi bars). Bars `BTCUSDT:BINANCE` 1m/5m/15m/1h/4h/1d, 2025-06-01 → 2026-07-07 (1m: 571,821 bars). Entries proxy = detect trên cache, không dùng 8629 entry cũ (bài toán khác: high-TF).

---

## Câu hỏi chưa giải quyết

- **Multi-symbol:** 3 variant có generalize sang ETH/SOL không, hay chỉ là BTC-2025-trending? DB prod có sẵn symbol khác không (cần check — memory ghi chỉ thấy BTCUSDT:BINANCE)?
- **Significance:** n_out 48–67 quá nhỏ, CI chứa 0. Cần bao nhiêu năm/symbol để CI tách khỏi 0? Hay bản chất edge này (trend beta) không bao giờ significant trên 1 asset?
- **Regime:** cả IN lẫn OUT đều trong một năm trending. Năm sideway (vd 2018, 2022) 3 variant có sập như research cũ cảnh báo không?
- **Fixed-RR vs level-TP:** level-TP (TP = level đối diện thật) net OOS gần zero (V1 +0.89); fixed-RR 3–4R thắng rõ. Nhưng fixed-RR dài = giữ lâu = nhiều beta. Level-TP mới đúng tinh thần "structure" người dùng muốn — có cách nào để level-TP net dương taker mà không rơi về beta không?
- **Engulfing thật:** strat production (`engulfing_pullback30_touch` sinh ít signal, chất hơn detector proxy) trên khung 1h + gate này có nâng lift cao hơn detector proxy không?
- **Fill/funding:** first-touch bỏ qua path intrabar + chưa trừ funding (giữ lệnh median vài chục giờ → funding đáng kể ở perp, làm net taker tệ hơn).
