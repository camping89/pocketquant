---
title: "EMA 9/21 dual-line + bật EMA & engulfing mặc định (frontend)"
description: >-
  Thay EMA overlay đơn (period 50) bằng bộ EMA fast/slow 9 & 21 với 2 màu tương
  phản tốt trên cả nền tối lẫn sáng; EMA 9 nổi hơn (cam, nét dày) so với EMA 21
  (xanh sáng, nét mảnh). Bật sẵn EMA + engulfing khi mở chart. Thuần frontend
  (web/), không đụng backend / golden fixture.
status: completed
priority: P2
branch: "develop"
tags:
  - frontend
  - chart
  - indicators
blockedBy: []
blocks: []
created: "2026-06-28T15:28:41.516Z"
createdBy: "ck:plan"
source: skill
---

# EMA 9/21 dual-line + bật EMA & engulfing mặc định (frontend)

## Overview

3 thay đổi thuần frontend trong `web/`:

1. EMA hiện là 1 đường period 50 (`ema50`, hardcoded frontend). Đổi thành **bộ 2 đường EMA 9 + EMA 21** dưới chung 1 toggle `EMA`.
2. Màu: **EMA 9 = `#FF9800` cam, `lineWidth 2`** (fast, nổi bật); **EMA 21 = `#42A5F5` xanh sáng, `lineWidth 1`** (slow, nền tham chiếu). Hai hue nóng/lạnh tương phản tốt trên cả nền tối `#1a1a2e` (hiện tại) lẫn nền sáng. `#42A5F5` chọn thay vì `#2196F3` để không trùng SMA / BB middle.
3. Bật `ema` và `engulfing` mặc định (`routes/index.tsx`).

**Không đụng:** backend (`src/pocketquant/`), golden fixture, engulfing detector, `IndicatorConfig` (giữ 1 field `ema: boolean`), `indicator-toggles.tsx`.

## Quyết định đã chốt (từ brainstorm)

- 1 nút `EMA` bật cả 9 + 21 (không tách 2 nút) → `IndicatorConfig.ema: boolean` giữ nguyên.
- Thay thế hoàn toàn EMA 50 (bỏ hẳn, không giữ 3 đường).
- 2 hue tương phản (cam + xanh) thay vì cùng tông đậm-nhạt → an toàn cả nền đen lẫn trắng. "EMA 9 đậm/nổi hơn" thể hiện qua tông nóng + nét dày gấp đôi.
- EMA 21 dùng `#42A5F5` (Blue 400) để tránh trùng `#2196F3` của SMA 20 / BB middle.

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [EMA dual-line 9/21](./phase-01-ema-dual-line-9-21.md) | Completed |
| 2 | [Bật default + verify build](./phase-02-b-t-default-verify-build.md) | Completed |

## Acceptance Criteria

- [x] Mở chart lần đầu: 2 đường EMA (cam dày = 9, xanh mảnh = 21) + engulfing markers hiện sẵn, không cần bấm gì.
- [x] Nút `EMA` tắt → cả 2 đường biến mất; bật lại → hiện lại cả 2.
- [x] `npm run build` (`tsc -b && vite build`) pass — không còn ref `ema50` nào sót gây lỗi TypeScript.

## Dependencies

Không có. Plan `2026-06-28-engulfing-strategy` (completed) đã ship engulfing detector + chart markers; plan này chỉ bật default, không phụ thuộc thay đổi đang chờ.
