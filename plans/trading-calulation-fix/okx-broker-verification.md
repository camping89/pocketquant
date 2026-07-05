# OKX Broker Verification — thick or thin?

> Giải câu hỏi mở #1 của `roadmap.md` (R3/R4): OKX trả **closed-PnL per position** hay **chỉ fills**? → quyết `IBrokerPort` có cân xứng paper↔OKX được không.

## Kết luận

**OKX là THICK broker — trả CẢ commission (`fee`) LẪN realized/closed PnL.** `IBrokerPort` cân xứng được: paper **tính** (CommissionModel + PositionAggregate), OKX **đọc** từ venue. Không bất đối xứng. Model E khả thi.

Xác nhận 2 nguồn: code adapter hiện tại + OKX v5 API docs (WebSearch).

## OKX v5 thực sự trả gì (docs)

| Kênh | Field kinh tế | Nghĩa |
|---|---|---|
| `orders` (WS) | `fee`, `fillFee`, `fillPnl`, `pnl`, `tradeId`, `execType` | phí + realized PnL **mỗi fill** + taker/maker |
| `positions` (WS) | `upl`, `pnl`, `fee`, `fundingFee`, `avgPx`, `realizedPnl` | PnL realized + funding khi position đổi |
| positions-history (REST) | `realizedPnl`, `fee`, `fundingFee`, `pnl`, `pnlRatio`, open/close avgPx, times | **Trade đóng sẵn** — map thẳng sang `Trade` |

→ OKX tự tính order→position→closed-trade + fee + PnL, dùng **average-cost** (`avgPx`) — **khớp** mô hình average-cost của paper broker (Model E). Trade contract cân xứng.

## Code hiện tại UNDER-MAP (đây là gap thật, không phải thiếu data)

| Nơi | Map gì | BỎ LỠ |
|---|---|---|
| `OkxOrderMapper.to_order_result` | `state, accFillSz, avgPx, ordId, clOrdId` | **`fee`, `fillPnl`, `pnl`, `tradeId`, `side`, `sl/tp`** |
| `OkxPositionMapper.to_position_update` | `pos, avgPx, upl, markPx, lever` | **`realizedPnl`, `fee`, `fundingFee`, `pnl`** |
| `_handle_position_update` | **chỉ log** | không emit event/callback (comment: "Future: could emit") |
| `map_okx_balance_to_domain` | `eq, availBal, frozenBal, upl` | realized pnl |

→ Việc OKX cho R3/R4 chủ yếu là **map thêm field đã có sẵn trong payload** + **emit Trade khi position close** (hiện chỉ log), KHÔNG phải dựng mới.

## Ảnh hưởng tới R3/R4

- **R3 commission**: `OrderResult.commission` ← OKX `fee` (đang bỏ lỡ, chỉ cần map). Paper mô phỏng qua `CommissionModel`. Cân xứng. ✅
- **R4 Trade emission**: paper emit Trade từ `PositionAggregate` khi close; OKX emit từ position-close event (`pos`→0, có `realizedPnl`) hoặc positions-history. Cùng `Trade` shape. `_handle_position_update` sẽ được nối để phát Trade (R4/R8).
- **Trigger khác nhau, OUTPUT giống nhau**: paper check SL/TP nội bộ; OKX venue báo close. Abstraction ở OUTPUT (`subscribe_trade`), không phải trigger. ✅

## Caveat mới (thêm vào roadmap)

1. **Dấu `fee`**: OKX `fee` thường **âm** (phí), maker có thể **dương** (rebate). `Trade.commission`/`OrderResult.commission` là chi phí dương → cần đổi dấu (`abs`/`-fee`) khi map.
2. **`feeCcy`**: phí có thể ở currency khác quote — cần chuẩn hoá về quote.
3. **Funding fee (SWAP)**: OKX tính funding mỗi 8h (`fundingFee`); paper broker **không mô phỏng** → gap parity trên perpetual. YAGNI trước mắt nhưng phải ghi nhận (R3).
4. **Trade source OKX**: chọn `orders.fillPnl` (per-fill) vs `positions.realizedPnl` vs positions-history (closed trade sẵn). Quyết trong R4.
5. **WS order mapper mất `side`/`sl`/`tp`**: `to_order_result` không set `side` — latent issue cho direction (FIFO đang xoá nên nhẹ, nhưng Trade cần side → map lại ở R4).
6. **`sprd-orders` (spread) không có fee** trên WS — nếu sau này dùng spread, đọc fee từ REST `sprd/trades`. Ngoài scope hiện tại.

## Unresolved (chuyển vào R tương ứng)

- R4: chốt nguồn Trade cho OKX (orders vs positions vs history) — cần chạy demo để xem payload thật.
- R3: funding fee có mô phỏng ở paper không, hay chấp nhận gap?
- Xác minh field trên `python-okx` SDK response thật (demo mode) khi implement — docs có thể lệch version.

## Sources
- [OKX API v5 docs](https://www.okx.com/docs-v5/en/)
- [OKX WebSocket API guide](https://github.com/lhzk377/okx-websocket-api-docs)
- [NautilusTrader OKX integration](https://nautilustrader.io/docs/latest/integrations/okx/)
