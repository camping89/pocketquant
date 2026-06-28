# Follow-up: divide-by-zero trong performance_calculator (flat equity curve)

**Loại:** tech-debt / follow-up ticket candidate
**Phát hiện:** trong khi implement engulfing strategy (commit `060e757`) — backtest test mới chạm tới
**Trạng thái:** chưa fix (ngoài scope plan engulfing) — đề xuất ticket riêng
**Mức độ:** Low (cosmetic warning, kết quả vẫn đúng nhờ guard hạ nguồn)

## Tóm tắt

`PerformanceCalculator.sharpe_ratio` và `sortino_ratio` phát `RuntimeWarning: divide by zero` + `invalid value encountered in subtract` khi equity curve chứa phần tử `0`. Đây là **pre-existing engine code**, KHÔNG phải lỗi engulfing — chỉ là test backtest engulfing mới (`test_engulfing_backtest.py::test_backtest_multi_trade_on_repeated_engulfing_round_trips`) là nơi đầu tiên dùng dữ liệu synthetic tạo equity curve có đoạn flat/0 chạm tới nhánh này.

## Vị trí

| File | Dòng | Code |
|---|---|---|
| `src/pocketquant/backtest/domain/services/performance_calculator.py` | `:80` (`sharpe_ratio`) | `returns = np.diff(equity_curve) / equity_curve[:-1]` |
| `src/pocketquant/backtest/domain/services/performance_calculator.py` | `:122` (`sortino_ratio`) | `returns = np.diff(equity_curve) / equity_curve[:-1]` |

Warning thứ 3 (`numpy/_core/_methods.py:188 invalid value encountered in subtract`) là **hệ quả lan truyền**: `x / 0 → inf/nan`, sau đó `np.std(returns, ddof=1)` trừ `arrmean` trên `inf` → `invalid value`.

## Root cause

- Mẫu số `equity_curve[:-1]` **không guard phần tử `0`**. Khi một điểm equity trong `returns_source` bằng `0`, phép chia phần tử-wise tạo `inf`/`nan`.
- `returns_source` = `returns_curve` (MTM per-bar) nếu có, ngược lại `equity_curve` realized (`metrics_builder.py:32-33`). Dữ liệu synthetic flat (bar không có vị thế → equity không đổi, hoặc điểm khởi tạo `0`) là điều kiện kích hoạt.

## Vì sao kết quả vẫn ĐÚNG (warning vô hại)

Cả 2 hàm có **guard hạ nguồn** bắt `inf`/`nan` trước khi trả về:

```python
# sharpe_ratio :89
if std_return == 0 or np.isnan(std_return):
    return 0.0
```

`sortino_ratio` tương tự (`:131`, `:136-137`). `nan` lan tới `std_return` → `np.isnan` bắt → trả `0.0`. Test `test_backtest_sharpe_bounded_and_realized_metrics_present` (hitnrun2) đã assert Sharpe finite, không NaN/inf → đầu ra vẫn hợp lệ. Vấn đề **chỉ là warning noise** trên stderr, không sai số liệu.

## Đề xuất fix (cho ticket riêng)

Guard mẫu số tại nguồn, 1 dòng mỗi callsite — ví dụ:

```python
prev = equity_curve[:-1]
returns = np.divide(
    np.diff(equity_curve), prev,
    out=np.zeros(len(prev)), where=prev != 0,
)
```

Hoặc gốc hơn: validate equity curve không chứa `0` ở `metrics_builder` trước khi đưa vào calculator (equity từ broker `total_equity` lẽ ra luôn `> 0` sau khi có vốn — điểm `0` có thể là artifact của điểm khởi tạo hoặc MTM trước khi nạp balance, cần xác minh).

## Phạm vi ảnh hưởng

- `sharpe_ratio`, `sortino_ratio` — 2 callsite duy nhất dùng pattern này.
- Tác động runtime: **không** (kết quả đúng nhờ guard). Chỉ ảnh hưởng độ sạch của test output + log.
- Không phá public contract; không đổi schema/metrics.

## Unresolved questions

- Điểm equity `0` đến từ đâu chính xác? (điểm khởi tạo curve, MTM point trước khi nạp balance, hay synthetic-data artifact riêng của test?) — cần trace `result_collector` build curve để chọn giữa "guard tại calculator" vs "validate tại nguồn".
- Có nên thêm assert "equity curve > 0" như invariant ở `metrics_builder` không, hay chấp nhận `0` và guard cục bộ?
