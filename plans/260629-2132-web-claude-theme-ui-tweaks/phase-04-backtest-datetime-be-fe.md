---
phase: 4
title: "Backtest datetime BE+FE"
status: done
priority: P2
dependencies: []
effort: "M"
---

# Phase 4: Backtest datetime BE+FE

<!-- Updated: Validation Session 1 - thêm result_collector.py (FAILED verify); TZ convert theo dropdown→UTC; baseline recipe `just baseline`; test fixtures date→datetime -->

## Overview

Cho phép backtest chọn thời gian tới **phút** (thay vì chỉ ngày). Đổi `start_date`/`end_date` từ `date` → `datetime` ở backend (public contract của `POST /api/v1/backtest/run`), và FE đổi `<input type="date">` → `datetime-local` với default end=now, start=now−1 năm.

## Requirements

- Functional: form gửi datetime tới phút; backend load bars đúng range `[start_datetime, end_datetime]`; default end=now, start=now−1y.
- Non-functional: backward-compat ở mức parse — `datetime.fromisoformat` chấp nhận cả `"2026-01-01"` (date thuần, → 00:00:00) lẫn `"2026-01-01T09:30"`.
- TZ (validation 1): input theo **tz dropdown đang chọn** (UTC/Local của `TimezoneSwitcher`), FE **convert sang UTC** trước khi gửi. Backend nhận UTC naive (đồng bộ `lib/datetime.ts` parse naive=UTC).

## Architecture

### Backend (chuỗi date→datetime)

`date` xuất hiện ở 4 file backtest. Đổi:

1. **`backtest_command_service.py`** `RunBacktestCommand`: `start_date: date` → `datetime`, `end_date: date` → `datetime`. `config["start_date"] = cmd.start_date.isoformat()` giữ nguyên (datetime.isoformat ra `2026-01-01T09:30:00`). Import `datetime`.
2. **`models/backtest_config.py`** `BacktestConfig`: `start_date: date` → `datetime`, `end_date: date` → `datetime`. Import `datetime`.
3. **`workers/backtest_dispatch.py`** `_config_from_dict`: `date.fromisoformat` → `datetime.fromisoformat` (chấp nhận cả date-only string). Import `datetime`.
4. **`engine/backtest_app_service.py`** `_load_bars`: bỏ `datetime.combine(config.start_date, datetime.min.time())` / `datetime.max.time()`; dùng thẳng `config.start_date` / `config.end_date` (đã là datetime). Giữ semantics end-inclusive: `bar_repo.stream` dùng `$lte end_datetime` — nếu user chọn end=09:30 thì bar 09:30 included, bars sau loại. (Trước đây end=ngày → 23:59:59.999999 cuối ngày; giờ end=phút chính xác hơn — đúng ý task.)

### Backend — `result_collector.py` (VERIFIED callsite — bắt buộc sửa)

Grep xác nhận `result_collector.py` đụng `config.start_date` ở 3 chỗ:
- **dòng 82** — `EquityPoint(timestamp=datetime.combine(config.start_date, datetime.min.time()), ...)`. Khi `start_date` thành `datetime`: `datetime.combine(dt, time)` vẫn hợp lệ (datetime là subclass của date, combine lấy phần date) NHƯNG nó vứt phần giờ/phút → sai khi user chọn intraday start. **Sửa: dùng thẳng `config.start_date`** (đã là datetime đầy đủ), bỏ `datetime.combine`. Verify import `datetime` còn dùng chỗ khác trong file trước khi gỡ.
- **dòng 425** — truyền `start_date=self._config.start_date` vào `build_metrics`. Giữ nguyên (build_metrics nhận datetime sau khi đổi type hint).
- **dòng 436** — `"start_date": self._config.start_date.isoformat()` trong config_snapshot. `datetime.isoformat()` OK, giữ nguyên.

### Backend — callers `BacktestConfig` khác

`metrics_builder.build_metrics(start_date, end_date)` type hint `date`, dùng `(end_date - start_date).days`. `datetime - datetime` cũng ra `timedelta` có `.days` → vẫn chạy. Cập nhật type hint `date` → `datetime`; logic giữ. Caller duy nhất = `result_collector.py:419` (verified).

`jobs/backtest_strategy_loader.py` `resolve_date_range` trả `tuple[date, date]`, `build_backtest_config(start_date: date, end_date: date)` tạo `BacktestConfig`. Hiện **không có caller** (forward-test job chưa wire — đã grep xác nhận). Nhưng `BacktestConfig` field giờ là `datetime` → truyền `date` vào dataclass vẫn chạy (Python không enforce), chỉ lệch type hint. Để tránh nợ kỹ thuật: đổi `build_backtest_config` truyền datetime (vd `datetime.combine(start, time.min)`), hoặc cập nhật type hint. KISS: cập nhật type hint + `datetime.combine` cho an toàn `_load_bars`. Ghi rõ trong steps.

### Backend — snapshot tests

`tests/baseline/openapi_app_snapshot.json` + `route_inventory_app_snapshot.json` chứa schema OpenAPI. Đổi `date` → `date-time` format sẽ làm snapshot lệch → test fail. **Phải regenerate** baseline snapshot (có recipe? kiểm `just` hoặc script). Đây là việc bắt buộc, không bỏ qua.

### FE (`backtest-form.tsx`) — TZ-aware theo dropdown (validation 1)

- `INPUT type="date"` → `type="datetime-local"` cho start + end.
- Lấy `const { mode, suffix } = useTimezone()` — input hiển thị/nhập theo mode đang chọn.
- Default (theo mode): dùng `dayjs` + plugin utc (đã extend ở `datetime.ts`) —
  ```ts
  const fmt = 'YYYY-MM-DDTHH:mm'  // datetime-local control format
  // "now" và "now-1y" hiển thị theo mode đang chọn:
  const base = mode === 'utc' ? dayjs().utc() : dayjs()
  const [endDate, setEndDate] = useState(base.format(fmt))
  const [startDate, setStartDate] = useState(base.subtract(1, 'year').format(fmt))
  ```
- Validate: `startDate > endDate` so sánh string (datetime-local format sortable) — giữ check hiện có.
- **Convert→UTC khi submit**: giá trị input là "wall-clock" theo mode. Nếu mode=`utc` → gửi nguyên (đã là UTC). Nếu mode=`local` → `dayjs(value).utc().format('YYYY-MM-DDTHH:mm:ss')` để chuyển local→UTC naive trước khi gửi. Backend luôn nhận UTC naive.
  ```ts
  const toUtcSubmit = (v: string) =>
    mode === 'utc' ? v : dayjs(v).utc().format('YYYY-MM-DDTHH:mm:ss')
  // body: start_date: toUtcSubmit(startDate), end_date: toUtcSubmit(endDate)
  ```
  > Lưu ý: `dayjs(v)` (không utc) parse `v` theo local tz của browser → `.utc()` chuyển sang UTC. Đúng khi mode=local. Khi mode=utc, `v` đã là UTC wall-clock nên gửi thẳng (không re-parse qua local).
- Hiển thị `suffix` (UTC / GMT+7…) cạnh label start/end để user biết input đang theo tz nào.
- Khi user đổi dropdown lúc form đang mở: giá trị input KHÔNG tự convert (giữ KISS — tránh re-compute gây nhảy số). Suffix đổi để phản ánh mode mới; user nhập lại nếu cần. Note hành vi này.

## Related Code Files

- Modify: `src/pocketquant/backtest/backtest_command_service.py`
- Modify: `src/pocketquant/backtest/models/backtest_config.py`
- Modify: `src/pocketquant/backtest/workers/backtest_dispatch.py`
- Modify: `src/pocketquant/backtest/engine/backtest_app_service.py` (`_load_bars` bỏ combine, dòng 84 isoformat OK)
- Modify: `src/pocketquant/backtest/engine/result_collector.py` (dòng 82 bỏ datetime.combine; 425/436 giữ)
- Modify: `src/pocketquant/backtest/engine/metrics_builder.py` (type hint date→datetime)
- Modify: `src/pocketquant/backtest/jobs/backtest_strategy_loader.py` (type hint + datetime.combine)
- Modify: `web/src/components/backtest/backtest-form.tsx` (datetime-local + TZ convert + useTimezone)
- Regenerate: `tests/baseline/openapi_app_snapshot.json`, `tests/baseline/route_inventory_app_snapshot.json` (recipe: `just baseline` hoặc `BASELINE_UPDATE=1 .venv/bin/python -m pytest tests/baseline/test_openapi_snapshot.py`)
- Fix fixtures (date→datetime): `tests/backtest_test/engine/test_result_collector_mark_to_market.py`, `test_engulfing_backtest.py`, `test_hitnrun2_backtest.py`, `test_backtest_app_service_persistence.py` (2 chỗ), `test_result_collector_fifo.py`

## Implementation Steps

1. (Đã grep ở validation) callsites: `result_collector.py` (82/419/425/436), `backtest_app_service.py` (84/181), 5 test fixtures. Xác nhận lại nếu code đổi từ lúc plan.
2. BE đổi type `date`→`datetime` theo thứ tự: `backtest_config.py` → `backtest_command_service.py` → `backtest_dispatch.py` (`datetime.fromisoformat`) → `backtest_app_service._load_bars` (bỏ combine) → `result_collector.py` (dòng 82 bỏ combine) → `metrics_builder` type hint → `backtest_strategy_loader` (type hint + `datetime.combine`).
3. Chạy `just types` (mypy) — sửa mọi lỗi type phát sinh.
4. Sửa 5 test fixtures: `start_date=date(2024,1,1)` → `datetime(2024,1,1)` (import datetime). Chạy `just test-pkg backtest` — đảm bảo pass.
5. Regenerate baseline: `just baseline` (hoặc `BASELINE_UPDATE=1 .venv/bin/python -m pytest tests/baseline/test_openapi_snapshot.py`). Review diff: chỉ `start_date`/`end_date` đổi `format: date`→`date-time`. Chạy `tests/baseline/` pass.
6. FE `backtest-form.tsx`: `datetime-local` + `useTimezone` + default 1y theo mode + convert→UTC khi submit + suffix label. `npm run lint` + `npm run build`.
7. E2E thủ công: backtest range tới phút (start 09:00 end 15:30 cùng ngày, symbol sync 1m) → bars đúng cửa sổ phút; default 1y → chạy bình thường; đổi dropdown Local → nhập giờ local → confirm BE nhận đúng UTC tương ứng.

## Success Criteria

- [ ] `POST /api/v1/backtest/run` chấp nhận datetime tới phút; bars load đúng `[start, end]` theo phút.
- [ ] `result_collector.py` dòng 82 dùng start_date đầy đủ (không vứt giờ/phút qua combine).
- [ ] Form default end=now, start=now−1y theo mode; chọn được phút; suffix tz hiển thị.
- [ ] mode=local: giờ nhập được convert đúng sang UTC trước khi gửi (verify E2E).
- [ ] `just types` pass; `just test-pkg backtest` pass (5 fixtures đã đổi datetime).
- [ ] `just baseline` regenerate + `tests/baseline/` pass; diff chỉ start_date/end_date format.
- [ ] Backward-compat: date-only string vẫn parse (→ 00:00:00).
- [ ] `npm run lint` + `npm run build` (web) pass.

## Risk Assessment

- **Breaking OpenAPI contract** — `date`→`date-time`. Mitigation: regenerate baseline (step 5); không có client ngoài FE (đã grep). Bruno/`api-test.http` dùng date-only vẫn parse OK.
- **`_load_bars` end-inclusive semantics đổi** — trước cuối ngày, giờ chính xác phút. Đây là behavior mong muốn (task). Note rõ để không hiểu nhầm là regression.
- **`build_metrics` `.days` = 0** khi backtest intraday (start/end cùng ngày) → `cagr` chia cho `max(days,1)=1`. Đã có `max(...,1)` guard → an toàn, nhưng cagr intraday vô nghĩa. Chấp nhận (ngoài scope task).
- **Test characterization fixtures** dùng `date(...)`. Mitigation: step 1 grep trước, step 4 cập nhật.

## Resolved (validation 1)

- Input `datetime-local` theo **tz dropdown đang chọn**; FE convert→UTC trước khi gửi (mode=local dùng `dayjs(v).utc()`). Backend luôn nhận UTC naive. Suffix tz hiển thị cạnh label. Đổi dropdown lúc form mở: không tự convert giá trị (giữ KISS), chỉ đổi suffix.
