# Phase 05 — Engine DTO audit deliverable + docstrings + docs + roadmap status

**Priority:** P2 · **Status:** pending · **Depends:** P1–P4
**Context:** [plan](plan.md) · [roadmap](../roadmap.md) (hàng R1)

## Mục tiêu
Chốt deliverable "audit engine DTO vs domain VO", đồng bộ docstring/docs với cấu trúc mới, tick trạng thái R1. Gần-zero code, chủ yếu prose + xác nhận.

## Deliverable: Engine DTO audit (kết quả)
Đã quét `engine/` — DTO duy nhất:
- `engine/market_data/sync_dtos.py`: `SyncSymbolCommand`, `BulkSyncCommand`, `SyncResponse`
- `engine/market_data/tracked_symbols_backfill.py`: `BackfillTrackedSymbolCommand`

**Kết luận:** đều là app/command–response DTO (API-shaped, mang default/validation), **không** phải domain VO đặt nhầm tầng. `Trade`/`Fill`/`EquityPoint` (VO thật) vốn đã ở `core.domain`. → **Không move gì trong R1.** Ghi kết luận này vào doc (không tạo file mới nếu `docs/` đã có chỗ; nếu không, thêm 1 mục ngắn trong `docs/system-architecture.md`).

## Files
**Modify**
- `core/domain/backtest/value_objects.py` — docstring phản ánh nội dung còn lại (`OpenLot` [+ `Order` đã rời sang order]). Không banner, AS-IS.
- `core/domain/backtest/__init__.py` — docstring gọn: "persisted backtest-run VO: BacktestResult, OpenLot, BacktestConfig".
- `core/domain/trading/__init__.py` — docstring: "universal trading contract + metrics (source-agnostic): Trade, Fill, EquityPoint, PerformanceMetrics, PerformanceCalculatorDomainService, trade_stats".
- `docs/system-architecture.md` — thêm `core.domain.trading` vào bản đồ domain packages + 1 dòng audit kết luận. Nếu doc liệt kê "Where does X live" → cập nhật Trade/Metrics/BacktestConfig/OrderRecord.
- `docs/code-standards.md` — nếu section "Class Naming by Layer" liệt kê VO/domain-service, thêm trading package.
- `plans/trading-calulation-fix/roadmap.md` — hàng R1 → done; ghi chú "metrics_builder.py đã xoá ở R1 → R5 bỏ mục đó"; giải 2 unresolved của R1 (Order rename = đã làm; engine DTO audit = không có VO nhầm chỗ).

## Steps
1. Cập nhật 3 docstring package.
2. Cập nhật `docs/system-architecture.md` (+ `code-standards.md` nếu cần) — delegate `docs-manager` nếu docs dài.
3. Cập nhật roadmap R1 status + unresolved.
4. Gates cuối: `ruff && pyright && lint-imports && just test` (toàn xanh).
5. `/ck:journal` — journal ngắn cho R1.

## Success
- Docstrings + docs khớp cấu trúc mới; roadmap R1 = done, ghi chú R5-carryover.
- Audit engine DTO có kết luận thành văn.
- Toàn bộ gates xanh — R1 khép lại, sẵn sàng R2 (gộp `backtest/`→`engine/backtest/`).

## Unresolved (chuyển cho R sau)
- `Trade.run_id`/`strategy_code` là FK backtest — live/forward map sang gì (R4/R5).
- `.build` signature source-agnostic hoá — R5.
