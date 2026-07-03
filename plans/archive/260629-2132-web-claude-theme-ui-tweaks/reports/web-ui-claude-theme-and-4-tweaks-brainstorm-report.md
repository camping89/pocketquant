# Brainstorm — Web UI: Claude theme + 4 tweaks

Mode: brainstorm (no flags). Scope: `web/` SPA + 1 backend contract change (backtest date→datetime).

## Problem statement

5 task UI từ `TODO.md`:

1. Đổi sang **Claude AI theme** cho cả dark + light.
2. Charts page: **bỏ dot line** cho indicators (vd EMA).
3. Strategies page: hiển thị **cùng danh sách indicator** như charts page — tái dùng code, không trùng lặp.
4. Backtest page: default start/end = **1 năm trước → nay**, cho phép chọn **tới phút**.
5. Góc trên phải, cạnh dropdown timezone: **đồng hồ realtime**.

## Codebase context (scout)

- Theme hard-coded: `web/src/index.css` `:root` (dark `#1a1a2e`/`#16213e`, accent teal `#26a69a`). Màu chart lặp ở `use-chart.ts` (`DEFAULT_OPTIONS`) + candle colors inline trong `trading-chart.tsx` và `strategy-chart.tsx`. Chưa có theme toggle / light mode.
- Indicators: `controls/indicator-toggles.tsx` (UI) + `hooks/use-indicators.ts` (compute) + `components/chart/indicator-series.ts` (`addIndicatorSeries`/`removeIndicatorSeries`) — đã là module dùng chung.
- `StrategyChart` (`components/strategies/strategy-chart.tsx`): **cố ý** không có indicator controls/series (tách khỏi `TradingChart` để né `PositionBoxPrimitive`).
- Backtest dates: FE `backtest-form.tsx` dùng `<input type="date">`. BE dùng `date` (chỉ ngày) ở `RunBacktestCommand`, `BacktestConfig`, `_config_from_dict` (`date.fromisoformat`), `BacktestAppService._load_bars` (`datetime.combine`), `metrics_builder`.
- Header: `TimezoneSwitcher` ở `__root.tsx` app-nav góc phải. `lib/datetime.ts` đã có `tzSuffix(mode)`, `formatHmsTime`, `useTimezone()` context.

## Quyết định (đã chốt với user)

| # | Quyết định |
|---|-----------|
| Theme default | **Dark** mặc định + toggle cạnh `TimezoneSwitcher`, persist `localStorage` |
| Candle màu | **Hòa palette Claude** nhưng giữ 2 hue đối lập (up teal/sage, down clay/terracotta) — đọc được long/short |
| Task 2 dot line | **Price line ngang nét đứt** (giá trị cuối series) → `priceLineVisible:false` |
| Task 4 backend | **Sửa cả backend**: `date`→`datetime` ở backtest API |
| Task 3 render | Toggles trên chart + render **đầy đủ** (gồm RSI/MACD panes) |
| Task 3 persist | **localStorage** (key riêng cho strategies) |

## Solution

### 1. Claude theme (dark + light)

- Pattern theo `TimezoneContext` đã có: `lib/theme/theme-context.tsx` + `use-theme.ts`. `mode: 'dark'|'light'`, default dark, persist `localStorage`, set `data-theme` trên `<html>`.
- `index.css`: tách `:root` hiện tại → `[data-theme="dark"]` + `[data-theme="light"]` token blocks. **1 nguồn sự thật = CSS variables** cho toàn bộ UI chrome.
  - dark: nền xám than `#1F1E1D`, accent clay `#D97757`.
  - light: nền kem `#F5F4EE`, text than, accent clay.
- Chart (lightweight-charts cần giá trị JS): `useChart` + candle series đọc màu qua `getComputedStyle(document.documentElement)` lúc tạo, và `applyOptions` lại khi theme đổi (tái dùng cơ chế `mode` effect đã có cho timezone). Giữ DRY — chart đọc lại chính CSS vars.
- Candle: up = teal/sage dịu, down = clay/terracotta (token hóa thành CSS var `--up-color`/`--down-color` cho mỗi theme).
- Toggle sun/moon đặt cạnh `TimezoneSwitcher` trong `__root.tsx`.

### 2. Bỏ dot line indicator

- `indicator-series.ts`: thêm `priceLineVisible:false` + `lastValueVisible:false` cho mọi LineSeries indicator (EMA/SMA/BB). Đường EMA solid giữ nguyên; chỉ tắt đường ngang nét đứt ở giá trị cuối.

### 3. Indicator list ở strategies (reuse)

- Thêm `IndicatorToggles` (tái dùng nguyên file) lên trên `StrategyChart`.
- `StrategyChart` nhận prop `indicators`, gọi `useIndicators` + `addIndicatorSeries`/`removeIndicatorSeries` (tái dùng đúng module). Render đầy đủ SMA/EMA/RSI/MACD/BB/Engulf.
- Engulf markers (`engulfingMarkers`) merge với trade markers hiện có — theo cùng pattern `trading-chart.tsx`.
- Persist `localStorage` key `strategies.indicators`.
- Ranh giới giữ nguyên: chỉ thêm indicator series, **không** kéo `PositionBoxPrimitive`.

### 4. Backtest datetime tới phút (BE + FE)

- BE: `start_date`/`end_date` `date`→`datetime` ở `RunBacktestCommand`, `BacktestConfig`; `_config_from_dict` dùng `datetime.fromisoformat`; `_load_bars` bỏ `datetime.combine` (dùng thẳng datetime); `metrics_builder` tính `days` từ `.date()`. Verify `backtest_strategy_loader` fallback 365d.
- FE: `<input type="date">`→`type="datetime-local"`; default end = now, start = now − 1 năm (`dayjs`); gửi ISO datetime.

### 5. Live clock

- `components/layout/live-clock.tsx`: `setInterval` 1s, format qua `formatHmsTime` + `tzSuffix` theo `useTimezone().mode` (tự đổi UTC/Local theo dropdown). Đặt trước `TimezoneSwitcher` trong `__root.tsx`. Cleanup interval on unmount.

## Touchpoints

**FE**: `index.css`, `lib/theme/*` (mới), `lib/use-theme.ts` (mới), `components/chart/use-chart.ts`, `components/chart/trading-chart.tsx`, `components/strategies/strategy-chart.tsx`, `components/strategies/strategies-page-layout.tsx`, `components/chart/indicator-series.ts`, `components/controls/indicator-toggles.tsx` (reuse), `components/backtest/backtest-form.tsx`, `components/layout/live-clock.tsx` (mới), `routes/__root.tsx`.

**BE**: `backtest/backtest_command_service.py`, `backtest/models/backtest_config.py`, `backtest/workers/backtest_dispatch.py`, `backtest/engine/backtest_app_service.py`, `backtest/engine/metrics_builder.py`.

## Risks

- **Candle palette**: đổi màu nến rời convention green/red phổ quát → giảm thiểu bằng cách giữ 2 hue đối lập (teal vs clay). Nếu trader phản hồi khó đọc, fallback green/red chuẩn.
- **Theme + chart sync**: lightweight-charts không nhận CSS var trực tiếp → đọc `getComputedStyle`; phải đảm bảo `data-theme` đã set trên `<html>` trước khi chart đọc (thứ tự mount ThemeProvider trước chart).
- **Backtest contract đổi**: `date`→`datetime` là breaking nếu có client/test khác gọi API. Kiểm tra `tests/http`, Bruno collection, scheduled backtest jobs. `datetime-local` không gửi timezone → quy ước UTC (đồng bộ với `lib/datetime.ts` parse naive = UTC).
- **Light theme độ tương phản**: nền kem cần kiểm accessibility cho text-secondary + grid lines (dễ chìm).

## Success criteria

- Toggle theme đổi tức thời cả UI chrome lẫn chart (bg/grid/candle), persist qua reload, default dark.
- EMA/SMA/BB không còn đường ngang nét đứt; đường line giữ nguyên.
- Strategies page có cùng bộ indicator toggles + render giống charts, dùng chung module (không copy logic), persist riêng.
- Backtest form default 1 năm, chọn được phút; backtest chạy đúng theo range tới phút.
- Clock chạy realtime, đổi UTC/Local theo dropdown.

## Unresolved questions

- Light theme: có cần đường viền/độ đậm khác cho candle trên nền kem không, hay dùng chung token với dark? (đề xuất: cùng token, tinh chỉnh nếu chìm)
- Backtest `datetime-local`: quy ước input là UTC hay Local của user? (đề xuất: UTC cho nhất quán với toàn bộ `lib/datetime.ts`; cân nhắc hiển thị suffix UTC cạnh input để rõ ràng)
