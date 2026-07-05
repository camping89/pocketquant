---
title: "Service Naming Convention Rename"
description: "Rename ~20 service-like class + file theo convention (đọc tên biết layer): *DomainService, *StrategyService, *AppService, I*Port, *Adapter, *Helper. Thuần cosmetic, không đổi hành vi."
status: completed
priority: P2
branch: develop
tags: [refactor, naming, architecture, di]
blockedBy: []
blocks: []
created: "2026-07-05T12:08:00+07:00"
createdBy: "ck:plan"
source: "plans/reports/brainstorm-260705-0944-service-naming-convention.md"
---

# Service Naming Convention Rename

Nguồn convention (đã chốt): `plans/reports/brainstorm-260705-0944-service-naming-convention.md`.

## Mục tiêu
Đổi tên **class + file** để đọc tên biết layer, không cần xem folder. **Thuần cosmetic — không đổi hành vi.** Verify: `pytest` + `import-linter` (7 contracts) + `pyright` xanh sau mỗi phase.

## Trạng thái: HOÀN THÀNH
Cả 6 phase (0→5) đã commit riêng trên `develop`. Verify cuối: `pytest` 552 passed / 1 skipped · `import-linter` 7 contracts kept · `pyright` sạch (1 lỗi pre-existing `test_engulfing.py` — không do rename) · `ruff` 2 lỗi I001 pre-existing (file không đụng). ~23 class + file rename, git giữ history qua `git mv`.

## Convention (tóm tắt)
| Layer / Role | Class | File |
|---|---|---|
| Application orchestrator | `*AppService` | `*_app_service.py` |
| Domain service | `*DomainService` | `*_domain_service.py` |
| Domain strategy | `*StrategyService` (`IStrategyService`) | `*_strategy_service.py` |
| Infra port | `I{Concept}Port` | `*_port.py` (1 port/file) |
| Infra adapter | `{Source}[{Type}]Adapter` | `*_adapter.py` |
| Helper | `*Helper` | `*_helper.py` |

Exempt: `*Command/QueryService`, `*Repository`, `*Provider`, `*Middleware`, `*Handler`, `*Factory`, `*Scheduler`, data class (entity/VO/enum/event/DTO).

## Phases (thứ tự low→high blast radius)
| # | Phase | Scope | Risk | File |
|---|---|---|---|---|
| 0 | Docs + CLAUDE.md link | convention → `code-standards.md`, link từ `CLAUDE.md` | none | [phase-00](phase-00-docs-convention.md) |
| 1 | Domain services + Helper | 4 domain svc + `LotTrackingHelper` (không qua DI) | low | [phase-01](phase-01-domain-services-helper.md) |
| 2 | Strategy | `IStrategyService` + 2 impl + split file | low-med | [phase-02](phase-02-strategy.md) |
| 3 | App orchestrators | 4 class → `*AppService` | med | [phase-03](phase-03-app-orchestrators.md) |
| 4 | Infra market_data | 2 port + `BinanceAdapter` + split + DI | med | [phase-04](phase-04-infra-market-data.md) |
| 5 | Infra brokers | 2 port + 3 adapter (`PaperBroker` 25 refs) + split + DI | high | [phase-05](phase-05-infra-brokers.md) |

Mỗi phase độc lập, tự verify được. Commit riêng từng phase.

## Verify (mỗi phase, bắt buộc xanh trước khi sang phase kế)
- `just test` (pytest)
- `import-linter` — 7 contracts (layer không đổi → an toàn; rename trong cùng package)
- `pyright` type check (Dishka resolve theo type → bắt sai type-hint)
- `git mv` khi đổi tên file để giữ history

## Blast radius (file refs, src+test)
`PaperBroker` 25 · `IBroker` 13 · `IDataProvider` 10 · `IStrategy`/`BacktestResultCollector`/`StrategyReconcileService`/`IRealtimeQuoteProvider`/`OKXBroker` 6 · domain svc 4-5 mỗi cái.

## Correction từ brainstorm report
`TradeStatsCalculator` **không tồn tại** (module VO + functions) → loại. Domain service = **4** class.

## Cross-plan coordination
Overlap `260630-0031-backtest-mae-mfe-excursion` (pending P3) trên `paper_broker.py`, `result_collector.py`, `backtest_engine_sandbox.py`. Khuyến nghị chạy plan rename này **trước** (cosmetic, nhanh) → MAE/MFE build trên tên mới. Soft-coordination, không hard-block.

## Key dependencies
- Dishka DI (resolve theo type) — mọi rename type phải đồng bộ provider return-hint + `FromDishka[…]`.
- `__init__.py` re-exports — nhiều package re-export symbol (vd `core/domain/risk/__init__.py`).
- import-linter 7 contracts @ `pyproject.toml` — layer-based, không đụng nếu file ở nguyên package.
