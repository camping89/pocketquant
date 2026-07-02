# Backtest Trades — Cursor Paging + Backend Stats Centralization

## Vấn đề

Tab **Trades** của trang backtest (`/backtest?run=<id>`) tải TOÀN BỘ trades một lần
(`GET /backtest/{run_id}/trades` không param) rồi:

- render toàn bộ `<tr>` **không virtualize** → DOM phình, lag
- tính client-side: histograms (PnL, duration), win/loss streak, profit-factor-by-direction, drawdown periods
- chart box/info định vị trade theo **array index** vào `positions[]` đầy đủ → index không ổn định khi paginate

## Mục tiêu (quyết định của user)

1. **Cursor paging** cho bảng trades (keyset), **infinite scroll + virtualized** (`@tanstack/react-virtual`).
2. **Filter (all/wins/losses) + sort 10 cột → server-side.**
3. **Toàn bộ stats + markers chuyển về backend**, gom vào **một dedicated app service** (`BacktestStatsService`). FE chỉ load, không tính.
4. **Giữ nguyên "chọn trade → vẽ box/info trên chart"** — chuyển sang chọn theo `trade_id` (UUIDv7 ổn định) thay array index.
5. **Open positions tách sang tab riêng** trên UI (không nằm trong bảng trades paginated).

## Kiến trúc & ràng buộc (import-linter)

- Stats **thuần** (không I/O) → `pocketquant.backtest.domain.services` (cạnh `PerformanceCalculator`).
- App-service `BacktestStatsService` → `pocketquant.backtest` (cạnh `BacktestQueryService`), inject `BacktestTradeRepository` + `BacktestRepository`.
- Repo paginated/markers → mở rộng `BacktestTradeRepository` trong `core.infra.persistence.repositories` (repos chỉ ở core).
- Routes → `app/routes/backtest.py`, `FromDishka[...]` + `DishkaRoute`.
- Không `fastapi`/`bson` ngoài app; PK UUIDv7; single uvicorn worker.

## Cursor design (keyset, không offset)

- Cursor = base64(JSON `{k: <sort_value>, id: <trade_id>}`) — tie-break bằng `_id` để ổn định.
- Sort key hợp lệ: `entry_time | pnl | quantity | duration_seconds | entry_price | exit_price | commission | direction | status`. `index`/`entry_time` mặc định `entry_time`.
- Query Mongo: `{run_id, <keyset condition theo (sort_val, _id) và dir>}`, `.sort([(key,dir),("_id",dir)]).limit(n+1)`; phần tử thứ n+1 xác định `has_more` + `next_cursor`.
- Filter `wins` → `pnl>0`, `losses` → `pnl<0` thêm vào query filter.
- Chỉ closed trades (collection `backtest_trades`). Open positions không paginate.

## Phases

| # | Phase | File | Trạng thái |
|---|-------|------|-----------|
| 1 | Backend: calculator + repo + stats service + routes + DI + tests | `phase-01-backend.md` | done |
| 2 | Frontend data layer: api + hooks + types | `phase-02-frontend-data.md` | done |
| 3 | Frontend UI: virtualized table + chart selection + BE stats + Open tab | `phase-03-frontend-ui.md` | done |
| 4 | Verify: tests, lint/types/build, openapi snapshot, review, smoke | `phase-04-verify.md` | done (smoke thủ công còn lại) |

Dependencies: 1 → 2 → 3 → 4 (contract backend chốt trước).

## Kết quả verify

- Backend: 110 tests pass (calculator 13, repo 10, stats service 4, + suite), ruff + pyright clean, import-linter 7/7 KEPT, openapi/route snapshot regenerated.
- Frontend: `npm run build` (tsc+vite) clean, `npm run lint` 0 errors, `npm run test` 32 pass. `@tanstack/react-virtual` added.
- Code review: keyset cursor SOUND (tie-break `_id`), stats parity EXACT vs FE oracle, contract propagated. Blocker (stats-utils chưa xóa) + H1 (count/sum mỗi page) + H2 (in-memory sort 32MB) đã fix.
- Nits N1–N4/M1: giữ nguyên (vô hại, YAGNI).

## Acceptance criteria

- Bảng trades tải theo trang (mặc định ~50 trade/trang), cuộn tới đáy nạp trang kế; chỉ render row trong viewport.
- Filter/sort áp dụng **toàn dataset** (server-side), không chỉ trang đã tải.
- Click 1 trade (ở bất kỳ trang nào) → chart scroll + vẽ box/info đúng trade đó; hover → outline box. Hoạt động qua trade_id, không phụ thuộc index.
- Chart markers (BUY/SELL arrow) vẫn hiển thị cho **mọi** trade của run (từ endpoint markers-lite).
- PnL histogram, Duration histogram, streaks, PF-by-direction, drawdown table hiển thị đúng như hiện tại nhưng **dữ liệu từ backend**.
- Open positions hiển thị ở tab riêng.
- `just lint`, `just types`, `just test` (backend) và `npm run lint`, `npm run build` (web) xanh. OpenAPI/route snapshot cập nhật.
- Không regression: overview/risk/orders tab, verdict, run-history rail, poll-until-finished.

## Ngoài phạm vi

- Không đổi cách backtest engine tính/persist metrics (chỉ đọc lại).
- Không paginate Orders tab (đã lazy, để nguyên).
- Không thêm cursor paging cho run-history rail.
- Không đổi schema Mongo trades (dùng field + index sẵn có).

## Rủi ro

- **Contract drift FE/BE**: chốt DTO trong phase 1, FE bám theo. Cập nhật openapi snapshot.
- **Selection ổn định**: rủi ro chính là mất box/info. Mitigate: chọn theo trade_id + truyền object trade vào chart, có test.
- **Keyset đúng đắn khi trùng sort value**: luôn tie-break `_id`; có test trùng `entry_time`/`pnl`.
- **Stats parity**: port 1-1 logic FE (đã có test FE làm oracle) → thêm test BE đối chiếu.
