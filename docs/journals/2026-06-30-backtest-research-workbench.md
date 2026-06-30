# Backtest Research Workbench

Reframe `/backtest` từ single-run ephemeral (reload là mất) thành workbench thống kê deep-link-able: stat dashboard 4 tab, history rail scoped, compare cross-scope, orders drill-down, verdict edit. 4 phase tuyến tính (1 BE/TDD → 3 FE), thực thi liền mạch.

## Quyết định đáng nhớ

- **Mở rộng endpoint thay vì đẻ mới.** Red-team bắt `GET /runs` trùng `GET /backtest/strategy/{id}` đã có → thêm optional `?symbol=&interval=` vào route cũ. Diff baseline thành thuần-additive (1 route orders mới + 2 param), không xóa route nào.
- **`symbol` composite `CODE:EXCHANGE` là một invariant một chiều.** Denormalize top-level từ `config_snapshot`, **uppercase tại mọi write-site** (`started`/`finalize`/`from_mongo` fallback) cho khớp filter `.upper()`. Bài học từ review M1: nếu chỉ query-side normalize, một writer tương lai lưu lowercase → history rỗng âm thầm. Một nguồn sự thật, hai phía không được giả định khác nhau.
- **Tên route theo convention repo, không theo plan.** Plan ghi `backtest.$runId.tsx`, nhưng TanStack file-route đó sẽ nest dưới layout cha (hiện form). Dùng trailing-underscore (`backtest_.$runId.tsx`, `backtest_.compare.tsx`) như `monitor_.jobs.$jobId` sẵn có → detail standalone, URL contract vẫn đúng `/backtest/$runId`.
- **Không recompute aggregate ở FE.** `profitFactorByDirection` chỉ tính split LONG/SHORT; aggregate đọc thẳng `metrics.profit_factor` của BE — tránh hai định nghĩa lệch nhau (red-team M7).
- **Hoãn monthly heatmap.** Equity curve persist downsample ≤5000 (strided) → số tài chính xấp xỉ với strategy thưa trade. Risk&Time MVP = equity+underwater (drawdown chính xác mỗi điểm) + drawdown table top-5.

## Va vấp

- **Lệnh build trong plan sai.** Plan giả định `just lint && just types && just baseline`; `justfile` chỉ có `just test`. Lệnh thật theo CI: `uv run ruff check` / `pyright` / `lint-imports` / `pytest`; baseline regen = `BASELINE_UPDATE=1 uv run pytest tests/baseline`.
- **Guard prod-DB chặn pytest.** Shell env `MONGODB_URL` trỏ VPS prod → conftest từ chối chạy. Testcontainers tự spin Mongo/Redis ephemeral nên chỉ cần `env -u MONGODB_URL -u REDIS_URL uv run pytest`.
- **routeTree.gen.ts không regen khi `tsc -b` chạy trước `vite build`.** Phải `npx vite build` một nhịp (plugin ghi tree) rồi mới `npm run build` full typecheck. `npx tsr generate` không đọc đúng entrypoints config.
- **"adjust state during render" + optimistic update đá nhau (review H1).** VerdictPanel reset textarea khi `verdict` prop đổi — nhưng optimistic-write VÀ revert-on-fail đều chảy qua prop đó, nên nhánh save-fail xóa text user vừa gõ (vi phạm Q6 "GIỮ text"). Fix: track `runId` thay vì `verdict` — chỉ reset khi chuyển sang run KHÁC, không khi verdict cùng run dao động.

## Kết quả

BE 608 passed / 1 skipped · ruff + pyright + import-linter 7/7 ✓. FE lint 0 errors · build ✓ · vitest 8/8 (`stats-utils`). Code review DONE_WITH_CONCERNS → H1 + M1 + M2 đã đóng; L1/L2/L3 ghi nhận (dedupe timestamp, normalize off `initial_capital` literal, sampling caveat) — tradeoff chấp nhận.

Plan kế tiếp `260630-0031-backtest-mae-mfe-excursion` (blockedBy plan này) giờ mở khóa: FE scatter cần Trades tab + chart wrapper từ phase 3.
