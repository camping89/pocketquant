# Code review — backtest chart orders visualization (wiring)

> **Ghi chú quy trình:** `code-reviewer` subagent stall mid-stream 2 lần (API error `Response stalled mid-stream`, hạ tầng — không phải prompt). Theo orchestration rule "không retry prompt lỗi lặp", controller tự review với full context (đã đọc mọi file changed + verify build/test/lint + trace blast-radius). Report này là kết quả review đó.

## Phạm vi
7 file changed (bỏ MEMORY.md của reviewer). Feature = **wiring** `TradingChart` vào backtest tab Trades.

## Verify tự động
- `npm run build` (tsc -b + vite) → PASS.
- `npm test` (vitest) → 40/40 PASS.
- `eslint` trên file changed → sạch. 3 warning ở `trading-chart.tsx` (line 102/194/243) đã confirm PRE-EXISTING trên `git HEAD` (effect `[data]` cũ + cleanup ref) — không do thay đổi này.

## Findings

### BLOCKER
- Không có.

### SHOULD-FIX
- Không có.

### NICE-TO-HAVE
- `NO_INDICATORS` object rỗng lặp cấu trúc `DEFAULT_INDICATORS` ở `routes/index.tsx`. YAGNI: không đáng trừu tượng hóa cho 2 nơi. Bỏ qua.
- Auto-scroll `barDur` suy từ 2 nến đầu — data có gap ở đầu window → pad hơi lệch. Chỉ ảnh hưởng thẩm mỹ ngữ cảnh, lightweight-charts tự clamp. Chấp nhận (đã nêu trong plan risk).

## Verify từng acceptance criterion

| # | Tiêu chí | Kết luận |
|---|---|---|
| 1 | Chart nến đúng window + markers BUY/SELL mọi lệnh | ✓ `anchorEndDate=end_date` → base query `end_date`; markers vẫn build từ TOÀN BỘ positions (memo `[positions]` không đổi) |
| 2 | Click dòng → box + viền vàng + cuộn | ✓ `onPositionClick→setHighlightedIndex`; posData filter chứa highlight index; effect auto-scroll deps `[highlightedPositionIndex, data]` |
| 3 | Hover → box nét đứt, KHÔNG cuộn | ✓ `onPositionHover→setHoveredIndex`; auto-scroll effect chỉ đọc `highlightedPositionIndex`, hover không nằm trong deps |
| 4 | Run cũ thiếu symbol → fallback, không crash | ✓ guard `run.symbol && run.interval` → empty-state message; `config_snapshot?.symbol` optional chain |
| 5 | Live chart + strategy-chart không regression | ✓ xem "Regression analysis" |

## Regression analysis (rủi ro cao nhất)

**Live chart `routes/index.tsx:109`** — `<TradingChart symbol interval indicators />`, KHÔNG có `anchorEndDate`:
- `anchorEndDate = undefined` → `useOhlcvHistory(s, i, undefined)` → query key 3-phần tử `['ohlcv', s, i]` (nhánh `anchorEndDate ? ... : ohlcvQueryKey(...)` chọn else) → y hệt trước.
- `useRealtimeBar(s, i, cRef, vRef, undefined == null → true)` → `enabled=true` → early-return KHÔNG kích hoạt → realtime nguyên vẹn.
- reset-accumulator deps thêm `anchorEndDate` (undefined, hằng) → không thêm lần reset nào cho live.

**`strategy-chart.tsx`** — dùng `useOhlcvHistory(symbol, interval)` 2 args; param thứ 3 optional → không đổi. Không import `TradingChart`/`useRealtimeBar`. Ngoài blast-radius.

**Query-key collision (rủi ro ẩn #2)** — anchored key 4-phần tử; `use-realtime-bar.ts:49` invalidate hardcode key 3-phần tử `['ohlcv', symbol, interval]` → KHÔNG match anchored key → anchored chart không bị invalidate nhầm bởi live SSE cùng symbol/interval; cache tách namespace. ✓

**Public contract** — cả 2 param mới (`anchorEndDate`, `enabled`) đều optional/có default, thêm ở cuối signature → call site cũ không gãy (đã verify build).

## Wiring index (điểm dễ sai nhất) — PASS
`IndexedPosition.index` = index gốc trong `backtest.positions` (comment source), bảo toàn qua filter+sort. `PositionsTable` click/hover trả `item.index` (gốc). `TradingChart` posData filter theo index gốc + `PositionBoxPrimitive` match `pos.index === highlightIndex`. Khớp end-to-end kể cả khi bảng đã sort/filter.

## Cleanup / memory leak — PASS
Anchored → `enabled=false` → `useRealtimeBar` early-return trước `new EventSource` → không mở SSE thừa. Effect deps có `enabled` → flip an toàn, cleanup cũ chạy đúng.

---
Status: DONE
Summary: Wiring đúng, build+test+lint sạch, không regression live chart/strategy-chart, query-key collision + realtime gate xử lý đúng. Không có BLOCKER/SHOULD-FIX.
Concerns: code-reviewer subagent stall 2 lần (hạ tầng) → controller tự review thay thế.
