# Brainstorm — Cost inversion (taker→maker) & alpha validation cho engulfing+structure

> Timestamp: 2026-07-12 (Asia/Saigon). Problem-first inversion. Câu tiếng Việt, term tiếng Anh giữ nguyên.
> Modes: (mặc định, không `--html`/`--wiki`).
> Nối tiếp: [research vòng 2](./from-research-to-user-engulfing-structure-level-taker-profit-report.md) + [research vòng 1](../260706-2238-engulfing-1m-strategy-research/master-report.md).
>
> **Quyết định người dùng (interview):** Frame A (cost là nút thắt) · test cả taker + maker so sánh · deliverable = report + validation plan (chưa chạy backtest vòng này).

---

## TL;DR

2 vòng research chứng minh (STRONG evidence) engulfing ~0 directional alpha; chỉ trend-beta high-TF net dương taker nhưng CI chứa 0 + phụ thuộc đuôi. Problem-first inversion phát hiện **một mâu thuẫn nội tại chưa ai chỉ ra**:

> **Strategy "vào lệnh tại structure level" bản chất là đặt LIMIT order nghỉ tại S/R = MAKER. Nhưng cả 3 service hiện tại + toàn bộ research đều entry market-at-close = TAKER. Ràng buộc "sống ở taker" là TỰ GÂY RA, sai execution model cho chính ý tưởng structure.**

Đòn bẩy lớn nhất, rẻ nhất, chưa thử: **đổi taker→maker qua limit-at-level** (round-trip 10bps→~4bps, có thể rebate âm). Mọi thứ khác (ensemble, vol filter, trailing) chỉ **giảm variance ước lượng**, không **tạo edge**. Report này định khung validation plan để test dứt điểm — kèm kill condition định trước.

---

## Vấn đề: Solution-jumping đã xảy ra

Người dùng hỏi "engulfing+structure có hướng nào chưa thử để sống ở taker" — mang sẵn giải pháp (engulfing) + ràng buộc (taker). Problem-first: giải pháp là confession của vấn đề chưa nói ra.

**Vấn đề thật KHÔNG phải** "làm engulfing có lời". **Mà là:** *tồn tại một edge giao dịch được, robust, generalize, sống sau cost — trên hạ tầng pocketquant?* Engulfing chỉ là candidate signal đầu tiên bám vào (vì đã đầu tư hạ tầng: 3 service + detector + chart toggle + golden fixture).

---

## Problem-first inversion (8 mục)

### 1. Solution-jumping diagnosis
- **Signal khiến engulfing feel necessary:** sunk cost hạ tầng engulfing đã xây; là pattern quen thuộc, dễ hình dung.
- **Pain ẩn dưới:** muốn một strategy có lời thật, engulfing là thứ đầu tiên thử → gắn bó cảm tính.

### 2. Underlying problem
Có edge tradeable/robust/generalize/sống-sau-cost trên pocketquant không? Engulfing là *một* candidate, không phải mục tiêu tự thân.

### 3. Assumption challenges

| Assumption | Risk nếu sai | Validation test |
|---|---|---|
| **Entry = taker (market)** | ⚠️ CAO NHẤT — structure strategy đặt lệnh TẠI level ⇒ limit ⇒ maker. Market-at-close = sai model. | **Test A**: limit-at-level (maker/rebate) vs market-at-close (taker). Cost RT có thể −60% |
| Engulfing mang directional info | Đã sai (random-same-gate ≈ engulfing) | Đã test 2 vòng — DEAD |
| Edge phải per-trade dương | Right-skew ⇒ median âm bình thường; edge ở tổng portfolio | **Test B**: pool đa symbol → CI co, equity mượt hơn |
| 1 symbol đủ kết luận | n_out 48–67 quá nhỏ; CI chứa 0 có thể chỉ là small-sample | **Test B**: BTC+ETH+SOL (đang backfill) |
| Structure level = S/R swing tĩnh | Có thể level động (VWAP, session H/L, round number) mạnh hơn | Ngoài scope vòng này; ghi làm lead |

### 4. Problem statement
- **Ai/context:** retail quant, hạ tầng pocketquant, DB 3 symbol (BTC có; ETH/SOL đang backfill).
- **Struggle:** mọi config engulfing net âm hoặc net dương không phân biệt được zero sau taker.
- **Cause:** (a) cost wall (1m noise ~3.5bps ≪ taker 10bps); (b) engulfing không directional alpha; (c) **execution model sai** — market thay vì limit-at-level.
- **Consequence:** 2 vòng chưa ra gì tradeable; nguy cơ vòng 3 lặp lại nếu không đổi khung.
- **Success quan sát được:** net dương sau cost · CI **không** chứa 0 · dương ≥3 symbol chưa tune · không sập khi bỏ top-3 winners · vượt random-same-gate control.

### 5. Ba framing thay thế
- **Frame A [ĐÃ CHỌN] — Kẻ thù là COST.** Structure trading ⇒ limit nghỉ tại level ⇒ maker. Ràng buộc taker tự gây ra. Đổi execution → economics đổi. *Đòn bẩy lớn nhất chưa thử.*
- **Frame B — Engulfing là dead end.** Bỏ engulfing directional; dùng như feature phụ hoặc bỏ hẳn. Chấp nhận kết quả âm 2 vòng.
- **Frame C — Làm beta tử tế.** Cái sống được = trend-follow 1d = beta. Xây thẳng trend-following đa symbol (vol-target, drawdown control), engulfing chỉ là entry timer.

### 6. Evidence status: **STRONG**
2 vòng độc lập · walk-forward · control counter + random đối xứng · bootstrap. "Engulfing ~0 directional alpha" hội tụ định tính + định lượng. (Hiếm khi đạt STRONG — nghĩa là KHÔNG nên cày thêm biến thể directional engulfing.)

### 7. Validation plan → xem mục riêng bên dưới.

### 8. Draft stakeholder message (chính bạn)
> "2 vòng chứng minh engulfing không directional alpha (STRONG). Trước khi bỏ vốn vòng 3, test MỘT giả định chưa thử: structure-level strategy bản chất là limit-at-level (maker), không market (taker) — research cũ tự trói vào taker. Nếu maker execution + đa symbol vẫn không tạo edge robust, chốt kết luận và pivot sang Frame C (beta tử tế) hoặc dừng."

---

## Validation plan chi tiết (3 test, xếp theo đòn bẩy)

### Test A — Maker execution model (Frame A, quyết định nhất)

**Cơ chế:** LONG đặt limit buy tại support level (thay vì market tại close bar tín hiệu). Fill khi `low ≤ level`. SHORT mirror tại resistance.

**Mô phỏng fill HONEST** (điểm dễ tự lừa nhất — phải làm đúng):

| Trường hợp | Xử lý | Vì sao |
|---|---|---|
| Fill | Khớp tại giá `level`, **0 slippage**, cost maker 4bps (hoặc −2 rebate) | Limit không chịu slippage, thêm thanh khoản |
| Adverse selection | 1 bar xuyên qua cả level lẫn SL → fill rồi stop ngay trong bar | Nếu bỏ qua = ăn gian; limit chỉ khớp đúng lúc giá sắp đi ngược |
| Non-fill | Giá không chạm level trong `arm_window` bar → hủy order, KHÔNG trade | Khác hẳn market-at-close; đây là lý do fill probability phải mô phỏng |

**So sánh fair:** cùng 3 variant (A/B/C từ report vòng 2), chạy song song:
- Taker: entry market tại close bar tín hiệu, RT 10bps.
- Maker: entry limit tại level, fill khi touch, RT 4bps / rebate −2.

Entry price khác (level vs close) → RR khác → tập lệnh khác (chỉ lệnh touch mới fill). Báo cáo: net@taker vs net@maker vs net@rebate, và **fill rate** (bao nhiêu % signal thực sự khớp).

**Kill test A:** nếu net@maker VẪN phụ thuộc top-3 winner + CI chứa 0 → cost không phải nút thắt → Frame A chết → chuyển Frame B/C.

### Test B — Multi-symbol ensemble (co CI)

- **Pool** trades BTC+ETH+SOL → bootstrap CI trên tập gộp (n_out ~3×). Edge thật → CI co, tách khỏi 0. Small-sample → vẫn chứa 0 nhưng hẹp hơn. No-edge → chứa 0 rộng.
- **Per-symbol OOS net cùng dấu** = generalize. Một symbol dương, hai âm = BTC-specific artifact.
- **Tail-independence:** winners phân tán qua symbol/thời điểm, không dồn cục.

**Hạ tầng sẵn sàng:** `pq_prefetch_multi.py` + `pq_multi_symbol_validate.py` + `pq_structure_lib.use_cache()` đã viết, chờ ETH/SOL backfill xong (đang chạy nền).

### Test C — Kill condition (định trước)

"Tách được alpha" = **TẤT CẢ**:
1. OOS net > random-same-gate control (cùng trend+level gate, entry ngẫu nhiên).
2. Không sập khi bỏ top-3 winners.
3. Bootstrap 95% CI không chứa 0.
4. Cùng dấu trên ≥3 symbol.

Nếu maker + đa symbol không đạt cả 4 → **kết luận cuối: engulfing không tradeable ở retail cost. Dừng directional engulfing. Pivot Frame C hoặc đóng sổ.**

---

## Brutal honesty

- **KHÔNG cày thêm biến thể param** — region đã stable (report vòng 2), thêm sweep = curve-fit đuôi. Evidence STRONG rồi.
- **Đòn bẩy thật = execution model, không phải signal.** Ensemble/vol-filter/trailing chỉ giảm variance ước lượng, không tạo edge.
- **Dự đoán thẳng:** khả năng cao kết luận cuối vẫn là *engulfing không alpha; cái sống = trend-beta + lợi thế maker*. Nhưng Test A đủ rẻ + đủ quyết định để chạy trước khi đóng sổ. Nếu maker cứu được net (giảm cost 60%), có thể một survivor mỏng thành tradeable — đáng biết.
- **Rủi ro Test A tự lừa:** fill probability + adverse selection là chỗ dễ ăn gian nhất. Nếu mô phỏng ẩu (fill mọi touch, bỏ qua bar xuyên thẳng) → net@maker đẹp giả tạo. Phải model non-fill + adverse.

---

## Success metrics & next steps

**Success (vòng 3):** trả lời dứt khoát 1 trong 2 — (a) maker execution + đa symbol tạo edge đạt cả 4 kill-criteria → có candidate tradeable; hoặc (b) không đạt → kết luận cuối, pivot.

**Next steps (chờ user quyết, KHÔNG tự chạy):**
1. ETH/SOL backfill xong → `pq_prefetch_multi.py` → Test B (đa symbol, config hiện tại).
2. Viết maker execution sim vào `pq_structure_lib` (limit-at-level + fill model) → Test A.
3. Chạy A×B (maker × 3 symbol) → đánh giá 4 kill-criteria → kết luận.

**Handoff:** nếu chọn build, đây là research → `/ck:plan` sau khi Test A/B cho tín hiệu xanh. Nếu Test C kill → pivot Frame C (trend-following đa symbol tử tế) là brainstorm riêng.

---

## Câu hỏi chưa giải quyết

- Fill probability model: `arm_window` bao nhiêu bar trước khi hủy limit? Real fill rate của limit tại swing level trên 1m BTC là bao nhiêu (chưa có dữ liệu order-book)?
- Maker rebate: account thật có đạt VIP tier rebate âm không? Quyết định net@maker vs net@rebate cái nào là con số thật.
- Funding: giữ lệnh fixed-RR dài (median vài chục giờ) → funding perp đáng kể, chưa trừ. Ảnh hưởng maker lẫn taker.
- Structure level tĩnh (swing S/R) vs động (VWAP/session H/L/round number): level nào cho fill rate + edge tốt hơn? (lead, ngoài scope vòng 3).
- Frame C nếu kích hoạt: trend-following đa symbol cần vol-targeting + drawdown control — thiết kế khác hẳn, cần brainstorm riêng.
