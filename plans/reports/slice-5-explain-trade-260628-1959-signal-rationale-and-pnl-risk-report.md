# Slice 5 — Explain Trade (Signal Rationale + PnL/Risk) — Brainstorm Report

## Metadata

| | |
|---|---|
| Priority | 5/5 (cuối, đắt & rủi ro nhất — đụng engine cho entry rationale) |
| Surface | FE + BE |
| Depends on | Slice 3 (backtest detail/positions), Slice 1 (forward trades), Slice 2 (order link) |
| Unblocks | none (capstone) |
| Date | 2026-06-28 |

> Re-scout note: report này đã verify lại toàn bộ citation bằng Read/Grep (xem §Changes cuối). Phát hiện mới quan trọng: PaperBroker dùng CHUNG cho backtest + forward, và **exit_reason gần như sẵn có** từ `OrderEvent.reason` — không đắt như đánh giá ban đầu. Chỉ **entry rationale** mới thực sự rớt.

---

## 1. Problem Statement

Cho 1 trade (closed position) bất kỳ trong tab **Backtest** hoặc **Forward**, user muốn mở "explain" gồm 2 phần (chốt CẢ HAI):

1. **Signal rationale** — vì sao strategy VÀO (pattern/indicator nào trigger: breakdown 4h window, engulfing strong) và vì sao RA (SL hit / TP hit; với hitnrun2: SL = looser của technical 8h low vs cap 1%; TP = looser của technical 1h high vs min 2%).
2. **PnL/risk breakdown** — R-multiple, % account risk, commission, slippage, MAE/MFE (max adverse/favorable excursion), duration.

Hiện FE chỉ show `dir / entry / exit / pnl / qty / time`, không có detail drawer. BE: `Signal.entry_logic` được sinh ra nhưng **rớt** trước khi tới order/position/trade (chứng minh §2). Exit reason thì NGƯỢC LẠI — đã được PaperBroker ghi vào `OrderEvent.reason`, chỉ chưa surface lên trade record.

---

## 2. Current State (evidence — đã verify từng dòng)

### 2.1 Entry rationale: sinh ra rồi MẤT

| Nơi | File:line | Trạng thái |
|---|---|---|
| `Signal.entry_logic` field | `core/domain/strategy/value_objects.py:20` (`entry_logic: str = ""`) | CÓ |
| hitnrun2 set reason | `core/domain/strategy/services/hitnrun2.py:146` (`entry_logic=f"hitnrun2:{tag}"`, tag ∈ `breakdown`/`breakup`) | CÓ |
| engulfing set reason | `core/domain/strategy/services/engulfing.py:169` (`entry_logic=f"engulfing:{tag}"`) | CÓ |
| **`entry_logic` được ĐỌC ở đâu?** | grep toàn repo: chỉ 3 hit trên — **0 reader**, 0 persist | **DEAD field** |
| `_create_order` propagate? | `engine/app_services/strategy_app_service.py:383-407` | **MẤT** — `OrderAggregate.create(...)` (l.398) không nhận `entry_logic` |
| `OrderAggregate.create` signature | `core/domain/order/entities.py:60-92` | params: `subscription_id, symbol, side, order_type, quantity, price, stop_price, sl_price, tp_price` — **không có entry_logic** |
| `SignalGeneratedEvent` | `core/domain/strategy/events.py:7-16` | có field giá nhưng **KHÔNG có reason**; grep: chỉ export trong `__init__.py`, **0 emitter / 0 handler** → dead event |
| `PositionAggregate` | `core/domain/position/entities.py:19-41` | **KHÔNG** field reason; `open()` (l.43-80), `to_mongo`/`from_mongo` (191-226) không lưu |
| `PositionOpenedEvent` | `core/domain/position/events.py:7-15` | **KHÔNG** mang reason |
| backtest `Trade` | `core/domain/backtest/value_objects.py:227-297` | **KHÔNG** field reason |
| `OpenLot` (FIFO) | `backtest/engine/lot_tracker.py:19-30` | **KHÔNG** field reason; backtest engine không bao giờ thấy `Signal` object |

### 2.2 Exit reason: ĐÃ tồn tại ở order-event level (phát hiện mới — rẻ)

| Nơi | File:line | Trạng thái |
|---|---|---|
| Reason codes | `core/domain/brokers/events.py:20-30` (`REASON_AUTO_SL="auto_sl"`, `REASON_AUTO_TP="auto_tp"`, `REASON_MARKET_FILL`, `REASON_LIMIT_CROSS`, `REASON_END_OF_RUN`…) | CÓ |
| `OrderEvent.reason` | `core/domain/brokers/events.py:38` (`reason: str \| None`) — persist qua `to_dict`/`from_dict` (l.45,55) | CÓ |
| SL/TP classify | `paper_broker.py:654-669` (`_check_sl_tp` → `REASON_AUTO_SL`/`REASON_AUTO_TP`); **SL trước TP** khi 1 bar straddle cả hai (l.657, docstring l.86) | CÓ |
| Synthetic exit emit | `paper_broker.py:671-723` (`_fire_synthetic_exit`) emit `OrderEvent` với reason | CÓ |
| Backtest `Order.events` | `core/domain/backtest/value_objects.py:127` (`events: list[OrderEvent]`) + persist (`to_mongo` 148) | CÓ |
| Back-link trade→exit order | `result_collector.py:285-287` (`exit_order.resulting_trade_id`); `Trade.exit_order_id` (`value_objects.py:247`) | CÓ |

→ **exit_reason derivable read-side**: `Trade.exit_order_id` → `Order.events[].reason` (auto_sl/auto_tp). Với hitnrun2 còn so `exit_price` vs `sl_price`/`tp_price` để biết level "technical hay cap" thắng (cần SL/TP component, xem §10 Q3).

### 2.3 PaperBroker dùng CHUNG backtest + forward (phát hiện mới — sửa kết luận cũ)

- `paper_broker.py:1-2` docstring: "Paper broker implementation for simulated trading + backtesting".
- `_execute_fill` (l.465-513) gọi `PositionAggregate.open(...)` ở CẢ hai path (l.489 LONG, l.505 SHORT). Backtest KHÔNG thay PaperBroker bằng engine khác — `result_collector` chỉ là consumer subscribe fill/event callback để build `Order`/`Trade` SONG SONG với position state của broker.
- Hệ quả: nơi tốt nhất để inject entry reason là `OrderAggregate` (chảy qua broker → cả 2 path), không phải sửa riêng forward/backtest.

### 2.4 PnL/risk — phần lớn DERIVABLE

| Field | Nguồn (verified) | Sẵn có? |
|---|---|---|
| pnl, commission | `Trade.pnl/.commission` (`value_objects.py:252-253`); forward `PositionAggregate.realized_pnl` (`entities.py:33`) | ✅ |
| duration | `Trade.duration_seconds` (254); forward derive (FE đã làm: `positions-utils.ts:43`) | ✅ |
| entry/exit/sl/tp | `Trade` + `PositionAggregate.sl_price/tp_price` (`entities.py:39-40`) | ✅ |
| slippage | PaperBroker bake vào fill_price (`paper_broker.py:436-439` `_apply_slippage`); `Fill.slippage=0.0` (`result_collector.py:246`) | ⚠️ luôn 0; chỉ ý nghĩa nếu so fill vs intended price |
| **R-multiple** | `pnl / (\|entry − sl\| × qty)` | ✅ derivable |
| **% account risk** | `(\|entry − sl\| × qty) / capital`; backtest capital từ `config_snapshot.initial_capital` (`result_collector.py:438`) | ✅ backtest; ⚠️ forward cần equity-at-entry |
| **MAE/MFE** | min/max OHLC trong `[entry_time, exit_time]` → `BarRepository.stream` (đã dùng ở `backtest_app_service.py:184`) | ❌ cần compute từ bars |

### 2.5 Signal → Open → Close flow (verified)

```
on_bar_completed (hitnrun2.py:72) → Signal{entry_logic="hitnrun2:breakdown", sl, tp}   ← entry reason CÓ
   ▼
strategy_app_service._process_signal (l.328) → _create_order (l.398)
        ✂ entry_logic KHÔNG truyền vào OrderAggregate.create   → entry reason MẤT
   ▼
PaperBroker (shared bt+fwd) submit_order (l.153) → _execute_fill (l.465)
   │  PositionAggregate.open(sl_price, tp_price)   no entry reason
   │  exit: _on_bar_completed (l.566) → _check_sl_tp → OrderEvent{reason=auto_sl|auto_tp}  ← exit reason CÓ
   ├─► [FORWARD]  positions collection (no entry reason; exit reason chỉ trong order events nếu lưu)
   └─► [BACKTEST] result_collector → Trade (no entry reason)  +  Order.events[].reason (exit reason CÓ)
                                                                            │
   FE positions-tab / recent-trades-table ◄────────────────────────────────┘  (chưa có explain drawer)
```

---

## 3. Requirements (verify được, tách 5A vs 5B)

### Chung
- **Scope boundary**: chỉ ADD explain cho 1 closed trade đã chọn; KHÔNG đổi logic sinh signal, KHÔNG đổi cách tính pnl/equity.
- **Constraint**: import-linter (`fastapi` chỉ trong app; `core ◁ engine ◁ backtest ◁ app`); PK uuid7; không `await` trong atomic block (PaperBroker callback fire NGOÀI lock — `paper_broker.py:17-19`).
- **Touchpoint FE**: drawer cắm vào CẢ `positions-tab.tsx` (Backtest) lẫn `recent-trades-table.tsx` (Forward).

### 5A — PnL/risk + exit_reason (rẻ, read-only)
- **Output**: explain DTO chứa `r_multiple`, `account_risk_pct`, `commission`, `duration_seconds`, `mae`, `mfe`, `mae_pct`, `mfe_pct`, `exit_reason` (derive từ `Order.events[].reason`).
- **Acceptance**: chọn 1 trade closed → drawer hiện đủ số; R-multiple = `pnl / risk_amount` khớp tay-tính sai số < 1e-6; trade auto-SL hiển thị `exit_reason="auto_sl"`.
- **Scope**: MAE/MFE BE từ `BarRepository.stream(symbol, interval, entry_time, exit_time)`.

### 5B — Entry rationale (đắt, đụng engine)
- **Output**: explain DTO thêm `entry_reason` (structured: rule code + trigger params).
- **Acceptance**: trade mới (sau ship 5B) hiển thị `"breakdown 4h: close < prev_low_4h=X"`.
- **Scope boundary**: trade cũ không có entry_reason → fallback "rationale unavailable"; KHÔNG backfill.

---

## 4. Approaches Evaluated

### 4.1 Phasing: 5A trước hay 5B trước?

| Approach | Pros | Cons |
|---|---|---|
| **5A trước, 5B sau (RECOMMEND)** | 5A chỉ read-side (query + FE + BarRepository read + join exit reason); ship ngay, giá trị ngay; cô lập rủi ro engine vào 5B. 5A nay bao gồm CẢ exit_reason (free từ OrderEvent) | giao 2 lần |
| 5B trước | entry rationale là phần user nhấn | đụng `OrderAggregate` + core domain + `_create_order`; nếu regress chặn cả slice |
| Gộp 1 phát | 1 merge | bề mặt rủi ro lớn nhất |

### 4.2 Entry-reason capture cho 5B (a/b/c)

| Opt | Cách | Pros | Cons | Verdict |
|---|---|---|---|---|
| **(a) Structured field** | Thêm `entry_logic`/`entry_reason` param vào `OrderAggregate.create`; chảy qua PaperBroker → `PositionAggregate.open` + `Order`/`Trade`; persist nullable | Chính xác, source of truth; PaperBroker shared nên 1 đường phủ cả bt+fwd; tận dụng `Signal.entry_logic` đã có | Đụng `OrderAggregate.create` (hot path, mọi order qua đây), `_create_order`, position open, lot_tracker→Trade; migration tư duy doc cũ | **RECOMMEND (dài hạn)** |
| (b) Reconstruct hậu kỳ | recompute indicator tại entry bar | không sửa engine | fragile, nhân bản lookback logic hitnrun2 → giải thích SAI, vi phạm DRY | Loại |
| (c) Static config only | show rule tĩnh từ `StrategyConfig.parameters` (entry_lookback=240, cap 1%…) | rẻ nhất, 0 đụng order/domain | không có giá trị runtime tại bar đó | **MVP (5B-lite)** ghép vào 5A |

**Bước trung gian (c→a)**: chỉ propagate `entry_logic` string qua `_create_order` → `OrderAggregate.create` → `Order`/`Trade`. Đây là phần nhỏ nhất của (a) cho rationale text-level. Vẫn đụng `OrderAggregate.create` signature (hot path) → cần no-regress test.

### 4.3 MAE/MFE compute: BE vs FE

| | Pros | Cons |
|---|---|---|
| **BE (RECOMMEND)** | 1 nguồn đúng; `BarRepository.stream` pattern đã dùng (`backtest_app_service.py:184`); query gọn theo `[entry,exit]` | thêm read-side compute O(bars holding) |
| FE | tái dùng chart data | chart có thể downsample / khác interval / không đủ range → MAE/MFE sai |

### 4.4 Exit-reason (mới — gần như free)

- Derive read-side: `Trade.exit_order_id` → load `Order` → `events[]` tìm event terminal (`reason ∈ auto_sl/auto_tp/limit_cross/end_of_run`). Không đụng engine. Nằm trong 5A.
- "Technical vs cap" (hitnrun2 SL/TP thắng level nào): cần raw component (technical low/high vs cap) tại entry — KHÔNG lưu hiện tại; chỉ suy được từ `entry_logic` + params + giá. Để 5B (structured) hoặc hiển thị thô `exit_price` vs `sl_price`.

---

## 5. Recommended Solution

**Phasing 5A → 5B. 5A = PnL/risk + MAE/MFE + exit_reason (tất cả read-only). 5B = entry_reason structured (đụng `OrderAggregate.create`).**

- **5A** (an toàn, 0 đụng engine ghi): explain DTO gồm derived PnL/risk + MAE/MFE từ `BarRepository.stream` + exit_reason join từ `Order.events[].reason`.
- **5B** (đụng engine — cảnh báo):
  - Thêm `entry_logic`/`entry_reason` (nullable) param vào `OrderAggregate.create` (`order/entities.py:60`) → field trên `OrderAggregate`.
  - `_create_order` (`strategy_app_service.py:398`) truyền `signal.entry_logic` (+ structured meta nếu làm full a).
  - `PaperBroker._execute_fill` (l.489,505): truyền entry reason vào `PositionAggregate.open` → field nullable persist.
  - Backtest: reason đi kèm order → `result_collector._upsert_order` (l.175) đọc từ order → `OpenLot` → `_emit_trades` (l.263) gắn lên `Trade`.

**Cảnh báo**: `OrderAggregate.create` là hot path (mọi order, gồm synthetic exit `_fire_synthetic_exit` l.679 — exit order phải để entry_reason=None). Đụng `PositionAggregate` + `Trade` + collector = bề mặt regression cao nhất repo. import-linter: reason là str/dict/enum thuần trong core, không kéo fastapi. uuid7 giữ nguyên.

---

## 6. Vertical Slice Breakdown

### 6.1 Backend

**5A**
- Core pure helper (cạnh `metrics_builder`): `r_multiple`, `account_risk_pct`, `mae/mfe` từ `list[Bar]` + entry/exit/side.
- `StrategyQueryService` (`engine/strategy_query_service.py`): `GetTradeExplainQuery(subscription_id, trade_id)` + `get_trade_explain` → load closed position (forward) / backtest trade, compute derived, gọi `BarRepository.stream`, join exit Order events cho exit_reason.
- Backtest variant: `BacktestTradeRepository` + `config_snapshot.initial_capital` + `Order.events`.

**5B**
- `OrderAggregate.create` + field entry reason (nullable); `_create_order` propagate; `_execute_fill`→`PositionAggregate.open` field; `result_collector`/`lot_tracker`/`Trade` cõng reason; serde nullable.

### 6.2 Frontend

- New `trade-explain-drawer.tsx` (slide-over): section **Rationale** (entry_reason fallback null; exit_reason hiện ngay từ 5A) + **PnL/Risk** (R-multiple, risk%, commission, slippage, MAE/MFE, duration).
- Backtest: `positions-tab.tsx` đã có `onPositionClick` (l.89) → mở drawer.
- Forward: `recent-trades-table.tsx` thêm `onClick` (StrategyTrade `types/strategy.ts` + `recent-trades-table.tsx:7-16` thiếu sl/tp → drawer fetch explain theo `trade_id`).
- Reuse `positions-utils.ts` `fmtDuration`/`fmtPnl`.

### 6.3 API Contract (explain DTO)

```jsonc
// GET /api/v1/strategies/{sub_id}/trades/{trade_id}/explain      (forward)
// GET /api/v1/backtest/runs/{run_id}/trades/{trade_id}/explain   (backtest)
{
  "trade_id": "uuid7",
  "direction": "LONG",
  "entry_price": 0, "exit_price": 0, "sl_price": 0, "tp_price": 0,
  "pnl": 0, "commission": 0, "slippage": 0, "duration_seconds": 0,
  "r_multiple": 0,          // 5A
  "account_risk_pct": 0,    // 5A
  "mae": 0, "mfe": 0, "mae_pct": 0, "mfe_pct": 0,   // 5A (BarRepository)
  "exit_reason": "auto_sl", // 5A — từ Order.events[].reason (auto_sl|auto_tp|limit_cross|end_of_run|market_fill)
  "entry_reason": {         // 5B nullable
    "rule": "hitnrun2:breakdown",
    "entry_lookback_bars": 240,
    "trigger_level": 0
  }
}
```

FE type `TradeExplain` mirror; `entry_reason` optional → drawer fallback "rationale unavailable".

---

## 7. Decomposition into Sub-tasks (ordered, shippable)

**5A (ship đầu, độc lập, read-only)**
1. Core pure helper R-multiple / account_risk_pct / MAE/MFE (+ unit test).
2. `StrategyQueryService.get_trade_explain` (forward) + backtest variant; wire `BarRepository`; join exit Order events → exit_reason.
3. Routes (app) GET explain forward + backtest; explain DTO.
4. FE `trade-explain-drawer.tsx` cắm vào `positions-tab` + `recent-trades-table`; render PnL/risk + exit_reason; entry_reason placeholder.

**5B (sau, đụng engine — review kỹ)**
5. `OrderAggregate.create` + field entry reason nullable; serde; test exit order = None.
6. `_create_order` propagate `entry_logic`; `_execute_fill`→`PositionAggregate.open` set reason; serde nullable.
7. Backtest: reason order→lot→Trade (`result_collector._upsert_order`/`_emit_trades`, `lot_tracker.OpenLot`).
8. FE: render rationale section thật.

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| **5B đụng `OrderAggregate.create` = hot path** (mọi order, gồm synthetic exit) | entry reason nullable default None; synthetic exit để None; snapshot số trades/pnl/metrics của 1 backtest fixture TRƯỚC/SAU phải bằng nhau |
| Backtest entry reason đi qua order (engine không thấy Signal) | propagate qua `OrderAggregate` → collector đọc từ order; nếu quá đắt → 5B-lite (c) defer structured params |
| Reconstruct (b) lệch logic | Loại |
| MAE/MFE compute cost (1m, holding dài) | `BarRepository.stream` cursor; compute on-demand khi mở drawer, không precompute |
| Backward-compat: trade/position cũ không reason | field nullable, `.get(...)`, FE fallback; KHÔNG backfill |
| slippage luôn 0 (paper bake fill_price) | hiển thị "n/a (paper)"; defer derive |
| exit_reason "technical vs cap" không lưu | 5A chỉ hiện auto_sl/auto_tp thô; level-source defer 5B |
| import-linter vỡ | reason = str/dict/enum thuần core |

---

## 9. Success Metrics & Validation

- `pytest tests/core_test` + backtest engine tests pass; thêm: explain helper unit test (R-multiple/MAE/MFE), exit_reason join test (auto_sl), backward-compat serde test (doc thiếu reason → None).
- **Engine no-regress test (bắt buộc 5B)**: backtest fixture → tổng trades + tổng pnl + metrics KHÔNG đổi vs baseline.
- import-linter `lint-imports` pass (7 contracts).
- `cd web && npm run lint && npm run build` pass; `TradeExplain` khớp DTO.

---

## 10. Dependencies & Open Questions

**Cross-ref slices**
- Slice 3 (`positions-tab.tsx`, `backtest-api.ts` `BacktestPosition`): drawer dùng lại shape + `onPositionClick`.
- Slice 1 (forward, `recent-trades-table.tsx`, `strategy_query_service.get_trades` l.131): forward explain cần `trade_id` ổn định → đã có `p.id`.
- Slice 2 (order link): `Trade.entry_order_id/exit_order_id` + `Order.resulting_trade_id` (`result_collector.py:287`). Slice 5 exit_reason ĐỌC chính `Order.events` mà Slice 2 surface → phụ thuộc Slice 2 đã expose order/events.

**Open Questions**
1. **Làm 5B trong scope này hay defer?** RECOMMEND ship 5A (gồm exit_reason) + 5B-lite (c, propagate `entry_logic`); structured 5B(a) tách plan riêng do rủi ro `OrderAggregate.create`.
2. a/b/c: nghiêng (a) dài hạn + (c) MVP — nhưng đây là quyết định người dùng, **chưa được người dùng xác nhận**.
3. Exit "technical vs cap" (hitnrun2): có cần lưu SL/TP component lúc open để giải thích level nào thắng, hay chấp nhận hiện thô `exit_price` vs `sl_price`/`tp_price`?
4. Forward "% account risk": equity-at-entry lấy đâu? Backtest có `initial_capital`; forward `PaperBroker.get_balance` là live, không snapshot tại open — cần xác nhận.
5. Forward exit_reason persistence: backtest có `Order.events` lưu DB; forward path có lưu order events vào DB không (hay chỉ in-memory broker)? Nếu không, forward exit_reason cần nguồn khác — cần xác nhận với Slice 1/2.

---

Status: DONE
Summary: Re-scout xong, verify mọi citation. Sửa drift lớn — exit_reason gần như FREE (từ `OrderEvent.reason` auto_sl/auto_tp + `Trade.exit_order_id`→`Order.events`), nên gộp vào 5A; chỉ entry_reason mới thực rớt (entry_logic là dead field, `_create_order` không propagate, 0 reader). PaperBroker shared backtest+forward → inject entry reason tại `OrderAggregate.create` phủ cả 2 path.
Changes:
- engulfing entry_logic line 167 → **169** (drift sửa); hitnrun2 l.146, value_objects.py l.20 (xác nhận).
- _create_order xác nhận l.398 không truyền entry_logic; bổ sung `OrderAggregate.create` signature (`order/entities.py:60-92`, không có entry_logic param).
- MỚI: `entry_logic` 0 reader toàn repo (dead field); `SignalGeneratedEvent` 0 emitter/0 handler (dead event).
- MỚI: PaperBroker (`core/infra/brokers/paper/paper_broker.py`) shared bt+fwd, `_execute_fill` mở `PositionAggregate` cả 2 path; exit reason có sẵn `_check_sl_tp` l.654-669 + reason codes `brokers/events.py:20-30`; `Order.events` persist `backtest/value_objects.py:127`.
- MỚI: `BarRepository.stream` đã dùng ở `backtest_app_service.py:184` → củng cố MAE/MFE BE.
- Recommendation đổi: 5A nay bao gồm exit_reason (read-only join); 5B chỉ còn entry_reason.
Concerns: 5B đụng `OrderAggregate.create` (hot path mọi order, gồm synthetic exit) = regression cao — bắt buộc no-regress test. Forward exit_reason cần xác nhận order events có persist DB không (Q5). Q2 a/b/c là quyết định người dùng, chưa được người dùng xác nhận.
