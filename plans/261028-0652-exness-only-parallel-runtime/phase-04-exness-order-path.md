---
phase: 4
title: "Exness order path: stored pause, opposite rejection, in-flight guard, caches, order pacer lane"
status: done
priority: P1
effort: 1.5d
dependencies: [3]
---

# Phase 04 — Exness order path (one process, no deploy)

## Goal

Make the single-process Exness open path safe to split later and fast enough for 1m entries: the entry pause is read from Mongo on every open and fails closed; an opposite-side entry is rejected on paper and on Exness and the Exness close path is gone; one open is in flight per subscription, and only the cheap check-and-register section is serialized; the balance and the realized loss are cached so a fresh open makes exactly one REST call; order calls get their own pacer lane. Live trading stays off. This phase ends with CI green on `develop`; nothing is deployed.

## Context

Line numbers are from `develop` @ 453e8e90. Phase 03 edits `app/di/adapters.py` and may shift its lines, so locate every target by its symbol first (`grep -n`).

- The pause lives in memory: `Safeguards.entries_paused` and `set_entries_paused` (`src/pocketquant/core/infra/brokers/exness/exness_safeguards.py:24-31`), loaded once at boot (`app/di/adapters.py:49-59`, `get_safeguards`), flipped in memory before the store write (`app/routes/safeguards.py:43-49`). The adapter reads the flag (`exness_broker_adapter.py:245-253`, `_presubmit_reason`). Store: `SafeguardsRepository.load_entries_paused` / `save_entries_paused` (`core/infra/persistence/repositories/safeguards_repository.py:16-28`).
- Stale comment: `app/di/services.py:171` ("Taking the safeguards also loads the stored entry pause before bootstrap.").
- Close path (D11): opposite order -> `closePosition` (`exness_broker_adapter.py:199-214`); `_Inflight.kind/position_id` (`:80-88`); `_recover_fill` matches `inflight.kind` (`:397-404`); `_on_transaction` matches `inflight.kind` (`:493-499`); `_apply_success` close pop (`:542-544`) and its trade hand-off (`:566`); `_finish`/`_complete` carry `trade` (`:568-584`); `_early` holds `(OrderResult, _Trade | None)` (`:118`); `closePosition` endpoint and `_ORDER_OPS` (`core/infra/exness/exness_client.py:57-60`). Broker-side closes keep `_emit_trade` (`_on_broker_close` `:516-532`, `_close_missing` `:472-486`).
- Paper today: an opposite fill reduces or closes the mirror (`engine/execution/position_app_service.py:94-128`) and the paper broker covers the position (`core/infra/brokers/paper/paper_broker_adapter.py:378-406`). `RiskCheckHandler.validate` has no side rule (`engine/execution/risk_check.py:14-47`). D30: reject opposite entries on paper too; exits are SL/TP only. The three shipped strategies never signal while `_open_direction` is set (`hitnrun2_strategy_service.py:97`, `engulfing_strategy_service.py:96`, `engulfing_pullback30_touch_strategy_service.py:119`), so backtest results of shipped strategies do not change [inference from those lines].
- Registration and send: `_send_tracked` registers `_inflight[rid]` and `_pending_ack` and sends (`exness_broker_adapter.py:317-370`); checks run in `_submit_open` (`:216-243`) across awaits with no lock.
- Pre-order reads: `_loss_cap_reason` -> `_realized_today` -> paged `getDealsHistory` on every open (`:265-305`); `get_balance` calls `getTradingStateSnapshot` every time (`:656-669`).
- Pacer: one `_RequestPacer` with a priority heap (`exness_client.py:147-195`), interval = strictest rate x 1.2 / fraction (`:116-120`, `:348-356`). Fixture `tests/core_test/infra/exness/fixtures/limits.json`: global 10/s, `openPosition` 4/s, `getOperationStatus` 10/s, strictest data 2/s. A5: order lane interval = `max(window/limit x 1.2 for openPosition and getOperationStatus, global window/limit x 1.2 / fraction)` = 0.3 s at fraction 0.6; data lane stays `min_request_interval / fraction` = 1.0 s.
<!-- Red team 2026-10-28: #8 -->
- Rate limit: `RateLimitMiddleware.dispatch` skips every request whose path starts with `_UNLIMITED_PREFIX = "/api/v1/admin/safeguards"` (`src/pocketquant/core/common/rate_limit/middleware.py:7,39-40`), GET included; admin auth skips GET (`src/pocketquant/app/middleware/admin_auth_middleware.py:23,35`). The GET route is public, so once it reads Mongo (Task 4.1) an internet flood would load the store the fail-closed open path reads. Tests: `tests/core_test/unit/common/test_rate_limit_middleware.py` (`_client` builds a Starlette app with `capacity=1`, `:31-40`; `test_pause_is_never_rate_limited` `:50-55`).
<!-- Red team 2026-10-28: #5 -->
- Send path: `OrderAppService.submit(order, broker)` calls `broker.submit_order(order)` (`engine/execution/order_app_service.py:37-53`); `IBrokerPort.submit_order(order)` (`core/domain/brokers/broker_port.py:44`) has two implementations in `src` (Exness `:199`, paper `paper_broker_adapter.py:154`) and two test fakes (`tests/engine_test/test_async_broker_fill_wiring.py:67`, `tests/engine_test/test_strategy_reject_delivery.py:73`). In the client, `_send_paced` waits on the pacer and then calls `_send` (`exness_client.py:289-312`); `_send` resends a transport failure up to `_TRANSPORT_ATTEMPTS = 3` with `asyncio.sleep(2**attempt)` between attempts (`:63`, `:314-334`); order calls never retry a 429 (`:305-307`). A transport error makes the adapter reconcile before the next open (`exness_broker_adapter.py:337-339`).

**Data flow after this phase.** `submit_order(order, deadline=...)` (market only) -> `_submit_open` takes `self._open_lock` -> stored pause read (fail closed) -> held check (any side rejects) -> in-flight check -> presubmit gates -> stop loss -> loss cap (cache, or synchronous read when stale) -> conditions (client cache 1 h) -> lot grid -> deadline check -> register `_inflight[rid]` and `_pending_ack` -> release the lock -> order-lane pacer wait -> deadline check -> `openPosition` (a transport failure is resent only while the deadline has not passed). <!-- Red team 2026-10-28: #5 -->

**File ownership.** Only this phase edits `exness_broker_adapter.py`, `exness_client.py`, `exness_safeguards.py`, `broker_factory.py`, `app/routes/safeguards.py`, `app/di/adapters.py`, `engine/execution/risk_check.py`, `core/common/rate_limit/middleware.py` and their tests; `app/di/services.py` loses one comment line; `broker_port.py`, `paper_broker_adapter.py` and `order_app_service.py` gain only the `deadline` keyword of Task 4.6. Phases 06 and 07 edit some of these files later, never in parallel. <!-- Red team 2026-10-28: #5 #8 -->

## Entry gate

Run each command from `D:/w/_me/algotrading/pocketquant`:

1. `git fetch -q origin && echo "branch=$(git rev-parse --abbrev-ref HEAD) dirty=$(git status --porcelain -- src web deploy tests scripts docs | wc -l | tr -d ' ') synced=$(test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo yes || echo no)"` prints `branch=develop dirty=0 synced=yes`.
2. `git grep -l -i -E "tradingview|cme_globex" -- src | wc -l | tr -d ' '` prints `0` (Phase 03 merged). <!-- Red team 2026-10-28: #10 -->
3. `uv run lint-imports | tail -1` prints `Contracts: 6 kept, 0 broken.`
4. `docker ps > /dev/null 2>&1 && echo docker-ok` prints `docker-ok`. If not, start `"/c/Program Files/Docker/Docker/Docker Desktop.exe" &`, wait 10 s and re-run once.

On a resume after this phase's own unpushed commits (plan.md Conventions, Resume), line 1 may print `synced=no`; that passes when `git rev-list --count HEAD..origin/develop` prints `0` (only this phase's commits are ahead).

On any miss: edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <which gate line failed and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261028-0652-exness-only-parallel-runtime --from 04 after <UTC time>
```

## Files to create/modify

- Modify: `src/pocketquant/core/infra/brokers/exness/exness_safeguards.py`, `src/pocketquant/core/infra/brokers/exness/exness_broker_adapter.py`, `src/pocketquant/core/infra/brokers/broker_factory.py`, `src/pocketquant/core/infra/exness/exness_client.py`, `src/pocketquant/app/routes/safeguards.py`, `src/pocketquant/app/di/adapters.py`, `src/pocketquant/app/di/services.py` (one comment), `src/pocketquant/engine/execution/risk_check.py`, `src/pocketquant/core/common/rate_limit/middleware.py` (#8), `src/pocketquant/core/domain/brokers/broker_port.py`, `src/pocketquant/core/infra/brokers/paper/paper_broker_adapter.py` and `src/pocketquant/engine/execution/order_app_service.py` (the `deadline` keyword only, #5). <!-- Red team 2026-10-28: #5 #8 -->
- Modify tests: `tests/core_test/infra/brokers/exness/test_exness_broker_adapter.py`, `tests/core_test/infra/brokers/exness/test_exness_broker_factory.py`, `tests/core_test/infra/exness/test_exness_client.py`, `tests/app_test/integration/test_safeguards_api.py`, `tests/engine_test/test_risk_check.py`, `tests/engine_test/test_paper_position_lifecycle.py`, `tests/core_test/unit/common/test_rate_limit_middleware.py` (#8); the other `BrokerFactory(...)` test constructors (#14): `tests/core_test/infra/brokers/paper_broker_commission_test.py:152`, `tests/engine_test/test_async_broker_fill_wiring.py:163`, `tests/engine_test/test_contract_spec_wiring.py:66,256`, `tests/engine_test/test_live_trade_collector_integration.py:83`, `tests/engine_test/test_reconcile_restart_resume_integration.py:69`, `tests/engine_test/test_strategy_reject_delivery.py:102`; the two fake brokers' `submit_order` (#5): `tests/engine_test/test_async_broker_fill_wiring.py:67`, `tests/engine_test/test_strategy_reject_delivery.py:73`. <!-- Red team 2026-10-28: #5 #8 #14 -->
- Create tests: `tests/core_test/infra/brokers/exness/test_exness_open_path.py`.

## Tasks

<!-- Added 2026-10-29 after the Phase 03 checkpoint -->
**Corrections (2026-10-29).**
- Anchors moved after Phase 03: `app/di/services.py:171` is now `:168`; `tests/engine_test/test_contract_spec_wiring.py:66,256` is now `:67,257`. Locate by symbol.
- Task 4.1 missed a caller: `tests/engine_test/test_exness_clamp_fill_position.py:47` builds `ExnessBrokerAdapter(client, bus, repo, Safeguards(...))` positionally; it passes a fifth argument `AsyncMock()` (its pause read returns a truthy mock, so pass an object whose `load_entries_paused` returns `False`). Added to Modify tests.
- Task 4.4 race: a close event can land while `_refresh_caches` or `_loss_cap_reason` is awaiting `_realized_today`, and the stale value would then overwrite the `None`. Add `self._realized_invalid_at = 0.0`; both close paths set it to `time.monotonic()` beside `self._realized = None`; every writer of `_realized` records `started = time.monotonic()` before the read and stores only when `started > self._realized_invalid_at`. Add `test_a_close_during_the_deals_read_keeps_the_cache_stale`: wrap `_realized_today` so it delivers a broker close event before returning; after `_refresh_caches()`, `h.broker._realized is None`.
- Task 4.7 step 1 uses the Phase 03 baseline form: `ruff check` passes; `ruff format --check` and `pyright` report no more than the baseline at the phase start (11 files, 25 errors), all in files this phase does not touch.
- Tasks run serially (shared files). The only accepted parameter without a second caller is `deadline`.


### Task 4.1 — The entry pause lives only in the store

**Goal:** a pause written by any process stops the next open of every process; an unreadable store refuses the open; a failed store write is reported as 503.

**Target files and symbols:** `Safeguards` (`exness_safeguards.py:10-31`); `AdaptersProvider.get_safeguards`, `get_broker_factory` (`app/di/adapters.py`); `BrokerFactory.__init__`, `create` (`broker_factory.py:22-84`); `ExnessBrokerAdapter.__init__`, `_submit_open`, `_presubmit_reason` and module docstring (`exness_broker_adapter.py:1-15,98-108,216-263`); `get_safeguards`, `pause_entries`, `resume_entries`, `_set_entries_paused` (`app/routes/safeguards.py:24-49`); comment `app/di/services.py:171`.

**Steps:**
1. Tests first. In `tests/core_test/infra/brokers/exness/test_exness_broker_adapter.py`: add class `_PauseStore` with attributes `paused: bool = False`, `error: Exception | None = None` and `async def load_entries_paused(self) -> bool` that raises `error` when set, else returns `paused`. `_Harness.__init__` builds `self.pause = _PauseStore()` and passes it as the fifth constructor argument of `ExnessBrokerAdapter`. Rewrite `test_paused_open_is_rejected_before_any_venue_call` and `test_resumed_open_is_sent` to set `h.pause.paused` instead of calling `set_entries_paused`. Delete `test_paused_close_of_a_held_position_is_sent` (the close path goes in Task 4.2). Add `test_an_unreadable_pause_refuses_the_open`: `h.pause.error = RuntimeError("mongo down")`; result is `REJECTED`, `error_message == "entries pause unreadable"`, `h.client.calls == []`, one captured log with `event == "exness.order_rejected_presubmit"` and `reason == "pause_unreadable"`.
2. In `tests/app_test/integration/test_safeguards_api.py`: change `_client` to yield `(client, app)` and update its three uses. Change the expected GET body of `test_pause_and_resume_flip_the_entry_pause` only if the key order changes (the keys stay the same six). Add `test_a_route_pause_refuses_the_next_open_of_another_adapter`: inside `_client(settings)`, POST `/pause`, then `repo = await app.state.dishka_container.get(SafeguardsRepository)`; import `_Harness` and `_order` from `tests.core_test.infra.brokers.exness.test_exness_broker_adapter`, build `h = _Harness()` and set `h.broker._safeguards_repo = repo` (no snapshot is needed: the pause read comes first); submit `_order()`; assert `REJECTED`, `error_message == "entries paused"`, `h.client.ops("openPosition") == []`. Add `test_a_failed_pause_write_returns_503`: `monkeypatch.setattr(SafeguardsRepository, "save_entries_paused", <async fn raising RuntimeError>)`; POST `/pause` returns `503` with `{"detail": "pause not stored"}`; GET still shows `"entries_paused": false`. Add `test_safeguards_has_no_entries_paused_field`: `"entries_paused" not in Safeguards.__dataclass_fields__`. <!-- Red team 2026-10-28: #8 --> Add `test_reads_within_a_second_share_one_store_read`: wrap `SafeguardsRepository.load_entries_paused` with `monkeypatch` so it counts calls and then calls the original; inside `_client(settings)`, five GETs in a row return 200 and the counter is `1`. The existing `test_pause_and_resume_flip_the_entry_pause` keeps proving that a GET right after a POST shows the new value (the POST refreshes the cache).
   In `tests/core_test/unit/common/test_rate_limit_middleware.py`: add `Route("/api/v1/admin/safeguards", _ok, methods=["GET"])` to `_client`; add `test_a_safeguards_read_flood_gets_429`: `[client.get("/api/v1/admin/safeguards").status_code for _ in range(2)] == [200, 429]`. `test_pause_is_never_rate_limited` stays. Module docstring: "The rate limiter caps each client, including the public safeguards read, but never the pause and resume writes."
3. Run `uv run python -m pytest tests/core_test/infra/brokers/exness/test_exness_broker_adapter.py tests/app_test/integration/test_safeguards_api.py -q 2>&1 | tail -1`; it must show `failed` (the harness passes 5 arguments to a 4-argument constructor). This is the expected red.
4. `exness_safeguards.py`: delete `entries_paused`, `set_entries_paused`, the `logger` and its import; docstring: "One object per process, read by the Exness broker on every order. The caps come from the environment; the entry pause is stored in Mongo and read on every open."
5. `app/di/adapters.py`: `get_safeguards` becomes a plain `def get_safeguards(self, settings: Settings) -> Safeguards` without the repository and without `entries_paused`. `get_broker_factory` takes `safeguards_repository: SafeguardsRepository` and passes `safeguards_repository=safeguards_repository` to `BrokerFactory`.
6. `broker_factory.py`: `__init__` gains the required keyword `safeguards_repository: SafeguardsRepository` (no default) stored as `self._safeguards_repository`; the Exness branch passes it as the fifth argument. There is no `None` case and no new `ValueError`. Every test constructor passes it: `safeguards_repository=AsyncMock()` (paper-only tests never touch it) at `tests/core_test/infra/brokers/paper_broker_commission_test.py:152`, `tests/engine_test/test_async_broker_fill_wiring.py:163`, `tests/engine_test/test_contract_spec_wiring.py:66,256`, `tests/engine_test/test_live_trade_collector_integration.py:83`, `tests/engine_test/test_reconcile_restart_resume_integration.py:69`, `tests/engine_test/test_strategy_reject_delivery.py:102`, and the three in `test_exness_broker_factory.py` (step 10). Re-list them first with `git grep -n "BrokerFactory(" -- tests`; Phase 03 may shift lines. <!-- Red team 2026-10-28: #14 -->
7. `exness_broker_adapter.py`: `__init__` takes `safeguards_repository: SafeguardsRepository` (import from `pocketquant.core.infra.persistence.repositories.safeguards_repository`) as `self._safeguards_repo`. At the top of `_submit_open`: `try: paused = await self._safeguards_repo.load_entries_paused()`; on any `Exception` log `logger.warning("exness.order_rejected_presubmit", reason="pause_unreadable", subscription_id=..., symbol=...)` and return `_rejected(order, "entries pause unreadable")`; when `paused`, log the existing `reason="entries_paused"` WARNING and return `_rejected(order, "entries paused")`. Delete the pause branch from `_presubmit_reason`. Docstring lines 12-14: "The caps are read from the shared ``Safeguards``; the entry pause is read from the store on every open, and an unreadable store refuses the open."
8. `app/routes/safeguards.py`: GET takes `request: Request` (FastAPI), `safeguards` and `repo`, and returns `asdict(safeguards) | {"entries_paused": <paused>}`, where `<paused>` comes from a per-app cache no older than 1 s: module constant `_READ_CACHE_S = 1.0`; `cached = getattr(request.app.state, "entries_paused_read", None)`; when `cached is None or time.monotonic() - cached[0] > _READ_CACHE_S`, read `await repo.load_entries_paused()` and store `(time.monotonic(), value)` in `request.app.state.entries_paused_read`. Comment: "The read is public: at most one store read per second per process, so a flood cannot load the store the open path reads." The cache lives on `app.state` (one per app, so test apps never share it); the open path never uses it. `_set_entries_paused(request, safeguards, repo, *, paused)`: `try: await repo.save_entries_paused(paused)` / `except Exception: logger.warning("exness.safeguards.pause_store_failed", paused=paused); raise HTTPException(status_code=503, detail="pause not stored")`; on success set `request.app.state.entries_paused_read = (time.monotonic(), paused)`, log WARNING `exness.safeguards.entries_paused` or `exness.safeguards.entries_resumed` (the events moved from `Safeguards`) and return the GET body. Both POST routes take `request: Request` and pass it. Delete the "in-memory flag flips first" comment. Module docstring: "flip the stored entry pause; a failed store write returns 503; the public read is cached for one second". <!-- Red team 2026-10-28: #8 -->
8a. `core/common/rate_limit/middleware.py`: the exemption covers writes only: `if request.method == "POST" and request.url.path.startswith(_UNLIMITED_PREFIX): return await call_next(request)`; comment "Pause and resume must work while the API is flooded; the public read is limited like any route." <!-- Red team 2026-10-28: #8 -->
9. `app/di/services.py`: delete the comment line `# Taking the safeguards also loads the stored entry pause before bootstrap.`
10. `tests/core_test/infra/brokers/exness/test_exness_broker_factory.py`: all three `BrokerFactory(...)` calls (`:28`, `:32`, `:40`) pass `safeguards_repository=AsyncMock()` (import `AsyncMock` beside `MagicMock`); the built-when-live case still expects an `ExnessBrokerAdapter`. No `None` case is added. <!-- Red team 2026-10-28: #14 -->
11. Commit: `fix(exness): read the entry pause from the store on every open`.

**Success criteria:** the eight named tests pass (six pause tests, the cached read, the GET flood); no source file references `set_entries_paused` (the removed `Safeguards` method; the route helper `_set_entries_paused` stays); the POST route never changes in-memory pause state; `BrokerFactory` has no `None` default for the store. <!-- Red team 2026-10-28: #8 #14 -->

**Verify:** `uv run python -m pytest tests/core_test/infra/brokers tests/engine_test tests/app_test/integration/test_safeguards_api.py tests/core_test/unit/common/test_rate_limit_middleware.py -q > /dev/null 2>&1; echo "exit=$?"; git grep -n -E "(^|[^_])set_entries_paused|entries_paused=await|safeguards_repository: SafeguardsRepository \| None" -- src | wc -l | tr -d ' '` prints `exit=0` then `0`. <!-- Red team 2026-10-28: #8 #10 #14 --> <!-- Added 2026-10-29: Verify regex excluded the route helper named in step 8 -->

### Task 4.2 — Reject opposite entries; delete the Exness close path

**Goal:** an opposite-side entry is rejected on paper (risk check) and on Exness (adapter) and never becomes a close; `closePosition` is gone from `src` (D11, D30).

**Target files and symbols:** `RiskCheckHandler.validate` (`risk_check.py:14-47`); `ExnessBrokerAdapter.submit_order`, `_submit_open`, `_send_tracked`, `_recover_fill`, `_on_transaction`, `_apply_success`, `_finish`, `_complete`, `_Inflight`, `_early` (`exness_broker_adapter.py:80-92,118,199-244,317-370,397-409,488-505,534-584`); `_ENDPOINTS`, `_ORDER_OPS`, `_PRIORITY_OPS` (`exness_client.py:40-60`).

**Steps:**
1. Tests first. `tests/engine_test/test_risk_check.py`: add `test_an_opposite_entry_is_rejected` parametrized over `(PositionSide.LONG, Direction.SHORT)` and `(PositionSide.SHORT, Direction.LONG)`: an open position of that side plus a signal of that direction returns `(False, "opposite position open")`; add `test_a_same_side_entry_still_reaches_the_exposure_check`: LONG position, LONG signal, exposure under the cap returns `(True, "")`. `tests/engine_test/test_paper_position_lifecycle.py`: add `test_an_opposite_signal_keeps_the_paper_position`: with `_engine()` and a connected paper broker, open LONG for `"a"`, then call `engine._process_signal(engine.get_strategy("a"), <SHORT Signal for "a">, 100.0)` after `engine.load_strategy(_config("a"))`; assert `[p.side for p in await broker.get_positions()] == [PositionSide.LONG]` and `mirror.get("a").side == PositionSide.LONG`. `tests/core_test/infra/brokers/exness/test_exness_broker_adapter.py`: replace `test_opposite_order_closes_held_position` with `test_opposite_order_is_rejected_and_keeps_the_position`: `h, _ = await _holding_p1()`; a SELL of equal quantity returns `REJECTED` with `error_message == "position already open for subscription"`, 0 new client calls, `h.broker._held_for("sub1")` still set. Delete `test_exit_skips_stop_loss_and_loss_cap`, `test_exit_is_sent_while_the_snapshot_gate_is_closed`, `test_exit_must_close_the_whole_position`, `test_close_filled_before_ack_emits_trade_after_fill` (each reaches only the close path). `tests/core_test/infra/exness/test_exness_client.py`: in `test_order_calls_are_refused_while_live_trading_is_off` delete the `closePosition` half and assert only `opened.value.code == "LIVE_TRADING_DISABLED"`.
2. Run `uv run python -m pytest tests/engine_test/test_risk_check.py -q -k opposite 2>&1 | tail -1`; it must show `2 failed` (expected red).
3. `risk_check.py`: after `if position is None or position.is_closed: return True, ""`, add `if (signal.direction == Direction.LONG) != (position.side == PositionSide.LONG): return False, "opposite position open"` (import `PositionSide` from `pocketquant.core.domain.position`). Docstring: add "An entry against an open position is rejected: exits are SL/TP only."
4. `exness_broker_adapter.py`: `submit_order` keeps the market-order check and calls `_submit_open`. Move the held check into `_submit_open` right after the pause read: `if self._held_for(order.subscription_id) is not None: return _rejected(order, "position already open for subscription")` (any side). Delete `_Inflight.kind` and `_Inflight.position_id`; `_recover_fill` and `_on_transaction` match `d.get("type") == "open"`; `_apply_success` always maps the opened position and calls `await self._finish(rid, result)`; `_finish(rid, result)` and `_complete(result)` lose the `trade` parameter; `_early: dict[str, OrderResult]`; `_send_tracked(order, json_body)` keeps only the open call (`op="openPosition"`, no `path_params`, log `kind` removed). Keep `_Trade` (still used by `_emit_trade`, `_on_broker_close`, `_close_missing`). Docstring lines 6-9: "``openPosition`` is acknowledged asynchronously; the fill arrives on the events stream, or is recovered from the operation status and the deals history. Positions close only by venue SL/TP or a broker stop-out."
5. `exness_client.py`: delete the `closePosition` endpoint; `_ORDER_OPS = frozenset({"openPosition"})`.
6. Commit: `fix(trading): reject opposite-side entries and delete the exness close path`.

**Success criteria:** both layers reject an opposite entry with zero venue calls; `closePosition` and `kind="close"` appear nowhere in `src`.

**Verify:** `uv run python -m pytest tests/engine_test/test_risk_check.py tests/engine_test/test_paper_position_lifecycle.py tests/core_test/infra/brokers/exness tests/core_test/infra/exness -q > /dev/null 2>&1; echo "exit=$?"; git grep -n -E 'closePosition|kind="close"|inflight\.kind' -- src | wc -l | tr -d ' '` prints `exit=0` then `0`. <!-- Red team 2026-10-28: #10 -->

### Task 4.3 — One open in flight per subscription; lock only the check section

**Goal:** a second open for a subscription is rejected while its first is in flight; two subscriptions on one bar never interleave their checks, yet their `openPosition` sends overlap (D21).

**Target files and symbols:** `ExnessBrokerAdapter.__init__`, `_submit_open`, `_send_tracked`, `_presubmit_reason` (`exness_broker_adapter.py:98-128,216-263,317-370`).

**Steps:**
1. Tests first, new file `tests/core_test/infra/brokers/exness/test_exness_open_path.py` (import `_Harness`, `_order`, `_drain` from `tests.core_test.infra.brokers.exness.test_exness_broker_adapter`):
   - `test_a_second_open_for_a_subscription_is_rejected_while_the_first_is_in_flight`: first open ACKed, no fill; second `_order()` for `sub1` returns `REJECTED`, `error_message == "entry already in flight for subscription"`, `len(h.client.ops("openPosition")) == 1`; an order for `subscription_id="sub2"` is sent.
   - `test_check_sections_do_not_overlap`: wrap `h.broker._loss_cap_reason` so it records `("enter", sub)` then `await asyncio.sleep(0.05)` then `("exit", sub)`; submit `sub1` and `sub2` concurrently with `asyncio.gather`; the record is `enter, exit, enter, exit` (never two `enter` in a row).
   - `test_three_opens_send_concurrently`: set `h.client.on_order_call` to record `time.monotonic()` then `await asyncio.sleep(0.5)`; submit three orders for `sub1..sub3` with `asyncio.gather`; `max(starts) - min(starts) < 0.7` and total wall time `< 1.2` s.
2. Run `uv run python -m pytest tests/core_test/infra/brokers/exness/test_exness_open_path.py -q 2>&1 | tail -1`; it must show at least `1 failed` (expected red).
3. `__init__`: `self._open_lock = asyncio.Lock()`.
4. `_submit_open`: wrap everything up to and including registration in `async with self._open_lock:` in this order: stored pause read; held check; in-flight check `if any(i.order.subscription_id == order.subscription_id for i in self._inflight.values()): return _rejected(order, "entry already in flight for subscription")`; `_presubmit_reason`; stop-loss check; `_loss_cap_reason`; conditions and lot grid; build `body`; then `rid = str(order.id)`, `self._inflight[rid] = _Inflight(order, name, datetime.now(UTC))`, `self._pending_ack.add(rid)`. After the `async with` block: `return await self._send_tracked(order, body)`.
5. `_send_tracked`: delete the two registration lines (moved into the lock); the rest is unchanged.
6. Commit: `fix(exness): one open in flight per subscription under an account open lock`.

**Success criteria:** the three tests pass; the HTTP call is outside `_open_lock` (read the diff: `self._client.call("openPosition"` is not inside the `async with`).

**Verify:** `uv run python -m pytest tests/core_test/infra/brokers/exness -q > /dev/null 2>&1; echo "exit=$?"` prints `exit=0`.

### Task 4.4 — Cached balance and realized loss (M1)

**Goal:** with fresh caches the whole open path (balance, loss cap, conditions, open) makes exactly one REST call, `openPosition`; a close marks the loss cache stale so the next open re-reads or refuses.

**Target files and symbols:** `ExnessBrokerAdapter.connect`, `disconnect`, `_loss_cap_reason`, `_on_broker_close`, `_close_missing`, `get_balance` (`exness_broker_adapter.py:137-159,265-288,472-486,516-532,656-669`).

**Steps:**
1. Tests first, in `test_exness_open_path.py`:
   - `test_fresh_caches_make_one_call_per_open`: `h = await _Harness().start()`; `await h.broker._refresh_caches()`; clear `h.client.calls`; `await h.broker.get_balance()` then `await h.broker.submit_order(_order())`; `[op for op, _ in h.client.calls] == ["openPosition"]`.
   - `test_a_broker_close_makes_the_next_open_read_deals_first`: hold `p1` (`_holding_p1` pattern with `sub1`), refresh caches, deliver a broker close event for `p1` (copy the `transaction_event` shape of `test_broker_side_close_publishes_fill_then_trade`), clear calls, submit `_order(subscription_id="sub2")`; ops are `["getDealsHistory", "openPosition"]`.
   - `test_a_failed_deals_read_after_a_close_refuses_the_open`: same, with `h.client.deals_error = ExnessApiError(500, "X", "y")`; result `REJECTED`, `error_message` starts with `"daily loss check failed"`, no `openPosition`.
   - `test_an_old_balance_cache_is_read_again`: after `_refresh_caches()`, set the stored balance timestamp 91 s in the past; `get_balance()` makes one `getTradingStateSnapshot` call.
2. Run the file; it must show at least `1 failed` (`_refresh_caches` does not exist yet).
3. Module constant `_CACHE_MAX_AGE_S = 90`. Fields in `__init__`: `self._balance_cache: tuple[float, AccountBalance] | None = None` and `self._realized: tuple[float, date, float] | None = None` (monotonic time, UTC date, value; import `date` from `datetime`); `self._refresh_task: asyncio.Task[None] | None = None`.
4. Move today's `get_balance` body into `_read_balance()`. `get_balance()` returns the cached value when `time.monotonic() - stored_at < _CACHE_MAX_AGE_S`, else `await self._read_balance()`, stores it and returns it.
5. `_loss_cap_reason`: use `self._realized` when its date is today's UTC date and it is younger than `_CACHE_MAX_AGE_S`; otherwise `await self._realized_today()` (an `ExnessApiError` keeps returning `daily loss check failed: <code>`) and store the result. The cap comparison is unchanged.
6. `_refresh_caches()`: read balance and realized-today and store both; any exception logs `logger.warning("exness.cache_refresh_failed", error=str(e))` and leaves the caches as they are. `_refresh_loop()`: forever, sleep until second 30 of the next minute (`delay = (30 - now.second - now.microsecond / 1e6) % 60 or 60`), then `await self._refresh_caches()`. `connect` starts it with `asyncio.create_task`; `disconnect` cancels and awaits it (same pattern as `_stream_task`).
7. `_on_broker_close` and `_close_missing` set `self._realized = None` after emitting the trade. A comment at `_loss_cap_reason` states the cost: "after a close the next open reads the deals synchronously, about one paced data call (1-2 s)."
8. Commit: `perf(exness): cache balance and realized loss for the open path`.

**Success criteria:** four tests pass; the refresh adds 2 data calls per minute per process holding a connected Exness broker.

**Verify:** `uv run python -m pytest tests/core_test/infra/brokers/exness -q > /dev/null 2>&1; echo "exit=$?"` prints `exit=0`.

### Task 4.5 — Order calls pace in their own lane

**Goal:** order calls never queue behind data calls; three opens leave 0.3 s apart at fraction 0.6 (A5); the priority heap is deleted.

**Target files and symbols:** `min_request_interval` (`exness_client.py:116-120`), `_RequestPacer` (`:147-195`), `ExnessClient.__init__` (`:211-212`), `_send_paced` (`:289-312`), `_pacer_for` (`:348-356`), `_PRIORITY_OPS` (`:60`), module docstring (`:5-8`).

**Steps:**
1. Tests first, in `tests/core_test/infra/exness/test_exness_client.py`: delete `test_a_priority_waiter_goes_before_a_queued_one`; change every `pacer.wait(priority=...)` to `pacer.wait()`. The `_client(..., paced=False)` helper (`test_exness_client.py:119-126`) patches only `min_request_interval` today, so unpaced tests would pace order calls at 0.3 s: make it also run `monkeypatch.setattr(exness_client, "order_request_interval", lambda _limits, _fraction: 0.0)` inside the same `if not paced:` block. <!-- Red team 2026-10-28: #10 --> Add:
   - `test_order_request_interval_uses_the_order_limits`: with the fixture limits, `order_request_interval(limits, 0.6) == pytest.approx(0.3)` and `order_request_interval(limits, 0.05) == pytest.approx(2.4)` (global 0.12 / 0.05).
   - `test_order_calls_use_their_own_lane`: `client = _client(_Exness(), monkeypatch, paced=True, exness_rate_fraction=0.6)`; `order = await client._pacer_for("openPosition")`; `assert order is await client._pacer_for("getOperationStatus")`; `assert order.min_interval_s == pytest.approx(0.3)`; `data = await client._pacer_for("getCandleHistory")`; `assert data is not order and data.min_interval_s == pytest.approx(1.0)`.
   - `test_three_order_waits_leave_point_three_apart`: `_RequestPacer(0.3, clock=clock, sleep=advance)` with the `_fake_time` helper; three `wait()` calls start at `0.0, 0.3, 0.6` (`pytest.approx`).
2. Run `uv run python -m pytest tests/core_test/infra/exness/test_exness_client.py -q 2>&1 | tail -1`; it must show `failed` (expected red).
3. `_RequestPacer`: replace the heap with one `asyncio.Lock` (FIFO): `async def wait(self) -> None: async with self._lock: delay = self._next_at - self._clock(); if delay > 0: await self._sleep(delay); self._next_at = self._clock() + self.min_interval_s`. Delete `_busy`, `_queue`, `_seq`, `_release` and the `heapq`/`itertools` imports. Docstring: "Lets requests leave one at a time, at least ``min_interval_s`` apart, in arrival order."
4. Add `order_request_interval(limits, fraction) -> float` next to `min_request_interval`: `own = max(window/limit for the methods openPosition and getOperationStatus) * 1.2`; `shared = global window/limit * 1.2 / fraction`; return `max(own, shared)`. Comment: "Only the trader sends order calls, so their own limits are not scaled by the fraction; the account-wide limit is."
5. `ExnessClient.__init__`: `self._pacer` becomes `self._data_pacer: _RequestPacer | None = None` and add `self._order_pacer: _RequestPacer | None = None`. `_pacer_for(op)`: bootstrap ops use the bootstrap pacer; otherwise build both lanes once from `await self.limits()` (`_data_pacer` = `min_request_interval / fraction`, `_order_pacer` = `order_request_interval(limits, fraction)`), then return `_order_pacer` for `op in _PRIORITY_OPS`, else `_data_pacer`. `_send_paced` calls `await pacer.wait()`. Update `test_the_rate_fraction_widens_the_pacer_interval` only if it reads `client._pacer` directly.
6. Module docstring lines 5-7: replace "Requests are spaced by the strictest published rate with headroom" with "Data calls are spaced by the strictest published rate with headroom; order calls have their own lane".
7. Commit: `perf(exness): pace order calls in their own lane`.

**Success criteria:** the three new tests pass; `heapq` and `priority=` are gone from `exness_client.py`.

**Verify:** `uv run python -m pytest tests/core_test/infra/exness -q > /dev/null 2>&1; echo "exit=$?"; git grep -n -E "heapq|priority=" -- src/pocketquant/core/infra/exness/exness_client.py | wc -l | tr -d ' '` prints `exit=0` then `0`. <!-- Red team 2026-10-28: #10 -->

<!-- Red team 2026-10-28: #5 -->
### Task 4.6 — An order never leaves after its deadline

**Goal:** the caller's deadline (the trader's `trading_until`, wired by Phase 06) is checked again after the account open lock and after the order-lane pacer wait, right before the request is sent; a transport failure is never resent after the deadline. A lost lease therefore cannot send an order that waited on the lock, a synchronous loss-cap read or the pacer. `None` means no deadline (backtests and direct calls).

**Target files and symbols:** `IBrokerPort.submit_order` (`broker_port.py:43-53`); `PaperBrokerAdapter.submit_order` (`paper_broker_adapter.py:154`); `OrderAppService.submit` (`order_app_service.py:37-53`); `ExnessBrokerAdapter.submit_order`, `_submit_open`, `_send_tracked`; `ExnessClient.call`, `_send_paced`, `_send` (`exness_client.py:248-334`); the two test fakes (`tests/engine_test/test_async_broker_fill_wiring.py:67`, `tests/engine_test/test_strategy_reject_delivery.py:73`).

**Steps:**
1. Tests first. The clock is `get_current_time()` from `pocketquant.core.common.time.simulation`; every test calls `clear_simulation_time()` in a `finally`. The simulated time is a `ContextVar`, so each test moves it from code that runs inside the submitting task (a hook), never from the test body after the task started.
   - In `tests/core_test/infra/brokers/exness/test_exness_open_path.py`, `test_an_order_whose_deadline_passes_inside_the_open_lock_is_not_registered`: `h = await _Harness().start()`; `set_simulation_time(T)`; wrap `h.broker._loss_cap_reason` so it calls `set_simulation_time(T + 2 s)` and then the original; `await h.broker.submit_order(_order(), deadline=T + 1 s)` returns `REJECTED` with `error_message == "order deadline passed"`; `h.client.ops("openPosition") == []`; `h.broker._inflight == {}`; one captured log `exness.order_rejected_presubmit` with `reason == "deadline"`.
   - Same file, `test_an_order_inside_its_deadline_is_sent`: deadline `T + 60 s`, no hook; one `openPosition`.
   - In `tests/core_test/infra/exness/test_exness_client.py`, `test_an_order_whose_deadline_passes_during_the_pacer_wait_is_not_sent`: `exness = _Exness()`; `client = _client(exness, monkeypatch, exness_live_trading=True)`; `set_simulation_time(T)`; replace the order lane's `wait` with an async function that calls `set_simulation_time(T + 2 s)` (`pacer = await client._pacer_for("openPosition")`; `monkeypatch.setattr(pacer, "wait", ...)`); `await client.call("openPosition", json_body={...}, idempotency_key="k", deadline=T + 1 s)` raises `ExnessApiError` with `code == "ORDER_DEADLINE"`; `[r for r in exness.other() if r.method == "POST"] == []`.
   - Same file, `test_a_transport_error_is_not_resent_after_the_deadline` (uses the `sleeps` fixture): `_Exness([httpx.ConnectError("boom"), httpx.Response(202, json={"ok": True})])`; `set_simulation_time(T)`; `sleeps.side_effect = lambda _s: set_simulation_time(T + 2 s)`; the call with `deadline=T + 1 s` raises `ExnessApiError` with `code == "TRANSPORT"` (so the adapter still reconciles: the first request may have reached the venue); `len([r for r in exness.other() if r.method == "POST"]) == 1`. The existing `test_a_transport_error_is_retried_with_the_same_idempotency_key` (no deadline) still passes.
2. Run `uv run python -m pytest tests/core_test/infra/brokers/exness/test_exness_open_path.py tests/core_test/infra/exness/test_exness_client.py -q -k deadline 2>&1 | tail -1`; it must show `failed` (expected red).
3. `broker_port.py`: `async def submit_order(self, order: OrderAggregate, *, deadline: datetime | None = None) -> OrderResult`; docstring adds "deadline: the trader's trading_until; the order is not sent at or after it. None = no deadline (backtests, direct calls)." The paper adapter and both test fakes take the same keyword and ignore it (paper fills inline, under the engine's own fence). `OrderAppService.submit(order, broker, *, deadline: datetime | None = None)` passes `deadline=deadline` to `broker.submit_order`.
4. `exness_broker_adapter.py`: `submit_order(order, *, deadline=None)` passes `deadline` to `_submit_open`. Inside `async with self._open_lock:`, as the last check before registration (after the loss-cap read and the conditions): `if deadline is not None and get_current_time() >= deadline:` log WARNING `exness.order_rejected_presubmit reason=deadline subscription_id=... symbol=...` and return `_rejected(order, "order deadline passed")`. `_send_tracked(order, body, deadline)` passes `deadline=deadline` to `self._client.call`. An `ExnessApiError` with code `ORDER_DEADLINE` takes the existing non-transport branch (pop `_inflight`, WARNING `exness.order_rejected`, return rejected).
5. `exness_client.py`: `call(..., deadline: datetime | None = None)` passes it to `_send_paced(op, method, url, body, idempotency_key, deadline)`. After `await pacer.wait()`: `if deadline is not None and get_current_time() >= deadline: raise ExnessApiError(0, "ORDER_DEADLINE", f"{op} deadline passed before send")`. `_send(..., deadline)`: in the `except httpx.TransportError` branch, raise the existing `ExnessApiError(0, "TRANSPORT", ...)` also when `deadline is not None and get_current_time() >= deadline` after the backoff sleep, before the next attempt. Docstring of `_send`: "transport failures retried with the same idempotency key, never after the deadline".
6. Commit: `fix(exness): never send or resend an order after the trading deadline`.

**Success criteria:** the four new tests pass; an order past its deadline makes no `openPosition` request; a pre-deadline transport failure still resends.

**Verify:** `uv run python -m pytest tests/core_test/infra/brokers tests/core_test/infra/exness tests/engine_test -q > /dev/null 2>&1; echo "exit=$?"; git grep -n "ORDER_DEADLINE" -- src | wc -l | tr -d ' '` prints `exit=0` then a number `>= 1`.

### Task 4.7 — Gates, push `develop`, CI green

**Goal:** the phase lands on `develop` with every local gate and CI green; no deploy.

**Target files and symbols:** none new; `pyproject.toml` `[tool.code-metrics]` only if the ratchet trips.

**Steps:**
1. `uv run ruff check src tests` prints `All checks passed!`; `uv run ruff format --check src tests` exits 0; `uv run pyright` prints `0 errors`.
2. `uv run lint-imports | tail -1` prints `Contracts: 6 kept, 0 broken.`
3. `uv run python scripts/code_metrics.py --ratchet; echo "exit=$?"` prints `exit=0`. If it fails on a ceiling, raise that ceiling in `[tool.code-metrics]` in its own commit `chore(metrics): raise the code-metrics ceiling for the exness open path` and note the old and new value in the phase summary. Never pad or split code to pass it.
4. Full suite (Verify below).
5. Push: `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin && test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `pushed`.
6. CI: `sleep 15; export GH_TOKEN=$(gh auth token --user camping89); RUN_ID=$(gh run list --workflow cicd.yml --branch develop --limit 5 --json databaseId,headSha -q ".[] | select(.headSha==\"$(git rev-parse HEAD)\") | .databaseId" | head -1); gh run watch "$RUN_ID" --exit-status > /dev/null 2>&1; gh run view "$RUN_ID" --json conclusion -q .conclusion` prints `success`.

**Success criteria:** local red is exactly the known Windows red; CI on the pushed `develop` HEAD concludes `success`.

**Verify:** `uv run python -m pytest tests/ -q > .cache/pytest-full.log 2>&1; tail -1 .cache/pytest-full.log; grep -E "^(FAILED|ERROR) " .cache/pytest-full.log | grep -vcE "test_utc_runtime_guard|test_cron_trigger_timezone"` prints a summary line containing `4 failed` and `4 errors`, then `0`.

## Rollback

Nothing is deployed. Revert the phase commits on `develop` with `git revert --no-edit <sha>..HEAD` and push `develop`. The safeguards document keeps its shape (`entries_paused`, `updated_at`), so the reverted code reads the same stored pause.

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
