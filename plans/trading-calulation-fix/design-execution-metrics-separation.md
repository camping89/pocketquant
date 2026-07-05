# Design — Execution / Metrics Separation (Model E)

> Brainstorm output cho `todo.md`. **Design-only, chưa plan.** Thay thế bản nháp
> "Model D — broker owns lifecycle". Nguồn: `plans/reports/analysis-260703-1027-paper-broker-position-pnl-commission.md`.

## 1. Problem statement

Hai hệ kế toán song song + metrics bị nhốt sai tầng:
- `PaperBrokerAdapter._balance` (futures, slippage-in-price, **không commission**) → sizing, MTM, Sharpe.
- `BacktestResultAppService` ("ResultCollector"): tự tính commission/fill + FIFO gross PnL → trades, total P&L, win%.
- `PerformanceCalculatorDomainService` (pure metrics) **bị kẹt trong tầng `backtest`** → forward/live (`engine`/`app`) không import ngược được.

Hệ quả: commission 1 nơi / PnL lặp 2 nơi; Sharpe (broker MTM) bỏ commission còn `total_return` (ledger) có → lệch; UI hiện gross → win-rate sai; metrics không tái dùng được cho forward-test.

## 2. Mô hình 3 nhóm (chốt với user)

```
core.domain.trading:  Trade, Fill, EquityPoint (contract PHỔ QUÁT)
                      + PerformanceMetrics + PerformanceCalculatorDomainService  (Group 3, pure)
        ▲ dùng chung mọi nguồn
┌──────────────────────────────────┬─────────────────────────────────┐
│ GROUP 1 — BACKTEST               │ GROUP 2 — FORWARD/LIVE + BROKER   │
│ replay lịch sử                   │ IBrokerPort:                      │
│   → PaperBrokerAdapter (SIM)     │   PaperBrokerAdapter (SIM, RT)    │
│                                  │   OKXBrokerAdapter (real venue)   │
│   → Trade[] + equity[]           │   → Trade[] + equity[]            │
└─────────────┬────────────────────┴───────────────┬─────────────────┘
              │            Trade[] + equity[]        │
              ▼                                      ▼
      ┌───────────────────────────────────────────────────────┐
      │ GROUP 3 — METRICS (độc lập, source-agnostic, pure)    │
      │ PerformanceCalculatorDomainService.build(trades,equity)│
      │   → PerformanceMetrics                                 │
      └───────────────────────────────────────────────────────┘
```

**PaperBrokerAdapter là sim engine DÙNG CHUNG** cho backtest (clock lịch sử) và paper-forward (live feed) — chuẩn Backtrader/Zipline/QC. Khác nhau chỉ **data source + đồng hồ**, không phải 2 engine khớp lệnh.

### Parity principle (ràng buộc bất biến)
Backtest và paper-forward **phải cùng một logic khớp lệnh** (cùng PaperBroker). Tách vật lý thành 2 engine → backtest lệch live = vô nghĩa. Vì vậy **KHÔNG** dựng BacktestEngine riêng; chỉ tách **Metrics** (Group 3) + **Trade contract** ra core.

## 3. Decisions locked

| # | Hạng mục | Chốt |
|---|---|---|
| 1 | PaperBroker | Sim engine **dùng chung** backtest + paper-forward. Không tách vật lý. |
| 2 | Metrics (Group 3) | **Độc lập, source-agnostic**, move lên `core` (tầng duy nhất mọi nơi dùng). Facade `PerformanceCalculatorDomainService.build(trades, equity, …)`. |
| 3 | Trade/Fill | Contract phổ quát → `core.domain.trading`. |
| 4 | Placement | **Gộp 1 package** `core.domain.trading` (Trade+Fill+EquityPoint+PerformanceMetrics+calculator). |
| 5 | Commission | Abstraction per-broker: `CommissionModel` → `OrderResult.commission`, trừ vào balance khi fill (entry cũng tốn phí). OKX map phí venue. |
| 6 | PnL | Single home `PositionAggregate` (average-cost). Xoá `_consumed_pnl`. |
| 7 | Trade production | Broker phát Trade khi close (average-cost). **Xoá FIFO `LotTrackingHelper`**. |
| 8 | Ledger | `BacktestResultAppService` rút ruột → **`BacktestReportAppService`** (collect Trade+equity → facade → persist). |
| 9 | Sizer | `PositionSizerDomainService` → **`PositionCalculatorDomainService`**; return `PositionCalculation{size, notional, risk_amount, est_entry_commission}`; risk params = const trong class; xoá dead `KELLY/FIXED`; `RiskCheckHandler` import const → 1 source. |
| 10 | Rename metrics | `BacktestMetrics` → `PerformanceMetrics` (web TS type riêng, không ảnh hưởng). |
| 11 | Defaults | Test account **USD 10,000** (paper + backtest); commission **4 bps**; OKX giữ `USDT` venue. |

## 4. Placement — layering-driven (không phải thẩm mỹ)

`PerformanceCalculatorDomainService` đang ở **tầng `backtest`** → `core ◁ engine ◁ backtest ◁ app` khiến forward/live không với tới. Muốn source-agnostic **buộc** move lên `core`.

```
core/domain/trading/          ← GỘP 1 package
  trade.py            Trade
  fill.py             Fill
  equity_point.py     EquityPoint
  performance_metrics.py               PerformanceMetrics  (rename từ BacktestMetrics)
  performance_calculator_domain_service.py
        PerformanceCalculatorDomainService
        + static build(trades, equity, …) -> PerformanceMetrics   (gộp build_metrics)
        + trade_stats (gộp từ trade_stats_calculator.py)

core/domain/backtest/         ← chỉ còn đặc thù backtest-run
  BacktestResult (nhúng PerformanceMetrics), OpenLot, config_snapshot

core/domain/order/            ← OrderAggregate (live) + OrderRecord (audit, từ backtest.Order)
```
- numpy vào `core` hợp lệ (lib ngoài); import-linter 7 contracts vẫn xanh (core chỉ import core.domain).
- `trade_stats_calculator.py` move cùng.

## 5. Component changes

**PaperBrokerAdapter (sim chung):** giữ 1 `CommissionModel` (ctor config, default 4 bps); commission trừ `_balance` khi fill; `_can_afford` cộng commission; phát `Trade` (average-cost, per close) qua kênh mới (`subscribe_trade`/`TradeClosedEvent`). `OrderResult` thêm `commission`.

**PositionCalculatorDomainService:** consts có giải thích, thay `RiskConfig` cho path mặc định —
```
_RISK_PER_TRADE = 0.02        # phần vốn rủi ro mỗi lệnh, đo trên khoảng entry→SL
_MAX_EXPOSURE_PERCENT = 0.10  # trần notional theo phần vốn (cap gần như luôn thắng)
_DEFAULT_SL_RISK_PERCENT = 0.01  # price-risk dự phòng khi lệnh không SL
```
Return `PositionCalculation{size, notional, risk_amount, est_entry_commission}`; nhận optional `CommissionModel` để ước commission entry. `RiskCheckHandler` import các const này.

**BacktestReportAppService (rút ruột ~470→~120 dòng):** subscribe Trade + snapshot equity per-bar → `PerformanceCalculatorDomainService.build(trades, equity)` → assemble `BacktestResult` → persist. Xoá LotTrackingHelper, `_consumed_pnl`, tính commission, FIFO.

## 6. Worked example — USD 10,000, commission 4 bps, slippage 10 bps

Engulfing LONG: close=100, pattern_low=98 → SL=97.902, TP=104.

| Bước | Tính | USD |
|---|---|---|
| size (cap 10% thắng) | 10000×0.10 / 100 | **10** |
| Entry fill (BUY +slip) | 100 × 1.001 | 100.10 |
| Entry commission | 100.10×10×0.0004 | 0.400 |
| Balance sau entry (futures) | 10000 − 0.400 | 9999.60 |
| Exit fill (SELL −slip @TP) | 104 × 0.999 | 103.896 |
| Exit commission | 103.896×10×0.0004 | 0.416 |
| **Gross PnL** | (103.896−100.10)×10 | **37.96** |
| **Net PnL** | 37.96 − 0.400 − 0.416 | **37.14** |
| **Final balance** | 9999.60 + 37.96 − 0.416 | **10037.14** |

Broker phát `Trade{entry=100.10, exit=103.896, qty=10, pnl(gross)=37.96, commission=0.816}`; `build()` gộp thành metrics. (10 bps cũ → net ~35.92.)

## 7. Blast radius

`IBrokerPort` (+trade channel), `OrderResult` (+commission), `PaperBrokerAdapter`, `OKXBrokerAdapter` (map fee/closed-PnL), **xoá** `LotTrackingHelper`, **rút ruột** `BacktestResultAppService`, `backtest_app_service`/`backtest_dispatch` (wiring), `BacktestConfig` (commission_bps → broker), move `metrics_builder`→core, di dời `Trade/Fill/EquityPoint/PerformanceMetrics`→`core.domain.trading`, `metric-cards.ts`/web (chỉ nếu đổi JSON keys — không), nhiều test.

## 8. Success criteria

- Metrics ở `core`, `build(trades, equity)` chạy cho backtest **và** (tương lai) forward. `backtest/domain/services` rỗng.
- 1 nguồn commission (broker), 1 nguồn PnL (`PositionAggregate`). Không còn `_consumed_pnl`/FIFO.
- `total_return`, final equity, Sharpe/Sortino cùng gồm commission.
- Backtest `engulfing`/`hitnrun2`: số trades + gross PnL **không đổi**; net khác do commission model; equity khớp broker balance.
- `just test` + `ruff` + `pyright` + `lint-imports` (7 contracts) pass.

## 9. Next steps

1. User duyệt Model E này.
2. Verify OKX adapter: fee + closed-PnL sẵn có để map `OrderResult.commission` + `Trade`?
3. `/ck:plan` chia phase: (a) `core.domain.trading` gộp + move Trade/Fill/EquityPoint/metrics + rename PerformanceMetrics; (b) CommissionModel + OrderResult.commission + balance; (c) Trade emission channel trên IBrokerPort; (d) rút ruột BacktestReportAppService + xoá LotTrackingHelper; (e) rewire BacktestConfig/dispatch; (f) PositionCalculatorDomainService + consts + PositionCalculation; (g) defaults USD 10000/4bps; (h) tests.

## 10. Unresolved questions

- OKX trả **closed-PnL per position** hay chỉ fills? Nếu chỉ fills → cả paper & OKX suy Trade broker-side (average-cost) cho `IBrokerPort` cân xứng — cần verify.
- Có strategy nào override `risk_per_trade`/`max_exposure_percent` per-strategy không? Nếu có → const thuần phá; cần giữ optional override thay vì xoá `RiskConfig`.
- `Trade.run_id`/`strategy_code` là FK backtest — với **live/forward** trades map sang gì (subscription_id? session id?) để `core.domain.trading` dùng chung cả 2 path?
- Thêm `paper_commission_bps` vào `Settings` (song song `paper_slippage_percent`)?
- `Order` record rename `OrderRecord` (tránh clash `OrderAggregate`) — đáng churn không?
- Package `core.domain.trading` ôm cả execution contract lẫn performance metrics — chấp nhận gộp (ít package) hay tách `performance` sau nếu phình?
