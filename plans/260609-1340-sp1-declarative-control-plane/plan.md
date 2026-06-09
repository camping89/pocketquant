---
title: "SP1 — Declarative Control Plane (Reconcile Loop)"
description: "Move strategy run-state from RAM to Mongo desired_state; app reconciles desired vs actual; restart auto-resumes."
status: completed
priority: P1
branch: "develop"
tags: [control-plane, reconcile, declarative, sp1]
blockedBy: []
blocks: []
created: "2026-06-09T06:49:31.504Z"
createdBy: "ck:plan"
source: skill
---

# SP1 — Declarative Control Plane (Reconcile Loop)

## Overview

Auto-trading run-state hiện sống trong RAM `StrategyAppService`, mất khi restart → FE phải bấm Start lại tay. Chuyển sang declarative: FE/handler ghi `desired_state` vào Mongo; app có reconcile loop so desired (DB) vs actual (RAM) → tự start/stop. Restart → đọc desired → auto-resume. Enabler bắt buộc cho SP3 (tách app/bff): sau SP1, ranh giới 6 handler ↔ runtime là 100% Mongo, không còn command-channel-vào-RAM.

Mô hình controller kiểu Kubernetes:

```
Control plane (desired)              Data plane (market)
 Mongo: subscription.desired_state     Mongo+Redis: bars, quotes,
      ▲              │                   positions, trades
 ghi  │              │ đọc desired            ▲          │
      │              ▼                        │ ghi      │ đọc
  [handler/human] ┌──────────────┐            │          ▼
                  │  reconcile   │────────────┘     [read path]
                  │  loop (app)  │  ghi actual_state về DB
                  └──────────────┘
```

## Locked decisions (user-confirmed 2026-06-09)

| # | Quyết định | Giá trị | Ghi chú |
|---|-----------|---------|---------|
| D1 | Reconcile mech | **Poll** mỗi N giây | Mirror `WsSubscriptionManager` pattern đã có |
| D2 | `desired_state` enum | **2 trạng thái** `running`/`stopped` | YAGNI, mở rộng sau |
| D3 | Persist actual_state? | **CÓ** — persist cả `desired_state` + `actual_state` | Reconcile ghi actual về DB; `list_symbols` đọc DB, bỏ coupling RAM (SP3-ready) |
| D4 | Frozen dataclass | Giữ `frozen=True`, dùng `dataclasses.replace` | Không bỏ frozen |
| Migration | Old docs default | **`desired_state=running`** (auto-resume tất cả) | ⚠️ Mass live-start risk — xem Phase 4 Risk |

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [Domain and Repository](./phase-01-domain-and-repository.md) | Completed |
| 2 | [Reconcile Service](./phase-02-reconcile-service.md) | Completed |
| 3 | [Handler Declarative Rewrite](./phase-03-handler-declarative-rewrite.md) | Completed |
| 4 | [Boot Wiring and Migration](./phase-04-boot-wiring-and-migration.md) | Completed |
| 5 | [Verify](./phase-05-verify.md) | Completed |

## Outcome (verified)

- Full suite: 444 passed, 12 skipped, 0 failed. import-linter 7/7 contracts kept. pyright 0 errors on changed files. ruff clean on changed files.
- Restart-resume proven by integration test (`tests/trading_test/test_reconcile_restart_resume_integration.py`): running sub auto-resumes across simulated restart, 0 manual starts.
- add_symbol default: **stopped** (user-confirmed — new adds do not auto-run; only migration of pre-existing subs → running).
- Code review: PASS-WITH-CONCERNS (no Critical/High). L1 (missing_instance per-tick log-spam) fixed — warn now fires once on drift, not every tick.
- Test layout note: core entity tests placed in actual repo path `tests/core_test/unit/domain/subscription/` (not the `tests/core_test/` shown in phase doc); migration/DI tests under `tests/api_test/unit|integration/`.

## Key dependencies

- Phase 1 (domain + repo) blocks all others — `desired_state`/`actual_state` field is the contract.
- Phase 2 (reconcile service) needs Phase 1 repo methods.
- Phase 3 (handlers) needs Phase 1 repo `update_desired_state`.
- Phase 4 (boot + migration) needs Phase 2 service + Phase 1 migration helper.
- Phase 5 verifies whole flow + import-linter + full suite.

## TDD note

Mode `--tdd`: refactor đụng core domain (frozen dataclass) + critical lifecycle (rehydrate, reconcile). Mỗi phase viết **characterization/behavior test trước**, lock hành vi, rồi sửa code cho pass. Pattern tham chiếu: `tests/execution_test/strategy_injection_roundtrip_characterization_test.py`.

## Dependencies

Cross-plan:
- **Blocks** `SP3 split app/bff` (chưa có plan dir; report `plans/reports/brainstorm-260609-1137-sp3-split-app-and-bff-report.md`). SP3 cần SP1 xong để ranh giới = Mongo.
- **Independent of** `SP2 rename api→app` (mechanical rename; chèn trước/sau đều được). Nếu SP2 chạy trước, mọi path `pocketquant.api.*` trong plan này đổi thành `pocketquant.app.*`.
