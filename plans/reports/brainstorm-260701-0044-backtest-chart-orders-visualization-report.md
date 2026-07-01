# Brainstorm — Backtest UI: chart nến + trực quan hóa entry/exit mỗi order

## Metadata
- Date: 2026-07-01
- Topic: Thêm chart nến vào backtest detail UI để thấy entry/exit + lời/lỗ từng order
- Modes: (none — markdown only)
- Status: Design approved, ready for `/ck:plan`

## Problem statement

Backtest detail UI hiện chỉ hiện metrics, equity/drawdown line chart, histograms và bảng trades. **Không có chart nến**, nên user không hình dung được mỗi lệnh vào/ra ở đâu trên giá, và lời/lỗ bao nhiêu point. Mục tiêu: nhìn chart thấy ngay order được đặt thế nào + thắng/thua.

## Phát hiện cốt lõi (scout)

**~90% đã được code sẵn, chỉ chưa wiring vào backtest UI.**

| Thành phần | Trạng thái | Vị trí |
|---|---|---|
| `TradingChart` — candlestick + volume + indicators | Có | `web/src/components/chart/trading-chart.tsx` |
| BUY/SELL markers từ `positions` | Có (dedup theo timestamp) | trong `TradingChart` |
| `PositionBoxPrimitive` — box Entry/SL/TP/Exit + label `[DIR] Entry/Exit/Qty/PnL/Fee`, tô màu lời/lỗ | Có | `web/src/components/chart/position-box-primitive.ts` |
| Highlight/hover 1 order (viền vàng/nét đứt) | Có (`highlightedPositionIndex`, `hoveredPositionIndex`) | trong `TradingChart` |
| `PositionsTab` callbacks `onPositionClick`/`onPositionHover`/`highlightedIndex` | Có (đang bỏ trống) | `web/src/components/strategy/backtest-panel/positions-tab.tsx` |
| Backend trả `positions[]` đầy đủ + `config_snapshot.{symbol,interval,start_date,end_date}` | Có | `src/pocketquant/.../result_collector.py`, route `GET /api/v1/backtest/{runId}` |

**Vấn đề thật:** `BacktestResultView` không render `TradingChart`, và gọi `PositionsTab` với `highlightedIndex={null}` (callbacks không nối). Đây là bài toán **wiring**, không phải xây mới.

## Rủi ro kỹ thuật then chốt

`useOhlcvHistory` luôn load nến **mới nhất** (`fetchOHLCVBars` không kèm `end_date`) rồi paginate lùi. Backtest thường chạy trên **khoảng thời gian cũ** → base load có thể không chứa vùng backtest → `timeToCoordinate` trả `null` → box/markers không vẽ được + auto-scroll rơi vào vùng trống.

**Đã xác minh giảm nhẹ:** `fetchOHLCVBars` hỗ trợ param `end_date`; `config_snapshot.end_date` có sẵn. → anchor base load theo `end_date` của run.

## Approaches đã cân nhắc

| # | Approach | Pros | Cons | Verdict |
|---|---|---|---|---|
| A | Wiring `TradingChart` đã có + anchor end_date | Reuse tối đa, effort thấp, đồng nhất với strategy/live chart | Cần thêm path optional anchor + auto-scroll | **Chọn** |
| B | Xây chart backtest riêng từ `useChart` | Toàn quyền tùy biến | Trùng lặp logic markers/box/highlight đã có (vi phạm DRY) | Loại |
| C | Chỉ thêm box vào equity chart | Không cần OHLCV | Không phải candlestick → không đạt yêu cầu "thấy order trên giá" | Loại |

## Final design (approved)

### Quyết định UX (chốt với user)
- **Layout:** chart trên + bảng trades dưới, trong **tab Trades**.
- **Tương tác:** click dòng → highlight + **auto-scroll/zoom** tới lệnh; hover → viền nét đứt.
- **Nhiều lệnh:** markers BUY/SELL vẽ **tất cả**; box chi tiết **chỉ theo lựa chọn** (click/hover).
- **Anchor nến:** base load theo **`end_date`** của run.
- **Box mặc định:** **chỉ markers**, không box cho tới khi click/hover.

### Thay đổi cần làm

1. **Phơi `symbol`/`interval` lên `BacktestRunResult`** — `web/src/api/backtest-api.ts`: `fetchBacktestRun` đọc `doc.config_snapshot.symbol` (composite `CODE:EXCHANGE`) + `.interval` + `.end_date`, gán lên kết quả. Không đụng backend.

2. **Anchor OHLCV theo backtest window** — thêm optional `anchorEndDate?: string` cho `useOhlcvHistory`: khi có → base query fetch với `end_date` = run's `end_date`; khi undefined → giữ nguyên live behavior (không phá chart trang chính). `TradingChart` nhận thêm optional prop `anchorEndDate`.

3. **Layout tab Trades** — `BacktestResultView`: thêm `TradingChart` (wrapper chiều cao cố định, `minHeight: 0`) phía trên `PositionsTab`. State `highlightedIndex` + `hoveredIndex` ở `BacktestResultView`, nối 2 chiều xuống `PositionsTab` (callbacks) và `TradingChart` (`highlightedPositionIndex`/`hoveredPositionIndex`).

4. **Auto-scroll tới lệnh khi click** — giữ `IChartApi` ref qua `onChartReady` (đã có). Khi `highlightedIndex` đổi: tính range `[entry_time, exit_time]` của position (mở rộng 2 bên vài chục nến) → `chart.timeScale().setVisibleRange(...)`. An toàn vì đã anchor theo end_date.

5. **Box theo lựa chọn** — trong `TradingChart`, build `posData` cho `PositionBoxPrimitive` chỉ gồm {lệnh highlight, lệnh hover}; mặc định rỗng (chỉ markers). Markers vẫn build từ toàn bộ `positions`.

### Scope OUT
- Không sửa backend.
- Không đụng chart trang chính (live `routes/index.tsx`) / `strategy-chart.tsx`.
- Không replay/animation theo thời gian (chỉ tĩnh).
- Equity/drawdown/histogram giữ nguyên.

## Acceptance criteria
1. Run finished → tab Trades → chart nến đúng khoảng backtest + mũi tên BUY/SELL mọi lệnh.
2. Click dòng bảng → chart cuộn tới lệnh, box Entry/Exit/SL/TP/PnL/Qty + viền vàng.
3. Hover dòng → box viền nét đứt.
4. Run cũ (vài năm trước) vẫn thấy đúng nến + box (không trống).
5. Chart trang chính (live) không đổi hành vi.

## Risks & mitigation

| Risk | Mức | Mitigation |
|---|---|---|
| OHLCV không anchor → box ngoài viewport | Cao | Mục 2 (anchor `end_date`) — bắt buộc, làm trước |
| Chart cần chiều cao cố định trong flex column | TB | Wrapper `height` cố định + `minHeight: 0` |
| Mobile tab Trades chật (chart + bảng) | Thấp | Chart chiều cao nhỏ hơn trên mobile qua CSS |
| `setVisibleRange` khi range nằm rìa dữ liệu | Thấp | Clamp range trong [oldest, newest] bar đã load |

## Success metrics
- User mở bất kỳ run nào (cũ/mới) đều thấy chart + lệnh không thao tác thủ công.
- Không regression chart live/strategy.
- Không thêm round-trip backend mới (reuse OHLCV + trades endpoints có sẵn).

## Files touchpoints (dự kiến)
- `web/src/api/backtest-api.ts` (sửa — phơi symbol/interval/end_date)
- `web/src/hooks/use-ohlcv-history.ts` (sửa — optional anchorEndDate)
- `web/src/components/chart/trading-chart.tsx` (sửa — anchorEndDate prop, box theo lựa chọn, auto-scroll qua onChartReady)
- `web/src/components/backtest/backtest-result-view.tsx` (sửa — mount chart + state highlight/hover + wiring)
- `web/src/index.css` hoặc CSS liên quan (thêm — chiều cao chart wrapper, responsive mobile)

## Unresolved questions
- Auto-scroll padding: mở rộng bao nhiêu nến mỗi bên quanh lệnh? (đề xuất ~20–30, tinh chỉnh khi implement)
- Box-by-viewport (vẽ box cho lệnh trong khung nhìn) đã loại khỏi bản đầu (chọn "chỉ markers") — có muốn để lại như enhancement sau không?
