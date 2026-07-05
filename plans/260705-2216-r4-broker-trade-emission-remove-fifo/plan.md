---
title: "R4 — Broker Trade Emission (avg-cost) + Remove FIFO"
description: "PositionAggregate emit TradeClosedEvent lúc reduce/close (average-cost); paper broker forward qua IBrokerPort.subscribe_trades; collector minimal-swap subscribe thay FIFO; xoá LotTrackingHelper + _consumed_pnl. OKX position→Trade defer R8. Kế thừa Model E."
status: pending
priority: P2
branch: develop
tags: [trading-calc, paper-broker, position-aggregate, engine, core-domain, fifo-removal]
blockedBy: []
blocks: [260630-0031-backtest-mae-mfe-excursion]
created: "2026-07-05T22:16:00+07:00"
createdBy: "ck:plan"
source: "plans/reports/brainstorm-260705-2216-r4-broker-trade-emission-remove-fifo.md"
---

# R4 — Broker Trade Emission (avg-cost) + Remove FIFO

Gộp 2 hệ kế toán position (paper broker `PositionAggregate` + collector `LotTrackingHelper` FIFO) về MỘT: `PositionAggregate` phát `TradeClosedEvent` lúc reduce/close (average-cost) → broker forward qua port callback → collector subscribe. Xoá FIFO.

## Context

- Brainstorm (đã duyệt): `plans/reports/brainstorm-260705-2216-r4-broker-trade-emission-remove-fifo.md`
- Roadmap hàng R4: `plans/trading-calulation-fix/roadmap.md` · Model E: `design-execution-metrics-separation.md` · OKX: `okx-broker-verification.md`
- Depends: R3 (done, `260705-2119-r3-commission-abstraction`). Blocks: `260630-0031-backtest-mae-mfe-excursion` (soft — đụng broker SL/TP path + xoá collector FIFO).

## Quyết định khoá

- **Q1** OKX: paper-only; defer OKX position→Trade emission → R8. R4 vẫn fix OKX order mapper `side`.
- **Q2** Option A: extend `PositionAggregate` emit `TradeClosedEvent` + port callback `subscribe_trades`/`unsubscribe_trades`.
- **Q3** Minimal swap: collector chỉ đổi nguồn trade; metrics vẫn build ở `finalize`; rename→`BacktestReportAppService` để R5.

## Phases

| # | Phase | Status | Depends |
|---|---|---|---|
| 01 | [Domain — TradeClosedEvent + PositionAggregate emit](phase-01-domain-trade-closed-event.md) | done | — |
| 02 | [Port + broker transport (paper emit, OKX no-op, mapper side)](phase-02-port-broker-transport.md) | done | 01 |
| 03 | [Collector minimal swap + wiring + delete FIFO](phase-03-collector-swap-remove-fifo.md) | done | 02 |
| 04 | [Regression parity + docs + roadmap status + validation](phase-04-regression-docs-validation.md) | pending | 03 |

## Invariants (mọi phase giữ)

- import-linter 8 contract xanh; no fastapi/bson; `app ◁ engine ◁ core`.
- Parity paper↔backtest (cùng `PaperBrokerAdapter`).
- Commission KHÔNG double-count: `on_fill` debit per-fill; `on_trade` chỉ credit pnl; `Trade.commission` chỉ để ghi doc.
- Thứ tự dispatch: OrderResult (fill callback) TRƯỚC TradeClosedEvent (trade callback) → OrderRecord tồn tại để back-link.
- `direction` map bằng `PositionSide.name` ("LONG"/"SHORT"), KHÔNG `.value` ("long"/"short").

## Validation cuối

`just test` (parity number không đổi cho strategy không scale) · `ruff` · `pyright` · `lint-imports` (8) — tất cả xanh. `git grep LotTrackingHelper|_consumed_pnl` sạch.

## Key risks

- Ripple chữ ký `reduce_quantity`/`add_quantity` → **default arg toàn bộ**.
- `opened_at` wall-clock lọt open_positions → broker inject sim-time `opened_at` khi open.
- FIFO→avg-cost đổi granularity (chỉ khi scale-in/out; strategy hiện không scale → số liệu không đổi).
