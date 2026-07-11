---
phase: 8
title: "CLI orchestration & persist"
status: completed
priority: P1
dependencies: [7]
---

# Phase 8: CLI orchestration & persist

## Overview

Entry point `run_rubric.py` nối toàn bộ pipeline: load → metric → score → render → (optional) persist. CLI với `--run-id`/`--all-finished`, `--dry-run` (default), `--persist`, `--out`.

## Requirements

- Functional: chạy 1 lệnh ra 4 artifact cho toàn bộ finished run; `--persist` ghi field `scorecard` (top-level MỚI) idempotent.
- Non-functional: `--dry-run` mặc định (không mutate); persist idempotent theo `rubric_version`; per-run isolation (1 run lỗi không abort batch).

## Architecture

```
scripts/rubric/
  run_rubric.py   # argparse CLI, orchestrate pipeline, persist_scorecard()
```

Pipeline mỗi run: `load_run` + `load_trades` (+ `load_bars` cho MAE/MFE) → `empirical_metrics` + `reconciliation` + `robustness` + `trade_path_analysis` + `static_audit` → `scoring.score_run` → collect ScorecardResult.
Sau batch: `render_comparison_table` + per-run `render_scorecard` + JSON + `render_html` → ghi `--out`.

Persist (`--persist`):
- `$set: {"scorecard": {rubric_version, generated_note, axes: {...}, overall_grade, metrics: {...}, audit: {...}, aliases: [...]}}` trên `backtest_runs._id == canonical_id`.
- **KHÔNG đụng** `verdict`/`metrics`/`equity_curve`/`config_snapshot`.
- Idempotent: cùng run + cùng rubric_version → overwrite `scorecard` (không append/duplicate).
- Alias runs (dedup): ghi scorecard vào canonical; alias doc set `scorecard.canonical_ref = canonical_id` (con trỏ, không tính lại).

CLI flags:
- `--run-id ID` (repeatable) | `--all-finished`
- `--out DIR` (default `docs/backtest-rubric/`) [Validation S2] — artifact + methodology gom một chỗ dưới docs/, commit như snapshot.
- `--dry-run` (default True) | `--persist` (opt-in, tắt dry-run)
- `--seed N` (bootstrap reproducibility)

## Related Code Files

- Create: `scripts/rubric/run_rubric.py`
- Uses: tất cả module Phase 1–7

## Implementation Steps

1. argparse: selection (`--run-id`/`--all-finished`), `--out`, `--dry-run`/`--persist`, `--seed`.
2. Resolve run set → dedup (Phase 1) → pipeline mỗi canonical run (try/except per-run, log lỗi, tiếp tục).
3. Render 4 artifact vào `--out`.
4. Nếu `--persist`: `persist_scorecard` cho canonical + alias-ref; đọc lại confirm count. Default dry-run → chỉ in "would persist".
5. Exit code: 0 nếu tất cả run ok; non-zero nếu run nào fail.
6. End-to-end test: `--all-finished --dry-run` → 4 artifact, 5 canonical, không mutate DB.

## Success Criteria

- [ ] `uv run python scripts/rubric/run_rubric.py --all-finished` (dry-run mặc định) → 4 artifact cho 5 canonical run, DB KHÔNG đổi.
- [ ] `--persist` → field `scorecard` xuất hiện trên 5 canonical + alias-ref trên duplicate; `verdict`/`metrics` nguyên vẹn; chạy 2 lần idempotent (không nhân đôi).
- [ ] Per-run isolation: 1 run lỗi (vd bars thiếu) không abort batch; báo trong summary.
- [ ] `ruff` + `pyright` clean toàn `scripts/rubric/`.
- [ ] Artifact reproduce chẩn đoán master-report (engulfing no-edge; hitnrun2 cost-killed).

## Risk Assessment

- **Persist mutate prod**: `--dry-run` mặc định là guard chính. `--persist` phải rõ ràng opt-in. Verify count sau ghi. Field mới `scorecard` không đụng schema hiện có → `from_mongo` bỏ qua, an toàn API/FE.
- **Idempotency**: `$set` overwrite (không `$push`) → chạy lại cùng version an toàn. Đổi version → field `scorecard` mang version mới (overwrite version cũ — chấp nhận, chỉ giữ latest; nếu cần history thì versioned sub-key, nhưng YAGNI giờ).
- **Batch partial failure**: per-run try/except; summary liệt kê fail; exit non-zero để CI/user biết.
- **Concurrency**: nếu recompute script khác đang chạy trên cùng Mongo → chỉ `$set scorecard`, không đụng trade/order collections nên không đụng độ với `recompute_backtest_costs.py`.
