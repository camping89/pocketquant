# Kongming 2026-10-23 01:08 — Có thể đóng hàng 2 và 3 của T8.7 mà không chờ cuối tuần không?

Runtime: Claude Code, model `fable` (Claude Fable 5.1). Read-only; không ssh, không gọi prod hay Exness.

## TL;DR

Không nên đóng hàng 2 và 3 bằng verdict PASS ngay bây giờ. Phần lớn tiêu chí (misaligned, lưới lịch so với venue qua cuối tuần, gate đóng cửa của `sync_1m`, `running 2`, p95) đã được code, unit test và bằng chứng hàng 0 phủ đủ; nhưng tiêu chí trung tâm của hai hàng này — `CB=0` khi WS ticks nằm im ~48 giờ — không có bằng chứng nào ngoài việc chạy thật, vì code WS Exness mới lên prod ngày 2026-10-19 và chưa từng trải qua cuối tuần nào. Chi phí chờ là hai lần kiểm tra ~10 phút (Sat 10:00 và Mon 10:00 Bangkok) và không phase nào bị chặn; nếu vẫn muốn đóng sớm thì ghi rõ "waived (user decision)" thay vì PASS, và chuyển riêng phép đếm `CB`/`RC` cuối tuần sang một lần kiểm tra thứ Hai.

## Bài toán thực sự

Quyết định không phải là "code có đúng không" mà là "bằng chứng nào mà chỉ cuối tuần thật mới tạo ra được, và nó có đáng hai lần kiểm tra ngắn không". Yêu cầu: giữ nguyên nghĩa của verdict PASS trong T8.7/T8.8; không phá cam kết `plan.md:54` ("across a weekend close and reopen") mà không ghi lại quyết định. Non-goal: kiểm tra DST (đã chuyển sang plan riêng, `phase-08:296-297`).

## 1. Các tiêu chí áp dụng cho hàng 2 và 3

Nguồn: `phase-08-validation-spread-backtests-paper-week.md:253-258` (Pass every row), `:265-266` (hai hàng), `:285-291` (T8.8), `:161` (Goal T8.7), `plan.md:54` (Paper week).

| # | Tiêu chí | Chứng minh điều gì (nói đơn giản) |
|---|---|---|
| P1 | `misaligned 0` trên mọi dòng C3 (`:254`) | Mọi bar 1m/1h đã lưu nằm đúng lưới UTC; không có bar lệch giờ sinh ra quanh giờ đóng/mở cửa. |
| P2 | Mọi `gap_ranges` đều venue-empty, C3 in `PASS` (`:255`) | Lịch (`ExnessSessionCalendarAdapter`) và dữ liệu thật của Exness khớp nhau qua Fri close → Sun reopen: chỗ nào lịch bảo "phải có bar" mà DB thiếu thì Exness cũng không có bar đó, tức là `sync_1m` không bỏ sót bar nào mà venue có. |
| P3 | Quy tắc tái kiểm/repair một lần (`:256`) | Một thiếu sót do thời điểm đo hoặc do một lần sync lỡ phải được lấp bằng `integrity/repair`; chỉ khi repair không lấp được thì hàng mới fail. |
| P4a | `sync_1m p95_ms < 60000` cửa sổ 7d (`:257`) | Job mỗi phút không bị chậm quá một phút trong cả tuần, kể cả khi các symbol đóng cửa bị skip. |
| P4b | `CB=0` (`:257`) | Suốt cửa sổ log (hàng 2: từ 2026-10-20T22:33Z hoặc từ `StartedAt`; hàng 3: từ hàng 2) WS ticks không bao giờ có 10 lần kết nối thất bại liên tiếp — tức là Exness vẫn chấp nhận kết nối/reconnect khi thị trường đóng và WS nằm im. Đây là lý do tồn tại của hàng 2 ("ticks WS idle", `:265`). |
| P4c | `running 2` (`:257`) | Hai subscription paper vẫn ở `actual_state == running` sau 48 giờ không có bar nào và sau các lần deploy. |
| P5 | Ghi nhận: `missing`, venue-empty ranges, `RC`, `RL`, `by_status` (`:258`) | Không pass/fail, nhưng `RC` qua cuối tuần là con số duy nhất cho biết WS idle có reconnect liên tục hay không. |
| T8.8 | Mỗi hàng 0–3 có verdict PASS; dòng tổng kết; hỏi user giữ/dừng subscription (`:286-291`) | Phase chỉ đóng khi bảng kết quả có PASS thật cho 4 hàng. |
| Goal | "a live XAUUSD daily break and a weekend close and reopen" (`:161`); `plan.md:54` | Cam kết của plan: đã nhìn thấy một cuối tuần thật. Hàng 1 đã phủ daily break; hàng 2–3 là nửa còn lại. |

## 2–3. Bằng chứng và phán quyết từng tiêu chí

Ký hiệu: **FACT** = tôi đã đọc code/test/file hoặc chạy test; **INFER** = suy luận của tôi.

### P1 `misaligned 0` — Phủ, không cần chờ

- FACT: `bar_start` của lịch Exness là `get_bar_start` trên lưới UTC (`exness_session_calendar_adapter.py:92-98`, `:257-258`); test `test_bar_start_is_the_utc_grid_with_sunday_weeks` (`test_exness_session_calendar_adapter.py:169-179`). `check_integrity` tính misaligned bằng `is_bar_aligned` với chính lịch đó (`integrity_jobs.py:76-81`).
- FACT: Hàng 0 re-run: XAU/EUR 1m 7d (cửa sổ 10-12 → 10-19, chứa cuối tuần 10-17/18) và 1h 90d (~12 cuối tuần) đều `misaligned 0` (`phase-08:273`). Spike: mọi series `all_aligned: true` (`docs/journals/2026-10-13-exness-api-spike.md:52`).
- INFER: Không có đường code nào sinh bar lệch lưới riêng cho cuối tuần. Phán quyết: **phủ**.

### P2 gap venue-empty — Phủ một phần

Phần đã phủ:
- FACT: Lưới cuối tuần của lịch khớp venue: hàng 0 re-run kiểm 7 ngày 1m chứa đúng một Fri close (10-16) và một Sun reopen (10-18) với bar backfill từ REST: XAU 1m 0 missing; EUR 1m 13 missing, tất cả venue-empty, không range nào rơi vào Chủ nhật 10-18 (`phase-08:273`, `:282`). XAU 1h 90d: 2 missing, 1 range venue-empty (holiday); EUR 1h 90d 0 (`:273`). Điều này chứng minh các hằng số phiên (`:51-85`) và `trading_minutes` (`:240-255`) đúng với dữ liệu thật của ít nhất một cuối tuần và ~12 cuối tuần ở 1h.
- FACT: Cạnh phiên được unit test: XAU Sat 12:00 closed, Sun 22:01:30 open, Fri 20:57:59 open / 20:58:00 closed (`test_exness_session_calendar_adapter.py:45-60`); EUR Fri 20:58:59 open / 20:59:00 closed, Sun 21:04:59 closed / 21:05:00 open (`:86-97`); `previous_close(Sat 12:00Z) == Fri 20:57:59Z` (`:202-206`). `_spans` phủ một tuần mỗi bên (`:168-185`) nên `previous_close` nhìn ngược qua cả cuối tuần.
- FACT: Gate của `sync_1m`: skip symbol đóng cửa quá `grace` = 60 s cho `sync_1m` (`sync_jobs.py:188-194`); test `test_a_long_closed_market_is_not_fetched_at_all`, `test_a_market_just_closed_is_still_fetched_once`, `test_an_open_market_is_always_fetched` (`tests/app_test/unit/market_data/test_sync_jobs_calendar_gate.py:65-83`). Tôi đã chạy: 2 file unit gate + `test_futures_sync_end_to_end.py` (có `test_no_progress_is_silent_while_the_market_is_shut`, Docker đang chạy) + `test_exness_live_trading_off.py`: 12 passed. Unit Exness + calendars: 146 passed.
- FACT: Hàng 1 đã chạy chính gate này qua daily break XAU (đóng 20:58:00, mở 22:00:30) và pass sau re-check 60 s (`phase-08:274`). Cạnh đóng Friday của XAU là cùng hằng số 20:57:59.
- FACT: Với 1h, giờ 21:00 (EUR) và 22:00 (XAU) Chủ nhật không được lịch kỳ vọng (phút 21:00/22:00 không giao với phiên bắt đầu 21:05:00/22:01:30, `integrity_jobs.py:47-51`); bar 1h cascade sinh ra ở đó được coi là aligned và chỉ 1m mới đếm `unexpected` (`:109-113`). Nên 1h/7d hàng 3 không thể fail vì lý do này.

Phần chưa phủ (chỉ cuối tuần thật mới cho):
- FACT: Hàng 1 đo lúc 22:33Z, tức sau khi reopen 22:00:30 đã fetch 100 bar và lấp mọi thứ. Chưa có phép đo nào nhìn vào bar cuối trước giờ đóng *mà không có lần reopen nào lấp sau đó*. Hàng 2 (Sat 03:00Z) là lần đầu. Nếu Exness chưa chốt candle 20:57 tại lúc `sync_1m` chạy 20:58:02, bar đó sẽ thiếu đến Chủ nhật.
- FACT: Cạnh đóng của EUR (20:58:59) chưa từng qua đường sync thật (EUR không có daily break).
- INFER: Đóng cửa 48 giờ không khác đóng cửa 62 phút về mặt code: fetch `count=-100` đọc ngược theo danh sách candle của venue, bỏ qua thời gian đóng; nhưng điều này chưa được quan sát.
- INFER về mức độ: nếu cạnh đóng có lỗ, quy tắc P3 cho phép repair một lần; kết quả có khả năng cao vẫn là PASS nhưng kèm một phát hiện có giá trị (grace 60 s có đủ không). Phán quyết: **phủ một phần**; cái thiếu là bằng chứng trên đường sync thật tại Fri close (hàng 2) và Sun reopen (hàng 3).

### P3 repair một lần — Phủ

- FACT: `repair_integrity` xóa misaligned, resync 5000 bar `skip_filter=True`, rồi re-check (`integrity_jobs.py:126-202`). Hàng 1 đã chứng minh nhánh "re-run sau 60 s" (`phase-08:274`). Phán quyết: **phủ**.

### P4a `sync_1m p95 < 60000` — Phủ, rủi ro thấp

- FACT: p95 hàng 0–1: 11728, 12297, 12573 ms (`:272-274`). Symbol đóng cửa bị skip trước khi gọi provider (`sync_jobs.py:192-194`).
- INFER: Cuối tuần job chỉ còn Binance + BTCUSD:EXNESS nên không thể chậm hơn vì XAU/EUR. Phán quyết: **phủ** (giá trị 7d có thể đo bất cứ lúc nào).

### P4b `CB=0` qua WS idle — Cần cuối tuần thật

- FACT: Logic breaker: `_failures` reset về 0 ở mỗi lần connect thành công (`exness_stream.py:81-82`), tăng 1 sau mỗi lần ngắt (`:112-113`), mở breaker ở 10 lần liên tiếp và ngủ 300 s (`:114-118`). Test `test_ten_consecutive_failures_open_the_circuit_breaker` (`test_exness_stream.py:111-120`). Không có stale watchdog cho ticks (`exness_quote_adapter.py:83-84`); không module nào trong engine/app đọc `last_tick_at` (grep: chỉ port `:27`, router `:37-43`, tradingview). Reconnect dùng `ws_url` → `access_point()` có re-resolve sau TRANSPORT/421 (`exness_client.py:276-286`, `:387-388`); test `test_an_access_point_error_is_retried_with_backoff` (`test_exness_stream.py:164-179`).
- FACT: Code WS Exness lên prod lần đầu 2026-10-19 (`fb4f2de`, master `7c3ca77`; `docs/journals/2026-10-19-exness-market-data-in-prod.md`). Hôm nay thứ Sáu 2026-10-23: prod **chưa từng** trải qua cuối tuần nào với WS này. Spike chỉ thu ticks 600 s vào thứ Ba (`spike:12`).
- FACT: `RC` đã không bằng 0 ngay trong ngày thường: 8, 11, 4 reconnect mỗi cửa sổ 12–19 giờ (`phase-08:272-274`); nguyên nhân không được ghi, tôi không xác minh được (không ssh).
- INFER: Breaker chỉ mở khi 10 lần connect thất bại liên tiếp; tổng backoff trước lần thứ 10 là 1+2+4+8+16+30+30+30+30 = 151 s, tức một sự cố kết nối Exness/mạng kéo dài ~2,5–3 phút là đủ ghi `CB=1` và fail hàng. Cửa sổ 2–3 ngày phơi nhiễm hơn 1 ngày. Điều quan trọng hơn: cách Exness đối xử với socket idle 48 giờ (giữ, đóng, có trả pong cho `ping_interval=20`/`ping_timeout=10` không, có áp strike `threshold 10, refill 1/600 s` lên reconnect không — `spike:38`) không có trong code, fixture hay bất kỳ bằng chứng nào. Phán quyết: **cần cuối tuần thật**.

### P4c `running 2` — Phủ, nhưng nên đo lại một lần

- FACT: `actual_state` = `strategy.is_running` (`strategy_reconcile_app_service.py:235-240`); `_is_running` chỉ về False ở init và `stop` (`strategy_service_interface.py:38,48`); không có đường "stale/idle/stuck" nào trong `engine/live` (grep rỗng). Trạng thái `closed`/`stuck` của data lag chỉ được log (`sync_jobs.py:758`), không ai tiêu thụ.
- FACT: Phase 11 go-live bị hủy tại 11.5, "Nothing deleted or created" (`go-live/plan.md:28`), nên hai subscription paper không bị xóa.
- INFER: 48 giờ không có bar không làm strategy rời `running`. Nhưng prod đã redeploy nhiều lần 10-21/22 (xem mục rủi ro) và tôi không xác minh được trạng thái hiện tại. Phán quyết: **phủ** về mặt code; một lần C2 với `CHECKS=''` bất kỳ lúc nào là đủ để xác nhận, không cần cuối tuần.

### P5 cột ghi nhận — Không có thay thế

- FACT: Không có bằng chứng nào về `RC`/`RL` trên WS idle. Đây là thông tin, không phải pass/fail, nhưng nó là thứ hàng 2 được thiết kế để thu.

### T8.8 và cam kết của plan — Không thể PASS nếu không chạy

- FACT: T8.8 yêu cầu "a `PASS` row for each of rows 0–3" (`:291`); `plan.md:54` và Goal `:161` nêu rõ "weekend close and reopen". Đóng không chạy nghĩa là phải sửa văn bản plan (waive), giống cách đã làm với DST (`:26`, `:296-297`), chứ không phải điền PASS.

## 4. Khuyến nghị và rủi ro còn lại

**Khuyến nghị:** chờ và chạy hai hàng như lịch. Lý do: (a) thông tin duy nhất còn thiếu — hành vi WS Exness khi idle 48 giờ và cạnh Fri close trên đường sync thật — không thể suy ra từ code/test; (b) chi phí là ~10 phút × 2, lần đầu cách đây ~26 giờ; (c) không có gì bị chặn: `go-live/plan.md:78` "No phase waits on it", quyết định 19:35 (`:102`) nói E2 "gates nothing".

Thách thức tiền đề "code không mới": với tiêu chí đang xét thì code *là* mới. FACT: WS/calendar Exness chạy prod từ 2026-10-19; từ hàng 1 (10-21 05:35+07) master đã nhận thêm nhiều deploy ngày 10-21/22, trong đó `0a5eb65a` (re-resolve access point trong `exness_client.py`), `072c24f3` (unexpected 1m trên integrity), `2be18e00` (cascade verification), `78d8c205`, `b30ea30c`/`c13fab50` (tunnel). Image prod hiện tại chưa qua một hàng E2 nào, càng chưa qua cuối tuần.

**Về Phase 12 go-live làm lưới an toàn:** FACT: Phase 12 "Pending", phụ thuộc Phase 11 đã bị hủy 2026-10-22 vì chưa có strategy có lãi (`go-live/plan.md:27-28`, `:104`), nên hiện không có ngày chạy. Khi chạy, Task 12.2 đếm `circuit_breaker_open` và `reconnecting` từ hàng trước (hàng thứ Hai phủ cuối tuần) nhưng chỉ lấy `unexpected_count` 1m/1d, không có kiểm tra missing/venue-empty như C3 (`phase-12:64-67`, `:96-97`). INFER: Phase 12 thay được P4b nhưng không thay P2, và chỉ khi nó thực sự chạy.

**Nếu user vẫn quyết định đóng ngay** (quyền của user; tôi ghi là trade-off, không phải blocker):
1. Ghi hàng 2 và 3 là `waived 2026-10-23 (user decision)` với lý do, không phải PASS; sửa T8.8 và `plan.md:54` cho khớp (giống cách chuyển DST).
2. Giữ hai subscription paper chạy; thêm một dòng kiểm tra thứ Hai 2026-10-26 ~10 phút: C1 (`CB`, `RC` từ `StartedAt`) + C3 `XAUUSD:EXNESS/1m/3 EURUSD:EXNESS/1m/3` + C2 `CHECKS=''`. Đây chính là hàng 3 rút gọn; nếu chấp nhận làm việc này thì chỉ còn tiết kiệm được hàng 2.
3. Nếu bỏ cả hàng thứ Hai: ghi rõ rủi ro dưới đây vào Risks của phase.

**Rủi ro còn lại nếu đóng ngay (INFER):**
- WS idle cuối tuần gây reconnect dồn dập hoặc breaker mở mà không ai thấy, cho đến cuối tuần đầu tiên có tiền thật; Phase 12 chỉ bắt được khi đã có strategy có lãi. Hậu quả khi đó: hàng quan sát fail và phải xử lý lúc đang có vị thế.
- Lỗ bar cuối trước Fri close (grace 60 s) ở XAU/EUR không được phát hiện; tác động nhỏ (1–2 bar, repair lấp được) nhưng là lỗ hổng dữ liệu lặp lại hằng tuần.
- Plan tự mâu thuẫn: cam kết "across a weekend" ở `plan.md:54` không có bằng chứng, trong khi mọi mục khác của plan đều có.

## Checklist (nếu chờ)

1. Sat 2026-10-24 10:00 Bangkok: chạy đúng hàng 2 (`:265`); bắt đầu C3 ở giây ≥ 20 (`:188`).
2. Nếu C3 `VENUE_HAS` ở phút 20:57 (XAU) hoặc 20:58 (EUR) thứ Sáu: áp quy tắc P3 (repair một lần) và ghi lại — đây là phát hiện về grace, không phải lỗi lịch.
3. Mon 2026-10-26 10:00 Bangkok: hàng 3 (`:266`); với 1h/7d, mọi bar 1h ở Sun 21:00/22:00 là aligned-không-kỳ-vọng và không làm fail.
4. T8.8: dòng tổng kết + hỏi user giữ/dừng subscription.

## Giả định

- (cao) Lịch chạy hàng 2/3 không bị deploy mới làm mất log: mỗi hàng ghi `S`/`F`, deploy chỉ rút ngắn cửa sổ (`:137`). Nếu có deploy giữa cuối tuần thì `CB` chỉ được chứng minh trong phần cửa sổ còn lại.
- (trung bình) Hai subscription vẫn `running` sau các deploy 10-21/22; tôi không xác minh được vì không ssh. Nếu C2 hôm nay in `running < 2` thì hàng 2/3 cần T8.6 chạy lại trước.
- (trung bình) Exness không thay đổi `trade_sessions` trước 2026-11-01; C5 không nằm trong hàng 2/3 nên không ảnh hưởng verdict.
