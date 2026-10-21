---
phase: 6
title: "SPA: PAPER/LIVE badge, state pill, Exness strip with Pause/Resume, real-money hints (B11)"
status: completed
priority: P1
effort: 0.5d
dependencies: [1, 2, 5]
---

# Phase 06: SPA: PAPER/LIVE badge, state pill, Exness strip, real-money hints (B11)

## Context
- Spec: the "After" view of `D:/w/_me/algotrading/plans/reports/advise-261020-1630-exness-go-live-safeguards-preview.html` and `D:/w/_me/algotrading/plans/reports/kongming-261020-1837-strategies-button-grouping.md` (both user-approved). Where they differ, the advisory decides: one state pill per row, no dot (the mockup draws both, `preview.html:345-350`).
- Needs: `broker` in the subscription list (Phase 02); `GET/POST /api/v1/admin/safeguards[...]` (Phase 05; the pause is stored, so the local check below writes the local `safeguards` collection); the 401 prompt-and-retry in `apiPost` (Phase 01).
- Today: the TS `Subscription` has no `broker` (`web/src/api/strategy-api.ts:8-21`); rows show a status dot (`components/strategies/strategy-card.tsx:5,16-20,44`); Start has no confirm (`start-stop-button.tsx:88-96`); the Stop dialog says "This will halt live execution." (`:68`); Delete sits beside Start/Stop (`strategy-config-card.tsx:70-91`); red buttons use inline styles (`start-stop-button.tsx:32-33,76`; `strategy-config-card.tsx:84-86`); `index.css` has `.btn-warn` (`:637-644`) and no `.btn-danger`.
- `.strategies-layout` and `.strategies-mobile` are each `calc(100vh - 41px)` (`index.css:1510-1523`); a strip above them would push the grid off-screen.
- vitest runs in `node` and includes only `src/**/*.test.ts` (`web/vitest.config.ts`); no DOM library. Logic is tested as a pure function; dialogs are checked by the user.
- `refetchInterval: 5_000` precedent: `strategy-list-sidebar.tsx:25`.
- Local run: `cp ../pocketquant-config/local/all-local.env .env` (local Mongo `localhost:52017`, `ENVIRONMENT=development`), `just up`, `just be` (port 41921), `just fe` (vite on 5173, proxies `/api`).

## Gates in this phase
- [USER] Task 6.11: the user checks the UI and replies `ui ok` or names the failing item.
- The `develop` push (Task 6.12) is authorized by the plan.

## Entry gate
Run first. On a miss: edit nothing, spawn no `kongming`, leave the phase pending, and end with:
```
Status: BLOCKED
NOT_YET: <reason>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261019-1957-exness-go-live --from 06 after <UTC time>
```
- `docker ps` exits 0 (start Docker Desktop and retry once after 10 s).
- `npm --version` exits 0 (else `NOT_YET: npm blocked by NVM; see plans/261019-1957-exness-go-live/reports/kongming-261021-0010-answers-reanalysis.md`).
- `git status --porcelain -- src web deploy tests scripts docs` prints nothing.
- After `git fetch origin`, `git show origin/develop:src/pocketquant/app/routes/safeguards.py | grep -c "admin/safeguards"` prints ≥ 1 (Phases 01, 02 and 05 are pushed).

## Tasks

### Task 6.1 — Re-check the dead files
- Goal: delete only files with no importer outside the deleted set.
- Target files and symbols: `web/src/components/strategies/status-dot.tsx`, `template-form.tsx`, `leverage-badge.tsx`, `equity-sparkline.tsx`; `web/src/components/strategy/subscription-panel.tsx`, `forward-status-badge.tsx`, `add-symbol-dialog.tsx`; `web/src/hooks/use-subscriptions.ts`.
- Steps: for each file run `grep -rn "<basename>\b" web/src` and grep each exported name. `status-dot.tsx` is imported only by `strategy-card.tsx:5` (changed in Task 6.5). Keep `listSubscriptions`, `addSymbol`, `removeSubscription`, `deleteStrategy`, `RunState` and the `status-pulse` keyframes (`index.css:1980`, used by `backtest-status-badge.tsx:40`).
- Success criteria: a list of files with no outside importer.
- Verify: every grep hit is inside the deleted set or `strategy-card.tsx`. Any other hit → stop (Failure Protocol).

### Task 6.2 — `broker` on the TS type
- Goal: the SPA knows the broker.
- Target files and symbols: `web/src/api/strategy-api.ts` → `Subscription`.
- Steps: add `broker: 'paper' | 'exness'` with doc comment "Set at create time; `exness` sends real orders."
- Success criteria: one field.
- Verify: no verification needed (Task 6.12 build).

### Task 6.3 — `moneyHint`
- Goal: one pure function gives each action its chip and title.
- Target files and symbols: create `web/src/lib/money-hint.ts` → `moneyHint(broker: 'paper' | 'exness', action: 'start' | 'stop' | 'delete' | 'pause' | 'resume'): { real: boolean; chip: 'Real money' | 'Paper'; title: string }`.
- Steps:
  1. `real` is true for `exness` and for `pause`/`resume` (account-level; callers pass `'exness'`).
  2. Titles: pause "Real money: blocks new entries; open positions and SL/TP unchanged"; resume "Real money: re-enables real-money entries"; exness start "Real money: starts real orders on Exness"; exness stop "Real money: stops new signals; open position stays with venue SL/TP"; exness delete "Real money: deletes this Exness subscription (stop it first)"; any paper action "Paper only, no real orders".
- Success criteria: one exported function.
- Verify: no verification needed (Task 6.10).

### Task 6.4 — CSS
- Goal: classes for danger buttons, chips, badges, pills, strip; the page fits with the strip.
- Target files and symbols: `web/src/index.css`.
- Steps:
  1. Add `.btn-danger` (+ hover) beside `.btn-warn` (`:637-644`); `.risk`, `.risk-real`, `.risk-paper`; `.mode`, `.mode-live`, `.mode-paper`; `.state-pill` with `--running`, `--starting`, `--stopped`; strip classes. Values from the mockup CSS (`preview.html:56-77,96-106`) using theme variables.
  2. Add `.strategies-page { display: flex; flex-direction: column; height: calc(100vh - 41px); }`; change `.strategies-layout` and `.strategies-mobile` to `flex: 1; min-height: 0`.
  3. Reword the comment at `:1979` to "used by state pills and status badges".
- Success criteria: the classes exist.
- Verify: `grep -c "\.btn-danger" web/src/index.css` prints ≥ 1.

### Task 6.5 — Row: badge and pill
- Goal: every row shows PAPER/LIVE and one state pill.
- Target files and symbols: `web/src/components/strategies/strategy-card.tsx` (`toStrategyStatus` `:16-20`).
- Steps: remove `StatusDot`; on line 1 after the exchange chip add the badge from `sub.broker` (`.mode-paper` grey, `.mode-live` red, `title="broker: <broker>"`); on line 2 after `interval · strategy_code` add the pill: `RUNNING` when `actual_state === 'running'`, `STARTING` when only `desired_state` is running, else `STOPPED`; update the header comment.
- Success criteria: no `StatusDot` import.
- Verify: `grep -c "StatusDot" web/src/components/strategies/strategy-card.tsx` prints `0`.

### Task 6.6 — Start/Stop dialogs
- Goal: LIVE Start confirms; paper Start is one click; Stop copy depends on broker.
- Target files and symbols: `web/src/components/strategies/start-stop-button.tsx`.
- Steps:
  1. Props `broker` and `label` (`"<code> · <interval>"`); Stop uses `.btn-danger`; drop the inline red blocks.
  2. Live Stop: heading "Stop live strategy?", body "This stops real-money execution on Exness for <label>. Open positions will remain unchanged.", second line "To block new entries but keep the strategy warm, use Pause in the Exness strip."
  3. Paper Stop: "Stop paper strategy?", "This stops paper trading for <label>. Open paper positions will remain unchanged."
  4. Start on `exness`: same dialog, heading "Start real-money orders on Exness for <code>?", body "Real orders go to Exness within the daily loss cap and max lots shown in the Exness strip.", confirm "Start". Paper Start stays one click.
  5. Cancel left, confirm right, `moneyHint` chip just left of confirm; every button gets `title={moneyHint(...).title}`.
- Success criteria: no "live execution" text remains.
- Verify: `grep -rn "live execution" web/src` prints nothing.

### Task 6.7 — Config card: one chip, Delete in the footer
- Goal: Delete is separated from Start/Stop.
- Target files and symbols: `web/src/components/strategies/strategy-config-card.tsx` (`:70-91`, footer after the Sub ID row `:128-144`).
- Steps: header keeps one chip (`moneyHint(sub.broker, isRunning ? 'stop' : 'start')`) and the Start/Stop slot (pass `broker`, `label`); move Delete to a footer row (top border, right-aligned, own chip, `className="btn btn-danger"`, title `moneyHint(sub.broker, 'delete').title`; when disabled the title stays "Stop the strategy before deleting"); keep `window.confirm` and `disabled={isLoading || isRunning}`.
- Success criteria: no inline red style for buttons.
- Verify: `grep -rn "#ef5350" web/src/components/strategies` shows no button style (only the error box).

### Task 6.8 — Exness strip with the query and mutations inside
- Goal: the strip shows live state and offers Pause (one click) and Resume (confirm).
- Target files and symbols: create `web/src/components/strategies/exness-strip.tsx` (no separate hook file: one caller).
- Steps:
  1. Inside the file: a `useQuery` on `['safeguards']` calling `apiFetch('/api/v1/admin/safeguards')` with `refetchInterval: 5_000`; two `useMutation`s calling `apiPost` on `.../pause` and `.../resume`, each invalidating `['safeguards']`. The response type has the six fields from Phase 05.
  2. Always rendered: "Exness", `live_trading:` ON (red) / OFF (grey), `daily loss cap: <cap> USD` or `not set`, `max lots: <max_lots>` or `minimum lot`, "Entries paused" badge with `role="status"` while paused.
  3. Right end: one "Real money" chip and one slot. Not paused → Pause (`btn btn-warn`, one click). Paused → Resume (`btn-sm`) opens a dialog: heading "Re-enable real-money entries?", body "New Exness entries will be allowed again, within the <cap> USD daily loss cap and <max_lots> max lots.", Cancel, chip, `btn btn-danger` "Resume entries".
  4. Titles from `moneyHint('exness', 'pause' | 'resume')`. While GET is loading or failing show `—` and keep Pause visible.
- Success criteria: one file holds the strip, query and mutations.
- Verify: `test -f web/src/hooks/use-safeguards.ts; echo $?` prints `1`.

### Task 6.9 — Page layout and `+ New` title
- Goal: the strip sits above the desktop and mobile blocks.
- Target files and symbols: `web/src/components/strategies/strategies-page-layout.tsx` (`:123-231`); `web/src/components/strategies/strategy-list-sidebar.tsx:63-69`.
- Steps: replace the fragment with `<div className="strategies-page">`, `<ExnessStrip />` first, then the unchanged blocks; give `+ New` `title="Creates a paper subscription"`.
- Success criteria: strip first on both widths.
- Verify: `grep -c "ExnessStrip" web/src/components/strategies/strategies-page-layout.tsx` prints ≥ 1.

### Task 6.10 — Table test and dead-file deletion
- Goal: `moneyHint` is pinned; dead files are gone.
- Target files and symbols: create `web/src/lib/money-hint.test.ts`; delete the files confirmed in Task 6.1.
- Steps: table test: every action × broker has a non-empty title; `real` true for every `exness` action and for pause/resume, false for paper start/stop/delete; paper titles equal "Paper only, no real orders". Delete the files.
- Success criteria: none of the deleted files exist.
- Verify: `npm --prefix web test` exits 0; `grep -rn "StatusDot\|ForwardStatusBadge\|SubscriptionPanel\|useSubscriptions\b" web/src` prints nothing.

### Task 6.11 — [USER] manual UI check on a local stack
- Goal: the user confirms the dialogs and layout.
- Target files and symbols: local `.env` (repo root, gitignored), local Mongo `subscriptions` collection.
- Steps:
  1. Record whether `.env` exists (`test -f .env; echo $?`). If it does not, `cp ../pocketquant-config/local/all-local.env .env`.
  2. `just up`. Start the backend in the background with a local test token: `ADMIN_TOKEN=local-ui-check just be`; start `just fe` in the background. Record both PIDs and ports (41921, 5173).
  3. `curl -s http://localhost:41921/api/v1/subscriptions/` . If the list is empty, the user creates one paper subscription with `+ New` in step 4 first.
  4. Ask the user exactly: "Open http://localhost:5173/strategies. The admin token for this local check is `local-ui-check`. Check: (1) every row shows PAPER and one state pill, no dot; (2) the strip shows OFF and Pause; Pause asks for the token once, then shows Entries paused and Resume; Resume opens the confirm and Resume entries restores Pause; (3) paper Start is one click and paper Stop shows the paper copy; (4) Delete sits in the card footer and no two red buttons share a group; (5) at 375 px width the strip sits above the tabs and Pause is reachable without scrolling. Reply `step 6` when done so I switch one row to LIVE."
  5. On `step 6`: set one local subscription to `exness` with `uv run python -c "from pymongo import MongoClient; from pocketquant.core.config import get_settings as g; s=g(); assert 'localhost' in str(s.mongodb_url); db=MongoClient(str(s.mongodb_url))[s.mongodb_database]; print(db.subscriptions.update_one({'_id': '<id>'}, {'\$set': {'broker': 'exness'}}).modified_count)"` (prints `1`). Ask: "(6) the LIVE row shows the LIVE badge, red chips, the LIVE Start confirm and the live Stop copy. Reply `ui ok` or name the failing item."
  6. Restore: the same command with `'paper'` (prints `1`). Stop both background processes by PID. If `.env` did not exist in step 1, delete it. Leave Docker running.
- Success criteria: the user replied `ui ok`; the document is back to `paper`; no process left.
- Verify: the reply text equals `ui ok`; `curl -s -o /dev/null -w "%{http_code}" http://localhost:41921/health` prints `000`. A failing item → Failure Protocol with the user's text as the output.

### Task 6.12 — Gates and push
- Goal: green on `origin/develop`.
- Target files and symbols: `web/`.
- Steps: `npm --prefix web test`; `npm --prefix web run build`; `npm --prefix web run lint`; commit; `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin` (never print the token).
- Success criteria: all exit 0; lint shows no error in touched files.
- Verify: test and build exit 0; `npm --prefix web run lint 2>&1 | grep -E "exness-strip|money-hint|strategy-card|start-stop-button|strategy-config-card|strategies-page-layout|strategy-list-sidebar" | grep -c error` prints `0`; `test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `pushed`.

## Risk
- The strip breaks pane height (M/L). Task 6.4 uses one flex column; Task 6.11 checks both widths.
- Polling GET every 5 s (L/L): one in-memory read, same rate as the list.
- A dead-file deletion removes a live import (L/M). Task 6.1 re-greps; `tsc -b` fails on a missing import.
- No automated test of the LIVE Start confirm (M/L). `moneyHint(...).real` is pinned; the wiring is checked by the user.

## Rollback
Revert the commit (after deploy A: revert and fast-forward `master` [ASK]). The SPA holds no state.

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same
failure evidence to the user. Never continue by self-reasoning.

## Outcome (2026-10-21)
- Commit `e9d4e87` on `origin/develop`. `npm --prefix web test` 67 pass; build exit 0; lint 0 errors in touched files.
- Task 6.11: the user delegated the check ("you test it for me"). The agent drove a headless browser against the local stack and checked items 1-6 against backend state. The user's earlier "UI ok" predated a working subscription (3 browser Pause POSTs were 401), so it is not counted.
- Local run differences: Binance WS was unreachable, so the test subscription was written to local Mongo and its run state set by hand; Redis moved to port 46379 in the throwaway `.env` (53679 is in a Windows reserved range); `just be` fails under the PowerShell shell (`TZ=UTC`), so uvicorn ran directly.
- Accepted deviation: the LIVE Start heading names `<code> · <interval>`, not only `<code>`.
- Follow-up fixes found in the UI check, pushed to `develop`: `58d0bf5` (the config card read a row copy taken at click time, so Start/Stop stayed stale until re-select; the page now keeps the id and reads the polled list) and `906d6bb` (the app nav overflowed to 610 px at 375 px; it wraps to two rows below 768 px and the strategies/backtest pages fill with flex instead of a hard-coded 41px). Checked in the browser: no horizontal or vertical page overflow on `/`, `/strategies`, `/backtest`, `/monitor` at 375 px and 1440 px.
- `71ad8e7`: delete and create invalidated `['subscriptions', code]`, which does not match the list key `['subscriptions']`, so the list waited for the next 5 s poll; every mutation now invalidates `['subscriptions']` (browser check: the row left the list 20 ms after the DELETE returned).
