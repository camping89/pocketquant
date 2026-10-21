# Kongming: open items audit (2026-10-21 00:33 +07)

Advisory only. `[F]` = verified tonight against a file (`file:line`) or a command run on this workstation; `[I]` = inference. Phase 01 is done (`ed85d1d` on `origin/develop` `[F]`); Phase 02 is being cooked; the plan and phase files are the versions edited at 00:21-00:31.

## TL;DR

Nothing blocks Phases 02-07 from running tonight. Three decisions are worth making now, because each changes plan text in a phase that is not yet cooked: (Q1) the single-order guarantee: accept the bounded risk (recommended) or add a small in-app "pause after first fill" to Phase 05; (Q2) drop the Cloudflare API-token fallback (recommended: the Free-plan field limits apply through the API too); (Q3) flip the Task 11.12 recommended reply to `keep on` after a clean round trip, otherwise Phase 12 observes a paused system for five days. Three user actions unblock later phases today: create the tunnel and store `TUNNEL_TOKEN` (Phase 07 waits on it; the key is absent now `[F]`), turn on Cloudflare 2FA, and paste the rate-limit expression into the dashboard editor (which also settles Q2). No [ASK] should be pre-approved: U2 and the 19:35 decision settled that, and every question now leads with a one-word recommended reply. No defect was found that stops a phase; five small inconsistencies are listed in section 5.

## 1. Open questions

### Needs a decision now (plan text changes before the phase is cooked)

**Q1. Single-order run: how hard a guarantee?** (planner concern a)

- Fact `[F]`: the Task 11.9 step 0 watch pauses after the first position only while a worker runs (about 2 h); on `no_entry` the worker exits `NOT_YET` with entries on until the next run, up to 24 h later (`phase-11:210-223,237,314`).
- Bound while unwatched `[F + I]`: with one `exness` subscription, `submit_order` opens only when that subscription holds no position (`exness_broker_adapter.py:199-203`), so trades are sequential and each needs its own SL/TP close first. The cap rejects an open once realized PnL for the UTC day is at or below -25 USD (`:262-264`), and sizing rejects stops above about 25 USD/oz (Phase 05 arithmetic). Worst case per UTC day is therefore about 50 USD (one trade that lands just above the cap, then one max-loss trade), and about 100 USD if an unwatched 24 h window straddles midnight UTC, plus gap slippage. Realistic exposure is far lower (hitnrun2 TP is at least 2 percent, so a winner takes time).
- Options:
  - A. Accept the bound (recommended). Zero code; the risk is already in `phase-11` Risk. Cheap tightening: raise the watch to 4 h (`TRIES=240`).
  - B. Re-pause at `no_entry`, then ask Resume [ASK] again at each re-run. Keeps U2 but gives only 2-4 h of entries per run day; go-live can take weeks if signals are rare. Not recommended.
  - C. In-app "pause after first fill": `single_entry` on `Safeguards` (stored next to `entries_paused`), `POST /admin/safeguards/resume?single=true`, and the adapter re-pauses after a successful open through a persist callback. About 40 lines plus three tests in Phase 05, which is not cooked yet. Failure modes are safe-direction (pauses early, or behaves as today). This is the only hard guarantee, including across a restart.
- Recommendation: A. Choose C only if "only one order" is a hard requirement for you rather than "bounded by the daily cap". What flips it: you would not accept a 50-100 USD worst case on a 250 USD account for one unwatched day.

**Q2. Cloudflare rate-limit rule: remove the API-token fallback.** (planner concern b)

- Fact `[F]`: the Free plan allows one rate-limiting rule whose expression may use only the Path and Verified Bot fields, IP counting, fixed 10 s period and timeout (Cloudflare "Rate limiting rules" availability table, fetched tonight). Both plan expressions use only `http.request.uri.path`; `wildcard` and `starts_with()` carry no plan note; only `matches` (regex) needs Business.
- Inference `[I, high]`: plan entitlements are enforced by the API; the dashboard is an API client. The "create via API" page names no bypass. If the dashboard rejects both expressions, the Rulesets API rejects them too, so the token buys nothing and adds a secret in `pocketquant-config` (and the `cloudflare/` directory it would live in does not exist and has no ignore rule `[F]`).
- Recommendation: delete the Task 9.3 fallback block, the `[USER] token stored` gate, and Task 9.14 step 1; on `both rejected: <errors>` the phase ends with `NOT_YET` and the errors go to counsel. This reverses decision (6) of 00:21, so it is yours to confirm. Action A3 below (paste the expression now) most likely makes the whole question moot.

**Q3. Task 11.12 default after a clean round trip: `keep on`, not `pause`.**

- Fact `[F]`: Task 11.12 recommends `pause` (`phase-11:298`); Phase 12 then records five rows of a paused system (`new_trades 0`), and Task 12.6 go-live resumes entries (`phase-12:150`). The five-day observation would observe no trading.
- Your words were "test only 1 order"; after that test passes, normal operation is the go-live trial. Recommendation: the 11.12 question reads `Recommended: keep on` when the run has `round_trip: DONE` material with no stop event and AC6 recorded (or accepted void), else `Recommended: pause`. Phase 12 then observes real trading under the cap, as designed on 2026-10-20 19:35.

### Safely asked at their gate (no action now; suggested defaults for the planner, deviation 4)

- Task 11.11 (AC6 void): `Recommended: accept` when only `clamped True`; `Recommended: stop` when `balance_deals > 0` (a deposit or withdrawal during the run needs an explanation first).
- Task 12.4 (Friday with an open position): `Recommended: 2` (pause entries; the open position keeps its venue SL/TP; nothing new opens into the Sunday gap).
- Task 12.6 (go-live): `Recommended: yes` when all five rows passed and no stop event; `Recommended: no` otherwise.
- Task 11.3 strategy choice: already decided to be recommended from the preflight (likely hitnrun2 XAUUSD 1m by the tie rule); confirm the balance there (U1).

## 2. Actions you can do now

**A1. Create the Cloudflare tunnel and store its token (unblocks Phase 07 Task 7.1; the key is absent now `[F]`).**
1. Cloudflare dashboard: Networking > Tunnels > Create a tunnel > Cloudflared; name `pocketquant-prod`. The Free plan may ask for a payment card (seen in the research report); have one ready.
2. Copy only the token after `--token` in the install command. Do not run that command anywhere.
3. Open the tunnel > Routes > Add route > Published application: subdomain `tunnel-test`, domain `pocketquant.xyz`, service URL `http://web:80`, Save. Leave `@` and `www` unchanged.
4. Add one line `TUNNEL_TOKEN=<token>` to `D:/w/_me/algotrading/pocketquant-config/vps/default/.env` (do not commit yet; Task 8.3 commits that file). Never paste the token in chat.
5. Check: `grep -c "^TUNNEL_TOKEN=." ../pocketquant-config/vps/default/.env` prints `1`.

**A2. Cloudflare account 2FA (Task 9.3 step 1; safe any time).** My Profile > Authentication > Two-Factor Authentication: turn it on (authenticator app or security key) and store the backup codes offline. Task 9.3 already accepts "I did it on 2026-10-21" (`phase-09:59`).

**A3. Test (or deploy) the rate-limit expression now (settles Q2).** Zone `pocketquant.xyz` > Security rules > Create rule > Rate limiting rules: name `api-flood`, Edit expression, paste `(http.request.uri.path wildcard "/api/*" and not http.request.uri.path wildcard "/api/v1/admin/safeguards*")`; characteristic IP; 200 requests per 10 seconds; action Block; duration 10 seconds. If the editor rejects it, try `(starts_with(http.request.uri.path, "/api/") and not starts_with(http.request.uri.path, "/api/v1/admin/safeguards"))`. Deploying it now is fine: the site is already proxied and the exempted path does not exist yet. Tell the agent which expression was accepted (or both errors).

**A4. Guardrails until Phase 08.**
- Do not push `master` and do not merge `develop` into any hotfix: prod has no `ADMIN_TOKEN` `[F: count 0]`, and `ed85d1d` makes every prod mutation return 503 until Task 8.3 sets it. Phase 08 orders 8.3 before 8.4, so the plan itself is safe.
- Do not edit `src/`, `tests/`, `web/` while the Phase 02 worker runs (its files are in the working tree now `[F]`).
- Keep Docker Desktop running (every entry gate checks `docker ps`).
- Do not cook with `--new-worktree`: `web/src/routeTree.gen.ts` is gitignored and exists only in this checkout (`[F]`, generated 00:19); `npm run build` runs `tsc -b` first (`web/package.json:8`) and fails on a fresh checkout. CI and Docker are unaffected (`web/Dockerfile` runs `npx vite build` only; the CI `tests` job is Python only `[F]`).

**A5. Hygiene (low priority).** `pocketquant-config` has an untracked `.claude/agent-memory/` directory `[F]` (agent memory written by an earlier run with that repo as cwd). Add `.claude/` to that repo's `.gitignore` so a stray `git add -A` never commits it.

**A6. Before Phase 11 (not now).** Make sure the Exness account holds at most 250 USD (U1); the agent reads the venue balance and you confirm it at Task 11.3.

## 3. Approvals: every [ASK] gate

U2 (`plan.md:125`) says every gate is approved when reached, and the 19:35 decision kept each `master` push as an [ASK]. Pre-approving anything therefore needs a plan edit to U2. My recommendation is to pre-approve nothing: with the recommended reply leading each question, each gate costs you one word, and the no-money gates are the only ones that could be pre-approved at all.

| Phase/Task | What is asked | Recommended reply | Pre-approvable without violating U2 or real-money safety? |
| --- | --- | --- | --- |
| 05 ratchet (only if `code_metrics --ratchet` fails) | raise the metric ceiling | `raise the ceiling` | Yes: no money, no prod; your standing rule already says raise rather than pad. Worth pre-approving because it fires mid-phase while you may be away. |
| 8.3 | commit `ADMIN_TOKEN` + four Exness keys to prod config; move both local remote-DB env files to localhost | `yes` | Technically yes (flag stays off, values are fixed by binding decisions), but it is listed under stop-and-ask ("editing pocketquant-config"). Keep at the time. |
| 8.4 | push `develop:master` (deploy A, live off) | `yes` | Keep at the time: 19:35 decision (2). |
| 9.8 | drop `WEB_PORT`, rotate `ADMIN_TOKEN`, push config | `yes` | Same as 8.3. Keep at the time. |
| 9.9 | push `develop:master` (deploy B, live off) | `yes` | Keep at the time: 19:35 decision (2). |
| 10.5 | `EXNESS_LIVE_TRADING=true`, push config, dispatch (deploy C) | `yes` | No: this is the arming decision. |
| 11.3 | confirm the recommended strategy and balance <= 250 USD | `yes` | No: U1 needs the live balance. |
| 11.5 | stop and delete the paper subscription | `yes` | No: listed gate; depends on the live state. |
| 11.6 | create and start the `exness` subscription (entries paused) | `yes` | No: first real-money object. |
| 11.8 | Resume entries for one order | `yes` | No: the real-money switch. |
| 11.11 (conditional) | accept the run without AC6 | see Q-section defaults | No: depends on the deal facts. |
| 11.12 | `pause` or `keep on` after the round trip | see Q3 | No: depends on the round-trip outcome. |
| 12.4 (Fridays with an open position) | weekend hold 1/2/3 | `2` | No: depends on the position. |
| 12.6 | declare go-live (resumes entries) | `yes` when five clean rows | No: the go-live decision. |
| Rollback [ASK]s (any phase) | revert and redeploy, flag off | case by case | No. |

[USER] steps (you act, then reply with a token): 6.11 `ui ok`; 7.1 `tunnel created` (A1 makes it skip); 8.8 `spa ok`; 9.2 `DNS cut over, 2 routes`; 9.3 `2fa on, rate rule on` (A2 + A3 make it a confirmation); 9.13 `pause ok`; 11.10 `sl seen`; 10.5 step 3 `dispatched` only if the agent's dispatch fails (`camping89` has `repo` and `workflow` scopes `[F]`, so it should not).

## 4. Verdict on the planner's deviations and concerns

| # | Deviation | Verdict |
| --- | --- | --- |
| 1 | `gh auth status --json hosts` scope check replaces `--user` form | Accept. gh 2.101.0 `[F]`; the planner ran it and it printed the scopes; `repo` and `workflow` present `[F]`. |
| 2 | Watch reads Mongo `positions` (open and closed) instead of the open-only GET | Accept; better. A position that opened and closed between polls is not missed. |
| 3 | 11.1 step 4 (first-entry pause) runs before the restart check | Accept; pausing before a stop-and-report is the safe order. |
| 4 | No concrete recommended reply for 11.11, 12.4, 12.6 | Accept; defaults supplied in section 1 for the planner to apply. |
| 5 | Probe extends to 180 days and has a `none` outcome | Accept. The snippet matches the client: `call(op, *, params=...)` (`exness_client.py:248-255`), negative `count` pages backwards from an inclusive `from` (`exness_adapter.py:57-66`), `instrument_name("XAUUSD:EXNESS")` is `XAUUSD` (`exness_mappers.py:28-36`). |
| 6 | U3 cross-reference | Accept (and it goes away under Q2). |
| 7 | npm item dropped | Accept: `node v24.21.0`, `npm 11.19.0` run tonight `[F]`; the Phase 06 gate still checks `npm --version`. |

Concern (a): see Q1. Recommendation: accept the bound (option A) and raise the watch to 4 h; option C only on your say-so. It needs your decision now only if you choose C, because Phase 05 is two phases away.

Concern (b): agreed and stronger than the planner stated; see Q2. Recommendation: remove the fallback. Needs your decision (it reverses decision (6) of 00:21).

## 5. Defects and inconsistencies in the edited plan

None stops a phase. In priority order:

1. Phase 01 is done but `plan.md:59` and `phase-01-admin-token-auth.md:4` still say Pending. The runner ignores status (it lists `phase-NN-*.md` and applies `--from`/`--to`, `eve-cook-plan/SKILL.md` "Resolve the phase list"), so this is cosmetic; fix it in the next docs commit and always pass `--from 02` or later.
2. Uncommitted plan material `[F]`: edits to `plan.md` and phases 05-12, the journal `plans/journals/2026-10-20-admin-token-guard-on-the-api-router.md`, and the two 00:10/00:21 reports. Entry gates exclude `plans/`, so Phases 02-07 are not blocked, but Phase 08's gate needs `HEAD == origin/develop`, so commit and push them (one `docs(plans)` commit) after the Phase 02 worker has committed, not while it runs. `cicd.yml` ignores `plans/**` and `**/*.md`, so that push triggers no CI.
3. `routeTree.gen.ts`: verified no effect on Phase 08's CI or Docker build (section 2, A4). Only a fresh checkout or worktree hits it at Tasks 6.12 and 8.2. No plan edit needed; a one-line note in the Phase 06/08 entry gates would be optional.
4. `IdempotencyMiddleware` `[F]`: caches POST/PATCH responses keyed only by the client-chosen `Idempotency-Key` for 24 h and replays them before routing (`core/common/idempotency/middleware.py:13-33,44-51`), so a replay skips the router guard. The SPA never sends the header and the key must be guessed, so it is a disclosure of an earlier response at most. Record it under "Out of scope (flagged)" in `plan.md`; no Phase 09 task is warranted.
5. Phase 09 Task 9.3 fallback writes a token to `pocketquant-config/cloudflare/api-token`; the directory does not exist and the repo has no ignore rule for it `[F]`. Moot under Q2; otherwise add the path to that repo's `.gitignore` in the same step.

Checked and found consistent `[F]`: the scripted snippets of Tasks 10.3, 11.2, 11.4, 11.7, 11.9, 11.11 and 12.2 against the current code (`ExnessClient(settings)`, `call`, `conditions(instrument)`, `deals_window_days()`, `close()`, `INTERVAL_TO_EXNESS`, `Interval` in `core.domain.shared.enums`, `AsyncMongoClient` with pymongo 4.16.0); `cicd.yml` has `workflow_dispatch` and gates build and deploy on `refs/heads/master`, which a dispatch with `--ref master` satisfies; `compose.prod.yml` `app.command` is a list, so Task 7.5 can append `--forwarded-allow-ips`; the committed guard test asserts `len(routes) == 17` as Task 5.9 expects; `MONGO_PORT`, `REDIS_PORT`, `PORTAINER_PORT` and `WEB_PORT` are bare numbers in the prod `.env`; `.cache/` is gitignored.

## Assumptions

- Cloudflare enforces plan entitlements identically through the Rulesets API: high. The availability page documents the limits; the API page names no bypass. The user's dashboard test (A3) settles whether the question even arises.
- The Exness M1 history edge is about one year: medium (prior plan note, not re-verified); Task 10.3's probe replaces it before any long run.
- The `camping89` classic token can dispatch `cicd.yml`: medium-high (`repo` and `workflow` scopes verified; dispatch not tested, by decision). Fallback is a UI dispatch.
- The worst-case exposure bound in Q1 assumes one `exness` subscription and a correct cap; both are verified in code, the arithmetic is mine.
- Phase 11 signal frequency is unknown; it only affects how costly option B would be.

Status: DONE_WITH_CONCERNS
Summary: No phase is blocked; three plan-text decisions (single-order guarantee, Cloudflare token fallback, 11.12 default) and three user actions (tunnel token, 2FA, rate-rule expression test) are the open items; no [ASK] should be pre-approved.
Concerns/Blockers: `TUNNEL_TOKEN` is absent, so Phase 07 will wait at Task 7.1 unless the user creates the tunnel first; an unwatched single-order run can lose up to about 50 USD per UTC day in the worst case unless the in-app pause-after-fill is added to Phase 05.
