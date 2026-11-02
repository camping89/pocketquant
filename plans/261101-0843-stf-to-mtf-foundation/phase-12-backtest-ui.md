---
phase: 12
title: "Backtest UI: intervals, defaults, labels"
status: completed
priority: P1
effort: 0.5d
dependencies: [8]
---

# Phase 12: Backtest UI: intervals, defaults, labels

<!-- Red team 2026-11-01: #15 -->
No open issue. AGNOSTIC is the plan.md Conventions check "Strategy-agnostic UI": `git grep -n -i -E "triple[ _-]?screen|force[ _-]?index|elder" -- web/src src/pocketquant/app src/pocketquant/engine | wc -l` prints `0` (the generic MACD chart indicator is allowed).

## Goal

The backtest form runs a strategy on an ordered list of intervals with parameters prefilled from the strategy's defaults, and every backtest view shows intervals and `key=value` parameters.

## Context

- Inputs from earlier phases (not on HEAD): Phase 06 `GET /api/v1/strategies/{code}` returns `parameters` (the strategy's `DEFAULTS`); Phase 08 `RunBacktestCommand.intervals: list[str]` replaces `interval`, `config_snapshot.intervals`, top-level `interval` = entry interval, and `GET /api/v1/backtest/strategy/{code}` rows carry `intervals` and `parameters`.
- Design verdicts: unsorted or duplicate interval lists are 422 at the backend, never silently sorted. Backtest results keep top-level `interval` = entry interval, so the rail filter stays an entry-interval filter. Compare cap stays 3.
- <!-- Red team 2026-11-01: #15 --> The web does not mirror the backend interval rule. The chip control keeps the list sorted by `INTERVAL_MS` (`web/src/lib/datetime.ts:65-70`, exported at `:70`), the only interval table in `web/src`; no second map is added. A 422 reaches the user as its message: `toApiError` puts `error.message` on the `ApiError` (`web/src/api/api-client.ts:16-33`), and the rail renders `runBacktest.error.message` (`web/src/components/backtest/run-history-rail.tsx:156-158`).
- Interval lists: `web/src/constants/active-intervals.ts:3` (`ACTIVE_INTERVALS`, includes `1w`, not exported today); short copies without `1w` in `web/src/components/backtest/backtest-form.tsx:11` and `run-history-rail.tsx:9`.
- Backtest form: single `<select>` `backtest-form.tsx:129-135`, `interval` state `:45`, JSON textarea `:55,76-84,146-154`, STF placeholder `:150`, STF hint `:81`, submit body `:86-94`. Strategy list comes from `useStrategyList` (`web/src/hooks/use-backtest-run.ts:28-35`, `GET /api/v1/backtest/strategies`).
- API types: `RunBacktestBody` `web/src/api/backtest-api.ts:176-187` (`interval: string`); `fetchBacktestRun` lifts `interval` from `config_snapshot` (`:236-247`); `BacktestRunRow` `:259-271` (no `parameters` field). Defaults route exists with no web caller (`src/pocketquant/app/routes/strategy.py:35-43`).
- Labels: `run-header.tsx:12-13,70` (`pair = [symbol, interval]`), only caller `backtest-detail-pane.tsx:40-49`; compare legend `run-compare-view.tsx:36-43`; diff header `metrics-diff-table.tsx:48-50`; list item `run-list-item.tsx:34`.
- Web tests are pure `src/**/*.test.ts` in node (`web/vitest.config.ts`); no jsdom (synthesis drop list).

## Entry gate

1. Conventions EG (1)-(3); the previous report is `reports/phase-11-*.md`.
2. `git grep -n "intervals" -- src/pocketquant/engine/backtest/backtest_command_service.py | wc -l` prints a number `>= 1` (Phase 08 merged).
3. `git grep -n "\"parameters\"" -- src/pocketquant/engine/strategy/strategy_query_service.py | wc -l` prints a number `>= 1` (Phase 06 defaults).
4. `cd web && npx tsc -b > /dev/null 2>&1; echo exit=$?` prints `exit=0`.

On a miss, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261101-0843-stf-to-mtf-foundation --from 12 after <UTC time>
```

## Files

- Create: `web/src/lib/intervals.ts`, `web/src/lib/intervals.test.ts`, `web/src/components/controls/interval-multi-select.tsx`.
- Modify: `web/src/constants/active-intervals.ts`, `web/src/api/backtest-api.ts`, `web/src/api/strategy-api.ts`, `web/src/hooks/use-strategies.ts`, `web/src/components/backtest/backtest-form.tsx`, `web/src/components/backtest/run-header.tsx`, `web/src/components/backtest/backtest-detail-pane.tsx`, `web/src/components/backtest/run-compare-view.tsx`, `web/src/components/backtest/metrics-diff-table.tsx`, `web/src/components/backtest/run-history-rail.tsx`, `web/src/components/backtest/run-list-item.tsx`.
- Delete: none.

## Tasks

### Task 12.1 — Interval order and run label helpers with tests

<!-- Red team 2026-11-01: #15 -->
**Goal:** one web module sorts an interval list by the existing `INTERVAL_MS` table and builds the run label; it holds no interval table and no copy of the backend rule.

**Target files and symbols:** `web/src/lib/intervals.ts` (`sortIntervals`, `configLabel`); `web/src/lib/intervals.test.ts`; `web/src/lib/datetime.ts` (`INTERVAL_MS`, read only); `web/src/constants/active-intervals.ts` (`ACTIVE_INTERVALS`).

**Steps:**
1. Write `web/src/lib/intervals.test.ts` first (vitest, `describe`/`it`):
   - `sortIntervals(['4h','15m','1h'])` equals `['15m','1h','4h']`; `sortIntervals(['1w','1d'])` equals `['1d','1w']`; the input array is not mutated.
   - `configLabel(['15m','1h','4h'], undefined, {exit_mode: 'strategy', entry_type: 'stop'})` equals `'15m 1h 4h · entry_type=stop exit_mode=strategy'` (keys sorted); `configLabel(undefined, '1m', {})` equals `'1m'`; `configLabel(['1h'], undefined, undefined)` equals `'1h'`.
2. Run `cd web && npx vitest run src/lib/intervals.test.ts > ../.cache/vitest.txt 2>&1; echo exit=$?`; expected red `exit=1` (module missing).
3. In `active-intervals.ts` change line 3 to `export const ACTIVE_INTERVALS = ...` (no other change).
4. Write `intervals.ts`: `import { INTERVAL_MS } from './datetime'`; `sortIntervals(list)` returns a new array sorted by `INTERVAL_MS[iv]`; `configLabel(intervals, fallback, parameters)` joins `intervals ?? (fallback ? [fallback] : [])` with spaces, then appends `' · '` plus `key=value` pairs sorted by key and joined by spaces when `parameters` has keys (`String(value)` for each value). One `//` comment above `sortIntervals`: the order only keeps the chips readable; the backend owns the interval rule and its 422 message reaches the user.

**Success criteria:** the test file passes; `web/src` defines no interval table besides `INTERVAL_MS` and no client copy of the interval rule.

**Verify:** `cd web && npx vitest run src/lib/intervals.test.ts > ../.cache/vitest.txt 2>&1; echo exit=$?; cd .. && git grep -n -E "INTERVAL_SECONDS|intervalsError" -- web/src | wc -l` prints `exit=0` then `0`.

### Task 12.2 — Interval multi-select control

**Goal:** a reusable chip control picks an ordered interval list and marks the entry interval.

**Target files and symbols:** `web/src/components/controls/interval-multi-select.tsx` (`IntervalMultiSelect({ value, onChange }: { value: string[]; onChange: (v: string[]) => void })`).

**Steps:**
1. Render one toggle button per `ACTIVE_INTERVALS` entry (class `interval-btn`, `active` when selected, as `controls/interval-selector.tsx` does). A click adds or removes the interval and calls `onChange(sortIntervals(next))`.
2. Below the chips render `Lowest first: <value joined by spaces> - the lowest is the entry interval.` <!-- Red team 2026-11-01: #15 --> No client-side validity message: an invalid set is answered by the backend 422.
3. The first selected chip gets `title="entry interval"` and a bold label.

**Success criteria:** the control compiles and imports only `intervals.ts` and `active-intervals.ts` from the app.

**Verify:** no verification needed (Task 12.3 runs `tsc -b`).

### Task 12.3 — Backtest form posts intervals with defaults prefilled

**Goal:** the form sends `intervals` and starts from the strategy's declared defaults; no STF text remains; a backend 422 shows its message.

**Target files and symbols:** `backtest-api.ts` (`RunBacktestBody`, `BacktestRunResult`, `fetchBacktestRun`, `BacktestRunRow`); `strategy-api.ts` (new `fetchStrategyDefaults`); `use-strategies.ts` (new `useStrategyDefaults`); `backtest-form.tsx` (`BacktestForm`).

**Steps:**
1. `backtest-api.ts`: in `RunBacktestBody` replace `interval: string` with `intervals: string[]`; add `intervals?: string[]` to `BacktestRunResult` and set it in `fetchBacktestRun` from `cfg.intervals as string[] | undefined` beside the `interval` lift (`:247`); add `intervals?: string[]` and `parameters?: Record<string, unknown>` to `BacktestRunRow`.
2. `strategy-api.ts`: `export async function fetchStrategyDefaults(code: string): Promise<Record<string, unknown>>` returns `(await apiFetch<{ parameters?: Record<string, unknown> }>(`/api/v1/strategies/${encodeURIComponent(code)}`)).parameters ?? {}`.
3. `use-strategies.ts`: `useStrategyDefaults(code: string)` = `useQuery({ queryKey: ['strategy-defaults', code], queryFn: () => fetchStrategyDefaults(code), enabled: !!code, staleTime: 5 * 60 * 1000 })`.
4. `backtest-form.tsx`: delete `INTERVALS` (`:11`) and the `interval` state; add `const [intervals, setIntervals] = useState<string[]>(['1m'])` and render `<IntervalMultiSelect value={intervals} onChange={setIntervals} />` in place of the interval `<select>` (label `Intervals`). Read `useStrategyDefaults(effectiveStrategy)`; add `const [paramsFor, setParamsFor] = useState('')` and, during render, when `defaults.data` is loaded and `paramsFor !== effectiveStrategy`, call `setParamsFor(effectiveStrategy)` and `setParamsText(JSON.stringify(defaults.data, null, 2))` (the React "adjust state while rendering" pattern; no `useEffect`). Placeholder becomes `'{}'`; the JSON error hint becomes `'Parameters must be valid JSON.'`. The body sends `intervals` as the control holds them. <!-- Red team 2026-11-01: #15 --> Add no interval check before submit; the existing rail error (`run-history-rail.tsx:156-158`) shows the backend 422 message.
5. Run `cd web && npx tsc -b`; fix every error it reports in the files of this phase only.

**Success criteria:** `git grep -n -E "key_level_lookback|\"direction\": \"long\"" -- web/src/components/backtest | wc -l` prints `0`; `tsc -b` exits 0.

**Verify:** `cd web && npx tsc -b > ../.cache/tsc.txt 2>&1; echo exit=$?; cd .. && git grep -n -E "key_level_lookback|\"direction\": \"long\"" -- web/src/components/backtest | wc -l` prints `exit=0` then `0`.

### Task 12.4 — Labels and rail show intervals and parameters

**Goal:** header, compare legend, diff header and list item show `configLabel`; the rail filter lists every active interval.

**Target files and symbols:** `run-header.tsx` (`RunHeaderProps`, `pair`), `backtest-detail-pane.tsx:40-49`, `run-compare-view.tsx:36-43`, `metrics-diff-table.tsx:48-50`, `run-list-item.tsx:34`, `run-history-rail.tsx:9,107-111`.

**Steps:**
1. `run-header.tsx`: add props `intervals?: string[]` and `parameters?: Record<string, unknown>`; `pair = [symbol, configLabel(intervals, interval, parameters)].filter(Boolean).join(' · ')`. `backtest-detail-pane.tsx` passes `intervals={run.intervals}` and `parameters={run.parameters}`.
2. `run-compare-view.tsx` legend: `{r.strategy_code} · {String(r.config_snapshot?.symbol ?? '')} · {configLabel(r.intervals, r.interval, r.parameters)}`. Keep the three hook slots and the cap of 3.
3. `metrics-diff-table.tsx` header: add a second small line under the symbol with `configLabel(r.intervals, r.interval, r.parameters)`.
4. `run-list-item.tsx:34`: `{row.symbol} · {configLabel(row.intervals, row.interval, row.parameters)}`.
5. `run-history-rail.tsx`: `const INTERVALS = ['', ...ACTIVE_INTERVALS]`; the filter label becomes `Entry interval (optional)` (the filter matches the top-level entry `interval`).

**Success criteria:** no short interval list remains in `web/src/components/backtest` (the subscription dialog copy at `new-subscription-dialog.tsx:7` goes in Phase 13); the compare cap of 3 is unchanged.

**Verify:** `git grep -n "'1m', '5m', '15m', '1h', '4h', '1d'" -- web/src/components/backtest | wc -l; git grep -n "slice(0, 3)" -- web/src/routes/backtest_.compare.tsx | wc -l` prints `0` then `1`.

### Task 12.5 — CLOSE

**Goal:** gates green, one commit on `develop`, CI green.

**Target files and symbols:** all files of this phase.

**Steps:**
1. AGNOSTIC prints `0`.
2. GATES with the web part (`npx tsc -b` exit 0, `npm run lint` `0 errors`, `npx vitest run` exit 0) and FULLSUITE from plan.md.
3. Commit `feat(web): run backtests on multiple intervals with strategy defaults`; push `develop` with the Ops recipe; run the CLOSE `gh run list` check.

**Success criteria:** CI conclusion `success` on HEAD.

**Verify:** `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch develop --limit 1 --json headSha,status,conclusion -q '.[0] | "\(.status) \(.conclusion) \(.headSha)"'` prints `completed success <sha>` where `<sha>` equals `git rev-parse HEAD`.

## Rollback

`git revert <commit>` on `develop` and push; nothing reaches prod before Phase 15.

## Report

`reports/phase-12-backtest-ui.md`: the entry-gate outputs; each task's Verify output; the AGNOSTIC count; GATES and FULLSUITE tail lines; any metric-ceiling commit; commit sha and CI run id; then `Result: PASS`.

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
