# Red team: security lens

Reviewer: Security Adversary + Fact Checker. Repo `develop` @ `e4a998b8`, 2026-11-01. Plan files read: plan.md, phases 06, 09 (grep), 10, 11, 13, 15, 16, 17; packet C1-C13. Owner decisions D1-D6 and C1-C13 are not challenged; where a finding touches one, it states the risk and options only.

## Finding 1: Entries pause and daily loss cap do not stop a resting Exness stop
- **Severity:** High
- **Location:** Phase 10, Task 10.4 (Implement, parking and fill branch); Task 10.5
- **Flaw:** The pause and loss-cap checks run once, at placement in `_submit_open`. A parked stop fills later through `_apply_success` with no re-check. Nothing cancels parked stops when entries are paused. The break-glass runbook still says a pause stops real-money entries.
- **Failure scenario:** Live is armed. The site is down and the owner pauses entries over SSH, as the runbook says. A stop placed an hour earlier triggers at the venue. A new real-money position opens after the pause.
- **Evidence:** Plan 10.4: "A fill is an open deal whose `link_field` names a parked venue id ... re-registers `_Inflight(order, name, now)` and calls `_apply_success`". The pause check exists only inside `_submit_open` (`src/pocketquant/core/infra/brokers/exness/exness_broker_adapter.py:219-237`, `load_entries_paused` at `:221`). The runbook is `docs/deployment.md:110-118` ("Pause entries over SSH ... Then close any open position in the Exness app"). It says nothing about pending orders.
- **Suggested fix:** In 10.4, make a pause and a loss-cap breach cancel every parked stop. Add `test_a_pause_cancels_the_resting_stop`. Add "cancel pending orders" to the runbook in `docs/deployment.md`. At minimum, add a Limitations bullet in 10.5.

## Finding 2: Manual close and strategy EXIT are blocked whenever the stop cancel fails, and after a restart the Exness cancel always fails
- **Severity:** High
- **Location:** Phase 11, Task 11.2 step 5; Phase 09, Task 09.4 steps 3 and 9; Phase 10, Task 10.4 (`cancel_order`)
- **Flaw:** `manual_action` returns False before the close when `_cancel_stop` fails. The engine restores `pending_stop` from Mongo at takeover. The Exness adapter only knows the in-memory `_parked` entries, and they are lost on restart (R5). So `cancel_order` misses, the close is never sent, and reconcile retries the action forever.
- **Failure scenario:** A deploy or handover happens while an Exness stop rests. The plan keeps resting stops on handover. The owner presses Close at market. Every 5 s the cancel misses, the call returns False and no DELETE is sent. Only the venue SL protects the position. Each tick logs `strategy.pending_cancel_failed` at WARNING. The strategy's own EXIT is blocked by the same rule: "if it is set and `_cancel_stop` fails, call `on_order_rejected` and return".
- **Evidence:** Plan 11.2 step 5: "A pending stop is cancelled through `_cancel_stop`, and a failed cancel returns False." Plan 10.4: `cancel_order` "finds the parked entry ... a miss returns False". Plan 09.4 step 9 restores `stops = [... pending_stop(sid) ...]`. `find_pending` returns `submitted` orders (`src/pocketquant/core/infra/persistence/repositories/order_repository.py:20-25`). The reconcile period is `reconcile_interval_seconds: float = 5.0` (`src/pocketquant/core/config.py:96`). Plan.md says "Engine `stop()` (handover) keeps resting stops".
- **Suggested fix:** Keep the order cancel-then-close (design verdict), but do not let a failed cancel block the close. Close whenever a position is open, and return False only when the close itself fails. Add `test_a_manual_close_runs_when_the_cancel_fails` and the same case for EXIT.

## Finding 3: A queued real-money action can never be withdrawn, and a refused venue call keeps it queued forever
- **Severity:** High (latent while live is disarmed)
- **Location:** Phase 11, Task 11.2; Phase 10, Task 10.3 (refused close returns False); Phase 13, Task 13.4 step 3
- **Flaw:** The action is set only when it is null and cleared only after it succeeds. No route clears it. `LIVE_TRADING_DISABLED`, `NOT_CONFIGURED`, a market-closed refusal and a 429 all count as "a venue call fails", so the action stays queued. The UI disables both buttons while an action is queued.
- **Failure scenario:** An Exness position is held while the flag is off (for example, it is disarmed after a go-live), or the market is closed for the weekend. The owner presses Close. The request is retried every 5 s. Days later the flag is armed or the market opens, and the position closes at that moment with no fresh confirmation. In the meantime every new request gets 409 `ACTION_PENDING`, and the only way out is a manual Mongo edit.
- **Evidence:** Plan 11.2 step 3: `update_one({"_id": id, "manual_action": None}, ...)`. Step 6: "a failed action stays for the next tick". Context: "Dropped: ... a 30 s expiry ... `/cancel-pending` path". Plan 10.3: `LIVE_TRADING_DISABLED` → False. Fence: `src/pocketquant/core/infra/exness/exness_client.py:231-232`.
- **Suggested fix:** This touches D6 (no expiry). The owner picks one of these; none reverses D6:
  - (a) Treat `LIVE_TRADING_DISABLED` and `NOT_CONFIGURED` as terminal: clear the action and log ERROR `manual_action.refused`.
  - (b) Refuse the route with 409 for an `exness` subscription while live trading is off.
  - (c) Add `DELETE /subscriptions/{id}/action` so the owner can withdraw it. This makes the guard count 21.

## Finding 4: The go-live warning is corrupted in the plan text, its Verify passes on the corruption, and it never reaches the go-live runbook
- **Severity:** High
- **Location:** Phase 10, Task 10.5 step 2 and Verify
- **Flaw:** Step 2 has a Verify line pasted into the middle of the bullet text. The executor copies text literally, so it would write that garbage into `docs/system-architecture.md`. The Verify regex `Exness pending stop|...` matches the garbage line itself, so the check passes. The R5 and pause gaps go only into the architecture doc. The operator arms live from `docs/deployment.md`, which the phase does not touch.
- **Failure scenario:** Live is later armed by following `deployment.md` ("Only an approved go-live sets `EXNESS_LIVE_TRADING=true`"). R5 is not fixed and no doc on that path warns about it. After the first restart, the resting stops are no longer tracked and the instrument is blocked (Finding 2).
- **Evidence:** Plan 10.5 step 2: "Add the link-field fact recorded in 10.1: "- An **Verify:** `grep -c -E "Exness pending stop|..." docs/system-architecture.md` prints a number of at least `2`. fill is linked to its order by the deal field `<link_field>`". The go-live line is `docs/deployment.md:79`. The phase 10 Files list does not include `docs/deployment.md`.
- **Suggested fix:**
  - Rewrite step 2 as a clean bullet.
  - Make Verify grep each exact bullet sentence with `grep -c -F`.
  - Add one go-live line beside `deployment.md:79`: "Before arming: Exness pending stops are not re-adopted after a restart, and a pause does not cancel them."

## Finding 5: The live flag is never re-checked before release, and the cited evidence covers the wrong containers
- **Severity:** Medium
- **Location:** Phase 15, Context and Entry gate 5, Task 15.3 [ASK]; Phase 16 entry gate
- **Flaw:** Phase 15 rests "live stays disarmed" on the compose pins for api and worker. The trader is the only role that trades, and the compose file does not pin it. Its flag comes from `pocketquant-config/.env`. No gate reads the trader's flag. A check run through PRODPY would execute in `api`, which is pinned to false, so it would print false whatever the trader holds.
- **Failure scenario:** Between today and D-2, a config edit or the sibling go-live plan sets the flag true. The release ASK still says "behind the disabled live flag". The close, pending and cancel ops ship armed, and the UI enables LIVE in the create form (Phase 13.3 reads `useSafeguards().data?.live_trading`).
- **Evidence:**
  - Phase 15 line 24: "compose pins `EXNESS_LIVE_TRADING: "false"` for api and worker (`deploy/compose.prod.yml:83,99`)".
  - The trader service is at `deploy/compose.prod.yml:109-114` with no pin; the comment at `:75` says "trader may trade live".
  - Today `pocketquant-config/vps/default/.env:63` holds a 5-character value matching `false` (the value was not printed).
- **Suggested fix:** Add an entry-gate line to Phases 15 and 16 that runs inside the trader container: `docker compose ... exec -T trader python -c "from pocketquant.core.config import get_settings; print('trader_live=' + str(get_settings().exness_live_trading))"`, expecting `trader_live=False`. Also correct the Context sentence.

## Finding 6: The new read endpoints publish the pending stop, SL/TP and strategy readings to the internet without a token
- **Severity:** Medium
- **Location:** Phase 11, Task 11.3 (`/snapshot`, `/orders`, enriched `list_symbols`)
- **Flaw:** GET skips the admin guard, and nginx proxies `/api/` publicly. The public subscription list enumerates the ids. The ring carries `pending {stop_price, sl_price, tp_price}` and the readings. `/orders` carries `stop_price, sl_price, tp_price`. Positions and trades are already public (`strategy.py:88-103`), so this exposure is incremental. It is new for resting trigger prices.
- **Failure scenario:** Once live is armed, anyone can read the account's resting stop trigger price and SL from `https://pocketquant.xyz/api/v1/subscriptions/<id>/snapshot`.
- **Evidence:**
  - Safe methods return early: `src/pocketquant/app/middleware/admin_auth_middleware.py:10,19-20`.
  - Public proxy: `web/nginx.conf:30-32`. Public API docs: `docs/deployment.md:54-55`.
  - The plan itself reads `/snapshot` with no header (Phase 17.1, Phase 16.6).
- **Suggested fix:** Question for the owner (the threat model depends on intent). Options:
  - (a) Accept it and state it in `docs/system-architecture.md`.
  - (b) Require the token on GET for every route that is not an SSE stream.
  - (c) Put Cloudflare Access in front of `/api/`.

## Finding 7: Parameter values are not type-checked, so wrong types return 500 or break the trader silently
- **Severity:** Medium
- **Location:** Phase 06, Task 06.1 step 3 (`check_strategy_inputs`); Phase 14, Task 14.2 step 2 (Triple Screen `__init__`)
- **Flaw:** Validation checks the keys against `DEFAULTS` and maps only `ValueError`. Triple Screen checks "every integer is `>= 1`" but not the type. `True >= 1` and `12.5 >= 1` both pass. `"5" >= 1` raises `TypeError`, which turns into a 500.
- **Failure scenario:** `{"stop_lookback": 2.5}` or `{"macd_fast": 12.5}` is accepted, stored and loaded by the trader. Every entry bar then logs `strategy_on_bar_error` at ERROR, and the row looks healthy. `{"macd_fast": "12"}` on create or on backtest run returns 500 `INTERNAL_ERROR` instead of 422.
- **Evidence:**
  - Plan 06.1 step 3: "`INVALID_PARAMETERS` ... when `cls(...)` raises `ValueError`".
  - Handler chain: `src/pocketquant/core/common/exceptions.py:64-67`. Only `ValueError` and `AppError` map to 4xx.
  - Per-bar catch: `src/pocketquant/engine/strategy/strategy_app_service.py:391-393`.
- **Suggested fix:** Add one generic rule in `check_strategy_inputs`: a value's type must equal the type of its default. A float default may take an int; an int default never takes a bool. Otherwise raise `INVALID_PARAMETERS`. Catch `(ValueError, TypeError)`. Add two tests.

## Finding 8: The `pending` shape differs across C7, Phase 11 and Phase 13, so the real-money row and confirmation show no price
- **Severity:** Medium
- **Location:** Phase 11, Task 11.1 step 6; Phase 13, Task 13.1 step 2 and Task 13.2 step 1
- **Flaw:** Three shapes are in play:
  - C7 fixes `pending{side, price}`.
  - Phase 11 writes `{side, stop_price, sl_price, tp_price}`.
  - Phase 13 types `pending: { side: string; price: number }` and pins `pendingText({ side: 'buy', price: 71250 })` in a test.
  
  Task 13.1 says "the code wins", but the tests and the types in 13.2 are written against `price`.
- **Failure scenario:** The row shows `BUY STOP @ undefined`/`NaN` next to the Cancel pending control. Or the executor hits a `tsc` and vitest conflict it cannot resolve, and the Failure Protocol fires.
- **Evidence:** `reports/debate-evidence-packet.md` C7. Plan 11.1 step 6: `"pending": None or {side, stop_price, sl_price, tp_price}`. Plan 13.2: `pendingText({ side: 'buy', price: 71250 })`.
- **Suggested fix:** Use one shape, C7's `price` (plus `sl_price` if wanted), in Phase 11, and align the Phase 13 types and tests to it.

## Finding 9: The push recipe puts the GitHub token on git's command line, against the plan's own rule
- **Severity:** Medium
- **Location:** plan.md Ops recipe "Push"; Phase 10 Task 10.6 step 4, Phase 11 Task 11.5 step 5, Phase 15 Task 15.5 step 2, and every CLOSE
- **Flaw:** The Conventions say "Secrets never go on a command line". The recipe expands `$(gh auth token ...)` into git's argv as part of the URL. The token is visible in the local process list for the whole push. Whether git echoes the URL with its credentials in error output is [UNVERIFIED]; that depends on the git version.
- **Failure scenario:** Any local process listing, or a crash dump taken during a push, captures the token. That token has push rights to `master`, and a push to `master` deploys prod.
- **Evidence:** plan.md Conventions ("Secrets never go on a command line or into the repo") versus Ops recipe ("`git push "https://x-access-token:$(gh auth token --user camping89)@github.com/..."`").
- **Suggested fix:** Use a credential helper, so the token is produced by a shell builtin and never becomes an argv value: `git -c credential.helper= -c 'credential.helper=!f() { echo username=x-access-token; echo "password=$(gh auth token --user camping89)"; }; f' push https://github.com/camping89/pocketquant.git develop`. If this recipe is a deliberate owner workaround (account quirk), keep it and delete the contradicting rule instead.

## Fact check

### Phase 10
| Claim | Result | Evidence |
|---|---|---|
| `_ENDPOINTS` `:27-45` | VERIFIED (starts `:28`) | `exness_client.py:28` |
| `_ORDER_OPS` `:46` = `{"openPosition"}` | VERIFIED | `exness_client.py:46` |
| `_PRIORITY_OPS` `:47` derives from `_ORDER_OPS` (new ops auto-join the order pacer) | VERIFIED | `exness_client.py:47,330` |
| Live fence `:231-232` | VERIFIED | `exness_client.py:231-232` |
| Order ops never retried on 429 `:276` | VERIFIED | `exness_client.py:276` |
| `order_request_interval` tuple `:115` | VERIFIED (`:115`) | `exness_client.py:112-116` |
| limits fixture lists the three ops at 4/1 s | VERIFIED | `tests/core_test/infra/exness/fixtures/limits.json:23-64` |
| `submit_order` rejects non-market `:209-214` | VERIFIED | adapter `:209-214` |
| `_submit_open` `:216`, `_open_lock` | VERIFIED | adapter `:216,219` |
| `_send_tracked` hardcodes `"openPosition"` | VERIFIED | adapter `:385,392` |
| `_watch_operation` `:430`, `_recover_fill` `:454` | VERIFIED | adapter `:430,454` |
| `_on_snapshot` `:486`, `_on_transaction` `:547`, `_on_broker_close` `:574` | VERIFIED | adapter |
| `exness.position_closed_by_broker` `:591` | VERIFIED | adapter `:591` |
| `cancel_order` returns False `:750-752` | VERIFIED | adapter `:750-752` |
| `_close_reason` `:802` | VERIFIED | adapter `:802` |
| `snapshot.json` has an empty `orders` | VERIFIED | `tests/core_test/infra/exness/fixtures/snapshot.json:8` |
| `_FakeClient.call` raises `AssertionError` for unknown ops `:85-105` | VERIFIED | test adapter `:85-105` |
| LIMIT case expects "market orders only" `:227` | VERIFIED | test adapter `:227` |
| `test_exness_open_path.py:15-20` imports the four helpers | VERIFIED | `:15-20` |
| Fence test `test_exness_client.py:273` | VERIFIED | `:273` (assert `:284`) |
| Task 10.1 "Write six lines" versus Verify `prints 7` | FAILED (internal mismatch: 7 keys listed) | plan 10.1 step 3 / Verify |

### Phase 11
| Claim | Result | Evidence |
|---|---|---|
| Guard test asserts 17 on HEAD | VERIFIED | `tests/app_test/integration/test_admin_token_guard.py:46` |
| 17 = actual mutation routes | VERIFIED (market_data 5, tracked 3, safeguards 2, strategy 4, backtest 3) | `git grep` of `app/routes` |
| Guard is router-level, so new routes are covered automatically | VERIFIED | `app/main_extensions.py:332-336` |
| GET skips the guard | VERIFIED | `admin_auth_middleware.py:10,19-20` |
| `Cache.get/mget/set` `:44-85` | VERIFIED | `redis.py:44,59,66` |
| Cache provided `infrastructure.py:62` | VERIFIED | `:62` |
| Engine factory `services.py:122-153` | VERIFIED | `:122-153` |
| `StrategyQueryService` auto-provided `services.py:214` | VERIFIED | `:214` |
| Reconcile starts after `take_over()` `roles.py:203-205` | VERIFIED | `:203-205` |
| `trading_until` None in standby `:90-92` | VERIFIED | `strategy_app_service.py:90-92` |
| `_reconcile` `:77-111` | VERIFIED | `strategy_reconcile_app_service.py:77` |
| `ix_orders_subscription_id` `:29` | VERIFIED | `order_repository.py:29` |
| `find_open(limit=200)` `:20` | VERIFIED | `position_repository.py:20` |
| `IStrategyService.__init__` `:17-22` | VERIFIED | `strategy_service_interface.py:17-22` |
| Per-bar strategy errors isolated | VERIFIED | `strategy_app_service.py:391-393` |
| `pending` shape matches C7 | FAILED | Finding 8 |

### Phase 15
| Claim | Result | Evidence |
|---|---|---|
| compose pins live off for api and worker `:83,99` | VERIFIED | `compose.prod.yml:83,99` |
| …therefore live stays disarmed | FAILED as evidence (trader not pinned) | `compose.prod.yml:75,109-114`; Finding 5 |
| prod `.env` flag false today | VERIFIED (value length 5, matches `false`) | `pocketquant-config/vps/default/.env:63` |
| Old index `:79-83` | VERIFIED | `subscription_repository.py:79-83` |
| `Subscription.from_mongo` `:52` | VERIFIED | `entities.py:52` |
| `BacktestResult.from_mongo` `:78` | VERIFIED | `backtest/entities.py:78-79` |
| `reconcile.failed` `:73` | VERIFIED | `strategy_reconcile_app_service.py:73` |
| Re-roll `IMAGE_TAG=sha-<short> bash deploy/vps/10-deploy.sh` `:9` | VERIFIED | `10-deploy.sh:9` |
| api port 41921 `:78` | VERIFIED | `compose.prod.yml:78` |
| `admin_token` `config.py:85` | VERIFIED | `config.py:85` |
| `.cache` is git-ignored (`vps_key`, `f.py`) | VERIFIED | `.gitignore:42` (`git check-ignore`) |
| Restore drops paper rows with no exits `:157-165` | VERIFIED | `strategy_app_service.py:157-165` |
| Rollback filter `$ne [$intervals_key, $interval]` picks only new-shape docs | VERIFIED by reading (legacy docs have equal values) | Phase 15 Rollback |
| `{"$literal": {}}` is needed | UNVERIFIED (plan says so itself) | Phase 15 Open issue |
| `cicd.yml:192-247` deploy steps | UNVERIFIED (not opened) | — |

### Phase 17 (delete filter)
| Claim | Result | Evidence |
|---|---|---|
| Live trades link by `run_id` = subscription id | VERIFIED | `trade_repository.py:24-28` |
| Backtest trades are in a separate collection (orphan `trades` filter cannot hit the Phase 16 runs) | VERIFIED | `backtest_trade_repository.py:12`; `backtest_app_service.py:151` |
| `Trade` fields start `:85` | VERIFIED | `trading/value_objects.py:85-87` |
| `_fire_synthetic_exit` `:528` | VERIFIED | `paper_broker_adapter.py:528` |
| paper `cancel_order` no-op `:224-226` | VERIFIED (`:225`) | `paper_broker_adapter.py:225` |
| `fetch_ohlcv` `:28` | VERIFIED | `exness_adapter.py:28` |
| `is_configured`, `close()` `:172-186,364` | VERIFIED | `exness_client.py:186,364` |
| `getCandleHistory` is not an order op | VERIFIED | `exness_client.py:37,46` |
| `TrackedSymbolService.remove` `:93-139` | VERIFIED (`remove` at `:120`) | `tracked_symbols_service.py:120` |
| PRODPY runs in `api` (pinned live off), so the comparison cannot send an order | VERIFIED | `compose.prod.yml:83` |
| Exact `_id` lists, children first, `deleted_count` per kind, guard counts | VERIFIED by reading the script | Phase 17.3, 17.6 |
| `assert PAPER not in S` protects the new subscription | VERIFIED by reading | Phase 17.3 |
| Orphans computed against all subscription ids, then the STF ids removed | VERIFIED by reading | Phase 17.3 |
| A doc with a missing `subscription_id` counts as an orphan (`$nin`) | VERIFIED (Mongo `$nin` matches a missing field) | — |
| No finding in the delete filter itself | — | — |

### Fence hardening note (no finding)
The parametrized fence test (10.2) covers the named ops only. Today every non-GET endpoint is in `_ORDER_OPS`, and after 10.2 this still holds (POST `/orders`, DELETE `/orders/{order_id}`, DELETE `/positions/{position_id}`). A one-line structural test, `{op for op, (m, _) in _ENDPOINTS.items() if m != "GET"} <= _ORDER_OPS`, would keep a future write op (for example `modifyOrder`, present in `limits.json:31-38`) from shipping unfenced.

Status: DONE
Summary: 9 security findings (4 High, 5 Medium) and a fact check across phases 10, 11, 15 and 17. Most claims are verified. Two failed: Phase 15's evidence that live is disarmed, and the `pending` shape compared with C7.
Concerns: Findings 3 and 6 need owner choices (D6-adjacent, public read threat model). Finding 4 is a plan text corruption that an executor will copy into docs as written.
