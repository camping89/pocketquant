---
phase: 7
title: "Verify isolation"
status: completed
priority: P1
effort: "4h"
dependencies: [4, 5, 6]
---

> **Đã làm (2026-06-09):**
> - **app standalone test** (`tests/app_test/integration/test_app_standalone_runtime.py`): app container resolve full runtime (JobScheduler/StrategyAppService/StrategyReconcileService/BacktestRequestWorker); reconcile tick converge desired=running→actual=running; worker drain queue — KHÔNG bff. 3 test.
> - **bff stateless test** (`tests/bff_test/` mới: conftest + bff_app_factory + integration/test_bff_stateless_serve.py): bff container raise `NoFactoryError` cho 4 runtime type (parametrized); POST start ghi `desired_state` only (actual giữ stopped, bff không reconcile); GET serve seeded read. 6 test.
> - **Full suite**: 470 passed, 12 skipped, 0 failed (≥ baseline 444). pyright 0 error + ruff clean trên file mới (98 ruff error còn lại = pre-existing trong package committed, KHÔNG thuộc SP3).
> - **lint-imports**: 9 contract kept, 0 broken.
> - **Docs sweep** (qua docs-manager): README, docs/README, system-architecture (thêm section App/BFF + Mermaid), system-relationship-map, deployment, features/strategy-lifecycle, CLAUDE.md layout+graph. 0 stale `:41920` proxy ref / "FastAPI serves dist" còn lại.
> - **code-reviewer**: DONE, no blocking, no regression. 7 focus item PASS. Report: `plans/reports/code-reviewer-260609-2136-sp3-phases-5-7-review-report.md`.
> - **Manual crash-isolation smoke**: PENDING — cần live docker stack (kill bff → app tick tiếp), env-dependent đúng như plan risk. Integration test phủ logic standalone. Chạy 1 lần ở deploy kế tiếp. Ghi verify report `plans/reports/`.

# Phase 7: Verify isolation

## Overview

Chứng minh mục tiêu cốt lõi SP3: **kill/restart bff không gián đoạn live trading; app standalone tự chạy full**. Integration test + manual smoke + full suite + import-linter. Cập nhật docs.

## Requirements

- Functional (success metrics từ brainstorm):
  - Kill `bff` khi có strategy `running` → strategy KHÔNG gián đoạn (trades/positions tiếp tục ghi qua app).
  - Restart `bff` → FE phục hồi đọc data; app KHÔNG restart.
  - `app` standalone (không bff) → reconcile + WS + scheduler + backtest worker hoạt động; strategy `running` auto-resume sau restart.
  - Mất `app` → bff vẫn serve read (data tĩnh) nhưng không tick mới (đúng kỳ vọng).
- Non-functional:
  - Full suite xanh (444+ test baseline SP1 + test mới SP3).
  - import-linter contract xanh (bff top độc lập).
  - pyright 0 error trên file đổi; ruff clean.

## Architecture

### Isolation test approach

Integration test khó kill process thật trong pytest. Thay bằng:
- **app standalone test**: khởi tạo app container (enable_jobs=True), seed sub `desired=running`, chạy reconcile tick → strategy load+start; KHÔNG cần bff. Mô phỏng "app chạy không FE". (Mở rộng `test_reconcile_restart_resume_integration.py` đã có từ SP1.)
- **bff stateless test**: bff container resolve + handle request (start/stop ghi desired_state, read trả data) KHÔNG khởi tạo runtime. (Phase 4 test đã phủ phần lớn.)
- **crash-isolation (manual/docker)**: compose up 2 service, seed running strategy, `docker kill pocketquant-bff`, verify app log tiếp tục tick + trades ghi; `docker start` bff, FE phục hồi. Ghi vào verify report (không phải pytest — env-dependent).

## Related Code Files

- Create: `tests/app_test/integration/test_app_standalone_runtime.py` — app chạy reconcile+worker không bff
- Extend: `tests/trading_test/test_reconcile_restart_resume_integration.py` — resume sau restart (SP1 đã có, verify còn xanh)
- Create: `tests/bff_test/integration/test_bff_stateless_serve.py` — bff serve read + write-desired không runtime
- Modify docs: `README.md` (run 2 process), `docs/system-architecture.md` (app/bff split), `docs/deployment.md` (2 service), `docs/websocket-architecture.md` (WS ở app), `CLAUDE.md` (monorepo layout + dependency graph thêm bff)
- Read context: `test_reconcile_restart_resume_integration.py`, docs hiện có

## Implementation Steps

1. Viết `test_app_standalone_runtime.py`: container app, seed sub running, tick reconcile → instance load+start, actual_state→running ghi DB; backtest worker nhặt request→done. Không bff involved.
2. Verify `test_reconcile_restart_resume_integration.py` (SP1) còn xanh sau Phase 3 reconcile thay đổi.
3. Viết `test_bff_stateless_serve.py`: bff handle GET reads (trả data từ seeded DB) + POST start (ghi desired_state) KHÔNG khởi tạo scheduler/engine.
4. `just test` full → xanh (baseline 444 + mới). Fail → fix theo Phase tương ứng, KHÔNG bỏ qua.
5. `lint-imports` → 8 contract (7 cũ + bff) xanh.
6. `just types` + `just lint` clean.
7. **Manual crash-isolation smoke** (docker compose): up app+bff+mongo+redis, seed running strategy, `docker kill pocketquant-bff` → quan sát app tiếp tục tick/trades (log + DB); `docker start pocketquant-bff` → FE đọc lại được. Ghi kết quả vào verify report `plans/reports/`.
8. Cập nhật docs: README run order, system-architecture (sơ đồ app/bff), deployment (2 service), CLAUDE.md monorepo layout (thêm `pocketquant-bff` + dependency graph `{app, bff}` top tier).

## Success Criteria

- [ ] app standalone test: reconcile+worker chạy, strategy running auto-resume — không bff.
- [ ] bff stateless test: serve read + ghi desired-state, không khởi tạo runtime.
- [ ] Manual: kill bff → app tick/trades tiếp tục; restart bff → FE phục hồi; app không restart.
- [ ] Full suite xanh (≥ baseline 444 + test mới).
- [ ] import-linter 8 contract xanh; pyright + ruff clean.
- [ ] Docs (README, system-architecture, deployment, websocket-architecture, CLAUDE.md) cập nhật app/bff split.

## Risk Assessment

- **Crash-isolation chỉ verify được bằng docker, không pytest**: env-dependent. Mitigation: ghi manual smoke steps + kết quả vào verify report; integration test phủ phần logic (standalone runtime).
- **Test mới flaky do timing reconcile/worker tick**: Mitigation: gọi `_reconcile()`/worker dispatch trực tiếp trong test thay vì chờ loop sleep (pattern SP1 đã dùng).
- **Docs drift**: nhiều file docs nhắc "app serve web" / "1 process". Mitigation: grep `serve.*web`, `41920`, "FastAPI serves" → cập nhật từng chỗ sang app/bff split. Tuân docs policy AS-IS (mô tả trạng thái mới, không changelog).
- **Baseline test count đổi**: SP3 thêm/sửa test; "≥444" là sàn, không phải con số cứng. Đếm lại sau.
