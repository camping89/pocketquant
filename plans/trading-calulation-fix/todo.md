# Todo — Trading Calculation Fix

**STATUS: ✅ DONE (R1–R8, 2026-07-06).** Chi tiết: `roadmap.md`. Kiến trúc: `design-execution-metrics-separation.md`.

- PaperBrokerAdapter
  - ✅ [R3] Abstraction + config cho IBrokerService: slippage + commission qua config broker. **Lệch câu chữ:** slippage KHÔNG set 0 — giữ realistic (`paper_slippage_percent=0.001`) theo quyết định brainstorm; const/config hoá đạt.
  - ✅ [R3] Commission → `IBrokerPort` (`CommissionModel` + `PercentageCommissionModel` → `OrderResult.commission`, trừ balance). "Quá cao": 10 bps → **4 bps** (Binance futures taker thật).
  - ✅ [R4] GrossPnL → `IBrokerPort`: `PositionAggregate.reduce_quantity` phát `TradeClosedEvent` (avg-cost). Broker single source.
  - ✅ [R3+R4] Abstraction chung mọi broker: `IBrokerPort.subscribe_trades` + `CommissionModel` per-broker (paper tính, OKX đọc venue — verified `okx-broker-verification.md`).
  - ✅ [R5] Purpose của result collector: rút ruột thành reporter thuần (broker single source; collector consume Trade+equity → metrics). Xoá FIFO/shadow-equity.
  - ✅ [R5] Rename `BacktestResultAppService` → **`BacktestReportAppService`** (bỏ "Result", hết clash Result pattern).
- ✅ [R6] `PositionSizerDomainService` → **`PositionCalculatorDomainService`**. **Lệch câu chữ:** giữ suffix `DomainService` (naming convention bắt buộc), không phải `...Service`. Return `PositionCalculation{size,notional,risk_amount,est_entry_commission}`.
  - ✅ [R6] Config → const đầu class (`RISK_PER_TRADE`/`MAX_EXPOSURE_PERCENT`/`DEFAULT_SL_RISK_PERCENT`), là nguồn default (RiskConfig fields tham chiếu); xoá KELLY/FIXED dead.
  - ✅ [R6] Mỗi const có 1 câu giải thích.
- ✅ [design + R7] Worked example USD 10,000 (`design-execution-metrics-separation.md` §6).
- ✅ [R7] Default test account **USD 10,000** cho paper + backtest (OKX giữ USDT venue).

## Deferred (không blocking)
- OKX live Trade emission (`subscribe_trades` no-op) — cần demo fill payload, 1 R tương lai.
- Funding fee SWAP không sim (YAGNI, gap document).
- `260630-0031-backtest-mae-mfe-excursion` — rebase nhẹ (mae/mfe/r_multiple vào Trade+event).
