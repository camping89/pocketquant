---
phase: 1
title: "Number format util"
status: completed
priority: P1
dependencies: []
---

# Phase 1: Number format util

## Overview

Tạo `web/src/lib/number-format.ts` — format util thuần cho quantity/price, sửa lỗi tràn cột (content cutoff) ở orders/trades/drawer/history. Có unit test. Độc lập, làm trước để P2/P3 dùng.

## Requirements

- Functional:
  - `formatQty(n: number | null | undefined): string` — significant-digits (≥6 sig digits), bỏ trailing zeros. `0.009343299644197806` → `0.00934330` (hoặc gọn hơn nhưng KHÔNG mất bậc), `5406` → `5406`. `null/undefined/NaN` → `—`.
  - `formatPrice(n: number | null | undefined): string` — 2 decimals + thousands separator. `109169.14140000001` → `109,169.14`. `null` → `—`.
- Non-functional: pure, không React import (như `datetime.ts`). KISS — dùng `Intl.NumberFormat` / `toPrecision`, không thư viện mới.

## Architecture

- File mới `web/src/lib/number-format.ts` — canonical. Đặt ở `lib/` đúng pattern util thuần (`datetime.ts`, `symbol-format.ts`, `theme-colors.ts`). KHÔNG mâu thuẫn workbench M6 (M6 nói về API fetch module).
- `positions-utils.ts` đang có `fmtPrice`/`fmtPnl` cục bộ → giữ `fmtPnl` (PnL-specific, có dấu `+`), nhưng `fmtPrice` re-export từ `number-format` để DRY (1 nguồn sự thật).
- `formatQty` design: dùng `Number(n.toPrecision(8))` rồi `String()` để bỏ trailing zeros + tránh float noise (`...0001`). Số nguyên lớn (5406) giữ nguyên.

## Related Code Files

- Create: `web/src/lib/number-format.ts`
- Create: `web/src/lib/number-format.test.ts`
- Modify: `web/src/components/strategy/backtest-panel/positions-utils.ts` (re-export `fmtPrice` từ `number-format`)

## Implementation Steps

1. Viết `number-format.ts`:
   ```ts
   const PLACEHOLDER = '—'
   const priceFmt = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

   export function formatPrice(n: number | null | undefined): string {
     if (n == null || Number.isNaN(n)) return PLACEHOLDER
     return priceFmt.format(n)
   }

   /** Quantity: ≥6 significant digits, bỏ trailing zeros + float noise. */
   export function formatQty(n: number | null | undefined): string {
     if (n == null || Number.isNaN(n)) return PLACEHOLDER
     if (n === 0) return '0'
     return String(Number(n.toPrecision(8)))
   }
   ```
2. Viết `number-format.test.ts` — cover: qty nhỏ crypto (`0.009343299644197806`), qty nguyên (`5406`), price thousands (`109169.1414` → `109,169.14`), null/NaN → `—`, float noise (`109169.14140000001` → `109,169.14`).
3. Sửa `positions-utils.ts`: `export { formatPrice as fmtPrice } from '../../../lib/number-format'` (bỏ định nghĩa local), giữ `fmtPnl` nguyên.
4. Chạy `npx vitest run number-format` → pass.

## Success Criteria

- [ ] `number-format.ts` + test pass.
- [ ] `formatQty` không mất bậc với qty crypto nhỏ, không có float noise đuôi.
- [ ] `formatPrice` có thousands separator, 2 decimals.
- [ ] `positions-utils.ts` re-export `fmtPrice`, không trùng định nghĩa.
- [ ] `npm run build` + `vitest run` pass.

## Risk Assessment

- **Làm tròn mất thông tin qty nhỏ:** dùng `toPrecision(8)` (sig digits) không `toFixed` → giữ được `0.00000123`. Mitigate qua test case qty rất nhỏ.
- **`Intl.NumberFormat` locale:** ép `'en-US'` để thousands = `,` nhất quán, không phụ thuộc browser locale.
