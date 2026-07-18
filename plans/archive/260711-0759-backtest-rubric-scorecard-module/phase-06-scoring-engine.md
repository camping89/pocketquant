---
phase: 6
title: "Scoring engine"
status: completed
priority: P1
dependencies: [2, 3, 4, 5]
---

# Phase 6: Scoring engine

## Overview

Chuyển metric thô từ Phase 2–5 thành điểm 0–4/metric qua threshold ngành. Hai cấp gộp: metric→axis bằng **weighted-sum** (mỗi trục), axis→overall bằng **min (weakest-axis)**. Grade A–F. Đây là "rubric" thật — bảng threshold versioned, mọi điểm truy về 1 số + 1 ngưỡng.

## Requirements

- Functional: threshold table cho mọi metric → điểm 0–4; weight/trục → axis grade A–F; tổng hợp overall grade.
- Non-functional: `rubric_version` versioned; đổi threshold/weight ⇒ bump version; scoring thuần (deterministic, không ML, không tối ưu).

## Architecture

```
scripts/rubric/
  scoring.py   # RUBRIC_VERSION, THRESHOLDS, WEIGHTS, score_metric(), score_axis(), score_run()
```

- `RUBRIC_VERSION = "1.0.0"` (string, persist kèm scorecard).
- `THRESHOLDS`: dict metric → list mốc (band → điểm 0–4). Ví dụ:
  - `calmar`: <0→0, 0–1→1, 1–2→2, 2–3→3, >3→4.
  - `ulcer_index`: >15→0, 10–15→1, 5–10→2, 2–5→3, <2→4 (đảo chiều — thấp tốt).
  - `sqn`: <1→0, 1–1.6→1, 1.6–2→2, 2–3→3, >3→4.
  - `psr`: <0.5→0, 0.5–0.75→1, 0.75–0.9→2, 0.9–0.95→3, >0.95→4.
  - `cost_to_edge`: <0.5→0 … >1.5→4. `mfe_capture`: <0.3→0 … >0.75→4. `mae_to_stop`: ngoài [0.5,0.85]→penalize.
  - DoF (Gray-penalty): nhiều param → trừ điểm design-integrity.
- `WEIGHTS`: mỗi trục có weight/metric (sum=1). 3 trục: performance, robustness, design_integrity.
- `score_axis(metrics) -> (score_0_4, grade)`; `score_run(all) -> ScorecardResult` (3 axis grades + overall + per-metric breakdown).
- Grade map: [3.5,4]→A, [2.5,3.5)→B, [1.5,2.5)→C, [0.5,1.5)→D, [0,0.5)→F.
- **[Validation S1] Overall grade = weakest-axis dominates**: `overall_score = min(3 axis scores)` (hoặc gần min — vd `0.7·min + 0.3·mean` nếu cần mượt, nhưng ưu tiên thuần min cho rõ triết lý). KHÔNG weighted-average 3 trục (che dấu điểm F). Robustness F ⇒ overall ≤ D dù performance A.
- **crypto-1m caveat** carried as metadata (threshold gốc equity/daily).

## Related Code Files

- Create: `scripts/rubric/scoring.py`
- Create: `docs/backtest-rubric/methodology.md` [Validation S1] — reference doc (English, per rule docs/=English): threshold table + công thức + diễn giải 3 trục + weakest-axis rationale + crypto-1m caveat; header ghi `RUBRIC_VERSION` khớp `scoring.py`.
- Uses: outputs của Phase 2–5 (empirical_metrics, robustness, trade_path_analysis, static_audit)

## Implementation Steps

1. Define `THRESHOLDS` (band table) + `WEIGHTS` per axis, versioned constant.
2. `score_metric(name, value)`: map value → band → 0–4; handle None (metric N/A → loại khỏi weighted-sum, re-normalize weight).
3. `score_axis`: weighted-sum → 0–4 → grade.
4. `score_run`: gọi 3 axis + `overall = min(3 axis scores)` (weakest-axis); đóng gói `ScorecardResult` (breakdown đầy đủ để render giải thích được).
5. Viết `docs/backtest-rubric/methodology.md`: threshold table (đồng bộ `THRESHOLDS`), công thức 3 trục, weakest-axis rationale, crypto-1m caveat, `RUBRIC_VERSION` header.
6. Unit test: run tổng hợp giả với metric đã biết → grade đúng; None metric re-normalize đúng; case robustness=F + performance=A → overall ≤ D (weakest-axis đúng).

## Success Criteria

- [ ] `score_run` cho 5 canonical run: mỗi run 3 axis grade + overall (=min 3 trục), breakdown truy về threshold.
- [ ] `engulfing` → design-integrity/performance thấp (no edge); `hitnrun2` → performance kéo xuống bởi cost-to-edge dù robustness khá (profit_factor cao) → lộ cost-killed.
- [ ] None metric (vd MAE/MFE low_coverage) → loại + re-normalize, không cho điểm 0 oan.
- [ ] `RUBRIC_VERSION` xuất hiện trong mọi ScorecardResult VÀ header `docs/backtest-rubric/methodology.md`.
- [ ] `docs/backtest-rubric/methodology.md` tồn tại, threshold table khớp `THRESHOLDS` trong code.
- [ ] Weakest-axis: test case robustness=F + performance=A → overall ≤ D.

## Risk Assessment

- **Threshold arbitrariness**: điểm phụ thuộc band do người đặt. Mitigation: band từ nguồn ngành (brainstorm sources), versioned, in threshold-table kèm output để người đọc tự phán. KHÔNG tự-hiệu-chuẩn từ n=6.
- **Weight sensitivity**: đổi weight → đổi grade. Mitigation: weight đơn giản (gần đều), versioned, expose trong output.
- **None handling**: metric N/A cho điểm 0 = phạt oan. BẮT BUỘC re-normalize, test case riêng.
