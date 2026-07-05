# Brainstorm — Service Naming Convention theo Layer (FINAL)

**Date:** 2026-07-05 · **Scope:** đặt tên **service-like class** sao cho **đọc class/file name biết layer** (không cần xem folder) · **Deliverable:** report + task cập nhật docs. **Status:** mọi quyết định đã chốt.

## Nguyên tắc

1. **Tên (class + file) tự mã hóa layer/role.** Không nhìn folder mới biết layer.
2. **Không stack 2 doer-suffix generic (-er/-or) trong 1 tên.** Nếu dính → chuyển từ dẫn đầu sang gerund: `LotTracker`+`Helper` → `LotTrackingHelper`. **Ngoại lệ:** danh từ nghiệp vụ kết -er (vd `Broker`) không tính là doer-suffix → `BrokerAdapter` hợp lệ.
3. Data class (entity/VO/enum/event/DTO) và role đã có suffix chuẩn → exempt.

## Convention cuối

| Layer / Role | Class suffix | File suffix |
|---|---|---|
| API route | *(functions, no class)* | `*_routes.py` |
| Application — orchestrator/state-machine/event-subscriber | `*AppService` | `*_app_service.py` |
| Domain — pure service | `*DomainService` | `*_domain_service.py` |
| Domain — strategy (impl) | `*StrategyService` | `*_strategy_service.py` |
| Interface — strategy | `IStrategyService` | `strategy_service_interface.py` |
| Interface — infra boundary/port | `I{Concept}Port` | `*_port.py` (1 port / file) |
| Infra — adapter/impl | `{Source}[{Type}]Adapter` | `*_adapter.py` |
| Helper — utility không thuộc layer-role | `*Helper` | `*_helper.py` |

**Adapter rule:** `{Source}Adapter` khi 1 class đa mục đích (vd Binance); `{Source}{Type}Adapter` khi source có nhiều adapter tách biệt (vd OKX: broker + websocket).

## Rename mapping đầy đủ

### 1. Domain service → `*DomainService`
| Current | New class | New file |
|---|---|---|
| `PositionSizer` | `PositionSizerDomainService` | `position_sizer_domain_service.py` |
| `BarBuilder` | `BarBuilderDomainService` | `bar_builder_domain_service.py` |
| `PerformanceCalculator` | `PerformanceCalculatorDomainService` | `performance_calculator_domain_service.py` |
| `TradeStatsCalculator` | `TradeStatsCalculatorDomainService` | `trade_stats_calculator_domain_service.py` |
| `SyncProgressTracker` | `SyncProgressTrackerDomainService` | `sync_progress_tracker_domain_service.py` |

*(VO/enum cùng file — `HistogramBin`, `StreakStats`, `DirectionProfitFactor`, `DrawdownPeriod`, `SyncProgressDecision` — KHÔNG đổi.)*

### 2. Strategy → `*StrategyService` (+ interface)
| Current | New class | New file |
|---|---|---|
| `IStrategy` | `IStrategyService` | `strategy_service_interface.py` |
| `EngulfingStrategy` | `EngulfingStrategyService` | `engulfing_strategy_service.py` |
| `HitNRun2Strategy` | `HitNRun2StrategyService` | `hitnrun2_strategy_service.py` |

### 3. Application orchestrator → `*AppService`
| Current | New class | New file |
|---|---|---|
| `BacktestResultCollector` | `BacktestResultAppService` | `backtest_result_app_service.py` |
| `StrategyReconcileService` | `StrategyReconcileAppService` | `strategy_reconcile_app_service.py` |
| `WsSubscriptionManager` | `WsSubscriptionAppService` | `ws_subscription_app_service.py` |
| `BacktestSandbox` | `BacktestSandboxAppService` | `backtest_sandbox_app_service.py` |

### 4. Infra port → `I{Concept}Port` (tách file riêng)
| Current (class @ file) | New class | New file |
|---|---|---|
| `IBroker` @ `brokers/interfaces.py` | `IBrokerPort` | `brokers/broker_port.py` |
| `IBrokerFactory` @ `brokers/interfaces.py` | `IBrokerFactoryPort` | `brokers/broker_factory_port.py` |
| `IDataProvider` @ `market_data/interfaces.py` | `IDataProviderPort` | `market_data/data_provider_port.py` |
| `IRealtimeQuoteProvider` @ `market_data/interfaces.py` | `IRealtimeQuoteProviderPort` | `market_data/realtime_quote_provider_port.py` |

### 5. Infra adapter → `*Adapter`
| Current | New class | New file | Ghi chú |
|---|---|---|---|
| `PaperBroker` | `PaperBrokerAdapter` | `paper_broker_adapter.py` | Broker=danh từ nghiệp vụ, hợp lệ |
| `OKXBroker` | `OKXBrokerAdapter` | `okx_broker_adapter.py` | OKX đa class → giữ Type |
| `OkxWebSocketClient` | `OKXWebSocketAdapter` | `okx_websocket_adapter.py` | |
| `BinanceClient` | `BinanceAdapter` | `binance_adapter.py` | đa mục đích → bỏ Type |

### 6. Helper → `*Helper`
| Current | New class | New file |
|---|---|---|
| `LotTracker` | `LotTrackingHelper` | `lot_tracking_helper.py` |

*(Tracker+Helper = 2 doer-suffix → gerund `Tracking`. `metrics_builder.build_metrics` là function → giữ. `CollectedResults`, `ReplayStats`, `FillOutcome`, `OpenLot`, `ConsumedLot` = VO/result dataclass → exempt.)*

## Exempt — giữ role-suffix (không ép convention)

| Nhóm | Ví dụ |
|---|---|
| CQRS | `*CommandService`, `*QueryService` (app layer, request-scoped ≠ orchestrator) |
| Persistence | `*Repository` |
| DI / cross-cutting | `*Provider`, `*Middleware` |
| App handler | `RiskCheckHandler` |
| Infra factory/scheduler | `BrokerFactory`, `JobScheduler` |
| Infra adapter sub-component | `OkxMessageParser`, `OkxOrderMapper`, `OkxPositionMapper`, `OkxReconnectionHandler`, `OkxStateReconciler` |
| Data class | entity, VO, enum, event, `*Command/*Query/*Response` |

## Risks

- Rename đụng **mọi** DI type-hint (Dishka resolve theo type), import, tên file → cần `tester` full suite + `pyright` + `import-linter` (7 contracts) sau rename.
- Tách `interfaces.py` → nhiều `*_port.py`: cập nhật mọi import điểm khai báo/impl.
- Thuần cosmetic, không đổi hành vi. Rủi ro chính = sót reference → linter/pyright bắt.

## Next actions (task đã tạo)

1. **[docs]** Cập nhật `docs/code-standards.md` → bảng "Class Naming by Layer" theo convention final + link từ `CLAUDE.md` để code mới tuân theo.
2. **[impl]** `/ck:plan` → rename ~23 class theo phase (Helper/DomainService/StrategyService/AppService trước → Port/Adapter sau, đụng nhiều DI) + `tester` verify mỗi phase.

## Unresolved questions

*Không còn — toàn bộ quyết định đã chốt.*
