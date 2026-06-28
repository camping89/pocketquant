---
phase: 1
title: "EMA dual-line 9/21"
status: completed
effort: "S"
---

# Phase 1: EMA dual-line 9/21

## Overview

Thay EMA overlay đơn (period 50) bằng bộ 2 đường EMA 9 + EMA 21, render dưới chung toggle `EMA`. Đụng 2 file, 7 ref `ema50` phải đổi hết.

## Requirements

- Functional: khi `config.ema === true`, tính & render 2 đường EMA(9) và EMA(21); khi false → cả hai rỗng (giữ pattern lazy hiện tại).
- Non-functional: không còn ref `ema50` sót lại (TypeScript strict sẽ bắt). EMA 9 phải nổi hơn EMA 21 về thị giác (màu nóng + nét dày).

## Architecture

```
use-indicators.ts  →  IndicatorData { ema9, ema21 }   (bỏ ema50)
indicator-series.ts →  COLORS.ema9 / COLORS.ema21
                       block if(config.ema): 2x addSeries(LineSeries)
```

Bảng màu/nét:

| Đường | Period | Màu | lineWidth | Lý do |
|-------|--------|-----|-----------|-------|
| EMA fast | 9 | `#FF9800` cam | 2 | giữ màu EMA cũ, fast nổi bật |
| EMA slow | 21 | `#42A5F5` xanh sáng | 1 | tương phản 2 nền, tránh trùng `#2196F3` (SMA/BB) |

## Related Code Files

- Modify: `web/src/hooks/use-indicators.ts`
- Modify: `web/src/components/chart/indicator-series.ts`

## Implementation Steps

1. **`use-indicators.ts`** — `IndicatorData` interface (dòng ~16): bỏ `ema50: LinePoint[]`, thêm:
   ```ts
   ema9: LinePoint[]
   ema21: LinePoint[]
   ```
2. **`use-indicators.ts`** — thân `useMemo` (dòng ~50): thay
   ```ts
   const ema50 = config.ema ? toLinePoints(times, ema(closes, 50)) : []
   ```
   bằng
   ```ts
   const ema9 = config.ema ? toLinePoints(times, ema(closes, 9)) : []
   const ema21 = config.ema ? toLinePoints(times, ema(closes, 21)) : []
   ```
3. **`use-indicators.ts`** — return object (dòng ~82): đổi `ema50` → `ema9, ema21`.
4. **`indicator-series.ts`** — `COLORS` (dòng ~13): bỏ `ema50: '#FF9800'`, thêm
   ```ts
   ema9: '#FF9800',
   ema21: '#42A5F5',
   ```
5. **`indicator-series.ts`** — block `if (config.ema ...)` (dòng ~39-43): thay 1 series bằng 2:
   ```ts
   if (config.ema) {
     if (data.ema9.length > 0) {
       const s = chart.addSeries(LineSeries, { color: COLORS.ema9, lineWidth: 2, priceScaleId: 'right' })
       s.setData(data.ema9)
       all.push(s)
     }
     if (data.ema21.length > 0) {
       const s = chart.addSeries(LineSeries, { color: COLORS.ema21, lineWidth: 1, priceScaleId: 'right' })
       s.setData(data.ema21)
       all.push(s)
     }
   }
   ```
6. Grep xác nhận `grep -rn "ema50" web/src` → 0 kết quả.

## Success Criteria

- [ ] `IndicatorData` không còn `ema50`; có `ema9` + `ema21`.
- [ ] `config.ema` bật → 2 series render (cam dày 9 / xanh mảnh 21); tắt → không series nào.
- [ ] `grep -rn "ema50" web/src` trả 0 dòng.
- [ ] `npx tsc -b` không lỗi ở 2 file này.

## Risk Assessment

- **Ref `ema50` sót** → lỗi TS. Mitigation: step 6 grep + typecheck ở phase 2. Đã liệt kê đủ 7 ref hiện có (2 file).
- **Trùng màu SMA** nếu lỡ dùng `#2196F3`. Mitigation: chốt `#42A5F5`.
- `lineWidth` lightweight-charts nhận literal number — không cần đổi type.
