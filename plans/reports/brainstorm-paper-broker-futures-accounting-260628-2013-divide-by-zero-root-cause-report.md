# Brainstorm: PaperBroker futures-accounting fix (root cause của divide-by-zero)

**Loại:** brainstorm / design hand-off cho `/ck:plan`
**Nguồn:** `plans/reports/follow-up-tech-debt-260628-2009-performance-calculator-divide-by-zero-report.md`
**Modes:** (none — no `--html`/`--wiki`)
**Quyết định chốt:** Scope **C** (fix cả 2 bug) · Model **C-futures** · Document accounting models trong `docs/` · Giữ guard tại `performance_calculator` (defense-in-depth)

---

## Problem statement

Report gốc chẩn đoán divide-by-zero ở `performance_calculator.sharpe_ratio/sortino_ratio` là **Low / cosmetic / kết quả vẫn đúng nhờ guard**. Reproduce + trace bác bỏ chẩn đoán đó: điểm `0` trong equity curve là **triệu chứng của 2 bug accounting thật trong `PaperBroker`**, và chúng làm **sai số liệu** (drawdown, Sharpe, Sortino, exposure), không chỉ noise.

### Reproduce (đã xác minh)

`PYTHONWARNINGS=error::RuntimeWarning` → test crash tại `performance_calculator.py:80` (`divide by zero`). Dump `returns_curve` (MTM): điểm `0` ở **index 7, 16, 25** — mỗi cycle 1 lần, đúng tại bar mở vị thế full-exposure. Curve nhảy `10000 → 0 → 10356`.

---

## Root cause: 2 bug = 1 nguồn (trộn 2 mô hình kế toán)

`PaperBroker` hạch toán fill theo **mô hình spot/cash** nhưng tính equity theo **mô hình futures** → mâu thuẫn nội tại.

| | Vị trí | Hành vi |
|---|---|---|
| Cash flow | `_execute_fill` `:469-492` | BUY: `_balance -= order_value`; SELL: `_balance += order_value` (full notional — spot) |
| Equity | `get_balance` `:387` | `total_equity = _balance + unrealized` (futures) |

### Bug 1 — `total_equity` rớt về ~0 khi mở vị thế all-in

Mở long `max_exposure=1.0`: `_balance` trừ hết notional → ~0. Tại bar entry `unrealized=0` (entry==current) → `total_equity ≈ 0`.
**Hệ quả:** MTM equity curve có điểm `0` → `np.diff/equity[:-1]` chia 0 → `inf/nan` → `np.std` ra `nan` → guard `np.isnan` ép Sharpe/Sortino về **`0.0` (sai, không phải "đúng")**; drawdown trên curve = **giả -100%**.

### Bug 2 — double-count `realized_pnl` khi đóng vị thế

`reduce_quantity` cộng `realized_pnl` vào position, rồi `_execute_fill` lại `_balance += live.realized_pnl` **sau khi** đã `+= order_value` (proceeds đã chứa pnl).

Verify bằng số (engulfing test, 3 cycle long, pnl mỗi cycle = 178.15 / 184.50 / 191.07):

```
broker balance hiện tại = 11107.4  = 10000 + 2×(178.15+184.50+191.07)   ← sai +5.5%
đúng phải là            = 10553.7  = 10000 + 1×(178.15+184.50+191.07)
```

Trace short + partial-close (đã kiểm theo yêu cầu) → **double-count xảy ra cho cả long, short, và partial close** (mọi nhánh có `live is not None`).

### Blast radius

`total_equity` consumers ngoài backtest metrics:
- `engine/handlers/risk/check_risk/handler.py:72,120` — exposure sizing + risk check
- `engine/app_services/strategy_app_service.py:336`

→ ảnh hưởng **cả forward-test (paper broker)**, không riêng backtest. Live (`OKXBroker`) **không dính** — balance lấy từ sàn thật.

### Điểm không sai (giữ nguyên)

`BacktestMetrics.total_return`/`cagr` dùng `collector._current_equity` (đường tính độc lập, `+= pnl` đúng 1 lần) → **đúng**. Chỉ MTM-derived metrics (persisted curve + drawdown trên nó + Sharpe + Sortino) và forward exposure bị nhiễm.

---

## Approaches đã cân nhắc

| Approach | Nội dung | Verdict |
|---|---|---|
| **A — guard warning** (report gốc) | `np.divide(..., where=prev!=0)` 2 callsite | ❌ Chỉ giấu triệu chứng; equity/Sharpe/exposure vẫn sai; bug broker còn nguyên cho forward |
| **B — fix Bug 1 tại nguồn** | `get_balance = balance + Σ market_value` | ⚠️ Vá điểm 0 + drawdown + exposure, nhưng để Bug 2 lại; công thức spot cho short rối |
| **C-spot** | xóa double-count + `total_equity = balance + Σ signed_market_value` | ⚠️ Vá 2 tầng, công thức short rối, giữ test cũ nhưng để nợ kỹ thuật |
| **C-futures** ✅ | chuyển hẳn sang margin model | ✅ 1 mô hình nhất quán, xóa cả 2 bug, khớp domain (perp/futures) |

---

## Giải pháp chốt: C-futures (margin model)

### Thay đổi `_execute_fill` (`:458-504`)

- **Open** (long/short mới): **KHÔNG đụng `_balance`**. Chỉ tạo `PositionAggregate`.
- **Close / reduce**: `_balance += live.realized_pnl` (chỉ realized — bỏ `± order_value`).
- **Add** (tăng vị thế cùng chiều): không đụng `_balance`.

→ Notional không còn chảy qua `_balance`; double-count biến mất; balance khởi điểm giữ nguyên cho tới khi có realized pnl.

### `get_balance` (`:387`) — giữ nguyên

`total_equity = _balance + unrealized` **tự đúng cho cả long lẫn short** dưới margin model (không cần signed market value). Đây là điểm đẹp nhất của C-futures.

### `_can_afford` (`:441-444`) — đổi semantics

Spot: `fill_price·qty ≤ _balance`. Futures (leverage 1×): notional ≤ `total_equity` (`_balance + unrealized`). Cần xác nhận margin assumption khi plan (mặc định 1× — không leverage; giữ guard "không vào lệnh quá equity").

### Guard tại `performance_calculator` (defense-in-depth)

Sau fix broker, curve không còn `0`, nhưng **vẫn thêm** guard 1 dòng/callsite phòng input bất thường tương lai (data thật, interval lạ):

```python
prev = equity_curve[:-1]
returns = np.divide(np.diff(equity_curve), prev, out=np.zeros(len(prev)), where=prev != 0)
```

### Tài liệu hoá (`docs/`)

Thêm mục mô tả **margin (futures) vs spot accounting** và lý do PaperBroker theo futures (khớp `OKXBroker` perp domain). Đích đề xuất: `docs/system-architecture.md` (đã có bảng broker ở `:304`, `:444`, `:526`) — thêm sub-section accounting model. AS-IS, bullet/bảng, không changelog.

---

## Implementation considerations & risks

| Risk | Mitigation |
|---|---|
| Đổi core broker dùng chung forward-test | Regression: long/short/partial round-trip assert balance + total_equity bằng số kỳ vọng |
| Characterization test `test_market_buy_applies_slippage_and_debits_balance` (`:93`) pin hành vi spot (`available_balance == 1M − cost`) | **Update test** — nó đang khóa hành vi sai; dưới futures `available_balance` không trừ notional khi mở. Đây đúng loại test cần đổi, không phải regression |
| `available_balance` semantics đổi | Định nghĩa lại rõ trong code comment + docs (available = free margin) |
| Có chỗ khác ngầm dựa vào số sai hiện tại | Grep `available_balance` consumers; chạy full `just test` |
| `_can_afford` đổi có thể cho vào lệnh trước đây bị reject | Kiểm test sizing/exposure; xác nhận margin 1× |

### Files touchpoints

| File | Hành động |
|---|---|
| `core/infra/brokers/paper/paper_broker.py` | `_execute_fill` (open không đụng balance; reduce chỉ += realized), `_can_afford` (equity-based) |
| `backtest/domain/services/performance_calculator.py` | guard `np.divide` ở `sharpe_ratio:80` + `sortino_ratio:122` |
| `tests/core_test/infra/brokers/paper_broker_fills_characterization_test.py` | update `debits_balance` assertion sang futures semantics |
| `tests/backtest_test/engine/test_engulfing_backtest.py` | thêm assert curve > 0 + Sharpe finite non-zero khi có biến động |
| `docs/system-architecture.md` | sub-section margin vs spot accounting |
| (new) regression test | long/short/partial round-trip balance + total_equity bằng số |

---

## Success metrics & validation

- `PYTHONWARNINGS=error::RuntimeWarning just test` → **no divide-by-zero**.
- Engulfing test: balance cuối = `10000 + Σ pnl` (đúng 1×), MTM curve mọi điểm `> 0`.
- Sharpe/Sortino **finite và khác 0** khi có biến động thật (không còn bị nuốt về 0).
- `max_drawdown` phản ánh swing thật, không còn -100% giả.
- Short + partial-close round-trip balance đúng (regression test mới).
- `just test` + `just lint` + `just types` xanh; import-linter 7 contracts không vỡ.

---

## Next steps

1. `/ck:plan --tdd` — TDD vì refactor core broker logic có test coverage hiện hữu cần khóa (characterization + cascade); tests-first chốt hành vi đúng trước khi đổi.
2. Plan phải tách phase: (a) regression test long/short/partial pin hành vi **đúng**, (b) fix `_execute_fill` + `_can_afford`, (c) guard calculator, (d) update characterization test, (e) docs.

---

## Unresolved questions

- **Margin model:** PaperBroker leverage cố định 1× hay cần tham số leverage? (mặc định đề xuất 1×, không margin call — khớp backtest hiện tại). Cần chốt trước khi sửa `_can_afford`.
- **`available_balance` semantics mới:** dưới futures = free margin. Có consumer nào (UI/forward) hiển thị `available_balance` như "cash spendable" không? — grep FE + reconcile trước khi đổi.
- **OKXBroker parity:** OKX trả balance từ sàn (perp) — xác nhận `total_equity` mapping (`okx_mapper` field `eq`) đã là equity-with-unrealized để PaperBroker khớp semantics, tránh lệch forward↔live.
