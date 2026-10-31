# Kongming counsel: Phase 11 Task 11.3 re-arm Verify failure

Date: 2026-10-31 ~05:30 UTC. Advisory only. Repo HEAD `42c96568` (develop), compose pin from `17026288` (2026-10-30), `add_symbol` live check from `94b5a98f` (2026-10-21).

## TL;DR

Prod is armed where it matters: the trader process has `EXNESS_LIVE_TRADING=true`, and the trader is the only process that builds the Exness broker and sends orders. The Verify failed because it reads the api process, which compose pins to `false` on purpose. That is a plan-text error, not a deployment error. But the same pin breaks one real step of the go-live flow: `POST /api/v1/strategies/{code}/subscriptions` with `broker=exness` is served by the api and is refused with HTTP 400 `BROKER_DISABLED` (`strategy_command_service.py:59-63`). Fix both with plan text, no code: point every `live_trading` read and the one exness create call at the trader container, which serves the same HTTP API on its internal `:41921`. Ship no code before Monday; file two follow-ups (SPA strip shows OFF while armed; UI create path for exness is dead on the split runtime).

## Reframed problem

Decision: can go-live Phases 11-12 start on Monday on the split runtime as re-armed, and what exact text replaces the reads that assume one `pocketquant-app` process holds every role? Requirements: entries stay paused, no second `Deploy C` line, no code deploy unless something is broken, read-only verification. Non-goal: redesign the live flag.

## Verified evidence (file:line)

- The api response's `live_trading` is the serving process's own `Settings.exness_live_trading` (`app/di/adapters.py:38-44`, `app/routes/safeguards.py:33`). It is not a system-wide signal. `entries_paused` is store-backed and shared by all processes (`safeguards.py:29-33`).
- Compose pins `EXNESS_LIVE_TRADING: "false"` for `api` (`deploy/compose.prod.yml:83`) and `worker` (`:99`); the trader inherits the `.env` value (`:109-114`, `env_file` via `*backend` at `:5-8`). Red-team security finding 5 asked for this pin (`reports/red-team-security.md:9`); Phase 08 wrote it (`phase-08-topology-and-cutover-deploy-b.md:102-105`). Your container-env readout (api false, worker false, trader true) matches this.
- Live order path runs only in the trader: `BrokerFactory.create("exness")` requires `safeguards.live_trading` (`core/infra/brokers/broker_factory.py:59-63`); `ExnessClient` refuses `openPosition` unless the flag is true (`core/infra/exness/exness_client.py:46,231-232`; `_ORDER_OPS = {"openPosition"}` only). The api never calls `StrategyAppService` (`docs/system-architecture.md:10`). So trader true + api false is the intended armed state.
- The broken step: `POST /api/v1/strategies/{strategy_code}/subscriptions` (`app/routes/strategy.py:50-52`) calls `StrategyCommandService.add_symbol`, which raises `DomainError("exness broker is disabled: EXNESS_LIVE_TRADING is false", error_code="BROKER_DISABLED")` when the serving process's flag is false (`engine/strategy/strategy_command_service.py:59-63`). `DomainError` maps to HTTP 400 `{"error":{"code":"BROKER_DISABLED",...}}` (`core/common/exceptions.py:26-27,34-37,47`). Go-live Task 11.6 step 3 sends this call through `exec -T api` after the Substitutions table (`phase-11-go-live-one-strategy.md:169`). It will fail.
- `start`, `stop`, `remove_symbol` carry no flag check (`strategy_command_service.py:32-42,88-89`). Pause/resume are store writes (`safeguards.py:50-62`). The go-live Python snippets run inside `api` use `getTradingStateSnapshot`, `conditions`, `getDealsHistory`; none is in `_ORDER_OPS`, so the api's `false` does not block them.
- Every role mounts the full HTTP API: `create_app()` calls `register_routes(app, settings)` unconditionally (`app/main.py:137`; `main_extensions.py:294-359` has no role filter). The trader container therefore answers `GET /api/v1/admin/safeguards` and the create route on its own `localhost:41921`, with `live_trading` true. Admin auth reads `settings.admin_token` (`app/middleware/admin_auth_middleware.py:23`), which comes from the shared `env_file`, so `$ADMIN_TOKEN` exists inside the trader too. The trader runs the same image as the api whose healthcheck uses `curl` (`compose.prod.yml:86`), so `curl` and `python` exist there.
- SPA: the Exness strip reads `/api/v1/admin/safeguards` from the api and shows `live_trading: OFF` (`web/src/components/strategies/exness-strip.tsx:28,56-61`). The per-subscription `LIVE`/`PAPER` chip comes from the subscription row, not this flag (`strategy-card.tsx:63`).
- Go-live reads of `live_trading`: Task 11.1 Verify (`phase-11-go-live-one-strategy.md:69`) and Task 11.6 step 2 facts (`:168`). Every other `<GET safeguards>` in go-live Phases 11 and 12 reads only `entries_paused` (`phase-11:150,172,205,224,300`; `phase-12:135,151,155`).
- `reports/re-arm-log.md` does not exist yet: Task 11.3 step 9 has not run (Verify's third count would also fail). `round-trip.md` Live run 1 is closed (`round_trip: DONE 2026-10-31T04:12:31Z`), so Task 11.2 is done.
- Docs: `docs/system-architecture.md:13` names two locks (factory, client). The `add_symbol` check is a third, undocumented lock. `docs/deployment.md:125-128` reads only `entries_paused` after a deploy; no doc claims the strip's `live_trading` reflects the trader.

## Answers

### Q1. Is prod correctly armed?

Yes (fact, from the container env you read and the code above): the trader has the flag on, both real locks (factory, client) live in the trader, api and worker are pinned off by design. The Verify failure is a wrong-process read.

Not everything on the api side is harmless, though. One api-side gate blocks the go-live flow: the exness subscription create (go-live 11.6 step 3) will return 400 `BROKER_DISABLED` from the api. Nothing else in go-live 11.x/12.x depends on the api's flag: preflight scripts, pause/resume, start/stop, positions, subscriptions list and the Phase 12 reads all work with api false.

Inference (medium confidence): nobody caught this because the check predates the split (2026-10-21) and the pin landed 2026-10-30 with a security rationale; the test `test_add_symbol_accepts_exness_only_while_live_trading_is_on` (`tests/engine_test/test_strategy_service.py:151-171`) encodes the single-process assumption.

### Q2. Replacement Verify and substitutions (read-only)

Use the trader process's own safeguards response. It is exactly the `Safeguards` object the trader's `BrokerFactory` consults, so it is the strongest read-only signal, and it returns `entries_paused` from the shared store in the same call. Same JSON shape, same pass condition, one word changed (`api` -> `trader`).

Task 11.3 Verify, replacement:

```bash
grep -c "^EXNESS_LIVE_TRADING=true$" ../pocketquant-config/vps/default/.env; HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant/deploy; dc() { docker compose -f compose.prod.yml --env-file .env "$@"; }; dc exec -T trader curl -s http://localhost:41921/api/v1/admin/safeguards; echo; dc exec -T api curl -s http://localhost:41921/api/v1/admin/safeguards; echo; dc ps -q trader | wc -l'; grep -c "^Re-armed:" plans/261028-0652-exness-only-parallel-runtime/reports/re-arm-log.md
```

Pass: `1`; a trader body containing `"live_trading":true` and `"entries_paused":true`; an api body containing `"live_trading":false` and `"entries_paused":true` (the pin is intact; this is the defense-in-depth check red-team 5 asked for); `1` (one trader copy, so `exec -T trader` is unambiguous); then `1`. Keep the step 7 and step 8 conditions as written.

If you prefer an env read instead of an HTTP read, the equivalent is `dc exec -T trader printenv EXNESS_LIVE_TRADING` printing `true` (Phase 06 used this shape at `phase-06-strategy-runtime-and-restart-state.md:74`). The HTTP read is better because it proves the process parsed the value into `Settings`, not just that the env var is set.

Add two rows to the Phase 11 Substitutions table:

| Go-live text | Use here |
|---|---|
| `<GET safeguards>` where the pass condition or the facts name `"live_trading"` (go-live 11.1 Verify, 11.6 step 2) | `dc exec -T trader curl -s http://localhost:41921/api/v1/admin/safeguards` (the trader is the only process whose flag gates orders; the api pins it off). Every other `<GET safeguards>` (only `entries_paused`) stays on `api`. |
| Go-live 11.6 step 3 create call (`POST .../strategies/<code>/subscriptions` with `"broker":"exness"`) | run it through `dc exec -T trader sh -s` with the same `printf ... \| curl -H @-` form; the api refuses it with 400 `BROKER_DISABLED` (`engine/strategy/strategy_command_service.py:59-63`). The following `POST .../subscriptions/<id>/start` stays on `api`. |

Shape for the create call (replace placeholders; token never on a command line):

```bash
HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env exec -T trader sh -s' <<'EOF'
printf 'X-Admin-Token: %s\n' "$ADMIN_TOKEN" | curl -s -X POST -H @- -H 'Content-Type: application/json' -d '{"symbol":"<symbol>","interval":"<interval>","broker":"exness"}' http://localhost:41921/api/v1/strategies/<strategy_code>/subscriptions
EOF
```

Why this is safe: `add_symbol` only writes a Mongo document with `desired_state="stopped"` (`strategy_command_service.py:68-78`); the trader's reconcile loop converges it after `start`, exactly as it would for an api-created document. Precondition to state in the step: `dc ps -q trader | wc -l` prints `1` (no roll in progress; the deploy lock makes this the normal state).

Also fix the Phase 11 Context line 19 wording ("its Task 11.1 Verify needs `"live_trading":true`") to say that read must come from the trader.

### Q3. Code or compose change before Monday?

No. Nothing in the order path is broken, and the one broken api route is bypassed by calling the trader, which already serves it. A code deploy now would cost a trader re-roll and a new `StartedAt` for no Monday gain. Keep the api/worker pin: it is the reason the api cannot send an order even through a bug, and the red team asked for it.

Two follow-ups to record (not before the canary passes; the plan's Phase 09-style cleanup or a new phase):

1. User-visible defect, safety-relevant: the SPA strip shows `live_trading: OFF` while the trader is armed. The owner could read OFF as "no real money at risk". Until fixed, tell the owner plainly in the Task 11.3 record and in every [ASK] that mentions the strip: "the strip's live_trading chip reads the api process and shows OFF; the trader is armed; the Pause/Resume buttons and the `Entries paused` chip are correct." Design options, labelled speculation: (a) the trader writes its flag into its lease document on acquire and the api's GET reads it from there (the api already reads lease docs in `/health`, `main_extensions.py:322`); (b) drop `live_trading` from the api response and the strip and keep only the per-subscription `LIVE` chip. (b) is smaller and KISS; (a) keeps an armed indicator.
2. The `add_symbol` fail-fast check (`strategy_command_service.py:59-63`) can never pass in prod on the split runtime, so the UI and public API cannot create an exness subscription. Options: delete it (the two documented locks in the trader remain, and a disarmed trader fails the subscription at reconcile with the same message), or move the fail-fast into the trader's reconcile path. Deleting also fixes test `tests/engine_test/test_strategy_service.py:151-171` and the docs' "two locks" statement stays true. Decide after go-live; the plan-text bypass covers the single owner-driven create.

Rollback and D33 re-roll text in Phase 11 reads only `entries_paused` and the leases; no change needed there.

## What to avoid

- Do not remove the api/worker pin to make the Verify pass. It reverses a verified security decision for a cosmetic read.
- Do not add a second `Deploy C` line to `ship-log.md`; go-live Phase 11's gate counts exactly one (`phase-11-go-live-one-strategy.md:53`).
- Do not create the exness subscription from the SPA; it will 400 on the split runtime.
- Do not run `exec -T trader` while a deploy roll is in progress (two trader copies); check `dc ps -q trader | wc -l` first.
- Do not treat `printenv` alone as proof; prefer the HTTP read for the Verify.

## Work checklist (caller)

1. Re-run the replacement Verify above (expect trader true/paused, api false/paused, `1` trader copy).
2. Run Task 11.3 step 9 (create `re-arm-log.md`, append `Re-armed: ...` with run `41171394802` and trader StartedAt `2026-10-31T05:12:51Z`, snapshot before/after, OOM line). Add one line: `note: api and worker pin EXNESS_LIVE_TRADING=false by design; the SPA strip shows OFF; the trader is armed (trader safeguards body attached)`.
3. Edit `phase-11-re-arm-live-gate.md`: Task 11.3 Verify text; two new Substitutions rows; Context line 19 wording. Commit `docs(plans): read the live flag from the trader` with the step 2 record, push `develop`, `git fetch origin`.
4. Re-run Task 11.3 Verify (now passes on all three counts), then proceed to Task 11.4 on Monday as planned.
5. Open the two follow-ups in the plan (strip flag source; `add_symbol` api check) with the file:line evidence above.
6. `rm -f .cache/ssh/vps_key` at exit.

## Success metrics

- Trader safeguards body shows `"live_trading":true,"entries_paused":true`; api body shows `"live_trading":false,"entries_paused":true`.
- Go-live 11.6 create through the trader returns 201/200 with `"broker":"exness"`, and `tl "<created>"` shows one `exness.broker_connected`.
- Go-live 11.7 logs `exness.order_rejected_presubmit ... reason=entries_paused` for the live subscription while paused (the trader built the broker, so the trader's flag is true in practice).

## Assumptions

- The trader container has `curl` because it runs the same image as the api, whose healthcheck calls `curl` (high; `compose.prod.yml:86`). If it did not, use `dc exec -T trader python -c "import urllib.request as u;print(u.urlopen('http://localhost:41921/api/v1/admin/safeguards').read().decode())"`.
- `ADMIN_TOKEN` is present in the trader env because all three services share `env_file: .env` (high; `compose.prod.yml:5-8`, red-team 5 says the roles inherit it).
- The trader's `Settings` parsed `true` from the env you read (high; the HTTP Verify proves it directly).
- The owner reads the SPA during the live run and could misread the OFF chip (medium; this is why the follow-up is flagged as safety-relevant rather than cosmetic).
- Nothing in go-live Phase 12 or the D33 re-roll depends on the api's flag (high; grep shows only `entries_paused` reads at `phase-12:135,151,155`).

Status: DONE_WITH_CONCERNS
Summary: Prod is armed at the trader, which is the only process that can send orders; the Verify read the api, which compose pins off by design. Fix by plan text: read `live_trading` from `exec -T trader`, and route the single exness create call (go-live 11.6 step 3) through the trader because the api refuses it with 400 `BROKER_DISABLED`.
Concerns/Blockers: SPA strip shows `live_trading: OFF` while armed (owner may misread); the api/UI exness create path is dead on the split runtime. Both are follow-ups, not Monday blockers.
