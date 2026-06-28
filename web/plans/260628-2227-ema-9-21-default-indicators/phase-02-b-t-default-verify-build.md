---
phase: 2
title: "Bật default + verify build"
status: completed
effort: "XS"
dependencies: [1]
---

# Phase 2: Bật default + verify build

## Overview

Bật `ema` + `engulfing` mặc định khi mở chart, rồi verify toàn bộ bằng build (typecheck + bundle).

## Requirements

- Functional: chart mở lần đầu hiện sẵn EMA (2 đường) + engulfing markers.
- Non-functional: `npm run build` pass sạch.

## Related Code Files

- Modify: `web/src/routes/index.tsx` (DEFAULT_INDICATORS, dòng ~27-34)

## Implementation Steps

1. **`routes/index.tsx`** — trong `DEFAULT_INDICATORS`:
   ```diff
   - ema: false,
   - engulfing: false,
   + ema: true,
   + engulfing: true,
   ```
   Các indicator còn lại (`sma`, `rsi`, `macd`, `bollinger`) giữ `false`.
2. Chạy `npm run build` (`tsc -b && vite build`) tại `web/` → phải pass, đặc biệt bắt mọi ref `ema50` sót từ phase 1.
3. (tùy chọn, nếu môi trường có dev server) `npm run dev`, mở chart, mắt thường xác nhận: 2 đường EMA (cam dày + xanh mảnh) + markers engulfing hiện ngay; bấm tắt/bật nút `EMA` thấy cả 2 đường ẩn/hiện đồng bộ.

## Success Criteria

- [ ] `DEFAULT_INDICATORS.ema === true` và `.engulfing === true`; các indicator khác vẫn `false`.
- [ ] `npm run build` exit 0, không lỗi TypeScript.
- [ ] (nếu chạy dev) chart mở sẵn EMA 9/21 + engulfing; toggle EMA ẩn/hiện cả 2 đường.

## Risk Assessment

- **Lỗi build do ref sót** từ phase 1 → đây chính là cổng verify. Nếu fail, quay lại fix ref trong 2 file phase 1 rồi build lại.
- Blast radius bằng 0 với backend: chỉ đổi giá trị default boolean + render frontend.
