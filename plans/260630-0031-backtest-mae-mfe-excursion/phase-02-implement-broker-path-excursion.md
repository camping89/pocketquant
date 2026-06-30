---
phase: 2
title: "Implement broker-path excursion"
status: pending
priority: P1
dependencies: [1]
---

# Phase 2: Implement broker-path excursion

## Overview

Implement excursion tracking theo design Phase 1: cập nhật max favorable/adverse price cho mỗi open lot/position TRONG đường broker `_on_bar_completed` (trước khi SL/TP consume), gắn mae/mfe/r_multiple vào `Trade` khi exit, serialize qua read path. Làm tests Phase 1 GREEN mà không regress.

## Requirements

- Functional: excursion đúng cho mọi ca test Phase 1 (same-bar, extreme-bar, LONG/SHORT, partial); `Trade.mae/mfe/r_multiple`; `list_trades` serialize 3 field; failed run → null.
- Non-functional: regression-lock GREEN; import-linter pass; mọi await preemption-point an toàn.

## Architecture

**Điểm chèn (chốt sau Phase 1):** trong `paper_broker._on_bar_completed` (`paper_broker.py:575`, sau set `_current_prices`, TRƯỚC `_fill_pending_on_bar`/`_check_sl_tp`), gọi cập nhật excursion cho mọi open position theo `event.high`/`event.low`. Excursion bám position; khi `_fire_synthetic_exit` → `on_fill` → `lot_tracker.feed` consume → `_emit_trades` đọc excursion từ lot và set vào Trade.

**Truyền excursion từ broker → collector:** broker theo dõi excursion trên position; lot_tracker.OpenLot mang `max_favorable_price`/`max_adverse_price` (init=`entry_price`). Cơ chế đồng bộ chốt Phase 1 — hoặc (a) collector cũng nhận bar event để note lot trước broker (subscribe TRƯỚC broker), hoặc (b) broker đính excursion vào exit fill result. Ưu tiên (a) nếu giữ được separation; (b) nếu cần đúng same-bar.

**Tính giá trị** (`_emit_trades`, `result_collector.py:251`):
- `mfe = (lot.max_favorable_price − entry_price) × qty_closed` (LONG); SHORT đảo.
- `mae = (lot.max_adverse_price − entry_price) × qty_closed` (LONG); SHORT đảo.
- `risk = abs(entry_price − sl_price) × qty_closed`; `r_multiple = pnl/risk` nếu `sl_price and risk>0` else None.

## Related Code Files

- Modify: `src/pocketquant/backtest/engine/lot_tracker.py` — `OpenLot.max_favorable_price`/`max_adverse_price` + `note_excursion(high, low)`.
- Modify: `src/pocketquant/core/domain/backtest/value_objects.py` — `Trade`: thêm `mae`/`mfe`/`r_multiple: float | None = None` **APPEND SAU `duration_seconds`** (dataclass field-order); `to_mongo` ghi; `from_mongo` `.get(...,None)`.
- Modify: `src/pocketquant/backtest/engine/result_collector.py` — nhận bar excursion (subscribe hoặc method); `_emit_trades` tính + set 3 field.
- Modify: `src/pocketquant/core/infra/brokers/paper/paper_broker.py` — note excursion trước SL/TP consume (nếu chọn approach broker-side).
- Modify: `src/pocketquant/backtest/engine/backtest_app_service.py` — wiring subscribe excursion handler TRƯỚC broker nếu approach (a).
- Modify: `src/pocketquant/backtest/backtest_query_service.py` — `list_trades` thêm `"mae"/"mfe"/"r_multiple"` (**red-team C2: read path FE thực dùng**).
- Modify: failed path `backtest_app_service.py:160-169` — null-out 3 field trên Trade khi `status=="failed"` (**red-team: tránh giá trị rác**).

## TDD: Tests First (đã viết Phase 1 — giờ làm GREEN)

Chạy regression-lock (giữ GREEN) + new excursion tests (RED→GREEN). Thêm:
- Integration `GET /{run_id}/trades` assert 3 field xuất hiện (số cho run mới, None cho trade thiếu) — khóa C2.
- Failed-run test: trade của run failed → mae/mfe/r_multiple = None.

## Implementation Steps

1. `lot_tracker.py`: thêm 2 field + `note_excursion`.
2. `value_objects.py Trade`: append 3 field sau `duration_seconds` + to/from_mongo `.get`.
3. Wiring excursion theo approach Phase 1 (broker note trước consume / collector subscribe trước broker).
4. `_emit_trades`: tính mae/mfe/r_multiple, set vào Trade.
5. `backtest_query_service.py list_trades`: serialize 3 field.
6. Failed path: null-out 3 field khi failed.
7. Regression-lock GREEN + excursion GREEN + integration trades GREEN → `just lint && just types` → import-linter.

## Success Criteria

- [ ] Regression-lock 8 file GREEN không đổi.
- [ ] Same-bar + extreme-bar excursion đúng (không 0, gồm bar exit).
- [ ] `GET /{run_id}/trades` trả mae/mfe/r_multiple.
- [ ] Failed run → 3 field null.
- [ ] `just test && just lint && just types` + import-linter pass.

## Risk Assessment

- **Same-bar đúng nhưng regress khác**: nếu chèn excursion làm đổi thứ tự event → Sharpe/MTM lệch. Regression-lock chặn; chạy sau mỗi bước.
- **Approach (a) subscribe-before-broker**: thêm handler subscribe TRƯỚC `broker.connect` — cần verify thứ tự ở `backtest_dispatch.py`/sandbox (broker connect tại inject). Nếu khó, dùng (b) broker đính excursion vào fill result.
- **Field-order import error**: append sau cùng — test import bắt ngay.
- **list_trades quên field**: integration test C2 chặn.
