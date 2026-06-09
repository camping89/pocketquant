# SP3 — Split `app` (headless runtime) + `bff` (FE gateway)

> Brainstorm summary. Sub-project 3/3. **Phụ thuộc SP1** (declarative control plane) để tách sạch.
> Liên quan: [SP1 control plane](./brainstorm-260609-1137-sp1-declarative-control-plane-report.md), [SP2 rename](./brainstorm-260609-1137-sp2-rename-api-to-app-report.md).

## Problem statement

Runtime trading (scheduler, WS feed, strategy lifecycle) và tầng HTTP serve-FE đang **fused trong 1 process**. Nỗi đau thật: deploy/restart FE hoặc crash 1 HTTP request làm gián đoạn strategy đang chạy live. Cần **crash isolation + restart FE không giết trading**. Tách 2 process:

- **`app`** — headless runtime: DI, migrations, scheduler, WS feed, strategy lifecycle, **reconcile loop**. Chạy độc lập, không cần FE/BFF.
- **`bff`** — stateless FastAPI: serve `web`, đọc Mongo/Redis, ghi desired-state. Chết/restart thoải mái.

## Vì sao phụ thuộc SP1 (CRITICAL)

Verified: FE có command đụng RAM của runtime — `POST /subscriptions/{id}/start|stop` → `StrategyAppService.start_strategy()` (`execution/.../strategy_app_service.py:118`) tạo/đụng strategy object **trong RAM của process đang chạy nó**. 6 handler đụng RAM: `start, stop, add_symbol, remove_symbol, delete, list_symbols`.

→ Nếu tách process **mà chưa có SP1**: lệnh start đập vào `bff` → strategy mọc trong RAM của `bff` (sai — không có WS feed nuôi tick). Buộc phải xây **command channel** (Redis Stream / internal HTTP) → tax thêm.

→ **Với SP1 (declarative)**: bff chỉ ghi `desired_state` vào Mongo, app reconcile. **Ranh giới 100% là Mongo/Redis. Command channel biến mất.** Đây là lý do SP1 phải xong trước SP3.

## Hiện trạng (verified)

| Điểm | Bằng chứng |
|------|-----------|
| FE live data qua Redis/Mongo, KHÔNG đọc RAM strategy | `stream_bars/route.py:33` (bar in-progress từ Redis); FE đọc DB+cache |
| Lifespan gom hết vào 1 process | `api/main.py:38-87` |
| HTTP routes tập trung 1 chỗ | `api/main_extensions.py:456` `register_routes` — 9 router + StaticFiles serve `web/dist` |
| Sync/backtest qua APScheduler job store (Mongo) | `sync_bulk/handler.py` enqueue; app scheduler nhặt → tách sạch sẵn |
| Settings có `enable_jobs` flag | `core/config.py:59` — đã có cơ chế bật/tắt background |

## Kiến trúc đích

```
        ┌──────────── app (headless) ────────────┐
        │ DI · migrations · indexes · recovery    │
        │ scheduler(sync) · WS feed · strategies  │
        │ RECONCILE LOOP (đọc desired_state DB)   │
        └──────────┬───────────────┬──────────────┘
                   │ ghi/đọc       │ đọc/ghi
              ┌────▼────┐     ┌────▼────┐
              │  Mongo  │     │  Redis  │
              └────┬────┘     └────┬────┘
                   │ đọc + ghi desired
        ┌──────────▼───────────────────────────┐
        │ bff (stateless FastAPI) · serve web   │
        │ read routes + ghi desired_state +     │
        │ enqueue jobs (Mongo job store)        │
        └──────────┬────────────────────────────┘
                   │ HTTP
                 [web/FE]
```

- `app`: không HTTP (hoặc chỉ `/health` nội bộ). Tự chạy full auto.
- `bff`: mọi route hiện tại; ghi desired-state + enqueue job; KHÔNG đụng RAM strategy.

## Phân chia trách nhiệm (sau SP1)

| Concern | app | bff |
|---------|-----|-----|
| DI container | ✅ (subset runtime) | ✅ (subset read/write-DB) |
| Migrations / indexes / recovery | ✅ | — |
| APScheduler (sync jobs) | ✅ (chạy) | enqueue vào Mongo store |
| WS feed (Binance) | ✅ | — |
| Strategy lifecycle + reconcile | ✅ | — (chỉ ghi desired-state) |
| HTTP read routes (chart, history, status, positions, trades) | — | ✅ |
| HTTP write metadata (tạo/xoá subscription, backtest run) | — | ✅ (ghi Mongo / enqueue) |
| Start/stop/add/remove strategy | reconcile thực thi | ✅ ghi desired-state |
| Serve `web/dist` (StaticFiles) | — | ✅ |

## Expected output (acceptance)

1. 2 package/entrypoint: `pocketquant-app` (headless) + `pocketquant-bff` (FastAPI). DI tách 2 subset.
2. `app` chạy không FE: scheduler + WS + strategy + reconcile hoạt động đầy đủ; tự resume strategy `running`.
3. `bff` chạy stateless: phục vụ mọi route FE hiện có; ghi desired-state + enqueue; restart không ảnh hưởng app.
4. Mất `bff` → app vẫn auto-trade. Mất `app` → bff vẫn serve đọc (data tĩnh) nhưng không có tick mới (đúng kỳ vọng).
5. Docker: 2 image / 2 service (compose); CI build cả 2; deploy 2 process.
6. import-linter: cả 2 là top layer độc lập, cùng đứng trên backtest/trading.

## Quyết định cần chốt khi plan

| # | Câu hỏi | Khuyến nghị |
|---|---------|-------------|
| D1 | Code split kiểu gì? | 2 package riêng (`pocketquant-app` giữ runtime + DI core; `pocketquant-bff` giữ routes). Hoặc 1 package 2 entrypoint (rủi ro import chéo). **Khuyến nghị 2 package** cho ranh giới cứng. |
| D2 | DI container chung hay tách? | Tách 2 hàm `create_app_container()` / `create_bff_container()` chia sẻ provider chung (Core/Persistence) + riêng (app: Infra scheduler/feed + Execution; bff: read handlers). |
| D3 | `app` có cần `/health` HTTP? | Có, 1 endpoint nội bộ tối thiểu cho liveness/orchestrator. Không phải full FastAPI. |
| D4 | Provider/handler hiện ở `pocketquant-api` đi đâu? | Read handlers (market_data, quotes, ohlcv, status, backtest read) → bff. Runtime services (sync_jobs, ws_subscription_manager, cascade_aggregator) → app. |
| D5 | `web` package đổi tên `fe`? | Optional. FE chỉ đổi base URL sang bff. Giữ `web` được. |
| D6 | Deploy/compose | 2 service trong `deploy/`; app không expose port public, bff expose. Cập nhật `pocketquant-config`. |
| D7 | Quan hệ với SP2 | Nếu SP2 đã rename `api→app`: SP3 tách phần HTTP RA khỏi `app` thành `bff` mới. Nếu chưa SP2: SP3 vừa tách vừa đặt tên luôn. |

## Risks

| Risk | Mức | Mitigation |
|------|-----|-----------|
| Tách process trước khi SP1 xong → đẻ command channel | **Cao** | **Gate cứng: SP1 phải merge trước.** Plan SP3 mở đầu bằng check `desired_state` + reconcile đã có |
| DI provider chia sai → bff vô tình giữ scheduler/feed | Cao | Test: bff khởi động KHÔNG start scheduler/WS; app khởi động KHÔNG mở public routes |
| 2 process cùng chạy migration/index lúc boot → race | Trung | Chỉ `app` chạy migration/ensure_indexes; bff giả định schema sẵn sàng |
| APScheduler job store: bff enqueue, app execute — double-run nếu bff lỡ start scheduler | Trung | bff KHÔNG khởi tạo JobScheduler runtime; chỉ ghi job vào Mongo store |
| StaticFiles serve web/dist chuyển sang bff | Thấp | Di chuyển mount sang bff; app bỏ |
| Deploy phức tạp hơn (2 service, healthcheck, restart policy) | Trung | Compose rõ ràng; app restart policy `always`; tài liệu trong `deploy/` |
| FE đứt khi bff đổi base URL / port | Thấp | Vite proxy + env; smoke test FE→bff |

## Success metrics

- Kill `bff` khi đang có strategy `running` → strategy KHÔNG gián đoạn (verify qua trades/positions tiếp tục ghi).
- Restart `bff` → FE phục hồi, app không restart.
- `app` chạy standalone (không bff) → reconcile + WS + scheduler hoạt động, strategy auto-resume.
- import-linter pass; 2 container build + chạy.

## Next steps

- **Chỉ bắt đầu sau khi SP1 merge.** (Khuyến nghị thứ tự: SP1 → SP2 → SP3, hoặc SP2 → SP1 → SP3.)
- `/ck:plan --tdd` (đụng critical runtime split, cần test khoá hành vi: app standalone, bff stateless, isolation).
- Pass cả report SP1 + SP3 làm context.

## Unresolved questions

1. D1 (2 package vs 1 package 2 entrypoint) và D2 (cách chia DI provider) — chốt khi plan.
2. `app` expose `/health` mức nào (chỉ liveness hay readiness check DB/Redis)?
3. Thứ tự với SP2: tách + rename gộp 1 lần, hay rename (SP2) xong mới tách (SP3)?
4. Deploy target hiện tại (compose? VPS? k8s?) — ảnh hưởng healthcheck/restart policy. Cần xem `pocketquant-config/vps`.
5. `web` có đổi `fe` không (D5) — nghiệp vụ/sở thích.
