# Brainstorm — Backtest Research Workbench

Reframe trang `/backtest` (hiện ad-hoc, single-run, ephemeral) thành **workbench phân tích cho trader định hướng thống kê**: giàu metric, có lịch sử, so sánh được nhiều run, drill-down tới order/fills, và (mới) MAE/MFE per trade.

- **Mode:** brainstorm (no flags)
- **Scope chốt:** B (Research Workbench) + Orders endpoint + Verdict UI + MAE/MFE track
- **Layout single-run:** tab
- **Charting:** lightweight-charts (time-series) + visx (histogram/heatmap)

## 1. Problem statement

Trader thống kê cần đọc nhanh "tốt/xấu", mổ xẻ phân phối lời/lỗ, đánh giá drawdown & robustness, và **so sánh nhiều biến thể tham số** để chốt strategy. UI hiện tại không phục vụ được:

- Kết quả lưu ở client state (`activeRunId`) → **reload là mất**, không có lịch sử.
- 14 metric phẳng, không phân nhóm, không ngữ cảnh tốt/xấu.
- Equity chỉ là sparkline 60px, **không** underwater/drawdown, **không** monthly heatmap, **không** phân phối PnL.
- **Không** so sánh nhiều run dù backend đã hỗ trợ.
- `backtest_orders` (orders + fills + events) **ghi mà không có route đọc** → write-only.
- **Không** có MAE/MFE / R-multiple (chuẩn của stats trader).

### Bản đồ 3 tầng (DB → API → UI) — nơi đứt gãy

| Dữ liệu | DB | API | UI | Đứt ở |
|---|:--:|:--:|:--:|---|
| `metrics` (14) | ✅ | ✅ `GET /{run_id}` | ✅ MetricsTab | — |
| `equity_curve` (+`drawdown` mỗi điểm) | ✅ | ✅ (+ `GET /{run_id}/equity`) | ⚠️ chỉ sparkline | UI nghèo |
| `trades` | ✅ | ✅ `GET /{run_id}/trades` | ✅ PositionsTable | — |
| Lịch sử run | ✅ `backtest_runs` | ✅ `GET /backtest/strategy/{id}` | ❌ | **UI** |
| `verdict` | ✅ | ✅ `PATCH .../verdict` | ❌ | **UI** |
| `orders`+fills+events | ✅ `backtest_orders` | ❌ không route | ❌ | **API** |
| MAE/MFE/R-multiple | ❌ | ❌ | ❌ | **toàn bộ** |

**Nguyên nhân gốc:** xây theo slice, backend đi trước FE. `git status` còn các report slice chưa merge: `backtest-history-comparison`, `adhoc-backtest-run`.

## 2. Codebase context (scout)

- **Styling:** thuần CSS variables, dark/light theme (`data-theme`), palette 9 token (accent `#D97757`, up `#4A9782`, down `#C96442`). **Không Tailwind/component-lib.** Font system + mono `tabular-nums` cho số.
- **Chart:** `lightweight-charts v5.1.0` — candlestick + markers + position boxes + `EquitySparkline`. Màu đọc từ CSS variables qua `readChartColors()`.
- **Shell:** TanStack Router, nav ngang `Charts | Strategies | Backtest | Monitor`. Data qua TanStack React Query (`useBacktestRun` poll 1.5s).
- **Backtest UI:** `/backtest` rộng 720px 1 cột, form → 3 tab `Metrics | Equity | Trades`. Reusable: `MetricCard`, `PositionsTable`, `StatusPill`, `EquitySparkline`, Tabs.
- **Persistence:** 3 collection `backtest_runs` / `backtest_orders` / `backtest_trades`, full read/write repo (`list_by_run`, `list_by_strategy_code`, `get_best_by_metric`, `list_top_pnl`). Equity downsample ≤5000 điểm.

## 3. Evaluated approaches

| | A: Stat Pack | B: Research Workbench | C: Full Forensics |
|---|---|---|---|
| Nội dung | giàu single-run | A + history + compare | B + MAE/MFE + orders |
| Backend | không | không (API sẵn) | có (engine + route) |
| ROI | cao | cao nhất | trung bình |
| Rủi ro | thấp | thấp | trung bình |

**Chốt:** B làm nền, **cộng** Orders + MAE/MFE (các phần "C" đã verify là khả thi rẻ/vừa). Lý do: tận dụng đúng data + endpoint đã build sẵn; MAE/MFE tái dùng hook bar có sẵn nên không phải đại phẫu.

## 4. Final design

### 4.1 Information architecture (deep-link theo runId → reload-safe)

```
/backtest                          shell: strategy selector + run history rail
├─ /backtest            (index)    empty state + run form
├─ /backtest/$runId                single-run dashboard (load từ GET /{run_id})
└─ /backtest/compare?runs=a,b,c    comparison 2–3 run
```

### 4.2 Single-run dashboard — 4 tab

- **Overview:** KPI hero (5 card tone-màu) · metrics phân 3 nhóm (Returns/Risk/Trade Stats qua `MetricGroup`) · **Equity + Underwater** full-width (drawdown đã có sẵn mỗi điểm).
- **Trades:** **PnL histogram** + **Duration histogram** (visx) · win/loss streak · profit factor LONG vs SHORT · bảng trades (tái dùng `PositionsTable`) + **cột MAE/MFE/R-multiple** (— nếu null).
- **Risk & Time:** **Monthly returns heatmap** (visx, năm×tháng, resample client) · **Drawdown table** top-N (depth/start→trough/recovery/duration) · **MAE/MFE scatter** (mfe vs mae, màu theo win/loss).
- **Orders:** bảng orders (lazy-load) → drawer drill-down `fills[]` + `events[]`, link `resulting_trade_id` ↔ trade.

**Verdict:** card header dashboard — đọc `verdict` từ full result, textarea edit, Save → `PATCH /{run_id}/verdict`.

### 4.3 History & Compare

- **Run history rail:** `GET /backtest/strategy/{id}` → bảng run (started_at, status, return/sharpe/win_rate/max_dd/#trades, verdict snippet), sort client-side (KISS — không cần `get_best_by_metric` endpoint), checkbox chọn 2–3.
- **Compare view:** equity overlay normalize % (3 đường) + metrics diff table (cột=run, highlight ô tốt nhất mỗi hàng).

### 4.4 Charting phân vai

| Loại | Lib |
|---|---|
| equity, underwater, candle, equity-overlay | lightweight-charts (đã có) |
| PnL/duration histogram, monthly heatmap, MAE/MFE scatter | visx (mới, modular: `@visx/scale @visx/shape @visx/group @visx/axis`), fill = CSS variables |

> Alternative: Observable Plot — loại vì nặng + khó ép CSS-variable theming dark/light.

### 4.5 Backend changes

| Việc | Chi tiết | Đụng |
|---|---|---|
| `GET /backtest/{run_id}/orders` | wrap `BacktestOrderRepository.list_by_run` (ĐÃ CÓ) → DTO + fills/events | route + 1 query method. **Không** đụng engine |
| MAE/MFE/R-multiple | track running excursion trong `_mtm_on_bar` (hook + OHLC high/low đã có); gắn vào `Trade` khi consume lot | `lot_tracker.OpenLot` + `Trade` (+to/from_mongo) + collector `update_excursions()` |
| verdict | PATCH đã tồn tại | chỉ wire UI |
| ranking | sort client-side | không thêm endpoint |

## 5. Implementation tracks (ranh giới PR)

| Track | Loại | Rủi ro | Độc lập? |
|---|---|---|:--:|
| 1. Stat Pack (Overview+Trades+Risk panels, visx) | FE | thấp | ✅ |
| 2. History rail + Compare view + routing `$runId`/`compare` | FE | thấp | ✅ |
| 3a. Orders endpoint + tab Orders | BE+FE | thấp | ✅ |
| 3b. MAE/MFE engine track + cột/scatter | BE+FE | trung bình | ✅ (deploy trước mới có data) |
| 4. Verdict panel | FE | thấp | ✅ |

## 6. Risks

- **Equity downsample ≤5000 điểm** → monthly heatmap & drawdown-recovery là **xấp xỉ**, không chính xác tuyệt đối. Chấp nhận cho phân tích trực quan; cần chính xác phải thêm endpoint full-resolution (ngoài scope).
- **MAE/MFE forward-only:** run cũ = null (không backfill). UI hiển thị "—".
- **R-multiple cần SL:** trade thiếu `sl_price` → null.
- **Orders nhiều** với backtest dài → tab Orders lazy-load + virtualize bảng.
- **visx thêm dep** (đã đồng ý) — giữ modular để bundle nhỏ.
- **Migration-tolerance:** `Trade.from_mongo` phải `.get('mae', None)` cho doc cũ.

## 7. Success metrics

- Reload `/backtest/$runId` giữ nguyên kết quả (không còn ephemeral).
- Single-run dashboard render đủ: KPI hero, metrics nhóm, equity+underwater, 2 histogram, monthly heatmap, drawdown table, orders drill-down, verdict edit.
- Compare 2–3 run: equity overlay + diff table highlight đúng ô best.
- Run mới sau deploy có MAE/MFE/R-multiple; run cũ hiển thị "—" không lỗi.
- `npm run lint && npm run build` pass; `just lint && just types && just test` pass cho backend track.

## 8. Next steps & dependencies

1. `/ck:plan` chia phase theo 5 track (track 1/2/4 thuần FE chạy song song được; 3a/3b backend tách PR).
2. Track 3b (MAE/MFE) nên deploy sớm để bắt đầu tích lũy data cho run mới.
3. Xác nhận thư viện visx version khi plan (kiểm tra tương thích React 19).

## Unresolved questions

1. Gộp tất cả 5 track vào 1 plan nhiều phase, hay tách MAE/MFE (3b) thành plan/PR riêng vì là track backend rủi ro cao hơn?
2. Monthly heatmap dùng equity downsample (xấp xỉ) có chấp nhận được không, hay cần endpoint full-resolution riêng (mở rộng scope)?
3. visx có tương thích React 19 ổn không — cần verify lúc plan (nếu vướng, fallback uPlot hoặc tự vẽ SVG).
