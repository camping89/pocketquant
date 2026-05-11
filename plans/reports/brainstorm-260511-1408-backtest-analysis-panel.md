---
type: brainstorm
date: 2026-05-11 14:08
slug: backtest-analysis-panel
status: design-approved
---

# Brainstorm — Backtest Analysis Panel Epic

## Problem Statement

User muốn xem **đầy đủ kết quả backtest của một subscription**: positions trên chart + metrics + equity/drawdown + filter/sort positions. Hiện tại chỉ có position boxes (SL/TP/Entry/Exit) overlay trên candle chart, thiếu destination để analyze.

Đồng thời, backend pairing logic có 3 gaps: long-only assumption, partial fills, commission comment misleading.

## Current State (Verified)

### Backend (đã có)
- `PositionRecord` value object — `packages/pocketquant-backtest/.../domain/value_objects.py:55`
- `_build_positions()` pair sequential BUY/SELL — `result_collector.py:209`
- Persisted MongoDB qua `BacktestResult.to_mongo()`
- API `GET /api/v1/strategies/{sid}/symbols/{subId}/backtest` trả full doc (positions + equity_curve + metrics + config_snapshot)

### Frontend (đã có)
- `BacktestPosition` type — `api/backtest-api.ts:3`
- `useSubscriptionBacktest()` — `hooks/use-subscriptions.ts:46`
- `PositionBoxPrimitive` (Lightweight-charts v5 primitive) — `components/chart/position-box-primitive.ts`
- BUY/SELL markers dedup theo timestamp — `trading-chart.tsx:154`

### Gaps
1. **Destination thiếu** — chỉ thấy boxes trên chart, không có metrics/equity/list.
2. **Backend pairing** — `_is_buy_order` infer side từ `_position_qty` state (long-only fail); `_build_positions` pair sequential 1 BUY ↔ 1 SELL (fail partial fills); `_collector.py:24` comment sai.

### Non-gap
- `commission_bps` NOT a bug — `BacktestConfig.commission_percent` (line 62) convert đúng bps → decimal. Chỉ docstring `_collector.py:24` viết sai.

## Decisions

| Q | Decision |
|---|---|
| Entry point | Mở rộng **subscription panel** hiện tại |
| Scope | 1 backtest run / 1 sub, luôn latest |
| View bổ sung | Position table + Equity/DD subchart + Metrics dashboard + Filter/sort |
| Layout | **Bottom panel collapsible** dưới chart, tabs (Metrics / Positions / Equity) |
| Backend bugs | Fix **tất cả** (commission comment + long-only + partial fills + short) |
| API | Reuse `getSubscriptionBacktest` (đã trả full doc) |
| Equity render | **Lightweight-charts v5 pane API** (`chart.addPane()`) |
| Short flip | **2 PositionRecord** (close LONG + open SHORT) — Backtrader/QuantConnect convention |
| Run history | **Scope out** — luôn latest |

## Approaches Evaluated

### A. Bottom panel + pane API (CHOSEN)
- **Pros**: TimeScale tự sync; theming nhất quán; layout pattern quen thuộc (Trading View style); reuse `getSubscriptionBacktest`.
- **Cons**: Resize logic FE; pane API yêu cầu lightweight-charts ≥5.0.8.

### B. Right drawer overlay
- **Pros**: Chart không bị mất chiều cao khi đóng drawer.
- **Cons**: Đẩy chart sang trái khi mở, animation phức tạp; equity subchart chèn vào drawer mất sync với main chart timeScale.

### C. Dedicated route `/backtest/$sid/$subId`
- **Pros**: Layout tự do, dễ deep-link.
- **Cons**: Tách flow khỏi chart hiện tại → user phải navigate; over-engineer cho scope "extend sub panel".

## Recommended Solution

**Bottom collapsible panel** với 3 tabs (Metrics | Positions | Equity), reuse `useSubscriptionBacktest`. Equity tab dùng pane trên main chart. Backend refactor `result_collector` sang **FIFO lot tracking**, expose `side` qua `OrderResult`.

## Phases

### Phase 1 — Backend correctness
**Files**: `pocketquant-core/.../brokers/models.py`, `pocketquant-backtest/.../engine/result_collector.py`, `domain/value_objects.py`
- Add `side: OrderSide` to `OrderResult`. Update `PaperBroker` + OKX broker fill emission.
- Refactor `_calculate_trade_pnl` → **FIFO open-lots queue**. Lot fields: `direction (LONG|SHORT)`, `entry_price`, `entry_time`, `qty_remaining`, `sl_price`, `tp_price`, `commission_entry`.
- Refactor `_build_positions` → emit PositionRecord khi 1 lot fully closed (hoặc remaining khi backtest end → open position).
- Add `direction` field to `PositionRecord`.
- Short flip: SELL qty > LONG lots → đóng LONG lots FIFO + excess mở SHORT lot. Tạo 1 close PositionRecord / lot consumed + 1 open PositionRecord cho SHORT excess.
- Fix `_collector.py:24` docstring `commission_bps` → `commission_percent`.
- Tests: long-only, short-only, scale-in/out, partial fills, flip LONG→SHORT, flip SHORT→LONG.

### Phase 2 — API types sync
- Verify shape `GET .../backtest` match `BacktestResult.to_dict()`.
- Update TS types: `SubscriptionBacktest` thêm `equity_curve`, `metrics`, `config_snapshot`; `BacktestPosition` thêm `direction`.
- Remove duplicated `BacktestResponse` type trong `backtest-api.ts` nếu trùng `strategy-api.ts`.

### Phase 3 — Bottom panel skeleton
**New folder**: `packages/pocketquant-web/src/components/strategy/backtest-panel/`
- `index.tsx` — collapsible container, drag resize handle, tab state.
- `metrics-tab.tsx`, `positions-tab.tsx`, `equity-tab.tsx` (stubs).
- Persist `{height, activeTab}` ở `localStorage` (key `backtest-panel.layout`).
- Mount khi `selectedSubId && backtestDoc?.status === 'completed'`.
- Integrate vào `routes/index.tsx` dưới `TradingChart`.

### Phase 4 — Metrics tab
- Grid cards: Total Return, CAGR, Sharpe, Sortino, Max DD, Win Rate, Profit Factor, Total Trades, Winning/Losing, Avg Win/Loss, Avg Duration, Total Commission.
- Color theming theo sign (xanh/đỏ). Tooltip mô tả ngắn từng metric.

### Phase 5 — Positions tab
- Table columns: `#`, `Entry Time`, `Direction (LONG/SHORT badge)`, `Entry`, `Exit`, `Qty`, `Duration`, `PnL`, `Fee`, `Status (Open/Closed)`.
- Header click → sort. Filter chip row: All / Wins / Losses / Open. Date range optional.
- Click row → `chart.timeScale().setVisibleRange({ from: entry - pad, to: (exit ?? lastBar) + pad })` + highlight position box (border 2px outline) qua state `highlightedPositionIdx` truyền vào `PositionBoxPrimitive`.
- Footer aggregate: count + sum PnL theo filter.

### Phase 6 — Equity tab
- `chart.addPane()` → paneIndex 1 cho equity. Sub-pane stretch factor 1 (main = 3).
- LineSeries equity (xanh), AreaSeries drawdown (đỏ, scale phải).
- Mount khi tab Equity active; unmount khi switch tab (giảm GPU load).
- Reuse main chart instance; KHÔNG tạo chart riêng.

### Phase 7 — Polish
- Empty states: "No backtest run", "No positions", "Status: failed".
- Loading spinner mỗi tab khi `isFetching`.
- Position box hover effect khi hover row table (event bus đơn giản qua chart ref + state).

## File Map

### Backend (modify)
- `packages/pocketquant-core/src/pocketquant/core/infrastructure/brokers/models.py` — add `side`
- `packages/pocketquant-core/src/pocketquant/core/infrastructure/brokers/paper_broker.py` — emit side
- `packages/pocketquant-trading/.../brokers/okx/okx_broker.py` — emit side
- `packages/pocketquant-backtest/.../engine/result_collector.py` — FIFO lot tracking, refactor `_build_positions`
- `packages/pocketquant-backtest/.../domain/value_objects.py` — add `direction` to PositionRecord

### Backend (new)
- `packages/pocketquant-backtest/tests/test_result_collector_fifo.py` — comprehensive scenarios

### Frontend (modify)
- `packages/pocketquant-web/src/api/strategy-api.ts` — extend `SubscriptionBacktest` type
- `packages/pocketquant-web/src/api/backtest-api.ts` — extend `BacktestPosition` with `direction`
- `packages/pocketquant-web/src/components/chart/position-box-primitive.ts` — support highlight + direction colors
- `packages/pocketquant-web/src/components/chart/trading-chart.tsx` — equity pane mount
- `packages/pocketquant-web/src/routes/index.tsx` — wire BacktestPanel

### Frontend (new)
- `packages/pocketquant-web/src/components/strategy/backtest-panel/index.tsx`
- `packages/pocketquant-web/src/components/strategy/backtest-panel/metrics-tab.tsx`
- `packages/pocketquant-web/src/components/strategy/backtest-panel/positions-tab.tsx`
- `packages/pocketquant-web/src/components/strategy/backtest-panel/equity-tab.tsx`
- `packages/pocketquant-web/src/components/strategy/backtest-panel/use-position-highlight.ts`

## Risks

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Adding `side` to `OrderResult` breaks live broker (OKX) | Medium | Verify OKX broker fill emission có sẵn side; add optional default `LONG` cho rollout phase |
| FIFO refactor change PnL của backtest cũ trong DB | Medium | Migration không cần (recompute on next run); flag old runs `schema_version` |
| Pane API resize làm chart flicker | Low | `setStretchFactor` chỉ set 1 lần lúc mount |
| Position table render 1000+ rows lag | Low | Virtual scroll nếu > 200 rows (TanStack Virtual) |

## Success Criteria

- [ ] User chọn 1 subscription → bottom panel xuất hiện với 3 tabs.
- [ ] Metrics tab hiển thị đủ 12+ metrics.
- [ ] Positions tab list đủ positions, sort/filter hoạt động, click row → chart zoom + highlight box.
- [ ] Equity tab hiển thị equity + drawdown sync timeScale với main chart.
- [ ] Backend: tests cover long-only + short-only + scale-in/out + partial fills + 2 hướng flip đều pass.
- [ ] `OrderResult.side` available, live broker (OKX) không break.
- [ ] Position direction (LONG/SHORT) hiển thị đúng trên table + chart box color.

## Dependencies

- Lightweight-charts ≥5.0.8 (verify `package.json`).
- Backend trên branch `develop`, FE cùng repo.

## Out of Scope

- Run history list / multiple runs / compare 2 runs.
- Cross-strategy overlay.
- Trigger new backtest từ panel (đã có button "Run all" ở sub panel).
- Multi-symbol position aggregation.

## Unresolved Questions

1. `OrderResult.side` mặc định gì khi rollout (backward compat với fills cũ trong DB)? — default `LONG`?
2. Position table có cần export CSV không? (KISS: skip, add nếu user request).
3. Khi user xem chart symbol KHÁC với symbol của selected sub — hide panel hay show với warning? (recommend: hide panel + tooltip "Switch to {sub.symbol} to view backtest").
