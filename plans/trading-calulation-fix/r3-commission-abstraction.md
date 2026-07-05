# R3 — Commission Abstraction (brainstorm chốt)

> Sub-brainstorm R3 của `roadmap.md`. Design-only. Nguồn grounding: đọc code thật
> (`paper_broker_adapter.py`, `value_objects.py`, `okx_order_mapper.py`,
> `backtest_result_app_service.py`, `config.py`, `broker_factory.py`). Kế thừa
> `design-execution-metrics-separation.md` (Model E) + `okx-broker-verification.md`.

## 1. Problem

Commission bị nhốt sai chỗ + 2 ledger song song:
- `PaperBrokerAdapter._balance` (futures: mở KHÔNG trừ tiền, chỉ credit realized-pnl delta khi reduce/close) — **commission = 0**.
- Commission thật tính post-hoc ở `BacktestResultAppService.on_fill`: `fill_price*qty*config.commission_percent`, trừ vào `_current_equity` (ledger riêng collector).
- `OrderResult` **không có** field commission. `OkxOrderMapper` **bỏ lỡ** `fee` (data có sẵn).

→ Broker balance sai (bỏ commission), commission tính 1 nơi tách khỏi broker, OKX under-map. Divergence: MTM/Sharpe (broker) bỏ commission, `total_return` (collector) có.

## 2. Decisions locked (4 câu hỏi mở → chốt)

| # | Câu hỏi | Chốt | Lý do |
|---|---------|------|-------|
| 1 | Funding fee SWAP sim? | **Không sim, document gap** | YAGNI — chưa có historical funding data; gap bounded; funding nhỏ ở holding ngắn/vừa. Backtest/paper = no funding, OKX live = real. |
| 2 | CommissionModel placement | **`core.domain.trading`** | Tầng neutral: PaperBroker (infra) + R6 PositionCalculator (position domain) đều import sạch, tránh coupling position→brokers. |
| 3 | Ranh giới R3 vs R5 (collector) | **Collector đọc `result.commission`** | Single-source ngay, số không đổi (cùng giá trị), dọn sẵn R5. |
| 4 | Settings field live-paper | **Thêm `paper_commission_percent` ở R3** | Match sibling `paper_slippage_percent`; wire ngay để live-paper có commission (parity backtest). R7 tune value + currency. |

## 3. Design

### CommissionModel (mới — `core/domain/trading/commission_model.py`)
```python
class CommissionModel(Protocol):
    def compute(self, price: float, quantity: float) -> float: ...   # cost ≥ 0

class PercentageCommissionModel:
    def __init__(self, bps: float) -> None: ...
    def compute(self, price, quantity) -> float:
        return abs(price * quantity) * self._bps / 10_000
```
Protocol (structural, no ABC). Export qua `core/domain/trading/__init__`. Seam test: `PercentageCommissionModel(bps=0)`.

### OrderResult (+1 field)
`core/domain/brokers/value_objects.py`: `commission: float = 0.0` (non-fill = 0, backward compat).

### PaperBrokerAdapter
- ctor `commission_model: CommissionModel | None = None` → `None` dựng `PercentageCommissionModel(bps=…)` trong body (tránh mutable default).
- **4 fill path** set `OrderResult.commission` + trừ `_balance`: market fill, limit-immediate, limit-cross (`_fill_pending_on_bar`), synthetic SL/TP exit (`_fire_synthetic_exit`). ⚠️ Sót path exit = mất exit commission.
- `_balance -= commission` dưới lock (trong/sau `_execute_fill`).
- `_can_afford`: `fill_price*qty + commission ≤ _balance`. Reduce/cover short vẫn return True sớm — commission vẫn trừ, chấp nhận balance âm nhẹ ở pathological case (comment).

### Collector single-source
`backtest_result_app_service.on_fill`: `commission = result.commission` (bỏ formula config). `_current_equity -= commission` giữ nguyên → metrics R3 **không đổi**.

### Wiring
`dispatch`/`sandbox.create_broker(commission_bps=config.commission_bps)` → `PercentageCommissionModel`. `Settings.paper_commission_percent=0.0004` → `app/di/execution.py` → `broker_factory` config → live PaperBroker.

### OKX
`okx_order_mapper.to_order_result`: `commission = abs(float(fee))` khi có `fee`. Giả định `feeCcy == quote` (USDT-margined perp). **side để R4**.

## 4. Không làm (YAGNI)
- ❌ Funding fee sim (document gap — roadmap caveat #3).
- ❌ SlippageModel (slippage giữ float; chấp nhận bất đối xứng với commission_model).
- ❌ est_entry_commission trong PositionCalculation (→ R6).
- ❌ maker/taker / tiered / per-contract commission.

## 5. Blast radius

NEW: `core/domain/trading/commission_model.py`

Sửa: `core/domain/trading/__init__.py`, `core/domain/brokers/value_objects.py`,
`core/infra/brokers/paper/paper_broker_adapter.py`,
`core/infra/brokers/okx/websocket/okx_order_mapper.py`,
`engine/backtest/backtest_result_app_service.py`,
`engine/backtest/backtest_dispatch.py`, `engine/backtest/backtest_sandbox_app_service.py`,
`app/di/broker_factory.py`, `app/di/execution.py`, `core/config.py` + tests.

import-linter: **8/8 giữ xanh** — `core.domain.trading` ← infra/domain đều hợp lệ, không contract mới.

## 6. Worked example (USD 10k, 4bps, slippage 10bps — R7 end-state)

Engulfing LONG close=100, TP=104, size=10:
| Bước | USD |
|---|---|
| Entry fill (BUY +slip) | 100.10 |
| Entry commission (100.10×10×0.0004) | 0.400 → balance 9999.60 |
| Exit fill (SELL −slip @TP) | 103.896 |
| Exit commission (103.896×10×0.0004) | 0.416 |
| Gross PnL | 37.96 |
| **Net PnL** | **37.14** |
| **Final balance** | **10037.14** |

R3 dựng plumbing (default BacktestConfig vẫn 10bps tới R7). Số worked-example đầy đủ khi R7 set 4bps + USD 10k.

## 7. Success criteria

- `CommissionModel` + `PercentageCommissionModel` ở `core.domain.trading`.
- `OrderResult.commission` set trên **cả 4** fill path; `_balance` trừ commission entry + exit.
- `_can_afford` gồm commission.
- Collector đọc `result.commission` (không tự tính) — single source.
- `BacktestConfig.commission_bps` → broker; `Settings.paper_commission_percent` → live-paper.
- OKX map `abs(fee)` → `OrderResult.commission`.
- `just test` + `ruff` + `pyright` + `lint-imports` (8) pass.

## 8. Rủi ro

1. **Sót commission** ở 1/4 fill path (nhất synthetic exit) → exit commission mất.
2. **Test churn**: nhiều assert balance/equity lệch do entry commission — expected, phải update.
3. **Reduce-cover balance âm nhẹ** — accept + comment.
4. OKX `fee` per-fill vs accumulated: `OrderResult` dùng `accFillSz`/`avgPx` (accumulated) → map accumulated `fee`. Verify payload thật (demo mode) khi impl.

## 9. Unresolved (chuyển R sau)
- `feeCcy != quote` (fee trả OKB / cross-margin) — R3 giả định quote, gap FX chưa xử. Verify khi OKX live thật.
- Funding fee perpetual parity gap — mở tới khi có funding data (không R cụ thể).
- OKX Trade source (orders/positions/history) + side mapping — R4.
