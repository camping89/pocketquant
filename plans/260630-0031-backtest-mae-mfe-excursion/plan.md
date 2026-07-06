---
title: "Backtest MAE/MFE Excursion Track"
description: "MAE/MFE/R-multiple per trade. Tách khỏi workbench do đụng engine + timing redesign. Track excursion TRONG broker SL/TP path (nơi có sẵn bar high/low), không phải _mtm_on_bar. TDD."
status: pending
priority: P3
branch: "develop"
tags: [backtest, engine, statistics, tdd]
blockedBy: [archive/trading-calulation-fix/r2-engine-restructure, archive/260705-2119-r3-commission-abstraction, archive/260705-2216-r4-broker-trade-emission-remove-fifo, archive/260706-0004-r5-report-service-gut-equity]  # TẤT CẢ blocker DONE + archived (initiative trading-calulation-fix đóng). Design docs: `../archive/trading-calulation-fix/design-execution-metrics-separation.md` (Model E). Approach cũ dựa `_lot_tracker.lots` + `_consumed_pnl` đã bị R4 xoá; excursion phải REDESIGN track trên `PositionAggregate` (broker SL/TP path `_fire_synthetic_exit`/`_check_sl_tp`) + đọc từ `TradeClosedEvent`, KHÔNG còn lot_tracker. Soft: R5 rename collector→BacktestReportAppService + gut equity.
blocks: []
created: "2026-06-30T01:56:28.266Z"
createdBy: "ck:plan"
source: skill
---

# Backtest MAE/MFE Excursion Track

## Overview

Tính **MAE** (Maximum Adverse Excursion), **MFE** (Maximum Favorable Excursion), **R-multiple** cho mỗi `Trade`. Tách khỏi plan workbench (`260630-0031-backtest-research-workbench`) vì đụng engine (`result_collector`, `lot_tracker`, broker) + cần redesign timing — rủi ro cao hơn hẳn phần FE.

**Lý do tách + redesign (từ red-team):** approach ban đầu (gọi `update_excursions` trong `_mtm_on_bar`) **SAI hệ thống**. Đã verify bằng code: broker subscribe `BarCompletedEvent` LAST (`paper_broker.py:573`), xử lý SL/TP exit + consume+remove lot trong `_on_bar_completed` (`:586-592`), rồi `_mtm_on_bar` mới chạy (`:596-597`). Nên khi quét `_lot_tracker.lots` ở cuối bar, lot vừa exit đã bị remove (`lot_tracker.py:124-129`) → **miss đúng bar chứa extreme** (bar trigger SL/TP); same-bar entry+exit → mae/mfe=0 sai.

**Redesign:** track excursion NGAY trong broker SL/TP path nơi `event.high`/`event.low` có sẵn (`paper_broker.py:586`), trước khi lot bị consume — hoặc cập nhật excursion trên position TRƯỚC `_check_sl_tp`, đảm bảo bar exit được tính.

**FORWARD-ONLY:** run mới sau deploy mới có; run cũ = null (không backfill). FE hiển thị "—".

Brainstorm: [`../archive/260630-0031-backtest-research-workbench/reports/brainstorm-260630-0031-backtest-research-workbench-report.md`](../archive/260630-0031-backtest-research-workbench/reports/brainstorm-260630-0031-backtest-research-workbench-report.md)

## Decisions

- **Timing redesign**: excursion track ở broker SL/TP path (có `event.high/low`), KHÔNG ở `_mtm_on_bar` (chạy sau khi lot remove).
- **Đơn vị**: lưu PnL excursion ($): `mfe = (max_fav_price − entry)×qty` (LONG, ≥0), `mae = (min_adv_price − entry)×qty` (≤0). `r_multiple = pnl / (abs(entry−sl)×qty)`, None nếu thiếu sl.
- **DTO**: `list_trades` (`backtest_query_service.py`) PHẢI serialize 3 field mới — đây là read path FE thực dùng.
- **Failed run**: null-out mae/mfe/r_multiple (excursion dở dang không tin cậy).
- **FE charting**: scatter dùng **echarts** (đã cài `^6.0.0`), KHÔNG uPlot/visx.

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [Regression lock + excursion design](./phase-01-regression-lock-excursion-design.md) | Pending |
| 2 | [Implement broker-path excursion](./phase-02-implement-broker-path-excursion.md) | Pending |
| 3 | [FE MAE-MFE scatter + columns](./phase-03-fe-mae-mfe-scatter-columns.md) | Pending |

## Dependencies

- **blockedBy**: `260630-0031-backtest-research-workbench` — Phase 3 (FE scatter/columns) cần workbench dashboard (Trades tab + PositionsTable + echarts wrapper) tồn tại trước. Phase 1+2 (engine) độc lập, làm trước được.

## Acceptance criteria

- [ ] Regression-lock: Sharpe/Sortino/total_return/cagr/max_drawdown/FIFO/annualization KHÔNG đổi.
- [ ] LONG & SHORT excursion đúng dấu; **same-bar entry+exit** + **exit-on-extreme-bar** tính đúng (test khóa).
- [ ] `r_multiple` đúng khi có sl, None khi thiếu.
- [ ] `list_trades` API trả mae/mfe/r_multiple (None cho run cũ, không bỏ key).
- [ ] Failed run → 3 field = null.
- [ ] FE scatter render (run mới); run cũ toàn null → không crash, scatter rỗng.

## Constraints (CLAUDE.md)

- Repo chỉ ở core; engine ở backtest; mọi await là preemption point; UUIDv7.
- Thêm field domain `Trade` → append SAU `duration_seconds` (dataclass non-default theo sau default → import error nếu chèn giữa).
