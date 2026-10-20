# Planner debate candidate 3: executability lens

Date 2026-10-20. Lens: each `phase-NN` file is cooked by one fresh worker (`/ak:cook <phase> --advice`, possibly Sonnet) in strict numeric order. The controller blocks until the worker settles (`~/.claude/skills/eve-cook-plan/SKILL.md` §5). [V] = verified in source, a file or a command today. [I] = my inference.

## 0. Conventions that every phase file carries (new)
These rules fix the main stall modes. They go in `plan.md` once, and each phase file repeats the short form, because a worker reliably reads only its own phase file.
- **Entry gate section.** It is a mechanical precondition, run first. A miss ends the phase with `NOT_YET: <reason>. Resume: /eve:cook-plan <plan-dir> --from NN after <UTC time>`. A miss is not a failed verification, so the worker does not spawn kongming and does not try a fix. This is how calendar waits avoid blocking a worker for days.
- **Failure Protocol section in each phase file.** `ak-cook/references/advisory-supervision-checkpoints.md` says that each phase file carries its own protocol. Today only `plan.md:139-140` has one.
- **Gate syntax.**
  - `[USER]`: the user acts. The worker asks one question with the exact text and the reply token it expects (for example `tunnel created`), then waits. Silence never counts as a yes.
  - `[ASK]`: a stop-and-ask approval. The question states the computed facts the user needs.
  - An approval given earlier never carries over to a later gate (U2).
- **Authority.** `git push origin develop` is authorized by the plan. A push to `master`, a `pocketquant-config` edit and every live action is `[ASK]`.
- **Ops recipe in `plan.md`, referenced by each prod phase.** I checked each item today.
  - The active gh account is `vunguyen-ai`, and `camping89` is logged in but inactive (`gh auth status`). The origin is `camping89/pocketquant` (`git remote -v`). Push with `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" <ref>`, and dispatch with `GH_TOKEN=$(gh auth token --user camping89) gh workflow run cicd.yml --ref master`. The dispatch command is [I]: a 403 is likely, but I did not test it.
  - The SSH key has CRLF line endings. Run `tr -d '\r' < ../pocketquant-config/vps/default/id_rsa > .cache/ssh/vps_key && chmod 600 .cache/ssh/vps_key`, then `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r')`. The source is the user memory `pocketquant-vps-access-quirks`. The base pattern is in `docs/deployment.md:48-51`.
  - Docker is needed before any pytest run. If `docker ps` fails, start Docker Desktop and retry after 10 s.
  - The expected red on Windows is exactly 4 failed plus 4 errors, all in `tests/core_test/unit/common/test_utc_runtime_guard.py` and `tests/core_test/infra/scheduling/test_cron_trigger_timezone.py` (both files exist [V]). Any other red counts as a failure. Today's text, "only the 4 known failures", lets a worker misread "4 failed, 4 errors" as 8.

## 1. Phase list, in run order (one plan; file order = run order)

**01 Admin-token auth on every mutation route.** This is the current phase 01, unchanged in scope.
- Files: as in the current phase 01.
- Delta: the structural test asserts `== 17` mutation routes and prints the list. "Expected 17" should be an assertion, not a printout. Phase 04 then edits that number.
- Verify: the current validation, plus Docker up first.
- Gates: none.

**02 Broker per subscription, one pooled Exness adapter.** This is the current phase 02, unchanged.

**03 Re-resolve the access point.** This is the current phase 03, unchanged.

**04 Safeguards object, entry pause, leverage-aware sizing.** This is the current phase 04 without step 9 (integrity) and without its test and doc lines.
- Files: the current list minus `integrity_jobs.py`, `sync_jobs.py` and `test_integrity_calendar.py`.
- Step 10 becomes "change the pinned count in `test_admin_token_guard.py` from 17 to 19". It is no longer "if pinned".
- Verify: the current validation with the integrity paths removed.
- Gates: a ratchet miss is a stop-and-ask.

**05 Count unexpected 1m bars on the integrity WARNING.** This is the current phase 04 step 9, plus its test case and the docs sentence.
- Files: `engine/market_data/app_services/integrity_jobs.py`, `engine/market_data/app_services/sync_jobs.py` and `tests/app_test/market_data/test_integrity_calendar.py` (exists [V]).
- Verify:
  - `uv run python -m pytest tests/app_test/market_data -q` exits 0;
  - ruff, pyright and the ratchet pass;
  - `grep -c "unexpected_count" src/pocketquant/engine/market_data/app_services/integrity_jobs.py` prints at least 1.
- Gates: none.

**06 SPA: badge, state pill, Exness strip, hints.** This is the current phase 05, with two deltas.
- (a) Delete `hooks/use-safeguards.ts` from "Create". Its query and its two mutations live inside `exness-strip.tsx`, which is the only caller.
- (b) The manual check becomes a `[USER]` gate:
  - the worker starts the backend and `npm --prefix web run dev` in the background and records their PIDs and ports;
  - it sets one local subscription to `broker: "exness"`;
  - it asks: "Open http://localhost:<port>/strategies and check the 6 items listed in this phase. Reply `ui ok` or the failing item.";
  - it restores the document and stops both processes before it ends (process rule).
- Verify: the current mechanical greps, plus the reply `ui ok`.

**07 Cloudflare Tunnel service.** This is the current phase 06.
- Entry gate: `grep -c "^TUNNEL_TOKEN=." ../pocketquant-config/vps/default/.env` prints `1`. When it prints 0, do the `[USER]` step and wait for `tunnel created`. The user can do this step before cooking starts, and then the worker never blocks here.
- The `[USER]` dashboard path changes to the 2026 one: Networking > Tunnels > Create > Cloudflared; then Routes > Add route > Published application, with `tunnel-test.pocketquant.xyz` pointing to `http://web:80`. The research report gives this path, and it says the Zero Trust "Networks" menu was removed on 2026-10-12. Warn the user that the Free plan may ask for a card.
- Tag step: the worker runs `curl -s "https://hub.docker.com/v2/repositories/cloudflare/cloudflared/tags?page_size=10&ordering=last_updated"`, takes the newest `YYYY.M.P` name, then `docker run --rm cloudflare/cloudflared:<tag> tunnel ready --help` must exit 0.
- Verify: the current validation.

**08 Ship with live off (deploy A).** This is the current phase 07.
- Delta: remove the E2 dependency.
- Entry gate: Phases 01-07 are on `origin/develop` (`git log origin/develop` contains each phase's commit subject), and `TUNNEL_TOKEN` is present.
- Steps:
  1. Run the release gate (current step 1).
  2. `[ASK]` Edit the config (current step 2).
  3. `[ASK]` Push `master`. The question states the computed facts:
     - the number of open paper positions, from `positions` with `closed_at: null` for the two validation subscription ids (`01a15754-39ed-…`, `01a15754-3ab5-…`, venue `phase-08…md:271`);
     - the next E2 row time (venue `phase-08…md:260-264`);
     - the warmup cost: hitnrun2 needs about 8 open-market hours and engulfing about 21 [V packet];
     - my suggested window: Sat 2026-10-24 after the row 2 check (03:00Z) and before the Sunday reopen.
  4. Run the current step 4 checks with one change. The user's SPA check uses Pause then Resume (with confirm) to test the token prompt and a mutation. It does not stop or start a validation subscription, because a stop loses strategy state (`plan.md:66`, B11) and would reset the E2 paper run.
  5. Add one line to `reports/ship-log.md` with the deploy time and the `StartedAt` of `pocketquant-app`, for the E2 C1 row.
- Verify: the current validation.

**09 Tunnel cutover (deploy B).** This is the current phase 08.
- Context fix: "a hostname cannot be added while a record exists" is now [V] (research). Removing a route does not delete its DNS CNAME, so the user deletes `tunnel-test` in DNS by hand.
- Origin check: `curl -s --max-time 5 http://<vps-ip>:80/` must print `000`, with curl exit `7` or `28`. Exit 28 is a timeout, which ufw would cause by dropping the packet [I]. Docker-published ports bypass ufw [V research], so once the publish is gone either exit code means closed.
- SSE check: run it only when XAUUSD is open, i.e. not between Fri 21:00Z and Sun 23:05Z. Otherwise write `SSE deferred` in `reports/ship-log.md`, and Phase 10's entry gate repeats it.
- `[ASK]` Push `master`. The question states the deploy-A time, so deploys A and B can share one warmup loss (same day).
- Verify: the current validation.

**10 Arm live (deploy C): E2 gate, preflight, flag on, Exness subscriptions.** This is the current phase 09 steps 1-5, gated on E2 in place of the current phase 07.
- Entry gate (all must hold; else `NOT_YET`):
  - (a) now ≥ 2026-11-02T03:00Z;
  - (b) `grep -cE '^\| [1-4] \|.*\*\*PASS\*\* \|$' plans/261009-0858-exness-venue-lean-sync-refactor/phase-08-validation-spread-backtests-paper-week.md` prints `4` (rows 1-4 PASS, and row 4 holds C5 `3600 True`, venue `:254,264`);
  - (c) `POST /api/v1/market-data/integrity/check` with the token, for XAUUSD and EURUSD at 1m with `days_back` 2, returns `unexpected_count` 0 for each;
  - (d) any deferred SSE check passes;
  - (e) `reports/round-trip.md` holds the user's D3 answer and their U1 balance (≤ 250 USD).
  - When (b) is short after 2026-11-02, `[ASK]` "E2 row N missing or FAIL; run venue T8.7 row N first?"
- Steps:
  1. Stop-distance check. Add `"run_id": "01a15754-39ed-73e3-921e-df085eb4a786"` to the query, because `run_id` is the subscription id (`live_trade_collector.py:58-63`). Pass when the count is > 0 and the number above 25 is 0. Otherwise `[ASK]`.
  2. Margin check (current step 2).
  3. `[ASK]` Set the flag and redeploy (current step 3, with the camping89 dispatch recipe).
  4. Record the baseline balance, the deals and the UTC time in `reports/round-trip.md`.
  5. `[ASK]` Swap the subscriptions (current step 5).
  6. Check AC3.
  7. `[USER]` standing instruction, which the user acknowledges with `pause plan ok`: "When the first LIVE position opens, press Pause in the strip. After it closes, press Resume and confirm."
- Verify:
  - the settings one-liner prints `True 25.0 0.01 1000.0 0.1 True`;
  - two `broker: "exness"` subscriptions show `running`;
  - `docker logs pocketquant-app 2>&1 | grep -c "exness.broker_connected"` prints `1`.
- The phase ends here. No worker waits for a trade.

**11 Round-trip evidence (re-runnable).** This is the current phase 09 steps 6-8 as read-only checks.
- Entry gate: for each `exness` subscription, the `trades` collection has at least one row with `run_id` equal to that subscription id. Else `NOT_YET` ("resume after the next fill; check daily").
- Steps:
  1. Run the per-trade checks of the current step 6. The user confirms the SL in the terminal (`[USER]`, reply `sl seen`).
  2. Check pause-while-open from timestamps:
     - a `positions` row has `opened_at < t_paused < closed_at < t_resumed`;
     - `t_paused` and `t_resumed` come from the `exness.safeguards.entries_paused` and `exness.safeguards.entries_resumed` log lines (a Phase 04 event);
     - there is no `openPosition` between them.
     
     If no position spans a pause, `[ASK]` with two options: wait for the next trade (`NOT_YET`), or accept the Phase 04 unit tests as the evidence.
  3. Run the commission check (current step 8) over the deals since the baseline. If any `balance` deal exists in that window, `[ASK]`, because a deposit breaks the equality.
  4. `[ASK]` Choose between continuing to observation with entries on and pausing (D4).
- Verify: each item in the current phase-09 Validation, and none of the five stop events in `docker logs`.

**12 Observation and go-live (re-runnable).** This is the current phase 10 without the DST step.
- Each run appends one row to `reports/live-observation.md` (current step 1 fields), then checks three things:
  - Friday after 18:00Z with any open `exness` position: `[ASK]` the weekend hold (current step 2 options);
  - fewer than 5 rows on distinct Mon-Fri UTC days: `NOT_YET` ("re-run tomorrow");
  - otherwise: `[ASK]` go-live, then the journal entry (current step 4).
- Verify:
  - every row has `CB==0`, no stop event, `unexpected==0`, and close deals equal to the new `trades` rows;
  - the go-live answer is recorded.

## 2. Deltas versus the current plan
| # | Delta | Reason | Evidence |
|---|---|---|---|
| 1 | The E2 gate moves from the ship phase (current 07) to arming live (new 10) | The E2 schedule allows deploys; a restart only shortens a row's log window. Shipping with live off risks no money | venue `phase-08…md:24,136,162`; packet lines 35-39; `plan.md:44` |
| 2 | The dated DST step of current 10 is replaced by the new 10 entry gate: E2 row 4 (C5 `3600 True` + C3) plus `unexpected_count` 0 | Live starts after 2026-11-02, so the old step duplicates E2 row 4. The unexpected count covers "no bars in the closed hour" | venue `:221,245,254,264`; `plan.md:93` (AC7) |
| 3 | Current 09 is split into arm (10) and evidence (11). Every calendar wait becomes an entry gate with a `NOT_YET` stop | A worker cannot wait 1-5 days for a signal; the runner blocks on each worker | `eve-cook-plan` SKILL.md §5; current phase 09 effort line |
| 4 | Observation is re-runnable with one row per run, and needs 5 trading-day rows | The dated window to 2026-10-30 cannot hold, and a daily row cannot be done in one worker session | packet line 40; current phase 10 step 1 |
| 5 | Pause-while-open becomes a `[USER]` SPA action, proven later from timestamps | The current version needs an agent to act right after a fill | current phase 09 step 7; `position/entities.py:37-38` |
| 6 | Integrity is split from current 04 into its own phase (05) | It owns different files, and a weaker model gets a smaller context | current 04 Files; `integrity_jobs.py`, `sync_jobs.py` |
| 7 | `use-safeguards.ts` is inlined into `exness-strip.tsx` | CLAUDE.md requires a second real caller before a new helper | `CLAUDE.md` "Rules that change decisions"; current phase 05 step 4 |
| 8 | The ship SPA check uses Pause/Resume, not stop/start of a validation subscription | A stop loses strategy state and would reset the E2 warmup | `plan.md:66`; current phase 07 step 4 last bullet |
| 9 | The stop-distance query is filtered by `run_id` and runs after E2 closes | Only that subscription counts, and after E2 there are more trades | `live_trade_collector.py:58-63`; venue `:271` |
| 10 | Every phase carries an Entry gate and a Failure Protocol, and a `NOT_YET` stop is exempt from kongming | `--advice` fires counsel on any missed Verify. A date wait is not a failure | `ak-cook/references/advisory-supervision-checkpoints.md` |
| 11 | An ops recipe (push account, CRLF key, Docker) goes in `plan.md` | Without it a worker hits a 403 or "invalid format" and stalls | `gh auth status`; `git remote -v`; `docs/deployment.md:48-51` |
| 12 | The expected red is stated exactly: 4 failed plus 4 errors in 2 named files | A Sonnet worker would count 8 and escalate | user memory "local tests need Docker"; both files exist |
| 13 | The Cloudflare dashboard path is corrected, and a tag lookup command is added | The old menu was removed on 2026-10-12 | `reports/researcher-261020-1906-cloudflare-tunnel-facts.md` |
| 14 | The origin-closed check accepts curl exit 7 or 28 | ufw may drop instead of refuse [I] | research: Docker ports bypass ufw |
| 15 | The SSE check runs only when the market is open; otherwise it is deferred | A closed-market stream emits nothing, so the check would fail falsely | current phase 08 step 8 ("during market hours") |
| 16 | The route count is pinned at 17 in 01 and moves to 19 in 04 | "if pinned" is a guess for the worker | current 04 step 10 last bullet |
| 17 | D3 is answered before cooking and recorded in `reports/round-trip.md`. I recommend A | B is new code with no code phase left to hold it once 08 has shipped | current phase 09 "Files" |
| 18 | AC6 gains a "no `balance` deal in the window" guard | A deposit breaks `Δbalance = P − C` | current phase 09 step 8 |

## 3. Answers to the four open questions
1. **Phase 08 (ship) need not wait for E2. Live arming (new 10) must.**
   - The E2 plan removed its no-deploy freeze. A restart "only shortens that row's log window and is not a failure" (venue `:136`, `:162`).
   - C3 and `sync_1m` p95 read Mongo, and "Running 2" comes back through reconcile [V packet].
   - The real cost is one warmup reset (about 8 h and 21 h) and the loss of any open paper position.
   - Shipping in the Sat 2026-10-24 window after row 2, with deploys A and B the same day, means one reset that falls before the Sunday reopen.
   - E2 rows 3 and 4 then validate the code that will go live, including Phase 03's client change. C3 must send the token after the deploy (venue `:185` already says so).
2. **Order for the earliest safe first live trade.**
   - All code and tunnel work (01-09) finishes inside E2's calendar, so 2026-11-02 becomes the arming day and not the ship day.
   - The earliest live fill is 2026-11-02 plus the strategy warmup on a fresh `exness` subscription: about 8 open hours for hitnrun2 and about 21 for engulfing. No preload exists [V packet].
   - It is not worth folding the flag-on into deploy B. The flag would sit on for about 9 days with the deep backfill blocked (`docs/deployment.md:241`), and flag-on is a real-money gate that belongs right before the swap.
   - So three deploys, of which two land before E2 closes.
   - Going live before E2 closes would reverse the plan's E2 prerequisite (`plan.md:27`). Only the user can do that.
3. **SSE heartbeat: out of scope.**
   - It is not requested and not a go-live blocker.
   - The bar hook already resyncs on drop: `es.onerror` sets stale and refetches OHLCV, and the hook relies on EventSource auto-reconnect (`web/src/hooks/use-realtime-bar.ts:107-113`).
   - The quote hook has no `onerror` (`use-realtime-quote.ts:80-115`). [I] It relies on the browser's default reconnect, which still reconnects.
   - The 125 s cut only hits quiet, closed-market streams, and the tunnel does not make that worse [I packet].
   - Record it as a known limit in Phase 09's ship-log, not as code.
4. **KISS in current 04-06.**
   - Cut `use-safeguards.ts`, because it has one caller (delta 7).
   - Splitting integrity (delta 6) adds no code; it only shrinks the worker's scope.
   - The rest is at minimum:
     - `Safeguards` has four real readers today: factory, adapter, reconcile and route;
     - `RiskConfig.leverage` is required by D1;
     - the healthcheck is one block.
   - Minor and kept: `Settings.exness_risk_per_trade` with `le=0.10` duplicates the `RiskConfig` check (`core/domain/risk/value_objects.py:17-18`). It fails at startup and not every 5 s in reconcile, so the duplication earns its line.

## 4. Executability risks (where a worker would stall, guess or skip)
- **A `[USER]` gate while the user is away.** The worker blocks on an Orca `question`. That is the design, but it holds a session. Mitigations:
  - the user does the tunnel creation before cooking (07 entry gate);
  - the DNS cutover in 09 is the only mid-phase user step longer than a reply.
- **Cross-plan dependency (E2).** New 10 reads another plan's results table. If the venue runner writes row 4 in a different format, the grep returns less than 4. The question in the `NOT_YET`/`[ASK]` path covers that, so the worker stops and does not guess.
- **Log-based evidence is lost on a restart.** The pause timestamps and stop events read `docker logs` (venue `:39`: a deploy recreates the container). The rule "no redeploy while paused or open" (`plan.md:109`) must sit in the 10, 11 and 12 phase files themselves, not only in `plan.md`.
- **The `gh workflow run` account.** If the camping89 recipe also gets a 403, the worker cannot apply config. Fallback: an empty `master` push is not allowed (it is a fast-forward of develop). The worker stops and asks the user to dispatch.
- **The SPA check needs a human.** No DOM test exists (`web/vitest.config.ts`, current phase 05 context). The `[USER]` reply token keeps it mechanical, and the worker must stop its dev processes.
- **Docker Desktop is down.** About 109 tests error, and that looks like a code failure. The ops recipe's `docker ps` pre-check prevents it.
- **Ambiguous "≥ 1" counts in the verdict greps.** The current text, "prints a number ≥ 1", is fine for a worker. The rule is to keep every pass condition as a literal output compare.
- **D3 = B chosen late.** The plan then needs a new code phase after 08, which conflicts with the strict file order. This is why D3 must be answered before cooking.

## Unresolved questions
- Is 5 trading-day rows the right observation length? The current plan's window was dated, not counted.
- Will the user accept the Sat 2026-10-24 window for deploys A and B, or must 08 and 09 run sooner?
- D3: A, which I recommend, or B?
- Does `gh workflow run` under `vunguyen-ai` get a 403? I did not test it.

Status: DONE
Summary: Twelve phases in run order. Shipping and the tunnel cutover move inside the E2 window, live arming waits for E2 row 4, and every calendar wait becomes a re-runnable entry gate that ends in `NOT_YET` instead of a stalled worker.
Concerns/Blockers: none. The new phase 10 depends on another plan's results-table format; see risks.
