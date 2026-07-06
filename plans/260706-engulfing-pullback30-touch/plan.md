---
title: "Engulfing pullback30 touch strategy variant"
description: ""
status: completed
priority: P2
branch: "develop"
tags: []
blockedBy: []
blocks: []
created: "2026-07-06T09:11:14.101Z"
createdBy: "ck:plan"
source: skill
---

# Engulfing pullback30 touch strategy variant

## Overview

Biến thể của strategy `engulfing`: bỏ qua entry tại close bar engulfing; chờ **bar kế tiếp**; nếu giá **chạm intrabar** mức pullback 30% body của bar engulfing (và không thủng SL) → vào **market tại close bar N+1**. State machine thuần, không đụng broker, bản gốc `engulfing` + golden fixture bất biến.

- Design nguồn: `plans/reports/brainstorm-260706-engulfing-pullback30-touch.md`
- Registry code: `engulfing_pullback30_touch` · class `EngulfingPullback30TouchStrategyService`
- Mode: TDD (test-first mỗi phase)

**Công thức** (`pullback_pct` default 0.30):
- LONG (bullish): `level = close_N − pullback_pct×(close_N − open_N)`; trigger `low(N+1) ≤ level`; skip nếu `low(N+1) ≤ SL`.
- SHORT (bearish): `level = close_N + pullback_pct×(open_N − close_N)`; trigger `high(N+1) ≥ level`; skip nếu `high(N+1) ≥ SL`.
- SL/TP neo theo pattern như gốc (`pattern_low`/`pattern_high`, key-level snapshot tại bar N); entry = close(N+1) → risk co lại; require risk>0.

## Acceptance criteria (toàn plan)

- [x] Bar engulfing đạt filter → **không** phát signal tại close bar đó.
- [x] Bar N+1 chạm mức 30% + không thủng SL → market signal, entry = close(N+1), SL/TP neo pattern.
- [x] Bar N+1 không chạm → không vào, setup reset (chỉ đúng bar kế tiếp).
- [x] Bar N+1 chạm SL → không vào.
- [x] `engulfing_pullback30_touch` có trong `STRATEGY_REGISTRY`; backtest chạy `status == finished`.
- [x] Bản gốc `engulfing` + `engulfing_golden_fixture.json` không đổi; full suite (23 test mới + 21 gốc) + ruff pass. (pyright: import-resolution bị chặn bởi venv môi trường — gốc baseline fail y hệt, không phải lỗi code.)

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [Unit tests + strategy implementation](./phase-01-unit-tests-strategy-implementation.md) | Done |
| 2 | [Registry + backtest integration test](./phase-02-registry-backtest-integration-test.md) | Done |
| 3 | [Verify suite + docs](./phase-03-verify-suite-docs.md) | Done |

## Dependencies

Không có phụ thuộc chéo. Các plan đang mở (r5–r8, notional-net-pnl, backtest-run-name, mae-mfe) không chạm strategy services layer. Bản gốc `engulfing` chỉ đọc lại (dùng chung `detect_engulfing`), không sửa.
