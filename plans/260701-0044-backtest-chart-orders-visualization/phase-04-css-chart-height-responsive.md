# Phase 04 — CSS: chart wrapper height + responsive mobile

## Context links
- Parent: [plan.md](plan.md)
- Depends on: [phase-03](phase-03-trades-tab-layout-and-wiring.md)
- File CSS duy nhất: `web/src/index.css` (backtest classes ~line 1525-1562)

## Overview
- Date: 2026-07-01
- Description: Cấp chiều cao cố định cho chart wrapper trong tab Trades (lightweight-charts fill parent qua ResizeObserver, cần parent có height). Responsive: chart thấp hơn trên mobile (tab Trades chật vì có cả chart + bảng).
- Priority: P3
- Implementation status: completed
- Review status: completed (controller self-review — reviewer subagent stalled)

## Key Insights
- `web/src/index.css` là file CSS duy nhất; backtest layout đã có `.backtest-layout`, `.backtest-detail-pane`, `.backtest-mobile`, media query mobile ~line 1539-1545.
- `TradingChart` root là `div{width:100%,height:100%}` → wrapper PHẢI có height cụ thể (px hoặc flex-basis), không để `auto`.
- Detail pane scroll dọc (padding 16, flex column) → chart height cố định + bảng cuộn riêng trong `.positions-tab__table-wrap` (đã có).

## Requirements
1. `.backtest-trades-chart` (class wrapper từ Phase 03): height cố định desktop (~ 380–440px), `min-height:0`, `width:100%`, position relative.
2. Mobile (media query đã tồn tại): height nhỏ hơn (~ 260–300px).
3. Không phá `.backtest-layout` / `.backtest-detail-pane` hiện có.

## Architecture
```
.backtest-detail-pane (scroll dọc)
 └─ tab trades
     ├─ .backtest-trades-chart { height: 420px }   ← mới
     └─ PositionsTab (bảng cuộn trong .positions-tab__table-wrap)

@media mobile: .backtest-trades-chart { height: 280px }
```

## Related code files
- `web/src/index.css` (sửa — thêm `.backtest-trades-chart` + rule trong media query mobile)
- `web/src/components/backtest/backtest-result-view.tsx` (đọc — class name khớp Phase 03)

## Implementation Steps
1. Thêm rule `.backtest-trades-chart { height: 420px; min-height: 0; width: 100%; position: relative; }` gần cụm backtest (~sau line 1562).
2. Trong media query mobile có sẵn (~line 1539): thêm `.backtest-trades-chart { height: 280px; }`.
3. Verify chart không bị 0px collapse + bảng vẫn cuộn độc lập.

## Todo list
- [ ] `.backtest-trades-chart` desktop height
- [ ] Mobile override trong media query
- [ ] Verify không collapse + bảng cuộn riêng

## Success Criteria
- Desktop: chart cao ~420px, render đầy đủ nến, không méo.
- Mobile (tab Trades): chart thấp hơn, bảng vẫn dùng được.
- Không regression `.backtest-layout`/`.backtest-detail-pane`.

## Risk Assessment
- **Thấp**: thuần CSS. Rủi ro duy nhất là chọn height lệch thẩm mỹ → tinh chỉnh khi xem.

## Security Considerations
Không.

## Next steps
Toàn plan xong → manual verify đủ 5 acceptance criteria (đặc biệt #4 run cũ, #5 live chart không regression) → `/ck:journal`.
