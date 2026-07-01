# Phase 03 — Layout tab Trades + wiring highlight/hover 2 chiều

## Context links
- Parent: [plan.md](plan.md)
- Depends on: [phase-01](phase-01-data-and-anchor-ohlcv.md), [phase-02](phase-02-chart-box-selection-and-autoscroll.md)
- Docs: `docs/code-standards.md`

## Overview
- Date: 2026-07-01
- Description: Trong `BacktestResultView` tab `trades`, mount `TradingChart` phía trên `PositionsTab`. Thêm state `highlightedIndex` + `hoveredIndex`, nối 2 chiều: click/hover dòng bảng ↔ box + auto-scroll trên chart.
- Priority: P2
- Implementation status: completed
- Review status: completed (controller self-review — reviewer subagent stalled)

## Key Insights
- `PositionsTab` ĐÃ có props `onPositionClick(index, position)`, `onPositionHover(index|null, position|null)`, `highlightedIndex` — hiện gọi với `highlightedIndex={null}`, không truyền callbacks. Chỉ cần nối.
- `BacktestResultView` nhận `run: BacktestRunResult` + `runId`. Sau Phase 01, `run.symbol`/`run.interval`/`run.end_date` đã có.
- `TradingChart` cần `indicators` prop (bắt buộc) → backtest không cần indicator → truyền object rỗng/default `{}` (kiểm tra `IndicatorConfig` shape, dùng giá trị mặc định tắt hết).
- Chart chỉ render khi `run.symbol` + `run.interval` có giá trị (guard tránh `TradingChart` với symbol rỗng → hook `enabled: !!symbol`).

## Requirements
1. Tab `trades`: `TradingChart` (wrapper chiều cao cố định) ở trên, các block hiện tại (streaks, PnL/Duration histogram, `PositionsTab`) ở dưới.
2. State ở `BacktestResultView`: `highlightedIndex: number|null`, `hoveredIndex: number|null`.
3. `PositionsTab`: truyền `highlightedIndex`, `onPositionClick={(i)=>setHighlightedIndex(i)}`, `onPositionHover={(i)=>setHoveredIndex(i)}`.
4. `TradingChart`: `symbol={run.symbol}`, `interval={run.interval}`, `anchorEndDate={run.end_date}`, `positions={run.positions}`, `highlightedPositionIndex={highlightedIndex}`, `hoveredPositionIndex={hoveredIndex}`, `indicators={defaultIndicators}`.
5. Reset highlight/hover khi đổi run (key hoặc effect) — tránh state cũ bám sang run mới.

## Architecture
```
BacktestResultView (state: highlightedIndex, hoveredIndex)
 ├─ tab 'trades':
 │   ├─ <TradingChart symbol interval anchorEndDate positions
 │   │       highlightedPositionIndex={highlightedIndex}
 │   │       hoveredPositionIndex={hoveredIndex} />   (wrapper height cố định)
 │   └─ <PositionsTab highlightedIndex
 │           onPositionClick={setHighlightedIndex}
 │           onPositionHover={setHoveredIndex} />
```
2 chiều: bảng → state → chart (box + scroll). (Click trên chart → bảng: ngoài scope bản này.)

## Related code files
- `web/src/components/backtest/backtest-result-view.tsx` (sửa — mount chart, state, wiring)
- `web/src/components/chart/trading-chart.tsx` (đọc — props từ Phase 01/02)
- `web/src/components/strategy/backtest-panel/positions-tab.tsx` (đọc — callbacks có sẵn)
- `web/src/types/market-data.ts` (đọc — `IndicatorConfig` default shape)

## Implementation Steps
1. Trong `BacktestResultView`: thêm `const [highlightedIndex, setHighlightedIndex] = useState<number|null>(null)` + `hoveredIndex` tương tự.
2. Xác định `defaultIndicators: IndicatorConfig` (đọc type — dựng object tắt hết, hoặc tái dùng default đã có ở `routes/index.tsx` nếu export sẵn; nếu không, khai báo local const).
3. Tab `trades`: bọc chart trong `<div className="backtest-trades-chart">` (height set ở Phase 04). Render `TradingChart` chỉ khi `run.symbol && run.interval`; else hiện 1 dòng "Symbol/interval không khả dụng cho run này".
4. Thay `<PositionsTab backtest={run} highlightedIndex={null} />` → truyền `highlightedIndex`, `onPositionClick`, `onPositionHover`.
5. Reset state khi `runId` đổi: thêm effect `useEffect(() => { setHighlightedIndex(null); setHoveredIndex(null) }, [runId])` (hoặc adjust-during-render pattern như `backtest-workbench.tsx` dùng).
6. Kiểm tra import path `TradingChart`.

## Todo list
- [ ] State highlightedIndex + hoveredIndex
- [ ] defaultIndicators cho backtest chart
- [ ] Mount TradingChart trong tab trades (guard symbol/interval)
- [ ] Nối callbacks + highlightedIndex vào PositionsTab
- [ ] Reset state khi đổi run

## Success Criteria
- Tab Trades: chart trên, bảng dưới, cùng hiển thị.
- Click dòng → box + viền vàng + chart cuộn tới lệnh.
- Hover dòng → box viền nét đứt (không cuộn).
- Đổi run khác → highlight/hover reset, chart load symbol/run mới.
- Run thiếu symbol → fallback message, không crash.

## Risk Assessment
- **TB**: chart trong flex column không có chiều cao → collapse 0px (lightweight-charts cần parent có height). Mitigation: Phase 04 set height; tạm thời inline height để verify.
- **Thấp**: `indicators` default sai shape → TS error. Mitigation: đọc type trước khi dựng.

## Security Considerations
Không.

## Next steps
→ Phase 04: CSS chính thức cho chart wrapper + responsive mobile.
