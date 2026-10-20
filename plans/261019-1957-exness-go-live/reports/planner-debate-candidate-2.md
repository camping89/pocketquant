# Planner debate candidate 2: real-money safety lens

Date: 2026-10-20. Input: `reports/debate-evidence-packet.md`, `plan.md`, phases 01–10, and the code listed below. [V] means checked in source on 2026-10-20. [I] means inference.

## Outcome
No real order is sent until every safeguard has been shown to work in prod at zero money: the pause on the real order path, sizing up to the lot grid, break-glass Pause without the tunnel, and the post-DST session calendar. Phases 07 and 08 ship with live off on a weekend, and they do not wait for E2. Phase 09, the first live order, waits for E2 row 4 (Mon 2026-11-02), so Phase 10 loses its DST check and keeps only observation and go-live. The code phases 01–06 are unchanged except for the Cloudflare dashboard wording. The binding decisions are kept, including D4 and a pause that resets on restart.

## 1. Phases in run order

### 01 Admin-token auth (B5). Unchanged.
- Goal: mutations return 401 without the token and 503 in production while it is unset. GET and SSE stay public.
- Verification: as in the current phase (`pytest tests/app_test/integration`, `npm --prefix web test`, build, ruff, pyright, lint-imports, ratchet).

### 02 Broker per subscription, one adapter (B6, B9). Unchanged.
- Safety note [V]: there is no update path that turns a paper subscription into `exness`, and `add_symbol` refuses `exness` while the flag is off. A live subscription can therefore only be created on purpose, with the token.

### 03 Access-point re-resolve (B8). Unchanged.

### 04 Safeguards, pause, leverage sizing, unexpected bars. Unchanged code. Two test additions:
- In `test_exness_broker_adapter.py`, while paused, a close for a held position is sent (already listed). Add one case: a `Safeguards` with `daily_loss_cap=None` still rejects opens with "EXNESS_DAILY_LOSS_CAP not set". This pins fail-closed behaviour through the new object (`exness_broker_adapter.py:243-245`).
- Add one case: with `max_lots=None`, the order is clamped to `volume_min`. This pins the verified behaviour at `exness_mappers.py:93`, so a missing or mistyped `EXNESS_MAX_LOTS` can never raise the size.

### 05 SPA badge, pill, strip, hints. Unchanged.
- The strip keeps Pause visible while GET fails (step 9). This is the safe-action rule, and it stays.

### 06 Cloudflare Tunnel service (round 1 and the code half of round 2). Wording delta only.
- Step 1 uses the 2026 dashboard path: Networking > Tunnels > Create > Cloudflared, then Routes > Add route > Published application `tunnel-test.pocketquant.xyz` → `http://web:80`. The old "Zero Trust → Networks → Public Hostname" menu was removed on 2026-10-12 (packet line 45).
- Pin an exact tag (for example `2026.10.2`). `tunnel ready` exists (packet line 44), so the fallback in step 3 is not needed.

### 07 Ship with live off. Changed entry condition, deploy window and one read-only check.
- Entry: phases 01–06 are on `develop`, and E2 row 2 (Sat 2026-10-24 03:00Z) has been recorded. **E2 closed is no longer required** (see Q1).
- Deploy window: a weekend market close (Sat 03:00Z to Sun 21:00Z, before the EURUSD reopen at 21:05Z), after an E2 row has been written and before the next one. If the code is late, use Sat 2026-10-31.
- Steps 1–4 are as in the current plan (config gate, push `master` gated, prod checks, `tunnel-test` checks).
- Step 5, new and read-only: run the Phase 09 step 1 stop-distance query now, against the paper `trades` of `hitnrun2`, and record it in `reports/round-trip.md`.
  - Pass: count > 0 and zero distances above 25 USD/oz.
  - Otherwise, stop and ask now. The user then has a week to decide, rather than finding out on the live day. `hitnrun2` caps its stop at 1% of entry, about 41.8 USD/oz on gold (`hitnrun2_strategy_service.py:37,102`), so stops between 25 and 41.8 are possible. Each one is rejected `below_min_lot`.
- Verification: the CI verdict reports `0 failures`; the settings line prints `False 25.0 0.01 1000.0 0.1 True`; `POST .../subscriptions/x/stop` returns `401`; `tunnel-test` returns 200.

### 08 Tunnel cutover. Same weekend as 07. Adds a break-glass drill and a runbook line.
- Steps 1–8 are as now. Step 1 uses Routes > Add route > Published application. It also deletes the leftover `tunnel-test` CNAME by hand, because removing a route does not remove it (packet line 46).
- New step 9, break-glass drill. This proves Pause without the tunnel, Cloudflare or the SPA:
  ```bash
  ssh -i $KEY $HOST 'T=$(grep ^ADMIN_TOKEN= /opt/pocketquant/.env | cut -d= -f2-); docker exec pocketquant-app curl -s -X POST -H "X-Admin-Token: $T" http://localhost:41921/api/v1/admin/safeguards/pause'
  ```
  - Pass: `GET` over SSH shows `entries_paused: true`. Then run the same command with `/resume` and get `false`. The `.env` path on the VPS is [UNVERIFIED]; take it from `deploy/vps/10-deploy.sh`.
  - The token is never printed.
- New step 10: add one block to the "Operator Runbook — break-glass" in `docs/deployment.md` (`:131`), titled "Stop real-money entries when the site is down". It gives the command above, plus "close the position in the Exness app". Its source is the drill, so the doc is proven before money exists.
- Verification: as now, plus the drill result in `reports/round-trip.md`.

### 09 Live round trip. Waits for E2 row 4. Steps reordered so each safeguard is proven before money.
- Entry: E2 row 4 (Mon 2026-11-02 03:00Z) is **PASS**. That row runs C5 with `3600 True` and C3 after DST, so the post-DST session calendar is proven. U1 holds: the user states a balance of at most 250 USD. D3 = A.
- Step 1: re-run the stop-distance check, with all paper trades up to 11-02.
- Step 2: margin check, unchanged, with `margin_percent` recorded raw.
- Step 3 **[gate]**: set the flag true and redeploy (`gh workflow run cicd.yml --ref master`). Verify that `GET /admin/safeguards` shows `live_trading: true`.
- Step 4, **pause before any `exness` subscription exists**: `POST .../pause`, then check `GET` for `entries_paused: true`. There is no gate, because Pause is the safe direction.
- Step 5 **[gate]**: delete the paper subscription on each triple, then create and start the `exness` subscription. Pass:
  - `broker: exness` and `running`;
  - one `exness.broker_connected` and one `exness.snapshot_reconciled`;
  - the SPA shows LIVE and "Entries paused".
- Step 6, the zero-money proof while paused. Wait for each strategy's first entry signal: about 8 market hours of `hitnrun2` warmup, and about 21 open hours for `engulfing`. Pass for each strategy:
  - `exness.order_rejected_presubmit reason=entries_paused`;
  - no `openPosition` in the log;
  - no `below_min_lot` for that signal.

  This proves, in prod and on the real path, that the sizer reaches the lot grid (`normalize_quantity` runs before `submit_order`, `strategy_app_service.py:405-415`) and that the pause gate holds. A `below_min_lot` here is a stop-and-ask. Baseline the balance and the deals since UTC midnight at the end of this step.
- Step 7 **[gate]**: Resume. Running the strategies one at a time is the user's choice (Risk 2). The first live entry follows.
- Step 8, round trip checks, as in the current step 6.
- Step 9, pause-while-open check, as in the current step 7. Resume is gated.
- Step 10, commission check (AC6), with an **asymmetric stop**. Let `realized_code = P − C`, which is what `_realized_today` computes (`exness_broker_adapter.py:266-277`), and `delta = balance_after − balance_before`.
  - If `delta < realized_code − 0.01`, the cap under-counts the loss (for example a swap or fee outside `_PNL_DEAL_TYPES`, `:59`). **Stop and report**, because this is unsafe.
  - If `delta ≥ realized_code − 0.01`, the cap is exact or conservative. It trips early, which is safe. Record the result and continue.
- Step 11: D4, as now. Pause if Phase 10 does not follow at once.

### 10 Observation and go-live. The DST check is removed (E2 row 4 did it).
- Step 1: observation rows, as now, for 5 trading days counted from the first Resume. Add the column `StartedAt changed since last row?`. If it changed while the intended state was paused, re-pause and record it.
- Step 2 **[gate]** before each Friday 20:30Z, decide the weekend hold (as the current step 2, without DST).
- Step 3 **[gate]**: go-live and the journal, as now. The journal cites E2 row 4 for DST.

## 2. Deltas against the current plan

| # | Delta | Reason | Evidence |
|---|---|---|---|
| Δ1 | Phase 07 needs E2 row 2 recorded, not E2 closed, and deploys only in a weekend window | The user already dropped the no-deploy freeze for E2; a restart only shortens a row's log window. C3 and C5 read stored bars and live sessions. Live is off, so no money is at stake | prev plan `phase-08-validation-...md:24,136`; packet lines 35-39 |
| Δ2 | Phase 09 waits for E2 row 4 PASS (2026-11-02) | Phase 09 deletes the paper subscriptions (unique triple), which would break E2's `running 2`. Waiting also keeps every live position out of the DST weekend, and the first order runs on a calendar proven after DST | `subscription_repository.py:102-106` (plan Phase 02 context); prev plan `phase-08...md:254,264` |
| Δ3 | Phase 10 drops its DST check; observation is dated from the first Resume | Row 4 C5 (`3600 True`) and C3 already cover it, and fixed dates that cannot hold are removed | packet line 40; prev plan `phase-08...md:221,264` |
| Δ4 | Phase 09 pauses before creating `exness` subscriptions, and needs one paused-signal rejection per strategy before Resume | It proves the pause gate and the sizing-to-lot-grid in prod at zero money. Today the pause is first proven while a real position is open (current step 7) | `strategy_app_service.py:405-415`; plan Phase 04 step 5 |
| Δ5 | Phase 08 adds an SSH break-glass Pause drill and a runbook block | After cutover the tunnel is the only public entry. A tunnel or Cloudflare outage would block SPA Pause, and the current rollback ladder has no path that avoids the tunnel | `plan.md:133-137`; `docs/deployment.md:131` |
| Δ6 | The AC6 stop becomes asymmetric | When the code double-counts commission, the cap trips early, which is safe. Only an under-count risks money. The current plan stops on the safe case | `exness_broker_adapter.py:266-277`; `phase-09...md:67-69` |
| Δ7 | The stop-distance check also runs in Phase 07 | It finds the `below_min_lot` gold problem about a week before the live day. Stops up to 1% of entry (about 41.8 USD/oz) are legal for `hitnrun2` | `hitnrun2_strategy_service.py:37,102` |
| Δ8 | Two Phase 04 tests pin fail-closed behaviour: no cap rejects, and no max-lots means the minimum lot | These are the two config typos that matter. The second is a verified non-issue, and the test keeps it that way | `exness_broker_adapter.py:107,243-245`; `exness_mappers.py:93` |
| Δ9 | Phases 06 and 08 use the 2026 dashboard path and remove the `tunnel-test` CNAME by hand | The old menu was removed on 2026-10-12, and removing a route leaves its CNAME | packet lines 45-46 |
| Δ10 | Phase 10 rows check whether `StartedAt` changed against the intended pause | A restart clears the pause silently, and nothing alerts | plan Phase 04 step 2; packet line 9 |
| Δ11 | The rollback ladder gains "Pause over SSH" (step 1b). Step 4 (flag false) requires a flat account first | With the flag off, no adapter is built, so a venue SL/TP close is not recorded. That is a bookkeeping gap, not a money loss | `plan.md:137`; `broker_factory.py:87-88` (plan Phase 04 context) |

The plan's unresolved question "Does hitnrun2 move its SL?" closes as **no** (packet line 24). The step 1 [UNVERIFIED] note is removed.

## 3. Answers to the open questions

**Q1. Must Phase 07 wait for E2?** No. Ship it with live off in a weekend window after an E2 row has been recorded, ideally Sat 2026-10-24.
- Live is off, so no money is at stake.
- The user already removed the E2 deploy freeze (prev plan `phase-08...md:24,136`).
- What a deploy costs E2: C1's log window gets shorter; paper positions and warmup reset; nothing E2 grades is lost.
- What waiting costs: Phases 07 and 08 slip to after 11-02. The first live order slips by the same amount, and the tunnel and cutover risk then lands in the same week as the first real money.

**Q2. Best order for the earliest safe first live trade.** Code 01–06 runs to about Fri 10-23. Phases 07 and 08 ship on the weekend of 10-24/25 with live off. Phase 09 starts after E2 row 4 passes on Mon 11-02.
- The earliest live entry is about 8 market hours later (`hitnrun2` warmup, `hitnrun2_strategy_service.py:92-94`), plus the paused-signal proof in Δ4.
- The faster alternative is a round trip in the week of 10-26. It saves about one week. It costs E2's `running 2`, it means holding or flattening around the DST weekend on an unproven post-DST calendar, and the first live order would precede the last data check.
- I recommend waiting. At 250 USD, a week of delay has no money cost.

**Q3. SSE heartbeat?** Not in scope.
- No safety control rides on SSE. Pause and Resume are POST, and the strip polls GET every 5 s (Phase 05 step 4).
- Quiet streams are already cut at 125 s today [I, packet line 55], and the browser `EventSource` reconnects by itself [I].
- Record it as a follow-up. The Phase 08 SSE check should use a busy stream (XAUUSD 1m during market hours) so it does not hit the 125 s cut.

**Q4. Is anything in 04–06 bigger than needed?** Mostly no.
- `Safeguards` has real readers today: the adapter, the factory, reconcile and the route. The pause needs one shared object, so it meets the second-caller rule.
- Possible trim: Phase 04 step 4 deletes `default_broker_config` keys and rewires the factory. Keeping `daily_loss_cap` and `max_lots` as adapter args and passing only `Safeguards` for the pause would be less churn. It would also leave two sources for the GET values, so I keep the current design.
- Phase 06 is minimal.
- Phase 05's size comes from binding UI decisions.

## 4. Risks ranked by money at stake
Account ≤ 250 USD, 0.01 lot. Gold: 1 oz per 0.01 lot, so the loss at the stop is the stop distance in USD, at most 25. EURUSD: 1000 units, so the loss at the stop is at most 25 USD.

1. **Pause cleared by a restart (deploy, crash, VPS reboot) while the user believes entries are paused.** Up to one capped day per missed restart: about 25 USD realized, plus open risk (Risk 2). Likelihood M.
   - Mitigations: no deploy while paused or positioned (kept); re-pause right after any deploy that is meant to stay paused; the `StartedAt` column (Δ10).
   - The warmup after a restart gives at least 8 market hours (`hitnrun2`) or about 21 (`engulfing`) before any entry. Checking at least every 8 h while paused therefore catches it in time [I].
   - For an absence longer than that, stop the subscriptions. That is a hard stop, and it costs a re-warm.
2. **The daily cap is realized-only and checked at open.**
   - Two open positions are not counted. The worst day is about 24.99 realized + 25 + 25 ≈ 75 USD (30% of the account) before gaps (`exness_broker_adapter.py:255-277`). Likelihood L, impact H.
   - The cap is a user decision and is kept. Options: accept it; or round-trip one strategy at a time in Phase 09; or later count open SL risk in the cap (new code, ask first).
3. **Gap through the SL** (weekend, news, DST reopen). This is unbounded in principle; for example, a 60 USD gold gap costs 60 USD. Mitigations: the weekend gate (Phase 10 step 2); Δ2 keeps the first live position out of the DST weekend.
4. **Cap under-counts real costs** (commission netting, swap on the close deal, fees outside `_PNL_DEAL_TYPES`). The cap would trip late by the uncounted amount, a few USD per trade [I]. Mitigation: Δ6 stops only on this direction.
5. **Restart while positioned.** The strategy state (`_open_direction`) is not restored; no restore path was found in `strategy_app_service.py` or reconcile [V grep].
   - After warmup, an opposite-direction signal of equal quantity (always true at 0.01 lot) is sent as `closePosition` (`exness_broker_adapter.py:197-212`). The position closes early.
   - The strategy then keeps `_open_direction` set, because the close fill has its own side (`hitnrun2_strategy_service.py:125-128`). It never enters again until the next restart [I].
   - Money: an early close only; the venue SL bounds the rest. Mitigation: the existing no-deploy-while-positioned rule; after an unplanned restart while positioned, stop and ask.
6. **Tunnel or Cloudflare outage blocks SPA Pause.** Trading continues within the caps. Mitigation: the Δ5 SSH drill and the runbook block; closing in the Exness app works with no tunnel.
7. **Margin.** The margin for 0.01 lot of gold at 1:1000 is about 4.2 USD, and even at 1:200 it is about 21 USD. A venue rejection becomes CANCELLED and loses no money. Phase 09 step 2 is kept.
8. **Flag off while positioned.** No adapter is built, so the venue close is not recorded (bookkeeping only). Mitigation: Δ11.
9. **No money: per-bar churn.** While paused, at the cap or `below_min_lot`, `hitnrun2` re-arms on each rejection (`:130-132`). It re-signals every 1m bar while its condition holds, which writes one REJECTED order and one WARNING per bar. This is pre-existing for `below_min_lot`. Record the counts in the observation rows; do not fix it in this plan.

## Unresolved questions
- Risk 2: does the user accept a worst day of about 75 USD with two concurrent positions, or should the Phase 09 round trips run one strategy at a time?
- What is the exact `.env` path on the VPS for the Δ5 drill? It is to be read from `deploy/vps/10-deploy.sh` at Phase 08.
- Risk 5 (a stuck strategy after a restart while positioned) is inference from code reading, with no test. Should it be a follow-up plan item?

Status: DONE
Summary: Candidate 2 keeps the code phases 01–06 and ships 07 and 08 with live off on the 10-24/25 weekend without waiting for E2. It holds the first live order until E2 row 4 passes on 11-02, and proves the pause and sizing in prod at zero money (start paused) plus an SSH break-glass Pause before any real order.
Concerns: The cap is realized-only, so two concurrent positions allow a worst day of about 75 USD, and a restart silently clears the pause. Both are bounded but need the user's eyes.
