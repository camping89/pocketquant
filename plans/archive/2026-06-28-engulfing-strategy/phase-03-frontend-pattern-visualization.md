---
phase: 3
title: "Frontend pattern visualization"
status: completed
priority: P2
dependencies: [1]
---

# Phase 3: Frontend pattern visualization

## Overview

Nút toggle "Engulfing" trên chart vẽ **tất cả** body-engulfing pattern, tô màu strong/weak theo quality filter. TS detector port từ định nghĩa Phase 1, khóa bằng **cùng golden fixture**. Merge markers engulfing với backtest markers — KHÔNG override.

## Requirements

- Functional: thêm `engulfing` vào `IndicatorConfig`; nút toggle trong `indicator-toggles.tsx`.
- Functional: `engulfing.ts` detect trên `CandlestickData[]` → markers; strong (pass filter) đậm, weak nhạt.
- Functional: markers engulfing + backtest markers cùng tồn tại trên 1 series (merge 1 array trước `setMarkers`).
- Non-functional: detection logic khớp Python (test bằng golden fixture chung).
- **Setup tooling:** `web/` HIỆN KHÔNG có test runner (chỉ `dev/build/lint/preview`). Phase này thêm **vitest** để chạy parity test. Đây là test FE ĐẦU TIÊN của project.

## Architecture

**Điểm tích hợp nguy hiểm nhất** — `trading-chart.tsx` hiện gọi `createSeriesMarkers(candleRef, markers)` một lần cho backtest. Gọi lần 2 cho engulfing sẽ tạo plugin instance thứ 2 / override. → Phải **merge** vào một mảng `SeriesMarker<Time>[]` rồi `setMarkers` một lần.

```
backtestMarkers (useMemo từ positions, đã có)  ┐
                                                ├─ merge → sort by time → markersRef.setMarkers(all)
engulfingMarkers (useMemo từ data.candles +     ┘
                  indicators.engulfing toggle)
```

**Màu strong/weak:**
```
bullish strong → arrowUp belowBar đậm (vd #16a34a)
bullish weak   → arrowUp belowBar nhạt (vd #86efac)
bearish strong → arrowDown aboveBar đậm (#dc2626)
bearish weak   → arrowDown aboveBar nhạt (#fca5a5)
"strong" = rejection_wick_pct <= NGƯỠNG_HIỂN_THỊ (mặc định 0.30, hằng FE)
```

**Va chạm marker entry vs pattern cùng timestamp:** backtest BUY/SELL arrow + engulfing arrow có thể trùng bar. Chấp nhận chồng (khác màu/vị trí), hoặc khi có positions thì ưu tiên backtest marker tại bar đó — quyết định lúc implement, ghi rõ.

**Marker cleanup (red-team Finding 11):** effect hiện tại (`trading-chart.tsx:230-245`) deps `[markers]`, cleanup `detach()` khi `markers.length===0`. Khi merge 2 nguồn, KHÔNG giữ cleanup-on-empty (toggle engulfing off + 0 positions → detach → flicker/leak khi re-create). Sửa: một `useMemo` merged deps `[markers, engulfingMarkers]`; effect deps `[merged]`; **cleanup detach CHỈ khi unmount** (không khi length===0); khi merged rỗng → `setMarkers([])` thay vì detach plugin.

**`use-indicators.ts` KHÔNG đụng (red-team Finding 10):** engulfing markers sống ở `trading-chart.tsx`, KHÔNG phải `use-indicators.ts` (nơi này chỉ tính line-series sma/ema/rsi/macd/bb). Đừng thêm branch `config.engulfing` vào `use-indicators.ts` (sẽ thành no-op vô hình). Chỉ cần `IndicatorConfig` có field + toggle + logic ở `trading-chart.tsx`.

**Chia sẻ fixture TS↔Python (red-team Finding 3 — COPY, không cross-root):** import-as-JSON từ bản copy trong `web/`, KHÔNG đọc `node:fs` cross-root tới `tests/`. Lý do: cross-root `node:fs` + path ngoài `web/` làm `tsc -b` (include `src`) và resolution vỡ. Cơ chế: fixture canonical ở `tests/core_test/.../engulfing_golden_fixture.json` (Phase 1); copy 1 bản vào `web/src/lib/indicators/__fixtures__/engulfing_golden_fixture.json`; test `import fixture from './__fixtures__/...json'` (vite hỗ trợ JSON import, không cần `node:fs`). Đồng bộ: 1 dòng trong Phase 5 verify so 2 file `diff` để chống drift (hoặc copy script).

**Vitest setup (test FE đầu tiên — red-team Finding 3+4):**
- Thêm devDep: `vitest`. KHÔNG cần jsdom — test chỉ pure function (không render React).
- `web/vitest.config.ts`: `test.environment='node'`, `test.globals=true` (để `describe/it/expect` không cần import).
- **tsconfig (Finding 3):** thêm `web/tsconfig.test.json` với `types:["vitest/globals"]` + include `**/*.test.ts`; **exclude `**/*.test.ts` khỏi `tsconfig.app.json`** (hiện `include:["src"]`, `types:["vite/client"]` → sẽ fail trên test file). Reference `tsconfig.test.json` từ `tsconfig.json`.
- **eslint (Finding 4):** thêm override block trong `web/eslint.config.js` cho `**/*.test.ts`: `globals` thêm vitest globals (tránh `no-undef`). Hiện config set `globals.browser` cho mọi `**/*.{ts,tsx}` (`eslint.config.js:20`).
- Script `"test":"vitest run"` + `"test:watch":"vitest"` vào `web/package.json`.
- Vì import-as-JSON (không `node:fs`), KHÔNG cần `types:["node"]`.

## Related Code Files

- Modify: `web/src/types/market-data.ts` — `IndicatorConfig` thêm `engulfing: boolean`.
- Modify: `web/src/components/controls/indicator-toggles.tsx` — thêm `{ key: 'engulfing', label: 'Engulf', color: '#16a34a' }`.
- Create: `web/src/lib/indicators/engulfing.ts` — `detectEngulfing(prev, curr)` + `engulfingMarkers(candles, threshold) -> SeriesMarker[]`.
- Modify: `web/src/components/chart/trading-chart.tsx` — useMemo engulfing markers (gated bởi `indicators.engulfing`); merge với backtest `markers`; một `setMarkers`; cleanup-on-unmount (Finding 11).
- Create: `web/src/lib/indicators/engulfing.test.ts` — import fixture copy, assert khớp.
- Create: `web/src/lib/indicators/__fixtures__/engulfing_golden_fixture.json` — copy từ Phase 1 canonical.
- Modify: `web/package.json` — devDep `vitest` + script `test`/`test:watch`.
- Create: `web/vitest.config.ts` — `test.environment='node'`, `globals=true`.
- Create: `web/tsconfig.test.json` — `types:["vitest/globals"]`, include `**/*.test.ts`; referenced từ `tsconfig.json`.
- Modify: `web/tsconfig.app.json` — exclude `**/*.test.ts`.
- Modify: `web/eslint.config.js` — override block cho `**/*.test.ts` (vitest globals).
- KHÔNG đụng: `web/src/hooks/use-indicators.ts` (Finding 10 — engulfing không sống ở đây).

## Implementation Steps

0. Setup vitest (Finding 3+4): `cd web && npm i -D vitest`; `vitest.config.ts` (`environment:'node'`, `globals:true`); `tsconfig.test.json` (`types:["vitest/globals"]`); exclude `**/*.test.ts` khỏi `tsconfig.app.json`; eslint override cho test files; script `"test":"vitest run"`. Smoke 1 test rỗng pass + `npm run build` vẫn xanh trước khi đi tiếp.
1. Copy `engulfing_golden_fixture.json` (Phase 1) → `web/src/lib/indicators/__fixtures__/`.
2. Thêm `engulfing: boolean` vào `IndicatorConfig`; chỉ `DEFAULT_INDICATORS` (`routes/index.tsx:27`) cần `engulfing:false` — grep `IndicatorConfig` xác nhận không còn literal khác. (Config không persist localStorage → không cần migration.)
3. Port `detectEngulfing` sang TS khớp Phase 1 (cùng boundary `<=`, cùng range-0 guard, cùng encoding rejection_wick_pct).
4. `engulfingMarkers(candles, threshold)`: loop i từ 1, detect(candles[i-1], candles[i]); nếu engulf → marker màu strong/weak.
5. Viết `engulfing.test.ts` import fixture copy, assert `is_bullish/is_bearish/rejection_wick_pct` khớp — khóa chống lệch định nghĩa.
6. Trong `trading-chart.tsx`: useMemo merged `[markers, engulfingMarkers]`; sort theo time; effect deps `[merged]`; `setMarkers(merged)`; cleanup detach CHỈ on unmount.
7. Thêm nút toggle vào `indicator-toggles.tsx`.
8. `cd web && npm run lint && npm run build && npm run test` (vitest parity pass).

## Success Criteria

- [ ] Toggle "Engulf" bật/tắt vẽ markers engulfing.
- [ ] Strong đậm, weak nhạt; bullish belowBar arrowUp, bearish aboveBar arrowDown.
- [ ] Backtest markers + engulfing markers cùng hiện, không cái nào biến mất (merge đúng, cleanup-on-unmount).
- [ ] `engulfing.test.ts` pass với fixture copy — kết quả TS khớp Python (vitest, máy enforce).
- [ ] `npm run lint && npm run build && npm run test` xanh (tsc -b không vướng test file).

<!-- Updated: Validation Session 1 + Red Team Session 1 - vitest + COPY fixture (không cross-root); tsconfig.test + eslint override; cleanup-on-unmount; use-indicators không đụng -->
> **Decision:** vitest parity máy enforce, fixture COPY vào web/ (không cross-root `node:fs` — red-team Finding 3). Strong threshold FE = `0.30` (khớp `max_rejection_wick_pct` BE default — **lưu ý:** nếu user tune param BE khác 0.30, chart vẫn 0.30; coloring là visual aid, không phản ánh config backtest cụ thể — ghi trong Phase 4 doc).

## Risk Assessment

- **Risk (CAO):** `createSeriesMarkers` gọi 2 lần → override / leak plugin. Mitigation: một markersRef, một `setMarkers(merged)`; giữ nguyên cleanup `detach()` hiện có.
- **Risk:** TS/Python lệch định nghĩa theo thời gian. Mitigation: golden fixture chung + test 2 bên (bước 4).
- **Risk:** float boundary khác giữa TS/Python (vd làm tròn). Mitigation: fixture so approx 2 bên; tránh phép tính khác thứ tự.
- **Risk:** sót nơi khởi tạo `IndicatorConfig` → TS build lỗi thiếu field. Mitigation: bước 1 grep toàn bộ; build bắt lỗi.
