# PocketQuant TODO

- read all docs, and clean up
- read strategy lifecycle and refactor
- submit binance orders


- unsubscribe_order_updates clear tất cả callback → phải đảm bảo thứ tự subscribe collector-trước-bridge và cả 2 active suốt replay (Phase 2 risk).
- Mark-to-market 1m × 2 năm = ~1M điểm → nguy cơ vượt Mongo 16MB → downsample khi persist (Phase 3 risk).

3 câu hỏi mở (ở phase-04)

1. Prod re-smoke có được duyệt không? (lúc audit bạn chọn "không ghi prod" — verify end-to-end cần ghi 1 doc).
2. Live OKX fill path có cùng cơ chế callback PaperBroker không? (live chưa chạy → follow-up, không chặn).
3. Ngưỡng downsample equity_curve khi persist — chốt số cụ thể lúc implement.
4. 