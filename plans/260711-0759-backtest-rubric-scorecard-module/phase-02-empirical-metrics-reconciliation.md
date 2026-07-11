---
phase: 2
title: "Empirical metrics & reconciliation"
status: completed
priority: P1
dependencies: [1]
---

# Phase 2: Empirical metrics & reconciliation

## Overview

Tính bộ metric mở rộng (quantstats formulas) từ trades + equity_curve, và lớp reconciliation tách gross-vs-net edge + planned-vs-realized R:R. Đây là trục **Performance** + phần định lượng của **Design-integrity**.

## Requirements

- Functional: mọi metric có công thức trong brainstorm, DRY reuse `PerformanceCalculatorDomainService` cho phần đã có.
- Functional: reconciliation tính planned R:R (từ per-trade sl/tp/entry), realized R-multiple, gross edge vs net edge (bps).
- Non-functional: pure functions numpy, không side-effect, xử lý edge case (empty, division-by-zero) trả 0/None rõ ràng.

## Architecture

```
scripts/rubric/
  empirical_metrics.py   # calmar, mar, ulcer_index, ulcer_perf_index, tail_ratio, common_sense_ratio,
                         # cpc_index, gain_to_pain, recovery_factor, kelly, risk_of_ruin, sqn, cost_to_edge
  reconciliation.py      # planned_rr, realized_r_multiple, gross_vs_net_edge_bps
```

Công thức (authoritative, quantstats/stats.py):
- `calmar = cagr / |max_drawdown|`
- `ulcer_index = sqrt(Σ drawdown_series² / (n−1))` — drawdown_series đã có trong equity_curve doc (field `drawdown`) hoặc tính lại từ equity qua `PerformanceCalculatorDomainService.drawdown_series`.
- `ulcer_perf_index = (total_return − rf) / ulcer_index` (rf=0)
- `tail_ratio = |quantile(returns,0.95) / quantile(returns,0.05)|` — returns = per-trade pnl/notional (bps) hoặc equity-curve returns.
- `common_sense_ratio = profit_factor × tail_ratio`
- `cpc_index = profit_factor × win_rate × win_loss_ratio` (win_loss_ratio = avg_win/|avg_loss|)
- `gain_to_pain = Σreturns / |Σ neg returns|`
- `recovery_factor = |Σreturns| / |max_drawdown|`
- `kelly = ((wl_ratio·win_p) − (1−win_p)) / wl_ratio`
- `risk_of_ruin = ((1−wr)/(1+wr))^n` — cap n để tránh underflow (dùng log-space nếu cần).
- `sqn = (expectancy_R / std_R) × sqrt(n)` — expectancy_R, std_R theo R-multiple từ reconciliation.
- `cost_to_edge = gross_edge_bps / friction_bps` (friction = commission+slippage round-trip từ config_snapshot).

Reconciliation (`reconciliation.py`):
- `planned_rr(trade) = |tp − entry| / |entry − sl|` (None nếu thiếu sl/tp).
- `realized_r_multiple(trade) = pnl_price_move / |entry − sl|` where pnl_price_move signed theo direction; None nếu thiếu sl.
- `gross_vs_net_edge_bps(trades, commission_bps, slippage_bps)`: gross = mean(signed price move / entry × 1e4); net = gross − friction. Tách để lộ "cost-killed" vs "no edge".

## Related Code Files

- Create: `scripts/rubric/empirical_metrics.py`, `scripts/rubric/reconciliation.py`
- Reuse (import as pure funcs): `src/pocketquant/core/domain/trading/performance_calculator_domain_service.py` (profit_factor, drawdown_series, max_drawdown, win_rate, average_win_loss)

## Implementation Steps

1. `empirical_metrics.py`: 13 pure functions trên. Reuse PerformanceCalculator cho profit_factor/drawdown_series/max_drawdown/win_rate/average_win_loss; chỉ viết mới phần thiếu.
2. `reconciliation.py`: planned_rr, realized_r_multiple (per-trade + aggregate mean/median), gross_vs_net_edge_bps.
3. Edge cases: empty trades → tất cả 0/None; gross_loss=0 → profit_factor cap (đã có trong PerformanceCalculator); ulcer n<2 → 0.
4. Unit test: giá trị đã biết (vd tail_ratio của array đối xứng ≈ 1; calmar khớp cagr/maxdd thủ công). [Validation S2] Mọi test module này đặt dưới **`tests/scripts/rubric/`** (cây tests/ chuẩn, vào default `just test`); import chỉ pure math (không DB — connection lazy Phase 1).

## Success Criteria

- [ ] 13 metric + 3 reconciliation function pass unit test với input đã biết.
- [ ] `019f36d2` reconciliation: planned R:R median ≈ 1.57, realized R-multiple âm (khớp master-report).
- [ ] `hitnrun2`: cost_to_edge < 1 dù profit_factor 2.11 (lộ cost-killed); `engulfing`: gross edge ≈ 0 (no edge).
- [ ] Không NaN/inf lọt ra (cap/guard hết).

## Risk Assessment

- **Returns definition ambiguity**: per-trade pnl/notional vs equity-curve returns cho khác kết quả. Chốt: tail_ratio/gain_to_pain trên **per-trade returns (bps)**; ulcer/calmar trên **equity_curve** (drawdown-based). Ghi rõ trong docstring mỗi hàm.
- **risk_of_ruin underflow** với n lớn (8629) → dùng log-space hoặc cap, không để về 0 âm thầm.
- **Divergence với PerformanceCalculator** nếu tự viết lại profit_factor → BẮT BUỘC reuse, không re-implement (DRY + tránh lệch số).
