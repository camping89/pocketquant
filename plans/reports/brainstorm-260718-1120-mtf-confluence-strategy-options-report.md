# Brainstorm — Multi-timeframe confluence: strategy + engine + workbench

- Date: 2026-07-18 · Session: brainstorm (ultrathink + research workflow 5 agents)
- Status: **PAUSED — chờ user trả lời Section 8 (Pending decisions)**. Trả lời xong → resume brainstorm hoặc `/ck:plan` với report này làm context.
- Nguồn: internal `plans/260706-2238-engulfing-1m-strategy-research/master-report.md`, engine source scan, web research (URLs inline)

## 1. Problem-first inversion

**Solution user đề xuất:** chuyển sang multi-timeframe (MTF) setup + human-in-the-loop UI.

**Problem thật bên dưới:** single-TF 1m đã được chứng minh *structurally unprofitable* — edge đạt được (~2–3.5 bps) < friction (4 bps maker / 10 bps taker round-trip). Không phải strategy sai chi tiết, mà timeframe sai cấu trúc. Đồng thời workbench chỉ hiển thị 1 timeframe nên human không thể review trade trong context HTF (higher timeframe) — loop nghiên cứu bị mù.

**Evidence status: STRONG** — internal walk-forward + control test + external academic. Đây KHÔNG phải vibes; hướng MTF đã có số liệu nội bộ chống lưng:

| Internal evidence (OOS, walk-forward) | Số |
|---|---|
| 1m signed fwd return @60m, baseline | −1.73 bps |
| Aligned với trend 1h (EMA20 closed bar) | **+3.58 bps** (control: counter −7.05, mirror đối xứng = filter thật) |
| Survivor A: 1d EMA20 regime → 1h engulfing trigger, hold 24h | net@maker **+31.9 bps**, n=416, e/c 9.0 |
| Survivor A, exit first-touch SL 3×ATR / TP 3R | net@maker **+68.9**, net@taker +62.9, e/c 18.2 |
| Survivor E: fade @1m + ATR≥8 | net@maker +1.73, n=1251 — chết ở taker |

**Meta-finding đã chốt:** edge KHÔNG nằm ở entry pattern (engulfing ~0 alpha OOS). Edge = (1) HTF regime filter + (2) hold đủ dài để amortize friction. "No holy grail" của user là đúng theo nghĩa: không pattern nào tự nó thắng — confluence chỉ là cách trade ít hơn, đúng chiều hơn, giữ lâu hơn.

## 2. Scout summary (codebase)

- **Strategy contract single-TF:** `StrategyConfig.interval: str` (1 giá trị), `IStrategyService.on_bar_completed(bar)` nhận 1 stream. Routing `StrategyAppService._find_strategies` match exact `symbol+interval` (`strategy_app_service.py:310-328`).
- **Live đã multi-stream sẵn:** `BarAppService` aggregate tick thành cả 7 interval in-memory, publish `BarCompletedEvent` per-interval khi close — HTF events đang bị drop vì routing exact-match. Cascade cron persist 5m/15m/1h/4h/1d vào Mongo.
- **Backtest là phía khó:** `HistoricalReplayAppService` replay đúng 1 interval, stamp `interval=config.interval` hardcode (line 76), sim time = bar **START** (không phải close).
- **Backtest UI:** 1 chart lightweight-charts v5 (đã có multi-pane cho RSI/MACD), master-detail workbench, verdict PATCH per-run, `anchorEndDate` freeze chart tại 1 thời điểm quá khứ — enabler rẻ cho per-trade HTF snapshot.
- **Toolkit offline sẵn:** `pq_prefetch`/`pq_lib` (multi-TF bars + trend_up_at no-lookahead + walk-forward masks) + rubric scorecard (`scripts/rubric/`) làm acceptance gate.

## 3. Research digest

### 3.1 Engine integration — 2 design, staging A→B khả thi

- **Option A "strategy-pull"** (~M): `StrategyConfig.context_intervals`, file mới `engine/strategy/htf_context_app_service.py` (ring buffer HTF closed bars; backtest = mini-cascade aggregate từ LTF stream trong sandbox; live = ăn HTF events có sẵn trên app bus), enrich `bar['htf']` trước dispatch, hook `on_warmup(bars_by_interval)`. Replay/broker/metrics KHÔNG đổi.
- **Option B "engine-push multi-stream"** (~L): k-way merge replay theo **close time** (`bar_start + interval_seconds`), tie-break LTF-first (khớp thứ tự live `BarAppService` loop ascending), stamp `bar.interval` thật. Durable, khớp semantics production.
- **Staging A→B gần như zero rework** nếu phase A chốt 3 điều: `context_intervals` mang semantics của B; strategy chỉ thấy `bar['htf']` snapshot + `on_warmup` (không cho query tự do); live side của provider ăn events từ ngày đầu.

**4 guard bắt buộc trước khi multi-interval events chạm sandbox bus** (silent-corruption hazards đã xác minh trong source):
1. Cascade persist **partial HTF bar** của bucket hiện tại (không có completeness flag) → mọi reader phải áp rule `bar_start + tf_secs <= now/sim-time`.
2. Sim time = bar START → visibility/merge key theo `bar_start` equality leak tới 59 phút lookahead; phải key theo close.
3. `PaperBrokerAdapter._on_bar_completed` không filter interval → HTF event sẽ trigger phantom SL/TP fill trên range rộng 60×.
4. `BacktestAppService._mtm_on_bar` không filter interval → equity sample out-of-order, hỏng Sharpe/drawdown.

### 3.2 Framework consensus (backtrader / NautilusTrader / LEAN / freqtrade / vectorbt)

Bất biến chung cả 5 engine: **HTF bar chỉ visible tại/ sau close time của nó**, và **không engine nào deliver HTF bar trước các LTF bars cấu thành nó** (LTF-first tại coinciding boundary). Warm-up = load N bars kết thúc *strictly before* start, đi qua path riêng (không sinh order). Khuyến nghị thêm regression test kiểu freqtrade lookahead-analysis: backtest [T0,T1] và [T0,T1′] phải cho signals giống hệt trong đoạn overlap.

### 3.3 Strategy archetypes (evidence × fee-survivability)

| # | Archetype | TF combo | Tần suất | Edge/trade (gross) | Evidence |
|---|---|---|---|---|---|
| 1 | Donchian ensemble trend-following | 1d, lookback 5–360d | vài lần/quý | hàng trăm bps | **STRONG** — SSRN net-of-fees, BTC 2015–25: CAGR 30%, Sharpe 1.58, MDD 19% |
| 2 | 1d 200MA regime + 4h RSI pullback | 1d→4h | ~0.6/tháng | ~+190 bps | MEDIUM — vendor A/B sạch (MDD 42→23, PF 1.34→1.78) nhưng **n=18** |
| 3 | Turtle Donchian 20/55 + midline filter | 1d | 1–3/tháng | +50–150 bps | MEDIUM — nhiều nguồn độc lập, param-insensitive |
| 4 | Elder triple-screen mechanized | 1w/1d→4h | 10–20/năm | ~160 bps | MEDIUM-LOW — template, phiên bản crypto = #2 |
| 5 | LTF fade gated by HTF range regime (ADX<20) | 4h gate→15m-1h fade | vài/tuần | hàng chục bps | MEDIUM cho regime-conditionality, WEAK net-of-fees — maker-only |
| 6 | Funding-rate extreme | overlay | — | — | veto-filter + cost model, không phải signal |

Pattern xuyên suốt: mọi archetype sống được fee đều **signal TF 4h/1d, hold giờ→tuần** — khớp kết luận nội bộ, không trùng hợp. ADX chỉ nên gate mean-reversion, không gate trend. Pre-falsified nội bộ (đừng dùng lại): session filter, vol_z stack, maker re-pricing làm nguồn edge, long-hold không có alpha-vs-control test.

**Pitfalls phải encode thành gate:** resample lookahead (bug thống trị MTF backtest — kể cả tool detect của freqtrade từng miss, issue #12507); live/backtest HTF mismatch (rule: mọi HTF condition đọc từ **previous closed HTF bar**, chấp nhận lag 1 bar); filter stacking = multiple testing (max ~3 layer, mỗi filter phải ảnh hưởng ≥15% trades, ~100+ trades qua ≥2 regime); trend-beta giả alpha (bắt buộc same-regime random-entry control + fees + funding).

### 3.4 UI / human-in-the-loop options (ranked)

| # | Option | Effort | Unlock |
|---|---|---|---|
| a | HTF indicator overlay + regime ribbon trên chart hiện tại (forward-fill HTF EMA, HistogramSeries ribbon) | **S** | Thấy trend-1h/1d filter trên mọi backtest chart, zero backend |
| c | Per-trade MTF context viewer — mini HTF chart trong drawer, `anchorEndDate` = **previous closed HTF bar** trước entry | **M** (rẻ bất thường vì `anchorEndDate` có sẵn) | Câu hỏi review cốt lõi: "lúc trade này fire, 1h/4h trông thế nào" |
| b | Chart HTF thứ hai sync theo **time-based** visible-range + crosshair (KHÔNG dùng logical-range cross-interval) | M | Scan MTF liên tục khi scrub trades |
| d | Trade review queue + tagging persist vào `backtest_trades` (clone verdict PATCH pipeline; fields nullable, key theo trade `_id` — né double-persist race) | L | Loop Tradervue: label theo HTF regime → đo edge per tag → thiết kế filter |
| e | Full multi-chart layout kiểu TradingView | L | Defer — YAGNI cho single-user tool |

## 4. Ba options

### Option 1 — Validate-first: offline research sprint, engine chờ

Backfill thêm data (multi-year gồm bear 2022, thêm symbol ngoài BTC) → viết `pq_mtf_*.py` trên `pq_lib` validate 3 candidate (survivor A config, Donchian ensemble, 200MA+4h RSI) qua 4-gate methodology → chỉ khi OOS net@maker đạt e/c ≥ 1.25 mới đụng engine. UI chỉ làm (a) [S].

- **Pros:** rẻ nhất, kill ý tưởng chết nhanh, đúng tinh thần "prove before build", toolkit đã sẵn.
- **Cons:** không giải quyết cả 2 phần user nêu (engine mental model + workbench); offline proxy có caveat (không intrabar path, không fill simulation, detector proxy ~10× signal count); trì hoãn capability mà mọi MTF strategy tương lai đều cần.

### Option 2 — Capability + 2 strategies evidence-backed (đề xuất)

Engine **phase A** (strategy-pull, B-compatible semantics, đủ 4 guard + `on_warmup`) + 2 strategies vào engine:

- **S1 "trend-rider"**: 1d EMA20/200MA regime filter → trigger 1h (engulfing hoặc RSI pullback) → exit fixed-horizon 24h hoặc SL 3×ATR / TP 3R. (= survivor A nội bộ, hợp nhất archetype 2 — evidence mạnh nhất, sống cả maker lẫn taker.)
- **S2 "donchian-breakout"**: 1d Donchian 20/55 + midline direction filter, SL 2×ATR(1d), exit 10-day channel. (= archetype 3; bước đệm lên ensemble archetype 1 sau.)

Offline validation (Option 1 nội dung) chạy **song song như acceptance gate** — engine build không block vì capability độc lập với strategy nào thắng. UI: (a)+(c) trước, (b) sau. Rubric scorecard = gate cuối cho mọi run.

- **Pros:** giải trọn 2 phần user yêu cầu; strategies ít trade + hold dài = friction-robust; A→B staging không rework; backtest chạy trên broker/cost model thật thay vì proxy.
- **Cons:** scope lớn nhất trong 3; cả S1+S2 cùng trend-beta failure mode (chop 4–6 tháng sideway); cần backfill multi-year + funding model cho hold dài.

### Option 3 — HITL workbench-first

UI đủ vòng loop: (a)+(c)+(d) — review queue, step qua từng trade với HTF context frozen tại entry, tag `htf-with-trend`/`htf-against-trend`/`chop`, persist → bảng win-rate/PnL per tag → derive filter → codify thành strategy. Engine chỉ thêm PATCH route + review fields.

- **Pros:** đúng chữ "human in the loop" nhất; tag-driven discovery là loop chuẩn của Tradervue/Edgewonk; UI assets tái dùng được vĩnh viễn.
- **Cons:** chậm nhất đến profitable strategy; nguy cơ **manual overfit** (mắt người tìm pattern trong noise = pitfall 3 phiên bản thủ công); phần labeling này `pq_entry_screen` đã tự động hoá phần lớn; không có engine MTF nên strategy rút ra vẫn chưa chạy được.

## 5. Recommendation

**Option 2**, với 2 điều kiện cứng:

1. **Gate trước khi code strategy vào engine:** offline validation multi-regime cho S1/S2 (ít nhất 1 giai đoạn non-trending, ví dụ backfill 2022). Engine phase A code được ngay song song — không phụ thuộc.
2. **Anti-lookahead tests đi cùng phase A** (không phải sau): unit test visibility rule + integration test truncated-window signal-equality.

Brutal honesty:

- Cái user gọi là "confluence" — data nói bản chất là **regime filter + friction amortization**. Trigger pattern gần như thay thế được (interchangeable). Đừng đầu tư vào entry pattern phức tạp; đầu tư vào filter + exit + cost model (funding).
- Portfolio S1+S2 "more than one strategy" nhưng **chưa diversified** — cùng chết trong chop. Diversifier thật duy nhất đã tìm thấy là fade E (thin, maker-only) → research lead, không build vội.
- HITL đúng chỗ = **research review loop** (option d). HITL kiểu "approve signal trước khi vào lệnh live" là bài toán khác hẳn (notification, timeout, engine pause) — đừng gộp vào scope này.

## 6. Success metrics & validation

- Offline gate: OOS net@maker > 0 với **e/c ≥ 1.25**, IN ≈ OOS, control (random same-direction) không khớp signal, ≥100 trades qua ≥2 regime.
- Engine gate: anti-lookahead tests pass; backtest single-TF cũ regression-clean (bit-identical metrics); `just test` + ruff + pyright + lint-imports (8 contracts) xanh.
- Strategy gate: rubric scorecard ≥ B, `cost_to_edge` score 4 (≥1.25), `mae_to_stop` 0.6–0.85.
- UI gate: (a) ribbon đúng với closed-HTF-bar rule (không repaint); (c) anchor = previous closed HTF bar (không lookahead).

## 7. Next steps (sau khi user chọn)

1. User chọn option + nghĩa HITL → `/ck:plan` với report này làm context.
2. Nếu Option 2: plan tách 4 track — (T1) engine phase A + guards + warmup, (T2) offline validation sprint (backfill data + pq_mtf scripts), (T3) S1/S2 implementation sau gate T2, (T4) UI (a)+(c).
3. Blocker data cần giải sớm: backfill multi-year BTC (gồm 2022 bear) + ≥1 symbol nữa; xác nhận maker fee tier thật của account; funding model cho hold >8h.

## 8. Pending decisions — điền answer rồi resume

> Mỗi mục có `**Answer:** _(chưa trả lời)_` — sửa trực tiếp vào file này hoặc trả lời trong chat. Q1+Q2 là bắt buộc để đi tiếp; Q3–Q6 có thể trả lời sau (đã ghi default tôi sẽ dùng nếu anh không ý kiến).

### Q1 (BẮT BUỘC) — Chọn hướng chính

| | Option | Tóm tắt | Trade-off chính |
|---|---|---|---|
| 1 | Validate-first offline | Chưa đụng engine. Backfill data multi-year/multi-symbol, viết `pq_mtf_*.py` trên `pq_lib`, validate qua 4-gate. Engine chỉ build khi OOS net@maker e/c ≥ 1.25. UI chỉ HTF ribbon [S]. | Rẻ nhất / chậm capability nhất; không giải cả 2 phần anh nêu |
| **2** | **Capability + 2 strategies (RECOMMENDED)** | Engine MTF phase A (strategy-pull, B-compatible) + 4 anti-lookahead guards + `on_warmup`. S1 trend-rider (1d regime → 1h trigger, = survivor A: OOS net@maker +31.9..+68.9 bps) + S2 donchian-breakout (1d). Offline validation song song làm gate. UI: ribbon [S] + per-trade HTF viewer [M]. | Scope lớn nhất; S1+S2 cùng trend-beta risk (chết chung trong chop) |
| 3 | HITL workbench-first | UI đủ review loop: ribbon + HTF context viewer + trade review queue tagging → đo edge per tag → derive filter → codify sau. Engine chỉ thêm PATCH route. | Đúng chữ HITL nhất / chậm nhất đến profitable; risk manual overfit |

**Answer:** _(chưa trả lời)_

### Q2 (BẮT BUỘC) — "Human in the loop" nghĩa là gì? (chọn được nhiều)

- **(a) Research review loop** — human review từng backtest trade trong MTF context frozen tại entry, tag/annotate, đo edge per tag để thiết kế filter. Nằm gọn trong UI options đã nêu.
- **(b) Live approval gate** — strategy sinh signal live → human approve/reject trước khi vào lệnh. Bài toán riêng (notification, timeout, engine pause) — nếu chọn, tách initiative khác, không gộp scope này.
- **(c) Chỉ quan sát/giám sát** — workbench đủ insight MTF để giám sát và bật/tắt strategy, không can thiệp per-trade.

**Answer:** _(chưa trả lời)_

### Q3 — Backfill data: symbols + độ sâu

Cần multi-year (bắt buộc gồm giai đoạn non-trending như 2022 bear) + ≥1 symbol ngoài BTC để S1/S2 qua gate "≥100 trades, ≥2 regimes". DB hiện chỉ có BTC ~1 năm.
Đề xuất default: **BTCUSDT + ETHUSDT + SOLUSDT, từ 2021-01 (1h/4h/1d; 1m chỉ cần cho execution-TF nghiên cứu)**.

**Answer:** _(chưa trả lời — default như trên nếu không ý kiến)_

### Q4 — Fee tier thật của account

Mọi nhánh maker-only (fade E, archetype 5) sống/chết theo con số này. Hiện giả định maker 2 bps/side, taker 4.5 bps/side, không rebate. Anh xác nhận tier thật (hoặc chưa có account futures thật → giữ giả định)?

**Answer:** _(chưa trả lời — default giữ giả định 2/4.5 bps, no rebate)_

### Q5 — Funding model cho hold dài

S1/S2 hold 24h+ → funding thành cost đáng kể (~3 bps/ngày khi sustained ±0.01%/8h). Hiện giả định phẳng 1 bps/8h. Options: (a) giữ flat assumption cho vòng đầu, (b) backfill funding-rate history thật từ Binance vào validation (thêm ~1 buổi work).

**Answer:** _(chưa trả lời — default (a) flat cho vòng validation đầu, (b) trước khi live)_

### Q6 — Thứ tự UI (nếu Q1 = Option 2 hoặc 3)

Đề xuất default: **(a) HTF ribbon [S] → (c) per-trade HTF viewer [M]** trong initiative này; (b) synced HTF chart + (d) review queue sang phase sau (d bắt buộc nếu Q2 chọn research-review-loop).

**Answer:** _(chưa trả lời — default như trên)_

## 9. Resume checklist (session sau)

1. Đọc report này; check Section 8 answers.
2. Q1+Q2 đã trả lời → xác nhận lại scope 1 câu, rồi `/ck:plan` với path report này làm context (Option 2 → plan 4 tracks như Section 7).
3. Research thô đầy đủ (5 agent reports, JSON): `~/.claude/projects/-home-ubuntu-1-W--me-algotrading-pocketquant/cebb79d7-8a7e-429b-9437-4bdadbdb5aab/subagents/workflows/wf_2db9d09f-15a/journal.jsonl` — session-local, có thể đã bị dọn; report này là bản digest đầy đủ nhất còn lại.
4. Prior-research gốc: `plans/260706-2238-engulfing-1m-strategy-research/master-report.md` (toolkit + methodology + survivor configs).
