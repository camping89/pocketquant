---
phase: 3
title: "Frontend Subscription Panel"
status: completed
priority: P1
effort: "1d"
dependencies: [2]
---

# Phase 3: Frontend Subscription Panel

## Overview
Thay flow "select strategy → POST /backtest/run" hiện tại bằng panel quản lý subscriptions + Run All + read-from-cache. Chart logic giữ nguyên — chỉ đổi data source.

## Requirements

**Functional**
- Strategy dropdown vẫn giữ; thêm subscription list bên dưới
- Add Symbol form (symbol, exchange, interval)
- Run All Backtests button — disabled khi không có subscription
- Click subscription row → load cached backtest → render chart
- Polling 2s khi `status='running'` cho subs đang chạy
- Status badges: none / running / done / failed (+ error tooltip)
- Delete subscription per row (×) + Delete strategy (cascade)

**Non-functional**
- TanStack Query keys hợp lý, invalidate đúng chỗ
- Polling chỉ enable khi có sub `running` (refetchInterval conditional)
- File component < 200 LOC

## Architecture

### API client extensions

`packages/pocketquant-web/src/api/strategy-api.ts` (extend hoặc tạo mới):
```ts
export type Subscription = {
  id: string;
  strategy_id: string;
  symbol: string;
  exchange: string;
  interval: string;
  created_at: string;
  backtest: { status: 'running'|'done'|'failed'; last_run_at: string; error_msg?: string } | null;
};

export const addSymbol = (strategyId, body) => api.post(`/strategies/${strategyId}/symbols`, body);
export const listSymbols = (strategyId) => api.get<Subscription[]>(`/strategies/${strategyId}/symbols`);
export const removeSymbol = (strategyId, subId) => api.delete(`/strategies/${strategyId}/symbols/${subId}`);
export const runAllBacktests = (strategyId) => api.post<{job_ids: string[]}>(`/strategies/${strategyId}/backtest/run-all`);
export const getSubscriptionBacktest = (strategyId, subId) =>
  api.get<BacktestResponse>(`/strategies/${strategyId}/symbols/${subId}/backtest`);
export const deleteStrategy = (strategyId) => api.delete(`/strategies/${strategyId}`);
```

### Hooks

`packages/pocketquant-web/src/hooks/use-subscriptions.ts`:
```ts
export const useSubscriptions = (strategyId) =>
  useQuery({
    queryKey: ['subscriptions', strategyId],
    queryFn: () => listSymbols(strategyId),
    enabled: !!strategyId,
    refetchInterval: (data) =>
      data?.some(s => s.backtest?.status === 'running') ? 2000 : false,
  });

export const useSubscriptionBacktest = (strategyId, subId) =>
  useQuery({
    queryKey: ['subscription-backtest', strategyId, subId],
    queryFn: () => getSubscriptionBacktest(strategyId, subId),
    enabled: !!strategyId && !!subId,
    retry: (count, err) => err.status !== 404,
  });

export const useRunAll = (strategyId) =>
  useMutation({
    mutationFn: () => runAllBacktests(strategyId),
    onSuccess: () => qc.invalidateQueries({queryKey: ['subscriptions', strategyId]}),
  });
// + useAddSymbol, useRemoveSymbol, useDeleteStrategy với invalidation tương tự
```

### Components

`packages/pocketquant-web/src/components/strategy/subscription-panel.tsx`:
```
┌─────────────────────────────────────────────────┐
│ Strategy: [macd-cross ▾]  [+ Symbol] [Run All] [🗑] │
├─────────────────────────────────────────────────┤
│ ● BTC-USDT • okx • 1h • 5m ago    [done]    [×] │
│ ● ETH-USDT • okx • 1h • 1h ago    [done]    [×] │
│ ○ SOL-USDT • okx • 4h • —         [none]    [×] │
│ ⟳ XRP-USDT • okx • 1h • running   [running] [×] │
└─────────────────────────────────────────────────┘
```

- Selected row → highlighted, drives `selectedSubId` state lifted to parent
- `onSelectSub(subId)` → parent fetches `useSubscriptionBacktest` → passes positions to `TradingChart`

`packages/pocketquant-web/src/components/strategy/add-symbol-dialog.tsx` (modal):
- Form: symbol input, exchange select, interval select (Interval enum)
- Submit → `useAddSymbol().mutate()` → on success close + invalidate

### Wire-up trong page

`packages/pocketquant-web/src/pages/...` (tìm page chứa `<TradingChart>` + `<StrategySelector>`):
- Replace `useBacktest()` mutation flow bằng `useSubscriptionBacktest(strategyId, selectedSubId)`
- `<StrategySelector>` giữ nguyên prop `onChange(strategyId)` — set state, reset `selectedSubId`
- Render `<SubscriptionPanel strategyId={strategyId} onSelect={setSelectedSubId} />`
- Khi `selectedSubId` đổi → query auto-fetch → chart render

### Status badge component

`packages/pocketquant-web/src/components/strategy/backtest-status-badge.tsx`:
- Props: `status`, `lastRunAt`, `errorMsg`
- Map status → color (gray/blue/green/red) + icon
- Tooltip hiển thị `last_run_at` + `error_msg` nếu failed

## Related Code Files

**Create**
- `packages/pocketquant-web/src/components/strategy/subscription-panel.tsx`
- `packages/pocketquant-web/src/components/strategy/add-symbol-dialog.tsx`
- `packages/pocketquant-web/src/components/strategy/backtest-status-badge.tsx`
- `packages/pocketquant-web/src/hooks/use-subscriptions.ts`

**Modify**
- `packages/pocketquant-web/src/api/strategy-api.ts` (add 6 functions; nếu chưa có tạo file mới)
- `packages/pocketquant-web/src/components/controls/strategy-selector.tsx` (nếu cần hook delete)
- Page wire-up: tìm via `grep "useBacktest"` rồi swap
- Có thể delete `packages/pocketquant-web/src/hooks/use-backtest.ts` (deprecated) — confirm khi swap xong

**Read for context**
- `packages/pocketquant-web/src/components/chart/trading-chart.tsx:33-265` (đọc, không sửa)
- `packages/pocketquant-web/src/hooks/use-backtest.ts` (current pattern)

## Implementation Steps

1. **API client**: thêm 6 functions vào `strategy-api.ts` + types
2. **Hooks**: `use-subscriptions.ts` với 6 hooks, polling conditional
3. **Status badge** component (small, ~40 LOC)
4. **Add symbol dialog** (modal với form)
5. **Subscription panel**: list + actions, lifted selection state
6. **Wire-up page**: replace `useBacktest()` với `useSubscriptionBacktest()`. Test golden path bằng dev server.
7. **Browser test**: Add 2 symbols → Run All → polling → status flips → click row → chart paints; Delete sub → row gone; Delete strategy → cascade visible; Concurrent Run All → no duplicate jobs visible.
8. Cleanup: remove `use-backtest.ts` nếu không còn caller.

## Success Criteria

- [x] Chọn strategy → subscription panel render với 0 hoặc N rows
- [x] Add symbol → row appears với "none" badge
- [x] Run All → tất cả rows flip "none/done" → "running" → polling cập nhật mỗi 2s → "done"
- [x] Click row done → chart render positions trong < 200ms
- [x] Delete row → row gone, chart clear nếu đang chọn
- [x] Delete strategy → toàn bộ subs + chart clear
- [x] Status='failed' → badge đỏ, tooltip hiển thị error_msg
- [x] Polling tự stop khi không còn sub `running`

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Polling chạy mãi nếu status stuck 'running' | P4 stale-recovery xử lý server-side |
| Chart not clearing khi switch sub | `selectedSubId` state reset trong `onChange` strategy |
| Add symbol form duplicate (dù backend 409) | Catch error, toast "subscription đã tồn tại" |
| Stale TanStack cache khi delete | Invalidate `['subscriptions', strategyId]` + `['subscription-backtest', ...]` trên mỗi mutation |
