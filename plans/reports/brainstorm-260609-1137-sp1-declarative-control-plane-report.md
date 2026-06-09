# SP1 — Declarative Control Plane (Reconcile Loop)

> Brainstorm summary. Sub-project 1/3. Enabler — phải làm trước SP3.
> Liên quan: [SP2 rename](./brainstorm-260609-1137-sp2-rename-api-to-app-report.md), [SP3 split](./brainstorm-260609-1137-sp3-split-app-and-bff-report.md).

## Problem statement

Hệ thống auto-trading nhưng trạng thái "strategy đang chạy" hiện sống trong RAM, mất khi restart. FE phải bấm "Start" lại bằng tay. Mental model đúng cho auto-trading: **forward test chạy 100% trên Mongo + Redis; FE/BFF chỉ là cổng cho con người**. Cần chuyển từ imperative (FE ra lệnh vào RAM) sang declarative (FE ghi desired-state vào DB; app tự reconcile).

## Hiện trạng (verified)

| Điểm | Bằng chứng | Hệ quả |
|------|-----------|--------|
| `Subscription` không có field trạng thái | `core/domain/subscription/entities.py` — chỉ `id, strategy_code, symbol, interval, created_at` | Không có nơi lưu "muốn chạy hay dừng" |
| `start_strategy`/`stop_strategy` chỉ đụng RAM, không persist | `execution/app_services/strategy_app_service.py:118-145` — gọi `strategy.on_start()`, set `is_running` trên object | Trạng thái run bay mất khi restart |
| `rehydrate` chỉ `load_strategy`, KHÔNG auto-start | `api/main_extensions.py:345` | Restart app → strategy nạp nhưng đứng im |
| 6 handler đụng RAM trực tiếp | `trading/handlers/strategy/{start,stop,add_symbol,remove_symbol,delete,list_symbols}/handler.py` → gọi `StrategyAppService` | FE buộc "ra lệnh vào RAM" — gốc của command-channel coupling |
| `is_running` đọc từ instance RAM | `trading/handlers/strategy/list_symbols/handler.py:29` | Trạng thái hiển thị = RAM, không phải DB |
| Subscription repo chưa có `update` | `infrastructure/.../subscription_repository.py` — chỉ `add/get/list/delete/ensure_indexes` | Phải thêm method ghi desired-state |

## Kiến trúc đích

Declarative + reconciliation (mô hình controller kiểu Kubernetes):

```
Control plane (desired)              Data plane (market)
 Mongo: subscription.desired_state     Mongo+Redis: bars,quotes,
      ▲              │                   positions, trades
 ghi  │              │ đọc desired            ▲          │
      │              ▼                        │ ghi      │ đọc
  [bff/human]   ┌──────────────┐              │          ▼
                │  reconcile   │──────────────┘     [bff/human read]
                │  loop (app)  │
                │  +WS +sched  │
                └──────────────┘
```

- FE "Start" → bff ghi `desired_state=running` vào Mongo → **không đụng RAM**.
- App có **reconcile loop**: so desired (DB) vs actual (RAM) → tự `start_strategy`/`stop_strategy`.
- Restart app → đọc desired → **auto-resume** mọi subscription `running`.
- Không FE/BFF → app vẫn chạy full auto.

## Expected output (acceptance)

1. `Subscription` có field `desired_state: Literal["running","stopped"]` (mặc định `stopped`), persist Mongo, có boot migration set giá trị cho doc cũ.
2. `SubscriptionRepository.update_desired_state(sub_id, state)` (hoặc `update(sub)`).
3. Reconcile loop trong app: chu kỳ so desired vs actual, start/stop strategy cho khớp. Idempotent.
4. 6 handler đụng-RAM đổi sang ghi desired-state DB (trừ `list_symbols` — xem dưới).
5. `rehydrate` + reconcile khởi động: restart → strategy `running` tự chạy lại, không cần bấm tay.
6. `is_running` / trạng thái hiển thị đọc từ DB desired-state + (optional) actual-state, không phụ thuộc instance RAM ở tầng FE.

## Quyết định cần chốt khi plan

| # | Câu hỏi | Option | Khuyến nghị |
|---|---------|--------|-------------|
| D1 | Reconcile **poll** hay **watch**? | Poll mỗi N giây (đơn giản, đã quen APScheduler) vs MongoDB change stream (real-time, phức tạp hơn) | **Poll** trước (KISS); watch sau nếu cần độ trễ thấp |
| D2 | `desired_state` enum 2 hay 3 trạng thái? | `running/stopped` vs thêm `paused`/`error` | 2 trạng thái (YAGNI); mở rộng sau |
| D3 | Tách `desired_state` vs `actual_state`? | Chỉ desired (actual suy từ RAM) vs persist cả actual để FE thấy "đang chuyển" | Chỉ desired trước; actual để optional cho UX |
| D4 | `Subscription` đang `@dataclass(frozen=True)` | Thêm field giữ frozen + `replace()` hay bỏ frozen | Giữ frozen, dùng `dataclasses.replace` |
| D5 | `add_symbol`/`remove_symbol`/`delete` reconcile thế nào | Symbol đổi → reconcile load lại; delete → desired=stopped + remove | Định nghĩa reconcile diff rõ trong plan |
| D6 | `list_symbols` đọc `is_running` từ RAM | Giữ đọc RAM (chỉ app có) hay chuyển sang DB | Nếu chưa tách process: đọc RAM OK; nếu hướng SP3: phải chuyển DB |

## Related code files

**Modify:**
- `core/domain/subscription/entities.py` — thêm `desired_state`, `to_mongo`/`from_mongo`
- `infrastructure/persistence/repositories/subscription_repository.py` — thêm `update_desired_state`
- `execution/app_services/strategy_app_service.py` — reconcile entrypoint / expose actual state
- `api/main_extensions.py` — `rehydrate_*` + đăng ký reconcile loop trong lifespan
- `trading/handlers/strategy/{start,stop,add_symbol,remove_symbol,delete,list_symbols}/handler.py` — ghi desired-state thay vì gọi trực tiếp RAM
- `core/config.py` — flag `reconcile_interval_seconds` (nếu poll)

**Create:**
- Reconcile service (đặt trong `execution` — vùng shared engine): `execution/app_services/strategy_reconcile_service.py` (hoặc tên tương đương)
- Boot migration set `desired_state` cho subscription cũ (theo pattern `migrate_strategy_id_fields`)

## Risks

| Risk | Mức | Mitigation |
|------|-----|-----------|
| Boot migration trên subscription production thật | Cao | Idempotent; default `stopped` để KHÔNG auto-start nhầm loạt strategy khi deploy; verify trên copy DB |
| Reconcile + manual start race (cùng đụng `_lock`) | Trung | Reconcile dùng chung `self._lock` của StrategyAppService; reconcile idempotent (`is_running` check đã có) |
| `desired_state=running` mặc định sai → auto-start nhầm | Cao | Mặc định `stopped`; chỉ set `running` cho sub đang chạy lúc migrate (nhưng RAM state đã mất → cân nhắc set tay/để stopped) |
| Frozen dataclass refactor lan rộng | Thấp | Dùng `replace()`, không bỏ frozen |
| import-linter: reconcile đặt sai layer | Thấp | Đặt trong `execution` (đã được backtest+trading dùng); không import lên `api`/`trading` |

## Success metrics

- Restart app: mọi subscription `running` tự chạy lại, 0 thao tác tay.
- FE start/stop chỉ ghi Mongo, app reconcile trong ≤ 1 chu kỳ.
- Test: `desired=running` + actual=stopped → reconcile start; `desired=stopped` + actual=running → reconcile stop; restart resume.
- import-linter pass.

## Next steps

- `/ck:plan --tdd` (refactor core domain + critical lifecycle → cần test khoá hành vi hiện tại trước).
- Pass report này làm context.

## Unresolved questions

1. **Migration default**: subscription cũ đang "chạy" (RAM đã mất) → set `desired_state=running` (auto-resume) hay `stopped` (an toàn, bấm lại 1 lần)? → quyết định nghiệp vụ, hỏi lúc plan.
2. D1 (poll vs watch) và D3 (persist actual_state) — chốt khi plan.
3. Reconcile loop có cần stop strategy khi subscription bị `delete` ngay cả khi WS feed đang đẩy tick? → định nghĩa reconcile diff cho delete.
