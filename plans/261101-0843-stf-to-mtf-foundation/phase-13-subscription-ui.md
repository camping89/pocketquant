---
phase: 13
title: "Generic subscription UI: form, row, drawer, actions"
status: completed
priority: P1
effort: 1.5d
dependencies: [11, 12]
---

# Phase 13: Generic subscription UI: form, row, drawer, actions

<!-- Red team 2026-11-01: #15 -->
No open issue. AGNOSTIC is the plan.md Conventions check "Strategy-agnostic UI": `git grep -n -i -E "triple[ _-]?screen|force[ _-]?index|elder" -- web/src src/pocketquant/app src/pocketquant/engine | wc -l` prints `0` (the generic MACD chart indicator is allowed).

## Goal

The strategies page shows every subscription as a generic row and opens a detail drawer per the owner-confirmed mockup, with create, edit-while-stopped, delete-with-warning, Close at market and Cancel pending behind a real-money confirmation, the last manual action's outcome, admin-token reads, and nothing strategy-specific.

## Context

- Inputs from earlier phases (not on HEAD): Phase 06 create body `{symbol, intervals, parameters, broker}`, edit route `PATCH /api/v1/subscriptions/{sub_id}` with body `{intervals, parameters}` (phase-06 Task 06.3 step 5), error codes `INVALID_INTERVALS`, `INVALID_PARAMETERS`, `SUBSCRIPTION_RUNNING`, `SUBSCRIPTION_HAS_EXPOSURE`; Phase 11 `POST /api/v1/subscriptions/{id}/close|cancel` (202, 409 `ACTION_PENDING`), `GET /api/v1/subscriptions/{id}/snapshot` (ring list, oldest first), `GET /api/v1/subscriptions/{id}/orders?limit=50`, list rows with `intervals`, `parameters`, `position`, `snapshot` (latest ring entry or null), `manual_action` and the last manual action outcome; Phase 09 order documents with `sl_price` and `tp_price`. Task 13.1 copies the real keys from that code.
- <!-- Red team 2026-11-01: #8 --> Shapes fixed by plan.md (C7 and Design verdict "Snapshot"): `pending = {side, price} | null`, `price` = stop price. `/orders` rows carry `price` and `updated_at` beside `stop_price`, `sl_price`, `tp_price`. One source per item: pending, decision and readings come from the row's `snapshot`; the position (with `unrealized_pnl`) comes from the row's `position`; the ring is read only for "Recent decisions", the orders only for the timeline.
- <!-- Red team 2026-11-01: #7 --> D7: every attempt to apply a manual action clears `manual_action` and records `accepted` or `rejected:<code>` in the ring and on the row. The action stays queued only while the trader is in standby or drain or has no price. So the buttons are disabled only while `manual_action` is set; once the trader has tried, the row shows the outcome and the owner may press again. A 409 `ACTION_PENDING` is shown as an error, never retried by the UI.
- <!-- Red team 2026-11-01: D8 --> D8: the snapshot, orders, subscription list, positions and trades reads require the admin token. Today only mutations send it: `send` reads `localStorage['pq.adminToken']` into `X-Admin-Token`, prompts once on 401 and retries once (`web/src/api/api-client.ts:35-57`); `apiFetch` sends no token (`:81-91`); the trades and positions hooks call bare `fetch` (`web/src/hooks/use-strategy-trades.ts:7-11`, `web/src/hooks/use-open-position.ts:15-20`). This phase routes those reads through `send`. Polled reads must not re-prompt every 5 s after the owner declines.
- D9: no freshness column. The mockup's freshness column (`[assumption]`) is not built.
- Mockup: `plans/reports/advise-261101-0847-stf-to-mtf-migration-ui-mockup.html` (row columns: strategy, symbol, interval chips with the entry chip highlighted, broker badge, state, position, pending, last decision, Start/Stop/Edit/Delete; drawer: readings table, decision with bar time, pending with Cancel pending, position with Close at market, recent decisions, orders and trades, chart with an interval switcher; form: strategy, symbol, intervals, broker PAPER/LIVE, parameters table with raw JSON toggle, `Create (stopped)`). Detail is a drawer, not a main column (synthesis section 6).
- No strategy is registered during this phase (Phase 05 empties `STRATEGY_REGISTRY`, Triple Screen arrives in Phase 14), so the local `UI OK` check covers layout and forms; the drawer with real data is `DRAWER OK` in Phase 17.
- Today: `Subscription` type `web/src/api/strategy-api.ts:7-20` (`interval`), create body `{symbol, interval}` `:27-32`; mutations `web/src/hooks/use-strategy-mutations.ts:45-53`; create dialog `web/src/components/strategies/new-subscription-dialog.tsx` (no broker, no parameters, error codes `:64-68`); row `strategy-card.tsx:77`; filter `strategy-list-sidebar.tsx:17-26`; three-column layout `strategies-page-layout.tsx:124-233` with the chart at `:142-148,209-215` and adapters `:64-98` (`useOpenPosition` at `:62`, only other importer `dashboard-column.tsx:1`); detail `strategy-config-card.tsx` (only importer: the layout); `dashboard-column.tsx` (only importer: the layout); `recent-trades-table.tsx` (importers: `dashboard-column.tsx`, `hooks/use-strategy-trades.ts` for the `StrategyTrade` type).
- Real-money confirm: `ConfirmDialog` `start-stop-button.tsx:120-171`; `moneyHint` `web/src/lib/money-hint.ts:5,13-19` (no `close`/`cancel`). Safeguards query lives in `exness-strip.tsx:1,19,27-31` with the comment "this is their only caller"; the form becomes the second caller.
- Reusable: drawer CSS `.drawer`, `.drawer-backdrop`, `.drawer-header`, `.drawer-section`, `.drawer-error` (`web/src/index.css:1124-1215`, used by `components/backtest/order-detail-drawer.tsx`); `IntervalSelector` (`components/controls/interval-selector.tsx:4-10`) with `useAvailableIntervals` (`hooks/use-available-intervals.ts:25`); `IntervalMultiSelect` and `configLabel` (Phase 12); `formatPrice`, `formatQty` (`lib/number-format.ts:9,16`); `apiPatch` (`api/api-client.ts:68`); `PnlBadge({ pnl, label })` (`pnl-badge.tsx:6`). `strategies-mobile*` CSS is also used by `components/backtest/backtest-workbench.tsx:96-107`; keep it.
- <!-- Red team 2026-11-01: #15 --> The web mirrors no backend rule: interval and parameter errors come back as 422 and show as `CODE: message`. Only JSON parsing happens in the client (the text must parse to be sent).
- No jsdom: logic lives in pure helpers tested in `*.test.ts` (`web/vitest.config.ts`).

## Entry gate

1. Conventions EG (1)-(3); the previous report is `reports/phase-12-*.md`.
2. `git grep -n -E "/\{sub_id\}/(close|cancel|snapshot|orders)" -- src/pocketquant/app/routes | wc -l` prints a number `>= 4`.
3. `git grep -n "\.patch(" -- src/pocketquant/app/routes/strategy.py | wc -l` prints a number `>= 1`.
4. `git grep -n "manual_action" -- src/pocketquant/engine/strategy/strategy_query_service.py | wc -l` prints a number `>= 1`.
5. `test -f web/src/lib/intervals.ts && test -f web/src/components/controls/interval-multi-select.tsx && echo ok` prints `ok`.

On a miss, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261101-0843-stf-to-mtf-foundation --from 13 after <UTC time>
```

## Files

- Create: `web/src/lib/subscription-view.ts`, `web/src/lib/subscription-view.test.ts`, `web/src/hooks/use-subscription-detail.ts`, `web/src/hooks/use-safeguards.ts`, `web/src/components/controls/params-editor.tsx`, `web/src/components/strategies/subscription-drawer.tsx`, `web/src/components/strategies/subscription-form-dialog.tsx` (by `git mv` of `new-subscription-dialog.tsx`).
- Modify: `web/src/api/api-client.ts`, `web/src/api/api-client.test.ts`, `web/src/api/strategy-api.ts`, `web/src/hooks/use-strategy-mutations.ts`, `web/src/hooks/use-strategy-trades.ts`, `web/src/lib/money-hint.ts`, `web/src/lib/money-hint.test.ts`, `web/src/components/strategies/strategy-card.tsx`, `web/src/components/strategies/strategy-list-sidebar.tsx`, `web/src/components/strategies/strategies-page-layout.tsx`, `web/src/components/strategies/start-stop-button.tsx` (label comment only), `web/src/components/strategies/exness-strip.tsx`, `web/src/components/backtest/backtest-form.tsx`, `web/src/index.css` (dead strategies-layout rules only).
- Delete: `web/src/components/strategies/strategy-config-card.tsx`, `web/src/components/strategies/dashboard-column.tsx`, `web/src/components/strategies/recent-trades-table.tsx`, `web/src/hooks/use-open-position.ts` (the drawer reads the position from the row).

## Tasks

### Task 13.1 — Admin-token reads, client types, calls and hooks

<!-- Red team 2026-11-01: D8 -->
**Goal:** the web client speaks the new subscription contract and sends the admin token on every read D8 guards, without re-prompting on each poll.

**Target files and symbols:** `api-client.ts` (`send`, new `apiFetchAdmin`); `api-client.test.ts`; `strategy-api.ts` (`Subscription`, `SnapshotEntry`, `SubscriptionPosition`, `SubscriptionOrder`, `ManualActionOutcome`, `listSubscriptions`, `addSymbol`, `editSubscription`, `requestAction`, `fetchSnapshot`, `fetchOrders`); `use-strategy-mutations.ts` (`useCreateSubscription`, `useEditSubscription`, `useSubscriptionAction`); `use-subscription-detail.ts` (`useSubscriptionSnapshot`, `useSubscriptionOrders`); `use-strategy-trades.ts`; `use-safeguards.ts` (`useSafeguards`, `Safeguards`).

**Steps:**
1. Tests first in `api-client.test.ts`, a new `describe('admin token on reads')` that re-imports the module per test (`vi.resetModules()` then `await import('./api-client')`, because the declined flag lives for the page load) with the existing `memoryStorage`, `json` and `sentToken` helpers: `it('sends the stored token on a read')`; `it('prompts once on a read 401 and retries with the new token')`; `it('does not prompt again after a declined read prompt')` (prompt returns `null`; two reads both reject with `ApiError` status 401; `prompt` called once); `it('still prompts on a mutation after a declined read prompt')`; `it('retries a read silently when a newer token was stored meanwhile')` (the first fetch stores `'new'` in `localStorage` and returns 401; the second call carries `'new'`; `prompt` not called). Run `cd web && npx vitest run src/api/api-client.test.ts > ../.cache/vitest.txt 2>&1; echo exit=$?`; expected red `exit=1`.
2. `api-client.ts`: `send(path, init, read = false)`. On 401: when the stored token differs from the one this request sent, retry once without a prompt; else when `read` and a read prompt was declined in this page load, throw; else prompt; an empty answer on a read sets the module flag `readPromptDeclined`. `apiFetchAdmin<T>(path, params?)` builds the URL as `apiFetch` does (share one small URL builder) and returns `(await send(url, { method: 'GET' }, true)).json()`. Rewrite the `:37-39` comment: mutations and the guarded reads carry the token; a declined prompt is not repeated by polled reads; the token is never baked in at build time.
3. Open the Phase 06 and Phase 11 code that serves the list row, `/snapshot` and `/orders` (`git grep -n -E "def (list_symbols|get_orders|get_subscription_snapshot|get_subscription_orders|_record_snapshot)|manual_action" -- src/pocketquant/engine/strategy src/pocketquant/app/routes/strategy.py`; Phase 11 names) <!-- Consistency sweep 2026-11-01 --> and copy their response keys into the types below. <!-- Red team 2026-11-01: #8 --> Where a key differs from this text, the code wins: rename it in the type and in the Task 13.2 fixtures together (the fixtures are built from these types), and say so in the report.
4. `Subscription`: drop `interval`; add `intervals: string[]`, `parameters: Record<string, unknown>`, `position: SubscriptionPosition | null`, `snapshot: SnapshotEntry | null`, `manual_action: 'close' | 'cancel' | null`, and the last outcome as `manual_action_outcome: ManualActionOutcome | null` with `ManualActionOutcome = { action: 'close' | 'cancel'; outcome: string; at: string }` (`outcome` is `accepted` or `rejected:<code>`; Phase 11 row key). `SnapshotEntry = { bar_start: string; interval: string | null; readings: { interval: string; name: string; value: unknown; ok: boolean | null }[]; decision: { action: string; reason: string } | null; outcome: string; pending: { side: string; price: number } | null }`. `SubscriptionPosition = { direction: 'LONG' | 'SHORT'; quantity: number; entry_price: number; sl_price: number | null; tp_price: number | null; unrealized_pnl: number }`. `SubscriptionOrder = { id: string; side: string; order_type: string; status: string; quantity: number; price: number | null; stop_price: number | null; sl_price: number | null; tp_price: number | null; filled_price: number | null; created_at: string; updated_at: string }`.
5. Calls: `listSubscriptions`, `fetchSnapshot(id)` (returns `SnapshotEntry[]`) and `fetchOrders(id)` (`/orders?limit=50`) use `apiFetchAdmin`; `use-strategy-trades.ts` fetches `/api/v1/subscriptions/${subId}/trades` through `apiFetchAdmin`; `addSymbol(code, { symbol, intervals, parameters, broker })`; `editSubscription(id, { intervals, parameters })` via `apiPatch`; `requestAction(id, action: 'close' | 'cancel')` via `apiPost(`/api/v1/subscriptions/${id}/${action}`, {})`.
6. Hooks: `useSubscriptionSnapshot(id)` and `useSubscriptionOrders(id)` poll every `5_000`; `useEditSubscription()` and `useSubscriptionAction()` invalidate `['subscriptions']` (the action also `['subscription-orders', id]` and `['subscription-snapshot', id]`); `useCreateSubscription` takes the new body. `use-safeguards.ts` moves the `Safeguards` interface and the `['safeguards']` query out of `exness-strip.tsx` (both now import `useSafeguards`); rewrite the `exness-strip.tsx:1` comment to name only the two mutations.

**Success criteria:** the new read tests pass; every caller compiles against the new types (Task 13.4's `tsc -b`); no bare `fetch(` remains in `web/src/hooks` for subscription reads.

**Verify:** `cd web && npx vitest run src/api/api-client.test.ts > ../.cache/vitest.txt 2>&1; echo exit=$?; cd .. && git grep -n -E "fetch\(.?/api/v1/subscriptions" -- web/src | wc -l` prints `exit=0` then `0`.

### Task 13.2 — Pure view helpers with tests

**Goal:** every text the row and drawer show comes from tested pure functions.

**Target files and symbols:** `web/src/lib/subscription-view.ts` (`positionText`, `pendingText`, `decisionText`, `manualActionText`, `parameterRows`, `parseParameters`, `timeline`, `errorText`); `subscription-view.test.ts`; `money-hint.ts` (`MoneyAction` gains `'close' | 'cancel'`), `money-hint.test.ts`.

**Steps:**
1. Tests first in `subscription-view.test.ts`, with fixtures typed as the Task 13.1 types:
   - `positionText(null)` is `'-'`; a LONG with SL and TP contains `'LONG'`, `'SL '` and `'TP '`; with `tp_price: null` it has no `'TP'`.
   - <!-- Red team 2026-11-01: #8 --> `pendingText(null)` is `'-'`; `pendingText({ side: 'buy', price: 71250 })` starts with `'BUY STOP @ '` and contains `formatPrice(71250)`.
   - `decisionText(null)` is `'-'`; an entry with decision `{action: 'hold', reason: 'position open'}` and outcome `'no_signal'` is `'hold - position open'`; outcome `'skipped:stale'` appends `' (skipped:stale)'`; <!-- Red team 2026-11-01: #7, #8 --> the outcomes Phase 11 writes all render: `no_signal` adds nothing, and `sent`, `skipped:stop_unchanged`, `skipped:nothing_open`, `rejected:close_failed` and `accepted` each append `' (<outcome>)'`; an entry with `interval: null` is a manual-action record and renders `'manual action (<outcome>)'` (for example `'manual action (rejected:close_failed)'`).
   - <!-- Red team 2026-11-01: #7 --> `manualActionText(null, null)` is `''`; `manualActionText('close', null)` is `'close requested - runs when the trader holds the lease'`; `manualActionText(null, {action: 'cancel', outcome: 'accepted', at})` is `'cancel accepted'`; `manualActionText(null, {action: 'close', outcome: 'rejected:MARKET_SESSION_CLOSED', at})` is `'close rejected:MARKET_SESSION_CLOSED - press again to retry'`.
   - `parameterRows({a: 1, b: 'x'}, {b: 'y', c: 2})` equals `[{key:'a',def:1,value:1,extra:false},{key:'b',def:'x',value:'y',extra:false},{key:'c',def:undefined,value:2,extra:true}]`.
   - `parseParameters('')` is `{value: {}}`; `parseParameters('{"a":1}')` is `{value: {a: 1}}`; `parseParameters('[1]')` and `parseParameters('{')` return `{error: <string>}`.
   - `timeline(orders, trades)` returns newest first by `updated_at` (orders) and `exit_time` (trades), each item `{at, text}`; a `stop_market` order text contains `'STOP'` and its `stop_price`; a trade text contains `'closed @'`.
   - `errorText(new ApiError('busy', 409, 'ACTION_PENDING'))` is `'ACTION_PENDING: busy'`; <!-- Red team 2026-11-01: D8 --> `errorText(new ApiError('x', 401))` is `'Admin token required: reload the page and enter it.'`; `errorText(new Error('x'))` is `'x'`.
   In `money-hint.test.ts` add: `moneyHint('exness','close').real` is `true` and its title starts with `'Real money'`; `moneyHint('paper','cancel').chip` is `'Paper'`.
2. Run `cd web && npx vitest run src/lib/subscription-view.test.ts src/lib/money-hint.test.ts > ../.cache/vitest.txt 2>&1; echo exit=$?`; expected red `exit=1`.
3. Implement with `formatPrice`/`formatQty`. `money-hint.ts` `REAL_TITLES` gains `close: 'Real money: closes the Exness position at market and cancels its pending order'` and `cancel: 'Real money: cancels the pending Exness order'`.

**Success criteria:** both test files pass.

**Verify:** `cd web && npx vitest run src/lib/subscription-view.test.ts src/lib/money-hint.test.ts > ../.cache/vitest.txt 2>&1; echo exit=$?` prints `exit=0`.

### Task 13.3 — One form for create and edit, shared params editor

**Goal:** create and edit use one form; both the subscription form and the backtest form use one parameters editor.

**Target files and symbols:** `web/src/components/controls/params-editor.tsx` (`ParamsEditor({ defaults, text, onChange })`); `subscription-form-dialog.tsx` (`SubscriptionFormDialog({ sub, onClose }: { sub?: Subscription; onClose: () => void })`); `backtest-form.tsx`; `strategy-list-sidebar.tsx`.

**Steps:**
1. `ParamsEditor`: the JSON text is the single state. Render a table `Key | Default | Value` from `parameterRows(defaults, parsed)`; editing a value cell writes `JSON.stringify({ ...parsed, [key]: v }, null, 2)` where `v` is `Number(input)` when the default is a number and the input is finite, `input === 'true'` when the default is a boolean, else the string. A `Edit as raw JSON` toggle shows a textarea bound to the text. A parse error from `parseParameters` shows in `#ef5350`. With no defaults it shows `This strategy declares no parameters.`
2. `backtest-form.tsx`: replace the parameters textarea with `<ParamsEditor defaults={defaults.data ?? {}} text={paramsText} onChange={setParamsText} />`; submit uses `parseParameters` (a parse error blocks submit).
3. `git mv web/src/components/strategies/new-subscription-dialog.tsx web/src/components/strategies/subscription-form-dialog.tsx`; rename the export to `SubscriptionFormDialog`. Delete `INTERVALS` (`:7`) and the single-select; use `IntervalMultiSelect`. Add a broker choice `PAPER | LIVE`: LIVE is disabled with the hint `LIVE places real-money orders and needs the trader's live flag on.` unless `useSafeguards().data?.live_trading === true`; show the `moneyHint(broker, 'start')` chip. Parameters: `ParamsEditor` with `useStrategyDefaults(strategy)`, prefilled as in Phase 12. Create submits `{symbol, intervals, parameters, broker}` with the button `Create (stopped)`. Edit mode (`sub` given): strategy, symbol and broker render as read-only text; intervals and parameters start from `sub`; the button `Save` is disabled unless `sub.desired_state === 'stopped' && sub.actual_state === 'stopped'`, with the note `Edit is enabled only while the subscription is stopped. Start re-runs warm-up.`. <!-- Red team 2026-11-01: #15 --> Only a `parseParameters` error blocks submit; interval and parameter rules are the backend's. Every server error shows `errorText(err)` (codes `SUBSCRIPTION_ALREADY_EXISTS`, `SYMBOL_NOT_TRACKED`, `BROKER_DISABLED`, `INVALID_INTERVALS`, `INVALID_PARAMETERS`, `SUBSCRIPTION_RUNNING`, `SUBSCRIPTION_HAS_EXPOSURE` reach the user as `CODE: message`).
4. `strategy-list-sidebar.tsx`: import `SubscriptionFormDialog`; the `+ New` title becomes `New subscription`; the filter matches `s.intervals.join(' ')` instead of `s.interval`; a list query error renders `errorText(err)` in `.drawer-error` above the rows (D8 401 included).

**Success criteria:** `test -f web/src/components/strategies/new-subscription-dialog.tsx` fails; `git grep -n "NewSubscriptionDialog" -- web/src | wc -l` prints `0`.

**Verify:** `test ! -f web/src/components/strategies/new-subscription-dialog.tsx && git grep -n "NewSubscriptionDialog" -- web/src | wc -l` prints `0`.

### Task 13.4 — Row, drawer, actions, layout

**Goal:** the page matches the mockup: a generic row list and a detail drawer with real-money confirmations and the last action outcome.

**Target files and symbols:** `strategy-card.tsx` (`StrategyCard`), `subscription-drawer.tsx` (`SubscriptionDrawer({ sub, onClose })`), `strategies-page-layout.tsx` (`StrategiesPageLayout`), `start-stop-button.tsx:10`, `use-strategy-trades.ts`, `web/src/index.css`.

**Steps:**
1. `StrategyCard({ sub, selected, onOpen, onEdit })`: line 1 = symbol code, exchange tag, LIVE/PAPER badge, interval chips (`sub.intervals`, first chip bold with `title="entry interval"`), state pill, strategy code; line 2 = `positionText(sub.position)` · `pendingText(sub.snapshot?.pending ?? null)` · `decisionText(sub.snapshot)`; <!-- Red team 2026-11-01: #7 --> line 3, when non-empty, `manualActionText(sub.manual_action, sub.manual_action_outcome)` (a `rejected:` outcome in `#ef5350`). Right side: `StartStopButton` (label `${code} · ${sub.intervals.join(' ')}`; update the `:10` comment to `"<code> · <intervals>"`), `Edit` (calls `onEdit`, disabled unless both states are stopped), `Delete` (disabled while running; opens `ConfirmDialog` with `moneyHint(sub.broker,'delete')`; when `sub.position` or `sub.snapshot?.pending` exists the body says `This subscription still has <positionText> / <pendingText>. Deleting it does not close them.`). Action clicks call `e.stopPropagation()`; a click elsewhere on the card calls `onOpen`.
2. `SubscriptionDrawer` uses the `.drawer` classes (width override `min(720px, 100vw)`), Escape and backdrop close it (as `order-detail-drawer.tsx`). <!-- Red team 2026-11-01: #8 --> Sections in mockup order, each from one source: header (`strategy_code · symbol · chips`, badge, state); `Readings` table (`Interval | Name | Value | OK` from `sub.snapshot.readings`; OK renders `✔`, `✘` or `–`); `Decision` (`decisionText(sub.snapshot)` plus `bar <bar_start>` and ` (<interval>)` only when `interval` is not null); `Pending order` (`pendingText(sub.snapshot?.pending ?? null)`) with `Cancel pending`; `Open position` (`positionText(sub.position)` plus `PnlBadge pnl={sub.position.unrealized_pnl}`) with `Close at market`; `manualActionText(...)` under the two buttons; `Recent decisions` (`useSubscriptionSnapshot` ring newest first, `HH:mm decisionText`); `Orders & trades` (`timeline(orders, trades)` from `useSubscriptionOrders` and `useStrategyTrades(sub.id)`); `Chart` = `IntervalSelector` over `useAvailableIntervals(sub.symbol).filter((o) => sub.intervals.includes(o.value))` (default `sub.intervals[0]`) above `StrategyChart`, with `IndicatorToggles`, the localStorage indicator state and the trade adapter moved from `strategies-page-layout.tsx:23-40,64-87`; the chart position is built from `sub.position` (`side` from `direction`, `entry_price`, `qty` = `quantity`, `liq_price: null`, `leverage: 1`). A query error in a section shows `errorText(err)` in `.drawer-error`.
3. `Cancel pending` (disabled with no `sub.snapshot?.pending` or a set `manual_action`) and `Close at market` (disabled with no `sub.position` or a set `manual_action`) open `ConfirmDialog` with `moneyHint(sub.broker, 'cancel' | 'close')` chip; for `exness` the heading is `This cancels a real-money order on Exness.` / `This closes a real-money position on Exness at market and cancels its pending order.`, for paper the same words with `paper`. Confirm calls `useSubscriptionAction().mutate({ id, action })`; an error shows `errorText(err)` in `.drawer-error` (`ACTION_PENDING` included). <!-- Red team 2026-11-01: #7 --> No other lock-out: after the trader's attempt clears `manual_action`, both buttons follow only the position and pending state again.
4. `strategies-page-layout.tsx`: render `ExnessStrip`, then `StrategyListSidebar` full width (rows open the drawer, `Edit` opens `SubscriptionFormDialog` with `sub`), then `SubscriptionDrawer` when a row is selected (selected id re-read from the polled list as today, `:43-52`). Remove the main column, the dashboard column, the mobile tab view and the `useOpenPosition` call.
5. Move `StrategyTrade` from `recent-trades-table.tsx` into `use-strategy-trades.ts`; delete `strategy-config-card.tsx`, `dashboard-column.tsx`, `recent-trades-table.tsx` and `hooks/use-open-position.ts`. In `web/src/index.css` delete each rule whose class (`strategies-layout`, `strategies-sidebar`, `strategies-main`, `strategies-dashboard`) has no user left (`git grep -n "<class>" -- web/src ':!web/src/index.css'` prints nothing); keep every `strategies-mobile*` rule.
6. Run `cd web && npx tsc -b && npm run lint`; fix what they report in this phase's files.

**Success criteria:** `tsc -b` exits 0; lint `0 errors`; no `sub.interval` reader and no `useOpenPosition` remains.

**Verify:** `cd web && npx tsc -b > ../.cache/tsc.txt 2>&1; echo exit=$?; cd .. && git grep -n -E "sub\.interval\b|selectedSub\.interval\b|useOpenPosition" -- web/src | wc -l` prints `exit=0` then `0`.

### Task 13.5 — [USER] local look, then CLOSE

<!-- Red team 2026-11-01: #15 --> (The freshness task is removed by D9.)

**Goal:** the owner sees the UI before the commit; gates green; CI green.

**Target files and symbols:** all files of this phase.

**Steps:**
1. AGNOSTIC prints `0`; GATES with the web part pass.
2. [USER] Ask the owner in Vietnamese (intent): run `just up`, `just be`, `just fe` locally, open `http://localhost:5173/strategies` and `http://localhost:5173/backtest`, check the list row layout, the `+ New` form (interval chips with the entry mark, PAPER/LIVE with LIVE disabled, parameters editor), and the backtest form (interval chips, parameters editor), then reply `UI OK` or list defects. Tell the owner the strategy list is empty until the next phase adds the first strategy, that a local database holding old single-interval subscriptions may need `just reset` (drops local data, the owner's choice), and that a local api without `ADMIN_TOKEN` does not ask for the token (the 401 path is covered by Task 13.1's tests and seen on prod in Phase 17). Only the literal `UI OK` passes; listed defects are fixed in this phase and the question is asked again.
3. Record `UI OK` in the report. FULLSUITE.
4. Commit `feat(web): generic multi-timeframe subscription view with manual close and cancel`; push `develop`; run the CLOSE check.

**Success criteria:** the report holds `UI OK`; CI `success` on HEAD.

**Verify:** `grep -c "^UI OK$" plans/261101-0843-stf-to-mtf-foundation/reports/phase-13-subscription-ui.md; GH_TOKEN=$(gh auth token --user camping89) gh run list --branch develop --limit 1 --json headSha,status,conclusion -q '.[0] | "\(.status) \(.conclusion) \(.headSha)"'` prints `1` then `completed success <sha>` with `<sha>` equal to `git rev-parse HEAD`.

## Rollback

`git revert <commit>` on `develop` and push; nothing reaches prod before Phase 15. The revert restores the token-less reads, which a D8 backend answers with 401: revert Phase 11 and Phase 13 together or neither.

## Report

`reports/phase-13-subscription-ui.md`: entry-gate outputs; the response keys copied in Task 13.1 (including `manual_action_outcome`) and any difference from this file; each Verify output; the owner's `UI OK` line; AGNOSTIC count; GATES and FULLSUITE tail lines; any metric-ceiling commit; commit sha and CI run id; then `Result: PASS`.

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same failure evidence to the user. Never continue by self-reasoning.
