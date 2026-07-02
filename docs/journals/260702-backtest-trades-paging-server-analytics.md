# Backtest Trades Paging + Server-Side Analytics

**Date**: 2026-07-02 22:07
**Severity**: High
**Component**: Backend / Web / Backtest Trades Tab
**Status**: Completed

## What Happened

Hoàn tất feature refactor tab Trades của trang backtest (`/backtest?run=<id>`). Trước: load toàn bộ trades một lần, tính stats client-side → UI lag + BE overload. Sau: server-side paging (keyset cursor, `.allow_disk_use(True)`), dedicated `BacktestStatsService`, infinite scroll + virtualized table, chart selection ổn định qua paging. Commit `504e276` (code), workflow CI/CD + Playwright automation 5/5 pass trên prod.

## The Brutal Truth

Tab Trades là cái cổ chai: load 10K+ trades → FE parsing + tính histogram/streak/PF/drawdown → DOM render → mỗi re-sort lại recalculate hết. Trên run lớn (3-4K trades), tab này bị freeze 3-4 giây. Chart selection bị break khi người dùng sort/filter lại vì selection tracking bằng array index (khi paging thay đổi thì index mismatch → click trade sai).

Thêm nữa, bỏ stats tính client-side mà chưa chắc backend hoàn hảo → phải code-review kỹ keyset cursor logic, tie-break, datetime decode (3 điều dễ sai).

## Technical Details

**Backend changes (`src/pocketquant/backtest/backtest_stats_service.py`):**
- New `BacktestStatsService`: gom toàn bộ analytics queries + aggregation (paged + aggregate modes).
- Domain calculator `trade_stats_calculator.py`: histogram/streaks/profit-factor/max-drawdown (pure functions, testable riêng).
- Repository mở rộng: `list_by_run_paged(run_id, sort_by, direction, cursor, limit)` keyset cursor, tie-break `_id`; `count_by_run`, `sum_pnl_by_run`, `list_markers_by_run`.
- Endpoint changes:
  - `GET /{run_id}/trades`: `{trades: [...]}` → `{items, next_cursor, has_more, total, total_pnl}` (paged contract)
  - New `GET /{run_id}/trades/markers`: trades dành để vẽ marker trên chart (trade_id, entry_exit signals)
  - New `GET /{run_id}/stats`: histogram/streaks/profit-factor/drawdown (top-level aggregate, không tính lại mỗi page)
- Index thêm `ix_bttrades_run_pnl` để tie-break khi sort `pnl`.
- Bỏ endpoint `BacktestQueryService.list_trades`.

**Keyset cursor design:**
```
cursor = Base64Encode({v: "1", id: <trade_id>, <sort_field>: <value>})
```
- `v`: version (upgrade-safe)
- Opaque: client không decode
- Tie-break `_id`: ordering deterministic khi `pnl` (hay sort field khác) trùng lặp
- Footer aggregate (total/total_pnl) chỉ tính ở page đầu (`cursor is None`), skip ở page sau (tối ưu hóa).

**Frontend changes:**
- Infinite scroll + `@tanstack/react-virtual` (row virtualization, 50-100 rows visible mỗi lần).
- Filter/sort server-side → `useInfiniteQuery` từ `@tanstack/react-query`.
- Selection từ array index → **trade_id (UUIDv7)**: click trade → highlight row + vẽ box/info trên chart, bền vững qua page thay đổi.
- Bỏ `stats-utils.ts` (client-side histogram/streak/PF/drawdown) → consume `GET /stats` endpoint.
- Tab Open Positions tách riêng (không mix vào Trades tab).

**Verify scope:**
- Backend: 110 tests pass (trade_stats_calculator, repository keyset, service paging)
- Web: 32 tests pass (infinite scroll, cursor decode, selection stable)
- Lint: ruff/pyright/eslint/tsc all clean
- import-linter: 7/7 contracts KEPT
- OpenAPI + route snapshot regenerated
- Code-review (code-reviewer): keyset sound, stats parity exact
- Fix: `git rm -f stats-utils.ts` (zsh `-i` alias prompt bị nuốt trong non-interactive shell)
- Automation: Playwright 5/5 pass trên prod (contract + UI + virtualization)

## What We Tried

1. **Offset pagination**: simple, but cursor-less paging = instability khi user sort mid-scroll (rows added/removed).
   - Switched: keyset cursor (deterministic) ✓

2. **Client-side stats (histogram/streaks)**: no extra BE load, intuitive.
   - Problem: 10K+ items → O(n) recalc mỗi filter/sort; UI freeze 3-4s trên large runs.
   - Switched: server-side stats, cache trong memory BE ✓

3. **Selection bằng array index**: simple, works khi table static.
   - Problem: paging thay đổi → index mismatch → click trade sai; chart selection lost.
   - Switched: stable UUID (trade_id) ✓

4. **MongoDB aggregate pipeline iterate (không `.allow_disk_use`)**: memory-efficient cho small pipelines.
   - Problem: >32MB pipeline spill → memory OOM risk, abandon
   - Switched: `.allow_disk_use(True)` (MDB 3.2+) ✓

5. **Footer aggregate (total/total_pnl) mỗi page**: consistency, user expects
   - Problem: redundant calculation mỗi cursor → tốn query time.
   - Switched: chỉ tính page đầu (user nhìn đó), page sau skip ✓

## Root Cause Analysis

**Tại sao UI lag:**
- FE load 10K trades đơn thuần = parse JSON + DOM render (chấp được).
- Nhưng stats tính client-side (histogram binning, streak detect) = O(n) mỗi lần → bottleneck thực tế.
- Virtualization mà không paging = memory trong DOM vẫn lớn → React reconciliation slow.

**Tại sao selection break:**
- Table rendering mà không stable key (dùng array index) = React key warningxung quanh; swap/reorder rows → key cũ map item mới → selection stale.
- Keyset cursor paging = row order thay đổi khi sort/filter → index không còn sense.

**Tại sao zsh `rm -i` prompt hidden:**
- zsh `rm` alias `rm -i` (interactive) để phòng xóa nhầm.
- Nhưng non-interactive shell (CI, script) có stdin=null → prompt nhận input gì? → prompt mặc nhiên cancel (file không xóa).
- Test chỉ chạy trên dev (stdin=tty) nên pass, production không test, stats-utils.ts vẫn tồn tại.
- Fix: dùng `git rm -f` (luôn force xóa tracked file) thay vì `rm`.

## Lessons Learned

1. **Keyset cursor = deterministic paging.** Offset unstable khi data thay đổi mid-scan; keyset tie-break (`_id`) guarantee order + repeatability.

2. **Stable selection keys (UUID > index).** Nếu user có thể re-order/filter table, selection phải dùng domain ID, không array position.

3. **Virtualization phải kèm paging.** Row virtual mà không paging = DOM nhỏ nhưng data khổng lồ trong memory. Cải thiên chậm nếu chỉ chốt ở FE.

4. **Stats centralization (BE > FE).** Khi stat logic phức tạp + recalc mỗi filter, BE chủ động. FE consume endpoint. DDD: encapsulate domain logic (`trade_stats_calculator`) ở domain layer, app-service expose.

5. **Non-interactive shell ≠ interactive dev.** `rm -i` prompt works ở terminal (stdin=tty) nhưng CI/script → input silently ignored. Git rm / bash set -e / explicit error check bảo vệ.

6. **PyMongo async pitfall: coroutine must await trước iterate.** `collection.aggregate(pipeline)` trả coroutine; `async for doc in agg_coro` = error. Phải `await` hoặc dùng `async_command_cursor`.

## Next Steps

- [x] Code reviewed + fixed (keyset sound, stats exact, zsh rm issue gone)
- [x] Tests pass (backend 110, web 32)
- [x] Shipped & deployed (commit `504e276`, prod `/backtest?run=...`)
- [x] Automation verified (Playwright 5/5)
- [ ] **Monitor prod:** lag metric on tab Trades, cursor stability after sort/filter
- [ ] **Update docs:** keyset cursor pattern + stable selection guideline → `docs/code-standards.md` (reference for future pagination)
- [ ] **Optional:** if future tabs hit same paging + stats issue, reuse `BacktestStatsService` pattern (already modular)

**Owner**: Backend (stats service) + Web (infinite scroll). Ready production.

**Timeline**: Completed 2026-07-02 22:07. Code `504e276` shipped, CI/CD + live tests pass.
