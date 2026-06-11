---
title: "Collapse 6 subpackages → 4, single backend process"
description: "Giải thể trading (services → engine, OKX → core/infra, xóa webhooks dead code); gộp bff vào app thành 1 process duy nhất trên :41921; fix bug 500 /trading/orders|positions. TDD: regression net từ SP3 lock behavior trước mỗi phase."
status: pending
priority: P2
branch: "develop"
tags: [restructure, de-over-engineering, tdd, lean]
blockedBy: []
blocks: []
created: "2026-06-11T09:56:54.369Z"
createdBy: "ck:plan"
source: skill
---

# Collapse 6 subpackages → 4, single backend process

## Overview

Brainstorm consensus ([report](../reports/brainstorm-260611-1651-collapse-six-subpackages-to-four-single-process-report.md)): `trading` là subpackage mỏng nhất — 3 services chỉ là CRUD trên repos của `core` + app_services của `engine`; OKX broker là adapter thuần giống `paper_broker` (đã nằm ở `core/infra/brokers/`); `webhooks` là dead code. `bff/di/` là bản copy gần nguyên văn của `app/di/` (~160 LOC trùng). User quyết định: **1 entrypoint backend duy nhất** — job, API, runtime gộp chung 1 process. Đảo ngược có chủ đích quyết định tách 2 process của SP3 (user xác nhận 2026-06-11).

End-state: `core ◁ engine ◁ backtest ◁ app`. Một process uvicorn trên `:41921` chạy tất cả: API routes, SPA serving, scheduler, WS feed, reconcile loop, backtest worker. Bug 500 của `/trading/orders|positions` tự hết vì single DI container có đủ `OrderAppService`/`PositionAppService` in-RAM.

TDD mode: regression net từ SP3 (`tests/baseline/` — OpenAPI snapshot, route inventory, boot smoke, layout contract) được cập nhật expectation TRƯỚC mỗi lần move code; mỗi phase kết thúc với toàn bộ net xanh.

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [Lock baseline net and delete dead webhooks](./phase-01-lock-baseline-net-and-delete-dead-webhooks.md) | Pending |
| 2 | [Dissolve trading into engine and core](./phase-02-dissolve-trading-into-engine-and-core.md) | Pending |
| 3 | [Merge bff into app single process](./phase-03-merge-bff-into-app-single-process.md) | Pending |
| 4 | [Deploy runtime and docs sync](./phase-04-deploy-runtime-and-docs-sync.md) | Pending |

## Verification gates (mỗi phase kết thúc xanh)

- `just test` — full pytest, 100% pass
- `just lint-imports` — import-linter contracts pass
- `just types` — pyright clean
- `just lint` — ruff clean
- Import-boot: `python -c "import pocketquant.app.main"` (sau Phase 3 chỉ còn 1 entrypoint)
- OpenAPI snapshot diff rỗng, trừ diff đã document (Phase 3: `info.title`/`info.description`)

## Behavioral changes (có chủ đích, đã được user duyệt)

| Change | Trước | Sau |
|---|---|---|
| `/api/v1/trading/orders\|positions` | luôn 500 (service không có trong bff DI) | 200 — single container resolve được in-RAM services |
| Số process backend | 2 (app :41920 + bff :41921) | 1 (app :41921) |
| `trading/webhooks/` | dead code ~110 LOC | xóa (git history giữ) |

## Deployment atomicity (CRITICAL)

CI auto-deploy lên VPS mỗi push develop (`.github/workflows/cicd.yml:165-215`). Quy tắc push:

- Phase 1, 2: push lẻ AN TOÀN (cấu trúc nội bộ, compose/entrypoint không đổi).
- Phase 3: commit nhưng **KHÔNG push** — image thiếu `pocketquant.bff` trong khi compose cũ trên VPS vẫn chạy `uvicorn pocketquant.bff.main:app` → crash-loop + web 502 toàn bộ API.
- Phase 3 + 4: push CÙNG 1 lần `git push` (backend image + web image cùng sha, compose + nginx đổi cùng đợt).

## Rollback (sau khi Phase 3+4 đã deploy)

Rollback image-only (`IMAGE_TAG=sha-xxx bash 10-deploy.sh`) **KHÔNG hợp lệ** sau merge:
- Backend image cũ + compose mới: app cũ trên :41921 chỉ có `/health` → mọi `/api/*` 404 nhưng healthcheck vẫn xanh.
- Web image cũ: nginx trỏ upstream `bff` không còn tồn tại → 502.

Quy trình đúng: `git revert` cả 2 commit Phase 3+4 → push → CI rebuild + deploy trọn bộ (backend + web + compose về topology cũ). Probe `/api/v1/*` mới trong `11-verify.sh` (Phase 4) đảm bảo rollback hỏng hiện hình ngay thay vì verify HEALTHY mù.

## Dependencies

- Các plan SP1/SP2/SP3 + lean-monorepo-restructure: đều `completed`, không blocking. Plan này đảo một phần end-state SP3 (split 2 process) theo quyết định mới của user — đã surface trade-off và được duyệt.
- Cross-plan: không phát hiện plan unfinished nào overlap.

## Out of scope

- Frontend (`web/`) thay đổi ngoài `nginx.conf` upstream + (không đổi) vite proxy
- Behavior/logic changes ngoài bảng trên — còn lại pure structure
- Tách process trở lại nếu backtest load làm chậm API (ghi nhận rủi ro, xử lý khi quan sát thấy)
- Auth coverage cho mutation routes (pre-existing: phần lớn POST/DELETE không có admin token; `/trading/*` sau fix 500 trả live positions không auth — chỉ reachable qua nginx nội bộ; cân nhắc plan riêng)

## Red Team Review

### Session — 2026-06-11
**Findings:** 15 sau dedupe (15 accepted — 2 dạng modified, 0 rejected)
**Severity breakdown:** 2 Critical, 4 High, 9 Medium
**Reviewers:** Assumption Destroyer (Contract Verifier) + Failure Mode Analyst (Fact Checker); security checks chạy trực tiếp bởi controller (2 lần spawn security-lens subagent bị API filter chặn)

| # | Finding | Severity | Disposition | Applied To |
|---|---------|----------|-------------|------------|
| 1 | CI auto-deploy mỗi push develop → push lẻ Phase 3 = outage live API | Critical | Accept | plan.md (Deployment atomicity), Phase 3 step 12, Phase 4 step 9 |
| 2 | Không có rollback section; rollback image-only hỏng cả 2 chiều sau merge, verify mù /api | Critical | Accept | plan.md (Rollback), Phase 4 (11-verify.sh probe + risk row) |
| 3 | xfail(strict) trên test đang pass → XPASS = FAIL, gate Phase 1 không thể xanh | High | Accept | Phase 1 steps 2/5 + success criteria (1 xfail) |
| 4 | Phase 4 smoke nhắm `just up` nhưng compose.local chỉ có mongo+redis | High | Accept | Phase 4 Key Insights + step 5 (smoke qua dev flow + compose config) |
| 5 | tests/bff_test assert NGƯỢC end-state (NoFactoryError cho runtime types) — move mechanical sẽ vỡ | High | Accept | Phase 3 Key Insights (enumeration: xóa/viết lại/giữ từng test) |
| 6 | Port 41920 còn ở deploy/Dockerfile:54,56,58 + app/main.py:132 run(); grep guard không có pattern 41920 | High | Accept | Phase 3 (Dockerfile + run() vào Modify), Phase 4 (grep guard + 41920) |
| 7 | 3 duplicate DI provides (StrategyCommand/Query, SyncService) — dishka silent last-wins | Medium | Accept | Phase 3 Key Insights + steps 2-3 (strip khi merge) |
| 8 | TDD-lock "+ /health" double-count (đã có trong snapshot); "đắp" register_routes → duplicate /health | Medium | Accept | Phase 3 step 1 (inventory nguyên văn) + step 4 (REPLACE) |
| 9 | import-linter hard-error khi source_modules trỏ module đã xóa — 2 contracts dạng source bị sót | Medium | Accept | Phase 2 Key Insights + step 6; Phase 3 step 8 (bff trong fastapi-containment source) |
| 10 | Console script `pocketquant-bff` (pyproject.toml:31) dangling; sweep `src tests` không thấy | Medium | Accept | Phase 3 step 7 (sweep + pyproject.toml justfile) |
| 11 | tests/trading_test/conftest.py (testcontainers fixtures) bị orphan khi move tests | Medium | Accept | Phase 2 step 7 + Related Code Files |
| 12 | test_openapi_snapshot.py + test_route_inventory.py import bff.main — regenerate flow crash; thứ tự repoint→diff→regenerate | Medium | Accept | Phase 3 Related Code Files + step 9 |
| 13 | Crash-loop boot giờ giết cả API + OKX churn (trước đây bff vẫn sống); risk row cũ chỉ nói happy path | High→Medium | Accept (modified: document + cân nhắc catch-log-degrade khi implement, không ép đổi behavior) | Phase 3 risk table |
| 14 | Không gì chặn `--workers N` tương lai nhân bản scheduler/reconcile/broker | Medium | Accept (modified: comment cảnh báo ở compose + justfile, không thêm runtime lock) | Phase 4 Related Code Files + Phase 3 risk table |
| 15 | `--reload` dev reboot full trading runtime mỗi save; admin auth là route-Depends không phải middleware (security check viết sai chỗ); mutation routes thiếu auth là pre-existing | Medium | Accept | Phase 3 step 10 (ENABLE_JOBS=false note), Security Considerations viết lại, plan.md Out of scope |

### Whole-Plan Consistency Sweep
- Files reread: plan.md, phase-01, phase-02, phase-03, phase-04
- Decision deltas checked: 15 (xfail 2→1; smoke just-up→dev-flow; +atomic push; +rollback; +41920 pattern; REPLACE thay đắp; dedupe DI; enumeration bff_test; conftest move; source_modules contracts; console script; snapshot order; blast radius; single-worker note; admin-auth recharacterized)
- Reconciled stale references: Phase 1 success criteria "2 xfail"→"1 xfail" (todo + criteria + step 5); Phase 3 todo list đồng bộ steps mới; Phase 4 todo/criteria bỏ `just up` full-stack, thêm probe + atomic push; plan.md không còn chỗ nào hứa "mỗi phase push độc lập"
- Unresolved contradictions: 0
