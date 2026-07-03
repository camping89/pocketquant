# Phase 01 — Data + anchor OHLCV theo backtest window

## Context links
- Parent: [plan.md](plan.md)
- Brainstorm: `plans/reports/brainstorm-260701-0044-backtest-chart-orders-visualization-report.md`
- Docs: `docs/code-standards.md` (async-suspension, comment policy), `docs/system-architecture.md` (real-time streaming)
- Depends on: — (phase đầu tiên)

## Overview
- Date: 2026-07-01
- Description: Phơi `symbol`/`interval`/`end_date` lên `BacktestRunResult`; cho `useOhlcvHistory` + `TradingChart` nhận optional `anchorEndDate` để load nến đúng khoảng backtest. Xử lý 2 rủi ro ẩn: query-key collision + realtime push nến lạc.
- Priority: P1 (rủi ro cao nhất, chặn mọi phase sau)
- Implementation status: completed
- Review status: completed (controller self-review — reviewer subagent stalled)

## Key Insights
- `fetchOHLCVBars(symbol, interval, limit, endDate?)` **đã** hỗ trợ `endDate` → backend không cần đổi.
- `config_snapshot` (đã verify) chứa `symbol` (composite `CODE:EXCHANGE`), `interval`, `end_date` (ISO string).
- **Query key collision**: `ohlcvQueryKey = ['ohlcv', symbol, interval]` — không gồm endDate. Anchored backtest chart + live chart cùng symbol/interval sẽ ghi đè cache nhau. PHẢI tách key khi anchored.
- **Realtime gate**: `TradingChart` line ~202 gọi `useRealtimeBar(symbol, interval, candleRef, volumeRef)` vô điều kiện → SSE push nến hiện tại + invalidate query. Chart anchor quá khứ phải DISABLE việc này.
- Backward compat tuyệt đối: khi `anchorEndDate` undefined → mọi hành vi giữ y nguyên (live chart + strategy-chart không đổi).

## Requirements
1. `BacktestRunResult` có thêm `symbol?: string`, `interval?: string`, `end_date?: string`; `fetchBacktestRun` map từ `config_snapshot`.
2. `useOhlcvHistory(symbol, interval, anchorEndDate?)`:
   - Khi `anchorEndDate` set: base query fetch với `end_date = anchorEndDate`; query key gồm `anchorEndDate`; KHÔNG dùng realtime invalidation path.
   - Khi undefined: hành vi hiện tại nguyên vẹn.
3. `TradingChart` nhận optional `anchorEndDate?: string`, truyền xuống hook; khi set → KHÔNG chạy `useRealtimeBar` (hoặc `useRealtimeBar` nhận `enabled=false`).

## Architecture
```
BacktestRunResult.{symbol,interval,end_date}  ← config_snapshot (backtest-api.ts)
        │
        ▼
TradingChart(anchorEndDate=end_date)
        │  ├─ useOhlcvHistory(symbol, interval, anchorEndDate)
        │  │     └─ base query: end_date=anchorEndDate, key=['ohlcv', symbol, interval, anchorEndDate]
        │  └─ useRealtimeBar(... enabled = anchorEndDate == null)
```
Query key: live = `['ohlcv', symbol, interval]` (giữ nguyên, dùng chung với `use-realtime-bar` invalidation); anchored = `['ohlcv', symbol, interval, anchorEndDate]`. Tách namespace → không đụng realtime invalidation (vốn hardcode key 3-phần tử trong `use-realtime-bar.ts`).

## Related code files
- `web/src/api/backtest-api.ts` (sửa — `BacktestRunResult` + `fetchBacktestRun`)
- `web/src/hooks/use-ohlcv-history.ts` (sửa — param `anchorEndDate`, query key, base queryFn)
- `web/src/hooks/use-realtime-bar.ts` (sửa — thêm `enabled` param, early-return khi false)
- `web/src/components/chart/trading-chart.tsx` (sửa — prop `anchorEndDate`, gate realtime, truyền xuống hook)
- `web/src/hooks/use-ohlcv.ts` (đọc tham chiếu — `ohlcvQueryKey`)

## Implementation Steps
1. `backtest-api.ts`:
   - Thêm `symbol?`, `interval?`, `end_date?` vào interface `BacktestRunResult`.
   - Trong `fetchBacktestRun`, map `symbol: (doc.config_snapshot?.symbol as string)?.toUpperCase()`, `interval`, `end_date` từ `config_snapshot`. Giữ nguyên phần ghép `positions`.
2. `use-ohlcv-history.ts`:
   - Signature → `useOhlcvHistory(symbol, interval, anchorEndDate?)`.
   - `queryKey`: `anchorEndDate ? [...ohlcvQueryKey(symbol, interval), anchorEndDate] : ohlcvQueryKey(symbol, interval)`.
   - `queryFn`: `() => fetchOHLCVBars(symbol, interval, PAGE_SIZE, anchorEndDate)`.
   - Accumulator reset effect: thêm `anchorEndDate` vào deps `[symbol, interval]` → `[symbol, interval, anchorEndDate]`.
   - `loadOlder` giữ nguyên (paginate lùi từ earliest cursor vẫn đúng cho anchored window).
3. `use-realtime-bar.ts`:
   - Thêm param `enabled = true`; ngay đầu effect: `if (!enabled) return` (không mở EventSource, không timer). Cleanup an toàn.
4. `trading-chart.tsx`:
   - Thêm `anchorEndDate?: string` vào `TradingChartProps`.
   - `useOhlcvHistory(symbol, interval, anchorEndDate)`.
   - `useRealtimeBar(symbol, interval, candleRef, volumeRef, anchorEndDate == null)`.
5. Comment: chỉ thêm 1 dòng WHY tại điểm gate realtime + điểm tách query key (giải thích collision), theo comment policy (WHY not WHAT).

## Todo list
- [ ] `BacktestRunResult` + `fetchBacktestRun` map config_snapshot
- [ ] `useOhlcvHistory` nhận `anchorEndDate` (key + queryFn + reset deps)
- [ ] `useRealtimeBar` nhận `enabled`, early-return
- [ ] `TradingChart` prop `anchorEndDate` + gate realtime + truyền hook
- [ ] Verify live chart + strategy-chart không regression

## Success Criteria
- `TradingChart` với `anchorEndDate` set: base load lấy nến kết thúc tại `end_date`; KHÔNG mở SSE; query cache tách khỏi live.
- `TradingChart` không `anchorEndDate`: hành vi y hệt hiện tại (live realtime hoạt động, scroll-left pagination OK).
- `fetchBacktestRun` trả `symbol`/`interval`/`end_date` đúng từ config_snapshot.
- `tsc`/build pass.

## Risk Assessment
- **Cao**: chạm `useOhlcvHistory` + `useRealtimeBar` + `TradingChart` — đều dùng bởi live chart `routes/index.tsx`. Mitigation: mọi nhánh mới gated sau `anchorEndDate != null`; verify live chart thủ công ngay sau phase này.
- **TB**: `config_snapshot.symbol` thiếu/không composite ở doc cũ → chart không load. Mitigation: `entities.py` đã có fallback denormalize; nếu undefined → chart hiện empty state (không crash).
- **Thấp**: query key đổi shape (4 phần tử) cho anchored → react-query xử lý tuple key bình thường.

## Security Considerations
Không có dữ liệu nhạy cảm mới. Chỉ đọc field đã public qua API hiện hữu.

## Next steps
→ Phase 02: box theo lựa chọn + auto-scroll (sau khi chart anchored render đúng nến + markers).
