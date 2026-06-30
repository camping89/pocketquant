# Brainstorm — Backtest Workbench: master-detail 1 trang + sửa UX/overlap

- **Ngày:** 2026-06-30
- **Phạm vi:** Frontend `web/` (React 19 + TanStack Router/Query + lightweight-charts)
- **Modes:** none (markdown only)
- **Trạng thái:** Đã duyệt thiết kế → handoff `/ck:plan`
- **Bằng chứng (screenshot):** `plans/reports/assets/260630-1544-backtest-workbench-ux/`

---

## 1. Problem statement

Trang backtest hiện "bad UXUI": **overlap nhẹ + content cutoff + lãng phí không gian**, và list/detail tách 2 route rời rạc. Yêu cầu: gộp list + detail vào 1 trang, click 1 run → **lazy-load** detail (không preload).

Đã xác nhận với user: **KHÔNG phải crash thật** (white-screen). `tsc -b` pass sạch. Vấn đề là layout + format số.

## 2. Bằng chứng (đã chụp trực tiếp bằng agent-browser)

| # | Vấn đề | Bằng chứng | Mức |
|---|--------|-----------|-----|
| 1 | **Lãng phí không gian** — `maxWidth: 720/1080` + `margin:auto` nhồi nội dung vào cột giữa, desktop 1440px trống ~430px mỗi bên | `desktop-1440-wasted-space.png` | Cao |
| 2 | **Số không format → cutoff** — QTY `0.009343299644197806`, giá `109169.14140000001` ở orders/trades/drawer | `order-drawer-unformatted-numbers.png`, `trades-tab.png` | Cao |
| 3 | **Charts bị bóp hẹp** — equity/drawdown/histogram chỉ chiếm bề ngang cột giữa | `desktop-1440-wasted-space.png` | TB |
| 4 | **List ↔ detail 2 route tách rời** — `/backtest` ↔ `/backtest_/$runId`, mất context | route files | Cao (yêu cầu chính) |
| 5 | **Drawer che table** — order drawer che cột Fills phía sau, table không nhường chỗ | `order-drawer-unformatted-numbers.png` | Thấp |

Điểm tích cực: drawer z-index/backdrop đúng; không có overlap chồng layer thật. Hook đã sẵn cho lazy: `useBacktestRun` có `enabled: !!runId`, `useBacktestOrders` chỉ fetch khi tab Orders mở.

## 3. Approaches đã cân nhắc

| Approach | Mô tả | Pros | Cons | Quyết định |
|----------|-------|------|------|-----------|
| **A. Master-detail trái/phải** | List trái ~400px, detail 1fr; clone `.strategies-layout` | Tái dùng pattern có sẵn; tận dụng full viewport; lazy tự nhiên | Cần compact list để không tràn | ✅ **Chọn** |
| B. List trên / detail expand inline (accordion) | Table full-width, click row expand dưới | Đơn giản | Chart trong accordion dễ nhảy layout; xem detail + so list khó | ✗ |
| C. Gộp tất cả (form+list+detail+compare) 1 trang | | Một chỗ làm hết | Nhiều thay đổi, rủi ro cao | ✗ (compare giữ riêng) |

## 4. Giải pháp chốt

### Route & state
- 1 route `/backtest?run=<id>` (gộp list+detail). `validateSearch({run})` giống `/compare`.
- Xóa `routes/backtest_.$runId.tsx`; link cũ redirect `/backtest?run=<id>`.
- Detail: `useBacktestRun(run)` với `enabled: !!run` → **lazy**, `run` null → empty state.
- `/backtest/compare?runs=a,b` **giữ nguyên route riêng**.

### Layout (clone `.strategies-layout`)
- Desktop ≥768px: grid `400px 1fr`, `height: calc(100vh - 41px)`, 2 pane scroll độc lập.
- Bỏ `maxWidth` cứng → full viewport. KPI grid `auto-fill minmax(140px,1fr)` dùng hết bề ngang.
- Mobile <768px: 2 tab `[List][Detail]`, chọn run nhảy sang tab Detail (như `handleSelectSub`).

### Cột List — compact row (không phải table 9 cột)
- Mỗi run 1 card: dòng 1 `ngày·strategy·symbol·interval`; dòng 2 `Return%`(màu) + `Sharpe` + `#trades` + verdict dot. Checkbox compare (≤3). Row active viền trái accent.
- Filter strategy/symbol/interval giữ logic `RunHistoryRail`, đổi render.

### Format số (sửa cutoff)
- `lib/number-format.ts` mới: `formatQty` (≤6–8 sig digits), `formatPrice` (`109,169.14`).
- Áp: `orders-table`, `positions-table`, `order-detail-drawer`, `backtest-history-table`.

### Error boundary (phòng thủ)
- `errorComponent` ở route `/backtest` → lỗi render detail/chart chỉ hỏng pane, không trắng app.

### Form "Run Backtest"
- Bọc trong drawer, nút "+ New run" trên đỉnh cột list (tái dùng pattern `order-detail-drawer`).

## 5. Files

| File | Hành động |
|------|-----------|
| `routes/backtest.tsx` | Viết lại: layout master-detail + `validateSearch({run})` + errorComponent |
| `routes/backtest_.$runId.tsx` | Xóa (redirect gộp vào route trên) |
| `components/backtest/backtest-workbench.tsx` | **Mới** — orchestrator 2 pane (desktop grid + mobile tabs) |
| `components/backtest/run-history-rail.tsx` | Sửa: compact row + nhận `selectedRun`/`onSelect` + nút "New run" |
| `components/backtest/run-list-item.tsx` | **Mới** — 1 compact row |
| `components/backtest/backtest-form.tsx` | Bọc drawer |
| `lib/number-format.ts` | **Mới** — formatQty/formatPrice |
| `index.css` | `.backtest-layout` (clone `.strategies-layout`) + compact row styles |

## 6. Rủi ro & lưu ý

- **Resize chart trong pane ẩn/hiện:** lightweight-charts dùng `ResizeObserver` riêng. Khi mobile chuyển tab hoặc detail mount/unmount, chart phải re-init đúng. Kiểm tra `EquityDrawdownChart`/`HistogramChart` cleanup effect (đã có `ro.disconnect()` + `chart.remove()`).
- **Rules of Hooks ở detail pane:** detail conditionally render theo `run`, nhưng hook `useBacktestRun` phải gọi unconditional (đã đúng — `enabled` flag).
- **Redirect route cũ:** đảm bảo bookmark `/backtest/<id>` cũ không 404.
- **`listAllBacktestRuns` fan-out:** giữ nguyên, không phải nguồn lỗi.

## 7. Success criteria

- [ ] Desktop ≥1280px: nội dung dùng full viewport, không cột trống 2 bên.
- [ ] Click run trong list → detail lazy-fetch (Network: chỉ gọi khi chọn), URL có `?run=<id>`, reload giữ run.
- [ ] QTY/price format gọn, không tràn cột ở orders/trades/drawer/history.
- [ ] Mobile <768px: 2 tab hoạt động, không tràn ngang.
- [ ] Lỗi render 1 pane không làm trắng cả app.
- [ ] `tsc -b` pass; `vitest run` pass.

## 8. Quyết định user (đã chốt)

| Câu hỏi | Chốt |
|---------|------|
| State/URL | Search param `?run=<id>` |
| List master | Compact card/row |
| Layout split | Cố định ~400px \| 1fr |
| Vị trí form | Nút "New run" mở drawer |
| Error boundary | Có |
| Compare | Giữ route riêng |
| Format số | Áp toàn bộ |
| Mobile | 2 tab single-pane |

## Unresolved questions

- Ngưỡng làm tròn `formatQty` chính xác (6 hay 8 significant digits)? — sẽ chốt lúc implement, ưu tiên không mất thông tin giá trị nhỏ của crypto.
- Có cần giữ lại "form full page" ở đâu đó cho deep-link không, hay chỉ drawer là đủ? — mặc định chỉ drawer.
