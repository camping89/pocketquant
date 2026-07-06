# Roadmap — Trading Calculation + Structure Refactor

> Master index. Initiative chẻ thành **8 sub-brainstorm (R1–R8)**, mỗi cái làm
> brainstorm→plan→implement ở **session riêng**. Chi tiết logic: `design-execution-metrics-separation.md`
> (Model E). OKX verification: `okx-broker-verification.md`. Gốc: `todo.md` +
> `plans/reports/analysis-260703-1027-paper-broker-position-pnl-commission.md`.

## Vision — kiến trúc đích

**3 tầng** (từ 4): `app ◁ engine ◁ core`. Nguyên lý: *backtest và live là hai **driver** trên một **engine** chung + một **domain** chung* — không phong tầng riêng cho backtest.

```
core/
  common/                      tiện ích agnostic (messaging, time, logging…)
  domain/                      ← TẤT CẢ aggregates/entities/VOs/domain-services
    trading/    Trade, Fill, EquityPoint, PerformanceMetrics,
                PerformanceCalculatorDomainService(.build), CommissionModel
    backtest/   BacktestResult, BacktestConfig, OpenLot   (VO đặc thù run)
    order/ position/ risk/ strategy/ brokers/ bar/ market_data/ quote/ …
  infra/                       binance, brokers, persistence, http_client, scheduling

engine/                        ← orchestration, framework-free
  strategy/     strategy_app_service, strategy_command/query_service
  execution/    order_app_service, position_app_service, orders_positions, risk_check (phẳng)
  market_data/  (feature area)
  backtest/     backtest_app, sandbox, historical_replay, report, dispatch, command/query/stats, loader
  live/         reconcile_service, live-run coordinator   (paper-RT + OKX; runtime driver ở app)

app/                           ← fastapi: routes, di, middleware, main
```

**Invariants (mọi R phải giữ):**
- Parity: backtest & paper-live **cùng** logic khớp lệnh (PaperBrokerAdapter dùng chung) — không tách engine khớp lệnh.
- import-linter xanh: `app ◁ engine ◁ core`, intra-engine `backtest ⟂ live` + máy chung ⊄ backtest/live, `core.domain ⊄ core.infra`, `fastapi only in app`, `no bson`.
- Metrics **source-agnostic** ở `core` (backtest + live cùng gọi `build(trades, equity)`).
- Structure track: **test giữ xanh sau mỗi move** (di chuyển thuần, không đổi logic).

## Decomposition — R1→R8

| R | Track | Scope | Depends |
|---|---|---|---|
| **R1** ✅ | structure | Tạo `core.domain.trading` (move Trade/Fill/EquityPoint + PerformanceCalculatorDomainService + trade_stats + `build`); rename `BacktestMetrics`→`PerformanceMetrics`; move `BacktestConfig`→`core.domain.backtest`; audit engine DTO vs domain VO; `Order` record→`OrderRecord`. **Done** — metrics_builder.py đã xoá (build folded vào `PerformanceCalculatorDomainService.build`). | — |
| **R2** ✅ | structure | Gộp `backtest/`→`engine/backtest/`; regroup engine `{strategy,execution,market_data,backtest,live}`; flatten `handlers/risk/check_risk`→`execution/risk_check.py`; tạo `engine/live/` + move `StrategyReconcileAppService`; import-linter 4→3 tầng + 2 intra-engine contract (8 tổng). **Done** — 5 feature area là regular package (`__init__.py` rỗng, grimp cần để discover contract-referenced module). | R1 |
| **R3** ✅ | logic | `CommissionModel` + `PercentageCommissionModel(bps)`; `OrderResult.commission`; paper broker tính + trừ balance (entry too), `_can_afford`; OKX map fee; rewire `BacktestConfig.commission_bps`→broker. **Done** — model ở `core.domain.trading`; commission trừ cả 4 fill path qua `_execute_fill_with_commission`; collector đọc `result.commission`; `Settings.paper_commission_percent=0.0004`→`broker_factory`; OKX map `abs(fee)`. `just test` 569 pass, ruff/pyright/lint-imports (8) xanh. | R1, R2 |
| **R4** ✅ | logic | Broker phát `Trade` khi close (avg-cost từ `PositionAggregate`) qua `subscribe_trades`/`TradeClosedEvent`; **xoá** `LotTrackingHelper` + `_consumed_pnl`. **Done** — `PositionAggregate.reduce_quantity` emit `TradeClosedEvent` economic-only (entry_commission tích luỹ qua open/add, drain portion tỉ lệ); `IBrokerPort.subscribe_trades` kênh thứ 3, paper broker forward SAU fill `OrderResult` (back-link exit order), OKX no-op defer R8; collector `on_trade` dựng `Trade` + credit pnl, `open_positions` từ `broker.get_positions()`. Commission single-debit không đổi (`on_fill` per-fill; `on_trade` chỉ credit pnl). `just test` 560 pass, ruff/pyright/lint-imports (8) xanh. | R3 |
| **R5** ✅ | logic | Rút ruột `BacktestResultAppService`→`BacktestReportAppService` + gut shadow equity ledger. **Done** — xoá `_current_equity`/`_peak_equity`/`_total_commission`; collector inject `IBrokerPort`, `on_trade` + `finalize` đọc `broker.get_balance().available_balance` (broker single source; verified `_balance` update trong lock, dispatch `TradeClosedEvent` ngoài lock → `get_balance` no deadlock, parity byte-exact với shadow cũ). `on_fill` chỉ stamp `result.commission` lên Fill (không double-debit); `total_commission` sum từ fills tại finalize. `finalize` async (2 call site `await`). 1 file (không tách — user chọn minimal churn). `just test` 560 pass (engulfing/hitnrun2 characterization số KHÔNG đổi), ruff/pyright/lint-imports (8) xanh. | R1, R4 |
| ✅ **R6** | logic | `PositionSizerDomainService`→`PositionCalculatorDomainService`; return `PositionCalculation{size,notional,risk_amount,est_entry_commission}`; consts + giải thích; xoá `KELLY/FIXED`; `RiskCheckHandler` import consts — **Done**. Rename service + VO (frozen, file riêng cut circular), 3 class consts (RISK_PER_TRADE/MAX_EXPOSURE_PERCENT/DEFAULT_SL_RISK_PERCENT) = 1 source default (RiskConfig fields tham chiếu). RiskConfig override giữ nguyên (tests param). RiskCheckHandler fallback consts. Xoá KELLY/FIXED enum + validate_size dead. Parity pass 560/560, 4 gate xanh (test/ruff/pyright-baseline/lint-imports 8). | R1, R3 |
| ✅ **R7** | config | Paper `initial_balance` 100k→10k + `paper_initial_balance`→10k; currency `USD` (paper/backtest), OKX giữ USDT; commission default 4 bps; verify worked-example trên run thật | R3, R5 |
| **R8** ✅ | hybrid | Live-run extraction + live Trade pipeline. **Done** — reframe: R2 đã tách ~80% structure, R8 = (a) **relocations**: `BrokerFactory`→`core.infra.brokers`, `Quote`/`WsSubscription`→`engine.market_data.app_services`; fold `rehydrate`→`StrategyReconcileAppService.bootstrap()` (thin app driver: inject→bootstrap→create_task→cancel). (b) **live Trade pipeline** (M1 relative-per-sub, chưa từng có): `LiveTradeCollector` (EventBus subscriber, `run_id←subscription_id`) persist `trades`; `LiveMetricsQueryService` on-demand (`GET /subscriptions/{id}/metrics`, cumsum-pnl equity anchored paper nominal, omit %-return); broker→bus qua `_forward_trade_to_bus` (live-only — backtest `inject_prepared_strategy` bypass → no double-count). OKX `subscribe_trades` giữ no-op (defer future R). `just test` 570 pass, ruff/pyright/lint-imports (8) xanh. | R2 |

## Dependency graph + thứ tự

```
STRUCTURE:  R1 ──► R2 ──────────────► R8
                    │
LOGIC:              ├─► R3 ─► R4 ─► R5
                    │         (R5 cũng cần R1)
                    ├─► R6  (song song, sau R1+R3)
                    └─► R7  (cuối: cần R3+R5)
```

Khuyến nghị chạy: **R1 → R2 → R3 → R4 → R5 → R6 → R7 → R8.**
Structure (R1,R2) trước để logic không phải rebase path; R8 cuối vì cần design riêng.

## Execution protocol (mỗi session)

1. Mở sub-brainstorm cho `Rk`: `/brainstorm` với scope hàng Rk + doc này.
2. Brainstorm → `/ck:plan` → implement → test (`just test` + `ruff` + `pyright` + `lint-imports`).
3. Structure R (R1,R2): **không đổi logic** — nếu test đỏ vì logic, dừng, tách ra.
4. Cập nhật cột trạng thái bảng trên khi xong Rk.

## Unresolved questions (giải trong R tương ứng)

- ~~**R3**: OKX trả closed-PnL per-position hay chỉ fills?~~ **GIẢI** (`okx-broker-verification.md`): OKX thick — trả `fee` + `realizedPnl`; `IBrokerPort` cân xứng OK. Adapter hiện under-map (map thêm field có sẵn). Caveat mới: dấu `fee` âm, funding fee SWAP paper không mô phỏng, WS mapper mất `side`.
- **R6**: **GIẢI** — 4 runtime site (main_extensions/strategy_reconcile/backtest_dispatch/backtest_strategy_loader) dùng `RiskConfig()` default, KHÔNG override per-strategy. **NHƯNG** tests override `max_exposure_percent` để parameterize sizing (engulfing/hitnrun2). → Giữ optional `RiskConfig` override; consts = nguồn default (class attrs `RISK_PER_TRADE`/`MAX_EXPOSURE_PERCENT`/`DEFAULT_SL_RISK_PERCENT` tham chiếu từ `RiskConfig` fields). `from_dict` dead (không caller) — giữ nguyên compat. Parity: `calculate().size` byte-identical, override behavior riêng-biệt nguyên.
- ~~**R1/R4**: `Trade.run_id`/`strategy_code` là FK backtest — với live map sang gì (subscription_id? session id?)?~~ **GIẢI (R8) — live-value map = `subscription_id`:** `LiveTradeCollector._on_trade_closed` stamp `run_id←event.subscription_id` (event mang sẵn `subscription_id`+`symbol`), `strategy_code←strategy_service.get_config(sub_id).name` (in-memory, no Mongo). `core.domain.trading.Trade` dùng chung 2 path, subscriber owns context (backtest stamp `config`, live stamp sub). Reads scope theo `run_id` (=sub_id) qua `TradeRepository.list_by_subscription`.
- ~~**R4**: OKX `OrderResult.commission` là **accumulated snapshot** vs paper **per-fill** → live tracker cộng dồn OKX sẽ **double-count**.~~ **GIẢI (R8) — defer OKX emission:** R8 live Trade pipeline chỉ wire paper broker (per-fill, an toàn). OKX `subscribe_trades` giữ no-op, defer sang **R tương lai** (cần demo fill payload verify snapshot-delta vs paper, tránh double-count `accFillSz`). Comment ở `okx_broker_adapter.subscribe_trades` trỏ rõ.
- ~~**R1**: `Order` record rename `OrderRecord` có đáng churn (tránh clash `OrderAggregate`)? engine DTO nào là domain VO thật (audit khi làm R1)?~~ **GIẢI (R1):** `Order`→`OrderRecord` đã move sang `core.domain.order` (cạnh `OrderAggregate`, không clash). Audit engine DTO: `engine/market_data/sync_dtos.py` + `tracked_symbols_backfill.py` đều là app/command–response DTO (API-shaped, có default/validation), **không** phải domain VO đặt nhầm tầng → không move gì.
- ~~**R2**: intra-engine dùng `layers` contract hay `independence` contract cho `backtest ⟂ live` + máy chung?~~ **GIẢI (R2):** 2 contract tách — `independence` [`engine.backtest`, `engine.live`] + `forbidden` máy-chung (`strategy`/`execution`/`market_data`) → driver (`backtest`/`live`). Tổng **8 contract**. Đồ thị verified DAG nên cả 2 KEPT không cần đổi logic.
- ~~**R7**: thêm `paper_commission_bps` vào `Settings`?~~ **GIẢI (R3):** thêm `paper_commission_percent: float = 0.0004` (match sibling `paper_slippage_percent`, dạng fraction), wire qua `execution.py`→`broker_factory` ngay ở R3. R7 chỉ tune value + currency.
- ~~**R3**: funding fee SWAP có mô phỏng ở paper không?~~ **GIẢI (R3):** KHÔNG sim — YAGNI (chưa có historical funding data); gap bounded, document. Backtest/paper = no funding, OKX live = real. Mở lại khi có funding data (không R cụ thể).
- ~~**R8**: ranh giới nào của live-run tách xuống engine được mà không kéo fastapi/scheduler xuống theo?~~ **GIẢI (R8):** `engine.live` giữ `StrategyReconcileAppService` (+ `bootstrap()`), `LiveTradeCollector`, `LiveMetricsQueryService` — framework-free. App driver mỏng: `inject → bootstrap() → create_task(run()) → cancel` + `enable_jobs` gate + WS/DI wiring. `BrokerFactory`→`core.infra.brokers`; `Quote`/`WsSubscription`→`engine.market_data.app_services`. Reconcile = plain asyncio task (KHÔNG scheduler). Zero fastapi trong engine — 8 import-linter contract xanh.
