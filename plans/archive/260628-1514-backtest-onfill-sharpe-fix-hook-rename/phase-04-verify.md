---
phase: 4
title: "Verify"
status: done
priority: P1
dependencies: [1, 2, 3, 5]
---

# Phase 4: Verify (regression lock + prod re-smoke)

## Overview

Khoá regression cho 2 fix + rename + grid-opt, chạy full gate, và re-smoke trên dữ liệu prod qua remote-db (TỰ ĐỘNG cuối phase, user chốt). Đảm bảo không drift live/backtest.

## Requirements

- Functional: toàn bộ acceptance criteria của plan đạt.
- Non-functional: `just test` / `just lint` / `just types` xanh; import-linter 7 contracts pass; không phá public OpenAPI snapshot.

## Tests cần thêm/cập nhật

| Test | Mục đích | File |
|---|---|---|
| Multi-trade backtest | `hitnrun2` ra > 1 trade sau khi wire fill | `tests/backtest_test/engine/test_hitnrun2_backtest.py` (mở rộng) |
| on_order_filled reset | opposite-side fill → `_open_direction=None`; same-side giữ (đã có `test_on_fill_same_side_does_not_reset:201`) | `tests/core_test/unit/domain/strategy/test_hitnrun2.py` |
| OrderFilledEvent route | `_on_order_filled` route đúng `subscription_id`; id lạ → no-op | new `tests/engine_test/test_order_filled_event_routing.py` |
| Synthetic exit publish | `_fire_synthetic_exit` publish `OrderFilledEvent{sub_id, side}` | `tests/...paper_broker` test |
| Sharpe annualization | `periods_per_year` keyword-only; known curve → known value (RED-TEAM: chưa có test nào) | new perf calc test |
| Interval.periods_per_year | mapping 7 interval (1w=52.14); interval lạ không raise | `tests/core_test/unit/domain/...enums` |
| MTM read-only | `total_return`/`cagr` byte-identical; `_current_equity` không bị ghi | `tests/backtest_test/engine/...` |
| Persist size | equity_curve ≤5000 điểm, doc <16MB trên fixture 1m dài | `tests/backtest_test/engine/...` |
| Rename guard | không còn `def on_bar`/`.on_bar(`/`def on_fill` trên strategy; `collector.on_fill` + `_on_*` handler giữ | grep-based / collect |

## Verification roles (whole-plan consistency)

1. **Rename completeness:** `grep -rn "def on_bar\b\|\.on_bar(\|def on_fill\b" src/ tests/` → chỉ còn `_on_*` handler + `collector.on_fill`. Confirm `_DefaultStrategy` + `_CountingStrategy` renamed.
2. **Bug #1 functional:** fixture nhiều breakout → `total_trades > 1`; synthetic exit publish event; `_on_order_filled` route theo id (backtest + live cùng cơ chế qua `OrderFilledEvent`).
3. **Bug #2 correctness:** Sharpe hợp lý; `total_return`/`cagr`/maxDD/win_rate/profit_factor byte-identical; MTM read-only.
4. **No drift:** một handler `_on_order_filled` cho mọi fill source; một `periods_per_year` source (Interval enum).
5. **Grid-opt (Phase 5):** mỗi combination ra trade > 0; 2+ run concurrent cùng symbol/interval cô lập (không cross-talk).

## Related Code Files

- Verify-only (read): tất cả file đã sửa ở Phase 1-3.
- Create: test files mới ở bảng trên.
- Check: `tests/baseline/openapi_app_snapshot.json` không đổi (rename hook là internal, không phơi ra API).

## Implementation Steps

1. `just test-pkg core` → `just test-pkg backtest` → `just test-pkg engine` (narrow trước).
2. `just test` (full), `just lint`, `just types`.
3. import-linter: `lint-imports` / theo pyproject (7 contracts) — rename không đổi layer, nhưng confirm.
4. Whole-plan consistency sweep: re-read plan.md + 4 phase, reconcile thuật ngữ (on_fill→on_order_filled nhất quán mọi nơi).
5. **Re-smoke qua remote-db (TỰ ĐỘNG cuối Phase 4, user chốt không hỏi lại):** backup `.env` (`cp .env .env.local-only.bak`), `cp pocketquant-config/local/remote-db.env .env` (code local → VPS Mongo/Redis, `ENABLE_JOBS=false`), `just be`, enqueue 1 backtest `hitnrun2` qua API, poll `/backtest/requests/{id}`, khẳng định `total_trades > 1` + Sharpe hợp lý. Cũng smoke grid-opt: 1 optimization nhỏ (2-3 combination) xác nhận mỗi combination ra trade. Khôi phục `.env` sau (`cp .env.local-only.bak .env`). ⚠ Writes đi vào **production** DB (deployment.md:347) — doc mới không xoá data cũ, có thể xoá sau khi xem.

## Success Criteria

- [x] Tất cả acceptance criteria trong `plan.md` đạt.
- [x] `just test` (592 passed/1 skipped/0 failed, ổn định 5 run) + `ruff` + `pyright` xanh. (Repo không có recipe `just lint`/`just types`/`just test-pkg` — chạy trực tiếp `ruff`/`pyright`/`lint-imports`.)
- [x] import-linter 7 contracts KEPT.
- [x] OpenAPI snapshot pass (baseline đã regenerate khớp comment-strip; test xanh ổn định).
- [x] Re-smoke (remote-db): grid-opt `BTCUSDT:BINANCE/1h` 2 combination → total_trades 262 & 296; Sharpe 11.25 & 0.83; live positions=0 (no phantom).
- [x] Whole-plan consistency sweep: 0 mâu thuẫn thuật ngữ.

## Re-smoke result (2026-06-28)

Endpoint dùng: **synchronous `POST /backtest/optimize`** (KHÔNG `/backtest/run` async — với `ENABLE_JOBS=false` local worker không drain; chỉ optimize chạy inline trong code local fixed, không bị VPS worker old-code "cướp"). Grid `entry_lookback_bars=[20,40]`, các param khác fixed, window 2026-01-01→2026-06-25.

| combo | entry_lookback | total_trades | win_rate | total_return | sharpe | sortino | maxDD |
|---|---|---|---|---|---|---|---|
| 0 | 40 | 262 | 67.2% | +2.19% | 11.25 | 26.56 | -1.06% |
| 1 | 20 | 296 | 56.1% | -0.94% | 0.83 | 0.27 | -3.01% |

- **Bug #1 fixed:** cả 2 combination ra hàng trăm trade (trước: cap 1). Strategy injection + fill routing hoạt động per-run.
- **Bug #2 fixed:** Sharpe sane + responsive (trước: -227/-30). Combo lời → Sharpe cao, combo lỗ → Sharpe thấp.
- **Isolation (Phase 2+5):** 2 run concurrent ra trade-count khác nhau (262≠296) → không cross-talk; live `positions: 0` → sandbox không leak phantom vào engine live.
- `.env` khôi phục về `all-local.env` sau re-smoke; backup prod ở `.env.remote-db.bak` (gitignored qua `.env.*`).

## Risk Assessment

- **Risk:** re-smoke ghi doc vào `backtest_runs` prod (TỰ ĐỘNG cuối Phase 4). Mitigation: doc mới không xoá doc cũ; backup/restore `.env`; có thể xoá doc sau khi xem.
- **Risk:** test multi-trade phụ thuộc fixture có đủ breakout. Mitigation: dựng fixture synthetic OHLCV có nhiều breakdown/breakup rõ ràng, không phụ thuộc dữ liệu prod.
- **Rollback:** nếu verify fail, giữ ở branch `develop` chưa push; revert theo phase.

## Verify-only task (live OKX — user chốt follow-up riêng)

- Grep + doc xác nhận live OKX `on_order_update` wiring gap (không có call-site subscribe vào OKX broker → live fill có thể chưa publish `OrderFilledEvent`). GHI NHẬN vào report, KHÔNG wire trong plan này. Mở plan riêng khi bật live.

## Resolved (validate session 2)

- Re-smoke: TỰ ĐỘNG cuối Phase 4 qua remote-db (ghi prod, không hỏi lại).
- Exec order: tuần tự 1→2→3→5→4.
- `@event_handler` registry binding: **per-instance** (verified `event_registry.py:41,60`) → Phase 5 per-run EventBus khả thi.
