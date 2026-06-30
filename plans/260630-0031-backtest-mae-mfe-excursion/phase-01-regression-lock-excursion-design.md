---
phase: 1
title: "Regression lock + excursion design"
status: pending
priority: P1
dependencies: []
---

# Phase 1: Regression lock + excursion design

## Overview

Trước khi đụng engine: viết bộ regression-lock test ĐẦY ĐỦ khóa mọi behavior tính toán hiện có, và viết tests RED cho excursion (bao gồm 2 ca khó nhất mà approach cũ làm sai). Không sửa code production ở phase này — chỉ tests + chốt design timing.

## Requirements

- Functional: bộ test khóa Sharpe/Sortino/total_return/cagr/max_drawdown/FIFO/annualization; tests RED định nghĩa hành vi excursion đúng (LONG/SHORT, same-bar exit, exit-on-extreme-bar, partial consume, r_multiple có/không sl).
- Non-functional: tests độc lập, không phụ thuộc network/DB ngoài fixture có sẵn.

## Architecture — timing design (chốt từ red-team)

**Approach cũ SAI:** `update_excursions` ở `_mtm_on_bar` chạy SAU khi lot exit bị remove → miss bar extreme.

**Approach mới:** cập nhật excursion trong broker `_on_bar_completed` (`paper_broker.py:567`), TRƯỚC khi `_check_sl_tp` consume position — hoặc tại điểm position còn sống và có `event.high`/`event.low`. Excursion bám theo position/lot, không theo curve. Khi exit fill phát sinh → giá trị excursion (đã gồm bar exit) đi kèm vào `Trade`.

Hai ca test quyết định đúng/sai:
1. **Same-bar entry+exit**: lot mở và đóng cùng 1 bar (SL hit ngay) → mae/mfe phải phản ánh high/low bar đó, KHÔNG = 0.
2. **Exit-on-extreme-bar**: bar exit CHÍNH là bar có extreme (TP trigger tại đỉnh) → mfe phải gồm đỉnh đó.

```
_on_bar_completed(event):
  note_excursion(event.high, event.low) cho mọi open position   ← TRƯỚC
  _fill_pending_on_bar
  _check_sl_tp → _fire_synthetic_exit (consume lot, đọc excursion đã có bar này)
```

> Điểm chèn chính xác (broker vs collector) chốt ở Phase 2 sau khi đọc kỹ `_fire_synthetic_exit` → `on_fill` → `_emit_trades` data flow. Phase 1 chỉ khóa hành vi mong muốn bằng test.

## Related Code Files

- Modify (tests only): `tests/backtest_test/engine/test_lot_tracker.py`, `tests/backtest_test/engine/test_result_collector_fifo.py`, `tests/core_test/unit/domain/backtest/test_value_objects_roundtrip.py`.
- Create: `tests/backtest_test/engine/test_result_collector_excursion.py` (ca same-bar, extreme-bar, SHORT, partial).
- Reference (đọc, không sửa): `src/pocketquant/core/infra/brokers/paper/paper_broker.py:566-602`, `src/pocketquant/backtest/engine/result_collector.py:91-122,251-297`, `src/pocketquant/backtest/engine/lot_tracker.py:124-148`.

## TDD: Tests First

**Regression-lock (PHẢI liệt kê đủ — red-team bắt thiếu 2 file):**
- `tests/backtest_test/engine/test_result_collector_mark_to_market.py` (Sharpe/Sortino off `_mtm_curve`).
- `tests/backtest_test/engine/test_result_collector_fifo.py` (FIFO + PnL).
- `tests/backtest_test/engine/test_lot_tracker.py` (feed/consume/flip).
- `tests/backtest_test/domain/test_performance_calculator_annualization.py`.
- `tests/core_test/unit/domain/backtest/test_value_objects_roundtrip.py`.
- `tests/core_test/unit/domain/backtest/test_backtest_value_objects_uuid_id.py` (**red-team thêm** — construct + round-trip Trade).
- `tests/core_test/infra/persistence/backtest/test_trade_repository.py` (**red-team thêm** — Trade save/get round-trip).
- `tests/backtest_test/engine/test_hitnrun2_backtest.py`, `test_engulfing_backtest.py` (end-to-end metrics).

**New tests (RED):**
1. Same-bar entry+exit → mae/mfe phản ánh bar high/low (NOT 0).
2. Exit-on-extreme-bar → mfe gồm extreme của bar exit.
3. LONG & SHORT đúng dấu (mfe≥0, mae≤0 theo direction).
4. Partial consume (scale-out) → mỗi phần kế thừa excursion lot.
5. r_multiple = pnl/risk khi có sl; None khi sl=None hoặc risk=0.
6. Trade round-trip giữ 3 field; doc cũ thiếu → None, không raise.

## Implementation Steps

1. Chạy toàn bộ regression-lock hiện có → xác nhận GREEN baseline.
2. Viết new tests excursion (RED) — đặc biệt ca #1, #2.
3. Đọc kỹ broker exit flow để chốt điểm chèn `note_excursion` (ghi vào phase 2).

## Success Criteria

- [ ] Regression-lock 8 file chạy GREEN (baseline trước khi sửa).
- [ ] New excursion tests tồn tại và RED (chưa có implementation).
- [ ] Điểm chèn `note_excursion` được chốt bằng văn bản trong Phase 2.

## Risk Assessment

- **Test giả-pass**: nếu fixture tự tạo bar không mô phỏng đúng same-bar exit → test xanh giả. Ca #1/#2 phải dùng đúng đường broker `_on_bar_completed`, không bypass.
- **Đọc nhầm data flow**: dành thời gian phase này trace `_fire_synthetic_exit`→`on_fill`→`_emit_trades` trước khi code phase 2.
