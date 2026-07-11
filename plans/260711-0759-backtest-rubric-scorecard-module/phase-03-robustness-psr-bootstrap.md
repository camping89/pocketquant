---
phase: 3
title: "Robustness (PSR + bootstrap)"
status: completed
priority: P2
dependencies: [1]
---

# Phase 3: Robustness (PSR + bootstrap)

## Overview

Trục **Robustness**: PSR (Probabilistic Sharpe Ratio, single-series) + bootstrap trade-order → phân bố maxDD. Đo độ tin cậy của kết quả 1 run mà KHÔNG cần sweep. MCPT signal-permutation hoãn (cần replay engine).

## Requirements

- Functional: PSR từ Sharpe + skew + kurtosis + n; bootstrap **permutation thứ tự trade** (sequencing-only, không resample-with-replacement) → phân bố maxDD với percentile.
- Non-functional: normal CDF bằng `math.erf` (không scipy); bootstrap seeded để reproduce; numpy vectorized.

## Architecture

```
scripts/rubric/
  robustness.py   # psr(sr, skew, kurt, n, sr_star=0), bootstrap_max_drawdown(trade_pnls, n_iter=1000, seed=...)
```

Công thức:
- `Φ(x) = 0.5·(1 + erf(x / sqrt(2)))` — stdlib `math.erf`.
- `PSR(SR*) = Φ( (SR − SR*)·sqrt(n−1) / sqrt(1 − γ3·SR + ((γ4−1)/4)·SR²) )`
  - SR = observed Sharpe (từ metrics hoặc PerformanceCalculator), γ3 = skew, γ4 = kurtosis (Fisher? dùng non-excess kurtosis — chú ý định nghĩa; công thức dùng γ4 = kurtosis, với normal γ4=3). Ghi rõ convention trong docstring.
  - SR* = 0 (n=6 run scale, không có benchmark family). Caveat trong output.
- Bootstrap maxDD:
  - Input: array per-trade pnl (USD hoặc bps).
  - Mỗi iter: `np.random.permutation` thứ tự trade → cumulative equity → maxDD (reuse `PerformanceCalculatorDomainService.max_drawdown`).
  - Output: `{observed_maxdd, p50, p95, p99, ratio_p95_to_observed}` — nghiên cứu: real DD thường ~3.1× backtest.

## Related Code Files

- Create: `scripts/rubric/robustness.py`
- Reuse: `src/pocketquant/core/domain/trading/performance_calculator_domain_service.py` (max_drawdown, sharpe_ratio nếu cần recompute)

## Implementation Steps

1. `psr()`: erf-based Φ; guard denominator ≤ 0 (SR quá cao + kurtosis nhỏ) → clamp; return trong [0,1].
2. `bootstrap_max_drawdown()`: seeded RNG, n_iter=1000, permutation → equity cumsum → maxDD; trả percentile dict.
3. Skew/kurtosis: `numpy` (viết helper hoặc dùng công thức moment; KHÔNG cần scipy).
4. Unit test: PSR của chuỗi normal SR=1,n=1000 ≈ giá trị kỳ vọng; bootstrap trên PnL đối xứng cho phân bố hợp lý; seed cố định → reproduce.

## Success Criteria

- [ ] `psr()` khớp reference tính tay (vài case SR/skew/kurt/n) trong sai số ε.
- [ ] Denominator guard: không crash khi SR cao/kurtosis thấp; output luôn ∈ [0,1].
- [ ] `bootstrap_max_drawdown` seeded reproduce; p95 ≥ observed maxDD (worst reorder tệ hơn thực tế).
- [ ] Chạy trên `019f36d2` (8629 trades): PSR thấp (Sharpe âm → PSR ≈ 0), khớp trực giác "không tin cậy".

## Risk Assessment

- **Kurtosis convention** (excess vs raw) sai làm PSR lệch dấu. Mitigation: chốt raw kurtosis (normal=3) khớp công thức gốc; test bằng case đã biết.
- **Bootstrap trade-order ≠ path-dependent reality**: reorder giữ nguyên tập PnL, chỉ đổi thứ tự → đo sequencing risk, KHÔNG đo tail của chính PnL. Ghi rõ đây là sequencing bootstrap. [Validation S1] Chốt **sequencing-only** (permutation) round này — KHÔNG resample-with-replacement (YAGNI).
- **n−1 với n nhỏ**: PSR cho run ít trade (nếu có) kém tin — nhưng mọi run hiện tại >5000 trades nên ổn.
