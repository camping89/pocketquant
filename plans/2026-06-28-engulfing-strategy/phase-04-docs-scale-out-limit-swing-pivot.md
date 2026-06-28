---
phase: 4
title: "Docs (scale-out limit + swing pivot)"
status: completed
priority: P3
dependencies: []
---

# Phase 4: Docs (scale-out limit + swing pivot)

## Overview

Hai tài liệu trong `docs/`: (1) vì sao engine KHÔNG hỗ trợ scale-out/multi-TP/partial close (giải thích 4 tầng giới hạn, AS-IS); (2) education về swing pivot / swing high-low dùng làm key-level cho TP.

## Requirements

- Functional: 2 doc markdown, prose tiếng Việt, giữ thuật ngữ tiếng Anh (theo CLAUDE.md doc policy).
- Non-functional: AS-IS (mô tả hiện trạng, không changelog/banner); bullets/tables + 1 ASCII/Mermaid khi có 2+ phần tương tác.
- Độc lập: không chặn và không bị chặn bởi phase code; có thể làm song song.

## Architecture

**Doc 1 — Scale-out limitation.** Mô tả 4 tầng giới hạn bằng **tên symbol** (KHÔNG line number — red-team Finding 1: line refs cũ sai `value_objects.py:17`→thực :19, `paper_broker.py:636`→thực :642, `:454`→thực :426/:460; và sẽ dịch sau khi 260628-1514 land. Doc policy: filenames + symbols explain WHY):

| Tầng | Giới hạn | Symbol |
|---|---|---|
| `Signal` | một `take_profit_price` (float) | `Signal.take_profit_price` (`value_objects.py`) |
| `IStrategy` | hook trả MỘT Signal/bar, không list | `IStrategy.on_bar_completed` (`interfaces.py`) |
| `PaperBroker` | một `tp_price`/position; đóng TOÀN BỘ qty | `PaperBroker._fire_synthetic_exit`, `_check_sl_tp` |
| Position | key `f"{subscription_id}:{symbol}"` → một position; lệnh 2 merge | `PaperBroker._execute_fill` (position_key) |

→ Kết luận: scale-out cần thay đổi cross-cutting (Signal, IStrategy, broker, lot-tracker, position-box render). Ghi là known limitation + hướng nếu làm sau.

**Doc 2 — Swing pivot education.** Nội dung:
- Swing high/low là gì (đỉnh/đáy cục bộ); phân biệt với max/min cửa sổ thô.
- Cách tính: max(highs[-N:]) / min(lows[-N:]) — cách `EngulfingStrategy` + `hitnrun2` dùng làm key-level proxy.
- Vì sao dùng làm TP key-level (giá hay phản ứng tại swing trước; TP đặt tại đó hợp lý hơn số tròn tùy ý).
- 2-3 ví dụ ASCII minh họa (1 case key-level xa hơn RR 1:1 → TP nhảy lên key; 1 case key-level gần → rơi về RR 1:1).
- Lưu ý: đây là proxy đơn giản, KHÔNG phải swing-pivot detection thật (đã loại ở brainstorm) — ghi rõ để không gây hiểu nhầm.

**Doc 2 — thêm 2 caveat (red-team Finding 5+6, Assumption Destroyer):**
- **Chart ≠ strategy signal set:** chart "show all patterns" vẽ MỌI engulfing; strategy chỉ entry SUBSET (gated bởi warmup `key_level_lookback_bars` + position-cap 1 lệnh). Pattern lúc warmup hoặc lúc đang có vị thế → có marker trên chart nhưng KHÔNG có trade. Đây là chủ ý, không phải bug. Ghi rõ để tránh "strategy bỏ lỡ entry hiển nhiên".
- **Strong-threshold chart (0.30) là visual aid cố định:** chart tô strong/weak ở ngưỡng FE cố định 0.30; strategy đọc `max_rejection_wick_pct` từ config (tune-được). Nếu backtest tune ngưỡng khác → màu chart KHÔNG phản ánh config đó. Coloring là aid trực quan, không phải dự đoán "sẽ/không entry" cho 1 backtest cụ thể.

## Related Code Files

- Create: `docs/engine-scale-out-limitation.md` (hoặc thêm section vào `docs/system-architecture.md` nếu hợp cấu trúc — quyết định lúc viết, ưu tiên file riêng cho dễ tìm).
- Create: `docs/swing-pivot-key-level.md` — education.
- Reference: `docs/README.md` — thêm link nếu có index docs.
- Verify trước khi viết: đọc lại `value_objects.py`, `interfaces.py`, `paper_broker.py` để số dòng/contract khớp thực tế lúc viết (sau khi 260628-1514 rename hook có thể đổi tên trong interfaces).

## Implementation Steps

1. Đọc lại 3 file source (value_objects, interfaces, paper_broker) xác nhận giới hạn còn đúng (đặc biệt sau rename hook của 260628-1514).
2. Viết Doc 1: bảng 4 tầng + Mermaid flow "vì sao 1 Signal không tạo được 2 TP" + kết luận known-limitation.
3. Viết Doc 2: định nghĩa + công thức + vì sao + ≥2 ví dụ ASCII.
4. Cập nhật `docs/README.md` index nếu tồn tại.
5. Đọc lại đảm bảo AS-IS (không banner/changelog), prose tiếng Việt + thuật ngữ tiếng Anh.

## Success Criteria

- [ ] `docs/` có 2 file mới; prose tiếng Việt, thuật ngữ tiếng Anh giữ nguyên.
- [ ] Doc 1 nêu đủ 4 tầng giới hạn với file reference đúng.
- [ ] Doc 2 có định nghĩa + công thức + ≥2 ví dụ + caveat "proxy, không phải pivot detection".
- [ ] Không banner/changelog/"Last Updated"; AS-IS.
- [ ] Link từ docs index (nếu có).

## Risk Assessment

- **Risk:** file:line stale sau rename hook 260628-1514. Mitigation: step 1 đọc lại trước khi ghi số dòng; ưu tiên mô tả invariant hơn số dòng cứng.
- **Risk:** doc 2 gây hiểu nhầm là có swing-pivot detection thật. Mitigation: caveat explicit.
- **Risk:** đặt sai chỗ (system-architecture vs file riêng). Mitigation: theo cấu trúc docs/ hiện có; file riêng nếu nội dung đủ lớn.
