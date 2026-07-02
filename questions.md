# Questions — backtest chart orders visualization (cook 260701-0044)

> Log câu hỏi cho user check sau. Tôi tự quyết theo default hợp lý + ghi lại đây để review.

## Đã tự quyết (cần xác nhận, không block)

1. **CSS chart height**: plan đề xuất desktop ~420px, mobile ~280px. Repo CSS là **mobile-first** (base = mobile, `@media (min-width:768px)` = desktop), khác mô tả plan ("media query mobile ~1539"). → Tôi đặt base `height:280px` + desktop override `420px`. Xác nhận lại giá trị thẩm mỹ khi xem UI thật.

2. **defaultIndicators cho backtest chart**: `DEFAULT_INDICATORS` ở `routes/index.tsx` bật `ema:true, engulfing:true`. Backtest chart tôi để **tắt hết** (`all false`) — backtest chỉ cần nến + markers + box. Có muốn bật EMA mặc định cho backtest không?

3. **Markers vẫn vẽ TẤT CẢ positions** (không chỉ lệnh được chọn) — giữ theo plan. Box chỉ vẽ cho lệnh highlight/hover. Lệnh trùng timestamp → marker gộp `BUY ×N` (sẵn có).

## Theo dõi khi verify UI

4. **Run cũ thiếu `config_snapshot.symbol`**: nếu doc cũ không có symbol composite → chart hiện fallback message, không crash. Verify run cũ thực tế (acceptance #4).

5. **Auto-scroll pad = 50 nến mỗi bên**: lệnh giữ rất lâu → box rộng hơn viewport, vẫn scroll `entry-50 .. exit+50`. Có muốn behavior khác (vd chỉ center entry)?

---

# Open Questions — scroll-left pagination cho chart (task trước)

## 1. DB có đủ nến lịch sử không? (prerequisite, CHƯA kiểm chứng)
Pagination giờ chạy đúng, nhưng độ sâu lịch sử bị giới hạn bởi dữ liệu thực có trong Mongo.
Nếu backfill mỏng (default `n=100` ở `tracked_symbols_backfill.py`), `hasMore` sẽ thành
`false` sớm và chart vẫn "dừng" — nhưng vì hết data, không phải lỗi fetch.
- **Câu hỏi:** có cần chạy backfill sâu hơn cho các symbol/interval chính (vd 1m BTCUSDT:BINANCE)?
- **Cần làm rõ:** ngưỡng backfill mong muốn (vd 5000 nến? 30 ngày?) cho mỗi interval.
- Việc đếm nến trong DB cần truy cập prod VPS DB → chưa tự ý chạy (theo memory: .env discipline).

## 2. PAGE_SIZE = 1000 — giữ hay nâng?
Mỗi older-page fetch 1000 nến. Có thể nâng tới 5000 (`LIMIT_OHLCV_QUERY_MAX`) để giảm số
round-trip khi user scroll xa. Hiện để 1000 cho cân bằng latency/payload.
- **Câu hỏi:** ưu tiên ít round-trip (5000) hay payload nhỏ mỗi lần (1000)?

## 3. Trigger threshold `from < 10` — tinh chỉnh?
loadOlder kích hoạt khi mép trái cách nến cũ nhất < 10 nến. Có thể cần prefetch sớm hơn
(vd < 50) để tránh "khựng" khi scroll nhanh. Chưa đo trên data thật.

## 4. Áp dụng cho strategy-chart?
`strategy-chart.tsx` cũng dùng `useOHLCV` nhưng chưa wire pagination (ngoài scope yêu cầu).
- **Câu hỏi:** có muốn áp dụng scroll-left pagination cho cả strategy-chart không?
