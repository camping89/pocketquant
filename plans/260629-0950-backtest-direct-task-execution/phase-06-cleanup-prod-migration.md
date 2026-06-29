---
phase: 6
title: "Cleanup & prod migration"
status: pending
effort: ""
---

# Phase 6: Cleanup & prod migration

## Overview

Verify end-to-end với VPS data (NEW local build), migrate prod docs cũ sang vocab mới (H3), drop 2 collection mồ côi AN TOÀN sau bake window (H4), update docs. Áp dụng red-team H3, H4, M3.

## Requirements

- Functional: chạy thật 1 single backtest `/backtest/run` cạnh VPS data (NEW build), verify `started→finished` + 3-collection persist + run_id invariant.
- Functional (H3): migrate prod `backtest_runs` docs cũ `completed→finished`, `running→started`.
- Functional (H4): drop `backtest_optimization_runs` + `backtest_requests` chỉ SAU khi VPS chạy new image + bake window + queue drained.
- Non-functional (M3): re-smoke dùng `/backtest/run` (NEW direct-task, không cần ENABLE_JOBS); drop dùng explicit prod conn string (KHÔNG qua `.env`); .env discipline.

## Architecture

### Verify flow (M3 — NEW build, direct-task)
```
# NEW local build (post phase 2) — /run là direct-task, KHÔNG cần ENABLE_JOBS
cp .env .env.allsafe.bak → cp remote-db.env .env (VPS Mongo)
just be → POST /backtest/run engulfing BTCUSDT:BINANCE 1m (cửa sổ nhỏ vài nghìn bars)
poll GET /backtest/{run_id} → started → finished
verify backtest_runs + orders + trades có run_id (== invariant C2)
verify sandbox isolation: live positions/orders count unchanged
stop backend → restore .env all-local → rm .env.allsafe.bak → grep localhost .env
```
LƯU Ý M3: re-smoke cũ dùng `/optimize` (memory note) — nay đã xóa. Cập nhật memory note: re-smoke = `/backtest/run` NEW build.

### Migration prod docs (H3)
```
# explicit prod conn string, KHÔNG dùng .env
mongosh "<prod-uri>" → 
  db.backtest_runs.updateMany({status:"completed"}, {$set:{status:"finished"}})
  db.backtest_runs.updateMany({status:"running"}, {$set:{status:"failed", error_message:"interrupted_by_migration"}})
```
(running cũ = orphan từ code cũ → failed, không phải started.)

### Drop migration (H4 — sau bake)
GATE trước drop:
1. Confirm VPS container chạy NEW image (deployed SHA qua verify report).
2. `db.backtest_requests.countDocuments({status:"pending"})` == 0 + không doc claimed gần đây.
3. Bake window (vài giờ/1 ngày) — đảm bảo không rollback IMAGE_TAG về old code (old code cần collection).
4. User confirm.
Rồi: drop `backtest_optimization_runs` + `backtest_requests` (log count trước/sau). Đây là bước IRREVERSIBLE cuối cùng.

## Related Code Files

- Modify: `docs/system-architecture.md` — backtest execution = single-run direct-task (bỏ queue/optimize/run-all); subscription = forward-only. AS-IS.
- Modify: `README.md` — cập nhật strategy/backtest section nếu đề cập optimize/queue/run-all.
- Modify: memory note `prod-resmoke-and-env-discipline` — re-smoke = `/backtest/run` NEW build (không phải /optimize); drop dùng explicit conn string.
- Read: memory `prod-resmoke-and-env-discipline`, deploy pipeline (`.github/workflows/cicd.yml`).
- Migration: chạy mongosh tay (explicit conn string), log count. KHÔNG tạo md ngoài plans/docs.

## Implementation Steps

1. Verify backend (phase 2-5 xanh) trước khi đụng prod.
2. Backup `.env` → swap remote-db (force cp tránh alias `cp -i`) → verify VPS.
3. `just be` (NEW build) → poll `/health` 200.
4. `POST /backtest/run` engulfing 1m (cửa sổ nhỏ) → poll → finished. Verify 3-collection + run_id invariant + sandbox isolation.
5. Stop backend → restore `.env` all-local → rm backup → `grep localhost .env`.
6. Deploy phases 2-5 (merge develop → auto-deploy). Confirm VPS new image live.
7. H3 migration: explicit prod conn → updateMany completed→finished, running→failed. Log counts.
8. H4 GATE: confirm new image + queue drained + bake window + user confirm → drop 2 collection (log count). IRREVERSIBLE last.
9. Update `docs/system-architecture.md` + README + memory note (AS-IS, no changelog).
10. `/ck:project-management` sync-back; `/ck:journal`.

## Success Criteria

- [ ] `/backtest/run` chạy thật cạnh VPS (NEW build): started→finished, 3-collection persist, run_id invariant (C2).
- [ ] Sandbox isolation: live positions/orders count unchanged.
- [ ] H3: prod docs cũ migrated (completed→finished, running→failed); counts logged.
- [ ] H4: 2 collection dropped sau bake + user confirm; counts logged.
- [ ] `.env` restored all-local; không backup sót; không secret commit.
- [ ] Docs + memory note phản ánh single-run direct-task (AS-IS).

## Risk Assessment

- **Risk (H4)**: drop khi VPS old code còn write backtest_requests → lost request/index lệch. Mitigation: GATE (new image + drained + bake + confirm); drop là bước cuối.
- **Risk (H4)**: rollback IMAGE_TAG sau drop → old code crash thiếu collection. Mitigation: bake window đủ dài để loại khả năng rollback; drop sau khi chắc chắn không rollback.
- **Risk (H3)**: migration sót doc → FE render "none". Mitigation: updateMany cả completed + running; verify count = 0 còn lại.
- **Risk (M3)**: quên restore .env → trỏ prod (đã xảy ra trước). Mitigation: backup-before-swap, restore bắt buộc, grep localhost cuối; drop dùng explicit conn string (không qua .env).
- **Risk**: `/dev/tcp` false-negative probe VPS (memory). Mitigation: dùng driver thật (mongosh/curl).
