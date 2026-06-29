---
phase: 5
title: "Live clock"
status: done
priority: P3
dependencies: [1]
effort: "S"
---

# Phase 5: Live clock

<!-- Updated: Validation Session 1 - no change (verified __root.tsx + tzSuffix); confirmed cụm [LiveClock][ThemeToggle][TimezoneSwitcher] -->

## Overview

Đồng hồ realtime ở góc trên phải app-nav, cạnh `TimezoneSwitcher`. Tự cập nhật mỗi giây, đổi UTC/Local theo timezone dropdown đang chọn.

## Requirements

- Functional: hiển thị `HH:mm:ss` + suffix tz; tick mỗi 1s; đổi UTC↔Local tức thì khi dropdown đổi.
- Non-functional: cleanup interval khi unmount; tái dùng formatter có sẵn (`tzSuffix`, dayjs) — không thêm lib.

## Architecture

### Component

```tsx
// web/src/components/layout/live-clock.tsx
import { useEffect, useState } from 'react'
import dayjs from 'dayjs'
import utc from 'dayjs/plugin/utc'
import { useTimezone } from '../../lib/use-timezone'
import { tzSuffix } from '../../lib/datetime'
dayjs.extend(utc)  // (đã extend ở datetime.ts, idempotent)

export function LiveClock() {
  const { mode } = useTimezone()
  const [now, setNow] = useState(() => dayjs())
  useEffect(() => {
    const id = setInterval(() => setNow(dayjs()), 1000)
    return () => clearInterval(id)
  }, [])
  const t = mode === 'utc' ? now.utc() : now.local()
  return (
    <span className="live-clock" title="Current time">
      {t.format('HH:mm:ss')} {tzSuffix(mode)}
    </span>
  )
}
```

> Không format qua `formatHmsTime(iso, mode)` vì hàm đó nhận ISO string của một timestamp đã lưu; ở đây ta có `dayjs` "now" trực tiếp — format thẳng gọn hơn, vẫn dùng `tzSuffix(mode)` chung.

### Đặt vào `__root.tsx`

Cụm góc phải hiện: `<div flex:1 /><div>{TimezoneSwitcher}</div>`. Đổi thành cụm 3 item, thứ tự: `[LiveClock] [ThemeToggle] [TimezoneSwitcher]` (ThemeToggle từ Phase 1). Wrap trong 1 `div` flex `gap:12, align-items:center`.

### Style

Thêm `.live-clock` vào `index.css`: `font-variant-numeric: tabular-nums` (số không nhảy), `font-size:13px`, `color: var(--text-secondary)`, monospace nhẹ. (Đã có `.utc-clock` ở monitor page dòng ~319 — tham khảo nhưng tạo class riêng để không đụng monitor.)

## Related Code Files

- Create: `web/src/components/layout/live-clock.tsx`
- Modify: `web/src/routes/__root.tsx` (thêm LiveClock vào cụm góc phải)
- Modify: `web/src/index.css` (`.live-clock` style)
- Reference: `web/src/lib/use-timezone.ts`, `web/src/lib/datetime.ts` (`tzSuffix`)

## Implementation Steps

1. Tạo `live-clock.tsx` (interval 1s + cleanup, format theo `mode`).
2. `__root.tsx`: wrap cụm góc phải `[LiveClock][ThemeToggle][TimezoneSwitcher]` trong flex container.
3. `.live-clock` style trong `index.css` (tabular-nums, var color).
4. `npm run lint` + `npm run build`; kiểm: clock tick mỗi giây; đổi dropdown UTC↔Local → giờ + suffix đổi tức thì; chuyển route → clock vẫn chạy (ở app-nav, không remount).

## Success Criteria

- [ ] Clock hiển thị `HH:mm:ss` + suffix, tick mỗi giây.
- [ ] Đổi timezone dropdown → clock đổi UTC/Local tức thì.
- [ ] Interval cleanup khi unmount (no leak).
- [ ] Layout góc phải gọn: clock + theme toggle + tz switcher thẳng hàng.
- [ ] `npm run lint` + `npm run build` pass.

## Risk Assessment

- **Phụ thuộc Phase 1** (ThemeToggle cùng cụm `__root.tsx`). Mitigation: `blockedBy` [1]; nếu Phase 1 chưa xong, đặt `[LiveClock][TimezoneSwitcher]` trước, chèn toggle sau.
- **Re-render mỗi giây** — chỉ `LiveClock` re-render (state cục bộ), không ảnh hưởng cây. An toàn.
