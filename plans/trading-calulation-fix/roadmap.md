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
| **R2** | structure | Gộp `backtest/`→`engine/backtest/`; regroup engine `{strategy,execution,market_data,backtest,live}`; flatten `handlers/risk/check_risk`→`execution/risk_check.py`; tạo `engine/live/` + move `StrategyReconcileAppService`; import-linter 4→3 tầng + intra-engine contract | R1 |
| **R3** | logic | `CommissionModel` + `PercentageCommissionModel(bps)`; `OrderResult.commission`; paper broker tính + trừ balance (entry too), `_can_afford`; OKX map fee; rewire `BacktestConfig.commission_bps`→broker | R1, R2 |
| **R4** | logic | Broker phát `Trade` khi close (avg-cost từ `PositionAggregate`) qua `subscribe_trade`/`TradeClosedEvent`; **xoá** `LotTrackingHelper` + `_consumed_pnl` | R3 |
| **R5** | logic | Rút ruột `BacktestResultAppService`→`BacktestReportAppService` (subscribe Trade+equity → `PerformanceCalculatorDomainService.build` → persist); ~~xoá `metrics_builder.py`~~ (đã xoá ở R1 — `.build` sạch sẵn để thừa hưởng) | R1, R4 |
| **R6** | logic | `PositionSizerDomainService`→`PositionCalculatorDomainService`; return `PositionCalculation{size,notional,risk_amount,est_entry_commission}`; consts + giải thích; xoá `KELLY/FIXED`; `RiskCheckHandler` import consts | R1, R3 |
| **R7** | config | Paper `initial_balance` 100k→10k + `paper_initial_balance`→10k; currency `USD` (paper/backtest), OKX giữ USDT; commission default 4 bps; verify worked-example trên run thật | R3, R5 |
| **R8** | hybrid | Trích live-run orchestration từ app (reconcile-loop/scheduler wiring) vào `engine/live/` chỗ framework-free; app giữ runtime driver (scheduler tick, WS, DI). Cần design app↔engine boundary | R2 |

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
- **R6**: có strategy nào override `risk_per_trade`/`max_exposure_percent` per-strategy? Nếu có → const thuần phá; giữ optional override.
- **R1/R4**: `Trade.run_id`/`strategy_code` là FK backtest — với live map sang gì (subscription_id? session id?) để `core.domain.trading` dùng chung 2 path? *(còn mở — chuyển R4/R5.)*
- ~~**R1**: `Order` record rename `OrderRecord` có đáng churn (tránh clash `OrderAggregate`)? engine DTO nào là domain VO thật (audit khi làm R1)?~~ **GIẢI (R1):** `Order`→`OrderRecord` đã move sang `core.domain.order` (cạnh `OrderAggregate`, không clash). Audit engine DTO: `engine/market_data/sync_dtos.py` + `tracked_symbols_backfill.py` đều là app/command–response DTO (API-shaped, có default/validation), **không** phải domain VO đặt nhầm tầng → không move gì.
- **R2**: intra-engine dùng `layers` contract hay `independence` contract cho `backtest ⟂ live` + máy chung?
- **R7**: thêm `paper_commission_bps` vào `Settings` (song song `paper_slippage_percent`)?
- **R8**: ranh giới nào của live-run tách xuống engine được mà không kéo fastapi/scheduler xuống theo?
