---
phase: 1
title: "Theme foundation"
status: done
priority: P1
dependencies: []
effort: "M"
---

# Phase 1: Theme foundation

<!-- Updated: Validation Session 1 - chốt FINAL palette hex; cụ thể hoá inventory 4 literal rgba dark-bg -->

## Overview

Hạ tầng theme: CSS variable tokens cho dark + light theo palette Claude AI, một `ThemeContext` (pattern y hệt `TimezoneContext` đã có), toggle sun/moon cạnh `TimezoneSwitcher`. Default **dark**, persist localStorage, set `data-theme` trên `<html>`. Đây là nền cho Phase 2 (chart đọc token) và Phase 5 (clock cạnh toggle).

## Requirements

- Functional: toggle dark↔light đổi tức thì toàn bộ UI chrome; persist qua reload; default dark khi chưa có giá trị lưu.
- Non-functional: 1 nguồn sự thật cho màu = CSS variables; không sửa màu rải rác từng component; light theme đủ tương phản (text-secondary, grid, border không chìm trên nền kem).

## Architecture

### Token model (`index.css`)

`:root` hiện tại hard-code 9 biến (dark). Tách thành 2 block, giữ **đúng tên biến cũ** để mọi `var(--…)` callsite không phải đổi.

**FINAL palette — chốt (validation session 1). KHÔNG tự đổi hex khi implement.** Giá trị theo tinh thần Claude AI (clay accent + nền warm-gray/kem), không phải trích xuất pixel từ claude.ai:

```css
:root[data-theme="dark"] {
  --bg-primary: #1F1E1D;      /* warm charcoal */
  --bg-secondary: #262624;
  --bg-tertiary: #30302E;
  --text-primary: #F5F4EE;    /* cream */
  --text-secondary: #B8B5AD;
  --border-color: #3A3937;
  --accent: #D97757;          /* clay */
  --up-color: #4A9782;        /* teal/sage — long */
  --down-color: #C96442;      /* terracotta — short */
}
:root[data-theme="light"] {
  --bg-primary: #F5F4EE;      /* cream */
  --bg-secondary: #ECEAE1;
  --bg-tertiary: #E3E0D5;
  --text-primary: #1F1E1D;
  --text-secondary: #6B6258;
  --border-color: #D6D3C8;
  --accent: #C15F3C;          /* clay đậm — tương phản trên nền sáng */
  --up-color: #3E7D6B;        /* teal — long */
  --down-color: #B55031;      /* terracotta — short */
}
```

> Contrast đã cân: light `--text-secondary #6B6258` trên `--bg-primary #F5F4EE` ≈ 5:1 (đạt WCAG AA cho text thường). Candle up (teal) vs down (terracotta) giữ 2 hue đối lập → đọc được long/short ở cả 2 theme. `--accent` clay chỉ dùng cho UI active states, không cạnh candle nên không nhầm với `--down-color`.
>
> Giữ nguyên `--status-*` job-history tokens (block `:root` thứ 2 trong file, dòng ~664) — chúng độc lập theme, để dark-only. KHÔNG mở rộng scope (out-of-scope theo plan.md).

Một số chỗ trong `index.css` hard-code màu literal thay vì `var()` (vd `#ffa726`, `rgba(22,33,62,…)`, `rgba(255,255,255,.05)`, `#0b1220`). Inventory chúng; với block này chỉ cần đảm bảo **UI chrome chính** (header, nav, button, table, card, symbol/interval/indicator controls) chạy bằng `var()`. Các literal rgba phụ thuộc nền tối (vd `rgba(22,33,62,.92)` sticky header) cần thay bằng token hoặc `color-mix`/var phù hợp để không vỡ ở light — liệt kê trong Implementation Steps.

### Theme context (mirror TimezoneContext)

- `web/src/lib/theme-context.tsx` — Provider only (react-refresh rule). `STORAGE_KEY = 'pq.theme.mode'`. `readInitialMode()` default `'dark'`. `setMode` ghi localStorage + set `document.documentElement.setAttribute('data-theme', m)`.
- `web/src/lib/use-theme.ts` — `useTheme()` hook (mirror `use-timezone.ts`).
- Set `data-theme` ngay khi đọc initial (trước first paint) để tránh flash: gọi `setAttribute` trong module-init của context file HOẶC inline script nhỏ. Đơn giản nhất: trong `readInitialMode()` set luôn attribute rồi return — chạy lúc Provider mount. Chấp nhận 1 frame flash ở dev; nếu cần zero-flash, thêm inline script ở `index.html`. (Đề xuất: zero-flash qua inline script ở `index.html` đọc localStorage + set `data-theme` trước khi React mount.)

### Mount

`main.tsx`: bọc `<ThemeProvider>` ngoài `<TimezoneProvider>` (hoặc cạnh nhau) — Theme phải set `data-theme` trước khi chart đọc `getComputedStyle` (Phase 2).

### Toggle UI

`web/src/components/layout/theme-toggle.tsx` — button dùng class `strategy-select` (đồng bộ style với `TimezoneSwitcher`), hiển thị ☀/☾ theo mode, `onClick` flip. Đặt trong `__root.tsx` app-nav, ngay trước `TimezoneSwitcher`.

> ⚠️ Phase 5 (live clock) cũng sửa `__root.tsx` cùng cụm góc phải. Thứ tự cuối: `[LiveClock] [ThemeToggle] [TimezoneSwitcher]`. Phase 1 chỉ thêm `ThemeToggle`; chừa chỗ cho clock.

## Related Code Files

- Create: `web/src/lib/theme-context.tsx`
- Create: `web/src/lib/use-theme.ts`
- Create: `web/src/components/layout/theme-toggle.tsx`
- Modify: `web/src/index.css` (token blocks + thay literal màu chrome bằng var)
- Modify: `web/src/main.tsx` (mount ThemeProvider)
- Modify: `web/src/routes/__root.tsx` (thêm ThemeToggle vào app-nav)
- Modify: `index.html` (web/index.html) — optional inline no-flash script
- Reference (đọc, không sửa): `web/src/lib/timezone-context.tsx`, `web/src/lib/use-timezone.ts`

## Implementation Steps

1. `index.css`: chuyển 9 biến `:root` → `:root[data-theme="dark"]`, thêm block `:root[data-theme="light"]`. Giữ nguyên tên biến.
2. Inventory literal màu trong `index.css` ngoài 9 token; với UI chrome chính, thay bằng `var(--…)`. Verified callsites cần xử lý (grep `rgba(22, 33, 62` ×3, `rgba(15, 52, 96` ×1):
   - dòng ~327 `.monitor-card` `rgba(22, 33, 62, 0.5)` → `color-mix(in srgb, var(--bg-secondary) 50%, transparent)`
   - dòng ~372 `.monitor-table thead th` `rgba(22, 33, 62, 0.92)` (sticky header) → `color-mix(... 92% ...)`
   - dòng ~432 `.monitor-table tfoot td` `rgba(22, 33, 62, 0.4)` → `color-mix(... 40% ...)`
   - dòng ~537 `.detail-panel` `rgba(15, 52, 96, 0.3)` (bg-tertiary tint) → `color-mix(in srgb, var(--bg-tertiary) 30%, transparent)`
   - `rgba(255, 255, 255, .0x)` overlay sáng (zebra, hover) → giữ được trên cả 2 nền (overlay trắng mờ trên nền sáng gần như vô hình, chấp nhận — KHÔNG vỡ layout). Note nếu muốn polish light về sau.
   - Literal semantic status (`#ffa726` warn, `#ef5350` error, `#26a69a` ok) — giữ; hoạt động trên cả 2 nền.
3. Tạo `theme-context.tsx` + `use-theme.ts` (mirror tz pattern). Default dark.
4. `readInitialMode` set `data-theme` attribute. (Optional) thêm inline no-flash script ở `web/index.html`.
5. `main.tsx`: wrap `<ThemeProvider>`.
6. Tạo `theme-toggle.tsx`; thêm vào `__root.tsx` app-nav trước `TimezoneSwitcher`.
7. `npm run lint` + `npm run build`; mở app, toggle, reload, kiểm cả 2 theme: header/nav/symbol picker/interval/indicator buttons/monitor table/backtest panel/strategies layout.

## Success Criteria

- [ ] Toggle đổi dark↔light tức thì cho toàn UI chrome (nav, header, controls, monitor table, strategies, backtest panel).
- [ ] Default dark khi localStorage trống; persist qua reload.
- [ ] Light theme: text-secondary, border, grid không chìm; không còn mảng nền tối literal sót lại trên nền kem.
- [ ] `data-theme` set trên `<html>` trước first paint (no-flash) hoặc flash ≤1 frame.
- [ ] `npm run lint` + `npm run build` pass.
- [ ] Tên biến CSS giữ nguyên — zero callsite `var()` phải đổi.

## Risk Assessment

- **Literal màu sót** phụ thuộc nền tối → vỡ ở light. Mitigation: inventory ở step 2, grep `rgba(22, 33, 62` / `rgba(15, 52, 96` / `rgba(255, 255, 255` trong `index.css`.
- **Flash theme sai** trước React mount. Mitigation: inline script ở `index.html` (đề xuất) đọc `pq.theme.mode` set `data-theme` đồng bộ.
- **Scope creep** sang `--status-*` job tokens. Mitigation: chốt out-of-scope, để dark-only như hiện tại.
