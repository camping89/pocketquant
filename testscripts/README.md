# Testscripts

Debug scripts chia theo nhóm, chạy từ project root.

## Yêu cầu

```bash
just up  # khởi MongoDB (27018) + Redis (6379)
```

| # | Script                                                  | Mô tả                                        |
|---|---------------------------------------------------------|----------------------------------------------|
| 1 | `python3 testscripts/debug-01-infra-health.py`          | Kiểm tra kết nối MongoDB + Redis             |
| 2 | `python3 testscripts/debug-02-sync-btc-4h.py`           | Sync BTC 4H từng bước (debug chính)          |
| 3 | `python3 testscripts/debug-03-query-ohlcv.py`           | Truy vấn dữ liệu OHLCV đã sync               |
| 4 | `python3 testscripts/debug-04-sync-status.py`           | Xem trạng thái sync & symbols                |
| 5 | `python3 testscripts/debug-05-full-sync-via-handler.py` | Test full pipeline CQRS (Mediator → Handler) |

## Scripts khác

| Script              | Mô tả                                               |
|---------------------|-----------------------------------------------------|
| `test_sync_jobs.py` | Test scheduled jobs (sync_daily, sync_all)          |
| `stream_quotes.py`  | Stream giá real-time qua WebSocket                  |
| `api-test.http`     | Tất cả API endpoints (dùng với VS Code REST Client) |

## Tuỳ chỉnh

```bash
# Đổi symbol/interval/số lượng bar
python3 testscripts/debug-02-sync-btc-4h.py --symbol ETHUSD --exchange BINANCE --interval 1h --bars 50
python3 testscripts/debug-03-query-ohlcv.py --symbol BTCUSD --interval 4h --limit 20 --start 2026-01-01
```

## Section 2 vs 5

- **Section 2**: Gọi provider + repo trực tiếp → dễ tìm lỗi ở layer nào
- **Section 5**: Qua Mediator → Handler → giống API thật
