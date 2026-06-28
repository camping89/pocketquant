# Slice 5 — Explain Trade (Signal Rationale + PnL/Risk) — Brainstorm Report

## Metadata

| | |
|---|---|
| Priority | 5/5 (cuối, đắt & rủi ro nhất — đụng engine) |
| Surface | FE + BE |
| Depends on | Slice 1 (backtest detail/positions), Slice 3 (forward trades), Slice 4 (order link) |
| Unblocks | none (capstone) |
| Date | 2026-06-28 |

---

## 1. Problem Statement

Cho 1 trade (closed position) bất kỳ trong tab **Backtest** hoặc **Forward**, user muốn mở "explain" gồm 2 phần (chốt CẢ HAI):

1. **Signal rationale** — vì sao strategy VÀO (pattern/indicator nào trigger: breakdown 4h window, engulfing strong) và vì sao RA (SL = max của technical 8h low vs cap 1%; TP = max của technical 1h high vs min 2%) theo `hitnrun2`.
2. **PnL/risk breakdown** — R-multiple, % account risk, commission, slippage, MAE/MFE (max adverse/favorable excursion), duration.

Hiện FE chỉ show `dir / entry / exit / pnl / qty / time`. Không có detail drawer. BE không persist "vì sao" — `Signal.entry_logic` được sinh ra nhưng **bị rớt** trước khi tới order/position/trade record (chứng minh ở §2).

---

## 2. Current State (evidence)

### 2.1 Reason ĐƯỢC sinh nhưng KHÔNG được persist — điểm mất thông tin

| Nơi | File:line | Trạng thái reason |
|---|---|---|
| Signal sinh ra reason | `core/domain/strategy/value_objects.py:20` (`entry_logic: str`) | CÓ — `Signal.entry_logic` |
| hitnrun2 set reason | `core/domain/strategy/services/hitnrun2.py:146` | CÓ — `entry_logic=f"hitnrun2:{tag}"`, tag ∈ `breakdown`/`breakup` |
| engulfing set reason | `core/domain/strategy/services/engulfing.py:167` | CÓ — `entry_logic=f"engulfing:{tag}"` |
| SL/TP raw numbers | `hitnrun2.py:100-101, 108-109` | CÓ — nhưng chỉ là `float` cuối; KHÔNG ghi "level nào thắng" (technical vs cap) |
| Domain event signal | `core/domain/strategy/events.py:7-16` (`SignalGeneratedEvent`) | **KHÔNG** có field reason / entry_logic |
| Forward: tạo order từ signal | `engine/app_services/strategy_app_service.py:398-407` (`_create_order`) | **MẤT** — `OrderAggregate.create(...)` KHÔNG nhận `entry_logic` |
| Forward: position aggregate | `core/domain/position/entities.py:19-41` | **KHÔNG** có field `reason`/`signal_meta`; `to_mongo`/`from_mongo` (191-226) không lưu |
| Forward: position events | `core/domain/position/events.py` (`PositionOpenedEvent`/`ClosedEvent`) | **KHÔNG** mang reason |
| Backtest: trade record | `core/domain/backtest/value_objects.py:227-297` (`Trade`) | **KHÔNG** có reason; chỉ entry/exit/sl/tp/pnl/commission/duration |
| Backtest: result collector | `backtest/engine/result_collector.py:263-281` (`_emit_trades`) | dựng `Trade` từ `OpenLot` — `OpenLot` (`lot_tracker.py:19-30`) không carry reason |

→ **Reason chỉ sống trong RAM tại đúng bar sinh signal, rồi biến mất.** Backtest engine không bao giờ thấy `Signal` object (nó replay qua PaperBroker fill → lot tracker), nên reason backtest còn xa hơn forward.

### 2.2 PnL/risk — phần lớn DERIVABLE từ data sẵn có

| Field | Nguồn | Sẵn có? |
|---|---|---|
| pnl, commission | `Trade.pnl/.commission` (`value_objects.py:252-253`); forward `PositionAggregate.realized_pnl` | ✅ |
| duration | `Trade.duration_seconds` (254); forward derive `closed_at − opened_at` | ✅ (forward FE đã tính: `positions-utils.ts:43`) |
| entry/exit/sl/tp | `Trade` + `PositionAggregate.sl_price/tp_price` (`entities.py:39-40`) | ✅ |
| slippage | backtest: PaperBroker bake vào fill_price → `Fill.slippage=0.0` (`result_collector.py:246`) | ⚠️ đang luôn 0; "slippage" chỉ ý nghĩa nếu so fill vs signal entry_price |
| **R-multiple** | `pnl / (|entry − sl| × qty)` — cần sl_price (có) | ✅ derivable |
| **% account risk** | `(|entry − sl| × qty) / initial_capital` — cần capital từ `config_snapshot.initial_capital` (`result_collector.py:438`) | ✅ backtest; ⚠️ forward cần account equity tại entry |
| **MAE/MFE** | min/max của OHLC trong `[entry_time, exit_time]` → `BarRepository` | ❌ cần compute từ bars |

### 2.3 Signal → Open → Close flow (chỗ mất rationale)

```
on_bar_completed (hitnrun2.py)
   │  Signal{entry_logic="hitnrun2:breakdown", sl, tp, entry_price}   ← reason CÓ ở đây
   ▼
strategy_app_service._process_signal (l.328)
   │  risk check → PositionSizer
   ▼
_create_order (l.398)   ✂  entry_logic KHÔNG được truyền  → reason MẤT
   │  OrderAggregate.create(sl_price, tp_price)  (no reason)
   ▼
PaperBroker fill → OrderFilledEvent
   ├─► [FORWARD]  PositionAggregate.open()      no reason field      → Mongo positions
   └─► [BACKTEST] result_collector → LotTracker → Trade()  no reason → Mongo backtest_trades
                                                                            │
   FE positions-tab / recent-trades-table  ◄────────────────────────────────┘
        chỉ render dir/entry/exit/pnl/qty/time  (chưa có explain drawer)
```

ASCII trên là 1 diagram (đủ theo yêu cầu).

---

## 3. Requirements (verify được, tách 5A vs 5B)

### Chung
- **Scope boundary**: chỉ ADD explain cho 1 closed trade đã chọn; KHÔNG đổi logic sinh signal, KHÔNG đổi cách tính pnl/equity hiện có.
- **Constraint**: import-linter (`fastapi` chỉ trong app; `core ◁ engine ◁ backtest ◁ app`); PK uuid7; không `await` trong atomic block.
- **Touchpoint FE**: drawer/panel cắm vào CẢ `positions-tab.tsx` (Backtest) lẫn `recent-trades-table.tsx` (Forward).

### 5A — PnL/risk (rẻ, derive)
- **Output**: 1 explain DTO chứa `r_multiple`, `account_risk_pct`, `commission`, `duration_seconds`, `mae`, `mfe`, `mae_pct`, `mfe_pct`.
- **Acceptance**: chọn 1 trade closed → drawer hiện đủ 8 số; R-multiple = `pnl / risk_amount` khớp tay-tính với sai số < 1e-6.
- **Scope**: MAE/MFE compute BE từ `BarRepository.stream(symbol, interval, entry_time, exit_time)`.

### 5B — Signal rationale (đắt, đụng engine)
- **Output**: explain DTO thêm `entry_reason` (structured: rule code + params) và `exit_reason` (sl_hit | tp_hit | signal_exit + level nào thắng technical/cap).
- **Acceptance**: trade mới (sau khi ship 5B) hiển thị đúng `"breakdown 4h: close < prev_low_4h=X"` và `"SL technical 8h (Y) > cap 1% (Z)"`.
- **Scope boundary**: position/trade cũ (không có reason) hiển thị fallback "rationale unavailable" — KHÔNG backfill.

---

## 4. Approaches Evaluated

### 4.1 Phasing: 5A trước hay 5B trước?

| Approach | Pros | Cons |
|---|---|---|
| **5A trước, 5B sau (RECOMMEND)** | 5A chỉ đụng read-side (query service + FE + BarRepository read), ship được ngay, giá trị ngay; cô lập rủi ro engine vào 5B | giao 2 lần |
| 5B trước | rationale là phần user nhấn mạnh | đụng core domain + engine + backtest engine; nếu regress → chặn cả slice; chưa thấy giá trị sớm |
| Gộp 1 phát | 1 lần merge | bề mặt rủi ro lớn nhất, khó review, dễ rollback toàn bộ |

### 4.2 Reason capture cho 5B (a/b/c)

| Opt | Cách | Pros | Cons | Verdict |
|---|---|---|---|---|
| **(a) Structured field** | Thêm `entry_reason`/`exit_reason` (enum + params dict) vào `PositionAggregate` + `Trade`; engine ghi lúc open, exit_reason lúc close; persist `to_mongo`/`from_mongo` | Chính xác, là source of truth, dài hạn đúng; tận dụng `Signal.entry_logic` đã có sẵn | Đụng core domain + engine `_create_order` + backtest `result_collector`/`lot_tracker`/`Trade`; cần "migration tư duy" cho doc cũ (đọc `.get(...)` nullable) | **RECOMMEND (dài hạn)** |
| (b) Reconstruct hậu kỳ | FE/BE recompute indicator tại entry bar từ OHLC | Không sửa engine sinh signal | **Fragile** — phải nhân bản logic `hitnrun2` lookback windows; lệch định nghĩa → giải thích SAI; vi phạm DRY (logic 2 nơi) | Loại |
| (c) Static config only | Chỉ show rule tĩnh từ `StrategyConfig.parameters` (entry_lookback=240, sl cap 1%…) + `entry_logic` tag nếu propagate được | Rẻ nhất, 0 đụng engine domain mở/đóng | Không có giá trị runtime thực (level X/Y/Z tại bar đó), chỉ là "luật chung" | **MVP (5B-lite)** — ship kèm 5A nếu propagate được `entry_logic` xuống order |

**Lưu ý quan trọng cho (c→a)**: `Signal.entry_logic` ĐÃ tồn tại. Một bước trung gian rẻ: chỉ cần truyền `entry_logic` qua `_create_order` → `OrderAggregate` → `PositionAggregate`/`Trade`. Đây là phần nhỏ nhất của (a), cho rationale text-level mà chưa cần structured params đầy đủ.

### 4.3 MAE/MFE compute: BE vs FE

| | Pros | Cons |
|---|---|---|
| **BE (RECOMMEND)** | 1 nguồn đúng; FE đã có ohlcv cho VIEWPORT nhưng KHÔNG đảm bảo phủ `[entry,exit]` (đặc biệt backtest dài / interval khác chart); query gọn qua `BarRepository.stream` | thêm read-side compute, cost ~O(bars trong holding window) |
| FE | tái dùng data chart sẵn | chart data có thể downsample / khác interval / không đủ range → MAE/MFE sai |

→ BE đúng đắn (data integrity).

---

## 5. Recommended Solution

**Phasing 5A → 5B; trong 5B chọn (a) structured field, ship kèm bước trung gian (c-lite: propagate `entry_logic`).**

- **5A** (read-only, an toàn): explain DTO = derived PnL/risk + MAE/MFE từ `BarRepository`. Không đụng engine/domain ghi.
- **5B** (đụng engine — cảnh báo rủi ro cao):
  - Thêm field nullable `entry_reason: dict | None`, `exit_reason: dict | None` vào `PositionAggregate` (`entities.py`) + `Trade` (`value_objects.py`), persist trong `to_mongo`/`from_mongo` (đọc bằng `.get(...)` → backward-compat doc cũ = `None`).
  - Engine: `_create_order` (`strategy_app_service.py:398`) truyền `signal.entry_logic` + structured meta; `PositionAggregate.open()` nhận thêm `entry_reason`; exit path set `exit_reason` (phân biệt sl_hit/tp_hit từ giá fill vs sl/tp).
  - Backtest: `OpenLot` (`lot_tracker.py`) + `_emit_trades` (`result_collector.py:263`) cõng reason. **Khó hơn forward** vì backtest engine không thấy `Signal` — cần đường dẫn reason đi kèm order/fill (vd qua `OrderResult.entry_logic` hoặc đính vào order doc rồi join). Đây là điểm đắt nhất.

**Cảnh báo**: đụng `PositionAggregate` + `Trade` + `_create_order` + `result_collector` + `lot_tracker` = bề mặt regression cao nhất repo. Import-linter: reason là plain dict/enum trong core, không kéo fastapi. uuid7 giữ nguyên (không thêm PK mới).

---

## 6. Vertical Slice Breakdown

### 6.1 Backend

**5A**
- `StrategyQueryService` (`engine/strategy_query_service.py`): thêm `GetTradeExplainQuery(subscription_id, trade_id)` + method `get_trade_explain` → load closed position (forward) hoặc backtest trade, compute derived fields, gọi `BarRepository.stream` cho MAE/MFE.
- Compute helper (core, pure): `r_multiple`, `account_risk_pct`, `mae/mfe` từ list[Bar] + entry/exit/side. Đặt cạnh metrics builder để DRY.
- Backtest variant: query `BacktestTradeRepository` + `config_snapshot.initial_capital`.

**5B**
- Domain: `PositionAggregate.entry_reason/exit_reason` + `Trade` 2 field + serde nullable.
- Engine: `_create_order` propagate; open/close set reason.
- Backtest: reason chui qua order → lot → trade.

### 6.2 Frontend

- New `trade-explain-drawer.tsx` (slide-over), 2 section: **Rationale** (entry/exit reason; fallback nếu null) + **PnL/Risk** (R-multiple, risk%, commission, slippage, MAE/MFE, duration).
- Backtest: `positions-tab.tsx` đã có `onPositionClick` (l.89) → mở drawer thay vì chỉ highlight.
- Forward: `recent-trades-table.tsx` thêm row `onClick` → drawer (StrategyTrade thiếu sl/tp → 5A forward cần BE bổ sung field hoặc drawer fetch explain theo `trade_id`).
- Tách `positions-utils.ts` reuse `fmtDuration`/`fmtPnl`.

### 6.3 API Contract (explain DTO)

```jsonc
// GET /api/v1/strategies/{sub_id}/trades/{trade_id}/explain  (forward)
// GET /api/v1/backtest/runs/{run_id}/trades/{trade_id}/explain (backtest)
{
  "trade_id": "uuid7",
  "direction": "LONG",
  "entry_price": 0, "exit_price": 0,
  "sl_price": 0, "tp_price": 0,
  "pnl": 0, "commission": 0, "slippage": 0,
  "duration_seconds": 0,
  "r_multiple": 0,          // 5A
  "account_risk_pct": 0,    // 5A
  "mae": 0, "mfe": 0,       // 5A (BarRepository)
  "mae_pct": 0, "mfe_pct": 0,
  "entry_reason": {         // 5B nullable
    "rule": "hitnrun2:breakdown",
    "entry_lookback_bars": 240,
    "trigger_level": 0      // prev_low_4h
  },
  "exit_reason": {          // 5B nullable
    "kind": "sl_hit",       // sl_hit|tp_hit|signal_exit
    "sl_source": "technical_8h" // technical_8h | cap_1pct
  }
}
```

FE type `TradeExplain` mirror; `entry_reason`/`exit_reason` optional → drawer fallback "rationale unavailable".

---

## 7. Decomposition into Sub-tasks (ordered, shippable)

**5A (ship đầu tiên, độc lập)**
1. Core pure helper: compute R-multiple, account_risk_pct, MAE/MFE từ `list[Bar]` + entry/exit/side (+ unit test).
2. `StrategyQueryService.get_trade_explain` (forward) + backtest variant; wire `BarRepository`.
3. Routes (app layer) GET explain forward + backtest; explain DTO.
4. FE `trade-explain-drawer.tsx` + cắm vào `positions-tab` (Backtest) và `recent-trades-table` (Forward); render PnL/risk, rationale section ẩn/placeholder.

**5B (sau, đụng engine — review kỹ)**
5. Domain field `entry_reason`/`exit_reason` (PositionAggregate + Trade) + serde nullable + test backward-compat (doc cũ → None).
6. Engine forward: `_create_order` propagate `entry_logic`; open/close set structured reason + exit_reason classify (sl_hit/tp_hit).
7. Backtest: reason đi kèm order→lot→trade (`lot_tracker` + `result_collector._emit_trades`).
8. FE: render rationale section thật (thay placeholder).

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| **5B đụng engine = regression cao** (signal/order/fill là hot path) | Tách 5B sau 5A; test engine "signal không đổi": snapshot số trades/pnl của 1 backtest fixture TRƯỚC/SAU 5B phải bằng nhau |
| Reason backtest khó (engine không thấy Signal) | Propagate qua order field; nếu quá đắt → ship 5B-lite (c): chỉ static config + `entry_logic` tag, defer structured params |
| Reconstruct hậu kỳ (b) lệch logic | Loại — không nhân bản lookback logic |
| MAE/MFE compute cost (holding window dài, 1m bars) | dùng `BarRepository.stream` (cursor, không load hết RAM); chỉ compute on-demand khi mở drawer, không precompute hàng loạt |
| Backward-compat: position/trade cũ không có reason | field nullable, `.get(...)`, FE fallback "unavailable"; KHÔNG migration/backfill |
| slippage luôn 0 (PaperBroker bake vào fill_price) | hiển thị "n/a (paper)" hoặc derive `fill_price − signal.entry_price` nếu propagate được entry_price gốc — defer |
| import-linter vỡ | reason = dict/enum thuần trong core; không import fastapi |

---

## 9. Success Metrics & Validation

- `pytest tests/core_test` + backtest engine tests pass; thêm: explain helper unit test (R-multiple/MAE/MFE), backward-compat serde test (doc thiếu reason → None).
- **Engine no-regress test (bắt buộc cho 5B)**: chạy 1 backtest fixture, assert tổng số trades + tổng pnl + metrics KHÔNG đổi so với baseline.
- import-linter: `lint-imports` pass (7 contracts).
- `cd web && npm run lint && npm run build` pass; type `TradeExplain` khớp DTO.

---

## 10. Dependencies & Open Questions

**Cross-ref slices**
- Slice 1 (`positions-tab.tsx`, `backtest-api.ts`): drawer dùng lại `BacktestPosition` shape + `onPositionClick`.
- Slice 3 (forward trades, `recent-trades-table.tsx`, `strategy_query_service.get_trades`): forward explain cần `trade_id` ổn định → đã có `p.id` (position id).
- Slice 4 (order link): `Trade.entry_order_id/exit_order_id` + `Order.resulting_trade_id` (`result_collector.py:287`) — explain có thể link sang order detail của Slice 4.

**Open Questions**
1. **Có làm 5B trong scope này hay defer?** RECOMMEND chỉ commit 5A + 5B-lite (c, propagate `entry_logic`); structured 5B(a) tách plan riêng do rủi ro engine.
2. a/b/c chốt ở plan: xác nhận chọn **(a)** dài hạn, **(c)** cho MVP — đúng intent user?
3. Backtest reason: chấp nhận đường `OrderResult.entry_logic` (sửa broker fill result) hay chỉ defer? Cần xác nhận PaperBroker fill result shape (chưa đọc trong report này).
4. Forward "% account risk": lấy account equity tại entry từ đâu (broker balance snapshot lúc open có lưu không)? Backtest có `initial_capital`; forward cần xác nhận.
5. slippage forward live: có nguồn fill vs intended price không, hay luôn n/a?

---

Status: DONE
Summary: Slice 5 brainstorm hoàn tất — xác nhận `Signal.entry_logic` sinh ra nhưng rớt tại `_create_order` (`strategy_app_service.py:398`), Trade/PositionAggregate không persist reason; recommend tách 5A (PnL/risk + MAE/MFE từ BarRepository, read-only) ship trước, 5B (structured reason capture, đụng engine — rủi ro cao) sau với engine no-regress test bắt buộc.
Concerns: 5B chạm core domain + engine + backtest engine cùng lúc = bề mặt regression cao nhất; backtest reason khó vì engine không thấy Signal object — có thể phải ship 5B-lite (config tĩnh + entry_logic tag) và defer structured params.
