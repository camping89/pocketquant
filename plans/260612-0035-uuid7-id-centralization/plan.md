---
title: "UUID7 ID centralization — re-key all owned _id to uuid7"
description: "Re-key mọi _id ta sở hữu về UUIDv7 (trừ apscheduler_jobs). 6 phases: WS1 type flip → tracked_symbols → job_history → backtest_requests (bỏ bt: prefix) → backtest_runs cache → subscriptions + FK rewrite. TDD: lock behavior bằng net hiện có trước mỗi phase. Mỗi phase 1 push riêng, migration boot-time idempotent."
status: in-progress
priority: P2
branch: "develop"
tags: [uuid7, mongodb, migration, tdd, data-integrity]
blockedBy: []
blocks: []
created: "2026-06-11T17:42:59.778Z"
createdBy: "ck:plan"
source: skill
---

# UUID7 ID centralization — re-key all owned _id to uuid7

## Overview

Consensus từ [brainstorm report](../reports/brainstorm-260611-2325-uuid7-id-centralization-report.md) (user confirm 2026-06-12): **100% UUIDv7** cho mọi `_id` ta sở hữu, exception duy nhất `apscheduler_jobs` (library-owned, rule §12.6 `docs/code-standards.md`). Supersede `plans/todo/260530-centralize-uuid7-id-strategy.md`.

Pattern chuẩn (đã có ở `Bar`/`Symbol`/`SyncStatus`): entity `id: UUID = Field(default_factory=generate_id)`, `to_mongo()` → `"_id": str(self.id)`, `from_mongo()` → `UUID(doc["_id"])`. Migration = boot-time idempotent trong lifespan (`app/main_extensions.py`, pattern `migrate_strategy_id_fields` đã prove 2 lần).

**Thứ tự phase có lý do:** Phase 4-5 gỡ coupling `_id ← sub_id` của `backtest_requests`/`backtest_runs` TRƯỚC, để Phase 6 (re-key `subscriptions`, blast radius lớn nhất) chỉ còn rewrite FK fields + RAM keys.

**Deviation so với brainstorm (phát hiện khi verify code):** `BacktestResult.id: UUID` chuyển từ Phase 1 sang Phase 5 — `save_for_subscription` (`backtest_repository.py:125`) override `result.id = sub_id` (16-hex, không phải UUID) cho tới khi Phase 5 gỡ; flip type sớm sẽ crash `from_mongo` trên cache docs. End-state không đổi.

**Rollout:** mỗi phase = 1 push → CI deploy → `11-verify.sh` HEALTHY → phase kế. Rollback = revert push (migrations idempotent, side-effect-free khi re-run). Pre-deploy mỗi phase: đếm docs trên VPS (`docker exec pocketquant-mongodb mongosh ...`) + mongodump theo `docs/deployment.md`.

**TDD:** mỗi phase viết/extend tests lock behavior TRƯỚC khi đổi code. Net: `tests/baseline/` (OpenAPI + route inventory snapshot — diff phải rỗng mọi phase), `tests/core_test/`, `tests/engine_test/`, `tests/backtest_test/`.

## Phases

| Phase | Name | Risk | Status |
|-------|------|------|--------|
| 1 | [WS1 representation id str to UUID](./phase-01-ws1-representation-id-str-to-uuid.md) | LOW | Completed (deployed, verify HEALTHY) |
| 2 | [Re-key tracked_symbols](./phase-02-re-key-tracked-symbols.md) | LOW | Completed (deployed, verify HEALTHY) |
| 3 | [Re-key job_history legacy ObjectId](./phase-03-re-key-job-history-legacy-objectid.md) | LOW | Implemented (gates xanh, chờ deploy + verify) |
| 4 | [Re-key backtest_requests drop bt prefix](./phase-04-re-key-backtest-requests-drop-bt-prefix.md) | MED | Pending |
| 5 | [Re-key backtest_runs cache docs](./phase-05-re-key-backtest-runs-cache-docs.md) | MED | Pending |
| 6 | [Re-key subscriptions and FK rewrite](./phase-06-re-key-subscriptions-and-fk-rewrite.md) | HIGH | Pending |

## Key Dependencies

- Phase 4, 5 PHẢI xong trước Phase 6 (gỡ coupling `_id ← sub_id`).
- Phase 1-3 độc lập nhau, nhưng giữ thứ tự để mỗi deploy chỉ có 1 nhóm thay đổi.
- Phase 6 risk cao nhất: 4 FK fields + RAM instance keys + `_SUB_ID_SHAPE` regex guard (`strategy_reconcile_service.py:43`) — quên đổi regex → orphan-unload silent no-op vĩnh viễn.

## Success Metrics (toàn plan)

- `mongosh`: mọi `_id` trong collections ta own match UUID regex (trừ `apscheduler_jobs`).
- Dedup giữ nguyên: add_symbol trùng triple → 409 như cũ; run-all concurrent → 1 pending request/sub.
- Full gates xanh mỗi phase (`just test && just lint && just types && just lint-imports`); OpenAPI + route inventory snapshot diff rỗng.
- `11-verify.sh` HEALTHY sau mỗi deploy.
- Reconcile orphan-unload test pass với UUID shape mới.

## Post-Plan Actions

- Archive `plans/todo/260530-centralize-uuid7-id-strategy.md` (superseded).
- `docs/code-standards.md` §12.6: wording giữ nguyên (1 exception duy nhất) — re-check sau Phase 6.
