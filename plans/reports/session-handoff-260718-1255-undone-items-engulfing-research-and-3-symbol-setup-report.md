# Session handoff — việc chưa xong sau research engulfing + setup 3 symbol

> 2026-07-18. Chốt sổ 2 luồng việc: (A) setup BTC/ETH/SOL vào prod, (B) research engulfing+structure 3 vòng + Test B. Câu tiếng Việt, term tiếng Anh giữ nguyên. Context đầy đủ: `plans/260712-0849-engulfing-structure-level-taker-profit/` + memory `engulfing-structure-research-and-3-symbol-setup`.

## Đã xong (không cần làm gì thêm)

| Việc | Bằng chứng |
|---|---|
| Backfill ETHUSDT + SOLUSDT vào prod (insert-only, không đụng BTC) | mỗi symbol 1,051,200 bars 1m (2024-07-12 → 2026-07-12), `deleted=0` |
| Cascade 5m/15m/1h/4h/1d cả 2 symbol | bar counts khớp lý thuyết (1h=17,520; 1d=731) |
| tracked_symbols + symbols + sync_status cho cả 3 | cron `sync_1m` chạy `synced_count=3`, data fresh (verify 2026-07-18: ETH 1m latest 08:10 UTC) |
| **1w bars ETH/SOL** (từng treo) | ✅ tự resolve qua cron `sync_backfill` 03:00 UTC — verify 2026-07-18: BTC n=466, ETH n=466, SOL n=310 (SOL list muộn hơn), latest 2026-07-13 |
| WS realtime quote cả 3 symbol | sau restart app: `binance_ws.connected streams=[SOL,BTC,ETH]`, quote API 200 cả 3. Fix persist qua reboot (boot-time subscribe đọc tracked_symbols — giờ đủ 3) |
| Smoke backtest ETH + SOL qua `POST /backtest/run` | status `finished`, metrics thật (ETH: 12 trades) — acceptance criteria đạt |
| Research 3 vòng + brainstorm + Test B multi-symbol | 3 report trong plan dir; kết luận cuối bên dưới |

## Kết luận research (ĐÓNG — đừng mở lại nếu không có evidence mới)

**Engulfing không có directional alpha giao dịch được ở retail cost.** Chuỗi bằng chứng:
1. Vòng 1 (260706): engulfing 1m thuần — âm mọi config, 5 cách chứng minh.
2. Vòng 2 (260712): thêm structure-level (swing S/R 1d) + trend gate 1d + fixed-RR → 3 variant net dương taker trên BTC, NHƯNG CI chứa 0, phụ thuộc top-3 winners, random-same-gate cũng dương.
3. Brainstorm (Frame A): nghi cost là nút thắt (structure = maker chứ không phải taker) — hợp lý về logic, chưa kịp test thì…
4. **Test B (multi-symbol, 2026-07-13): KILL.** Chỉ BTC dương OOS; ETH lẫn lộn dấu; SOL âm mạnh cả 3 variant (−36 → −52 bps, win rate 0.08–0.15). `drop3_out` âm 9/9. Pooled bootstrap CI vẫn chứa 0, point pooled ~0/âm (A +2.0, B −2.3, C −8.8). **4/4 kill-criteria FAIL → BTC-artifact/trend-beta, không phải alpha.** Pooling không co CI = chữ ký "no edge", không phải "small-sample".

→ Hệ quả: **Test A (maker execution sim) mất phần lớn ý nghĩa** — tiết kiệm ~6 bps cost không sửa được gap −36..−52 bps của SOL.

## CHƯA XONG (theo priority)

### 1. Quyết định hướng research tiếp — CẦN USER QUYẾT
Ba lựa chọn, chưa chốt:
- **(a) Dừng hẳn** — research đóng, dùng data 3 symbol cho việc khác.
- **(b) Pivot Frame C** — trend-following đa symbol tử tế (vol-targeting, drawdown control, multi-regime validation); engulfing nhiều nhất là entry timer. Đây là brainstorm/scope MỚI, không phải tiếp nối engulfing. Cái net dương duy nhất qua 3 vòng đều là trend-beta 1d — làm beta cho tử tế là hướng trung thực duy nhất còn lại.
- **(c) Test A dù đã yếu lý do** — chỉ nếu chấp nhận maker-only + bỏ SOL; giá trị thấp, không khuyến nghị.

### 2. WS latent bug — priority thấp, đã có workaround
`BinanceWebSocketAdapter.subscribe()` (`src/pocketquant/core/infra/binance/binance_websocket_adapter.py:76`) chỉ thêm vào dict, KHÔNG gửi SUBSCRIBE frame vào socket đang mở — stream list chỉ chốt tại `connect()`/`_build_url()`. Symbol thêm runtime kẹt tới lần reconnect kế (đã gặp thật: ETH/SOL kẹt ~6h ngày 2026-07-12).
- Workaround (đủ dùng): `docker restart pocketquant-app` (~15s downtime).
- Fix đúng (nếu sau này thêm symbol runtime thường xuyên): gửi dynamic `{"method":"SUBSCRIBE","params":[...],"id":N}` control frame khi `is_connected()`. **Phải verify Binance WS docs hiện hành trước** (format, limit stream/connection, hành vi `/ws/` vs `/stream` endpoint). Cẩn trọng: đụng reconnect logic có watchdog + backoff — dễ regression; cần test cho dynamic-subscribe path.

### 3. `.env` local đang trỏ prod VPS
`.env` hiện = remote-db (MONGODB_URL → prod, `ENABLE_JOBS=false`). Đúng discipline khi đang research trên prod data, nhưng nếu chuyển sang dev local: `cp ../pocketquant-config/local/all-local.env .env`. KHÔNG chạy pytest khi .env còn trỏ prod (conftest tự refuse). Không tự restore trong session này vì user có thể còn dùng prod data cho research tiếp.

### 4. Research caches ephemeral
`/tmp/pq_cache_{BTCUSDT,ETHUSDT,SOLUSDT}` mất giữa session. Tái lập: `uv run python plans/260712-0849-engulfing-structure-level-taker-profit/scripts/pq_prefetch_multi.py` (đọc prod read-only). Scripts nhận cache qua `pq_structure_lib.use_cache()`.

## Câu hỏi mở (logged thay vì hỏi, theo yêu cầu)

1. **Pivot Frame C hay dừng?** — quyết định lớn nhất, quyết scope research kế (xem mục 1).
2. Nếu Frame C: universe symbol nào (chỉ 3 hiện có hay thêm), vol-targeting theo ATR hay realized vol, drawdown control mức nào? — thuộc brainstorm mới.
3. WS bug: có kế hoạch thêm symbol runtime thường xuyên không? Nếu có → nâng priority fix; nếu không → giữ workaround.
4. Funding perp chưa mô hình hóa trong mọi backtest research (giữ lệnh vài chục giờ → funding đáng kể, đẩy net âm hơn). Nếu còn research hold-dài thì phải thêm.
5. Fee tier thật của account (maker rebate?) — chỉ còn relevant nếu quay lại Test A.
