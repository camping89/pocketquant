# Phase 06 — Frontend updates

**Priority:** Restores UI after route split. Blocks verification.
**Status:** ⏳ pending, blocked by 5

## Scope

Update FE types, API client, hooks, and components to match new field names + URL shapes.

## Type updates

`src/api/strategy-api.ts`:
```ts
interface Subscription {
  id: string
  strategy_code: string        // was strategy_id
  symbol: string
  interval: string
  created_at: string
  is_running: boolean          // NEW — see Open Item below
  backtest: SubscriptionBacktestStatus | null
}
```

`src/api/backtest-api.ts`:
- `SubscriptionBacktest.strategy_id` → `strategy_code`

## API client updates

`src/api/strategy-api.ts`:
- `listSymbols(strategyId)` → `listSubscriptions(strategyCode?)` → `GET /api/v1/subscriptions/?strategy_code=...`
- `addSymbol(strategyCode, body)` → `POST /api/v1/strategies/{strategyCode}/subscriptions`
- `removeSymbol(strategyCode, subId)` → `removeSubscription(subId)` → `DELETE /api/v1/subscriptions/{subId}`
- `runAllBacktests(strategyCode)` → `POST /api/v1/strategies/{strategyCode}/run-all-backtests`
- `getSubscriptionBacktest(subId)` → `GET /api/v1/subscriptions/{subId}/backtest`
- `deleteStrategy(strategyCode)` → `DELETE /api/v1/strategies/{strategyCode}`

## Hook updates

`src/hooks/use-strategy-mutations.ts`:
- `useStartStrategy` → `useStartSubscription`; URL → `/api/v1/subscriptions/{subId}/start`
- `useStopStrategy` → `useStopSubscription`; URL → `/api/v1/subscriptions/{subId}/stop`
- `useDeleteSubscription(strategyCode)` → `useDeleteSubscription()` (no template needed)
- `useDeleteStrategyById(strategyCode)` → unchanged semantically; arg name `strategyCode`
- `useCreateSubscription(strategyCode)` — unchanged shape, just rename param

`src/hooks/use-subscriptions.ts`:
- `useSubscriptions(strategyCode | null)` — rename param

QueryKey scheme — pick ONE convention and use everywhere:
- `['subscriptions']` for all-list
- `['subscriptions', strategyCode]` for template-filtered
- `['subscription', subId]` for single
- `['subscription-backtest', subId]`
- `['subscription-trades', subId]`

`src/hooks/use-backtest.ts`, `use-strategy-trades.ts`, `use-open-position.ts`: update URLs and queryKeys.

## Component updates

| File | Change |
|---|---|
| `src/components/strategies/dashboard-column.tsx` | field access `sub.strategy_id` → `sub.strategy_code` |
| `src/components/strategies/new-subscription-dialog.tsx` | request body field name |
| `src/components/strategies/strategy-card.tsx` | field access |
| `src/components/strategies/strategy-config-card.tsx` | field access + start/stop already uses `sub.id` ✓ |
| `src/components/strategies/strategy-list-sidebar.tsx` | filter logic uses `strategy_code` |
| `src/components/strategy/add-symbol-dialog.tsx` | request body |
| `src/components/strategy/subscription-panel.tsx` | field access |

## Open item — `is_running`

The current `StartStopButton` uses `sub.backtest?.status === 'running'` to decide running state — that's backtest, not strategy. After this refactor, the cleanest fix is to surface `is_running: bool` in the `/subscriptions/{sub_id}` and list responses (computed from `StrategyAppService.get_strategy(sub.id).is_running`).

This adds one line in two handlers (`get_subscription/handler.py`, `list_subscriptions/handler.py`) and one field in the FE type. Include it here OR mark as a follow-up — decide at implementation time. **Recommendation:** include it; it closes the loop on the original bug that started this conversation.

## Implementation steps

1. Update TS types in `strategy-api.ts`, `backtest-api.ts`.
2. Update all API client functions (URL + param names).
3. Update all hooks (URL + param names + queryKey scheme).
4. Update all 7 components (field access + dialog form bodies).
5. `npm run lint && npx tsc --noEmit && npm run build`.
6. Manual smoke in the browser (after backend in place): add sub → start → see running → stop → backtest → delete.

## Acceptance criteria

- All listed files updated, no orphan references to `strategy_id` in TS
- `npx tsc --noEmit` passes
- `npm run lint` passes (no new errors)
- `npm run build` succeeds
- Manual smoke flow works against local backend

## Out of scope

- Visual redesign — purely a rename and URL update
