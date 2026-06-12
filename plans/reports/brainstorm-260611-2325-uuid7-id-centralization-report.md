# Brainstorm: UUID7 ID Centralization — re-evaluation post 4-subpackage restructure

**Date:** 2026-06-12 | **Input:** `plans/todo/260530-centralize-uuid7-id-strategy.md` | **Status:** CONSENSUS — sẵn sàng plan

## Problem statement

Todo doc 30/05 chốt: mọi `_id` ta sở hữu = UUIDv7 (trừ `apscheduler_jobs` — library-owned). Chưa implement. Codebase đã đổi lớn từ đó: 6 subpackages → 4, 1 process, paths trong todo doc (`packages/pocketquant-*`) đều stale. Session này re-verify hiện trạng, phát hiện scope thiếu, chốt lại disposition từng collection với user.

## Hiện trạng verified (2026-06-12, sau restructure)

`generate_id()`/`generate_id_str()` (`core/common/uuid.py`) wrap `uuid7()` native Python 3.14 — đã centralized, không đổi.

### Representation (WS1)

| Entity | Hiện tại | Target |
|---|---|---|
| `Bar`, `Symbol`, `SyncStatus` | `id: UUID` + str tại Mongo boundary | ✅ đã đúng |
| `OrderAggregate` (`order/entities.py:32`), `PositionAggregate` (`position/entities.py:28`) | `id: str` (giá trị đã uuid7 qua `generate_id_str()`) | `id: UUID` |
| `BacktestResult` (`backtest/entities.py:26`), `OptimizationResult` (`:78`) | `id: str` (giá trị uuid7) | `id: UUID` |
| `BacktestRequest` (`backtest/request.py:29`) | `id: str` — run-all dùng `bt:{sub_id}` KHÔNG phải uuid | `id: UUID` — convert CÙNG phase re-key (không thể trước) |
| `Subscription` (`subscription/entities.py:38`) | `id: str` = sha256 16-hex | `id: UUID` sau re-key |
| backtest orders/trades | `order_id`/`trade_id`/`fill_id: str` (giá trị uuid7) | `UUID` |

### Outlier `_id` — census ĐẦY ĐỦ (todo doc cũ thiếu 2 dòng)

| # | Collection | `_id` hiện tại | Cơ chế đang dựa vào | Trong todo cũ? |
|---|---|---|---|---|
| A | `subscriptions` | `sha256(code\|SYMBOL\|interval)[:16]` (`Subscription.deterministic_id`) | dedup insert (DuplicateKeyError), URL, RAM instance key, FK | ✅ |
| B | `tracked_symbols` | composite `symbol` string | unique index `symbol` đã có sẵn → re-key rẻ | ✅ |
| C1 | `job_history` | mix: `generate_id_str()` (mới) + legacy ObjectId (docs cũ) | append-only log, không FK | ✅ |
| C2 | `apscheduler_jobs` | APScheduler job name | library-owned | ✅ EXEMPT |
| **D** | `backtest_requests` | **`bt:{sub_id}`** (`backtest_command_service.py:177`) — run-all; single dùng uuid7 | `replace_one(_id, upsert)` = dedup concurrent run-all + bound 1 doc/sub | ❌ MỚI |
| **E** | `backtest_runs` (cache docs) | **`_id = sub_id`** (`backtest_repository.py:97-106` `save_for_subscription`) | upsert per-subscription cache slot; single-run docs trong CÙNG collection đã uuid7 (mixed!) | ❌ MỚI |

### FK fan-out của subscription id (rộng hơn todo cũ)

1. `orders.subscription_id`, `positions.subscription_id` (field)
2. `backtest_runs.subscription_id` (field) + `backtest_runs._id` (cache docs, = sub_id)
3. `backtest_requests.sub_id` (field) + `backtest_requests._id` (`bt:{sub_id}`)
4. RAM: `StrategyAppService` instance keys = sub.id; synthetic backtest keys `{code}::bt::{sub_id}`
5. Safety guard: `_SUB_ID_SHAPE = ^[0-9a-f]{16}$` (`strategy_reconcile_service.py:43`) — orphan-unload chỉ đụng keys match shape này; ĐỔI ID SHAPE → PHẢI ĐỔI REGEX cùng lúc, nếu quên thì orphan-unload thành no-op vĩnh viễn (silent)
6. FE: URLs `/api/v1/subscriptions/{subId}` (`web/src/api/strategy-api.ts`) — FE không tự tạo id, chỉ echo từ list response → không cần sửa FE code, chỉ break bookmarks

## Approaches đã cân nhắc

| Approach | Pros | Cons | Verdict |
|---|---|---|---|
| 1. 100% uuid7 (re-key tất cả A/B/C1/D/E) | Rule §12.6 không exception nội bộ; uniformity tuyệt đối | 3 migration thật + dedup chuyển sang unique indexes + backtest_requests đổi storage profile | **CHỌN** (user re-confirm sau khi thấy cost mới) |
| 2. Re-key A/B/C1, exempt D/E (deterministic-by-design) | Ít moving parts; D/E là cache/queue key có chủ đích | 3 exceptions trong §12.6 thay vì 1; "uniformity" nửa vời | Bị từ chối |
| 3. WS1 + B + C1 only, hoãn A | Phần rẻ làm ngay, phần đắt chờ lý do mạnh hơn | Mục tiêu consistency không đạt | Bị từ chối |

## Quyết định chốt (user confirm 2026-06-12)

1. **Giữ 100% uuid7** — re-key cả `subscriptions` dù cost đã tăng (5 điểm FK + regex guard). Exception duy nhất: `apscheduler_jobs`.
2. **`backtest_requests` re-key uuid7** — dedup giữ bằng **partial unique index** `(sub_id)` với `partialFilterExpression {status: "pending"}`; enqueue đổi từ `replace_one(_id)` sang upsert theo `(sub_id, status="pending")`. Mitigation tăng trưởng collection (done docs không còn bị overwrite): enqueue xóa done/failed docs cũ của sub_id đó, hoặc TTL index trên completed_at — quyết khi implement.
3. **`backtest_runs` cache docs re-key uuid7** — unique index `subscription_id` (partial: field exists); `save_for_subscription`/`find_by_subscription` đổi filter từ `_id` sang `subscription_id`. Migration chỉ đụng docs có `subscription_id == _id`.
4. **`job_history` legacy ObjectId: re-key copy-delete** — giữ lịch sử runs (dashboard stats 24h/7d/30d).
5. **Migration = boot-time idempotent** trong lifespan (pattern `migrate_strategy_id_fields` đã prove 2 lần) — tự deploy qua CI, không cần maintenance window.
6. **Rollout: push từng phase riêng** — mỗi phase 1 push → CI deploy → `11-verify.sh` HEALTHY → phase kế. Rollback = revert push (migrations idempotent + side-effect-free khi chạy lại).

## Phasing đề xuất (thứ tự CÓ LÝ DO)

| Phase | Nội dung | Risk | Vì sao thứ tự này |
|---|---|---|---|
| 1 | WS1 representation: `id: str` → `id: UUID` cho Order/Position/BacktestResult/Optimization/bt-orders/trades (giá trị đã uuid7, chỉ đổi type + to_mongo/from_mongo) | LOW | Không migration; lock type tại boundary trước khi đụng data. `BacktestRequest` KHÔNG nằm đây (id còn `bt:` prefix) |
| 2 | `tracked_symbols` re-key: uuid7 `_id`, giữ unique index `symbol` | LOW | Index unique có sẵn → guarantee không đổi; không FK |
| 3 | `job_history` re-key legacy ObjectId (copy-delete) | LOW | Append-only, không FK |
| 4 | `backtest_requests`: partial unique index pending TRƯỚC → đổi enqueue → re-key `_id` → `BacktestRequest.id: UUID` | MED | Gỡ coupling `_id ← bt:{sub_id}` TRƯỚC khi re-key subscriptions, để Phase 6 chỉ phải rewrite field `sub_id` |
| 5 | `backtest_runs` cache docs: unique index `subscription_id` → đổi upsert filter → re-key `_id` | MED | Cùng lý do: gỡ coupling `_id ← sub_id` trước Phase 6 |
| 6 | `subscriptions` re-key (CUỐI, cô lập): (a) unique compound index `(strategy_code, symbol, interval)` TRƯỚC; (b) migration old→new map + rewrite `orders.subscription_id`, `positions.subscription_id`, `backtest_runs.subscription_id`, `backtest_requests.sub_id`; (c) xóa `deterministic_id`, add_symbol dùng `generate_id()` + bắt DuplicateKeyError từ compound index; (d) `_SUB_ID_SHAPE` → UUID regex; (e) `Subscription.id: UUID` | **HIGH** | Mọi coupling `_id` đã gỡ ở 4-5 → blast radius chỉ còn fields + RAM keys (rehydrate tự nhận id mới sau restart, container restart sẵn khi deploy) |

Mỗi phase: TDD-lock theo net hiện có (OpenAPI snapshot — id shape trong response đổi ở Phase 6: FE nhận uuid string thay 16-hex, schema vẫn `string` → snapshot không đổi; route inventory không đổi).

## Risks còn lại

| Risk | Sev | Mitigation |
|---|---|---|
| Quên đổi `_SUB_ID_SHAPE` → orphan-unload silent no-op | HIGH | Phase 6 checklist + test: load instance với uuid key, xóa sub doc, assert unload xảy ra |
| Migration map old→new chạy giữa chừng bị kill (partial rewrite FK) | MED | Migration ghi map vào collection tạm `_id_migration_map` trước, rewrite từ map, idempotent re-run từ map; xóa map khi xong |
| Hai add_symbol đua nhau sau khi mất hash-PK | MED | Unique compound index tạo TRƯỚC khi đổi codepath (cùng phase, thứ tự trong migration) |
| `backtest_requests` growth (done docs tích lũy) | LOW | Cleanup-on-enqueue hoặc TTL — chốt khi implement Phase 4 |
| Bookmarks/URLs sub-id cũ break | ACCEPTED | User đã chấp nhận từ 30/05, re-confirm hôm nay |
| Prod data chưa đếm được từ local | LOW | Pre-deploy mỗi phase: `docker exec pocketquant-mongodb mongosh --eval 'db.X.countDocuments(...)'` trên VPS + mongodump theo `docs/deployment.md` |

## Success metrics

- `mongosh`: mọi `_id` trong collections ta own match UUID regex (trừ `apscheduler_jobs`)
- Dedup vẫn hoạt động: add_symbol trùng triple → 400/409 như cũ; run-all concurrent → 1 pending request/sub
- Full gates xanh mỗi phase; OpenAPI + route inventory snapshot diff rỗng
- `11-verify.sh` HEALTHY sau mỗi deploy
- Reconcile orphan-unload test pass với UUID shape mới

## Next steps

1. `/ck:plan` từ report này (đề xuất `--tdd`: refactor behavior-preserving trên control-plane live-trading, net regression có sẵn)
2. Sau plan: archive `plans/todo/260530-centralize-uuid7-id-strategy.md` (superseded bởi report này + plan mới)
3. Cập nhật `docs/code-standards.md` §12.6 nếu wording exception cần re-confirm (vẫn 1 exception duy nhất)

## Unresolved questions

1. `backtest_requests` done-docs cleanup: cleanup-on-enqueue vs TTL index — chốt khi implement Phase 4 (không chặn plan).
2. Số lượng legacy ObjectId docs thật trong `job_history` prod — đếm pre-deploy Phase 3 (ảnh hưởng thời lượng migration, không ảnh hưởng thiết kế).
