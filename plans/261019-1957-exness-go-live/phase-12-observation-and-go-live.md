---
phase: 12
title: "Observation and go-live (re-runnable daily)"
status: pending
priority: P1
effort: ~15 min per run
dependencies: [11]
---

# Phase 12: Observation and go-live (re-runnable daily)

## Context
- User decision: observation is re-runnable daily and needs five clean rows on distinct Mon-Fri UTC days, counted from the latest `resumed_at` in `plans/261019-1957-exness-go-live/reports/round-trip.md` (a strategy added later gets its own five days). The go-live gate is the user's.
- Each run adds at most one row per UTC day to `plans/261019-1957-exness-go-live/reports/live-observation.md`. A row compares against the previous row's UTC time (`SINCE`); the first row uses the latest `resumed_at`.
- Live ids are every subscription in `GET /api/v1/subscriptions/` with `"broker":"exness"`, not the markdown.
- The pause is stored and survives a restart (Phase 05). A restart resets strategy warmup and log counts (they read `docker logs --since`). It is not a failure by itself; the row records it.
- While a Phase 11 run is open (a `## Live run` section without `round_trip: DONE`), Phase 11 owns the pause (intended paused until its `resumed_at`). This phase then exits at the entry gate and never resumes.
- User decision 2026-10-21 00:43: Task 11.12 recommends `keep on` after a clean round trip, so the rows normally observe a trading system under the 25 USD daily cap. When the user chose `pause` instead, the rows record a paused system (`new_trades 0`) until Task 12.6 resumes entries.
- US DST ends Sun 2026-11-01. The Exness session model is in `America/New_York` (`core/infra/calendars/exness_session_calendar_adapter.py:7-10,34`), so UTC session edges move one hour later; the XAUUSD Sunday reopen moves from 22:01:30Z to 23:01:30Z. User decision 2026-10-20 20:20: the `unexpected` bar counts and the DST reopen check are record only; they never fail a row.
- Stop events: `exness.position_unmapped`, `exness.unknown_request_fill`, `exness.operation_unresolved`, `exness.position_missing_close_deal`, `exness.event_handler_failed`. Also stop on any `below_min_lot`, any `order_quantity_below_broker_minimum` for a live id, and any `exness.order_rejected` (`plan.md` "Stop and report").
- A bar signal ends in one line with `strategy_id` (the subscription id, set by reconcile): `signal_rejected_by_risk`, `zero_position_size`, `order_quantity_below_broker_minimum` or `signal_processed` (`engine/strategy/strategy_app_service.py:379,402,408,420`), or `strategy_on_bar_error` when it raises. A `signal_processed` line follows every submitted order, rejected ones included. Tick-triggered orders log no signal line, so for a tick strategy orders can exceed signals. The `signals / orders` column counts those lines against the orders created for the live ids (user decision 2026-10-20 20:50, record only).
- Scripts that call Exness use `get_settings().model_copy(update={"exness_rate_fraction": 0.2})` and clamp the deal window with `ExnessClient.deals_window_days()` (`exness_client.py:370-372`).
- Every planned restart follows the "Restart while live" runbook (`docs/deployment.md`). A local backend against prod Mongo/Redis runs only with `ENABLE_JOBS=false` (plan rule).

## Gates in this phase
[ASK] = stop and ask; lead with the recommended reply and its reason, then state the listed facts; only an explicit yes counts; "no" or "wait" ends the phase with the NOT_YET block. [USER] = the user acts and replies with the stated token. No earlier approval counts.
- [ASK] 12.4 weekend hold (Fridays with an open position). [ASK] 12.6 go-live.

## Entry gate
Run first. On a miss: edit nothing, spawn no `kongming`, leave the phase pending, and end with:
```
Status: BLOCKED
NOT_YET: <reason>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261019-1957-exness-go-live --from 12 after <UTC time>
```
- `grep -c "round_trip: DONE" plans/261019-1957-exness-go-live/reports/round-trip.md` prints ≥ 1 (else `NOT_YET: no live round trip recorded yet; run --from 11 --to 11`).
- `grep -c "^## Live run" plans/261019-1957-exness-go-live/reports/round-trip.md` equals the `round_trip: DONE` count (else `NOT_YET: a Phase 11 run is in progress; finish it with --from 11 --to 11`).
- `plans/261019-1957-exness-go-live/reports/live-observation.md` has no row for today's UTC date (else `NOT_YET: today's row exists`, resume after tomorrow 03:00Z).
- `git status --porcelain -- src web deploy tests scripts docs` prints nothing.

## Tasks
Code blocks below are indented for Markdown. Before running one, remove only the common leading indentation of the block (keep the Python indentation inside it), so each closing `EOF` starts at column 0. The shell keeps no variables between commands: every command sets `HOST` itself. `<GET safeguards>` means `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" "docker exec pocketquant-app curl -s http://localhost:41921/api/v1/admin/safeguards"`. The admin pause call is `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'docker exec -i pocketquant-app sh -s'` with stdin `curl -s -X POST -H "X-Admin-Token: $ADMIN_TOKEN" http://localhost:41921/api/v1/admin/safeguards/pause` (resume: `.../resume`).

### Task 12.1 — SSH setup and the intended state
- Goal: know `SINCE` and whether entries should be paused.
- Target files and symbols: `.cache/ssh/vps_key` (deleted at every exit); `plans/261019-1957-exness-go-live/reports/round-trip.md`; `plans/261019-1957-exness-go-live/reports/live-observation.md` (create with the header row below if absent).
- Steps:
  1. `mkdir -p .cache/ssh && tr -d '\r' < ../pocketquant-config/vps/default/id_rsa > .cache/ssh/vps_key && chmod 600 .cache/ssh/vps_key`.
  2. `SINCE` = the UTC time of the last row, else the latest `resumed_at`.
  3. Intended paused = the newest of: the last `after round trip:` line, a later `go-live` or `weekend hold` note in `plans/261019-1957-exness-go-live/reports/live-observation.md`. `paused` or weekend choice 2 → paused; otherwise not paused.
  4. Header if creating the file: `| UTC date | StartedAt | restarted | paused (intended/actual) | CB | stop events | below_min / order_rejected | rejected_async | cap_reached | reconnecting | stuck | close deals / new trades | paused rejections | signals / orders (record) | unexpected XAU/EUR (record) | DST reopen (record) |` and the separator row.
- Success criteria: two values known.
- Verify: no verification needed (Task 12.3 compares).

### Task 12.2 — Collect the row
- Goal: one row of facts.
- Target files and symbols: prod logs, Mongo, Exness, integrity check.
- Steps:
  1. Logs (`<SINCE>` as ISO):
     ```bash
     HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r')
     ssh -i .cache/ssh/vps_key "$HOST" 'bash -s' <<'EOF'
     S=<SINCE>
     docker inspect -f '{{.State.StartedAt}}' pocketquant-app
     IDS=$(docker exec pocketquant-app python -c "import json,urllib.request as u;[print(x['id']) for x in json.load(u.urlopen('http://localhost:41921/api/v1/subscriptions/')) if x['broker']=='exness']")
     L=$(docker logs --since "$S" pocketquant-app 2>&1)
     for e in exness_ws.circuit_breaker_open exness.position_unmapped exness.unknown_request_fill exness.operation_unresolved exness.position_missing_close_deal exness.event_handler_failed exness.order_rejected_async exness.daily_loss_cap_reached exness_ws.reconnecting; do echo "$e $(echo "$L" | grep -c "$e")"; done
     echo "stuck $(echo "$L" | grep data_lag.state_changed | grep EXNESS | grep -c stuck)"
     echo "below_min $(echo "$L" | grep -c below_min_lot) $(echo "$L" | grep order_quantity_below_broker_minimum | grep -cF "$IDS")"
     echo "order_rejected $(echo "$L" | grep -cE 'exness\.order_rejected[^_]')"
     echo "signals $(echo "$L" | grep -E 'signal_processed|signal_rejected_by_risk|zero_position_size|order_quantity_below_broker_minimum' | grep -cF "$IDS")"
     EOF
     ```
  2. State (fill `SINCE`):
     ```bash
     HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r')
     ssh -i .cache/ssh/vps_key "$HOST" 'docker exec -i pocketquant-app python -' <<'EOF'
     import asyncio, json, os, urllib.request
     from datetime import UTC, datetime, timedelta
     from pymongo import MongoClient
     from pocketquant.core.config import get_settings
     from pocketquant.core.infra.exness.exness_client import ExnessClient
     API, SINCE = "http://localhost:41921/api/v1", datetime.fromisoformat("<SINCE ISO>")
     s = get_settings(); db = MongoClient(str(s.mongodb_url))[s.mongodb_database]
     IDS = [x["id"] for x in json.load(urllib.request.urlopen(API + "/subscriptions/")) if x["broker"] == "exness"]
     def post(path, body):
         req = urllib.request.Request(API + path, data=json.dumps(body).encode(),
             headers={"Content-Type": "application/json", "X-Admin-Token": os.environ["ADMIN_TOKEN"]})
         return json.load(urllib.request.urlopen(req))
     print("live_ids", IDS)
     print("paused", json.load(urllib.request.urlopen(API + "/admin/safeguards"))["entries_paused"])
     print("open", db.positions.count_documents({"subscription_id": {"$in": IDS}, "is_closed": False}))
     print("new_trades", db.trades.count_documents({"run_id": {"$in": IDS}, "exit_time": {"$gte": SINCE}}))
     print("paused_rejections", db.orders.count_documents({"subscription_id": {"$in": IDS}, "status": "rejected", "created_at": {"$gte": SINCE}}))
     print("orders", db.orders.count_documents({"subscription_id": {"$in": IDS}, "created_at": {"$gte": SINCE}}))
     for sym in ("XAUUSD:EXNESS", "EURUSD:EXNESS"):
         print("unexpected", sym, post("/market-data/integrity/check", {"symbol": sym, "interval": "1m", "days_back": 1})["unexpected_count"])
     async def deals():
         c = ExnessClient(s.model_copy(update={"exness_rate_fraction": 0.2}))
         try:
             floor = datetime.now(UTC) - timedelta(days=await c.deals_window_days())
             params, closes = {"from": max(SINCE, floor).isoformat(), "limit": 200}, 0
             while True:
                 body = await c.call("getDealsHistory", params=params)
                 closes += sum(it["deal"].get("type") == "close" for it in body.get("items", []))
                 if not body.get("has_more") or not body.get("next_cursor"):
                     break
                 params = {"cursor": body["next_cursor"], "limit": 200}
             print("close_deals", closes)
         finally:
             await c.close()
     asyncio.run(deals())
     EOF
     ```
  3. DST reopen (record only), only on the first row dated 2026-11-02 or later: `count_documents` of `bars` with `symbol "XAUUSD:EXNESS"`, `interval "1m"` and `datetime` in [2026-11-01T22:00Z, 2026-11-01T23:00Z) (expect `0`) and in [2026-11-01T23:01Z, 2026-11-02T00:00Z) (expect ≥ 1); and `orders` with `subscription_id` in the live ids, `symbol` `XAUUSD:EXNESS` and `created_at` in [2026-11-01T21:00Z, 2026-11-01T23:01Z) (expect `0`). Write `ok` when all three match, else the three numbers. Other rows: write `—`.
- Success criteria: every column has a value.
- Verify: step 1 prints 14 lines; step 2 prints `live_ids`, `paused`, `open`, `new_trades`, `paused_rejections`, `orders`, two `unexpected` lines and `close_deals`.

### Task 12.3 — Judge and append the row
- Goal: a clean row, or a stop.
- Target files and symbols: `plans/261019-1957-exness-go-live/reports/live-observation.md`.
- Steps:
  1. `restarted` = StartedAt differs from the previous row's (or from the last StartedAt recorded in `plans/261019-1957-exness-go-live/reports/round-trip.md` for the first row).
  2. If intended paused and actual `paused False`: pause now (admin call), set the cell to `paused/re-paused` (the pause is stored, so someone resumed it).
  3. If `restarted` and `open` > 0: stop and report (an unplanned restart while an `exness` position is open).
  4. Append the row. The `signals / orders` cell is `<signals>/<orders>` (signals = strategy entry decisions logged for the live ids, orders = orders created for them, any status). `signals / orders`, `unexpected` and DST cells are recorded as they are.
- Success criteria: the row is appended.
- Verify: CB `0`; every stop event `0`; `below_min 0 0` and `order_rejected 0`; `close_deals` equals `new_trades`; actual paused equals intended (after a re-pause). A stop event, a below-minimum count or an `order_rejected` count → stop and report; any other miss → Failure Protocol. `signals / orders`, `unexpected` and the DST cell never fail the row.

### Task 12.4 — [ASK] Weekend hold (Fridays only)
- Goal: the user decides whether an open position stays over the weekend.
- Target files and symbols: `plans/261019-1957-exness-go-live/reports/live-observation.md` (a `weekend hold:` note).
- Steps: if today is Friday (UTC) and `open` > 0, ask: "Recommended: 2 (pause entries; the open position keeps its venue SL/TP, and nothing new opens into the Sunday gap). An Exness position is open going into the weekend. Options, softest first: (1) keep everything running; (2) Pause entries (blocks opens, keeps strategies warm, the open position keeps its venue SL/TP); (3) stop the live subscriptions (the position keeps its SL at the venue). <If the date is 2026-10-30: US DST ends Sun 2026-11-01; the session model shifts +1 h, proven in code, not yet in prod.> Reply 1, 2 or 3." Apply the choice (2 → admin pause; 3 → admin `POST /api/v1/subscriptions/<id>/stop` per live id) and append `weekend hold: <choice> <UTC>`. Not Friday, or `open` = 0 → skip.
- Success criteria: a note when asked.
- Verify: choice 2 → `<GET safeguards>` contains `"entries_paused":true`; choice 3 → each live id shows `actual_state` `stopped`; skip → no verification needed.

### Task 12.5 — Count clean rows
- Goal: decide between `NOT_YET` and the go-live gate.
- Target files and symbols: `plans/261019-1957-exness-go-live/reports/live-observation.md`.
- Steps: count rows dated on or after the latest `resumed_at`, on distinct Mon-Fri UTC dates, that passed Task 12.3. Fewer than 5 → commit the row (`docs(plans): add a live observation row`), `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin` (never print the token), `rm -f .cache/ssh/vps_key`, and end with `NOT_YET: <n> of 5 observation rows; re-run tomorrow`, resume after the next UTC day 03:00Z.
- Success criteria: a count.
- Verify: no verification needed (the count decides).

### Task 12.6 — [ASK] Go-live and the journal
- Goal: AC11.
- Target files and symbols: create `docs/journals/<YYYY-MM-DD>-exness-go-live.md`.
- Steps:
  1. Re-read `plans/261019-1957-exness-go-live/reports/round-trip.md`: if any `## Live run` section lacks `round_trip: DONE`, end with `NOT_YET: a Phase 11 run is in progress` and never resume.
  2. Ask: "Recommended: <`yes` (all five rows passed and no stop event) | `no` (<what did not pass>)>. Five clean observation rows since <resumed_at>. AC6: <lines from round-trip.md>. Recorded only: signals / orders per row <cells>; unexpected bars <non-zero cells or none>; DST reopen <ok on date | numbers | not yet, before 2026-11-02>. Latest E2 row: <`grep -E '^\| [0-4]( re-run)? \| 2026' plans/archive/261009-0858-exness-venue-lean-sync-refactor/phase-08-validation-spread-backtests-paper-week.md | tail -1`>. Open follow-ups: worst day ≈ 25 + 25 × open positions USD (cap is realized-only); restart while positioned loses strategy state; AC6 over-count if recorded. Declare go-live? (This resumes entries if they are paused.)"
  3. `no` → end with `NOT_YET: the user deferred go-live`, resume after tomorrow 03:00Z.
  4. On yes: if paused, admin `POST .../resume` and check `<GET safeguards>` shows `"entries_paused":false`. Append `go-live: <UTC>` to `plans/261019-1957-exness-go-live/reports/live-observation.md`.
  5. Journal (plain English, AS-IS, short): the date; the live strategies and their subscription ids; the binding values (250 USD, 0.01 lot, leverage 1000, cap 25, risk 0.10); the stop-distance preflight lines and AC6 lines; the DST status; links to `plans/261019-1957-exness-go-live/reports/`.
  6. Commit `docs(journals): record the exness go-live`; `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin`; `rm -f .cache/ssh/vps_key`.
- Success criteria: journal exists; entries on.
- Verify: `ls docs/journals/*-exness-go-live.md` lists one file; `<GET safeguards>` (run before the key is removed) contains `"entries_paused":false`; `test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `pushed`.

## Exit rule
Before any `NOT_YET` exit or a stop after Task 12.1, run `rm -f .cache/ssh/vps_key`.

## Risk
- The session model is wrong after DST (M/M): orders in a closed hour are rejected by the venue (CANCELLED) or bars are skipped. The DST cell and `unexpected` record it; the go-live question names it; a venue rejection already stops the row (`order_rejected`).
- Weekend gap through the SL (M/M): Task 12.4.
- Paused found unpaused (L/M): each row re-pauses when intended and records it.
- A strategy that never trades shows clean rows (M/L): `below_min` stops the row on skipped entries; the `signals / orders` and `new_trades` cells show activity to the user at go-live (signals with no orders point at risk or sizing rejections).

## Rollback
Use `plan.md` "Rollback" and the "Restart while live" runbook (`docs/deployment.md`). Declaring go-live changes no code or config.

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
