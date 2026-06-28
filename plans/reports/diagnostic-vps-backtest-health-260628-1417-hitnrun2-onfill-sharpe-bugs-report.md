# Diagnostic — Live VPS backtest health + hitnrun2 audit

**Scope:** SSH read-only vào prod VPS (`root@207.148.79.60`) + audit code engine backtest. Không ghi gì lên prod. Tập trung `hitnrun2` + pipeline.

## TL;DR

| Câu hỏi | Trả lời |
|---|---|
| Backtest "còn chạy & hoạt động" không? | **Có, về mặt cơ chế.** Worker sống, queue sạch, app healthy 7 ngày, backtest chạy end-to-end và persist. |
| Có bug / thiếu sót không? | **Có — 2 bug thật làm KẾT QUẢ backtest sai**, dù pipeline không crash. |

Mấu chốt: pipeline "xanh" nhưng output **vô nghĩa về mặt tài chính**. Hệ thống báo "completed" trong khi strategy thực ra bị đóng băng sau trade đầu tiên và risk metrics là rác.

## Live VPS state (read-only)

- **Containers:** app / web / mongodb / redis / portainer — tất cả `healthy`. App `Up 7 days`, `RestartCount=0`, started `2026-06-20`.
- **Health endpoint:** `{"status":"healthy", db latency 1ms, redis 0ms, environment: production}`.
- **`ENABLE_JOBS=true`** → backtest worker được start ở boot (dòng log `backtest_worker.started` đã bị rotate mất — log driver `json-file` 3×10m, hiện chỉ còn từ 2026-06-27 — KHÔNG phải worker chết).
- **Queue `backtest_requests`:** 2 docs, cả 2 `done` (1 single, 1 subscription). Không có doc kẹt `pending`/`running` → worker đã drain sạch, `reclaim_stale_running` không phải làm gì.
- **`backtest_runs` (cache):** 8 docs, tất cả `completed`. Bản mới nhất `completed_at = 2026-06-13`.
- **Subscriptions:** 1 — `hitnrun2 / BTCUSDT:BINANCE / 1m`.
- **Bars:** 1.44M tổng, riêng `BTCUSDT:BINANCE 1m` = **1,117,039 bar** (2024-05-08 → 2026-06-28). Dữ liệu KHÔNG thiếu.

**Kết luận sống/chết:** worker + queue + persistence đều hoạt động. Không có gì "đang treo".

## Bug #1 — `strategy.on_fill` không bao giờ được gọi → tối đa 1 trade mỗi backtest (NGHIÊM TRỌNG)

**Bằng chứng từ prod:** mọi `backtest_runs` có `total_trades ∈ {0, 1}`. Run 70 ngày trên 1m (≈100k bar) chỉ ra **1 trade**. Với chiến lược breakout SL 1% / TP 2% trên BTC, con số đúng phải là hàng trăm.

**Root cause (code):**
- `hitnrun2` chỉ mở 1 vị thế tại một thời điểm: `on_bar` early-return khi `self._open_direction is not None` (`hitnrun2.py:93-94`).
- `_open_direction` chỉ được reset về `None` trong **`HitNRun2Strategy.on_fill`** (`hitnrun2.py:114-124`), khi broker SL/TP auto-fill đóng vị thế.
- Nhưng `strategy.on_fill` có **0 call-site** trong toàn bộ `src/` (grep `\.on_fill(` → chỉ ra định nghĩa ở `interfaces.py:62` + `hitnrun2.py:114`, không ai gọi).
- `PaperBroker._notify_callbacks` (`paper_broker.py:527`) chỉ feed các callback đăng ký qua `subscribe_order_updates` → trong backtest chỉ có `BacktestResultCollector.on_fill` (signature `(result)`, khác hẳn signature strategy `(order, fill_price)`). Không có cầu nối nào từ fill của broker về `strategy.on_fill`.

**Hệ quả:** Sau trade đầu, vị thế bị SL/TP đóng trong sổ broker + collector (nên vẫn ra 1 Trade với pnl), nhưng strategy không hề biết → `_open_direction` kẹt mãi → mọi tín hiệu sau đó bị chặn. Backtest "completed" nhưng thực chất test đúng 1 lệnh.

**Đây là functional bug, không phải vấn đề tham số.** Nó vô hiệu hoá toàn bộ giá trị của backtest.

## Bug #2 — Sharpe/Sortino annualization sai → risk metrics là rác (NGHIÊM TRỌNG)

**Bằng chứng từ prod:** `sharpe = -227.7`, `-30.8`, `-19.3`, `-15.7` trên các run chỉ có 1 trade. Sharpe ngoài khoảng ±5 gần như luôn là lỗi tính.

**Root cause (code):**
- `PerformanceCalculator.sharpe_ratio` (`performance_calculator.py:75-78`) annualize bằng `mean_return * 365` và `std * sqrt(365)` — giả định mỗi điểm equity_curve cách nhau **đúng 1 ngày**.
- Thực tế `equity_curve` được sample **theo sự kiện**, không theo thời gian: `BacktestResultCollector._record_equity_point` chỉ append khi có fill đóng lệnh hoặc open thuần (`result_collector.py:113, 272`). Khoảng cách giữa các điểm là bất kỳ (vài phút tới vài ngày), và do Bug #1 nên thường chỉ có **3 điểm** cho cả backtest.
- Annualize một chuỗi return sample không đều bằng hằng số 365/√365 → ra số vô nghĩa. `max_drawdown` (không annualize) thì vẫn đúng.

**Lưu ý phụ thuộc:** Bug #2 còn bị Bug #1 khuếch đại (quá ít điểm). Sửa #1 sẽ làm equity_curve dày hơn nhưng **vẫn sai** vì gốc rễ là sample theo sự kiện chứ không theo bar/ngày. Hai bug độc lập, phải sửa cả hai.

## Quan sát phụ (không phải bug chặn)

- **Subscription cache stale:** `backtest_runs` của subscription cập nhật lần cuối 2026-06-13. Không có job nào tự enqueue subscription backtest — chỉ chạy khi FE gọi `POST /strategies/{code}/run-all-backtests`. Nếu bạn kỳ vọng cache tự refresh định kỳ thì đó là **thiếu sót thiết kế**; nếu chấp nhận trigger thủ công thì đúng ý đồ hiện tại.
- **Observability gap:** doc `backtest_runs` có `started_at/completed_at` nhưng `last_run_at`/`updated_at` để `undefined` (schema không nhất quán giữa các doc cũ/mới). Khó audit "chạy lần cuối khi nào" bằng query.
- **Log retention ngắn:** 3×10m json-file → mất lịch sử >~1 ngày. Không debug được sự cố cũ. Cân nhắc tăng `max-size`/`max-file` hoặc ship log ra ngoài.
- **`win_rate` hiển thị khó hiểu:** 1 trade thua → `win_rate=0`, 1 trade thắng → `win_rate=1`. Đúng công thức nhưng vô nghĩa thống kê với n=1 (do Bug #1).

## Quy kết root cause: strategy hay app code?

**Cả 2 bug đều ở APP/ENGINE main code. `hitnrun2` sạch.**

### Bug #1 → app/engine (`StrategyAppService`)
- `IStrategy` interface (`interfaces.py:10-19`) cam kết: *"StrategyAppService calls hooks ... on_fill() - Called when orders are filled"*; docstring `on_fill`: *"Override to update internal state after fills"*.
- `hitnrun2` override `on_fill` **đúng theo contract** — reset `_open_direction`. Strategy viết đúng.
- `StrategyAppService._on_bar_completed` (`strategy_app_service.py:214-240`) chỉ gọi `on_bar` + `_process_signal`, **không bao giờ gọi `on_fill`**.
- `subscribe_order_updates` có **1 call-site duy nhất**: `backtest_app_service.py:90` đăng ký `collector.on_fill`. Không có cầu nối fill → `strategy.on_fill` ở cả live lẫn backtest path.
- → Orchestrator bỏ sót hook đã cam kết. **App bug.** Ảnh hưởng mọi strategy dùng `on_fill`, không riêng hitnrun2.

### Bug #2 → app (`PerformanceCalculator` + `result_collector`)
- `sharpe_ratio`/`sortino_ratio` annualize hằng số 365; `result_collector` sample equity_curve theo sự kiện. Cả 2 là backtest engine dùng chung, hitnrun2 không đụng tới. **App bug, độc lập strategy.**

## Bối cảnh đã chốt với user (2026-06-28)
- **Live trading KHÔNG chạy** — mới chỉ backtest. Bug #1 sẽ disqualify live (hang) → **được phép sửa**.
- Kiến trúc 5 container (`app` + `web` + `mongodb` + `redis` + `portainer`) là ĐÚNG; code 1-package/1-process = 1 container `app`. Không cần đổi.
- `backtest_runs`=8 là lịch sử test thủ công (7 single keyed by run_id + 1 subscription cache), không phải bug.

## Đề xuất hướng xử lý (chưa thực thi — cần bạn duyệt)

1. **Bug #1 — wire `strategy.on_fill`:** trong path inject backtest (`backtest_dispatch` / `strategy_app_service.inject_prepared_strategy`), đăng ký một callback vào `broker.subscribe_order_updates` để bridge fill → `strategy.on_fill(order, fill_price)`. Phải đảm bảo cùng cơ chế hoạt động cho cả live (reconcile) lẫn backtest, nếu không live strategy cũng dính cùng lỗi đóng băng.
   - **Cần kiểm tra thêm:** live trading có dính cùng bug không? Reconcile loop có gọi `on_fill` không? (Grep cho thấy KHÔNG — đáng lo nếu đã/đang chạy live.)
2. **Bug #2 — sửa annualization:** hoặc (a) sample equity_curve theo bar đều đặn rồi annualize theo số bar/năm của interval, hoặc (b) tính Sharpe theo per-trade return (không annualize, hoặc annualize theo số trade/năm thực tế). Cần bạn chọn định nghĩa Sharpe mong muốn.
3. (Tuỳ chọn) chuẩn hoá schema timestamp + tăng log retention.

## Unresolved questions

1. **Live trading có đang chạy thật không, và có dính Bug #1 không?** Nếu `on_fill` cũng không được gọi ở path live thì mọi live strategy cũng đóng băng sau 1 lệnh — mức độ nghiêm trọng tăng vọt. Cần xác nhận trước khi quyết ưu tiên.
2. **Định nghĩa Sharpe bạn muốn** (per-bar annualized vs per-trade) — quyết định cách sửa Bug #2.
3. **Subscription cache có cần tự refresh định kỳ không**, hay giữ trigger thủ công qua run-all?
4. Bước tiếp theo: muốn tôi mở `/ck:debug` để sửa 2 bug này, hay chỉ dừng ở báo cáo?
