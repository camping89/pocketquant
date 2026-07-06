# Phase 02 — Frontend: name UI

Phụ thuộc phase-01 (shape API + PATCH endpoint).

## Files sửa

### 1. `web/src/api/backtest-api.ts`
- `RunBacktestBody`: thêm `name?: string`.
- `BacktestRunResult`: thêm `name?: string | null`.
- `BacktestRunDoc`: thêm `name?: string | null`.
- `fetchBacktestRun` return map: thêm `name: doc.name`.
- `BacktestRunRow`: thêm `name: string | null`.
- Thêm `setBacktestName(runId, name)` → `apiPatch('/api/v1/backtest/{runId}/name', { name })` (mirror `setVerdict`).

### 2. `web/src/hooks/use-backtest-run.ts`
Thêm `useSetBacktestName(runId)` mirror `useSetVerdict` (optimistic update `['backtest-run', runId]`; `onSettled` invalidate `['backtest-run', runId]` **và** `['backtest-runs']` để list hiện name mới).

### 3. `web/src/components/backtest/backtest-form.tsx`
- Thêm state `name`, input "Name (optional)" ở đầu form (dùng `labelStyle`/`inputStyle` sẵn có).
- `onSubmit` body: `name: name.trim() || undefined` (không gửi khi rỗng).

### 4. `web/src/components/backtest/run-list-item.tsx`
Line1: title = `row.name || row.strategy_code` (bold). Nếu có `row.name`, hiện `strategy_code` như secondary; nếu không, giữ nguyên hành vi hiện tại.

### 5. `web/src/components/backtest/run-header.tsx`
- Thêm prop `name?: string | null` + `runId` đã có.
- Title = `name || strategyCode` (fallback). Thêm inline edit: nút "Edit"/"Add name" → input + Save/Cancel, dùng `useSetBacktestName` (mirror VerdictPanel logic: giữ text khi save fail, reset khi đổi runId).
- Giữ `strategyCode`/`pair`/runid như cũ.

### 6. `web/src/components/backtest/backtest-detail-pane.tsx`
Truyền `name={run.name}` vào `RunHeader`.

## Validation
- `cd web && npm run build` (tsc + vite) — không lỗi type/build.
- Smoke thủ công: tạo run có/không name; sửa name; xem list + header.

## Risks
Optimistic name edit chỉ update cache `['backtest-run', runId]`; list rows refresh qua invalidate `['backtest-runs']`. Không đổi contract khác.
