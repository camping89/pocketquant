# Planner debate candidate 1: KISS and minimal change

Lens: fewest phases, fewest prod restarts, least new code, every binding decision kept.
[V] = verified in source or a plan file on 2026-10-20. [I] = inference.

## Outcome in one paragraph
Nine phases instead of ten. Two `master` pushes, and no config-only redeploy (today: two pushes plus the flag redeploy in Phase 09 step 3). Both restarts happen before any `exness` subscription exists. After the first live subscription, the plan contains no deploy at all, so "a restart clears the pause" cannot be triggered by the plan itself. Phase 06 (ship) waits for the latest E2 row to pass, not for E2 to close. The live phase waits for E2 row 3 (Mon 2026-10-26). E2 row 4 and the DST check run as one check on Mon 2026-11-02. With that, the dated observation window (to Fri 10-30) and the DST check hold again.

## 1. Phase list (file order = run order)

### 01 Admin-token auth on every mutation route (B5). Unchanged from the current plan.
- Files, steps, validation: current `phase-01-admin-token-auth.md`.
- Gate: none (develop push only).

### 02 Broker per subscription, one Exness adapter per process (B6, B9). Unchanged.
- Files, steps, validation: current `phase-02-subscription-broker-selection.md`.

### 03 Access-point re-resolve (B8). Unchanged.
- Files, steps, validation: current `phase-03-access-point-re-resolve.md`.

### 04 Safeguards, entry pause, leverage-aware sizing, unexpected-bar count (B4, B11). One small delta.
- Everything as in the current phase 04, except step 7. Reconcile does not take the `Safeguards` object. It gets one keyword `exness_risk: RiskConfig | None = None`. DI (`app/di/services.py:174-187`) builds it once from the `Safeguards` object: `RiskConfig(leverage=s.leverage, risk_per_trade=s.risk_per_trade)`. `_ensure_instances` passes `risk=self._exness_risk` when `sub.broker == "exness"` and it is set. Every other subscription gets `RiskConfig()`.
- Test change: `test_subscription_broker_selection.py` builds reconcile with `exness_risk=RiskConfig(leverage=1000, risk_per_trade=0.10)`. The assertions stay the same.
- Validation: same commands as the current phase 04.

### 05 SPA: badge, state pill, Exness strip, hints (B11). One optional delta.
- Everything as in the current phase 05. Optionally, the safeguards query and the pause/resume mutations live inside `exness-strip.tsx` instead of a new `hooks/use-safeguards.ts`, because the strip is their only consumer (CLAUDE.md: a second real caller is needed first).
- Validation: same as the current phase 05.

### 06 Tunnel rounds 1 and 2, then ship with live off (B7, B10). This merges the current 06 and 07.
- Goal: develop holds 01–05 plus the `cloudflared` service. Prod runs it with `ADMIN_TOKEN`, the caps and the sizing keys, and the flag is still false. `tunnel-test` serves the SPA and a long SSE stream through the tunnel, while the old path keeps serving.
- Files: `deploy/compose.prod.yml`, `deploy/vps/11-verify.sh`, `docs/deployment.md`. Outside the repo: `pocketquant-config/vps/default/.env` (gated) and the Cloudflare dashboard (user).
- Steps:
  1. **[USER]** Dashboard path (2026): Networking > Tunnels > Create tunnel (Cloudflared), named `pocketquant-prod`. Copy the token but do not run the install command. Then Routes > Add route > Published application: `tunnel-test.pocketquant.xyz` → `HTTP` `web:80`. Paste `TUNNEL_TOKEN=` into `pocketquant-config`. The Zero Trust Free plan may ask for a card (research).
  2. Agent: `grep -c "^TUNNEL_TOKEN=." ../pocketquant-config/vps/default/.env` prints `1`.
  3. Code: the `cloudflared` service from the current phase-06 step 4, with an exact tag such as `2026.10.2`. The `tunnel ready` healthcheck is verified (research, PR #1135), so drop the current step-3 fallback branch. Add the container to `CONTAINERS` and `HEALTH_CONTAINERS` in `11-verify.sh`, and update the `docs/deployment.md` container list and env table. Push `develop`.
  4. Release gate on `develop`: `just test` (only the 4 known `tzset` failures), `uv run lint-imports`, `uv run python scripts/code_metrics.py --ratchet`, `npm --prefix web test`, `npm --prefix web run build`.
  5. **[Stop-and-ask]** Config: `ADMIN_TOKEN`, `EXNESS_DAILY_LOSS_CAP=25`, `EXNESS_MAX_LOTS=0.01`, `EXNESS_LEVERAGE=1000`, `EXNESS_RISK_PER_TRADE=0.10`. `EXNESS_LIVE_TRADING` stays absent. Commit and push `pocketquant-config`.
  6. **[Stop-and-ask]** `git push origin develop:master`, then `gh run watch <id> --exit-status`. Do it on a weekday, so the SSE check sees market traffic.
  7. Verify: run every check in the current phase-07 step 4 (settings one-liner prints `False 25.0 0.01 1000.0 0.1 True`; safeguards GET; a POST returns 401; all subscriptions read `paper`; `unexpected_count` appears; `cloudflared` is `(healthy)`; `tunnel-test` returns 200; the old site returns 200; SPA token prompt). Add one check: `curl -s -N --max-time 150 https://tunnel-test.pocketquant.xyz/api/v1/market-data/bars/stream/XAUUSD%3AEXNESS?interval=1m | grep -c "^data:"` prints ≥ 1 during market hours.
  8. E2 rows from now on add the `X-Admin-Token` header to C3. The previous plan already says so (`plans/261009-0858-.../phase-08-...md:185`).
- Validation: the CI verdict reports `, 0 failures)`, and every value in step 7 matches.
- Entry: 01–05 are on `develop`, and the latest scheduled E2 row is `PASS`.

### 07 Tunnel cutover (round 3) and the live flag in one deploy. This merges the current 08 with Phase 09 step 3.
- Goal: `pocketquant.xyz` and `www` serve only through the tunnel, origin `:80` is closed, and `EXNESS_LIVE_TRADING=true` takes effect in the same restart. No `exness` subscription exists yet, so the flag sends nothing.
- Files: as in the current phase 08 (`compose.prod.yml`, `11-verify.sh`, `docs/deployment.md`). Config: remove `WEB_PORT` and add `EXNESS_LIVE_TRADING=true`.
- Steps:
  1. **[USER]** Delete `CNAME www`, then add the `www` route at once. Then delete `A @` and add the `@` route (apex CNAME flattening works). Delete the leftover `tunnel-test` route and its DNS CNAME by hand, because removing a route keeps the CNAME (research). Doing www first exposes the less-used name to the gap first [I].
  2. Agent, with port 80 still open: `/`, `www`, and `/api/v1/admin/safeguards` each return 200, and `cloudflared` logs show no `error`. On a failure the user restores the record, and the phase stops.
  3. Code: current phase-08 steps 3–5 (drop `web` `ports:`, change the `11-verify.sh` probe to `http://web:80` from inside `pocketquant-app`, delete the port section, update the docs). Push `develop`.
  4. **[Stop-and-ask]** Two config edits in one commit: remove `WEB_PORT`, and set `EXNESS_LIVE_TRADING=true`. These are two separate approvals within one stop.
  5. **[Stop-and-ask]** `git push origin develop:master`, then watch the run.
  6. Verify:
     - `http://<vps-ip>:80/` is refused (curl exit 7);
     - `https://pocketquant.xyz/` and `/api/v1/subscriptions/` return 200;
     - the settings one-liner prints `True 25.0 0.01 1000.0 0.1 True`;
     - safeguards GET shows `live_trading: true` and `entries_paused: false`;
     - `GET /api/v1/subscriptions/` still shows only `paper`;
     - `grep -rn "WEB_PORT" deploy docs/deployment.md` prints nothing.
- Entry: phase 06 has passed. Prefer Sat 2026-10-24, after E2 row 2. The markets are closed then, so no paper position is open [I, from the session constants].
- Side effect: the deep backfill refuses while the flag is true (`scripts/backfill/provider_bars.py:76-77`). No step in this plan needs it, and C3 repairs go through `integrity/repair`.

### 08 Live minimum-lot round trip per strategy. This is the current 09 without step 3.
- Entry: phase 07 has passed, E2 row 3 (Mon 2026-10-26 03:00Z) is `PASS`, U1 holds (the balance is stated), and D3 is answered.
- Steps: current phase-09 steps 1, 2, 4–9, with these changes:
  - Step 1 drops the `[UNVERIFIED]` note. The SL is set once at signal time (`hitnrun2_strategy_service.py:151`, `engulfing_strategy_service.py:170`), so `trades.sl_price` minus entry is the entry stop distance.
  - Step 3 is gone, because the flag is already true.
  - Step 5 records the two new `exness` subscription ids in the E2 results table as the row-4 `IDS`.
- Validation: as in the current phase 09.
- Rule: no `master` push and no redeploy from this phase until go-live. The plan schedules none.

### 09 Observation, DST check (= E2 row 4), go-live. This is the current 10, deduplicated.
- Step 1: observation from the first live entry to Fri 2026-10-30 ~20:30Z, one row per day as in the current phase 10.
- Step 2: the weekend gate, unchanged.
- Step 3: Mon 2026-11-02 03:00Z. Run E2 row 4 once (C5 `3600 True`, C1, C3 1m/2 and 1h/7, C2 with `IDS` = the `exness` ids). Then add the current phase-10 checks that row 4 does not cover: an XAUUSD bar after 23:01:30Z and none in 22:00–23:00Z; no order rejected for a closed market; `unexpected == 0`. One pass closes both E2 (T8.8) and this check.
- Step 4: **[Stop-and-ask]** go-live and the journal entry, unchanged.

## 2. Deltas versus the current plan

| # | Delta | Reason | Evidence |
|---|---|---|---|
| Δ1 | Merge the current 06 into 07 (new 06) | The 06 code is about 25 lines of compose and verify edits, and nothing in it is deployed or checked until 07. One phase covers write, ship and verify | `phase-06-cloudflare-tunnel.md:70` ("deploy and round 2 checks run in Phase 07 step 4") |
| Δ2 | Move the flag flip from Phase 09 step 3 (its own redeploy) into the cutover deploy (new 07) | One restart and one CI cycle fewer. The flag sends nothing until an `exness` subscription exists, because the factory builds the adapter only on `create("exness")` and the client gates only order ops. The flip comes after the tunnel is proven, so live creation and Pause go over the tunnel | `broker_factory.py:85-98`, `exness_client.py:265`, `strategy_app_service.py:121` |
| Δ3 | Ship (new 06) waits for the latest E2 row to pass, not for E2 to close | E2 has no deploy freeze, and a restart only shortens a row's log window. Integrity, `sync_1m` p95 and C5 are unaffected | `261009-.../phase-08-...md:136`, packet "Paper validation E2" |
| Δ4 | The live phase waits for E2 row 3 (Mon 10-26), and E2 row 4 counts the `exness` ids | The unique index on `(strategy_code, symbol, interval)` forbids a paper and an `exness` subscription on the same triple, so "running 2" in row 4 cannot hold on the paper ids once the live phase starts. Row 3 already covers the weekend close and reopen | `subscription_repository.py:102-104`, `261009-.../phase-08-...md:254,263-264` |
| Δ5 | E2 row 4 and the DST check run once | Both run C5 and C3 on the same date for the same symbols (DRY) | `261009-.../phase-08-...md:264`, `phase-10-observation-dst-go-live.md:36-41` |
| Δ6 | Reconcile gets `exness_risk: RiskConfig \| None` instead of `Safeguards` | engine/live reads one domain value object and no infra type. The assertions are the same and there is one less dependency in the reconcile constructor | `strategy_reconcile_app_service.py:59-69,167-173`, `services.py:174-187` |
| Δ7 | Optional: inline `use-safeguards.ts` into `exness-strip.tsx` | One consumer, so one file per flow | `phase-05-spa-mode-pause-and-hints.md:47-50,71-75` |
| Δ8 | Fix the facts in 06 and 08 | The Zero Trust "Networks" menu is gone (2026-10-12), and the path is now Networking > Tunnels > Routes. `tunnel ready` is verified, so the fallback goes. The DNS-conflict rule is now [V], not inference. The `tunnel-test` CNAME is removed by hand | research packet; `phase-06...md:21,29,35`; `phase-08...md:14,32` |
| Δ9 | Close the stale unresolved questions | The SL is not moved after entry [V]. `margin_percent` stays recorded raw, because only `volume_min` and the margin formula decide the pass | `plan.md:144-146`; packet "Code facts" |
| Δ10 | Effort and dates | Observation runs Mon 10-26 to Fri 10-30, DST and go-live on Mon 11-02. The `plan.md` unresolved question about the window is answered | `plan.md:143` |

Not changed, on purpose: every SPA mockup item, the pause semantics, the three-round tunnel rollout, the env values, the stop-and-ask list, the rollback ladder, and the Phase 04 `Safeguards` object. That object has two real callers today (the adapter and the safeguards route). It also deletes the `exness_*` keys from `default_broker_config` (`services.py:166-167`) and the adapter's own cap fields (`exness_broker_adapter.py:100-106`), so its net code is small [I, not counted].

## 3. Answers to the open questions

1. **Must Phase 07 wait for E2 to close on 11-02? No.** The user replaced the freeze with a schedule that tolerates restarts (`261009-.../phase-08-...md:136`). The checks the packet lists are unaffected, except the C1 log window, which already only shortens. The one real conflict is not the deploy but the live phase deleting the paper subscriptions. This candidate gates live on row 3 and moves row 4's "running 2" to the `exness` ids. That move is a user decision (gate G-E2 below), because it changes the previous plan's pass rule. Warmup cost [V, packet]: each restart costs hitnrun2 about 8 open-market hours and engulfing about 21 open hours of paper signals. Paper positions are lost. Two restarts during E2 are therefore acceptable.
2. **Is the order of the master pushes and live steps the best one for the earliest safe first live trade?** With Δ2, the order is: ship (weekday) → cutover and flag (Sat 10-24) → row 3 PASS (Mon 10-26 03:00Z) → live subscriptions. The earliest live entries are hitnrun2 about 8 open hours later (around Mon 10-26 11:00Z) and engulfing about 21 open hours later [V, warmup figures in the packet; times are inference]. Starting live before row 3 would skip the only weekend-reopen data check, and it would expose the first live position to an unchecked reopen. Cutover before live is kept, so the token-bearing live actions never cross plain HTTP after the flag is on. If the code slips past Fri 10-23, both deploys move later, the live start slips, and the observation window shrinks. Go-live stays at or after 11-02.
3. **Is an SSE heartbeat in scope? No.** The tunnel does not buffer `text/event-stream`. The 125 s idle cut already applies through today's proxy (research [V]/[I]). The bar hook's `onerror` marks the chart stale, refetches, and lets `EventSource` reconnect (`web/src/hooks/use-realtime-bar.ts:107-113`). The quote hook has no `onerror` and relies on the default `EventSource` reconnect (`use-realtime-quote.ts:80-113`) [I: the default retry applies after an edge close]. A heartbeat is new code with no binding decision behind it. Δ in phase 06 step 7 adds one long-stream check during market hours, which is when traffic flows. If the user sees flapping stale indicators after the cutover, a `: ping` every 20 s is the follow-up.
4. **Is anything in Phases 04–06 bigger than needed?** Mostly no, because every SPA item and both sizing keys are binding. The cuts are small: Δ1 (merge 06 into ship), Δ6 (one value object into reconcile), Δ7 (no single-caller hook file), and dropping the healthcheck fallback in 06 step 3. The `title` on `+ New` and the `.strategies-page` flex change are needed for "a title on every mutating button" and the strip height.

## 4. Risks, cuts and merges

| Risk | L×I | Mitigation |
|---|---|---|
| With the flag on at the cutover, a leaked admin token could create an `exness` subscription before the user means to (`BROKER_DISABLED` no longer applies) | L×M | Orders are still 0.01 lot and capped at 25 USD per UTC day. The token crossed plain HTTP between the 06 and 07 deploys. Cheap option: rotate `ADMIN_TOKEN` in the same 07 config commit, at no extra deploy, and the SPA re-prompts once on 401 |
| The cutover has to roll back after the flag is on | L×L | Port first, then DNS (current phase-08 rollback). The flag stays true but does nothing, because no `exness` subscription exists |
| The user declines Δ4 (row 4 counting the `exness` ids) | M×M | Fallback: run the live phase after E2 row 4 on 11-02. The plan then matches the current one (go-live dated later), with Δ1, Δ2, Δ5 and Δ6 kept |
| Code slips past Fri 10-23 | M×L | Both deploys move later. The 07 cutover does not need a weekend; it needs a quiet hour |
| A crash restart while live clears the pause | L×M | Unchanged from the current plan: the strip polls GET and shows the truth. The plan itself schedules no deploy after the live phase starts |
| Merged phase 06 is long for one runner step | L×L | Its steps are sequential, with two gates. The file stays shorter than the current 06 plus 07 |

Cut: the separate flag redeploy (Phase 09 step 3), the separate DST run on 11-02 (now one run with E2 row 4), the `tunnel ready` fallback branch, the `use-safeguards.ts` file (optional), and three stale unresolved questions.
Merged: 06 into 07 (new 06), Phase 09 step 3 into 08 (new 07), E2 row 4 into Phase 10 step 3 (new 09).
User gates added: G-E2, which asks whether E2 row 4 may count the two `exness` subscriptions on the same triples, decided before the new 08 step 5. D3 is still open, and I recommend **A** (no code), because B adds a script and does not exercise the strategy path (`plan.md:73`).

## Unresolved questions
- G-E2 (above) is the user's call.
- Whether to rotate `ADMIN_TOKEN` at the cutover. It is cheap, but not required by any decision.
- [UNVERIFIED] Whether the prod `.env` binds Mongo, Redis and Portainer to 127.0.0.1. This is out of scope and flagged only.

Status: DONE
Summary: Nine phases, two master pushes and no config-only redeploy. Ship waits for the latest E2 row to pass, the cutover carries the flag flip, live waits for E2 row 3, and E2 row 4 merges with the DST check on 2026-11-02. One new user gate (G-E2) covers the paper versus exness subscription conflict on the unique triple.
