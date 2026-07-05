# Phase 02 — Test Rework + Full Validation Parity

**Priority:** P2 · **Status:** done · Depends: Phase 01.

## Overview

Rework unit test cho collector (giờ cần broker cho `get_balance()`), chạy full validation. Bằng chứng parity = characterization tests engulfing/hitnrun2 pass KHÔNG sửa số.

## Related code files

**Edit:**
- `tests/backtest_test/engine/test_result_collector_mark_to_market.py` — import/class rename + fake broker + `await finalize` + rework `_round_trip`

**Verify pass KHÔNG sửa (parity proof):**
- `tests/backtest_test/engine/test_engulfing_backtest.py` (real BacktestAppService + PaperBrokerAdapter)
- `tests/backtest_test/engine/test_hitnrun2_backtest.py`

## Implementation steps

### 1. Fake broker cho isolation test
Test hiện drive collector standalone (không broker). Post-R5 `on_trade`/`finalize` đọc `broker.get_balance()`. Dựng minimal fake:
```python
from pocketquant.core.domain.brokers.value_objects import AccountBalance

class _FakeBroker:
    """Minimal IBrokerPort stand-in — only get_balance() is exercised.
    Test scripts available_balance to mirror the broker's realized ledger
    (initial − Σcommission + Σpnl) as fills/trades are fed to the collector."""
    def __init__(self, balance: float) -> None:
        self.available_balance = balance
        self.total_equity = balance
    async def get_balance(self) -> AccountBalance:
        return AccountBalance(
            total_equity=self.total_equity,
            available_balance=self.available_balance,
            currency="USD",
            unrealized_pnl=self.total_equity - self.available_balance,
        )
```
(Không cần implement full `IBrokerPort` — collector chỉ gọi `get_balance()`. Nếu pyright than thiếu method, dùng `# type: ignore[arg-type]` tại ctor call hoặc typed protocol nhỏ — ưu tiên duck-typing đơn giản.)

### 2. Rework `_round_trip`
- `c = BacktestReportAppService(_config(), initial_capital=10_000.0, broker=broker, run_id=_oid("run"))`.
- Trước mỗi `on_trade`, set `broker.available_balance` = realized-equity kỳ vọng sau close (mirror broker: `10_000 − entry_comm − exit_comm + pnl`). Đây chính là số cũ `_current_equity` sẽ có.
- `mark_to_market` calls: set `broker.total_equity` (wild swings) độc lập với `available_balance` → chứng minh MTM không đụng realized curve.
- `await c.finalize(...)` (async): set `broker.available_balance` = final realized trước finalize.

### 3. Invariants giữ trong test (mạnh hơn sau gut)
- **MTM không mutate realized accounting** → total_return/cagr/max_drawdown/win_rate/profit_factor byte-identical với/không MTM. Giờ trivially-true (collector không còn realized accounting nội bộ) nhưng VẪN assert: realized curve chỉ từ `on_trade` broker read, MTM chỉ vào `_mtm_curve`.
- Sharpe/Sortino dùng MTM curve khi có.
- Persisted equity_curve cap ≤ 5000 (`_MAX_PERSISTED_EQUITY_POINTS`).

### 4. Docstring test
"BacktestResultAppService mark-to-market" → "BacktestReportAppService mark-to-market". Filename giữ (minimal churn) — nội dung update.

## Validation (toàn bộ phải xanh)

```
just test                 # 560 pass; engulfing/hitnrun2 số KHÔNG đổi
ruff check .
pyright
lint-imports              # 8 contract
```

Nếu engulfing/hitnrun2 đổi số → Approach A sai đâu đó (broker read lệch shadow) → DỪNG, debug (không sửa expected number để pass).

## Todo
- [x] `_FakeBroker` với `get_balance()`
- [x] Rework `_round_trip` (script balance + `await finalize`)
- [x] Rename import/class/docstring trong test
- [x] Assert 3 invariant (MTM-isolation, Sharpe-from-MTM, cap ≤5000)
- [x] `just test` xanh, engulfing/hitnrun2 số không đổi
- [x] ruff + pyright + lint-imports xanh

## Success criteria
- Full suite xanh; characterization engulfing/hitnrun2 pass KHÔNG chỉnh expected.
- Test isolation dùng fake broker, không phụ thuộc PaperBrokerAdapter thật.
