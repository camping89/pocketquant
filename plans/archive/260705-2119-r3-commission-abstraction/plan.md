---
title: "R3 — Commission Abstraction"
description: "CommissionModel + PercentageCommissionModel(bps) → OrderResult.commission; paper broker trừ balance mọi fill (entry+exit); collector single-source; commission_bps→broker; Settings.paper_commission_percent; OKX map fee. Kế thừa Model E."
status: completed
priority: P2
branch: "develop"
tags: [trading-calc, commission, paper-broker, okx, engine, core-domain]
blockedBy: []
blocks: [260630-0031-backtest-mae-mfe-excursion]
created: "2026-07-05T21:19:00+07:00"
createdBy: "ck:plan"
source: skill
---

# R3 — Commission Abstraction

## Overview

Hợp nhất commission về broker: `CommissionModel` (pure, `core.domain.trading`) → `OrderResult.commission`; `PaperBrokerAdapter` tính + trừ `_balance` **mọi fill** (entry + exit) + gate `_can_afford`; collector đọc `result.commission` (single-source, dọn cho R5); rewire `BacktestConfig.commission_bps` + `Settings.paper_commission_percent` vào broker; OKX map `abs(fee)`. R1+R2 done. **Divergence 2-ledger fix đầy đủ ở R5** — R3 đặt nền.

Design chốt (4 quyết định + worked example + blast radius): [`../trading-calulation-fix/r3-commission-abstraction.md`](../trading-calulation-fix/r3-commission-abstraction.md)
Roadmap: [`../trading-calulation-fix/roadmap.md`](../trading-calulation-fix/roadmap.md) · Model E: [`../trading-calulation-fix/design-execution-metrics-separation.md`](../trading-calulation-fix/design-execution-metrics-separation.md)

## Invariants (giữ suốt R3)

- **Parity**: backtest & paper-forward cùng 1 PaperBroker — commission áp cùng chỗ, không tách.
- **import-linter 8/8 xanh**: `CommissionModel` ở `core.domain.trading` (neutral) — infra broker + (tương lai R6) position domain import sạch, không contract mới.
- **Metrics R3 không đổi số**: collector đọc `result.commission` = đúng giá trị formula cũ → persisted metrics bất biến; chỉ broker `_balance` giờ mới trừ commission.
- **YAGNI**: KHÔNG funding-fee sim, KHÔNG SlippageModel, KHÔNG est_entry_commission (R6), KHÔNG maker/taker.

## Phases

| # | Phase | Depends | Status |
|---|-------|---------|--------|
| 01 | [CommissionModel + OrderResult.commission](phase-01-commission-model-order-result.md) | — | completed |
| 02 | [PaperBroker: compute+deduct 4 fill path + _can_afford](phase-02-paper-broker-commission.md) | 01 | completed |
| 03 | [Collector single-source + wiring (config/Settings→broker)](phase-03-collector-and-wiring.md) | 02 | completed |
| 04 | [OKX map abs(fee) → OrderResult.commission](phase-04-okx-fee-mapping.md) | 01 | completed |
| 05 | [Tests + verify (just test/ruff/pyright/lint-imports)](phase-05-tests-and-verify.md) | 01-04 | completed |

```
P01 ─┬─► P02 ─► P03 ─┐
     └─► P04 ────────┴─► P05
```
P04 song song được với P02/P03 (chỉ cần P01).

## Success criteria (tổng)

- `CommissionModel`+`PercentageCommissionModel` ở `core.domain.trading`; export `__init__`.
- `OrderResult.commission` set trên **cả 4** fill path; `_balance` trừ entry+exit commission; `_can_afford` gồm commission.
- Collector đọc `result.commission` (bỏ formula `config.commission_percent`).
- `commission_bps`→broker (dispatch/sandbox); `Settings.paper_commission_percent=0.0004`→execution→broker_factory→live paper.
- OKX `to_order_result` map `abs(float(fee))`.
- `just test` + `ruff` + `pyright` + `lint-imports` (8) pass.

## Rủi ro chính

1. **Sót commission** ở 1/4 fill path (nhất `_fire_synthetic_exit`) → exit commission mất. → P02 checklist bắt buộc cả 4.
2. **Test churn** balance/equity assert lệch do entry commission — expected. → P05.
3. **Reduce-cover balance âm nhẹ** (commission trừ dù `_can_afford` return True sớm) — accept + comment.
4. OKX `fee` per-fill vs accumulated — map accumulated (khớp `accFillSz`/`avgPx`); verify payload demo khi impl. → P04.
