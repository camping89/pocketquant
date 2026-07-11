---
phase: 4
title: "Trade-path MAE/MFE"
status: completed
priority: P2
dependencies: [1]
---

# Phase 4: Trade-path MAE/MFE

## Overview

Tính MAE/MFE cho mỗi trade bằng cách quét `bars` intrabar giữa entry_time và exit_time, rồi suy ra MFE capture rate + MAE-to-stop ratio. Đây là phần reconciliation design-vs-realized đo bằng số (trả lời trực tiếp câu hỏi "dùng definition"). Offline, cho run cũ — độc lập với plan engine `260630-0031`.

## Requirements

- Functional: per-trade MAE (biên nghịch xa nhất), MFE (biên thuận xa nhất) từ bar high/low trong [entry_time, exit_time]; capture rate + MAE-to-stop aggregate.
- Non-functional: no-lookahead (chỉ bars trong khoảng trade), xử lý same-bar entry+exit, vectorize theo run (load bars 1 lần, slice theo trade).

## Architecture

```
scripts/rubric/
  trade_path_analysis.py   # compute_excursions(trades, bars) -> per-trade MAE/MFE + aggregate diagnostics
```

Logic (theo MAE/MFE methodology, brainstorm):
- Với mỗi trade, slice bars có `entry_time ≤ datetime ≤ exit_time`.
- LONG: `MFE = max(high) − entry`, `MAE = min(low) − entry` (≤0). SHORT mirror: `MFE = entry − min(low)`, `MAE = entry − max(high)`.
- Chuẩn hoá về R nếu có sl: `MAE_R = MAE / |entry − sl|`, `MFE_R = MFE / |entry − sl|`.
- **MFE capture rate** = actual_exit_profit / MFE (per winning trade; aggregate mean trên winners).
- **MAE-to-stop ratio** = mean(|MAE|) / mean(stop_distance), stop_distance = |entry − sl|.
- Same-bar entry+exit (duration < 1 bar): dùng bar đó (high/low của bar chứa cả entry+exit) — không để MAE/MFE=0 sai.

## Related Code Files

- Create: `scripts/rubric/trade_path_analysis.py`
- Uses: `data_access.load_bars` (Phase 1), `TradeRow` (Phase 1)

## Implementation Steps

1. `compute_excursions(trades, bars)`: build datetime→index cho bars (sorted); mỗi trade bisect [entry,exit] → slice → MAE/MFE theo direction.
2. Chuẩn hoá R (khi có sl), tính capture rate (winners), MAE-to-stop (all).
3. Same-bar guard: nếu slice rỗng hoặc 1 bar → dùng bar chứa entry_time.
4. Aggregate: `{mfe_capture_mean, mae_to_stop_mean, mae_R_p50/p90, mfe_R_p50/p90}`.
5. Unit test: synthetic bars + trade đã biết → MAE/MFE đúng dấu; same-bar case; SHORT mirror.

## Success Criteria

- [ ] LONG & SHORT MAE/MFE đúng dấu trên synthetic fixture.
- [ ] Same-bar entry+exit không cho 0 sai (dùng bar high/low).
- [ ] `019f36d2`: MAE-to-stop ratio cao (khớp master-report "SL 14 bps quá chật, 57% bị quét") — bằng chứng định lượng.
- [ ] MFE capture rate tính trên winners, ∈ [0,1] (hoặc >1 nếu exit vượt MFE do slippage — clamp/note).
- [ ] Chạy trong thời gian hợp lý (bars load 1 lần/run, không N queries).

## Risk Assessment

- **Bars gap** (thiếu bar giữa entry/exit) → slice thiếu → MAE/MFE dưới ước lượng. Mitigation: đếm bars-in-window vs expected theo interval; cờ `low_coverage` nếu thiếu nhiều.
- **entry_time không khớp bar boundary exactly**: dùng bisect [entry, exit] inclusive; entry bar có thể chứa entry giữa bar → chấp nhận (offline approximation, note trong output).
- **Overlap plan `260630-0031`**: plan đó track excursion trong engine (chính xác hơn, forward-only). Rubric = offline approximation cho run cũ. KHÔNG mâu thuẫn; nếu engine field có sau, rubric đọc thẳng thay vì tự tính. Ghi rõ approximation trong scorecard.
